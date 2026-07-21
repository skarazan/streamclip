"""End-to-end run: VOD -> transcript -> moments -> rendered shorts + metadata."""

import json
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


PIPELINE_VERSION = "v10.1 (groq transcription, cpu-only, context-biased captions)"


def _ai_moments(cfg, words, profile, chat, llm, report, vod_work):
    """Pure AI-chosen moments: whole-VOD LLM scoring + editor rerank, the
    tier-C path, ignoring the crowd. Used by the A/B test to sit AI picks
    next to crowd picks in one batch. Reuses the per-persona score cache."""
    import json as _json
    mom_cache = vod_work / f"moments.{cfg.get('persona', 'generic')}.json"
    if mom_cache.exists():
        scored = [detect.Moment(**d) for d in
                  _json.loads(mom_cache.read_text())]
    else:
        scored = detect.score_with_llm(
            words, llm["model"], llm["chunk_minutes"],
            base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
            streamer=cfg.get("streamer_name", "the streamer"),
            fallback_models=llm.get("fallback_models"), profile=profile,
            persona=cfg.get("persona", "generic"), chat=chat)
        if scored:
            mom_cache.write_text(_json.dumps(
                [{"start": m.start, "end": m.end, "score": m.score,
                  "title": m.title, "hook": m.hook, "reason": m.reason}
                 for m in scored]))
    if not scored:
        return []
    return detect.rerank_moments(
        scored, words, profile, llm["model"],
        base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
        streamer=cfg.get("streamer_name", "the streamer"),
        fallback_models=llm.get("fallback_models"),
        persona=cfg.get("persona", "generic"))


def analyze_vod(cfg: dict, vod_url: str, vod_work: Path, report=None,
                rerank=True):
    """VOD -> (words, speech-gated loudness profile, scored moments).
    Shared by the worker (run) and the long-form compiler; transcript caches
    per VOD so re-analysis is cheap. rerank=True applies the strict editor
    pass (the 3-Shorts quality bar); comps pass rerank=False for the fuller
    scored set — more moments to fill a long video, still energy-ranked."""
    import numpy as np

    report = report or (lambda *a, **k: None)
    t_model = cfg["transcribe"]["model"]
    provider = cfg["transcribe"].get("provider", "local")
    tr_cache = vod_work / ("transcript.groq-turbo.json" if provider == "groq"
                           else f"transcript.{t_model.replace('/', '_')}.json")
    if not tr_cache.exists():
        older = sorted(vod_work.glob("transcript*.json"))
        if older:
            tr_cache = older[0]
    prof_cache = vod_work / "loudness.npy"
    raw_cache = vod_work / "loudness_raw.npy"  # pre-gate: keeps game/NPC sound

    # Fully cached (transcript + loudness) -> no audio download, no Groq, no
    # ffmpeg. This is the common case: every VOD the worker already clipped is
    # cached, so compilations reuse that work for free.
    if tr_cache.exists() and prof_cache.exists():
        words = [transcribe.Word(**w) for w in json.loads(tr_cache.read_text())]
        profile = np.load(prof_cache)
        raw_profile = np.load(raw_cache) if raw_cache.exists() else None
        print(f"Fully cached ({tr_cache.name} + loudness.npy) — no download")
    else:
        if free_gb() < 1.0:
            raise RuntimeError(
                f"only {free_gb():.1f} GB free — need ~1 GB to process a VOD; "
                f"free up disk (VOD audio is deleted right after, see below)")
        report("downloading_audio")
        print("Downloading audio track...")
        audio = fetch.download_audio(vod_url, vod_work)
        print(f"  -> {audio.name} ({audio.stat().st_size / 1e6:.0f} MB, "
              f"{free_gb():.1f} GB disk left)")
        try:
            report("transcribing")
            print("Transcribing (Groq API, ~200x realtime; cached per VOD)...")
            if provider == "groq":
                try:
                    words = transcribe.transcribe_groq(audio, cache_path=tr_cache)
                except Exception as e:
                    print(f"  groq failed ({str(e)[:120]}) -> local {t_model}")
                    words = transcribe.transcribe(
                        audio, t_model, cfg["transcribe"]["compute_type"],
                        cache_path=vod_work / f"transcript.{t_model}.json")
            else:
                words = transcribe.transcribe(
                    audio, t_model, cfg["transcribe"]["compute_type"],
                    cache_path=tr_cache)
            print("Analyzing audio loudness...")
            raw_profile = transcribe.loudness_profile(audio)
            profile = detect.speech_gated(raw_profile, words)
            np.save(prof_cache, profile)  # so next comp needs no audio at all
            np.save(raw_cache, raw_profile)  # non-speech sounds for jump-cuts
        finally:
            # free the big file immediately — transcript + loudness are cached
            for f in vod_work.glob("vod_audio.*"):
                f.unlink(missing_ok=True)
    dur_h = (words[-1].end / 3600) if words else 0
    print(f"  {len(words)} words, ~{dur_h:.1f}h of speech")

    # chat replay: optional signal, never blocks a run
    chat = None
    try:
        report("transcribing", "sampling chat replay")
        chat = fetch.download_chat(vod_url, vod_work / "chat.json",
                                   duration=words[-1].end if words else 0.0)
        print(f"Chat replay: {len(chat.get('density', []))} density samples, "
              f"{len(chat.get('texts', []))} messages "
              f"({'full crawl' if chat.get('full') else 'sampled'})")
    except Exception as e:
        print(f"Chat replay unavailable ({str(e)[:80]}) — continuing without")

    # crowd ground truth: viewers' own Twitch clips of THIS vod. Tier A
    # (rich signal) replaces LLM chunk-scoring entirely — humans already
    # found the moments; the LLM only refines boundaries/titles in the
    # editor pass. Tier B merges crowd anchors into the scored pool.
    # Tier C (small channels, no clips) = pure signal-stack scoring.
    crowd_moments: list = []
    try:
        from . import crowd as _crowd
        clips_raw = _crowd.fetch_vod_clips(
            vod_url, cache=vod_work / "twitch_clips.json")
        clusters = _crowd.cluster_moments(clips_raw)
        for cl in clusters[:15]:
            # the earliest clip in a cluster CONTAINS the moment: Twitch's
            # clip button records the ~30s BEFORE the press. Anchor there.
            s = max(0.0, cl.start - 10.0)
            e = min(max(cl.end, s + 22.0), s + 90.0)
            crowd_moments.append(detect.Moment(
                start=s, end=e,
                score=min(10.0, 5.0 + cl.strength / 5.0),
                title=(cl.titles[0] if cl.titles else "crowd moment")[:80],
                reason=f"{cl.clippers} viewers clipped this live "
                       f"({cl.views} clip views)",
                crowd=cl.clippers, crowd_peak=cl.median_start,
                source="crowd"))
        if crowd_moments:
            print(f"Crowd ground truth: {len(clips_raw)} viewer clips -> "
                  f"{len(clusters)} moments, using top {len(crowd_moments)}")
    except Exception as e:
        print(f"Crowd clips unavailable ({str(e)[:80]}) — signal-stack only")

    tier_a = len(crowd_moments) >= 8
    # A/B test mode: also produce N purely AI-CHOSEN moments (whole-VOD LLM
    # scoring, ignoring the crowd) alongside the crowd ones, so crowd-vs-AI
    # selection can be compared in the same batch.
    ai_count = int(cfg.get("clips", {}).get("ai_count", 0))

    llm = cfg["llm"]
    if tier_a:
        # humans judged WHAT; the editor pass judges HOW (bounds/title/hook)
        report("scoring", "viewers already clipped the best moments — refining")
        print(f"Tier A: crowd-first, skipping chunk scoring "
              f"({len(crowd_moments)} crowd candidates)")
        moments = crowd_moments
        if rerank:
            moments = detect.rerank_moments(
                moments, words, profile, llm["model"],
                base_url=llm.get("base_url"),
                api_key_env=llm.get("api_key_env"),
                streamer=cfg.get("streamer_name", "the streamer"),
                fallback_models=llm.get("fallback_models"),
                persona=cfg.get("persona", "generic"), post_bar=6)
        for m in moments:
            m.source = "crowd"
        if ai_count > 0 and words:
            print(f"A/B: also scoring the VOD for {ai_count} AI-chosen clips...")
            ai = _ai_moments(cfg, words, profile, chat, llm, report, vod_work)
            # AI picks that don't overlap a crowd pick, best first
            for m in ai:
                m.source = "ai"
            moments = moments + ai
        return words, profile, moments

    if words and detect.llm_available(
            llm["model"], llm.get("base_url"), llm.get("api_key_env"),
            llm.get("fallback_models")):
        print(f"Scoring moments with {cfg['llm']['model']}...")
        def _score_log(msg):
            print(msg)
            m = str(msg).strip()
            if m.startswith("!"):
                m = "switching to a backup AI model..."
            elif m.startswith("(scored with fallback"):
                m = ""
            elif "chunk" in m:
                m = m.replace("LLM scoring ", "").split("(")[0].strip()
            report("scoring", m)
        # scored-moments cache: reruns (comp after worker, card fixes, A/B)
        # shouldn't re-pay the whole-VOD scoring bill. Keyed by persona since
        # the rubric changes the picks.
        mom_cache = vod_work / f"moments.{cfg.get('persona', 'generic')}.json"
        if mom_cache.exists():
            moments = [detect.Moment(**d)
                       for d in json.loads(mom_cache.read_text())]
            print(f"  {len(moments)} scored moments from cache "
                  f"({mom_cache.name})")
        else:
            moments = detect.score_with_llm(
                words, llm["model"], llm["chunk_minutes"], log=_score_log,
                base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
                streamer=cfg.get("streamer_name", "the streamer"),
                fallback_models=llm.get("fallback_models"), profile=profile,
                persona=cfg.get("persona", "generic"), chat=chat)
            if moments:
                mom_cache.write_text(json.dumps(
                    [{"start": m.start, "end": m.end, "score": m.score,
                      "title": m.title, "hook": m.hook, "reason": m.reason}
                     for m in moments]))
        if not moments:
            print("  LLM found nothing usable; falling back to loudness.")
            moments = detect.moments_from_energy(profile)
        elif rerank:
            report("scoring", "editor pass: keeping only the bangers")
            moments = detect.rerank_moments(
                moments, words, profile, llm["model"], log=_score_log,
                base_url=llm.get("base_url"),
                api_key_env=llm.get("api_key_env"),
                streamer=cfg.get("streamer_name", "the streamer"),
                fallback_models=llm.get("fallback_models"),
                persona=cfg.get("persona", "generic"))
    else:
        print("No API credentials for configured model -> loudness-only mode.")
        moments = detect.moments_from_energy(profile)
    if crowd_moments:  # tier B: crowd anchors join the pool, crowd-flagged
        moments = list(moments) + crowd_moments
    return words, profile, moments


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

    words, profile, moments = analyze_vod(cfg, vod_url, vod_work, report)
    _raw_cache = vod_work / "loudness_raw.npy"
    import numpy as _np
    raw_profile = _np.load(_raw_cache) if _raw_cache.exists() else None

    # over-select by 4: a deep bench so the downstream gate (arc-verified,
    # then cam-present) has real alternatives — an off-cam or unverified
    # moment gets dropped rather than shipped for lack of a replacement
    want = cfg["clips"]["count"]
    ai_count = int(cfg["clips"].get("ai_count", 0))
    crowd_want = want - ai_count

    def _sel(ms, n):
        return detect.select_clips(
            ms, profile, n, cfg["clips"]["min_length"],
            cfg["clips"]["max_length"], words=words,
            min_gap_s=cfg["clips"].get("min_gap_minutes", 20) * 60,
            raw_profile=raw_profile)

    if ai_count > 0:
        # A/B: pick each source's candidates separately so neither crowds out
        # the other; label them for side-by-side comparison
        crowd_ms = [m for m in moments if m.source != "ai"]
        ai_ms = [m for m in moments if m.source == "ai"]
        clips = _sel(crowd_ms, crowd_want + 2) + _sel(ai_ms, ai_count + 2)
        print(f"A/B bench: {len(crowd_ms)} crowd + {len(ai_ms)} AI moments")
    else:
        clips = _sel(moments, want + 3)
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
        # rigid layout rule: if the cam was found ANYWHERE in this batch,
        # every clip gets it. The cam barely moves within one stream, and a
        # batch mixing split/full-frame looks broken (dark rooms make
        # per-segment detection flaky). Full-frame only when the whole batch
        # and the probes found nothing.
        matched = [c for c in cams if c]
        if matched and not all(cams):
            # batch-fill ONLY when the identity check merely failed to lock a
            # box but the streamer IS on cam. If identity matching ran and
            # found NO face of the streamer in a segment, he's off-cam there
            # (fullscreen game scene, away) — a forced cam pane shows an empty
            # room. Full-frame that clip instead.
            if identity is not None:
                print(f"Facecam: {len(matched)}/{len(segs)} matched; "
                      "unmatched clips = streamer off-cam -> full frame")
            else:
                fill = tuple(float(v) for v in
                             np.median(np.array(matched), axis=0))
                cams = [c or fill for c in cams]
                print(f"Facecam: {len(matched)}/{len(segs)} segments matched "
                      "-> batch-fill for the rest")
        elif not matched and pos_box:
            cams = [pos_box] * len(segs)
        for i, c in enumerate(cams, 1):
            print(f"[{i}/{len(segs)}] Facecam "
                  f"{'matched -> split layout' if c else 'none -> full frame'}")

    # 8. caption transcripts: the rough whole-VOD transcript picked the
    # moments; the words that get BURNED ON SCREEN come from a premium model
    # over just these ~90 seconds (base.en heard "BANG BANG" as "BANK")
    cap_model = cfg["transcribe"].get("caption_model")
    provider = cfg["transcribe"].get("provider", "local")
    t_model = cfg["transcribe"]["model"]
    cap_words: list = [None] * len(segs)
    items = [(seg, m.start) for m, seg in zip(clips, segs)]
    if provider == "groq":
        report("rendering", "transcribing clips with the accurate model")
        print(f"Caption pass: groq turbo over {len(segs)} segments...")
        try:
            ctx = (f"Twitch gaming stream by {cfg.get('streamer_name', 'a streamer')}. "
                   f"Casual loud speech, screaming, gamer slang.")
            cap_words = transcribe.transcribe_clips_groq(items, context=ctx)
        except Exception as e:
            print(f"  groq caption pass failed ({str(e)[:120]})"
                  + (f" -> local {cap_model}" if cap_model else ""))
            if cap_model:
                cap_words = transcribe.transcribe_clips(
                    items, cap_model, cfg["transcribe"]["compute_type"])
    elif cap_model and cap_model != t_model:
        report("rendering", "transcribing clips with the accurate model")
        print(f"Caption pass: {cap_model} over {len(segs)} segments...")
        cap_words = transcribe.transcribe_clips(
            items, cap_model, cfg["transcribe"]["compute_type"])

    # 8.5 ARC-VERIFIED SHIPPING GATE. Verdict pattern across every user
    # review: clips whose trigger+button quotes are audibly inside them =
    # "cinema"; clips we couldn't verify = "random bs". So verify against
    # the clip's OWN captions and let verified arcs outrank everything.
    def _quote_ratio(quote: str, ws) -> float:
        if not quote or not ws:
            return -1.0  # no quote / no words: distinguish from a 0% match
        text = " ".join(w.text.lower() for w in ws)
        toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", quote.lower()).split()
                if len(t) > 2]
        if not toks:
            return -1.0
        return sum(1 for t in toks if t in text) / len(toks)

    def _quote_in(quote: str, ws) -> bool:
        # 0.45: editor quotes come from the rough whole-VOD transcript,
        # captions from a per-clip re-transcription — wording drifts
        return _quote_ratio(quote, ws) >= 0.45

    verified, too_long = [], []
    for i, m in enumerate(clips):
        ws = cap_words[i] or [w for w in words if m.start <= w.start <= m.end]
        # calibrated on real ratios: editors quote BUTTONS verbatim (reliable
        # exact check) but paraphrase TRIGGERS — so the setup is verified
        # structurally: real speech in the clip's first half, or the quote.
        dur = (ws[-1].end - ws[0].start) if ws else 0.0
        setup_words = sum(1 for w in ws
                          if ws and w.start - ws[0].start <= dur * 0.5)
        ok = (_quote_in(m.button_quote, ws)
              and (_quote_in(m.trigger_quote, ws) or setup_words >= 8))
        verified.append(ok)
        # format fit: smart-cut can now condense talking-dense clips, so only
        # a moment whose silence-cut length is STILL huge (>52s — beyond what
        # tightening the talking can rescue) is a poor fit; let the bench
        # replace those. Mid-range clips get smart-cut at render.
        ivs = detect.keep_intervals(words, m.start, m.end, profile=raw_profile)
        eff = sum(e - s for s, e in ivs)
        too_long.append(eff > 52.0)
        rt = _quote_ratio(m.trigger_quote, ws)
        rb = _quote_ratio(m.button_quote, ws)
        print(f"  arc check '{m.title[:45]}': "
              f"{'VERIFIED' if ok else 'unverified'} "
              f"(trigger {rt:.0%} '{m.trigger_quote[:40]}' | "
              f"button {rb:.0%} '{m.button_quote[:40]}')"
              f"{' (no cam)' if not cams[i] else ''}")

    if len(clips) > want:
        # VERIFIED FIRST: an unverified clip (no real trigger->payoff arc)
        # is "random bs" and must never ship over a real moment; rank the
        # rest by cam-present > fits-format.
        def _rank(idxs):
            verd = [i for i in idxs if verified[i]]
            base = verd if len(verd) >= 1 else idxs
            return sorted(base, key=lambda i: (not cams[i], too_long[i],
                                               not verified[i], i))
        if ai_count > 0:
            # A/B split: keep the best crowd_want crowd picks AND the best
            # ai_count AI picks, so the batch always has both to compare
            ci = [i for i in range(len(clips)) if clips[i].source != "ai"]
            ai = [i for i in range(len(clips)) if clips[i].source == "ai"]
            order = sorted(_rank(ci)[:crowd_want] + _rank(ai)[:ai_count])
        else:
            pool = [i for i in range(len(clips)) if verified[i]]
            if len(pool) < want:
                pool = list(range(len(clips)))
            order = sorted(_rank(list(range(len(clips))))[:want])
        for i in (set(range(len(clips))) - set(order)):
            reasons = [r for r, on in (
                ("off-cam", not cams[i]), ("too long", too_long[i]),
                ("unverified arc", not verified[i])) if on]
            print(f"  dropping '{clips[i].title[:45]}' "
                  f"({'/'.join(reasons) or 'overshoot'})")
            segs[i].unlink(missing_ok=True)
        clips = [clips[i] for i in order]
        segs = [segs[i] for i in order]
        cams = [cams[i] for i in order]
        cap_words = [cap_words[i] for i in order]

    # 9. render — ffmpeg is subprocess-bound, so clips render in parallel
    report("rendering", f"rendering {len(clips)} clips")
    top_frac = style.get("split_top", 0.42)

    def _render_one(i_m_seg_cam):
        i, m, seg, cam = i_m_seg_cam
        tag = f"{m.source.upper()}_" if m.source else ""
        name = f"{i:02d}_{tag}{_slug(m.title)}"
        print(f"[{i}/{len(clips)}] Rendering short...")
        clip_words = cap_words[i - 1] or words
        ass_start, ass_end = m.start, m.end
        # LAYERED CUTTING. 1) silence jump-cut removes dead air but keeps
        # short gaps (NPC sounds/beats live there), guarded by raw loudness.
        ivals = detect.keep_intervals(words, m.start, m.end,
                                      profile=raw_profile)
        eff = sum(e - s for s, e in ivals)
        # 2) SMART-CUT: if a clip is STILL too long after removing silence,
        # it's talking-dense (a donation/story bit with redundant repetition)
        # — an LLM condenses the talking to the trigger->reaction->payoff arc.
        # Sound-payoff clips never reach here (their silence-cut fits), so we
        # never risk an LLM (text-only) cutting a gap that holds a sound.
        target = cfg["clips"].get("smart_cut_target", 30)
        if cfg["clips"].get("smart_cut", True) and eff > target + 3:
            llm = cfg["llm"]
            sc = detect.smart_cut(
                words, m.start, m.end, m.trigger_quote, m.button_quote,
                target, llm["model"], base_url=llm.get("base_url"),
                api_key_env=llm.get("api_key_env"),
                fallback_models=llm.get("fallback_models"))
            if sc:
                ivals = sc
        # fallback: if a crowd clip is still long (smart-cut off/failed), drop
        # leading kept-spans until under budget — keeps the payoff (the end).
        while (sum(e - s for s, e in ivals) > target + 8 and len(ivals) > 1):
            ivals = ivals[1:]
        if len(ivals) > 1:
            saved = (m.end - m.start) - sum(e - s for s, e in ivals)
            print(f"  jump-cutting {len(ivals) - 1} silence(s), "
                  f"-{saved:.1f}s dead air")
            seg = render.cut_silences(
                seg, [(s - m.start, e - m.start) for s, e in ivals],
                vod_work / f"seg_{i:02d}_cut.mp4")
            clip_words = detect.remap_words(clip_words, ivals)
            ass_start, ass_end = 0.0, sum(e - s for s, e in ivals)
        ass = render.build_ass(clip_words, ass_start, ass_end,
                               style, vod_work / f"seg_{i:02d}.ass",
                               hook=m.hook, hook_color_idx=i - 1,
                               hook_pos=top_frac if cam else None)
        final = render.render_short(seg, ass, out_dir / f"{name}.mp4",
                                    style.get("crop", "center"),
                                    cam=cam, top_frac=top_frac,
                                    brand=cfg["output"].get("brand", ""))
        meta = out_dir / f"{name}.txt"
        desc = cfg["output"]["description_template"].format(title=m.title)
        picked = ("viewer clips (crowd)" if m.source == "crowd"
                  else "AI scoring" if m.source == "ai" else "auto")
        meta.write_text(
            f"TITLE: {m.title}\n\nDESCRIPTION:\n{desc}\n"
            f"PICKED BY: {picked}\n"
            f"WHY: {m.reason}\nSOURCE: {vod_url} @ {m.start:.0f}s\n")
        print(f"  -> {final.relative_to(PROJECT_ROOT)}")
        seg.unlink(missing_ok=True)  # keep disk usage low
        (vod_work / f"seg_{i:02d}.mp4").unlink(missing_ok=True)  # pre-cut original
        return {"file": str(final), "title": m.title, "hook": m.hook,
                "score": m.score, "start_s": m.start, "end_s": m.end}

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(_render_one,
                              [(i, m, seg, cam) for i, (m, seg, cam)
                               in enumerate(zip(clips, segs, cams), 1)]))

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
