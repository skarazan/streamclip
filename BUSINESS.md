# StreamClip — Business Plan (v1, 2026-07-24)

Owner: COO (Fable). Engineering owner: CTO (Sol 5.6 / Codex).
Companion docs: PROJECT.md (how the product works), SPEC-web-split.md (what to
build next on the web side).

---

## 1. Product & positioning

**StreamClip turns a Twitch VOD into upload-ready vertical Shorts, fully
automatically.** No editor, no picking screen — the streamer streams, clips
appear. The differentiators, in the order customers feel them:

1. **Crowd-anchored selection** — clips are picked from evidence (viewer
   clips, chat spikes), not LLM vibes. Nobody else in the space grounds
   selection in what the audience actually clipped.
2. **Arc-verified shipping gate** — a clip only ships when its setup→payoff is
   verifiably inside it. This is why output doesn't feel random.
3. **Works for small streamers** (Tier C signal stack) — the paying customer
   has near-zero viewer clips; competitors' "AI highlights" are worst exactly
   there.

Comparable tools (Opus Clip, Eklipse, Sizzle, Powder): $10–30/mo, generic
LLM-scored highlights, weak on gaming/react formats, none do crowd grounding.
We price inside the band and win on output quality per gaming stream.

**Positioning line:** "Your community already marks the funny moments.
StreamClip turns them into Shorts while you sleep."

## 2. Pricing

- **Starter — $14.99/mo**: 8 VOD credits/mo (1 credit = one VOD processed →
  3 shorts + metadata). Extra credits $1.99 each or 5 for $7.99.
- **Creator — $29.99/mo**: 20 credits, priority queue, style profiles,
  compilation builder when it ships.
- **Trial**: 2 credits, phone-verified (Twilio) to stop farm abuse. No card
  required — card-required trials kill conversion at this price point.

Credits meter the one real variable cost (compute per VOD) so a daily
streamer can't make us cash-negative on a flat plan. Yearly (2 months free)
added only after churn data exists.

## 3. Unit economics

### COGS per VOD (~6h stream, current CPU pipeline)

| Item | Cost | Note |
|---|---|---|
| Transcription (Groq whisper-large-v3-turbo) | ~$0.13 | measured, ~200x realtime |
| LLM scoring + editor + judge | $0.00–0.05 | Gemini free tier now; budget gpt-5-mini rates for reliability at scale |
| Modal compute (CPU, ~15–25 min) | ~$0.25–0.50 | 8 vCPU worker; the big lever (see §6) |
| Segment download bandwidth | ~$0 | ingress free |
| R2 storage + egress | ~$0.01 | egress is free on R2; clips ~100MB/batch |
| **Total** | **~$0.45–0.70** | round to **$0.70 planning figure** |

### Contribution per subscriber (Starter, worst case all 8 credits used)

- Revenue $14.99 − Stripe (2.9% + $0.30 ≈ $0.73) − COGS (8 × $0.70 = $5.60)
- **≈ $8.66/sub/mo contribution (58% margin worst case; ~75% at typical 5-VOD usage)**
- Extra credits at $1.99 vs $0.70 COGS ≈ 65% margin, same band. Healthy.

**Margin floor rule: no feature ships that pushes COGS per VOD above $1.00
without a price change.** (A GPU whisper batch worker CUTS cost, fine; a
"re-render with 5 variants" feature would triple render compute, gate it to
Creator.)

### Fixed costs (monthly)

| Item | Now (pre-launch) | At ~50 subs |
|---|---|---|
| Supabase | $0 | $25 (Pro) |
| Vercel (dashboard + landing) | $0 | $20 |
| Domain + email (Resend) | ~$2 | ~$2 |
| Twilio Verify | ~$0 | ~$5 (trials) |
| Sentry/uptime/analytics | $0 (free tiers) | $0–26 |
| **Total** | **≈ $2** | **≈ $52–78** |

Founder cost ceiling remains **$50/mo until first revenue**; the free tiers
hold to roughly 30–50 users, which is conveniently our validation gate.

### Break-even and targets

- Fixed ~$78/mo at scale tiers → **9 Starter subs = break-even.**
- $500/mo net (ramen checkpoint): ~60 subs. $2k/mo: ~230 subs, or ~150 with a
  30% Creator mix — Creator mix is the real income lever, not volume.
- Phase gates stay as ROADMAP has them: **≥30 waitlist signups with real
  Twitch usernames before any more product spend**; 10 concierge customers
  before self-serve polish.

## 4. What is still missing for a sellable product (gap diagnosis)

Ordered by "blocks charging money" first:

**P0 — cannot take money without these**
1. **Stripe**: subscription + credit packs + webhook → credit ledger. Ledger
   table exists (`credit_events`); no billing attached.
2. **Credit enforcement in the worker**: job refused when balance ≤ 0
   (currently founder accounts have infinite credits).
3. **Legal/trust pages**: ToS, Privacy, cookie consent, refund policy —
   required by Stripe, Twitch API ToS compliance, and GDPR (EU streamers are
   a big segment).
4. **Auth hardening**: session expiry, Twitch token refresh, account deletion
   (GDPR art. 17), support email.

**P1 — cannot retain without these**
5. **Auto-trigger**: Twitch EventSub `stream.offline` → enqueue VOD. The
   whole pitch is "clips appear while you sleep"; today jobs are manual.
6. **Notifications**: email/Discord "your clips are ready" with thumbnails.
7. **Reliability visibility**: status banner in dashboard when workers are
   down (motivates the repo split, SPEC-web-split.md), Sentry on both
   services, uptime monitor on the poll loop.
8. **Onboarding flow**: connect Twitch → pick template → first batch runs on
   most recent VOD automatically. Time-to-first-clip is THE activation metric;
   target < 20 min from signup.

**P2 — growth**
9. Landing page conversion pass (see SPEC-web-split.md §4).
10. Compilation builder as a paid differentiator (exists in pipeline, not in
    product).
11. Retention feedback loop (per-clip 👍/👎 → scoring prompt) — also our moat:
    proprietary preference data.
12. Auto-post to YouTube/TikTok via customer OAuth (Creator-plan feature).

## 5. Risks

| Risk | Exposure | Mitigation |
|---|---|---|
| Twitch ToS / API revocation | fatal | stay on official Helix/EventSub for data; VOD media download via yt-dlp is the gray zone — isolate it so a switch to official means (or streamer-side upload) is one module |
| Free LLM tiers vanish (Gemini 429s already daily) | pipeline stalls | fallback chain exists; budget line assumes PAID gpt-5-mini rates so a forced switch doesn't break margin |
| One viral customer floods queue | queue latency, COGS spike | credits already cap spend; add per-user concurrency 1 |
| Copyright/DMCA on clips | account risk is customer's, platform risk ours | ToS clause: customer owns/licenses their stream content; we process on their behalf |
| Founder burnout (evenings-only) | schedule slip | Codex owns code, Fable owns docs/business; founder's job narrows to review + marketing |

## 6. Cost-reduction roadmap (post-revenue, in order of $ impact)

1. **Batch GPU whisper on Modal** (T4 spot, batch 4 VODs): transcription+
   compute path drops toward ~$0.15/VOD. Biggest single lever. NEVER attach
   GPU to a schedule (the $25/day T4 incident) — spawn-on-demand only.
2. Chunk-parallel CPU renders already amortize; keep renders on the same
   worker invocation as scoring to avoid double container spin-up.
3. Cache aggressively per VOD (already done: transcript/loudness/crowd/cam
   identity) — re-runs are nearly free; "Run again" in dashboard costs ~$0.05.

## 7. 30-day plan (business side)

- Week 1: this plan reviewed; Stripe products + webhook spec handed to CTO;
  legal pages drafted (template-based, founder reviews).
- Week 2: landing conversion pass live; waitlist → trial email sequence (3
  emails); founder's channel posts daily as the demo feed.
- Week 3: 5 concierge onboards from waitlist (manual, founder DMs); measure
  time-to-first-clip and clip-acceptance rate per batch.
- Week 4: pricing sanity check against usage data; decide Starter credit
  count (8 vs 10); Phase-1 go/no-go against the ≥30-waitlist gate.

**North-star metric: % of delivered clips the customer actually uploads.**
Everything else (retention, referral, price tolerance) follows from that one
number.
