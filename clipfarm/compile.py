"""Compile the best recent clips into one long-form 16:9 video.

Long-form watch-time (not Shorts) is what counts toward YouTube monetization,
so this stitches a "funniest moments" comp from clips already picked+scored by
the pipeline. Reuses their timestamps to re-download native-landscape source,
captions each with Groq, burns a countdown badge, concatenates, and writes a
YouTube title + description with chapter timestamps.

Run:  python -m clipfarm.compile --days 14 --count 12 --title "CaseOh's Funniest Moments"
Reads clips from Supabase (same env as worker). Output in out/compilations/.
"""

import argparse
import datetime
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import fetch, render, transcribe
from .config import PROJECT_ROOT, ffmpeg_path

W, H = 1920, 1080

# captions tuned for landscape: lower, a touch smaller, bottom-center
COMP_STYLE = {
    "font": "Montserrat ExtraBold",
    "font_size": 56,
    "primary_color": "&H00FFFFFF",
    "highlight_color": "&H0000FFFF",
    "outline_color": "&H00000000",
    "outline": 4,
    "border_style": 1,
    "caption_pos": 0.88,
    "words_per_line": 4,
    "uppercase": True,
    "hook": {},
    "watermark": {},
}


def _sb(path: str, **kw) -> list:
    key = os.environ["SUPABASE_SERVICE_KEY"]
    r = httpx.get(os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1" + path,
                  headers={"apikey": key, "Authorization": f"Bearer {key}"},
                  timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def pick_clips(user_id: str, days: int, count: int, min_score: float,
               channel: str | None = None) -> list[dict]:
    """Top clips in the window, best first, de-duplicated by source moment.
    Embeds the parent job's vod_url so segments can be re-downloaded.
    `channel` (twitch login) keeps a comp to one streamer — in production one
    account is one streamer, but a shared/test account mixes them."""
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = _sb(f"/clips?user_id=eq.{user_id}"
               f"&created_at=gte.{since}&score=gte.{min_score}"
               f"&select=title,hook,score,start_s,end_s,job_id,jobs(vod_url)"
               f"&order=score.desc")
    chan_cache: dict[str, str] = {}

    def _chan(vod: str) -> str:
        if vod not in chan_cache:
            try:
                chan_cache[vod] = fetch.vod_info(vod)["channel"]
            except Exception:
                chan_cache[vod] = ""
        return chan_cache[vod]

    want = (channel or "").lower().lstrip("@")
    seen, out = set(), []
    for r in rows:
        vod = (r.get("jobs") or {}).get("vod_url")
        if not vod:
            continue
        if want and _chan(vod) != want:
            continue
        # same moment can be re-clipped across runs; keep one per (vod, ~start)
        k = (vod, round(r["start_s"] / 5))
        if k in seen:
            continue
        seen.add(k)
        r["vod_url"] = vod
        out.append(r)
        if len(out) >= count:
            break
    return out


def _ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def compile_video(user_id: str, title: str, days: int = 14, count: int = 12,
                  min_score: float = 8.0, quality: str = "best[height<=1080]",
                  countdown: bool = True, channel: str | None = None) -> dict:
    clips = pick_clips(user_id, days, count, min_score, channel=channel)
    if not clips:
        raise SystemExit(f"No clips scoring >= {min_score} in the last {days} days.")
    # countdown format (worst-to-best) keeps viewers watching for #1
    clips = list(reversed(clips))  # DB gave best-first; play best last
    print(f"Compiling {len(clips)} clips into '{title}'")

    out_dir = PROJECT_ROOT / "out" / "compilations"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    work = Path(tempfile.mkdtemp(prefix="comp_"))

    rendered, chapters, cursor = [], [], 0.0
    n = len(clips)
    for i, c in enumerate(clips):
        rank = n - i  # #N countdown
        seg = work / f"seg_{i:02d}.mp4"
        print(f"[{i + 1}/{n}] #{rank} {c['title']} "
              f"({c['start_s']:.0f}-{c['end_s']:.0f}s)")
        fetch.download_segment(c["vod_url"], c["start_s"], c["end_s"], seg, quality)
        words = transcribe.transcribe_clips_groq(
            [(seg, c["start_s"])],
            context="Twitch gaming stream. Loud casual speech, screaming, slang.")[0]
        ass = render.build_ass(words, c["start_s"], c["end_s"], COMP_STYLE,
                               work / f"seg_{i:02d}.ass", res=(W, H))
        final = work / f"final_{i:02d}.mp4"
        render.render_landscape(seg, ass, final,
                                badge=f"#{rank}" if countdown else None)
        rendered.append(final)
        chapters.append((cursor, rank, c["title"]))
        cursor += c["end_s"] - c["start_s"]
        seg.unlink(missing_ok=True)

    # concat (uniform params from render_landscape -> stream copy, instant)
    listfile = work / "concat.txt"
    listfile.write_text("".join(f"file '{f}'\n" for f in rendered))
    out_video = out_dir / f"{stamp}_{_slug(title)}.mp4"
    r = subprocess.run(
        [ffmpeg_path(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", "-movflags", "+faststart",
         str(out_video)],
        capture_output=True, text=True)
    if r.returncode != 0:
        # fallback: re-encode if stream-copy concat balks
        subprocess.run(
            [ffmpeg_path(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(listfile), "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(out_video)],
            check=True)

    desc = _description(title, chapters)
    meta = out_dir / f"{stamp}_{_slug(title)}.txt"
    meta.write_text(desc)

    import shutil
    shutil.rmtree(work, ignore_errors=True)
    total = _ts(cursor)
    print(f"\nDone: {out_video.relative_to(PROJECT_ROOT)} ({total})")
    print(f"Title + chapters: {meta.relative_to(PROJECT_ROOT)}")
    return {"video": str(out_video), "meta": str(meta),
            "duration_s": cursor, "clips": len(clips)}


def _description(title: str, chapters: list[tuple[float, int, str]]) -> str:
    lines = [f"TITLE: {title}", "",
             "DESCRIPTION:",
             "The funniest moments, ranked. Timestamps below 👇", ""]
    # YouTube requires the first chapter at 0:00
    for start, rank, ct in chapters:
        lines.append(f"{_ts(start)} #{rank} {ct}")
    lines += ["", "#caseoh #gaming #funny #twitch"]
    return "\n".join(lines)


def _slug(text: str, n: int = 50) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:n] or "compilation"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.environ.get(
        "COMPILE_USER_ID", "599228e6-c961-40c0-b88d-6872c9cf02bd"))
    ap.add_argument("--title", default="CaseOh's Funniest Moments")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--min-score", type=float, default=8.0)
    ap.add_argument("--channel", default=None,
                    help="twitch login to keep the comp to one streamer")
    ap.add_argument("--no-countdown", action="store_true")
    a = ap.parse_args()
    compile_video(a.user, a.title, days=a.days, count=a.count,
                  min_score=a.min_score, countdown=not a.no_countdown,
                  channel=a.channel)
