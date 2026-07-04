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

**Wayin implications (Jul 2026):** (1) price pressure at the bottom — don't fight it; position against clip-slop: "3 posted-ready bangers, not 100 maybes to sort through". (2) their auto-publish scheduler is a retention lock (connected socials = churn resistance) — pull auto-post earlier on our roadmap. (3) nobody confirmed has true stream-end automation — EventSub stays our sharpest edge; ship it. (4) their existence + SEO spend = market validation. (5) **Head-to-head sample, same CaseOh VOD (Jul 4 2026):** Wayin returned a 2.5-min 720p LANDSCAPE range of the streamer googling a word, titled like a vocab lesson ("Why You Might Demur at Nighttime Adventures") — no vertical, no captions, no facecam framing; finishing is extra steps/credits. Tiers gate usage only, not quality — this IS their product output. StreamClip same stream: 17-28s styled verticals, facecam split, 9/10 comedy picks. Keep screenshots for comparison marketing.

**Wedge:** gaming-native (humor scoring prompted for streamer comedy, not
"engagement"), facecam auto-split matched to clip-channel meta, style cloning
of the streamer's existing brand (fonts/colors/watermark), transparent scores.
$14.99 undercuts OpusClip Pro while being more specialized.

## Unit economics @ $14.99

Fixed per customer:
- Stripe: 2.9% + $0.30 ≈ **$0.73**
- Phone verify (Twilio Verify, ~$0.05-0.08): one-time per trial, amortized ≈ **$0.10**

Variable per VOD processed (the reason credits exist):
| Cost | Concierge/now | At scale |
|---|---|---|
| Transcription (8h VOD) | free-tier APIs / local | ~$0.10-0.30 self-hosted whisper GPU batch; ~$1-2 if API (avoid) |
| LLM scoring (~130k tok) | free tiers | ~$0.03-0.08 (DeepSeek/Qwen/Bedrock cheap tier) |
| Segment download + render + egress | local | ~$0.10-0.20 (CPU spot + S3 presigned) |
| **Total per VOD** | ~$0 | **~$0.25-0.60** |

**Credit design is the margin lever.** Base tier: **8 VOD credits/mo**
(≈ 2 streams/week, 3 clips each) → COGS ≈ $2-5 → margin $9.5-11.5. ✅
Unlimited daily processing would be ~$8-18 COGS and kill the target — never
ship "unlimited". Sell extra credits at $1.50/VOD (≈60-80% margin) to heavy users.

**Trial cost control:** trial = 2 VOD credits, not 14 days unlimited.
Phone verification blocks repeat-trial abuse (worth the ~20-30% signup
friction because each trial VOD costs real compute). Revisit if signups stall.

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
