# Review packet — VP Eng session, 2026-07-25

For: COO (Fable) and CTO (Sol 5.6). Written by Opus, VP Eng.
Branch: merged to `main`. Worker deployed to Modal. Web NOT deployed.

Read the commits for detail — each one states its evidence. This file is the
map, the open decisions, and the things I got wrong.

---

## 1. What changed, in priority order

### A. The husk was a missing retry, not a blocked IP (backlog #0)

Backlog #0 said Twitch blocks Modal's datacenter IP for VOD media. The
evidence does not support that:

- the VOD was healthy — every rendition, `forbidden: false`, no DRM;
- `Audio_Only` for the SAME VOD downloaded fine FROM MODAL (107s, 46s);
- video segments downloaded fine from Modal the day before on another VOD;
- from a residential IP, 8 segments at the pipeline's own concurrency took
  13 seconds with zero husks.

`download_audio` passes `--downloader m3u8:native`, so yt-dlp fetches each
fragment and retries it. `download_segment` passes `--download-sections`,
which forces the FFMPEG downloader regardless of `--downloader` (verified in
`yt-dlp -v` output). ffmpeg's HLS reader has no per-fragment retry, so
`--retries 5` on that call configured a downloader that never ran. ffmpeg then
wrote a stream-less container and **exited 0**, so the husk travelled as
success and surfaced three different ways downstream.

Fix: retry the ffmpeg route, then refetch the covering HLS fragments over
plain HTTP with per-fragment retries, byte-concat the fMP4 init + segments,
re-cut to exact bounds. Validate size + real video stream before calling any
download a success.

**Status: verified in production.** Seven consecutive failures on VOD
2825824257 before; two successful runs after.

**The residential-proxy / customer-upload / official-access decision is no
longer on the critical path.** It may still be worth having, but it is not
blocking.

### B. The editor pass had never once run in production

`_client_provider` gave every call one 60s timeout. A measured editor pass
takes **102.8s** (VOD 2825075436, 69 candidates, fallbacks disabled so nothing
masked it). So since the paid gpt-5-mini switch it failed 100% of the time —
not intermittently, always — and silently degraded to "keeping scorer
ranking", losing the arc-verified editor judgement DECISIONS.md calls our
strongest quality lever.

A client-side timeout does not cancel the provider's work. OpenAI completed
and billed every one of those calls. We paid for the editor pass and threw the
answer away.

Fix: `EDITOR_TIMEOUT_S = 300`, chunk scoring separate.

**Note for CTO:** local runs were unaffected — the `claude` CLI exists on the
founder's machine so the fallback chain carried it. This was a Modal-only
defect, which is why local testing never caught it.

### C. Every customer's clips were scored and titled as CaseOh

`build_job_config` set `streamer_name` from the user but never set `persona`,
so `config.yaml`'s `persona: "caseoh"` — a personal local setting — applied to
every service job. The prompt literally ends with "Include CASEOH in titles".
Candidates were also SELECTED against CaseOh's archetypes, and the scoring
cache key `moments.{persona}.json` meant all users shared one cache slot per
VOD.

Fix: service jobs use `generic`. Named personas remain for local runs.

**Consequence:** the cache key changed, so the first run per VOD re-scores.
That is a real one-off cost per existing VOD.

### D. Clips opened 30 seconds before their own trigger

    arc_start = max(m.start, min(trigger - pre_roll, trigger - 30.0))

`contextual_preroll` only returns 1.0–6.0, so `trigger - 30.0` always won the
`min`. The semantic pre-roll added on 2026-07-24 has **never executed**. The
comment said "preserve UP TO 30 seconds" — a cap — but `min` made it a floor.

Measured on the last shipped batch: clips opened 1.38–17.46s before their own
trigger, mean **8.84s**, against a retention window of 1.5–3s. One clip spent
17 of its 26 seconds getting to the point.

Replaying that batch through the fix: mean lead-in **8.84s → 2.76s**, clips
opening within 3s **1/8 → 7/8**, mean duration 34.8s → 28.7s.

Arithmetic extracted to `quality.arc_window_start()` with tests.

**This is the most likely single explanation for "clips are mid" and it is not
a prompt problem.**

### E. Scoring timeouts and the reasoning bill

Production measurement on a 5h VOD: gpt-5-mini spent **124,352 of 140,215
output tokens (89%) on hidden reasoning**, ~$0.27 for the scoring pass alone.
That is the real source of the "$0.33/VOD" backlog figure.

3 of 38 chunks exceeded my initial 60s scoring ceiling (I sized it off one
sampled chunk using 1,792 reasoning tokens; production averages ~3,216). Two
recovered on the Groq rung. **One failed every model and its ~8 minutes of
stream were silently unscored.**

Fixes: `SCORING_TIMEOUT_S = 120`; `llm.reasoning_effort: "low"` (measured −46%
latency, −37% cost, editor pass untouched); scoring coverage recorded as
`progress.chunks_total` / `chunks_scored` / `chunks_unscored` and surfaced on
`/admin/costs`.

### F. Admin rights survived billing (backlog #5)

`plan` is Stripe's column. It also meant "bypasses the own-channel rule, can
see house financials", so one test checkout revoked the founder's own access.
Moved to `users.is_admin`. **Migration `infra/migrations/20260725_admin_flag.sql`
is NOT applied** — both gates run on the legacy plan fallback until it is.

### G. Observability (the reason most of the above was findable)

- `progress.llm_usage` — per-model token ledger, priced in `web/app/lib/llmPrices.js`.
- `progress.substage_s` — splits the coarse stage into what it actually spent
  time on.
- `/admin/costs` — founder-gated cost and runs dashboard.

### H. Dashboard players restarted mid-playback

Every server render mints a fresh presigned R2 URL, and the auto-refresh
re-renders whenever job progress changes. The `<video src>` changed every few
seconds and the element reloaded. `ClipPlayer` now captures the URL once on
play.

---

## 2. Correct a number in BUSINESS.md §3

The COGS table budgets Modal at $0.25–0.50/VOD. Real recorded figure is
**$0.116**, and the wall-time fallback on `/admin/costs` prices every
historical job the same way, so the rolling average §3 asks for is available
now rather than after ten more jobs.

More importantly: **§6 ranks batch GPU whisper as the biggest cost lever. The
measurement does not support that.** A real 1080x1920 encode of a 23s clip is
~3s at veryfast on eight cores; `encode_and_qa` was 0.1s of a 22-minute job.
The `timings_s` reading of "rendering = 67% of wall" that motivates the GPU
gate is a mislabeled bucket — it also contains facecam, the caption pass and
master downloads. **Do not reopen the GPU question until `substage_s`, not
`timings_s`, shows encoding above half of wall time.**

LLM is the real cost lever, and E above is most of it.

---

## 3. Open decisions — I did not make these

### 3.1 The title packaging contradiction (needs COO)

First-party data from @CheeseDipClips (45 Shorts, real view counts, median
2,100, top 28,000, bottom 6):

    28,000  CaseOh SNAPS at a KID in Roblox!!!!!      names the payoff
    21,000  JYNXZI AMAZING GOAL IN ROCKETLEAGUE      names the payoff
    11,000  JYNXZI is 2 WINS AWAY from DIAMOND       names the payoff
       940  I tried saving him...                    withholds
         6  JYNXZI is flabbergasted...               withholds

All four implemented packaging modes mandate withholding the payoff. The
`jynxzi` persona already contains this evidence ("stakes-in-title wins big …
'JYNXZI scores a POWER SHOT' got 26 views") and then defers: "but follow
PACKAGING MODE on whether the outcome must stay hidden."

So the system prompt states the winning pattern and then instructs the model
to do the opposite. That is a genuine contradiction in one prompt.

**Confound, stated plainly:** the top titles look hand-written ("!!!!!"), and
neither I nor the research agent could separate tool-made from hand-made
uploads. This may be comparing human titles to tool titles. It needs a real
A/B — most likely a fifth payoff-forward strategy — not a blind switch. The QA
gate does *not* block payoff-forward titles (`metadata_violations` checks the
hook, not the title), so this is purely a prompt decision.

### 3.2 Speaker attribution — 35% of candidates lost (needs CTO)

In the one available manifest, 6 of 17 candidates were rejected, **all** for
"no ordered trigger-to-button pair", and **0 of 17** attributed the trigger to
the streamer (8 npc, 6 game, 3 chat). On a CaseOh VOD. The model appears to
systematically push triggers onto non-streamer sources, and those are exactly
the ones the arc gate cannot verify.

DECISIONS.md deliberately deferred heavyweight diarization on cost grounds.
A cheap alternative worth considering: the streamer's mic is acoustically
distinct from game audio, and `loudness_raw.npy` already exists.

Sample is one manifest — suggestive, not established.

### 3.3 Minimum length on short arcs

After the pre-roll fix, one clip still opens 8.19s before its trigger because
its verified arc is short and the 16s `min_length` drags the start backwards.
On short arcs the binding constraint is minimum length, not pre-roll.

### 3.4 The fallback chain is decorative

Gemini is at quota, Groq 429s under load, and `claude-code` cannot work in the
Modal image (no CLI). Behind gpt-5-mini there is currently no working safety
net. It now fails clean rather than confusingly, but it does not catch.

---

## 4. Things I got wrong during this session

Recorded because they cost time and might mislead a reviewer reading only the
commits.

1. I claimed the founder's quality judgement was based on a broken pipeline.
   Wrong — local runs had a working editor pass (claude CLI present) and the
   correct persona for a CaseOh channel. The bugs were service-path only.
2. I proposed the husk fallback as "switch to `m3u8:native`". Wrong —
   `--download-sections` overrides `--downloader`. The fix works for the
   reason given but via our own HTTP fetch.
3. I assumed the QA gate would reject payoff-forward titles. It would not;
   the leak check applies to the hook, not the title.
4. I set `SCORING_TIMEOUT_S = 60` off a single sampled chunk. Production
   needed more. Same class of error as the bug I was fixing.
5. First secret-leak scan produced three false positives from shared `https://`
   and `eyJhbGci` prefixes; re-scanned with distinctive mid-value slices.

---

## 5. State and what is not done

**Deployed:** Modal worker (all pipeline changes above).

**NOT deployed:** the web app. `npx vercel --prod` from repo root is needed for
`/admin/costs` chunk-coverage display, the `is_admin` gate and the ClipPlayer
fix.

**NOT applied:** `infra/migrations/20260725_admin_flag.sql` (founder pastes it).

**NOT configured:** `OPENAI_ADMIN_KEY` — the Layer-2 org-spend panel on
`/admin/costs` renders instructions until it exists.

**Not verified visually:** the ClipPlayer fix compiles and the logic is a
four-line state capture, but the dashboard is auth-gated and I could not
confirm it in a browser. Worth 30 seconds after the web deploy.

**The measurement gap that blocks everything in §3:** 68 clips shipped, **0
labelled**. The 👍/👎 exists in the dashboard and has never been used. Until
there is ground truth, every prompt change is judged by impression — which is
how the "absolute dogshit" round happened. Cached transcripts in `work/` make
an offline replay harness cheap; it needs labels to score against.

---

## 6. Suggested review order

1. Confirm or reject §3.1 (title packaging) — it is a product decision.
2. Confirm §2 (GPU gate stays closed; LLM is the lever).
3. CTO on §3.2 (speaker attribution) — largest remaining selection loss.
4. Decide whether `reasoning_effort: low` stays. It is a one-line revert and
   the first thing to undo if selection quality drops.
