"""Find latest VOD and download audio / video segments via yt-dlp."""

import json
import subprocess
import time
from pathlib import Path

from .config import ffmpeg_path


def _run(cmd: list[str], timeout: int = 1800) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r.stdout


class SegmentUnavailable(RuntimeError):
    """Twitch would not serve this range's media after every available route."""


# Browsers get served; bare library user-agents get scrutinised. yt-dlp sends
# this by default and we match it on the paths where we do our own HTTP.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

# A real multi-second segment is never this small. ffmpeg writes a valid but
# STREAM-LESS mp4 (observed: 262 bytes) and exits 0 when every HLS fragment
# fails, so a zero return code proves nothing about the media.
_MIN_SEGMENT_BYTES = 50_000
_MIN_AUDIO_BYTES = 100_000


def _has_video_stream(path: Path) -> bool:
    probe = str(Path(ffmpeg_path()).parent / "ffprobe")
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0",
             str(path)],
            capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return False
    return "video" in out


def _validate_media(path: Path, min_bytes: int, *, need_video: bool) -> None:
    """Refuse an empty container. ffmpeg's exit code cannot be trusted here —
    this is the check that turns a silent husk into a real failure."""
    size = path.stat().st_size if path.exists() else 0
    if size < min_bytes:
        raise SegmentUnavailable(
            f"{path.name}: stream-less download ({size} bytes) — Twitch served "
            f"no media for this range")
    if need_video and not _has_video_stream(path):
        raise SegmentUnavailable(
            f"{path.name}: container has no video stream ({size} bytes)")


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
    _validate_media(files[0], _MIN_AUDIO_BYTES, need_video=False)
    return files[0]


def media_reachable(vod_url: str, duration_s: float,
                    quality: str = "worst") -> tuple[bool, str]:
    """Can we fetch ANY video for this VOD? Returns (ok, reason).

    Segment download is step 7 of the pipeline, after transcription and the
    paid LLM scoring pass. When Twitch refuses media to this egress IP, that
    ordering burned ~13 minutes and a full scoring bill per attempt before
    finding out. Six seconds at the lowest rendition answers the same
    question first.
    """
    import tempfile

    at = max(0.0, min(duration_s * 0.5, max(0.0, duration_s - 30.0)))
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "reach.mp4"
        try:
            download_segment(vod_url, at, at + 6.0, probe, quality,
                             attempts=1)
        except Exception as e:                              # noqa: BLE001
            return False, str(e)[:300]
    return True, ""


def _ytdlp_segment(vod_url: str, start: float, end: float, dest: Path,
                   quality: str) -> Path:
    """The fast path: yt-dlp cuts exactly at the requested bounds.

    `--download-sections` makes yt-dlp hand the playlist to the FFMPEG
    downloader (verified: "Invoking ffmpeg downloader"), and `--downloader`
    cannot override that. ffmpeg's HLS reader has no per-fragment retry, so
    `--retries` below governs a downloader that isn't running — one refused
    fragment is fatal here. That is why the fallback exists.
    """
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
            raise SegmentUnavailable("segment download produced no file")
        return candidates[0]
    return dest


def _playlist_url(vod_url: str, quality: str) -> str:
    """Resolve the rendition's media playlist. yt-dlp owns format selection —
    we only want the URL it picked."""
    out = _run(["yt-dlp", "-f", quality, "--no-download",
                "--print", "%(url)s", vod_url], timeout=120)
    urls = [line.strip() for line in out.splitlines() if line.strip()]
    if not urls:
        raise SegmentUnavailable("could not resolve a media playlist URL")
    return urls[-1]


def _fragment_segment(vod_url: str, start: float, end: float, dest: Path,
                      quality: str, tries: int = 3) -> Path:
    """Fallback: fetch the covering HLS fragments ourselves, then cut.

    This is deliberately the shape of `download_audio`, which keeps working
    from Modal's egress while the ffmpeg path returns husks for the same VOD:
    fetch each fragment over plain HTTP and RETRY it. CloudFront's refusals
    are intermittent, so a retried fragment usually lands.
    """
    import re

    import httpx

    playlist = _playlist_url(vod_url, quality)
    base = playlist.rsplit("/", 1)[0] + "/"
    with httpx.Client(timeout=30, headers={"User-Agent": _UA},
                      follow_redirects=True) as client:
        def _get(name: str) -> bytes:
            last = ""
            for attempt in range(tries):
                try:
                    r = client.get(base + name)
                    if r.status_code == 200 and r.content:
                        return r.content
                    last = f"HTTP {r.status_code}"
                except Exception as e:                     # noqa: BLE001
                    last = f"{type(e).__name__}"
                time.sleep(1.5 * (attempt + 1))
            raise SegmentUnavailable(f"fragment {name}: {last}")

        text = _get(playlist.rsplit("/", 1)[-1]).decode("utf-8", "replace")
        init = next((m.group(1) for m in
                     (re.search(r'URI="([^"]+)"', line) for line in
                      text.splitlines() if line.startswith("#EXT-X-MAP"))
                     if m), None)
        timeline, clock, pending = [], 0.0, None
        for line in text.splitlines():
            if line.startswith("#EXTINF"):
                pending = float(re.match(r"#EXTINF:([\d.]+)", line).group(1))
            elif line and not line.startswith("#") and pending is not None:
                timeline.append((clock, pending, line))
                clock += pending
                pending = None
        covering = [f for f in timeline if f[0] < end and f[0] + f[1] > start]
        if not covering:
            raise SegmentUnavailable(
                f"no fragments cover {start:.0f}-{end:.0f}s "
                f"(playlist is {clock:.0f}s long)")

        # fMP4: the init segment followed by media segments is a valid stream,
        # so a byte concat is all the muxing this needs.
        blob = dest.with_name(dest.stem + ".frags.mp4")
        with blob.open("wb") as out:
            for name in ([init] if init else []) + [f[2] for f in covering]:
                out.write(_get(name))

    # Re-encode to land exactly on the requested bounds, matching what
    # --force-keyframes-at-cuts gave the fast path.
    offset = max(0.0, start - covering[0][0])
    r = subprocess.run(
        [ffmpeg_path(), "-y", "-v", "error", "-ss", f"{offset:.3f}",
         "-i", str(blob), "-t", f"{end - start:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         str(dest)],
        capture_output=True, text=True)
    blob.unlink(missing_ok=True)
    if r.returncode != 0:
        raise SegmentUnavailable(f"fragment cut failed: {r.stderr[-400:]}")
    return dest


def download_segment(vod_url: str, start: float, end: float, dest: Path,
                     quality: str, attempts: int = 2) -> Path:
    """Download only [start, end] of the VOD as video, cut exactly at bounds.

    Twitch serves stream-less husks to some egress IPs. Every route is
    validated before it counts as success, and the caller gets an exception
    instead of an empty file that breaks a later stage.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    problems = []
    for attempt in range(attempts):
        try:
            got = _ytdlp_segment(vod_url, start, end, dest, quality)
            _validate_media(got, _MIN_SEGMENT_BYTES, need_video=True)
            return got
        except (SegmentUnavailable, RuntimeError) as e:
            problems.append(f"yt-dlp#{attempt + 1}: {str(e)[:160]}")
            dest.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(2.0 * (attempt + 1))
    try:
        got = _fragment_segment(vod_url, start, end, dest, quality)
        _validate_media(got, _MIN_SEGMENT_BYTES, need_video=True)
        return got
    except (SegmentUnavailable, RuntimeError) as e:
        problems.append(f"fragments: {str(e)[:160]}")
        dest.unlink(missing_ok=True)
    raise SegmentUnavailable(
        f"{start:.0f}-{end:.0f}s unavailable after every route — "
        + " | ".join(problems))
