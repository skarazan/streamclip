# Roadmap: pipeline → product

Current state: working local pipeline (this repo) — VOD → whisper transcript →
LLM humor scoring → facecam-split styled shorts. That's the engine; the product
is everything around it.

## Phase 0 — Validation (now, $0) — waitlist-first

- [ ] Landing page (`web/landing/`) deployed to Vercel/Cloudflare Pages free;
      wire waitlist form to Tally/Formspree free tier
- [ ] Drive traffic $0: founder's channel posts daily (tool output = the demo),
      short "how it was made" clips on TikTok/Twitter, gaming-streamer Discords
- [ ] Run founder's channel daily with the pipeline; collect retention data
- [ ] Switch dev/testing to free API tiers (`llm.base_url` — Groq / Gemini /
      OpenRouter free models; see config.yaml). Benchmark pick-quality of 2-3
      free models against claude-code baseline on the same VOD
- [ ] Per-channel style config: extract `style:` into per-customer profiles

**Exit gate: ≥30 waitlist signups with real Twitch usernames. No gate pass → change pitch/audience, not code.**

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

---

# EXECUTION PLAN v2 — 2026-07-04 (current state -> paid product)

State now: engine + cloud worker + dashboard + auth + credits all LIVE at $0/mo.
Missing: public URL, job-creation UI, EventSub, styles, billing, legal, launch.

## Phase 1 — Usable private product (this week)
| # | Task | Owner | Done when |
|---|---|---|---|
| 1.1 | Pick name, buy domain, grab socials | YOU | domain in hand |
| 1.2 | Vercel account + connect repo | YOU | then me: deploy, env vars, new redirect URLs in Twitch+Supabase | app on real URL |
| 1.3 | ✅ DONE 07-05: "Clip a VOD" button + POST /api/jobs (credit check, 1-job-at-a-time, URL validation; worker re-checks all + own-channel) | ME | user can self-serve a job |
| 1.4 | ✅ DONE 07-05 (chain + editor rerank pass deployed, verified on Jynxzi) | ME | quota outage != bad clips |
| 1.5 | ✅ DONE 07-05: 4 presets (classic/beast/boxed/neon) + dashboard picker; Montserrat+Anton bundled; renderer border_style+blur; frame-verified on worker | ME | new user picks a look in onboarding |
| 1.6 | Email "your clips are ready" (Resend free) | ME | notification lands |
| 1.7 | Worker errors -> Discord webhook | ME | failures ping us, not Modal email |

## Phase 2 — The automation edge
| 2.1 | EventSub: stream.offline webhook route (needs 1.2 URL) | ME | streamer goes offline -> job appears |
| 2.2 | Per-user auto-clip toggle wires to EventSub subscribe/unsubscribe | ME | opt-in automation |
| 2.3 | Delay tuning (VOD availability) + dedupe per stream | ME | no double jobs |

## Phase 3 — Money
| 3.1 | Legal identity (sole prop / IE where tax-resident) | YOU | can open Stripe |
| 3.2 | Stripe: $14.99/mo Payment Link (8 credits/mo) + top-up packs (5 for $7.50) | YOU acct, ME wiring | checkout works |
| 3.3 | Stripe webhook -> credit grants + plan flag | ME | payment = credits, automatic |
| 3.4 | ToS + Privacy pages (own-VOD rights, music disclaimer, credits policy) | ME draft, YOU approve | published |
| 3.5 | Pricing page + final landing copy (use competitor receipts) | ME | public story matches product |

## Phase 4 — Beta -> launch
| 4.1 | 5-10 beta streamers (Discords, r/Twitch, your community); founder QA every batch | YOU+ME | 10 active users |
| 4.2 | Feedback buttons wired (column exists) -> scorer prompt tuning | ME | thumbs data flowing |
| 4.3 | Demo video (15s script in DECISIONS) + Wayin/Opus comparison post | YOU film, ME cut | assets ready |
| 4.4 | Public launch: PH + build-in-public + daily channel output | YOU | first stranger signup |
| 4.5 | Metrics: signups/activation/wk2 retention/MRR/churn on /admin | ME | weekly review vs kill criteria |

## Standing ops
- Modal credit + Gemini quota watch; flip to paid scoring (~$0.05/stream) at first paying-customer pinch
- Benchmark scorers quarterly (3.5-flash vs alternatives, same VOD)
- Kill criteria unchanged: <15 paying at 90d post-beta -> stop/pivot
