# Review packet — VP Eng session, 2026-07-25

For: COO (Fable) and CTO (Sol 5.6). Written by Opus, VP Eng.
All work is on `main` and pushed. Worker and web were deployed during the
session; the final selection-quality changes (§1.I) are pushed but NOT yet
deployed — see §5.

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


### I. Selection quality — diagnosed from a founder-labelled batch

Job `5b48b4e4` (VOD 2821788113) shipped 3 clips. Founder verdict: first two
bad, third good. Those are the project's first labelled clips — 68 had shipped
before with zero labels.

    BAD   "Three pots landed on one spin"            21.3s
    BAD   "There was a button - then a key appeared" 16.0s
    GOOD  "Why the router started singing to him"    23.2s

Founder's description of the failures: "random ahh clips with nothing in it
just random gameplay, no good reaction no nothing. First one the main gameplay
part was him just gambling in a video game which wasn't even in frame." And
the criterion: **"It needs to have a story or instant funny reward led to by a
hook."**

The editor's own recorded reason for the slot-machine clip:

> "Simple, tight slot-win arc with a clear build (one-more spin) and a single,
> loud payoff in the final third. **Loudness confirms genuine hype (>=0.40).**
> Clean start on the spin call and immediate payline reaction — ideal Short."

Three defects, all now fixed:

**1. The editor selected on volume.** PROJECT.md §4 records the founder's
ruling — "have u considered the fact that game volume being high doesn't make
it viral?" — and loudness was cut 3.0x -> 0.75x IN THE SCORER. The editor
prompt still carried "Genuine screaming/meltdown is >= 0.40", written as a
veto (below it, reject scream claims) and read by the model as evidence FOR
posting. The rule is now explicitly one-directional: loudness can only reject,
never justify, and citing the number as support is banned outright.

**2. A verified arc is not a story.** The gate checks that trigger_quote and
button_quote appear IN ORDER. "Oh yeah, one more" -> "Bang! Times three! Woo!"
satisfies that completely and contains no story, no human reaction, and a
payoff that lives on a screen the viewer cannot see. Added an OFF-SCREEN
PAYOFF rejection: if understanding why the moment lands requires reading a
game-state event (payline, loot roll, score, killfeed, rank, menu), reject it
even when he reacts loudly and even when the arc verifies. The test given to
the model: with the gameplay pane blank, does the audio alone still deliver a
story or an instant laugh?

**3. The archetype filter was disconnected from the pass that ships.**
`RERANK_SCHEMA.archetype` was free text while `MOMENT_SCHEMA` constrained it to
12 values, so the editor invented labels ("jumpscare / panic") that matched
nothing. The rejections of physical_fail / destructive_rage / irl_reveal /
clutch_needs_replay existed only in `score_with_llm` and could never fire on
editor output. Enum now shared, and the editor path drops those archetypes.

Note the pattern across both investigations: `trigger_role` was `game` here,
and 0 of 17 candidates in the earlier manifest attributed the trigger to the
streamer. §3.2 remains the largest open selection issue.


### I-bis. Test result: the §1.I fixes were a REGRESSION

Controlled re-run of the same VOD (`a3ff7e36`). Scored moments came from cache
so the scorer was identical; only the editor prompt changed, which changed the
judgment cache key and forced a fresh editor call. Clean A/B on one variable.

**Outcome: worse.** Founder's verdict on the new batch: "the good clip is gone
and replaced by sm bs."

    OLD  2417.4-2438.7s  "Three pots landed on one spin"
    NEW  2417.4-2438.7s  "He asked chat for one more spin"   <- identical range

The slot-machine clip he rejected survived, retitled. The clip he liked (the
router/QR moment) was dropped. Two unrelated moments replaced it, also
unwanted.

What each fix actually did:

**Archetype enum — WORKED.** All 15 judgments used enum values; the invented
labels ("slot win reaction", "jumpscare / panic") are gone, and the new
editor-path filter dropped 2 `clutch_needs_replay` and 1 `irl_reveal` that
would previously have been shippable. Rejections went from ~0 to 6 reject /
6 bench / 3 post out of 15. Keep this — it is a real schema bug fix.

**Loudness veto — RATIONALISED AWAY.** I banned "loudness confirms" and stated
the number can only reject. The model wrote "Loudness >0.40 **supports** the
celebratory shout." 2 of 15 reasons still cite loudness.

**Off-screen payoff — ARGUED PAST.** I gave it the explicit test "with the
gameplay pane blank, does the audio alone still land?" For a slot payout the
model asserted "streamer yells a joyous line that **needs no visuals**" and
posted it.

**Unintended side effect:** constraining the archetype enum made the model
LABEL-SHOP. It classified a gambling win as `wholesome` — the nearest allowed
value that evades the filter.

**The lesson, which is worth more than the fixes working would have been:**
a prompt rule that asks the model to self-assess does not hold when the same
prompt also asks it to fill a batch. It will assert compliance. The enum
worked *because* it is a schema constraint, not a request. Selection
constraints belong in code or schema, not in prose.

Acting on that: `quality.cap_game_triggered()` now caps game-triggered picks at
half a batch, deterministically, and only when a verified non-game candidate
exists further down the bench. It does not ban game triggers — jumpscares are
legitimately game-triggered and DECISIONS.md protects them. Evidence: 9/15 and
17/17 triggers attributed to the game across two batches, all 3 POSTs in the
reviewed batch game-triggered, 2 of 3 rejected by the founder.

**This cap is UNTESTED against a real run.** It is reasoned from n=3 labels.
Given that the last three prompt-level selection changes made output worse, it
should be validated before anything further is built on it.

**Recommendation to COO/CTO: freeze selection changes until there are more
labels.** Today's selection work went 1 for 4 (enum yes; loudness, off-screen,
and net batch quality no). The binding constraint is not ideas, it is that
n=3 cannot distinguish a real improvement from variance.

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

## 4. Every mistake I made, and the rule it implies

Recorded in full at the founder's request. Several of these cost real time and
two of them put wrong data in front of him.

**1. Sized a timeout off a single sample — twice.**
Set `SCORING_TIMEOUT_S = 60` from one chunk using 1,792 reasoning tokens;
production averages ~3,216 and 3 of 38 chunks timed out. This is the same
class of bug as the 60s editor ceiling I was fixing at the time.
*Rule: size ceilings off the tail of a real distribution, never one sample.*

**2. Told the founder his quality judgement was based on a broken pipeline.**
Wrong. Local runs had a working editor pass (the `claude` CLI exists on his
machine, so the fallback carried it) and the correct persona for a CaseOh
channel. The bugs were service-path only. He corrected me and the evidence
backed him.
*Rule: check whether a defect reaches the environment being discussed before
using it to discount someone's judgement.*

**3. Proposed a fix based on a flag I had not verified.**
Recommended falling back to `--downloader m3u8:native`. `--download-sections`
forces the ffmpeg downloader and silently overrides `--downloader`. The final
fix works for the reason I gave, but via our own HTTP fetch, not that flag.
*Rule: verify the mechanism before proposing the remedy that depends on it.*

**4. Asserted a gate would block something without reading it.**
Claimed the QA gate would reject payoff-forward titles. It would not —
`metadata_violations` checks the hook for payoff leakage, not the title.
*Rule: read the function before describing what it enforces.*

**5. Wrote founder feedback onto the wrong clips.**
He said "first two are ass third is good" about job `5b48b4e4`; I labelled
job `c293fa81`. Three wrong rows in `clips.feedback`, reverted once he caught
it. On a table with 3 labels total, that is a large fraction of the ground
truth corrupted.
*Rule: confirm which artifact a verdict refers to before writing it to the
database. Ambiguous antecedent is not a licence to guess.*

**6. Diagnosed from correlation and ignored the mechanism.**
Concluded that empty on-screen hooks caused the two bad clips — 12/12 prior
clips had hook text, 2/3 in the new batch did not, and those two were the
rejected ones. Clean correlation, wrong cause. The founder's actual objection
was that the clips contained no story or reaction. I had even noted that the
editor pass runs at full reasoning and emits the hook, which should have told
me my `reasoning_effort` theory could not explain it.
*Rule: when the mechanism does not support the correlation, the correlation is
not the finding. Ask what the artifact actually contains.*

**7. Ran a secret scan whose method produced false positives.**
First client-bundle scan matched on the first 8 characters of each secret;
`https://` and `eyJhbGci` are shared prefixes, so it reported three leaks that
were not leaks. Re-scanned with distinctive mid-value slices.
*Rule: a scan that cannot distinguish a secret from a public URL is not a
security check.*

**8. Assumed the deploy mechanism instead of checking it.**
Told the founder to run `npx vercel --prod` while also implying a push would
publish. Vercel here is CLI-deployed from the local working tree with no git
integration, so pushing deploys nothing — and 13 commits sat unpushed while
the live site ran 4-hour-old code.
*Rule: verify how a project actually deploys before advising on it.*

Two meta-lessons worth keeping:

- **The bugs that mattered most were inversions and defaults, not missing
  features.** `min` where `max` was meant; a timeout ceiling below the work;
  a persona default never overridden; a schema field left free text. Each was
  silently reverting a decision already made and written down in DECISIONS.md.
- **Silent success is the recurring failure mode.** ffmpeg exiting 0 on an
  empty file, a timed-out call still being billed, a chunk lost on every model,
  an archetype filter matching nothing. Every one of these reported success or
  said nothing at all. Prefer loud failure over a clean-looking log.


---

## 5. State and what is not done

**Pushed:** everything. `main` is at parity with `origin/main`.

**Deployed during the session:** the Modal worker (husk fallback, media
precheck, editor timeout, persona, pre-roll, ledger, substage timings) and the
Vercel web app (`/admin/costs`, `is_admin` gate, ClipPlayer fix, chunk
coverage).

**NOT deployed:** the §1.I selection changes — archetype enum, the loudness
veto rewrite, and the off-screen-payoff rejection. They landed after the last
deploy. A worker redeploy is needed and must wait for an idle queue:

    ~/clipfarm/.venv/bin/modal deploy worker/modal_worker.py

**NOT applied:** `infra/migrations/20260725_admin_flag.sql` (founder pastes it
into the Supabase SQL editor). Both admin gates run on the legacy plan
fallback until then, so a Stripe checkout can still strip access.

**NOT configured:** `OPENAI_ADMIN_KEY` — the org-wide spend panel on
`/admin/costs` renders setup instructions until it exists.

**Not verified visually:** the ClipPlayer fix compiles and is a four-line state
capture, but the dashboard is auth-gated and I could not confirm it in a
browser. Worth 30 seconds: open two clips while a job runs and see if playback
holds.

**Ground truth: 3 labelled clips, up from 0.** All three are from job
`5b48b4e4` and are recorded in `clips.feedback`. That is enough to generate the
hypotheses in §3.1 and §1.I but not to test them. Cached transcripts in
`work/` make an offline replay harness cheap — it needs labels to score
against, and ~10 more would make the title question decidable instead of
arguable.

**§1.I was tested and regressed — see §1.I-bis.** The slot clip survived, the
liked clip was lost. Only the archetype enum fix earned its place. The
`cap_game_triggered` rule added afterwards is itself untested.

---

## 6. Suggested review order

1. Confirm or reject §3.1 (title packaging) — it is a product decision.
2. Confirm §2 (GPU gate stays closed; LLM is the lever).
3. CTO on §3.2 (speaker attribution) — largest remaining selection loss.
4. Decide whether `reasoning_effort: low` stays. It is a one-line revert and
   the first thing to undo if selection quality drops.
