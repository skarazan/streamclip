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

## Variety v7 (2026-07-05, deployed — final state of the editing overhaul)

User: "perfect editing... just clips stayed about same football topic". Fixes:
editor shortlist built round-robin over 30-min buckets (one loud section can't
crowd out the stream), EDITOR prompt dedupes same-bit/topic candidates, and
select_clips enforces clips.min_gap_minutes (20, config.yaml) between picks
with graceful relaxation. Verified: picks spread 3.2h/5.8h/6.1h vs the
previous 14-minute cluster; full-frame correctly chosen for a fullscreen-cam
scene mid-batch. NOTE: verify-run titles said "Nicholas" — streamer_name came
from the founder account's twitch_login; harmless test artifact.

## Facecam v6 (2026-07-05, deployed — identity matching)

v2-v4 facecam kept picking WRONG faces on Jynxzi (react streamer): people in
watched videos, a photo of himself, his own stream preview. Position priors
all failed — OBS scene switches move the real cam. Final architecture
(clipfarm/facecam.py): YuNet detects + SFace embeds (models/sface.onnx, 38MB,
bundled); 8 probes spread across the WHOLE VOD vote on the streamer's face
identity (content faces can't span hours); each clip segment is then searched
for that identity (corner-most, smaller box on ties); no match = full frame
(correct for fullscreen-cam scenes). Identity cached per VOD ({"v":4} in
work/<vod>/cam_box.json — loaders reject v<4, old formats were poisoned).
Motion gate kills static photos. VERIFIED by frame extraction on Jynxzi:
cam pane = actually him, all 3 clips. Probe cost ~1-2 min once per VOD.
OPS: after every `modal deploy`, kill live containers (`modal container list`
/ `stop -y`) — stale pre-deploy containers claim jobs with OLD code (bit us
twice); every drain prints `drain code: <version>` to catch it.

## Curation v3.1 (2026-07-05, deployed — "pipeline v3.1-curation" in job logs)

User called the v2 clips "mid, not worth posting" — correctly. Causes + fixes:
- Chunk scorer grade-inflates (every 8-min chunk hands out 10s; 6.4h = ~48
  chunks) and can't hear delivery. Now: loudness profile is SPEECH-GATED
  (music/soundboard seconds zeroed, renormalized to speech peak — intro music
  had energy 0.91 and birthed a hallucinated 0s clip), transcript lines carry
  [SCREAM]/[loud] tags, prompt calibrates scores stream-wide.
- NEW editor rerank pass (detect.rerank_moments): top-15 shortlist re-judged
  head-to-head in ONE call with timestamped snippets + measured loudness;
  keeps only post_score>=7 (zero keeps -> ships top-1), tightens bounds
  (peak in final third — kills post-punchline rambling), rewrites titles/hooks.
  Moments with <8 words of speech in window are dropped before ranking.
- Verified on Jynxzi VOD (job 2b87df71): editor kept 9/15, shipped 3 real
  scream-peaks (energy 0.58-0.69 vs 0.14-0.31 for the mid batch).

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

1. FIXED+DEPLOYED 2026-07-05 ("pipeline v2-editing" in job logs): reveal-moment
   early cuts had a real bug — +3s pad was added, then the max_len clamp cut
   the END back off. Now: loudness-settle end extension (reaction plays out,
   +2s air, cap +6s), over-length trims the START never the end, boundaries
   snap to transcript words (no mid-word cuts). detect.select_clips takes words.
2. FIXED+DEPLOYED 2026-07-05: per-VOD cam-box cache built — pipeline downloads
   all segments first, detects facecam per segment, median box fills failures,
   persists to work/<vod>/cam_box.json on the Modal volume for reruns.
3. FIXED+DEPLOYED 2026-07-05: gameplay pane slides sideways off the source's
   own cam overlay when the centered crop would show it twice.
   → 1-3 verified end-to-end on Jynxzi VOD rerun (test-user job 9eda102f:
   3/3 split layout, word-aligned ends). User should still eyeball those 3
   clips on the dashboard for feel. NEW GOTCHA: the first drain after `modal
   deploy` can be claimed by a leftover pre-deploy container running OLD code —
   check for the pipeline version line in job logs before trusting a verify run.
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
