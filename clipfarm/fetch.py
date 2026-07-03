"""Find latest VOD and download audio / video segments via yt-dlp."""

import json
import subprocess
from pathlib import Path

from .config import ffmpeg_path


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
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


def download_audio(vod_url: str, dest_dir: Path) -> Path:
    """Download audio-only track (small — a few hundred MB for a long stream)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(dest_dir / "vod_audio.%(ext)s")
    _run([
        "yt-dlp", "-f", "Audio_Only/bestaudio/worst",
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
