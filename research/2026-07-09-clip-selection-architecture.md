# Prompted clipper-model architecture (research, 2026-07-09)

## What commercial tools do
- OpusClip: virality score = hook strength (first 3s) + emotional arc + value + trend. 50-60% of drop-off happens in first 3s — hook dominates.
- PogChampNet (closest prior art): chat-spike keywords for RECALL (candidate windows), human/classifier for precision. Failure mode: energy-without-payoff (loud but boring). LLM semantic pass = the fix.
- Consensus architecture everywhere: multi-signal candidate gen (audio/chat energy) → LLM semantic judgment → hook-specific scoring.

## Prompting findings
- Pointwise rubric scores = noisy/uncalibrated. Pairwise/tournament = more accurate BUT O(n²). Production pattern: pointwise per-chunk (recall) → pairwise tournament in final rerank only.
- **Few-shot with the channel's OWN top-retention clips = highest-leverage lever.** 5-8 transcript excerpts of known hits per streamer as calibration anchors ("this is a 9/10, here's why"). Also negative examples from flops.
- CoT-before-score: reasoning BEFORE numeric score = less variance, better human agreement, free debug trace.
- Persona prompts help subjective/creative tasks (clip selection = yes) but pair with hard rubric.
- Editor pass must be a DIFFERENT prompt (global critic, cuts duplicates, verifies hook head-to-head), not stage-1 + "be stricter".

## Cheap signals to add (no vision models)
1. **Speech-rate spikes** — free from existing word timestamps. Excitement/panic marker.
2. **Chat replay spikes** — Twitch GQL/IRC download; message-rate + emote density per 5s. Known strong signal (PogChampNet, Eklipse). Use as VELOCITY signal only (sarcasm breaks sentiment).
3. **Laughter/scream acoustic classifier** — 93%+ accuracy from pitch/MFCC features; separates loud-funny from loud-angry.
4. **Silence-after-spike shape** — comedic pause detector, free from existing loudness profile (spike → cliff).

## Persona rubrics
- CaseOh: register shift (talk→scream in 1-2 sentences), self-interruption fragments ("WAIT— NO— NO NO—"), 3-beat shape (setup → scream → TAG JOKE). Scream without tag = incomplete, extend 3-5s for button. Hard topic-switch after peak = clean out-point.
- Jynxzi: profanity density + chained exclamations + game-state callouts (clutch/ace/1v4) near spike. Rage/hype arcs build 30-90s — cut from TOP of escalation, not loudest word. Teammate/chat reaction line after peak = button. Generic complaining w/o payoff = unlikeable, skip.
- Universal binary gate: SELF-CONTAINED (zero outside context) — separate from funny/energy score.

## Evaluation loop (no training)
- Metric: 3s retention (hook quality) + 30s retention (sustain), NOT views. Medians not means.
- Tag every published Short with prompt version + reasoning trace + fired signals.
- Weekly: bottom decile → negative few-shot examples; top decile → positive anchors (refresh).
- A/B: alternate prompts by VOD (odd/even), ≥15-20 Shorts per arm before comparing.

## Recommended pipeline (stages)
0. Signal extraction: transcript + loudness (have) + speech-rate + laughter classifier + silence-shape + chat velocity/emote density → aligned energy timeline
1. Candidate gen per 10-min chunk (gpt-5-mini): persona rubric + few-shot anchors + energy timeline; CoT-before-score; JSON {start,end,category,reasoning,hook_strength,energy,comedy_or_hype,self_contained,has_button,cut_start,cut_end}; 0-4 candidates per chunk, forcing none OK
2. Cross-chunk dedup + hard-cut non-self-contained + cut LLM-only picks with zero signal corroboration
3. Editor pass (separate prompt, whole-VOD, tournament rerank to final N): diversity check, head-to-head hooks, re-verify self-containment/button, distrust high-energy+thin-reasoning
4. Publish + tag for eval loop

## Draft prompts
Full Stage-1 and Stage-3 prompt drafts (with CaseOh + Jynxzi persona blocks) are in the agent transcript 2026-07-09 — copy from session before implementing detect.py changes.
