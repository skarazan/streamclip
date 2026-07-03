"""End-to-end run: VOD -> transcript -> moments -> rendered shorts + metadata."""

import re
import shutil
import time
from datetime import date
from pathlib import Path

from . import detect, fetch, render, transcribe
from .config import PROJECT_ROOT, check_disk, free_gb


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:n] or "clip"


def run(cfg: dict, vod_url: str | None = None) -> dict:
    t0 = time.time()
    check_disk(cfg)

    work = PROJECT_ROOT / "work"
    work.mkdir(exist_ok=True)

    # 1. locate VOD
    if vod_url:
        title = "stream"
        print(f"Using VOD: {vod_url}")
    else:
        print("Finding latest VOD...")
        vod_url, title = fetch.latest_vod_url(cfg["channel"]["twitch_url"])
        print(f"Latest VOD: {title}\n  {vod_url}")

    vod_id = _slug(vod_url.rstrip("/").rsplit("/", 1)[-1], 24)
    vod_work = work / vod_id
    vod_work.mkdir(exist_ok=True)

    # 2. audio
    audio_files = [f for f in vod_work.glob("vod_audio.*")
                   if not f.name.endswith((".part", ".ytdl"))]
    if audio_files:
        audio = audio_files[0]
        print(f"Audio already downloaded: {audio.name}")
    else:
        print("Downloading audio track (this is the small download)...")
        audio = fetch.download_audio(vod_url, vod_work)
        print(f"  -> {audio.name} ({audio.stat().st_size / 1e6:.0f} MB, "
              f"{free_gb():.1f} GB disk left)")

    # 3. transcribe (cached)
    print("Transcribing locally with Whisper (long streams take a while)...")
    words = transcribe.transcribe(
        audio, cfg["transcribe"]["model"], cfg["transcribe"]["compute_type"],
        cache_path=vod_work / "transcript.json",
    )
    dur_h = (words[-1].end / 3600) if words else 0
    print(f"  {len(words)} words, ~{dur_h:.1f}h of speech")

    # 4. loudness
    print("Analyzing audio loudness...")
    profile = transcribe.loudness_profile(audio)

    # 5. moments
    llm = cfg["llm"]
    if words and detect.llm_available(
            llm["model"], llm.get("base_url"), llm.get("api_key_env")):
        print(f"Scoring moments with {cfg['llm']['model']}...")
        moments = detect.score_with_llm(
            words, llm["model"], llm["chunk_minutes"],
            base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
            streamer=cfg.get("streamer_name", "the streamer"))
        if not moments:
            print("  LLM found nothing usable; falling back to loudness.")
            moments = detect.moments_from_energy(profile)
    else:
        print("No API credentials for configured model -> loudness-only mode "
              "(set ANTHROPIC_API_KEY or OPENAI_API_KEY, see config.yaml llm:).")
        moments = detect.moments_from_energy(profile)

    clips = detect.select_clips(
        moments, profile,
        cfg["clips"]["count"], cfg["clips"]["min_length"], cfg["clips"]["max_length"],
    )
    if not clips:
        raise SystemExit("No clip candidates found.")
    print(f"Selected {len(clips)} clips:")
    for m in clips:
        print(f"  [{m.start/60:6.1f}m] score {m.score:.0f} energy {m.energy:.2f}"
              f"  {m.title}")

    # 6. download segments + render
    out_dir = PROJECT_ROOT / cfg["output"]["dir"] / f"{date.today()}_{vod_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    style = cfg["style"]
    results = []

    for i, m in enumerate(clips, 1):
        name = f"{i:02d}_{_slug(m.title)}"
        seg = vod_work / f"seg_{i:02d}.mp4"
        print(f"[{i}/{len(clips)}] Downloading segment "
              f"{m.start:.0f}s-{m.end:.0f}s...")
        seg = fetch.download_segment(
            vod_url, m.start, m.end, seg, cfg["clips"]["quality"])

        cam = None
        if style.get("layout", "full") == "split":
            from . import facecam
            cam = facecam.detect_facecam(seg)
            print(f"[{i}/{len(clips)}] Facecam "
                  f"{'found -> split layout' if cam else 'not found -> full frame'}")

        print(f"[{i}/{len(clips)}] Rendering short...")
        top_frac = style.get("split_top", 0.42)
        ass = render.build_ass(words, m.start, m.end, style,
                               vod_work / f"seg_{i:02d}.ass",
                               hook=m.hook, hook_color_idx=i - 1,
                               hook_pos=top_frac if cam else None)
        final = render.render_short(seg, ass, out_dir / f"{name}.mp4",
                                    style.get("crop", "center"),
                                    cam=cam, top_frac=top_frac)

        meta = out_dir / f"{name}.txt"
        desc = cfg["output"]["description_template"].format(title=m.title)
        meta.write_text(
            f"TITLE: {m.title}\n\nDESCRIPTION:\n{desc}\n"
            f"WHY: {m.reason}\nSOURCE: {vod_url} @ {m.start:.0f}s\n")
        print(f"  -> {final.relative_to(PROJECT_ROOT)}")
        results.append({"file": str(final), "title": m.title, "hook": m.hook,
                        "score": m.score, "start_s": m.start, "end_s": m.end})
        seg.unlink(missing_ok=True)  # keep disk usage low

    # cleanup big audio file, keep transcript cache
    for f in vod_work.glob("vod_audio.*"):
        f.unlink()

    mins = (time.time() - t0) / 60
    print(f"\nDone in {mins:.1f} min. Shorts + titles in: "
          f"{out_dir.relative_to(PROJECT_ROOT)}/")
    print("Review each clip, then upload from the YouTube app/studio.")
    return {"out_dir": str(out_dir), "vod_url": vod_url, "clips": results}


def clean_work() -> None:
    work = PROJECT_ROOT / "work"
    if work.exists():
        shutil.rmtree(work)
        print("Cleared work/ directory.")
