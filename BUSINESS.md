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

> **REALITY CHECK (2026-07-25, VP Eng).** Differentiators 2 and 3 above are
> currently ASPIRATIONAL, not demonstrated. Across every batch reviewed this
> week the founder's verdict has been "mid" or worse, and the one batch scored
> clip-by-clip came in at **1 good of 3**. The arc-verified gate passed a
> slot-machine spin as a valid story (PROJECT.md §4 counter-evidence), so
> "output doesn't feel random" is not yet true. Seven infrastructure defects
> were fixed on 2026-07-25 — a segment-download failure, an editor pass that
> had never run, a wrong persona, a 30s pre-roll bug, and more — and **none of
> them moved perceived quality.** Do not use "we win on output quality" in
> marketing copy, the landing page, or investor/waitlist material until a
> labelled batch supports it. See §4 P0-0.

**Positioning line:** "Your community already marks the funny moments.
StreamClip turns them into Shorts while you sleep."

## 2. Pricing

- **Starter — $14.99/mo**: 8 VOD credits/mo (1 credit = one full VOD scan →
  up to 5 verified shorts + metadata; dashboard allows 1–8). Extra credits
  $1.99 each or 5 for $7.99. Quality gate means count is a target, not a
  promise — sell "verified clips only", never a fixed number.
- **Creator — $29.99/mo**: 20 credits, priority queue (exists: editor-priority
  queue ordering), style profiles, timeline-editor exports beyond the included
  quota, compilation builder when it ships.
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
| LLM scoring + editor + judge (gpt-5-mini, paid) | ~$0.20–0.30 | MEASURED 2026-07-25: scoring alone $0.27 at default reasoning (89% of output tokens were hidden reasoning); `reasoning_effort: low` cuts ~37% → ~$0.17 + editor pass |
| Modal compute (CPU) | **$0.116** | MEASURED (VP Eng, real job records) — not the earlier $0.25–0.50 guess |
| Segment download bandwidth | ~$0 | ingress free |
| R2 storage + egress | ~$0.01 | egress is free on R2; clips ~100MB/batch |
| **Total** | **~$0.45–0.55** | keep **$0.70 planning figure** as buffer |

**LLM is the cost lever, not GPU.** §6's GPU-whisper ranking was based on a
mislabeled timing bucket; real encode time is ~0.1s of a 22-min job (VP Eng
review 2026-07-25 §2). The GPU question stays closed until `substage_s` shows
encoding above half of wall time.

Since v11 (2026-07-24) the worker **records stage timing and estimated compute
cost on every completed root job** — replace this table with a rolling average
of real job records as soon as ~10 production jobs exist. Note the default is
now 5 clips/scan (was 3): captions/renders are marginal per Codex's
measurement, but verify against recorded costs, and watch two new COGS lines:
timeline-editor **proxy encodes** (one per edit job) and **final revision
exports** (one full encode each — meter these if users iterate heavily).

### How many clips per VOD (decided 2026-08-03)

Measured from real job records: **the marginal cost of one more clip is
$0.011**. Transcription and scoring are per-VOD fixed costs ($0.394 combined);
a clip only adds ~84 seconds of 8-vCPU time for its segment download, caption
pass, facecam match and encode.

| clips | COGS/VOD | margin (Starter) | expected GOOD clips at the measured ~1-in-5 |
|---|---|---|---|
| 3 (old default) | $0.426 | 72% | 0.6 |
| 8 | $0.480 | 70% | 1.6 |
| **10 (recommended)** | **$0.502** | **68%** | **2.0** |
| 15 | $0.556 | 65% | 3.0 |

Going from 3 to 10 costs 7.6 cents a VOD and four points of margin, and it is
the only lever that reliably increases usable output, because
research/2026-08-03-signal-ceiling.md establishes that no available signal
separates good moments by more than ~1.25x. We cannot rank our way to a good
clip; we can afford to surface more of them.

The pipeline already selects ~12 candidates and ships 3 — we are paying to
find and verify twelve, then discarding nine.

**Conditions on shipping 10.** Volume without triage is worse than three
clips, so this is only correct alongside a fast review surface: a grid of
hover-preview thumbnails with one-tap keep/discard. That does not violate the
automatic rule — the customer still never hunts through a five-hour VOD,
which is the labour actually being sold. Wall-clock also rises (~85s per extra
clip, two encodes in parallel), so a 10-clip job runs ~20-25 min; that is
within the "clips while you sleep" promise but not within a live demo.

Pricing copy stays "verified clips only, count is a target": the quality gate
still refuses to ship unverified moments, so a quiet stream yields fewer.

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

## 4. Sellability gap diagnosis

Ordered by "blocks charging money" first:

**P0-0 — OUTPUT QUALITY. The actual blocker, added 2026-07-25.**

Every other item here is plumbing for selling a product customers want. The
evidence does not yet show they would want this one. Standing position:

- Founder verdict on every reviewed batch this week: "mid" or worse. The one
  batch labelled clip-by-clip: **1 good of 3.**
- Seven infrastructure defects fixed on 2026-07-25 (husk downloads, an editor
  pass that had never once run in production, the wrong persona on every
  customer job, a pre-roll bug that opened clips 30s before their trigger,
  silent chunk loss, scoring timeouts, admin gating). Quality did not move.
- Four selection changes attempted the same day: **1 worked** (archetype enum),
  3 did not. A controlled re-run of the other two REGRESSED — it kept the clip
  the founder rejected and dropped the one he liked.
- Root cause is not framing or plumbing. It is which moments get picked, and
  what "good" means is not encoded anywhere. Founder's bar: *a story, or an
  instant funny reward, led into by a hook.* Nothing in the pipeline tests for
  that; the arc gate only tests that two quotes appear in order.

**The measurement gap is the binding constraint.** 71 clips have shipped; 3
are labelled. At n=3 no change can be distinguished from variance, which is
exactly how the earlier "absolute dogshit" round happened. Recommended gate
before any further selection engineering: **~20 labelled clips**, then an
offline replay harness over cached transcripts (cents per run, no rendering).

Consequences for the plan: the ≥30-waitlist phase gate should not be spent
until a labelled batch clears a stated bar, and the "quality gate means count
is a target, not a promise" pricing line in §2 is currently doing real work —
keep it.

**P0 — code implemented 2026-07-25; deployment gates remain**
1. **Stripe**: Checkout for both plans and both credit packs, Customer Portal,
   signed/idempotent webhook processing, and an append-only credit ledger are
   implemented. CTO deployment gate: create the four Stripe Price objects,
   provide keys, register the webhook, and run test-mode acceptance.
2. **Credit enforcement**: the worker now atomically reserves credits through
   a row-locking RPC before compute, prevents concurrent work for one user, and
   idempotently refunds internal failures. A single-worker legacy bridge keeps
   local runs alive until the migration is applied; production may not rely on
   that bridge.
3. **Legal/trust**: ToS, Privacy, and Cookie pages plus site-wide footer links
   are implemented. COO/founder gate: counsel reviews the clearly marked launch
   drafts before paid customers are accepted.
4. **Auth/account**: explicit OAuth denial/session errors, `/login`, `/logout`,
   re-auth redirects, and seven-day deletion scheduling are implemented. The
   worker purges the user’s R2 prefix before deleting the Supabase auth user.

**P1 — code implemented; service configuration remains**
5. **Auto-trigger**: signed Twitch EventSub `stream.offline` ingestion,
   idempotent enqueueing, delayed archive lookup, and per-account subscription
   registration are implemented. Deployment needs a public callback URL and
   EventSub secret; existing users reconnect once to ensure subscriptions.
6. **Notifications**: a best-effort Resend completion email is implemented and
   never changes job success. Deployment needs the verified sending domain and
   `RESEND_API_KEY`. Discord and thumbnails remain future enhancements.
7. **Reliability visibility**: the worker heartbeat, queue depth, public
   `/status`, `/api/status`, and stale-heartbeat dashboard banner are
   implemented. Deployment needs the additive migration and an external uptime
   monitor. Sentry project creation/DSNs remain an external setup task.
8. **Onboarding**: first login now chooses templates, discovers the latest
   Twitch archive when the provider token permits, accepts a manual VOD
   fallback, and enqueues the first five-clip target without leaving the flow.

**Shipped since first draft (v11, 2026-07-24)** — no longer gaps:
- Timeline editor (proxy-first, draggable cuts, waveform, revision exports) —
  a real retention feature and a sales point: "automatic first, one-click
  fix-up when you want it." Does NOT violate the everything-automatic rule:
  selection and shipping stay automatic; editing is optional post-delivery.
- Title/opening templates with deterministic QA; settings snapshotted per job.
- Progressive publishing (clips appear as they pass QA — helps perceived
  speed and the <20-min activation target).
- Per-job compute-cost records (feeds §3 with real numbers).

**P2 — growth**
9. Landing, pricing, FAQ structured data, demo explanation cards, changelog,
   sitemap/robots, cookieless analytics hooks, and mobile conversion pass are
   implemented. Real demo media and Plausible domain configuration remain.
10. Compilation builder as a paid differentiator (exists in pipeline, not in
    product).
11. Retention feedback loop (per-clip 👍/👎 → scoring prompt) — also our moat:
    proprietary preference data. The dashboard now captures the signal; using
    it as calibrated model context remains a later pipeline experiment.
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
