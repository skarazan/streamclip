# Roadmap: pipeline → product

Current state: working local pipeline (this repo) — VOD → whisper transcript →
LLM humor scoring → facecam-split styled shorts. That's the engine; the product
is everything around it.

## Phase 0 — Validation (now, $0)

- [ ] Concierge test per BUSINESS.md (40 DMs, 3 free shorts each, ask for $15/mo)
- [ ] Run founder's channel daily with the pipeline; collect retention data
- [ ] Switch dev/testing to free API tiers (`llm.base_url` — Groq / Gemini /
      OpenRouter free models; see config.yaml). Benchmark pick-quality of 2-3
      free models against claude-code baseline on the same VOD
- [ ] Per-channel style config: extract `style:` into per-customer profiles

**Exit gate: ≥5 paying commitments. No gate pass → no Phase 1.**

## Phase 1 — Manual-onboarding MVP (2-4 weeks of evenings)

Goal: 10 concierge customers served semi-automatically, founder still in loop.

- [ ] Queue worker: wrap pipeline in a job runner (Redis/RQ or SQS) on one
      cheap VPS; jobs = {channel, vod_url, style_profile, credits}
- [ ] Twitch Helix API + OAuth (replace yt-dlp channel scraping for VOD
      listing; keep yt-dlp for media download until it hurts)
- [ ] Simple delivery: S3/R2 presigned links emailed/DM'd when clips ready
- [ ] Per-customer usage ledger (credits burned) — a table, not a billing system
- [ ] Auto-trigger: poll for stream end → enqueue latest VOD

## Phase 2 — Self-serve product

- [ ] Web app: Twitch login → dashboard (clips grid, scores, download, style editor)
- [ ] Stripe subscription + credit metering + 2-credit trial
- [ ] Twilio Verify phone gate on trial
- [ ] Style editor UI writing the per-channel style profile
- [ ] Feedback loop: 👍/👎 per clip → appended examples in scoring prompt

## Phase 3 — Scale & quality

- [ ] GPU batch worker for whisper (biggest COGS cut: ~$1-2 → ~$0.15/VOD)
- [ ] Speaker-tracking crop (upgrade from static facecam box)
- [ ] Auto-post to YouTube/TikTok via customer OAuth
- [ ] Multi-streamer prompt profiles; non-gaming verticals if pulled

## Repo layout plan

```
clipfarm/        # the engine (current code) — stays importable as a package
worker/          # Phase 1: queue consumer wrapping clipfarm.pipeline
api/             # Phase 2: FastAPI backend (auth, billing, credits, jobs)
web/             # Phase 2: frontend
infra/           # deploy scripts / IaC
```

Personal-use copy lives at `~/clipfarm` (untracked, with .env and claude-code
scoring) — this repo is the product line; don't develop in the personal copy.
