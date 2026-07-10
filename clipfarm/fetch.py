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


def download_chat(vod_url: str, dest: Path,
                  duration: float, stride: float = 30.0
                  ) -> list[tuple[float, float]]:
    """Chat DENSITY samples -> [(t_seconds, msgs_per_sec)] via Twitch's
    public GQL comments API. One query returns a ~5s page around an offset,
    so a full crawl of a 4h VOD is thousands of requests — but the velocity
    signal only needs density, so we sample a page every `stride` seconds in
    parallel. Cached as JSON. Volume only; sarcasm breaks chat sentiment."""
    if dest.exists():
        return [tuple(x) for x in json.loads(dest.read_text())]
    import requests
    from concurrent.futures import ThreadPoolExecutor
    vid = vod_url.rstrip("/").rsplit("/", 1)[-1]
    gql = "https://gql.twitch.tv/gql"
    headers = {"Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko"}
    sha = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"

    def _sample(off: float) -> tuple[float, float] | None:
        payload = {
            "operationName": "VideoCommentsByOffsetOrCursor",
            "variables": {"videoID": vid, "contentOffsetSeconds": int(off)},
            "extensions": {"persistedQuery": {"version": 1,
                                              "sha256Hash": sha}},
        }
        try:
            r = requests.post(gql, json=payload, headers=headers, timeout=20)
            edges = (((r.json().get("data") or {}).get("video") or {})
                     .get("comments") or {}).get("edges") or []
            ts = [float(e["node"]["contentOffsetSeconds"]) for e in edges]
            if len(ts) < 2 or ts[-1] <= ts[0]:
                return (off, 0.0)
            return (off, len(ts) / (ts[-1] - ts[0]))
        except Exception:
            return None

    offsets = [o * stride for o in range(int(duration // stride) + 1)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        msgs = [s for s in ex.map(_sample, offsets) if s is not None]
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(msgs))
    tmp.replace(dest)
    return msgs


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
