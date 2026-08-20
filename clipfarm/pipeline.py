"""End-to-end run: VOD -> transcript -> moments -> rendered shorts + metadata."""

import json
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from . import detect, fetch, quality, render, transcribe
from .config import PROJECT_ROOT, check_disk, free_gb


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:n] or "clip"


PIPELINE_VERSION = "v12.3 (payoff visibility audited in the final 9:16 crop)"


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
            persona=cfg.get("persona", "generic"), chat=chat,
            title_strategy=cfg.get("style", {}).get(
                "title_strategy", "curiosity"),
            reasoning_effort=llm.get("reasoning_effort"))
        if scored:
            mom_cache.write_text(_json.dumps(
                [{"start": m.start, "end": m.end, "score": m.score,
                  "title": m.title, "hook": m.hook, "reason": m.reason,
                  "archetype": m.archetype,
                  "trigger_quote": m.trigger_quote,
                  "button_quote": m.button_quote,
                  "button_kind": m.button_kind,
                  "trigger_role": m.trigger_role,
                  "button_role": m.button_role}
                 for m in scored]))
    if not scored:
        return []
    return detect.rerank_moments(
        scored, words, profile, llm["model"],
        base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
        streamer=cfg.get("streamer_name", "the streamer"),
        fallback_models=llm.get("fallback_models"),
        persona=cfg.get("persona", "generic"),
        cache_dir=vod_work / "judgments",
        title_strategy=cfg.get("style", {}).get(
            "title_strategy", "curiosity"),
        desired_count=cfg.get("clips", {}).get("count", 3))


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
        for cl in clusters[:30]:
            # Twitch vod_offset is the published clip START. Give the editor
            # a bounded context window around the independent start mode; do
            # not pretend it identifies the payoff.
            s = max(0.0, cl.anchor_start - 12.0)
            e = min(max(cl.end, cl.anchor_start + 28.0), s + 60.0)
            crowd_moments.append(detect.Moment(
                start=s, end=e,
                score=min(10.0, 5.0 + cl.strength / 5.0),
                title=(cl.titles[0] if cl.titles else "crowd moment")[:80],
                reason=f"{cl.clippers} viewers clipped this live "
                       f"({cl.views} clip views)",
                crowd=cl.clippers, crowd_anchor=cl.anchor_start,
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
    desired_count = int(cfg.get("clips", {}).get("count", 3))
    editor_shortlist = min(30, max(24, desired_count * 4))

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
                persona=cfg.get("persona", "generic"), post_bar=6,
                shortlist=editor_shortlist, cache_dir=vod_work / "judgments",
                title_strategy=cfg.get("style", {}).get(
                    "title_strategy", "curiosity"),
                desired_count=desired_count)
        for m in moments:
            m.source = "crowd"
        crowd_inventory = sum(m.decision != "reject" for m in moments)
        # Crowd clips are an excellent prior, but a high requested count can
        # exhaust them. Only then scan the cached whole transcript for extra
        # moments; the merged editor and deterministic gates still enforce the
        # same quality bar.
        auto_expand = crowd_inventory < desired_count + 2
        if (ai_count > 0 or cfg["clips"].get("ai_merge") or auto_expand) and words:
            if auto_expand:
                print(f"Crowd bench has {crowd_inventory} usable candidates "
                      f"for {desired_count} requested; expanding whole-VOD search")
            print("Also scoring the VOD for AI-chosen moments...")
            ai = _ai_moments(cfg, words, profile, chat, llm, report, vod_work)
            for m in ai:
                m.source = "ai"
            # drop AI picks that are the same moment as a crowd pick
            ai = [a for a in ai
                  if not any(abs(a.start - c.start) < 45 for c in moments)]
            moments = moments + ai
            if cfg["clips"].get("ai_merge") or auto_expand:
                # MERGED JUDGE: one head-to-head pass over BOTH pools — the
                # AI rates the crowd's moments against its own and the best
                # win on merit, no quotas. Crowd picks carry their "N viewers
                # clipped this" evidence into the judging.
                report("scoring", "judging crowd vs AI moments head-to-head")
                print(f"Merged judge: {len(moments)} candidates "
                      f"(crowd + AI) -> head-to-head")
                moments = detect.rerank_moments(
                    moments, words, profile, llm["model"],
                    base_url=llm.get("base_url"),
                    api_key_env=llm.get("api_key_env"),
                    streamer=cfg.get("streamer_name", "the streamer"),
                    fallback_models=llm.get("fallback_models"),
                    persona=cfg.get("persona", "generic"),
                    shortlist=editor_shortlist, post_bar=6,
                    cache_dir=vod_work / "judgments",
                    title_strategy=cfg.get("style", {}).get(
                        "title_strategy", "curiosity"),
                    desired_count=desired_count)
                won = {}
                for m in moments:
                    won[m.source] = won.get(m.source, 0) + 1
                print(f"  judge kept: {won.get('crowd', 0)} crowd, "
                      f"{won.get('ai', 0)} AI")
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
            scoring_stats: dict = {}
            moments = detect.score_with_llm(
                words, llm["model"], llm["chunk_minutes"], log=_score_log,
                stats=scoring_stats,
                base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
                streamer=cfg.get("streamer_name", "the streamer"),
                fallback_models=llm.get("fallback_models"), profile=profile,
                persona=cfg.get("persona", "generic"), chat=chat,
                title_strategy=cfg.get("style", {}).get(
                    "title_strategy", "curiosity"),
                reasoning_effort=llm.get("reasoning_effort"))
            # A chunk lost on every model means that slice of the stream was
            # never scored. Put it in progress so a thin batch has a visible
            # cause on /admin/costs instead of reading as a weak VOD.
            if scoring_stats:
                report("scoring",
                       f"{scoring_stats['chunks_scored']}/"
                       f"{scoring_stats['chunks_total']} chunks scored",
                       chunks_total=scoring_stats["chunks_total"],
                       chunks_scored=scoring_stats["chunks_scored"],
                       chunks_unscored=scoring_stats["chunks_unscored"])
            if moments:
                mom_cache.write_text(json.dumps(
                    [{"start": m.start, "end": m.end, "score": m.score,
                      "title": m.title, "hook": m.hook, "reason": m.reason,
                      "archetype": m.archetype,
                      "trigger_quote": m.trigger_quote,
                      "button_quote": m.button_quote,
                      "button_kind": m.button_kind,
                      "trigger_role": m.trigger_role,
                      "button_role": m.button_role}
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
                persona=cfg.get("persona", "generic"),
                cache_dir=vod_work / "judgments",
                title_strategy=cfg.get("style", {}).get(
                    "title_strategy", "curiosity"),
                desired_count=desired_count)
    else:
        print("No API credentials for configured model -> loudness-only mode.")
        moments = detect.moments_from_energy(profile)
    if crowd_moments:  # tier B: crowd anchors join the pool, crowd-flagged
        moments = list(moments) + crowd_moments
    return words, profile, moments


def run(cfg: dict, vod_url: str | None = None) -> dict:
    print(f"pipeline {PIPELINE_VERSION}")
    t0 = time.time()
    # `substage` splits a coarse customer-facing stage into what it actually
    # spent time on. "rendering" measured 67% of wall time, which reads as
    # "encoding is the bottleneck" — but it also covers facecam, the caption
    # pass, master downloads and OCR QA, and a real encode is ~3s. Cost and
    # GPU decisions were being made against that mislabeled bucket.
    report = cfg.get("_progress") or (lambda stage, detail="", **kw: None)
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

    # 1.2 The persona and streamer name in a config file belong to ONE
    # channel. Pointing --vod at somebody else's stream kept them: a maj0r VOD
    # was scored against CaseOh's archetypes and shipped titled "CASEOH ...".
    # Service jobs were fixed on 2026-07-25 by forcing `generic`; local runs
    # still inherited the personal config. Verify against the VOD itself.
    if vod_url and cfg.get("persona", "generic") != "generic":
        try:
            actual = (fetch.vod_info(vod_url).get("channel") or "").lower()
        except Exception:
            actual = ""
        configured = (cfg.get("channel", {}).get("twitch_url", "")
                      .rstrip("/").rsplit("/", 1)[-1].lower())
        if actual and configured and actual != configured:
            print(f"VOD belongs to '{actual}', config is for '{configured}' "
                  f"-> persona=generic, streamer_name='{actual}'")
            cfg = {**cfg, "persona": "generic", "streamer_name": actual}

    # 1.5 Can we actually get video? Segment download is step 7, after
    # transcription and the paid LLM scoring pass, so a VOD whose media Twitch
    # refuses used to cost ~13 minutes and a full scoring bill before failing.
    # Six seconds of the lowest rendition answers it now. Skippable for local
    # experiments that only need the transcript.
    if cfg["clips"].get("media_precheck", True):
        report("finding_vod", "checking VOD media is fetchable",
               substage="media_precheck")
        duration_s = float(cfg.get("_vod_duration_s") or 0.0)
        if not duration_s:
            duration_s = fetch.vod_info(vod_url).get("duration_s") or 0.0
        ok, why = fetch.media_reachable(vod_url, duration_s)
        if not ok:
            raise SystemExit(
                "Twitch is not serving this VOD's video to this machine "
                f"(probe failed before any paid work): {why}")
        print("Media precheck: video is fetchable")

    words, profile, moments = analyze_vod(cfg, vod_url, vod_work, report)
    _raw_cache = vod_work / "loudness_raw.npy"
    import numpy as _np
    raw_profile = _np.load(_raw_cache) if _raw_cache.exists() else None

    # over-select by 4: a deep bench so the downstream gate (arc-verified,
    # then cam-present) has real alternatives — an off-cam or unverified
    # moment gets dropped rather than shipped for lack of a replacement
    want = cfg["clips"]["count"]
    # merged mode: the judge already ranked crowd vs AI on merit, so no
    # per-source quota — best N win outright
    ai_count = 0 if cfg["clips"].get("ai_merge") else int(
        cfg["clips"].get("ai_count", 0))
    crowd_want = want - ai_count

    def _sel(ms, n):
        return detect.select_clips(
            ms, profile, n, cfg["clips"]["min_length"],
            cfg["clips"]["max_length"], words=words,
            min_gap_s=cfg["clips"].get("min_gap_minutes", 20) * 60,
            raw_profile=raw_profile)

    moments = [m for m in moments if m.decision != "reject"]
    # The full-VOD scan/editor call is already paid. Keep a deeper verified
    # bench so additional requested outputs mostly add cheap segment captions
    # and local renders instead of forcing another whole-stream run.
    bench_n = min(30, max(want * 4, want + 8))
    if ai_count > 0:
        # A/B: pick each source's candidates separately so neither crowds out
        # the other; label them for side-by-side comparison
        crowd_ms = [m for m in moments if m.source != "ai"]
        ai_ms = [m for m in moments if m.source == "ai"]
        clips = (_sel(crowd_ms, min(bench_n, crowd_want + 5))
                 + _sel(ai_ms, min(bench_n, ai_count + 5)))
        print(f"A/B bench: {len(crowd_ms)} crowd + {len(ai_ms)} AI moments")
    else:
        clips = _sel(moments, bench_n)
    if not clips:
        raise SystemExit("No clip candidates found.")
    print(f"Selected {len(clips)} clips:")
    for m in clips:
        print(f"  [{m.start/60:6.1f}m] score {m.score:.0f} energy {m.energy:.2f}"
              f"  {m.title}")

    # 6. Download lightweight analysis proxies first. Exact 1080p section
    # downloads re-encode at their boundaries, so doing that for the entire
    # 17-24 candidate bench blocks the first result for minutes. Proxies are
    # sufficient for facecam, transcript and semantic gates; final-quality
    # media is fetched only for the next render wave below.
    out_dir = PROJECT_ROOT / cfg["output"]["dir"] / f"{date.today()}_{vod_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    prior = [
        *out_dir.glob("*.mp4"), *out_dir.glob("*.txt"),
        *out_dir.glob("selection_manifest.json"),
    ]
    if prior:
        archive = out_dir / "_previous" / datetime.now().strftime(
            "%Y%m%d-%H%M%S")
        archive.mkdir(parents=True, exist_ok=True)
        for artifact in prior:
            artifact.replace(archive / artifact.name)
        print(f"Archived {len(prior)} prior top-level artifact(s) to "
              f"{archive.relative_to(PROJECT_ROOT)}")
    style = cfg["style"]

    def _download_one(index_m):
        i, m = index_m
        seg = vod_work / f"probe_{i:02d}.mp4"
        print(f"[{i}/{len(clips)}] Downloading segment "
              f"{m.start:.0f}s-{m.end:.0f}s...")
        # download_segment now retries the ffmpeg route and then refetches the
        # covering HLS fragments itself before giving up, and validates the
        # container rather than trusting an exit code. A raise here means the
        # range is genuinely unavailable, not that one fragment was refused —
        # so dropping the candidate and letting the bench refill is correct.
        try:
            return fetch.download_segment(
                vod_url, m.start, m.end, seg,
                cfg["clips"].get("analysis_quality", "best[height<=360]"))
        except fetch.SegmentUnavailable as e:
            print(f"  ! segment {i}: {e} -> dropping candidate")
            seg.unlink(missing_ok=True)
            return None

    report("clipping", f"downloading {len(clips)} candidate moments",
           substage="probe_download")
    download_workers = min(
        max(1, int(cfg["clips"].get("download_workers", 3))), len(clips))
    with ThreadPoolExecutor(max_workers=download_workers) as pool:
        segs = list(pool.map(_download_one, enumerate(clips, 1)))
    if any(s is None for s in segs):
        clips = [m for m, s in zip(clips, segs) if s is not None]
        segs = [s for s in segs if s is not None]
        if not clips:
            raise RuntimeError("every candidate segment failed to download "
                               "(VOD unavailable or expired)")

    # 7. facecam: the screen is full of faces that aren't the streamer, and
    # OBS scenes move the cam around, so the only durable anchor is the
    # streamer's face identity — established once from probes spread across
    # the whole VOD, then matched inside each segment. Cached per VOD.
    cams: list = [None] * len(segs)
    if style.get("layout", "full") == "split":
        import json as _json

        import numpy as np

        from . import facecam
        report("rendering", "locating facecam", substage="facecam")
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
        elif not matched and pos_box and identity is None:
            # Position consensus is a fallback for "we have no recognizer and
            # no identity", NOT a second opinion that may overrule one.
            #
            # Previously this ran whenever nothing matched, including when
            # identity matching had run and found the streamer in ZERO
            # segments — which is the correct answer on a reaction stream
            # where his cam is tiny, hidden, or off. The consensus box then
            # went onto every clip and the "facecam" pane rendered a crop of
            # the VIDEO he was reacting to, watermark and all, with the same
            # video repeated underneath. Observed on VOD 2835837716, job
            # 744c0357, clip 02.
            cams = [pos_box] * len(segs)
        elif not matched and identity is not None:
            print("Facecam: identity found in 0/%d segments -> full frame "
                  "(streamer off-cam; a forced pane would show content that "
                  "is not him)" % len(segs))
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
        report("rendering", "transcribing clips with the accurate model",
               substage="caption_pass")
        print(f"Caption pass: groq turbo over {len(segs)} segments...")
        try:
            ctx = (f"Twitch gaming stream by {cfg.get('streamer_name', 'a streamer')}. "
                   f"Casual loud speech, screaming, gamer slang.")
            cap_words = transcribe.transcribe_clips_groq(
                items, context=ctx,
                max_workers=cfg["transcribe"].get("caption_workers", 3))
        except Exception as e:
            print(f"  groq caption pass failed ({str(e)[:120]})"
                  + (f" -> local {cap_model}" if cap_model else ""))
            if cap_model:
                cap_words = transcribe.transcribe_clips(
                    items, cap_model, cfg["transcribe"]["compute_type"])
    elif cap_model and cap_model != t_model:
        report("rendering", "transcribing clips with the accurate model",
               substage="caption_pass")
        print(f"Caption pass: {cap_model} over {len(segs)} segments...")
        cap_words = transcribe.transcribe_clips(
            items, cap_model, cfg["transcribe"]["compute_type"])

    # 8.5 Deterministic source gate. A model proposes quotes and roles; this
    # timestamped matcher certifies that cause -> payoff is actually present
    # and ordered. Failed candidates stay in the manifest but never ship.
    source_arcs = []
    source_gate_records = []
    keep_idx = []
    for i, m in enumerate(clips):
        ws = cap_words[i] or [w for w in words if m.start <= w.start <= m.end]
        arc = quality.verify_arc(
            m.trigger_quote, m.button_quote, ws, m.start, m.end,
            button_kind=m.button_kind, trigger_role=m.trigger_role,
            button_role=m.button_role, profile=raw_profile)
        source_arcs.append(arc)
        source_gate_records.append({
            "candidate": i + 1, "title": m.title, "source": m.source,
            "decision": m.decision, "score": m.score,
            "start": m.start, "end": m.end,
            "trigger_quote": m.trigger_quote,
            "button_quote": m.button_quote,
            "button_kind": m.button_kind,
            "trigger_role": m.trigger_role,
            "button_role": m.button_role,
            "arc": arc.to_dict(),
            "rejected": None if arc.passed else arc.reason,
        })
        substance_reject = quality.low_substance_reason(
            m.decision, m.button_kind, m.archetype)
        low_substance = substance_reject is not None
        verdict = ("REJECTED" if low_substance or not arc.passed
                   else "VERIFIED")
        verdict_reason = substance_reject or arc.reason
        print(f"  arc check '{m.title[:45]}': "
              f"{verdict} ({verdict_reason})"
              f"{' (no cam)' if not cams[i] else ''}")
        if arc.passed and not low_substance:
            keep_idx.append(i)
        else:
            m.reject_reason = substance_reject or arc.reason
            source_gate_records[-1]["rejected"] = m.reject_reason
            segs[i].unlink(missing_ok=True)
    if not keep_idx:
        raise SystemExit("No candidate passed the trigger-to-button gate.")

    # Preserve the full verified bench. Rendering and media QA consume it in
    # rank order until the requested number of artifacts pass.
    keep_idx.sort(key=lambda i: (
        clips[i].decision != "post", -clips[i].score, not cams[i]))
    # Don't let a whole batch be game-triggered reactions. Deterministic
    # because the equivalent editor-prompt rule was rationalised away.
    kept_positions = quality.cap_game_triggered(
        [clips[i].trigger_role for i in keep_idx], want)
    if len(kept_positions) < len(keep_idx):
        dropped = len(keep_idx) - len(kept_positions)
        print(f"  bench: deferred {dropped} game-triggered candidate(s) so the "
              f"batch isn't only reactions to game events")
        keep_idx = [keep_idx[p] for p in kept_positions]
    clips = [clips[i] for i in keep_idx]
    segs = [segs[i] for i in keep_idx]
    cams = [cams[i] for i in keep_idx]
    cap_words = [cap_words[i] for i in keep_idx]
    source_arcs = [source_arcs[i] for i in keep_idx]

    # 9. render — ffmpeg is subprocess-bound, so clips render in parallel
    report("rendering", f"rendering {len(clips)} clips",
           substage="encode_and_qa")
    top_frac = style.get("split_top", 0.42)

    manifest = {
        "pipeline_version": PIPELINE_VERSION, "vod_url": vod_url,
        "requested": want, "source_gate": source_gate_records,
        "template": {
            "caption_preset": style.get("preset", "classic"),
            "title_strategy": style.get("title_strategy", "curiosity"),
            "opening_effect": style.get("opening_effect", "punch_zoom"),
        },
        "provenance": {
            "generation": "automatic_pipeline",
            "manual_interventions": [],
        },
        "attempts": [], "shipped": [],
    }
    manifest_lock = threading.Lock()

    def _render_one(out_i, cand_i, m, seg, cam, source_arc):
        i = out_i
        src_seg = seg  # the DOWNLOADED file; `seg` gets reassigned when cut
        source_start = m.start
        tag = f"{m.source.upper()}_" if m.source else ""
        name = f"{i:02d}_{tag}{_slug(m.title)}"
        print(f"[bench {cand_i + 1}/{len(clips)}] Rendering candidate...")
        clip_words = cap_words[cand_i] or [
            w for w in words if m.start <= w.start <= m.end]
        min_dur, target, hard_max = quality.duration_budget(m.archetype)
        min_dur = max(min_dur, float(cfg["clips"].get("min_length", 16)))
        # The verified quotes are evidence endpoints, not the complete story.
        # Game/NPC/video triggers need visible runway before the quoted line:
        # the cheer, attempted rescue, reveal, or action often happens there.
        # Most importantly, NEVER jump-cut inside trigger -> button. Silence
        # in that bridge can carry the visual cause that makes the reaction
        # intelligible.
        pre_roll = quality.contextual_preroll(
            m.trigger_quote, m.trigger_role, m.reason)
        arc_start = quality.arc_window_start(
            source_arc.trigger.start, m.start, pre_roll)
        if (m.button_kind or "").lower() == "scream":
            close_end = quality.closing_beat_end(
                clip_words, source_arc.button.end, m.end)
            arc_end = min(m.end, close_end + .75)
        else:
            arc_end = min(m.end, source_arc.button.end + 1.25)
        if arc_end - arc_start < min_dur:
            arc_start = max(m.start, arc_end - min_dur)
        ass_start, ass_end = arc_start, arc_end
        gap_audit, cuttable_gaps = [], []
        preserve_active_bridge = quality.needs_visual_bridge(
            m.trigger_quote, m.trigger_role, m.button_kind)
        for idle_gap in quality.speech_gaps(
                clip_words, arc_start, arc_end):
            if idle_gap.duration < 3.0:
                continue
            gap_motion = quality.visual_motion(
                seg, idle_gap.start - source_start,
                idle_gap.end - source_start)
            cut = quality.should_cut_idle_gap(
                idle_gap.duration, gap_motion,
                preserve_active=preserve_active_bridge)
            gap_audit.append({
                "start": idle_gap.start, "end": idle_gap.end,
                "duration": idle_gap.duration,
                "motion": {
                    "mean": gap_motion.mean,
                    "static_fraction": gap_motion.static_fraction,
                },
                "cut": cut,
            })
            if cut:
                cuttable_gaps.append(idle_gap)
        ivals = quality.remove_idle_gaps(
            arc_start, arc_end, cuttable_gaps)
        if sum(e - s for s, e in ivals) < min_dur:
            # A technically valid 10-second fragment is still too abrupt for
            # this product. Restore one continuous context span rather than
            # padding or shipping below the configured minimum.
            safe_start = max(m.start, arc_end - min_dur)
            ivals = [(safe_start, arc_end)]
        duration_reject = quality.retained_duration_reason(ivals)
        if duration_reject:
            attempt = {
                "candidate": cand_i + 1, "title": m.title,
                "source_start": m.start, "source_end": m.end,
                "source_arc": source_arc.to_dict(), "intervals": ivals,
                "rejected": [duration_reject],
            }
            with manifest_lock:
                manifest["attempts"].append(attempt)
            print(f"  rejected: {duration_reject}")
            src_seg.unlink(missing_ok=True)
            return None
        # Certify the proposed post-cut timeline. If a silence/LLM cut drops
        # either endpoint or leaves a long tail, fall back to one safe span
        # explicitly bounded by the matched trigger and button.
        def _final_arc(spans):
            remapped = detect.remap_words(clip_words, spans)
            duration = sum(e - s for s, e in spans)
            return quality.verify_arc(
                m.trigger_quote, m.button_quote, remapped, 0.0, duration,
                button_kind=m.button_kind, trigger_role=m.trigger_role,
                button_role=m.button_role,
                profile=quality.remap_profile(raw_profile, spans), final=True)

        final_arc = _final_arc(ivals)
        if not final_arc.passed:
            safe_start = max(m.start, source_arc.trigger.start - pre_roll)
            safe_end = min(m.end, source_arc.button.end + .75)
            if safe_end - safe_start < min_dur:
                safe_start = max(m.start, safe_end - min_dur)
            ivals = [(safe_start, safe_end)]
            final_arc = _final_arc(ivals)
        attempt = {
            "candidate": cand_i + 1, "title": m.title,
            "source_start": m.start, "source_end": m.end,
            "source_arc": source_arc.to_dict(), "intervals": ivals,
            "final_arc": final_arc.to_dict(),
            "retention_gaps": gap_audit,
        }
        violations = quality.metadata_violations(
            m.title, m.hook, final_arc, m.button_role,
            title_strategy=style.get("title_strategy", "curiosity"))
        if not final_arc.passed or violations:
            attempt["rejected"] = violations or [final_arc.reason]
            with manifest_lock:
                manifest["attempts"].append(attempt)
            print(f"  rejected after cut planning: "
                  f"{'; '.join(attempt['rejected'])}")
            src_seg.unlink(missing_ok=True)
            return None

        # apply whenever the kept spans don't cover the whole segment. Gating
        # this on len(ivals) > 1 silently threw away every single-span cut —
        # "keep just this 17s window" is smart-cut's most common answer, and
        # those clips shipped at full length.
        trimmed = bool(ivals) and (len(ivals) > 1
                                   or ivals[0][0] > source_start + 0.05
                                   or ivals[0][1] < m.end - 0.05)
        if trimmed:
            saved = (m.end - source_start) - sum(e - s for s, e in ivals)
            cuts = f"{len(ivals) - 1} silence(s)" if len(ivals) > 1 else "to one span"
            print(f"  jump-cutting {cuts}, -{saved:.1f}s dead air")
            clip_words = detect.remap_words(clip_words, ivals)
            ass_start, ass_end = 0.0, sum(e - s for s, e in ivals)
        ass = render.build_ass(clip_words, ass_start, ass_end, style,
                               vod_work / f"seg_c{cand_i + 1:02d}.ass",
                               hook=m.hook, hook_color_idx=i - 1,
                               hook_pos=top_frac if cam else None)
        # Centre the 9:16 slice on whatever is actually moving. A fixed centre
        # crop keeps ~half the frame width, so slot reels, loot rolls and
        # killfeeds at the edges were being cut out of the very clips that
        # were about them ("the gambling wasn't even in frame"). Returns None
        # on a static or evenly-busy scene, which keeps the old framing.
        action_x = None
        if style.get("action_crop", True):
            try:
                probe_start = max(
                    0.0, source_arc.trigger.start - source_start - 1.0)
                probe_end = min(
                    m.end - source_start,
                    source_arc.button.end - source_start + 1.0)
                action_x = render.action_center_x(
                    seg,
                    exclude=((cam[0], cam[0] + cam[2]) if cam else None),
                    start=probe_start, end=probe_end)
            except Exception as e:      # framing is never worth a failed job
                print(f"  action-crop probe failed ({type(e).__name__}) "
                      f"-> default framing")
            if action_x is not None:
                print(f"  action-centred crop at {action_x:.0%} of frame width")
        visibility_required = quality.visual_payoff_required(
            m.trigger_role, m.button_kind)
        try:
            source_width, source_height = render._dims(seg)
            visibility = render.audit_payoff_visibility(
                source_width, source_height, cam, top_frac, action_x,
                visibility_required)
        except Exception as e:
            visibility = render.PayoffVisibility(
                visibility_required, "indeterminate",
                f"visibility audit unavailable: {type(e).__name__}")
        attempt["payoff_visibility"] = visibility.to_dict()
        if not visibility.passed:
            attempt["rejected"] = [visibility.reason]
            with manifest_lock:
                manifest["attempts"].append(attempt)
            print(f"  rejected before render: {visibility.reason}")
            src_seg.unlink(missing_ok=True)
            return None
        final = render.render_short(seg, ass, out_dir / f"{name}.mp4",
                                    style.get("crop", "center"),
                                    cam=cam, top_frac=top_frac,
                                    brand=cfg["output"].get("brand", ""),
                                    opening_effect=style.get(
                                        "opening_effect", "punch_zoom"),
                                    keep=(
                                        [(s - source_start, e - source_start)
                                         for s, e in ivals]
                                        if trimmed else None),
                                    action_x=action_x)
        media_qa = quality.inspect_media(
            final, expected_duration=sum(e - s for s, e in ivals))
        attempt["media_qa"] = media_qa.to_dict()
        with manifest_lock:
            manifest["attempts"].append(attempt)
        if not media_qa.passed:
            print(f"  artifact QA failed: {'; '.join(media_qa.errors)}")
            final.unlink(missing_ok=True)
            seg.unlink(missing_ok=True)
            if src_seg != seg:
                src_seg.unlink(missing_ok=True)
            return None
        meta = out_dir / f"{name}.txt"
        desc = cfg["output"]["description_template"].format(title=m.title)
        picked = ("viewer clips (crowd)" if m.source == "crowd"
                  else "AI scoring" if m.source == "ai" else "auto")
        meta.write_text(
            f"TITLE: {m.title}\n\nDESCRIPTION:\n{desc}\n"
            f"PICKED BY: {picked}\n"
            f"WHY: {m.reason}\nSOURCE: {vod_url} @ {m.start:.0f}s\n"
            f"ARC: {m.trigger_quote} -> {m.button_quote}\n")
        print(f"  -> {final.relative_to(PROJECT_ROOT)}")
        # delete the ACTUAL files this clip used. Rebuilding the name from `i`
        # deleted another thread's input whenever the arc gate dropped a clip:
        # segments are numbered before the drop, render indices after it, so
        # clip 3 was deleting seg_03 while clip 2 was still reading it.
        seg.unlink(missing_ok=True)  # keep disk usage low
        if src_seg != seg:
            src_seg.unlink(missing_ok=True)  # pre-cut original
        result = {"file": str(final), "title": m.title, "hook": m.hook,
                  "score": m.score, "start_s": m.start, "end_s": m.end,
                  "_candidate_index": cand_i,
                  "duration_s": media_qa.duration,
                  "source": m.source,
                  "archetype": m.archetype,
                  "trigger_role": m.trigger_role,
                  "button_kind": m.button_kind,
                  "payoff_visibility": visibility.to_dict(),
                  "edit_recipe": {
                      "source_start": source_start,
                      "source_end": m.end,
                      "keep_intervals": ivals,
                      "cam": list(cam) if cam else None,
                  }}
        with manifest_lock:
            manifest["shipped"].append(result)
        return result

    # Automatic bench refill: continue through verified candidates until N
    # artifacts pass both semantic and media QA.
    results = []
    ready = cfg.get("_clip_ready") or (lambda result: None)
    render_workers = max(1, min(
        int(cfg["clips"].get("render_workers", 2)), 2))
    bench = list(enumerate(zip(clips, segs, cams, source_arcs)))
    cursor = 0
    # Refill in small waves. This keeps at most two CPU encodes active and
    # avoids rendering the entire bench when the first candidates pass.
    while cursor < len(bench) and len(results) < want:
        need = want - len(results)
        wave = bench[cursor:cursor + min(render_workers, need)]
        cursor += len(wave)

        def _master(entry):
            cand_i, (m, probe, cam, source_arc) = entry
            report(
                "rendering",
                f"{len(results)}/{want} ready — fetching final-quality winner",
                substage="master_download")
            try:
                master = fetch.download_segment(
                    vod_url, m.start, m.end,
                    vod_work / f"master_c{cand_i + 1:02d}.mp4",
                    cfg["clips"]["quality"])
            except fetch.SegmentUnavailable as e:
                # The probe for this range downloaded fine, so a refusal at
                # final quality is this rendition/range, not the whole VOD.
                # Drop the candidate and let the bench refill instead of
                # failing a job that already has verified alternatives.
                print(f"  ! master for candidate {cand_i + 1}: {e} -> skipping")
                probe.unlink(missing_ok=True)
                return None
            probe.unlink(missing_ok=True)
            return cand_i, m, master, cam, source_arc

        # The same two-slot ceiling covers final-quality network/section work
        # and the following encodes. We never prepare the rest of the bench
        # until a QA failure proves that a refill is needed.
        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            prepared = [p for p in pool.map(_master, wave) if p is not None]
        if not prepared:
            continue
        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            futures = {
                pool.submit(
                    _render_one, cand_i + 1, cand_i, m, seg, cam, source_arc
                ): cand_i
                for cand_i, m, seg, cam, source_arc in prepared
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                    ready(result)
    for _, (_, seg, _, _) in bench[cursor:]:
        seg.unlink(missing_ok=True)
    results.sort(key=lambda result: result["_candidate_index"])
    manifest["shipped"].sort(
        key=lambda result: result.get("_candidate_index", 0))
    manifest["fulfilled"] = len(results) == want
    (out_dir / "selection_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    if not results:
        raise SystemExit("All rendered candidates failed final artifact QA.")

    # cleanup big audio file, keep transcript cache
    for f in vod_work.glob("vod_audio.*"):
        f.unlink()

    mins = (time.time() - t0) / 60
    print(f"\nDone in {mins:.1f} min. Shorts + titles in: "
          f"{out_dir.relative_to(PROJECT_ROOT)}/")
    print("Review each clip, then upload from the YouTube app/studio.")
    rejected_attempts = [
        a for a in manifest["attempts"] if a.get("rejected")]
    return {
        "out_dir": str(out_dir),
        "vod_url": vod_url,
        "clips": results,
        "requested": want,
        "fulfilled": manifest["fulfilled"],
        "candidate_count": len(source_gate_records),
        "verified_count": len(keep_idx),
        "rejected_count": (
            sum(bool(r.get("rejected")) for r in source_gate_records)
            + len(rejected_attempts)
        ),
        "rejection_reasons": [
            reason
            for attempt in rejected_attempts
            for reason in attempt.get("rejected", [])
        ][:8],
    }


def clean_work() -> None:
    work = PROJECT_ROOT / "work"
    if work.exists():
        shutil.rmtree(work)
        print("Cleared work/ directory.")
