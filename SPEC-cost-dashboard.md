# SPEC: Founder cost & runs dashboard

For: Opus (implementing). From: COO (Fable), 2026-07-25.
Read PROJECT.md §1–3 first for repo layout; CONTRACT.md for the web/worker
boundary rules. This is a founder-only internal tool — small, ugly-is-fine,
correct numbers matter more than styling.

## Goal

One page where the founder sees, live:
1. every running job (stage, elapsed, VOD, user) and what it has cost so far;
2. recent completed/failed jobs with their final per-job cost;
3. today's / this month's spend per provider (OpenAI at minimum);
4. remaining prepaid balances where an API exposes them.

## Where it lives

Route `app/admin/costs` in the **monorepo** Next.js app
(`~/streamclip/web/app`) — that is what deploys to Vercel (root dir `web/app`;
the extracted `~/streamclip-web` repo is NOT wired to prod — keep it in sync
or ignore it, but prod = monorepo). Deploy: `npx vercel --prod` from repo
root (`.vercelignore` already handles the upload size).

Gate: server component checks the Supabase user row has
`plan in ('founder','internal')`; anyone else gets 404. Reuse the
`serverClient()` + service-key REST pattern from
`web/app/app/dashboard/page.jsx` and `app/api/jobs/route.js`.

## Keys — names only, never print values

All secrets already exist; do not create new ones, do not echo values into
code, logs, commits, or chat. Server-side only (Next server components / API
routes), never NEXT_PUBLIC.

- Local dev: `~/streamclip/.env` (gitignored). Prod: Vercel project
  `streamclip` env vars (already configured for Supabase/R2; add any missing
  one via `npx vercel env add NAME production` — the founder pastes the value
  when prompted, you never handle it).
- `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — jobs,
  users, credit_events, worker_health.
- `OPENAI_API_KEY` — per-request usage comes back on every response
  (`response.usage`); this key may NOT be able to read the org-wide Costs API
  (see below).
- `GROQ_API_KEY` — no billing API; per-request usage only.
- `GEMINI_API_KEY` — free tier, cost $0; ignore.
- Modal: no simple spend API; approximate from stage timings (below) and the
  known rate (~8 vCPU container, Modal's published per-core-second CPU price).

## Data design — two layers

### Layer 1 (the truth, requires small worker change): per-call usage ledger

The worker/pipeline already records `progress.timings_s` and an estimated
compute cost on completed jobs (v12 — inspect a completed job's `progress`
jsonb for the exact field names before assuming). Extend the LLM call sites in
`clipfarm/detect.py` (`_score_chunk_openai`, `_score_chunk_claude`, the
rerank/smart-cut paths) to accumulate `response.usage` into a per-job dict:

```
progress.llm_usage = {
  "gpt-5-mini": {"input_tokens": N, "output_tokens": N, "calls": N},
  ...per model...
}
```

Flush it into the job row whenever progress is reported (the pipeline already
PATCHes progress per stage — piggyback, don't add new write paths). Price it
in the dashboard, not the worker: keep a `lib/llmPrices.js` map
({model: {in, out} per 1M}) so price updates don't need a worker redeploy.
gpt-5-mini reasoning tokens arrive inside `usage.completion_tokens_details.
reasoning_tokens` and are billed as output — count total completion tokens.

Modal compute estimate: `sum(timings_s) × 8 cores × Modal CPU rate` — label
it "est."

### Layer 2 (org totals, no worker change): OpenAI Costs API

`GET https://api.openai.com/v1/organization/costs?start_time=...` gives
daily org spend. It requires an **Admin API key** (`OPENAI_ADMIN_KEY`), which
probably does not exist yet — implement the panel so it renders "add
OPENAI_ADMIN_KEY to enable" when the key is absent or the call 401s, and tell
the founder in the PR/summary how to mint one (platform.openai.com → org
settings → Admin keys). Do NOT block the rest of the page on it.

## Page layout (single screen)

1. **Running now** — from `jobs` where status=running joined with
   `worker_health`: VOD link, user login, stage + detail, elapsed (now −
   started_at), est cost so far (Layer 1 partial usage × prices + Modal est).
   Auto-refresh: reuse the `DashboardAutoRefresh` digest-polling pattern
   (3s), or plain `setInterval` fetch — this page is founder-only, load is
   irrelevant.
2. **Last 20 jobs** — status, duration, clips published, per-job LLM cost
   (Layer 1), est compute, total. Failed jobs show `error` inline.
3. **Provider totals** — today + month-to-date: OpenAI (Layer 2 if key,
   else sum of Layer 1), Groq (sum of Layer 1 if recorded, else "n/a"),
   Modal ("est." sum), Supabase/Vercel/R2 (static "free tier" labels for
   now).
4. **Header stat row** — spend today, spend MTD, avg cost/VOD (last 10
   done jobs), credits outstanding (sum of users.credits where plan not in
   founder/internal — that's future liability).

## Constraints

- Never put keys or raw usage responses in client components; fetch
  server-side, pass numbers only.
- Worker changes must be additive (CONTRACT.md): new keys inside `progress`
  jsonb only, no schema migration.
- Worker redeploy after the ledger change:
  `~/clipfarm/.venv/bin/modal deploy worker/modal_worker.py` — do NOT deploy
  while a job is running (check `/api/status` state=idle first); a killed
  container orphans its job for 150 min (known issue).
- Commit style: explain why, not what. Don't touch unrelated Codex WIP.

## Acceptance

- Page 404s for a non-founder account.
- With a job running: it appears with live stage + a cost figure that grows.
- A completed job's row total ≈ the OpenAI dashboard's delta for that period
  (±20% is fine — reasoning token estimates drift).
- No secret value appears in any commit, log line, or client bundle
  (grep the build output for the first 8 chars of each key to prove it).
- `npx vercel --prod` from `~/streamclip` deploys it; existing dashboard
  unaffected.
