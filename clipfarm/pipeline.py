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


PIPELINE_VERSION = "v8-captions (distil-large-v3 transcription, model-versioned cache)"


def run(cfg: dict, vod_url: str | None = None) -> dict:
    print(f"pipeline {PIPELINE_VERSION}")
    t0 = time.time()
    report = cfg.get("_progress") or (lambda stage, detail="": None)
    check_disk(cfg)

    work = PROJECT_ROOT / "work"
    work.mkdir(exist_ok=True)

    # 1. locate VOD
    if vod_url:
        title = "stream"
        print(f"Using VOD: {vod_url}")
    else:
        report("finding_vod")
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
        report("downloading_audio")
        print("Downloading audio track (this is the small download)...")
        audio = fetch.download_audio(vod_url, vod_work)
        print(f"  -> {audio.name} ({audio.stat().st_size / 1e6:.0f} MB, "
              f"{free_gb():.1f} GB disk left)")

    # 3. transcribe (cached)
    report("transcribing")
    print("Transcribing locally with Whisper (long streams take a while)...")
    # a transcript from ANY model is good enough for editing/layout/style
    # work — only transcribe fresh when this VOD has never been transcribed.
    # (New VODs always get the current model; caption-quality upgrades apply
    # to them automatically.)
    t_model = cfg["transcribe"]["model"]
    cache = vod_work / f"transcript.{t_model.replace('/', '_')}.json"
    if not cache.exists():
        older = sorted(vod_work.glob("transcript*.json"))
        if older:
            cache = older[0]
            print(f"Reusing cached transcript {cache.name} — no re-transcribe")
    words = transcribe.transcribe(
        audio, t_model, cfg["transcribe"]["compute_type"], cache_path=cache,
    )
    dur_h = (words[-1].end / 3600) if words else 0
    print(f"  {len(words)} words, ~{dur_h:.1f}h of speech")

    # 4. loudness — gated to speech so intro music/soundboards measure zero
    print("Analyzing audio loudness...")
    profile = detect.speech_gated(transcribe.loudness_profile(audio), words)

    # 5. moments
    llm = cfg["llm"]
    if words and detect.llm_available(
            llm["model"], llm.get("base_url"), llm.get("api_key_env"),
            llm.get("fallback_models")):
        print(f"Scoring moments with {cfg['llm']['model']}...")
        def _score_log(msg):
            print(msg)
            m = str(msg).strip()
            # customers see progress, not plumbing
            if m.startswith("!"):
                m = "switching to a backup AI model..."
            elif m.startswith("(scored with fallback"):
                m = ""
            elif "chunk" in m:
                m = m.replace("LLM scoring ", "").split("(")[0].strip()
            report("scoring", m)
        moments = detect.score_with_llm(
            words, llm["model"], llm["chunk_minutes"], log=_score_log,
            base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
            streamer=cfg.get("streamer_name", "the streamer"),
            fallback_models=llm.get("fallback_models"), profile=profile)
        if not moments:
            print("  LLM found nothing usable; falling back to loudness.")
            moments = detect.moments_from_energy(profile)
        else:
            report("scoring", "editor pass: keeping only the bangers")
            moments = detect.rerank_moments(
                moments, words, profile, llm["model"], log=_score_log,
                base_url=llm.get("base_url"),
                api_key_env=llm.get("api_key_env"),
                streamer=cfg.get("streamer_name", "the streamer"),
                fallback_models=llm.get("fallback_models"))
    else:
        print("No API credentials for configured model -> loudness-only mode "
              "(set ANTHROPIC_API_KEY or OPENAI_API_KEY, see config.yaml llm:).")
        moments = detect.moments_from_energy(profile)

    clips = detect.select_clips(
        moments, profile,
        cfg["clips"]["count"], cfg["clips"]["min_length"], cfg["clips"]["max_length"],
        words=words,
        min_gap_s=cfg["clips"].get("min_gap_minutes", 20) * 60,
    )
    if not clips:
        raise SystemExit("No clip candidates found.")
    print(f"Selected {len(clips)} clips:")
    for m in clips:
        print(f"  [{m.start/60:6.1f}m] score {m.score:.0f} energy {m.energy:.2f}"
              f"  {m.title}")

    # 6. download all segments first — facecam detection gets every segment
    out_dir = PROJECT_ROOT / cfg["output"]["dir"] / f"{date.today()}_{vod_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    style = cfg["style"]
    results = []

    segs = []
    for i, m in enumerate(clips, 1):
        seg = vod_work / f"seg_{i:02d}.mp4"
        report("clipping", f"clip {i}/{len(clips)}: downloading moment")
        print(f"[{i}/{len(clips)}] Downloading segment "
              f"{m.start:.0f}s-{m.end:.0f}s...")
        segs.append(fetch.download_segment(
            vod_url, m.start, m.end, seg, cfg["clips"]["quality"]))

    # 7. facecam: the screen is full of faces that aren't the streamer, and
    # OBS scenes move the cam around, so the only durable anchor is the
    # streamer's face identity — established once from probes spread across
    # the whole VOD, then matched inside each segment. Cached per VOD.
    cams: list = [None] * len(segs)
    if style.get("layout", "full") == "split":
        import json as _json

        import numpy as np

        from . import facecam
        report("rendering", "locating facecam")
        cam_cache = vod_work / "cam_box.json"
        identity, pos_box = None, None
        if cam_cache.exists():
            try:
                cached = _json.loads(cam_cache.read_text())
                # v<4 boxes were fooled by content faces; only identity-era
                # cache entries are trusted
                if isinstance(cached, dict) and cached.get("v", 0) >= 4:
                    if cached.get("emb"):
                        identity = np.array(cached["emb"])
                    if cached.get("pos_box"):
                        pos_box = tuple(cached["pos_box"])
                    print("Facecam: cached VOD identity")
            except Exception:
                pass
        if identity is None and pos_box is None:
            duration = words[-1].end if words else 0.0
            identity, pos_box = facecam.probe_vod(
                vod_url, duration, vod_work, cfg["clips"]["quality"])
            if identity is not None or pos_box:
                tmp = cam_cache.with_suffix(".tmp")
                tmp.write_text(_json.dumps(
                    {"v": 4,
                     "emb": identity.tolist() if identity is not None else None,
                     "pos_box": pos_box}))
                tmp.replace(cam_cache)  # atomic: parallel jobs see no partials
        for i, seg in enumerate(segs):
            if identity is not None:
                cams[i] = facecam.match_segment(seg, identity)
            elif pos_box:
                cams[i] = pos_box
        for i, c in enumerate(cams, 1):
            print(f"[{i}/{len(segs)}] Facecam "
                  f"{'matched -> split layout' if c else 'none -> full frame'}")

    # 8. render
    for i, (m, seg, cam) in enumerate(zip(clips, segs, cams), 1):
        name = f"{i:02d}_{_slug(m.title)}"
        report("rendering", f"clip {i}/{len(clips)}: captions + layout")
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
