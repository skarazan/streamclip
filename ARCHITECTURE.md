# V1 Architecture — fully automated, $0 infra until revenue

## The promise (product loop)

1. Streamer signs up → **connects Twitch** (OAuth) → optionally **connects
   YouTube** → picks settings (clips/day, length, caption style) or lets
   **style analysis** clone the look of their existing shorts automatically.
2. Streamer streams. Nothing else.
3. Stream ends → Twitch EventSub `stream.offline` webhook fires → job queued
   with delay (VOD needs time to finalize) → pipeline runs → clips + scores
   land in their dashboard a few hours after stream end → email/Discord ping.
4. Credits burn per VOD. Out of credits → prompt to upgrade/top-up.

## $0 stack (free tiers, replace parts only when revenue demands)

| Piece | Choice | Free tier reality |
|---|---|---|
| Frontend + API | Next.js on Vercel | free hobby tier, custom domain |
| Auth | Supabase Auth (has built-in **Twitch OAuth provider**) | free |
| DB (users, jobs, credits, style profiles) | Supabase Postgres | free 500MB |
| Clip storage + delivery | Cloudflare R2 | free 10GB + free egress |
| Job queue | Postgres table + `FOR UPDATE SKIP LOCKED` | free (no Redis needed at this scale) |
| **Worker** | this repo's pipeline as a polling daemon **on the founder's Mac** | $0; move to VPS/GPU at ~15 customers |
| Stream-end trigger | Twitch EventSub webhook → Vercel API route | free |
| Email notify | Resend | free 3k/mo |
| Billing (later) | Stripe | pay-per-transaction only |
| Phone verify (later) | Twilio Verify | trial credit first |

Worker-on-Mac is the trick that keeps V1 at $0: the queue is in the cloud,
the heavy compute polls from home. Customers never know. Ceiling ≈ 10-15
daily-VOD customers on one M2; that's exactly when revenue pays for a VPS.

## YouTube connect → automatic style analysis (onboarding killer feature)

Exactly the process used to clone @CheeseDipClips, automated:
1. YouTube OAuth (readonly) → list channel's recent Shorts
2. Download 2-3 via yt-dlp, extract frames
3. Vision LLM analyzes: caption font/case/color/position, hook style +
   keyword coloring, watermark, layout (split vs full)
4. Write a `style profile` JSON → renderer consumes it
5. No YouTube channel? Preset gallery + manual editor.

Style profiles are already config-driven in the renderer — this feature is
"generate the config from screenshots" and is largely prompt work.

## Data model (core tables)

users(id, twitch_id, yt_channel_id, phone_verified, plan, credits, style_profile jsonb)
jobs(id, user_id, vod_url, status queued|running|done|failed, clips jsonb, error, created_at)
clips(id, job_id, r2_key, title, hook, score, start_s, end_s, feedback int)
events(user_id, type, meta jsonb)  -- credit burns, webhooks, audit

## Build order

1. **Landing page + waitlist** (this repo `web/landing/`) — deploy to Vercel
   free. This IS the validation instrument now: drive streamers to it (Twitter/
   TikTok clips of the tool working, Discord communities, founder's channel),
   measure signups. ≥30 waitlist emails ≈ the old "5 paying yes" gate.
2. Worker daemon (`worker/`) wrapping the pipeline, polling Supabase jobs.
3. Dashboard MVP: Twitch login, VOD list, "clip this" button, clips grid.
4. EventSub automation (stream ends → auto job).
5. YouTube style analysis onboarding.
6. Stripe + credits + phone verify. Charge the waitlist.
