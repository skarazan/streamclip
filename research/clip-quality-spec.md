# CLIP QUALITY SPEC — what defines a good clip, and how we find it automatically
*Synthesized 2026-07-13 from two research passes (viral-clip anatomy; selection ground truth).
This is the canonical selection reference. The pipeline should be measured against it.*

## 0. The core finding

**LLMs are measurably bad humor judges** (best model: ρ=0.27 correlation with humans —
vs ~80% agreement on normal judging tasks) and their documented #1 failure is over-rating
loud/absurd/energetic content. **Loudness is the weakest, most false-positive-prone signal
in every academic study.** Our "loud fragments that flop" was the textbook outcome, not bad luck.

The fix is architectural, not prompt polish: **humans must supply the humor judgment,
automatically** — via Twitch's own viewer-created clips (crowd ground truth), chat
behavior, and structural markers. The LLM's job shrinks to what it's actually good at:
boundaries, titles, captions, archetype classification.

## 1. What defines a good clip (moment > packaging)

For Shorts, **~80-90% of virality is the moment + first 2 seconds**; title/desc ~10-20%
(search + context only); thumbnail ~0% (feed autoplays). The top Twitch clips of CaseOh/
xQc literally have titles like "cos", "wow", "?????????" — raw moment carried them.

A good clip has ALL of:
1. **A legible trigger** — the viewer sees/hears WHAT caused the reaction, inside the clip.
2. **Genuine reaction** — real surprise/anger/joy, not performed hype. (Genuineness is the
   #1 top-1% differentiator; crowds detect it, models don't.)
3. **Disproportion or reversal** — expectation violated (chair through wall on a chill
   stream; max bravado → instant death). Magnitude of surprise separates top-1% from good.
4. **Self-contained stakes** — legible with zero channel knowledge. Agencies report
   self-containedness ≈ 2x CTR. Running-bit callbacks underperform with new viewers.
5. **Quotability** — a repeatable line extends life across platforms ("my chair broke").
6. **A button** — ends on payoff/tag, not a trail-off.

## 2. Archetype taxonomy (from dissecting 20+ actually-viral clips)

Achievable with our editing (captions + facecam crop, no zooms/replays/B-roll):
| Archetype | Freq | Notes |
|---|---|---|
| Banter/roast (vs chat or guest) | very high | speech+face carries it fully |
| Drama/controversy soundbite | med-high | pure dialogue; deadpan delivery = hardest to auto-detect |
| Bit/roleplay commitment | med | sustained persona voice; 15-40s |
| One-word stinger reaction | very high on Twitch | 1-3 words, face carries 90% — transcript-invisible, crowd-signal detectable |
| Wholesome/emotional break | med | LOW energy + sincere = a highlight class we systematically missed |
| Escalating comedic rage arc | high | verbal escalation survives crop; visual gags lost |
| Perfect-timing coincidence (verbal) | med | works when streamer narrates it |

**Structurally incompatible — auto-downweight, do not pick:**
- Instant physical fail (chair break, backflip) — payoff outside the facecam crop
- Destructive rage quit — object destruction needs wide shot
- IRL/relationship reveals — second person out of frame
- Clutch moments whose stakes need killcam/replay/HUD

## 3. Transcript-detectable signatures (feed the scorer these, not raw loudness)

- **Banter:** fast turn-taking (<2s alternation), retort → laughter cluster within 1-2s
- **Escalating rage:** same phrase repeated 3+ times, rising pitch/volume TREND (not spike)
- **Coincidence:** disbelief cluster ("wait / no way / did he just") + self-narration
- **Non-sequitur:** hard topic discontinuity vs prior 10s + confused-question cluster
- **Bit commitment:** sustained alternate diction 15s+ that doesn't reset
- **Wholesome:** sincerity lexicon + slower cadence + LOW energy (absence of spike = signal)
- **Rage quit:** profanity spike → mid-word cutoff → dead air (the SILENCE is the signature)
- **Deadpan soundbite:** high semantic charge + flat delivery (tone contradicts text)
- **Stinger:** 1-3 token transcript — undetectable from text; only crowd signal finds these

Two hard warnings baked in: **loud ≠ viral** (velocity+valence spikes miss irony, subtext,
inside jokes), and **silence/flatness are signals** (three strong archetypes are defined by
absence of the loud signature).

## 4. Ground truth: Twitch viewer clips (THE primary signal)

Viewers press the clip button live = a human judging "worth showing someone," per moment,
per stream, free. Implementation:

- `GET /helix/clips?broadcaster_id=X&started_at=..&ended_at=..` (app access token via
  client-credentials; 800 req/min bucket; results pre-sorted by view_count desc)
- `vod_offset` maps each clip to the exact VOD second. **Backfills async** — query ~1-24h
  after stream end (fits our schedule; worker can requeue until offsets populate)
- No video_id filter → window by the VOD's created_at + duration; match video_id after backfill
- Pagination caps ~1000/window → split windows on high-clip channels

**Clustering (many people clip the same moment seconds apart):**
- Twitch defines `vod_offset` as the **start of the published clip**, not the
  button press or payoff timestamp. It is setup-window evidence only.
- Exact clip IDs are deduplicated; one creator contributes at most one vote
  inside a six-second start neighborhood.
- Smooth start timestamps (6s Gaussian), find independent local modes, and
  assign each clip directly to its nearest mode within 15s. Do not use
  single-link/DBSCAN chaining: A≈B and B≈C must never imply A≈C.
- Moment strength = distinct creator_ids (primary; dedupes power-clippers)
  + log(summed view_count) (secondary; views lag hours-days — recency-aware)
- Median start within each bounded mode is a robust context anchor. The
  trigger/button matcher—not the crowd timestamp—determines final boundaries.
- `is_featured` = streamer/editor manually vouched → bonus weight
- Sparse/zero clips (small channels, clips disabled) → fall back to current signal stack

**Also an eval harness:** re-query days later; moments whose Twitch clips gained big views
but we didn't pick = counted misses. Real accuracy metric, no LLM judging itself. All prompt/
weight changes must beat this metric before shipping (protects against reward-hacking drift).

## 5. Cheap corroborating signals (all free)

- **"Clip that" detection:** "clip it/clip that/someone clip" in transcript OR chat = near-ground-truth
- **Streamer's own laughter** after their line (self-laugh = genuine)
- **Chat velocity z-spikes** (have it) — recall signal only, require lexical/emote diversity
  to filter poll/vote false positives
- **Voice-energy DELTA vs streamer's rolling baseline** (replaces raw dB — Eklipse's own fix)
- **Chat semantics beat chat volume** (EMNLP 2017): emote-burst composition, all-caps, repeated phrases

## 6. Scoring architecture v3 (crowd-first)

```
1. Twitch clips API → bounded start modes → top 24-30 candidates
2. + "clip that" callouts + chat z-spikes not already covered → candidate set
3. Transcribe ONLY ±2min around candidates (~30-40min audio vs 7h — Groq free tier trivial)
4. LLM per candidate (gpt-5-mini or fallback — small prompts):
   a. classify archetype (taxonomy §2) → REJECT incompatible archetypes (§2 bottom)
   b. rubric check, required elements: what's the trigger? what's the reversal?
      is it self-contained? where's the button? (proving understanding before judging —
      beats 1-10 scores in every study)
   c. propose boundaries plus verbatim trigger/button quotes and speaker roles
5. Deterministic gate localizes trigger then button in timestamped words,
   rejects NPC/game/video-owned payoffs, and requires payoff in the final 38%
   with <=2.75s tail on the actual post-cut timeline
6. Final rank = crowd strength (dominant) × archetype-compatibility × rubric completeness
   — LLM taste NEVER outranks crowd signal
7. Render from an archetype duration budget, inspect 1080x1920/CFR/audio/A-V
   sync plus conservative creator-dashboard OCR, and refill from the bench
   until the requested count passes or verified candidates are exhausted
```

Cost per stream: clips API free, chat free, ~35min Groq audio free, ~15 small LLM calls
(~$0.01-0.03). No whole-VOD scoring. No Opus. ~10x cheaper than current.

## 7. Self-improvement loop (later, after v3 stable)

- Weekly: top/bottom deciles of OUR published shorts (3s + 30s retention, medians) →
  refresh few-shot anchors; misses vs Twitch-clip ground truth → negative examples
- Prompt/weight variants as bandit arms, reward = REAL retention (never LLM self-scores —
  documented reward-hacking: judges reward absurdity drift)
- YouTube's own gate: ~65% retention on <30s Shorts decides distribution — that's the target

## 8. Long-form comps under this spec

- Same crowd-first moments feed comps (already have music-risk filter, hot open, cards)
- Opener rule upgrade: highest crowd-strength moment that is also archetype-compatible
  and instantly legible — the crowd count IS the "zero-context legibility" proxy
- Retention target: fix the 0:00-2:30 cliff (comp #1: 50% gone by 1:20)

## Appendix: prior analytics (see analytics-intel.md)
Sub-20s + stakes-titles win; reaction-framing > object-framing; comp retention leaks at entry.
