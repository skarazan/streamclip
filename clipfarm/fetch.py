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


def latest_vod_url(twitch_url: str) -> tuple[str, str]:
    """Return (url, title) of the most recent VOD on the channel."""
    out = _run([
        "yt-dlp", "--flat-playlist", "--playlist-end", "1", "-J",
        f"{twitch_url.rstrip('/')}/videos?filter=archives&sort=time",
    ])
    data = json.loads(out)
    entries = data.get("entries") or []
    if not entries:
        raise RuntimeError(f"No VODs found on {twitch_url}")
    e = entries[0]
    return e["url"], e.get("title", "stream")


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
