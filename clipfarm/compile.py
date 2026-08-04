"""Compile a long-form 16:9 "funniest moments" video from recent VODs.

Long-form watch-time (not Shorts) is what counts toward YouTube monetization.
This pulls a channel's last N streams, runs the same scoring pipeline the
worker uses to find the best moments, then stitches ~1-minute landscape clips
into one 11-18 minute video with the streamer's own caption style and a
chaptered description.

Run:  python -m clipfarm.compile --channel caseoh_ --streams 4 \
          --title "CaseOh's Funniest Moments of the Week"
Sources fresh from Twitch VODs (transcripts cache per VOD). Env: same as the
worker (Supabase for the style preset, GROQ_API_KEY, OPENAI_API_KEY).
Output in out/compilations/.
"""

import argparse
import datetime
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import detect, fetch, pipeline, render, transcribe
from .config import PROJECT_ROOT, ffmpeg_path, load_config

W, H = 1920, 1080
CLIP_LEN = 60.0   # long-form: ~1 min of context per moment
MIN_MIN, MAX_MIN = 11, 18  # required finished length window
# Fraction of a raw window that survives the silence jump-cut. Measured on the
# first cut-enabled comp; used only to size the clip count so the finished
# video still lands in the length window.
EXPECTED_KEEP = 0.88
# Long-form silence tolerances. Shorts use 3.5s/6s because every second is
# rent; at 13 minutes the video can afford to let a moment breathe, and
# cutting a 7s quiet stretch often deletes the visual gag itself.
# Set EQUAL on purpose: everything up to this is kept outright, past it is
# cut outright. Leaving a middle band would defer to loudness, and a silent
# visual gag (streamer watching something land, a BBL on screen) has no
# loudness to show for itself -- which is exactly how it got deleted.
LF_MAX_GAP = 12.0
LF_HARD_GAP = 12.0
LF_KEEP_AIR = 1.0    # leave a full beat around each cut


def _sb(path: str, **kw) -> list:
    key = os.environ["SUPABASE_SERVICE_KEY"]
    r = httpx.get(os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1" + path,
                  headers={"apikey": key, "Authorization": f"Bearer {key}"},
                  timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def landscape_style(user_id: str | None) -> dict:
    """The streamer's OWN caption preset (same look as their shorts), scaled
    down and repositioned for 16:9. Reads style_profile like the worker does."""
    cfg = load_config()
    style = cfg["style"]
    if user_id:
        prof = (_sb(f"/users?id=eq.{user_id}&select=style_profile") or [{}])[0]
        for k, v in (prof.get("style_profile") or {}).items():
            if isinstance(v, dict) and isinstance(style.get(k), dict):
                style[k].update(v)
            else:
                style[k] = v
    # landscape frame is much shorter than a vertical short -> shrink the
    # caption and drop it near the bottom; keep font/colors/case identical
    style["font_size"] = int(style.get("font_size", 70) * 0.62)
    style["caption_pos"] = 0.87
    style["words_per_line"] = max(style.get("words_per_line", 2), 4)
    style["hook"] = {}       # no per-clip hook overlay in the comp
    style["watermark"] = {}
    return style


def moments_from_vods(channel: str, streams: int, want: int,
                      clip_len: float) -> list[dict]:
    """Analyze the channel's last `streams` VODs and return the top `want`
    moments across all of them, best first, spread within each stream."""
    cfg = load_config()
    cfg["streamer_name"] = channel
    # channel handle -> selection persona (rubric + anchors)
    for key in ("caseoh", "jynxzi"):
        if key in channel.lower():
            cfg["persona"] = key
            break
    twitch_url = f"https://www.twitch.tv/{channel}"
    vods = fetch.list_vods(twitch_url, streams)
    if not vods:
        raise SystemExit(f"No VODs found for {channel}")
    print(f"Analyzing {len(vods)} recent {channel} VODs...")

    work = PROJECT_ROOT / "work"
    work.mkdir(exist_ok=True)
    # ask each VOD for enough candidates that the global top `want` has slack
    per_vod = max(3, math.ceil(want / len(vods)) + 3)
    pool: list[dict] = []
    for vod_url, vtitle in vods:
        vid = re.sub(r"[^a-zA-Z0-9]+", "-", vod_url.rsplit("/", 1)[-1])[:24]
        vod_work = work / vid
        vod_work.mkdir(exist_ok=True)
        print(f"\n=== {vtitle[:60]} ({vod_url}) ===")
        try:
            words, profile, moments = pipeline.analyze_vod(
                cfg, vod_url, vod_work, rerank=False)
        except Exception as e:
            print(f"  skipped ({type(e).__name__}: {str(e)[:100]})")
            continue
        picks = detect.select_clips(
            moments, profile, per_vod,
            cfg["clips"]["min_length"], cfg["clips"]["max_length"],
            words=words, min_gap_s=cfg["clips"].get("min_gap_minutes", 20) * 60)
        for m in picks:
            # music-risk gate (comps only): a Content ID claim on long-form
            # redirects the WHOLE video's revenue. Windows that are mostly
            # non-speech audio are the classic claim surface (stream music,
            # game OSTs). Speech coverage over the widened comp window:
            mid = (m.start + m.end) / 2
            ws, we = max(0.0, mid - clip_len / 2), mid + clip_len / 2
            speech = sum(min(w.end, we) - max(w.start, ws) for w in words
                         if w.end > ws and w.start < we)
            if speech / clip_len < 0.35:
                print(f"  music-risk skip ({speech / clip_len:.0%} speech): "
                      f"{m.title[:50]}")
                continue
            pool.append({"vod_url": vod_url, "start_s": m.start, "end_s": m.end,
                         "title": m.title, "hook": m.hook,
                         "score": m.score, "combined": m.combined})
    pool.sort(key=lambda x: x["combined"], reverse=True)
    picks = pool[:want]
    # retention data: viewers bail in the first 2 clips when the open is
    # same-flavor. Keep the #1 moment as the opener, then round-robin across
    # source VODs (each stream = different game/bit) for early variety.
    by_vod: dict[str, list[dict]] = {}
    for c in picks[1:]:
        by_vod.setdefault(c["vod_url"], []).append(c)
    ordered, vods = [picks[0]] if picks else [], list(by_vod)
    while len(ordered) < len(picks):
        for v in vods:
            if by_vod[v]:
                ordered.append(by_vod[v].pop(0))
    return ordered


def _ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _raw_profile(vod_url: str):
    """Pre-speech-gate loudness for this VOD, if the cache has it.

    Needed so the jump-cut can tell a quiet NPC line from real silence; the
    speech-gated array cannot (DECISIONS.md 2026-07-23). Missing cache is not
    an error — keep_intervals falls back to duration alone.
    """
    import numpy as np
    vid = vod_url.rstrip("/").rsplit("/", 1)[-1]
    p = PROJECT_ROOT / "work" / vid / "loudness_raw.npy"
    try:
        return np.load(p) if p.exists() else None
    except Exception:
        return None


def compile_video(channel: str, title: str, streams: int = 4,
                  target_min: float = 14.0, clip_len: float = CLIP_LEN,
                  quality: str = "best[height<=1080]",
                  style_user_id: str | None = None,
                  brand: str | None = None,
                  inter_clip_cards: bool = True) -> dict:
    if brand is None:
        brand = load_config()["output"].get("brand", "")
    # count is set by the required 11-18 min finished length at clip_len each
    # Clips are jump-cut, so a 60s window ships shorter than 60s. Ask for
    # enough moments that the FINISHED video still lands in the 11-18 min
    # window; without this the trim quietly pushed a 14-min target to ~10.
    count = round(target_min * 60 / (clip_len * EXPECTED_KEEP))
    count = max(math.ceil(MIN_MIN * 60 / clip_len),
                min(count, math.floor(MAX_MIN * 60 / clip_len)))
    clips = moments_from_vods(channel, streams, count, clip_len)
    if len(clips) < math.ceil(MIN_MIN * 60 / clip_len):
        raise SystemExit(
            f"Only found {len(clips)} strong moments across {streams} VODs — "
            f"need {math.ceil(MIN_MIN * 60 / clip_len)} for an {MIN_MIN}-min "
            f"video. Try more --streams.")
    print(f"\nCompiling {len(clips)} clips (~{len(clips) * clip_len / 60:.0f} min) "
          f"into '{title}'")

    style = landscape_style(style_user_id)
    out_dir = PROJECT_ROOT / "out" / "compilations"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    work = Path(tempfile.mkdtemp(prefix="comp_"))

    rendered, chapters, cursor = [], [], 0.0
    # Founder 2026-07-26, watching the first 15-clip cut: the cards "mess up
    # the flow". They were there to brand the video and mark chapter starts;
    # chapters survive without them because the timestamps are computed here,
    # not read off the cards. Cutting straight from payoff to next setup keeps
    # the momentum a compilation lives on.
    card_dur = 0.9 if inter_clip_cards else 0.0
    n = len(clips)
    for i, c in enumerate(clips):
        # widen the tight short-form pick to ~clip_len of context, centred on
        # the moment; long-form wants the build-up and the aftermath
        mid = (c["start_s"] + c["end_s"]) / 2
        cs = max(0.0, mid - clip_len / 2)
        ce = cs + clip_len
        seg = work / f"seg_{i:02d}.mp4"
        print(f"[{i + 1}/{n}] {c['title']} ({cs:.0f}-{ce:.0f}s, {clip_len:.0f}s)")
        fetch.download_segment(c["vod_url"], cs, ce, seg, quality)
        words = transcribe.transcribe_clips_groq(
            [(seg, cs)],
            context="Twitch gaming stream. Loud casual speech, screaming, slang.")[0]
        # Same jump-cut the Shorts get. A compilation built from fixed windows
        # keeps every pause, and fifteen of those is minutes of dead air — the
        # "not tight" complaint. keep_intervals is duration-primary and
        # guarded by raw loudness, so quiet game/NPC sound survives while
        # genuine silence goes (DECISIONS.md 2026-07-23).
        keep, seg_len = None, ce - cs
        # Long-form tolerances, NOT the Shorts ones. A Short pays rent on
        # every second; a 13-minute video has room to let a joke land. Gaps
        # up to LF_MAX_GAP are always kept, so beats and visual gags survive;
        # only genuinely long quietness (past LF_HARD_GAP) is removed, and
        # the window's own head and tail are never trimmed, so the setup and
        # the aftermath stay.
        ivals = detect.keep_intervals(words, cs, ce,
                                      max_gap=LF_MAX_GAP,
                                      keep_air=LF_KEEP_AIR,
                                      hard_gap=LF_HARD_GAP,
                                      profile=_raw_profile(c["vod_url"]))
        kept = sum(e - s for s, e in ivals)
        if ivals and kept > 5.0 and (ce - cs) - kept > 1.5:
            keep = [(s - cs, e - cs) for s, e in ivals]
            words = detect.remap_words(words, ivals)
            seg_len = kept
            print(f"      jump-cut {(ce - cs) - kept:4.1f}s dead air "
                  f"-> {seg_len:.0f}s")
        ass = render.build_ass(words, 0.0 if keep else cs,
                               seg_len if keep else ce, style,
                               work / f"seg_{i:02d}.ass", res=(W, H))
        final = work / f"final_{i:02d}.mp4"
        render.render_landscape(seg, ass, final, keep=keep)
        # branded inter-clip card — but NEVER before the opener: retention
        # data shows the first seconds decide everything, so the video must
        # open mid-banger, not on 0.9s of black card
        if i == 0 or not inter_clip_cards:
            rendered.append(final)
            chapters.append((cursor, c["title"]))
            cursor += seg_len
        else:
            card = render.title_card(c["title"], work / f"card_{i:02d}.mp4",
                                     dur=card_dur, brand=brand)
            rendered += [card, final]
            chapters.append((cursor, c["title"]))  # chapter lands on the card
            cursor += card_dur + seg_len
        seg.unlink(missing_ok=True)

    # concat with a full re-encode + audio resample: stream-copy concat drifts
    # audio across many segments (the bug the user hit); re-encoding pins sync
    listfile = work / "concat.txt"
    listfile.write_text("".join(f"file '{f}'\n" for f in rendered))
    out_video = out_dir / f"{stamp}_{_slug(title)}.mp4"
    subprocess.run(
        [ffmpeg_path(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile),
         "-vsync", "cfr", "-af", "aresample=async=1",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
         "-movflags", "+faststart", str(out_video)],
        check=True)

    # sanity: video and audio streams must agree on duration — mixed concat
    # inputs once produced 2x-long video (half-speed playback) with exit 0
    probe = subprocess.run(
        [str(Path(ffmpeg_path()).parent / "ffprobe"), "-v", "error",
         "-show_entries", "stream=codec_type,duration", "-of", "json",
         str(out_video)], capture_output=True, text=True)
    durs = {s["codec_type"]: float(s.get("duration", 0))
            for s in __import__("json").loads(probe.stdout).get("streams", [])}
    if abs(durs.get("video", 0) - durs.get("audio", 0)) > 2.0:
        raise RuntimeError(
            f"A/V duration mismatch in output: video {durs.get('video'):.0f}s"
            f" vs audio {durs.get('audio'):.0f}s — concat input params drifted")

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


def _description(title: str, chapters: list[tuple[float, str]]) -> str:
    lines = [f"TITLE: {title}", "",
             "DESCRIPTION:",
             "All the best moments in one video. Timestamps below 👇", ""]
    # YouTube requires the first chapter at 0:00
    for start, ct in chapters:
        lines.append(f"{_ts(start)} {ct}")
    lines += ["", "#caseoh #gaming #funny #twitch"]
    return "\n".join(lines)


def _slug(text: str, n: int = 50) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:n] or "compilation"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True,
                    help="twitch login to source VODs from, e.g. caseoh_")
    ap.add_argument("--title", default=None)
    ap.add_argument("--streams", type=int, default=4,
                    help="how many recent VODs to pull moments from")
    ap.add_argument("--target-min", type=float, default=14.0,
                    help=f"target length in minutes ({MIN_MIN}-{MAX_MIN})")
    ap.add_argument("--clip-len", type=float, default=CLIP_LEN,
                    help="seconds of context per moment (default 60)")
    ap.add_argument("--style-user", default=os.environ.get(
        "COMPILE_USER_ID", "599228e6-c961-40c0-b88d-6872c9cf02bd"),
        help="Supabase user id whose caption preset to match")
    ap.add_argument("--brand", default=None,
                    help="watermark/card brand text (default: config output.brand)")
    ap.add_argument("--no-cards", action="store_true",
                    help="drop the 0.9s title card between clips — cuts "
                         "straight from one payoff into the next setup")
    a = ap.parse_args()
    title = a.title or f"{a.channel}'s Funniest Moments"
    compile_video(a.channel, title, streams=a.streams,
                  target_min=a.target_min, clip_len=a.clip_len,
                  style_user_id=a.style_user, brand=a.brand,
                  inter_clip_cards=not a.no_cards)
