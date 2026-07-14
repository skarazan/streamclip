"""Find latest VOD and download audio / video segments via yt-dlp."""

import json
import subprocess
from pathlib import Path

from .config import ffmpeg_path


def _run(cmd: list[str], timeout: int = 1800) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r.stdout


_GQL = "https://gql.twitch.tv/gql"
_GQL_HEADERS = {"Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}
_GQL_SHA = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"


def _chat_page(vid: str, offset: int) -> list[tuple[float, str]]:
    import requests
    payload = {
        "operationName": "VideoCommentsByOffsetOrCursor",
        "variables": {"videoID": vid, "contentOffsetSeconds": int(offset)},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": _GQL_SHA}},
    }
    r = requests.post(_GQL, json=payload, headers=_GQL_HEADERS, timeout=20)
    edges = (((r.json().get("data") or {}).get("video") or {})
             .get("comments") or {}).get("edges") or []
    out = []
    for e in edges:
        node = e["node"]
        text = "".join(f.get("text", "")
                       for f in node["message"].get("fragments", []))
        out.append((float(node["contentOffsetSeconds"]), text))
    return out


def download_chat(vod_url: str, dest: Path, duration: float,
                  stride: float = 30.0, full_page_budget: int = 150) -> dict:
    """Chat replay, adaptive: SMALL channels get a FULL message crawl (a page
    is ~50 messages regardless of time span, so slow chat = few pages = the
    whole chat for free — exactly the customers whose signal is scarce). Big
    channels fall back to density sampling (a page per `stride` seconds).
    Returns {"density": [(t, msgs_per_sec)], "texts": [(t, msg)] | [],
    "full": bool}. Cached as JSON (v2)."""
    if dest.exists():
        d = json.loads(dest.read_text())
        if isinstance(d, dict) and d.get("v") == 2:
            return d
        if isinstance(d, list):  # v1 cache: density-only
            return {"v": 2, "density": [tuple(x) for x in d],
                    "texts": [], "full": False}
    import requests  # noqa: F401  (used via _chat_page)
    from concurrent.futures import ThreadPoolExecutor
    vid = vod_url.rstrip("/").rsplit("/", 1)[-1]

    # attempt full offset-walk within the page budget
    texts: list[tuple[float, str]] = []
    offset, full = 0, True
    for _ in range(full_page_budget):
        try:
            page = _chat_page(vid, offset)
        except Exception:
            page = []
        if not page:
            break
        texts.extend(p for p in page if p[0] > (texts[-1][0] if texts else -1))
        last = page[-1][0]
        if last >= duration - 5:
            break
        if last <= offset:
            offset += 10
        else:
            offset = int(last) + 1
    else:
        full = False  # budget exhausted: chat too busy for a full crawl

    if full and texts:
        # density derived directly from the complete message list
        import numpy as _np
        counts = _np.zeros(int(duration // stride) + 1)
        for t, _m in texts:
            if t < duration + stride:
                counts[min(int(t // stride), len(counts) - 1)] += 1
        density = [(i * stride, c / stride) for i, c in enumerate(counts)]
    else:
        # busy chat: sampled density (as before), keep sampled texts for
        # emote/callout analysis (partial coverage, still useful)
        texts = []

        def _sample(off: float):
            try:
                page = _chat_page(vid, int(off))
                if len(page) < 2 or page[-1][0] <= page[0][0]:
                    return (off, 0.0, page)
                return (off, len(page) / (page[-1][0] - page[0][0]), page)
            except Exception:
                return None
        offsets = [o * stride for o in range(int(duration // stride) + 1)]
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = [s for s in ex.map(_sample, offsets) if s is not None]
        density = [(off, rate) for off, rate, _ in res]
        for _off, _rate, page in res:
            texts.extend(page)
        texts.sort(key=lambda x: x[0])

    out = {"v": 2, "density": density, "texts": texts, "full": full}
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(dest)
    return out


def list_vods(twitch_url: str, n: int = 1) -> list[tuple[str, str]]:
    """Return [(url, title)] for the n most recent archived VODs, newest first."""
    out = _run([
        "yt-dlp", "--flat-playlist", "--playlist-end", str(n), "-J",
        f"{twitch_url.rstrip('/')}/videos?filter=archives&sort=time",
    ])
    data = json.loads(out)
    entries = data.get("entries") or []
    return [(e["url"], e.get("title", "stream")) for e in entries]


def latest_vod_url(twitch_url: str) -> tuple[str, str]:
    """Return (url, title) of the most recent VOD on the channel."""
    vods = list_vods(twitch_url, 1)
    if not vods:
        raise RuntimeError(f"No VODs found on {twitch_url}")
    return vods[0]


def vod_info(vod_url: str) -> dict:
    """Cheap metadata probe: {live, duration_s}. Run before committing a
    worker — liveness stalls processing, duration drives credit cost."""
    out = _run(["yt-dlp", "-J", "--no-download", vod_url], timeout=120)
    info = json.loads(out)
    # post_live = stream ended but Twitch hasn't finalized the VOD;
    # yt-dlp falls back to serial ffmpeg-HLS at ~1x realtime for those.
    # NOTE: a VOD listed while live also reports partial duration.
    return {
        "live": bool(info.get("is_live")
                     or info.get("live_status") in ("is_live", "post_live")),
        "duration_s": float(info.get("duration") or 0),
        "channel": (info.get("uploader_id") or info.get("uploader")
                    or info.get("channel") or "").lower(),
    }


def vod_still_live(vod_url: str) -> bool:
    return vod_info(vod_url)["live"]


def download_audio(vod_url: str, dest_dir: Path) -> Path:
    """Download audio-only track (small — a few hundred MB for a long stream)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(dest_dir / "vod_audio.%(ext)s")
    _run([
        "yt-dlp", "-f", "Audio_Only/bestaudio/worst",
        "--downloader", "m3u8:native",
        "--concurrent-fragments", "8",
        "--socket-timeout", "30", "--retries", "5",
        "-o", out_tmpl, vod_url,
    ])
    files = sorted(f for f in dest_dir.glob("vod_audio.*")
                   if not f.name.endswith((".part", ".ytdl")))
    if not files:
        raise RuntimeError("audio download produced no file")
    return files[0]


def download_segment(vod_url: str, start: float, end: float, dest: Path,
                     quality: str) -> Path:
    """Download only [start, end] of the VOD as video, cut exactly at bounds."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    section = f"*{start:.2f}-{end:.2f}"
    _run([
        "yt-dlp", "-f", quality,
        "--ffmpeg-location", ffmpeg_path(),
        "--socket-timeout", "30", "--retries", "5",
        "--download-sections", section,
        "--force-keyframes-at-cuts",   # re-encodes at cuts => exact boundaries
        "--no-part",
        "-o", str(dest),
        vod_url,
    ])
    if not dest.exists():
        # yt-dlp may append extension
        candidates = list(dest.parent.glob(dest.stem + ".*"))
        if not candidates:
            raise RuntimeError("segment download produced no file")
        return candidates[0]
    return dest
