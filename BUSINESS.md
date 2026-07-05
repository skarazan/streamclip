# StreamClip — Business Plan & Unit Economics

> Working name "streamclip" — rename before launch.
> Pricing/cost figures marked (~) are from Jan-2026 knowledge and must be
> re-verified against live pricing pages before any spend decision.

## Product

SaaS for Twitch streamers: connect channel → VODs auto-clipped into scored,
styled vertical shorts. Credits per subscription tier. Streamers clip their
OWN content (clean IP position — we are a tool, not a clip farm).

**Pricing:** $14.99/mo, 14-day free trial gated by phone verification.
**Margin target:** $10/customer/mo → COGS budget ≤ $3.50 after payment fees.

## Market position (verify numbers before launch)

| Competitor | Price | Notes |
|---|---|---|
| OpusClip | free tier / ~$15 / ~$29 | market leader, generic (podcasts+everything), speaker tracking, auto-post |
| Eklipse | free tier / ~$13-16 | gaming-focused, closest competitor |
| StreamLadder | ~free / ~$20 | editor-first, manual clip conversion |
| Klap, Vizard | ~$23-29 | generic video repurposing |
| **WayinVideo (wayin.ai)** | $4.99-9.58 entry, $70 PRO+ | aggressive new entrant: paste-Twitch-VOD-link -> 50-100 clips sorted by "viral potential", built-in auto-publish scheduler (TikTok/Shorts/Reels), credits system, heavy SEO content marketing. Weaknesses: paste-link manual trigger (no stream-end automation), volume-over-curation (100 maybes vs few bangers), limited editing, no channel style cloning, generic multi-vertical platform. |

**Wayin implications (Jul 2026):** (1) price pressure at the bottom — don't fight it; position against clip-slop: "3 posted-ready bangers, not 100 maybes to sort through". (2) their auto-publish scheduler is a retention lock (connected socials = churn resistance) — pull auto-post earlier on our roadmap. (3) nobody confirmed has true stream-end automation — EventSub stays our sharpest edge; ship it. (4) their existence + SEO spend = market validation. (5) **Head-to-head sample, same CaseOh VOD (Jul 4 2026):** Wayin returned a 2.5-min 720p LANDSCAPE range of the streamer googling a word, titled like a vocab lesson ("Why You Might Demur at Nighttime Adventures") — no vertical, no captions, no facecam framing; finishing is extra steps/credits. Tiers gate usage only, not quality — this IS their product output. StreamClip same stream: 17-28s styled verticals, facecam split, 9/10 comedy picks. Keep screenshots for comparison marketing. Their portrait mode (tested same day): layout FLIPS mid-clip back to letterboxed landscape with cam as corner thumbnail — same failure users complain about in OpusClip; no captions on output; generic non-gaming titles. StreamClip decides layout once per clip -> never flips. Marketing line earned: "Your face stays on screen. The layout never flips mid-clip."

**Wedge:** gaming-native (humor scoring prompted for streamer comedy, not
"engagement"), facecam auto-split matched to clip-channel meta, style cloning
of the streamer's existing brand (fonts/colors/watermark), transparent scores.
$14.99 undercuts OpusClip Pro while being more specialized.

## Unit economics @ $14.99 — MEASURED 2026-07-05 (Jynxzi 6.4h VOD, prod pipeline v7)

Fixed per customer:
- Stripe: 2.9% + $0.30 ≈ **$0.73**
- Phone verify (Twilio Verify, ~$0.05-0.08): one-time per trial, amortized ≈ **$0.10**

Variable per VOD, measured on the real Modal worker (T4 + 8cpu + 8GB ≈
~$1.03/h ≈ $0.017/min — re-verify rates on modal.com/pricing):
| Cost | Measured |
|---|---|
| Fresh 6.4h VOD end-to-end (15.4 min wall) | **$0.26** |
| gpt-5-mini scoring + editor pass | **$0.05** |
| One-time identity probes per VOD (~2 min) | $0.03 |
| R2 storage | pennies; **egress $0** (R2 = free egress; download abuse ≠ bandwidth bill) |
| Supabase / Twitch metadata | $0 (free tiers) |
| **Total per fresh VOD** | **~$0.35** (≈ $0.05/VOD-hour rule of thumb) |

**Tier math (8 credits/mo):** COGS 8 × $0.35 = $2.80 + Stripe $0.73 + verify
$0.10 = **$3.63 → margin $11.36/customer (76%)**. ✅ Break-even ~5-7 customers.
Credit packs: $4.99 / 4 GW → COGS $1.40 → 72% margin.

**Credit design is the margin lever.** Never ship "unlimited": a daily
streamer would burn ~$10-12/mo COGS. Long VODs cost 2 credits (>8h), hard
refuse >16h — compute is linear in VOD hours, flat credits would invert.

**Trial cost control:** trial = 2 VOD credits, not 14 days unlimited.
Phone verification blocks repeat-trial abuse. **Max trial-abuser burn: $0.70
per verified phone number.**

## Abuse & cost containment (added 2026-07-05)

The debt-scenario audit. Worst cases BEFORE guards: 0-credit users could
queue unlimited jobs (worker billed credits only AFTER the GPU work — fixed);
no VOD length cap (24h subathon VOD = 2-3x cost per credit — fixed);
no infra spend ceiing (fixed by dashboard caps, below).

Layered guards, outermost = absolute:
1. **Modal spending cap** (dashboard → billing): hard monthly ceiling. Even if
   every software guard fails, the bill physically cannot exceed this. USER
   ACTION REQUIRED, 2 min.
2. **OpenAI monthly budget** (platform → limits): same idea. USER ACTION.
3. **Worker credit gate** (worker.py, deployed): job refused BEFORE any
   compute when credits < needed (1 GW ≤8h, 2 GW ≤16h, refuse >16h).
   A refused job costs ~2s of CPU (~$0.001) — 10,000 spam jobs ≈ $10, and
   Modal cap bounds even that.
4. **Phone-verified trial, 2 GW** — repeat-trial abuse costs attacker a phone
   number per $0.70 of our compute.
5. **R2 free egress** — viral clip downloads cost us $0 bandwidth by
   architecture. (Do NOT migrate to S3.)
6. Same-VOD dedupe via transcript/identity caches — reruns ~half cost.
7. When the "Clip a VOD" button ships: server-side check = 1 queued job per
   user + credits > 0 at insert (RLS/API, not client).
8. Regenerate button (roadmap): first regenerate free (cached transcript
   ≈ $0.15), further ones cost 1 GW.

**The $40k-debt answer:** with caps #1-2 set, worst-case monthly damage =
Modal cap + OpenAI cap, chosen by us (e.g. $100 + $20). Everything else
degrades service, never the wallet.

## Break-even

Fixed monthly floor (infra base, queue, DB, domain): ~$30-80 until scale.
At $10 margin: **8 customers ≈ break-even. 100 customers ≈ $1k/mo profit.**

## Risks

1. **Distribution** — the actual hard problem. Mitigation: founder's own
   channel as living case study; concierge DMs before any ad spend.
2. **Twitch dependency** — yt-dlp scraping breaks/blocks at scale. Must move
   to Twitch Helix API + user OAuth (also unlocks sub-only VODs). ToS-clean
   because users authorize their own content.
3. **Pick quality vs OpusClip's trained models** — mitigate with per-channel
   prompt tuning + user feedback loop (thumbs up/down retrains the prompt).
4. **Whisper compute** — largest COGS; needs the GPU batch worker by ~50
   customers, free tiers carry us until then.

## Validation gate (do BEFORE building the web app)

Concierge test, $0 budget: DM 40 small gaming streamers + clip channels,
offer 3 free shorts from their last VOD (run through current pipeline by
hand). Ask for $15/mo commitment for daily service.
- ≥5 yes → build V1.
- 0-1 yes → pivot the offer (price, format, or audience) before writing code.
