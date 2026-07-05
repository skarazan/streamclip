# HANDOVER — StreamClip session context (written 2026-07-05, ~04:00 local)

For the next Claude session. Read this + DECISIONS.md + ROADMAP.md (Execution
Plan v2) before doing anything. Memory file `caseoh-clips-channel.md` has the
compressed history.

## What this is

StreamClip (working name): SaaS that auto-clips Twitch streamers' VODs into
scored, captioned vertical Shorts. $14.99/mo + "gigawatt" credits (BTTF
branding — user's choice, currency = gigawatts/GW). User = solo founder,
evenings, $50/mo budget cap, NO local compute (Mac = 8GB/2.7GB-free, dev only).
This is the user's SOLE venture (ChessWager + Shopify-Xero dropped).

## State: FULLY WORKING END TO END

Twitch OAuth login → dashboard → job queue → Modal GPU worker (1-min schedule)
→ gpt-5-mini scoring → styled vertical clips → R2 → dashboard with live
progress + download. Proven on 2 streamers (CaseOh, Jynxzi — 3×10/10 clips on
a foreign 6.4h VOD in 15.4 min). ~$0/mo infra (free tiers + ~$0.05/stream
scoring from user's $10 OpenAI credit).

## Paths & repos

- `~/streamclip` — THE PRODUCT. Private repo github.com/skarazan/streamclip (gh CLI authed as skarazan).
- `~/clipfarm` — user's PERSONAL clipper (CheeseDipClips styling, claude-code scorer). DO NOT develop here.
- Python for everything: `~/clipfarm/.venv/bin/python` (shared venv, has all deps incl. modal CLI).
- Web app: `~/streamclip/web/app` (Next.js, JS not TS, Tailwind via CDN). Dev server via preview tool; launch.json lives at `~/ChessWager/.claude/launch.json` (preview tool reads cwd project = ChessWager quirk).
- Secrets: `~/streamclip/.env` (chmod 600, gitignored) — Supabase URL + service key, R2 (endpoint/key/secret/bucket), GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, TWITCH_CLIENT_ID/SECRET. Web: `web/app/.env.local` (has Supabase anon key too).
- Modal secret name: `streamclip` (update via `modal secret create streamclip K=V ... --force` — MUST include every key each time, it replaces).

## Infra

| Piece | Detail |
|---|---|
| Supabase | project dztfidwbxtfkxitndxtb; tables users/jobs/clips/credit_events (+ jobs.progress jsonb added later); claim_job() RPC (SKIP LOCKED); RLS = users see own rows. DDL changes: user must paste SQL in dashboard SQL editor (we have no DDL access). |
| Modal | app `streamclip-worker`; deploy: `cd ~/streamclip && ~/clipfarm/.venv/bin/modal deploy worker/modal_worker.py`. T4 GPU, cpu=8, timeout 7200, Period(1 min) drain schedule, volumes: streamclip-hf-cache, streamclip-work (transcript cache per VOD). Free credits ~$30/mo. |
| R2 | bucket streamclip-clips; keys `user_id/job_id/NN.mp4`; presigned URLs from dashboard. |
| Twitch app | "clipperThatnoOnehasDoneBefore", client id u7k992oxic2a40gfuahe1ag5frogwv; redirect = Supabase callback. Login verified working. |
| Users | founder: nicholas_sus_tv uid 599228e6-c961-40c0-b88d-6872c9cf02bd (999999 GW, plan=founder). test: uid 6478458b-501d-4675-912c-913845bc5cd9 (twitch_login mutated per test — currently 'jynxzi'). |

## Scorer (clipfarm/detect.py)

- Primary `gpt-5-mini` (won blind benchmark judged by claude CLI), chain:
  llama-4-scout (groq) → gemini-3.5-flash → llama-3.3-70b. Chain + per-model
  clients + per-chunk walk all implemented. PACING=0 for paid, 7s free tiers.
- Parallel scoring 6 workers (paid only). Parallel clip production (3 workers).
- Prompt hardening: ignore in-game NPC dialogue (whisper transcribes it!);
  energy floor 0.12; combined = score + 3×energy; end +3s pad; "include the
  reveal" rule for guess-moments.
- Benchmark harness: `benchmark/scorer_bench.py` (candidates need keys; judge
  = claude CLI at ~/.npm-global/bin/claude, $0 via user's subscription).

## Known issues / next fixes (user-reported, real)

1. Clips can still end early on reveal-moments (pad now 3s + prompt rule — VERIFY on next run).
2. When facecam not detected → full-frame fallback can exclude streamer entirely
   (Jynxzi Messi clip). PROPOSED FIX (not built): per-VOD cam-box cache — cam
   position is constant per stream; reuse box from segments where detected.
3. Cosmetic: source stream's own cam overlay appears in gameplay pane corner.
4. Progress card shows stale/raw detail for jobs claimed before latest deploys.
5. gemini free tier rate-limits linger ~day after abuse; groq quotas reset daily.

## Product gaps (Phase 1, ~this week)

No "Clip a VOD" button (jobs inserted via API by Claude only!). No style
presets UI. No email notify. No error→Discord alerting. Not deployed publicly.
THEN Phase 2 EventSub (auto-clip on stream end — THE differentiator; live-VOD
deferral guard already built), Phase 3 Stripe Payment Links + ToS.

## User's critical path (only they can do)

1. NAME + domain — undecided! Candidates DNS-checked available: gigaclip.gg
   (recommended), heavyclip.com, gigawatt.gg. "twitchclip.ai" VETOED (trademark).
   Appliance names explored (ClipMicrowave maybe-as-voice, CLIPWASHER vetoed
   —"washed" slang). BTTF gigawatts branding LOCKED for currency.
2. Vercel account + connect repo. 3. Legal entity. 4. Stripe.

## Competitor intel (in BUSINESS.md)

Wayin (wayin.ai) tested head-to-head on same VOD: landscape 2.5-min vocab-lesson
"clips", portrait mode flips layout mid-clip (OpusClip's same flaw), tiers gate
usage not quality. Positioning: "3 posted-ready bangers, not 100 maybes";
"layout never flips mid-clip". Screenshots saved in user's context/downloads.

## Operational gotchas (learned painfully)

- Every Bash cd resets; always `cd ~/streamclip && ...` per command.
- zsh: `echo ===`, `=word` glob-break; no `timeout` cmd on macOS.
- Sandbox classifier blocks: curl|bash installers, ~/.zshrc edits, npm -g to
  /usr/local. Workarounds: user runs it, or npm --prefix ~/.npm-global.
- Modal `app stop` needs `-y`; deploy does NOT kill in-flight runs; timeout
  emails often = zombie containers being reaped (check DB before panicking).
- yt-dlp: post_live VODs download at ~1× realtime via ffmpeg-HLS — guard defers
  them (45min, status visible to customer). Force `--downloader m3u8:native`.
  A VOD listed while streamer is LIVE shows partial duration — check live first.
- Two jobs on the SAME VOD concurrently = wasteful duplicate transcribe (atomic
  writes prevent corruption, volume race fixed via .part exclusion).
- OpenAI keys: user pasted 2 keys before funding; ALWAYS test quota not just auth.
- Web preview tool can't do OAuth flows — user tests login in real browser.
- llm_available() must stay chain-aware (checks all rungs' env keys).

## User profile / working style

Streamer-slang, terse, decisive, pushes back correctly (trust their instincts —
they were right about jynxzi "you're doing something wrong"). Caveman mode
hook is active in this project (compressed replies). They paste API keys into
chat — store in .env, remind to rotate someday, don't nag. They fund things
when shown why ($10 OpenAI after benchmark case). Kill criteria and all locked
decisions in DECISIONS.md — don't relitigate, don't expand scope beyond the
8-week plan without them asking.
