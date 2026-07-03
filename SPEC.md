# V1 Build Spec

## Screens (Next.js, 6 total)

1. `/` — marketing page (reuse web/landing content) + login CTA
2. `/login` — Supabase Auth, Twitch provider only
3. `/onboarding` — pick style preset (gallery of 4), clips-per-stream (1-5), auto-clip toggle
4. `/dashboard` — clip grid: thumbnail, score badge, title, download, 👍/👎, regenerate; credits counter top-right
5. `/settings` — style editor (font/colors/positions/watermark = style profile JSON), Twitch connection state, credit top-up (Stripe Payment Link)
6. `/admin` — founder only: job queue view, all users, error log

## API surface (Next.js API routes)

- `POST /api/eventsub` — Twitch webhook (stream.offline → insert job with 2h delay)
- `POST /api/jobs` — manual "clip this VOD" (vod_url) — validates credits
- `POST /api/clips/:id/feedback` — 👍/👎
- `POST /api/clips/:id/regenerate` — re-render w/ different moment (costs 0 credits, rate-limited)
- Everything else = Supabase client direct with RLS

## Data model → `infra/schema.sql`

users / jobs / clips / credit_events. Job claim via `claim_job()` RPC
(FOR UPDATE SKIP LOCKED) so N workers never double-claim.

## Worker (this repo `worker/`)

Poll loop, cloud-agnostic (runs anywhere Python runs — laptop now, VPS/Modal later):
claim job → build per-job config (style profile + clip count) → run clipfarm
pipeline → upload MP4s to R2 → insert clips rows → mark done, burn credit.
Failure → status=failed + error text, credit refunded.

## 8-week milestones

| Wk | Ship |
|---|---|
| 1 | schema.sql live on Supabase; worker v0 runs a job end-to-end (manual insert) |
| 2 | Next.js skeleton: Twitch login, dashboard reads clips from DB |
| 3 | R2 delivery wired, downloads work, style presets (4) render correctly |
| 4 | EventSub: stream ends → job appears → clips appear. THE moment. |
| 5 | Credits ledger enforced, Stripe Payment Links, trial = 2 credits |
| 6 | Settings/style editor, regenerate, feedback buttons |
| 7 | Polish + admin page + error alerting (Discord webhook) |
| 8 | Private beta: 5-10 streamers from waitlist/Discords, founder QA every batch |

## Free-model scoring for beta

Worker default: `base_url` Groq (free tier, llama-3.3-70b) or Gemini flash free.
Benchmark vs claude-code picks on one VOD before beta. Upgrade to paid DeepSeek
(~$0.05/stream) when credits revenue exists.
