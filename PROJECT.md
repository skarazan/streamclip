# StreamClip — full project brief

Paste-ready context for Fable or a fresh AI agent. Everything here is what the
code actually does as of 2026-07-24, why it does it that way, and what is still
wrong. Where a rule looks arbitrary, the reason is given — those reasons were
paid for with bad batches, and reverting them re-creates the bug.

---

## 1. What this is

**StreamClip** — SaaS that turns a Twitch VOD into ready-to-upload vertical
Shorts (YouTube Shorts / TikTok / Reels), fully automatically.

Input: a Twitch VOD URL. Output: N ~25s 1080x1920 MP4s with burned captions, a
hook line, the streamer's facecam stacked over gameplay, plus a `.txt` per clip
holding title/description/why-it-was-picked.

- Repo: `~/streamclip` (private, github.com/skarazan/streamclip)
- Solo founder, evenings, hard budget ceiling. Pricing intent: $14.99/mo +
  metered credits.
- `~/clipfarm` is a separate PERSONAL clip channel setup. **Do not develop
  there.** It only supplies the shared virtualenv:
  `~/clipfarm/.venv/bin/python` — this is the interpreter for everything.

### The one non-negotiable product rule

**Discovery and initial shipping are automatic.** No human-in-the-loop clip
picking and no "review these 20 candidates and choose." A dashboard
candidate-picker was built once and deleted on the founder's instruction. If
a selection-quality problem seems to need human judgement, the answer is a
better automatic signal, not a candidate-review UI.

The dashboard does expose **template selection**, which is not clip picking:
customers choose how verified clips are packaged (caption preset, title
strategy, opening pattern) and can submit or re-run VOD jobs. Selection,
initial cutting, and shipping gates remain automatic. After a finished clip
exists, its owner may non-destructively adjust its timeline and export one
revision. That is a correction workflow over an already selected clip, not a
manual substitute for automatic discovery.

### Dashboard retention templates (2026-07-24)

- Title strategies: curiosity gap (default), stakes first, reaction tease,
  setup quote. Final editor prompts must withhold the button; deterministic QA
  rejects payoff-leaking hooks, overlong titles, and curiosity summaries using
  “then.”
- Opening patterns: clean, punch zoom (default), impact zoom plus a generated
  bass hit, and micro pan. They settle during the first 0.8s and do not loop.
- Dashboard settings are snapshotted into `jobs.progress` at submission.
  A mid-run settings change applies only to the next job.
- Completed job progress and each selection manifest record the exact template.
- Manual VOD submission, stage monitoring, downloads, and “Run again” are all
  dashboard actions; normal operations do not require an AI coding session.

### Target customer shapes selection

The paying customer is a **small streamer** — possibly with *zero* viewer
clips on their VODs. Any design that only works for a streamer with a large
clipping audience is a demo, not a product. See tiers below.

### Dashboard and correction editor (current checkpoint)

The dashboard is the operating surface; routine runs must not require an AI
coding session.

- Users submit or rerun a Twitch VOD, choose 1–8 clips, select caption/title/
  opening templates, and see job stages plus progressively published clips.
- Ready clips appear as soon as their individual media QA passes. Vertical
  loading cards reserve the outstanding requested count and explicitly say
  that more clips are processing.
- `DashboardAutoRefresh.jsx` polls `/api/dashboard-state` every three seconds.
  The endpoint returns a digest made from stable job/clip/revision fields;
  signed R2 URLs are excluded. The page refreshes only when that digest
  changes, so new clips and failures appear without manual browser refreshes.
- Fast failed jobs remain visible for 15 minutes with their worker error.
- `ClipTimelineEditor.jsx` opens a continuous 360×640 proxy with 30 seconds of
  source headroom on each side. The user can trim bounds, restore or resize AI
  cuts, create custom cuts, zoom 1×–8×, scrub with precise handles, and use the
  waveform beneath the picture track.
- Paused scrubbing is **Source inspect**. Starting playback is **Edit preview**
  and skips every red range. Timeline changes are recipes and never trigger a
  render. Only **Export final 1080×1920** performs the expensive encode.
- `clip_source` prepares the proxy first, marks it usable, then downloads the
  master and transcribes words concurrently for the eventual final export.
- Editor playback uses `/api/edit-jobs/[id]/media`, an authenticated
  same-origin R2 streaming route. It forwards byte ranges and must return
  `206 Partial Content` plus `Content-Range` for seeks. Do not diagnose a black
  infinite-buffer player as a failed encode until the proxy is probed: the
  2026-07-24 incident was a valid H.264/AAC file and a broken delivery handoff.
- `clip_edit` writes an immutable revision key, runs final media/OCR QA, and
  updates the clip row only after validation. A revision must remain visible
  on the dashboard after export.

Interactive editor jobs are prioritized at the next queue claim, but never
preempt a running full VOD and never create another worker. For an existing
Supabase deployment, apply
`infra/migrations/20260724_editor_priority.sql`.

### Sellable-service layer (2026-07-25 CTO checkpoint)

- `CONTRACT.md` defines the DB/R2-only web/worker boundary. The additive
  service migration adds heartbeat, billing idempotency, atomic credit RPCs,
  Stripe/account fields, and one-running-job-per-user queue isolation.
- Stripe Checkout, Customer Portal, signed webhooks, monthly/pack credit
  grants, and the customer ledger UI are implemented but inert without
  explicit price IDs and secrets.
- Twitch EventSub `stream.offline` can enqueue an idempotent delayed root job;
  the worker resolves the archive after Twitch publishes it.
- First login routes through `/app/onboarding`; the dashboard remains available
  at both `/app` and `/dashboard`.
- Public conversion/compliance routes are part of the Next.js app: pricing,
  FAQ, demo, changelog, status, login, and legal Terms/Privacy/Cookies.
- Worker heartbeat keeps web availability independent from processing and
  makes a five-minute stale worker visible without hiding old clips.
- Account deletion is a seven-day scheduled operation; the worker deletes the
  user R2 namespace before deleting the Supabase auth user and cascading rows.
- `scripts/extract-web-repo.sh` prepares a clean local `streamclip-web` split.
  GitHub/Vercel creation, production migration, billing activation, webhook
  registration, email domain, monitoring, and legal approval remain explicit
  deployment actions—not things an agent should silently perform.

---

## 2. Run it

```bash
cd ~/streamclip
~/clipfarm/.venv/bin/python -u -m clipfarm run --clips 3 --ai-merge \
  --vod https://www.twitch.tv/videos/2825075436 >> run.log 2>&1
```

Flags: `--clips N` (count), `--ai-clips M` (A/B: force M purely-AI picks),
`--ai-merge` (crowd + AI judged head-to-head, no quotas), `--config`,
`clean` command wipes the work dir.

- Config: `config.yaml` (per-streamer: `config.jynxzi.yaml` etc.)
- Secrets: `~/streamclip/.env`, chmod 600, gitignored. **Never echo a key into
  chat, a log, or a commit.**
- Caches live in `work/<vod_id>/`: `transcript.groq-turbo.json`,
  `loudness.npy`, `loudness_raw.npy`, `chat.json`, `twitch_clips.json`,
  `cam_box.json`, `moments.<persona>.json`. With these present a rerun is
  ~4 min and costs ~nothing.
- Output: `out/<date>_<vod_id>/NN_<SOURCE>_<slug>.mp4` + `.txt`

**Verify by inspecting artifacts, never by trusting the log.** Extract frames
with ffmpeg and look at them; check durations with ffprobe. Several bugs
printed a happy log line while shipping a broken file (see §7).

---

## 3. Pipeline, stage by stage

`clipfarm/pipeline.py :: run()` orchestrates. Roughly:

1. **Resolve VOD** (`fetch.py`) — latest from the channel, or `--vod`.
2. **Audio + transcript** (`transcribe.py`) — Groq `whisper-large-v3-turbo`,
   ~200x realtime, word-level timestamps, ~$0.13 per 6h VOD. **Audio is
   deleted the moment the transcript and loudness arrays are cached** (see
   §7 disk incident). Local faster-whisper is the offline fallback.
3. **Loudness** — two arrays are cached, and both matter:
   - `loudness.npy` — speech-gated, used for energy scoring
   - `loudness_raw.npy` — pre-gate, needed for sound-aware cutting, because a
     quiet NPC line and dead air are indistinguishable after gating
4. **Chat replay** — Twitch GQL directly (the `chat-downloader` pip package
   breaks with `KeyError: 'data'`; cursor pagination hits
   `IntegrityCheckFailed`), sampled by density in parallel.
5. **Crowd ground truth** (`crowd.py`) — see §4.
6. **Moment selection** (`detect.py`) — see §4.
7. **Segment download** — only the chosen windows, via yt-dlp
   `--download-sections` with `--force-keyframes-at-cuts`.
8. **Facecam** (`facecam.py`) — see §5.
9. **Caption pass** — the whole-VOD transcript picked the moments; the words
   that get *burned on screen* come from a second, better transcription of
   just the chosen ~90s (`base.en` heard "BANG BANG" as "BANK").
10. **Arc-verified shipping gate** — see §4.
11. **Render** (`render.py`) — layered cutting, split layout, ASS captions,
    hook line, optional brand watermark. Clips render in parallel.

`compile.py` builds long-form compilations from the same moments.

---

## 4. Selection: why the crowd is the core

### The failure that caused the current design

Pure LLM humor scoring produced batches the founder called *"absolute
dogshit"* and *"useless clips."* An LLM reading a transcript cannot tell
whether something was actually funny — it can only tell whether it *reads*
funny. So judgement moved out of the model and onto evidence.

### Crowd ground truth (`crowd.py`)

Twitch Helix `/clips` for the VOD (app token). Clips carry `vod_offset`,
`view_count`, `is_featured`. Cluster clips whose offsets fall within 45s;
require ≥2 distinct clippers.

```python
strength = clippers + 2.0 * log10(1 + views) + (3.0 if featured else 0.0)
```

Distinct clippers dominate: *many people independently reaching for the clip
button* is the signal. Views are logged because one viral clip shouldn't
outweigh ten independent clippers.

**Crowd-peak invariant:** a cluster's `median_start` is where the payoff is.
Bounds may be trimmed around it — they may never exclude it. Every trimming
path in the codebase is guarded by this.

### Tiers — the small-streamer path is the product

| Tier | Condition | Behaviour |
|---|---|---|
| A | ≥8 crowd clusters | Crowd-only candidates; skip chunk scoring entirely (fast, cheap) |
| B | 1–7 clusters | Crowd anchors merged into the scored pool, flagged as crowd |
| C | 0 clusters | Pure signal stack: loudness, chat spikes, LLM scoring |

Tier C is the one that has to work for paying customers. Tier A is what makes
CaseOh-scale testing cheap.

### Scoring signals and their weights

- **Loudness weight was cut 3.0x → 0.75x.** Founder: *"have u considered the
  fact that game volume being high doesn't make it viral?"* Loud ≠ funny.
- **Chat spikes** — density-sampled, a real independent signal.
- **"clip that" callouts** — a capped hint, deliberately weak. Streamers say
  "clip that" to bookmark *bugs* for later review, not just funny moments.
  Never authoritative.

### The editor / judge pass (`detect.rerank_moments`)

An LLM acts as editor over a shortlist. Schema puts `reason` **first**, before
any score — chain-of-thought before the number, or the score is a vibe.
It also emits `archetype`, `trigger_quote`, `button_quote`, `self_contained`,
`has_button`.

The shortlist is built **round-robin over 30-minute buckets** so one loud
section can't crowd out the stream, and `clips.min_gap_minutes` (20) keeps the
batch spread across the VOD.

**Merged judge (`--ai-merge`)** — the founder's idea: after the AI picks its
own moments, have it review the crowd's picks next to its own and decide.
Crowd moments and AI moments go into ONE head-to-head rerank; AI picks within
45s of a crowd pick are deduped; no quotas. The prompt explicitly says a
non-crowd moment *should* outrank a crowd one when its arc is stronger, so the
model isn't just deferring to the tag.

**Result so far, four runs: 5-1, 5-1, 4-0, 2-1 — always crowd-favoured.** An
earlier quota-based A/B (3 crowd + 2 AI) produced 2 AI clips the founder
judged better, but that looks like the quota reserving slots, not the AI
picking better. Worth more runs before concluding.

### Arc-verified shipping gate (the strongest quality lever found)

Every user verdict correlated with one thing: whether the clip's
trigger→payoff arc is *audibly inside the clip*. Clips that verified were
"cinema"; clips that didn't were "random bs." Six for six.

**2026-07-25 counter-evidence — the gate is necessary but NOT sufficient.**
Arc verification is a check on ORDER and PRESENCE of two quotes. It does not
check that the payoff is a payoff. A slot-machine spin whose trigger was
"Oh yeah, one more" and whose button was "Bang! Times three! Woo!" verified
cleanly, scored 8, shipped, and the founder rejected it as "random gameplay,
no good reaction no nothing" — the payoff was an on-screen payline the 9:16
crop never showed. Two of three clips in that batch failed for the same
reason while passing every gate we own.

So "verified" must not be read as "good". The gate stops us shipping clips
whose story is *absent*; it cannot stop us shipping clips whose story is
*trivial*. Founder's stated bar, which nothing in the pipeline currently
encodes: **a clip needs a story, or an instant funny reward, led into by a
hook.**

So the editor must emit `trigger_quote` and `button_quote`, and before render
those are fuzzy-matched against the clip's **own** captions (≥45% token
overlap — the two transcriptions differ in wording).

- Buttons are quoted near-verbatim → checked directly.
- Triggers are paraphrased → verified structurally (real speech in the first
  half) OR by quote.
- **Scream buttons** ("AHHHHH!") can't be text-matched — whisper spells screams
  a dozen ways or drops them — so a noise button is verified **acoustically**:
  a loudness spike in the clip's back half. Without this the gate was throwing
  away exactly the jumpscare clips that carry a Short.

Ranking: verified first, then cam-present, then fits-format. All candidates are
kept (not filtered) so quotas can still be filled.

**Over-select by 4** so the gate has a real bench to drop into.

---

## 5. Delivery layer

### Cutting (layered, in this order)

1. **Silence jump-cut** (`detect.keep_intervals`) — **duration-primary**, and
   this was measured, not assumed: quiet NPC sounds and dead air have nearly
   identical loudness (mean ~0.03). Only *duration* separates them.
   - gap ≤3.5s → keep (beats, NPC lines, reaction pauses live here)
   - gap >6s → always cut, however loud (a 26s "loud" gap once survived)
   - between → keep only if raw loudness in the gap ≥0.45
2. **Smart-cut** — if still too long after silence removal, the clip is
   talking-dense; an LLM returns KEEP spans condensing it to
   trigger→reaction→payoff. Rejected automatically if the button doesn't
   survive. Sound-payoff clips never reach here, so a text-only model never
   gets to cut a gap that holds a sound.
3. **Tail trim** — a lone over-length span keeps its tail (payoff), guarded by
   the crowd peak.
4. **End on the punchline** — crowd bounds keep rolling after the payoff, so
   cut ~2s after the last word of the button line. *(Implemented; not yet
   observed firing — see §8.)*

### Facecam (`facecam.py`) — the hardest part, many failed attempts

Reaction streamers break every naive approach: the screen is full of faces
that aren't the streamer (people in watched videos, photos, the streamer's own
stream preview), and OBS scene switches move the cam around. Position priors
all failed.

**What survives:** the streamer's face is the same face all stream. YuNet
detects, SFace embeds, ~8 probes across the whole VOD vote on which identity is
the streamer (content faces can't span hours), then each segment is searched
for that identity. Identity is cached per VOD in `cam_box.json`.

Rules learned the hard way:

- **Match selection is by prominence** (similarity × √area × motion), with
  corner-distance only a tiebreak among comparably prominent matches. Ranking
  by corner-distance alone let a dim wall detection beat the real cam whenever
  the cam sat near the middle — the pane then showed an empty room.
- **The pane crops the cam exactly and blur-fills the remainder** with a
  blown-up copy of the cam. Reshaping the crop to the pane's aspect was the
  cause of every "camera is messed up": shrinking sliced the top of his head
  off, growing dragged in whatever sat beside the cam.
- **The crop is sized to sit INSIDE the overlay** (2.1x/1.9x the head box),
  not to match it. Overshoot shows a strip of gameplay and reads as broken;
  undershoot just frames him closer and still reads as a cam.
- **Snapping to the overlay's real border was tried and reverted.** Median-frame
  Sobel, then line-coherence scoring — both lost to textured video (a food
  close-up beside the cam beats a thin border on every edge score). Do not
  retry without a fundamentally different signal.
- **The gameplay pane must exclude the cam region** (padded), shrinking into
  the widest clear span if no full-width slice fits — otherwise the streamer
  renders twice, once per pane.
- **Cam wider than 62% / taller than 55% of frame → full frame.** Nothing clean
  is left to show beside it, and detection gets unreliable once his head runs
  off the frame edge.
- **A clip with no cam ranks below one with a cam** — founder's explicit rule.
  If a segment genuinely has no cam, full-frame is correct; don't force a pane.

### Captions & style

ASS subtitles, 1–2 words at a time, plain white bold, as-spoken case; a
persistent hook line upper-middle with one keyword colored. All in
`config.yaml → style`. Per-customer style profiles are a planned extraction.

---

## 6. Cost and environment constraints

- **No GPU or peak-price increase right now.** The local dashboard wakes a
  detached one-job CPU worker. Hosted Modal remains one eight-core CPU worker;
  a GPU-on-schedule mistake once idled a T4 near-24/7, so never attach a GPU to
  a schedule without an explicit cost decision and benchmark.
- Speed comes from bounded utilization: three candidate downloads, three
  caption calls, and at most two FFmpeg final renders overlap. Clips publish
  individually. Timeline cuts are folded into the final FFmpeg graph so a cut
  clip is encoded once.
- **Don't burn Opus tokens on pipeline scoring.** Model chain in `config.yaml`:
  `gemini-3.5-flash` → `gemini-3.6-flash` → Claude CLI/Groq fallbacks. Gemini
  model quotas are separate pools inside one project, so both Flash models are
  attempted before paid capacity. `gpt-5-mini` was best in a blind benchmark
  but is 429-capped on billing. The Claude CLI needs prompts on **stdin** —
  argv is too small.
- Groq free tier is limited; whisper cost is real but small. Watch the 8h-ish
  free ceiling.
- Disk: refuse to start under 1GB free; delete audio and segments as soon as
  they're consumed.

---

## 7. Mistakes already made — do not repeat

| Symptom | Root cause | Fix |
|---|---|---|
| Disk to 0 bytes | audio hoarded across VODs | delete audio right after caching transcript+loudness |
| Comp video at half speed | title cards lacked CFR/`-r 30`/timescale, concat mangled timestamps (1667s video vs 853s audio) | uniform encode params everywhere + hard A/V duration guard |
| 83s "Short" shipped | cutting branch gated on `len(ivals) > 1`, so a single-span smart-cut fell through | apply whenever spans don't cover the segment |
| Batch died mid-render | segments numbered *before* the arc gate drops clips, render indices *after* — clip 3 deleted seg_03 while clip 2 was reading it | delete the paths the clip actually used |
| Cam pane showed an empty room | match ranked by corner-distance only | prominence ranking |
| Cam zoomed into his mouth / showed food beside his face | crop reshaped to pane aspect | exact crop + blur fill, sized under |
| Jumpscare clips dropped | arc gate demanded lexical match of "AHHHHH" | acoustic verification of noise buttons |
| Cutout thrash (0.18 → 0.50 → transients) | assumed loudness separates NPC sound from dead air; it does not | duration-primary rule |
| Timeline felt rigid and slow | sliders plus a render after each adjustment | continuous low-quality proxy, editable keep recipe, one final export |
| Red cuts played instead of being skipped | paused source inspection and edit playback shared one mode | explicit Source inspect/Edit preview modes; every Play action enables cut skipping |
| Exported revision disappeared | dashboard state did not update after clip mutation | immutable revision key plus digest-based dashboard refresh |
| New clips required manual refresh | server-rendered dashboard had no external-state signal | stable `/api/dashboard-state` digest polling |
| Editor stayed black with an infinite spinner | cross-origin presigned R2 handoff stalled although the MP4 decoded | authenticated same-origin byte-range media route; preserve `206`/`Content-Range`; expose retry/error state |
| `NameError: json` / `provider` / `t_model` | refactors that broke every run | AST-audit after refactors |
| A rerun that never ran | zsh `no matches found` on a glob aborted the whole `&&` chain; durations were byte-identical to the previous batch | use `find -delete`; check artifacts, not the log |

**Render-roulette is a trap.** The editor is nondeterministic — four runs on
the identical VOD produced four different clip sets. Rerunning re-rolls the
batch instead of refining it. When a cut is approved, **pin it**
(`scratchpad/pin_pilot.py` pattern) rather than hoping it reappears.

---

## 8. What needs improving (roughly prioritized)

1. **Editor bench depth.** Gemini often keeps only 3–6 of 15 candidates, so
   after the arc gate drops 2–3 there is no bench left and weak clips ship by
   survival rather than merit. Fix the prompt or the shortlist size.
2. **The payoff/end trim isn't firing.** Implemented in `pipeline._payoff_end`
   but no clip has logged "ending on the payoff." Either the token match fails
   or the 3s threshold is never met. Founder-reported symptom is real: *"goes
   quite a bit longer than the joke."*
3. **NPC / game-dialogue clips pass the arc gate.** The transcript has no
   speaker labels, so a funny line delivered by the *game* verifies as if the
   streamer said it. Founder called such a clip "kinda mid." Needs speaker
   separation or a "was this his voice" check.
4. **Crowd-vs-AI verdict is unsettled.** Merged judge favours crowd 4/4 runs;
   the founder preferred AI picks under the older quota split. Needs a real
   comparison, ideally against retention data.
5. **Facecam edge cases.** Giant/central cams fall back to full frame, which
   can crop his face badly. A cam-aware full-frame crop side would help.
6. **Retention feedback loop.** Analytics exist per uploaded Short but nothing
   feeds back into scoring. This is the only way to escape guessing.
7. **Per-channel style profiles** — currently one `style:` block per config
   file; product needs per-customer.
8. **Measure editor streaming overhead.** Same-origin proxy delivery is the
   reliable path, but it adds an application hop and ownership lookup per
   range request. Keep it for correctness; only optimize after measuring
   production traffic, and preserve range semantics in any replacement.
9. **Modal production rollout** — queue/schema code exists, but deployment and
   cost policy still require explicit approval.

### Quality-learning foundation (2026-08-19)

The latest evidence changes the order above:

- The public CheeseDipClips snapshot now contains 66 Shorts. Across the 63
  posts at least seven days old, duration vs log-views has Spearman
  `rho=-0.227`: a weak association, not permission to penalize duration.
  Several 40–55s clips are among the winners. The reproducible snapshot and
  caveats live in `research/2026-08-19-shorts-outcome-audit.md`.
- Final crop planning now probes motion only around the verified
  trigger-to-button passage, calculates the exact gameplay crop used by
  ffmpeg, and records `payoff_visibility` in the manifest. A localized visual
  carrier outside that crop is rejected; an unlocalized/static carrier is
  recorded honestly as `indeterminate`, not falsely certified. Replaying all
  six existing founder labels proved this does **not** separate good moments
  from bad ones: it is a render invariant, not a selection signal. Results are
  in `research/2026-08-19-payoff-visibility-benchmark.md`.
- Completed clips retain automatic selection and now accept one-tap
  keep/discard feedback. Discards require a structured failure reason so
  `weak_moment`, `missing_context`, `cause_not_visible`, boundary, packaging,
  framing, and technical failures no longer collapse into one thumbs-down.
- The service stores selection evidence in `clips.selection_meta`. Apply
  `infra/migrations/20260819_quality_learning.sql` before deploying v12.3;
  web/worker compatibility fallbacks keep clips usable during rollout but do
  not preserve the richer label/evidence fields until the migration lands.
- The dashboard and job contract now accept 1–10 requested clips, matching the
  worker's existing 10-clip bench strategy. Shipping fewer remains valid when
  verified candidates are exhausted.
- Do not build the proposed full multimodal semantic editor yet. Opus's review
  requires at least six creators, 200 labels, a hard candidate/cost cap, and a
  predicted held-out lift before that research resumes.

---

## 9. Working agreement for whoever picks this up

- Verify visually before claiming anything works. Pull frames, watch durations.
- Report failures plainly, with the output. A run that crashed is not "mostly
  working."
- Prefer fixing the signal over adding a knob; prefer deleting a failed
  experiment over leaving it behind a flag.
- Keep the automatic-end-to-end constraint intact.
- Commit messages explain *why*, including approaches that were tried and
  reverted, so nobody re-runs a dead end.
