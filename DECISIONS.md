## 2026-07-23 — Quality pipeline v11

### Crowd evidence is start evidence, not payoff truth

Twitch `vod_offset` is the published clip start. We use bounded density modes
with direct 15-second assignment, not a 45-second single-link chain.

- Benefit: unrelated jokes cannot merge transitively into multi-minute blobs.
- Cost: a diffuse event may split into two candidates; reranking can dedupe it.
- Failure contained: one creator's burst and duplicate IDs count once.

### Models propose; timestamped evidence certifies

The editor must return every candidate with trigger/button quotes, ownership,
button kind, and post/bench/reject status. A deterministic ordered matcher
rejects absent, reversed, NPC/game/video-owned, early-payoff, and long-tail
arcs both before and after jump cuts.

- Benefit: the scorer cannot certify its own hallucinated interpretation.
- Cost: transcription drift can reject a good moment.
- Mitigation: fuzzy ordered token matching, a separate acoustic scream path,
  and a deep bench. We prefer fewer clips over knowingly unverified clips.

### Archetype budgets replace one universal length target

Stingers target 12s, banter about 20s, and rage/committed bits about 25-26s,
with explicit minimum and hard maximums.

- Benefit: short jokes stop dragging and genuine arcs keep necessary setup.
- Risk: a mislabeled archetype gets the wrong budget.
- Mitigation: final arc placement/tail checks still apply regardless of label.

### Artifact QA is a shipping gate

Outputs must be 1080x1920 CFR 30fps with audio, <=100ms A/V duration mismatch,
6-40s duration, expected cut-plan length, and no persistent creator-dashboard
OCR hits. Failed artifacts are removed and replaced from the verified bench.

- Benefit: semantic quality and encoding quality are both enforceable.
- Cost: OCR adds render latency and can false-positive on gameplay text.
- Mitigation: dashboard terms must persist across at least two sampled frames.

### Deferred: heavyweight diarization

Pyannote/SpeechBrain were not installed on the 8 GB workstation: Torch/model
storage and inference cost would compete with rendering while still struggling
on mixed streamer/game audio. Explicit editor speaker roles plus deterministic
payoff-role rejection ship now. A calibrated lightweight speaker embedding
model remains an optional future corroborating signal, never the sole gate.

### 2026-07-23 correction — never optimize away the causal bridge

Trigger and button quotes are evidence endpoints, not a license to delete
everything between them. Final Shorts now keep one continuous span from
contextual pre-roll through the button. Game/NPC/video triggers receive six
seconds of pre-roll so the action that causes a reaction stays visible.

- Benefit: the viewer sees setup → action → reaction rather than two quotes
  stitched together.
- Cost: story clips can run 30-45 seconds.
- Decision: a complete 42-second story is preferable to a confusing 10-second
  fragment. Candidates over 45 seconds are replaced, not amputated.

Story score also outranks facecam availability. A bench candidate classified
as a scream over a trivial trigger cannot fill the quota, even if a model
approved it.

### Square pixels are part of the 9:16 contract

Stored dimensions alone are insufficient: source sample-aspect metadata can
make a 1080×1920 file display at the wrong shape. Rendering now forces
`setsar=1`; artifact QA requires width 1080, height 1920, SAR 1:1, and display
aspect 9:16.

### Context must be active, not merely continuous

A fixed six-second pre-roll created quiet openings, while preserving an entire
story allowed phone-reading dead zones. Contextual pre-roll is now semantic:
intent lines such as “gotta save him” get one second; outcome/callout lines
that refer to an earlier action may receive up to six. Speech buttons retain
only 0.75 seconds of tail and final verification allows at most 1.25 seconds.

Speech-free intervals are measured against source-video motion. A gap of three
seconds or more is jump-cut only when visual motion is also low, retaining
0.35 seconds on each side for breathing room. Silent but visibly active
gameplay remains continuous. The post-cut trigger/button gate runs again; if a
safe cut cannot preserve the story, the candidate is rejected. Output count is
a target, not permission to ship quota filler.

Motion alone is not relevance. Active silent gameplay is protected only when
the trigger expresses an intent/action whose outcome must be seen (“gotta save
him”, “let me try”). Once the cause has already landed—such as a chat callout
after a cheer—later speech-free gameplay can be removed even if the camera is
moving.

## 2026-07-24 — Packaging is a template; truth remains a gate

Titles are no longer plot summaries. The dashboard exposes four controlled
strategies—curiosity gap, stakes first, reaction tease, and setup quote—but all
must withhold the verified button. Titles over 72 characters, curiosity titles
that narrate “then,” and on-screen hooks that substantially repeat the payoff
are rejected.

- Benefit: the title and persistent hook create an open loop instead of telling
  viewers the whole clip before it plays.
- Risk: vague curiosity bait can overpromise.
- Containment: the title must remain grounded in the verified trigger/button
  evidence, and existing clickbait/acoustic checks still apply.

Opening effects are similarly bounded templates: clean, punch zoom, impact hit,
and micro pan. They settle in under 0.8 seconds and never loop. Impact audio is
generated locally and mixed below the source rather than relying on a licensed
sound pack.

Dashboard settings are snapshotted when a job is queued. This avoids a race
where changing a template while a job runs makes its output irreproducible.
Completed job progress and the selection manifest record the applied template.

### Gemini quota pooling

The default editor chain tries `gemini-3.5-flash`, then
`gemini-3.6-flash`, before leaving Google for Claude CLI and Groq fallbacks.
Google applies quotas per project, but limits vary by model, so this ordering
uses the second Flash model's allowance without adding another credential or
silently lowering the quality bar to a lightweight model.

### More output from one scan

The dashboard defaults to five clips and permits one through eight. The
pipeline keeps up to 24 ranked candidates because the whole-VOD transcript and
editor judgment dominate cost; captioning and locally rendering another
verified minute are marginal work.

Increasing the target never weakens the quality bar. A valid arc inside an
oversized source window is now tightened instead of rejected merely because
its button occurs early. Old caches without raw acoustic data may verify an
intelligible spoken button, but cannot certify a “scream” metadata claim.
Active game bridges before scream/visual payoffs are retained, nearby spoken
tags after screams are kept, and final cuts respect the configured 16-second
minimum.

### Proxy-first timeline editing

Timeline editing must not turn each small decision into a render job. The
editor therefore uses one continuous 360×640, 30fps, one-second-keyframe proxy
whose composition is already locked to the final 9:16 layout. The browser
interprets the keep-interval recipe during playback and seeks over removed
ranges immediately.

- Benefit: extending bounds, restoring cuts, and adding cuts feel instant.
- Tradeoff: browser seeking can show a tiny discontinuity at a jump cut and
  the draft is intentionally soft.
- Containment: preview keyframes are one second apart, exact cut timestamps
  remain in the recipe, and only the final 1080×1920 render is publishable.

Once the proxy is uploaded, high-quality source download and transcription run
concurrently in the background. A fast user can still export before this
cache finishes; the export worker falls back to downloading/transcribing
instead of failing. Proxy format versions prevent old 16:9 previews from being
silently reused after the layout contract changes.

Timeline cut blocks are editable data, not binary AI verdicts. Both boundaries
of every automatic or manual removal remain draggable, with timestamp labels,
large hit targets, and 1×–8× zoom. The editor proxy job also extracts a compact
normalized waveform so timing decisions can use audible structure without
decoding the high-quality master in the browser. Proxy-version changes force
older waveform-less drafts to regenerate once rather than degrading silently.

### Same-origin, range-aware editor playback

The proxy itself can be valid while a browser remains permanently stuck on a
black buffering frame. Direct presigned R2 URLs proved fragile for interactive
seeking in the dashboard, especially when the player immediately seeks to the
first retained interval instead of time zero.

Decision:

- `/api/edit-jobs/[id]` returns an authenticated same-origin media URL;
- `/api/edit-jobs/[id]/media` verifies job ownership and streams the R2 object;
- incoming `Range` is forwarded to R2 and `Accept-Ranges`, `Content-Range`,
  `Content-Length`, content type, ETag, and status `206` are preserved;
- the player exposes loading, stalled, media-error, and retry states.

This adds one application hop and an ownership lookup to editor preview
requests. That cost is accepted for the low-resolution editing proxy because
it removes CORS/presigned-URL/browser-policy variance and makes failures
observable. Finished downloadable clips continue using direct signed R2 URLs;
the proxy is not re-encoded to repair a delivery failure.

## 2026-07-24 — Speed means utilization, not uncapped compute

Recent full jobs spent roughly 6–15 minutes in an eight-core container, yet
candidate downloads, caption calls and final renders were serial. Renting
additional containers or a T4 would increase peak spend before fixing that
under-utilization.

Decision:

- retain one CPU-only eight-core root worker;
- overlap three downloads and three caption requests;
- run no more than two final encodes at once;
- publish each QA-passing clip progressively;
- combine timeline cuts and final rendering into one encode;
- prioritize editor jobs at the next queue claim without preemption;
- record stage timing and estimated compute cost on every completed root job.

Risks and containment:

- Twitch or provider throttling: small fixed pools and existing retry/backoff,
  never unbounded fan-out.
- Two FFmpeg jobs competing for CPU: hard cap of two; benchmark real jobs
  before changing it.
- A late candidate failure leaving fewer clips: render in waves and refill
  from the verified bench until the requested count or bench is exhausted.
- Users mistaking a partial batch for completion: ready count and vertical
  loading cards explicitly state that the other clips are still processing.
- Progressive artifacts racing database state: each clip is uploaded before
  its row is inserted, and the job records published IDs under a lock.
- Faster editor work raising peak cost: editor priority changes queue order
  only; it does not create another Modal container.

GPU acceleration remains rejected until timing data shows rendering is more
than half of wall time and an identical-output NVENC benchmark demonstrates a
large enough speedup to justify its higher hourly price.

## 2026-07-25 — Revenue controls are database transactions

Reading a credit balance in web and subtracting it after a successful worker
run permits two workers to spend the same balance. Root VOD jobs now reserve
their full cost through `reserve_job_credits` under a user-row lock before
expensive work. Failure refunds are idempotent; Stripe grants are keyed by
external event IDs; one root job runs per user.

The temporary legacy path exists only so the current single local worker keeps
running between code deployment and the additive migration. Multi-worker
production may not launch until the RPC migration is applied.

## 2026-07-25 — Web availability does not imply worker availability

The web service reads job/clip state from Supabase and never needs a live
worker to serve old artifacts. Workers publish heartbeat, state, version and
queue depth through `worker_health`; web warns after five stale minutes.
Service extraction is prepared locally, but creating a GitHub repository,
Vercel deployment, paid Stripe products, webhooks, monitoring accounts, or
live legal obligations remains an explicit founder deployment action.

## 2026-07-25 — Launch on a supported, audited web runtime

The extracted web service originally inherited Next 14 and React 18. A clean
install reported high-severity production dependency advisories, so the launch
baseline is now Next 16.2.11 and React 19.2.8. Server cookies, route params and
page search params use the asynchronous request APIs required by Next 16.

Next 16.2.11 still declares older PostCSS and Sharp ranges in its package
metadata. The lockfile therefore pins audited replacements through explicit
package overrides (`postcss@8.5.23`, `sharp@0.35.3`). Do not remove those
overrides until the framework's own dependency tree resolves to equally new or
newer releases. A production build and `npm audit` are required after every
framework or override change; never use `npm audit fix --force` blindly.

## 2026-07-25 — Stripe products are business-use SaaS

Managed Payments rejects products without one of its eligible product tax
codes. Both subscriptions and both VOD-credit packs are access to the same
hosted creator tool, so all four use Stripe's business-use SaaS code
`txcd_10103001`. Product provisioning is incomplete until the tax code is
verified alongside amount, interval and active status. Raw Stripe
configuration errors stay in server logs and are never rendered to customers.

## 2026-07-25 — A Checkout redirect is not fulfillment

Stripe can redirect a successful localhost purchase while its webhook cannot
reach the loopback server. The billing page previously claimed Stripe was
updating the ledger forever, even when the billing migration was absent.
Signed webhooks remain authoritative in production. As a recovery path, the
Checkout success URL now includes Stripe's opaque Session ID; an authenticated
endpoint retrieves it server-side, verifies the paid state and user ownership,
then applies the same idempotent subscription/invoice or credit-pack ledger
keys as the webhook. This safely converges webhook-first and redirect-first
delivery and exposes a bounded setup message when the migration is missing.

## 2026-07-25 — Admin rights are an account property, not a billing state

`plan` is billing's column: Stripe writes starter/creator on checkout and
churned on cancellation. It also carried "this account bypasses the
own-channel rule and can see house financials", so one test checkout silently
revoked the founder's bypass and 404'd them out of `/admin/costs`.

Admin status moves to `users.is_admin` (`20260725_admin_flag.sql`, additive and
idempotent). Billing never writes that column, so a subscription, a
cancellation and a refund are all survivable.

- Benefit: the two admin gates stop depending on a value another system owns.
- Cost: one more column, and two read paths that must tolerate its absence.
- Containment: both gates fall back to the legacy plan values while the
  migration is unapplied; `AdminFlagTests` pins the checkout/cancel cases.

## 2026-07-25 — Measure sub-stages before buying hardware

`timings_s` put 66.7% of wall time in `rendering`, which reads as "encoding is
the bottleneck" and satisfies the GPU gate in BUSINESS.md §6. It is the wrong
conclusion: `rendering` also covers facecam identity, the Groq caption pass,
final-quality master downloads and OCR QA, and a measured 1080x1920 encode of
a 23s clip is ~3s at veryfast on eight cores.

`progress.substage_s` now splits that bucket (`probe_download`, `facecam`,
`caption_pass`, `master_download`, `encode_and_qa`) alongside the unchanged
customer-facing `stage`. Additive key; sub-stage totals reconcile exactly with
the coarse stage totals.

- Benefit: cost and hardware decisions get attributed time instead of a label.
- Cost: one more jsonb key per progress write.
- Decision: the GPU question stays open until `substage_s` — not `timings_s` —
  shows encoding above half of wall time.

### Reasoning tokens are the LLM bill

Measured on one real 8-minute chunk (VOD 2813202773, gpt-5-mini): the default
effort spent 1792 of 1963 output tokens (91%) on hidden reasoning, billed at
the $2/M output rate. `low` cut cost 37% and latency 46%; `minimal` cut cost
41% but returned more moments at lower top scores — less selective, andeach extra
candidate costs a segment download and a render downstream.

Prompt caching needs no work: with an identical system prefix, 2560 of 2655
input tokens came back cached at the 10x discount. An earlier zero-cache
reading was an artifact of varying `reasoning_effort` between calls, which
splits the cache key.

`llm.reasoning_effort` is therefore config-gated and defaults to null (provider
default, unchanged behaviour). It applies to chunk scoring and smart-cut only;
the editor/judge pass keeps full reasoning. One chunk is not evidence about
selection quality — A/B a full Tier-C VOD against `progress.llm_usage` before
changing the default.

## 2026-07-25 — The husk was a missing retry, not a blocked IP

Seven jobs on VOD 2825824257 (maj0r, a Tier-C target customer) failed, burning
107 min of wall time, $0.78 of Modal and 41 min of paid LLM scoring. The
recorded cause was "Twitch blocks Modal's datacenter IP for VOD media". The
evidence does not support that:

- the VOD is healthy — every rendition, `forbidden: false`, no DRM;
- `Audio_Only` for the SAME VOD downloaded fine FROM MODAL (107s, 46s);
- video segments downloaded fine from Modal the day before on another VOD;
- from a residential IP, 8 segments at the pipeline's own concurrency took
  13 seconds with zero husks.

The two download paths use different downloaders. `download_audio` passes
`--downloader m3u8:native`, so yt-dlp fetches each fragment and retries it.
`download_segment` passes `--download-sections`, which forces the FFMPEG
downloader regardless of `--downloader` (verified: "Invoking ffmpeg
downloader"). ffmpeg's HLS reader has no per-fragment retry, so `--retries 5`
on that call governs a downloader that never runs, and one refused fragment is
fatal. ffmpeg then writes a stream-less container and **exits 0**, so the husk
propagated as success.

CloudFront's refusals to datacenter egress are intermittent. Retrying is the
whole fix.

Decision:

- `download_segment` retries the ffmpeg route, then falls back to fetching the
  covering HLS fragments over plain HTTP with per-fragment retries, byte-
  concatenating the fMP4 init + media segments and re-cutting to exact bounds;
- every media download is validated (size + a real video stream) before it
  counts as success — an exit code is not evidence;
- failures raise `SegmentUnavailable` and leave no file behind, instead of
  handing a husk to captions, facecam and render;
- a 6-second media precheck runs BEFORE transcription and scoring.

Risks and containment:

- The fallback re-encodes, so it is slower than a keyframe-exact section cut;
  it only runs after the fast path has already failed.
- A master download refused at final quality now drops that candidate and
  refills from the bench rather than failing a job with verified alternatives.
- The precheck costs ~2s per job and reuses the duration the worker already
  fetched, so it adds no extra `yt-dlp -J` call.

The residential-proxy / customer-upload / official-access decision stays open,
but it is no longer on the critical path.

## 2026-07-25 — The semantic pre-roll was never actually running

The 2026-07-24 decision ("Context must be active, not merely continuous")
replaced a fixed six-second pre-roll with a semantic one: intent lines get one
second, outcome/callout lines up to six. The code shipped as

    arc_start = max(m.start, min(trigger - pre_roll, trigger - 30.0))

`contextual_preroll` only ever returns 1.0-6.0, so `trigger - 30.0` always won
the `min`. Every clip opened with thirty seconds of runway and the semantic
function was dead code. The comment above it said "preserve UP TO 30 seconds" —
a cap — but `min` makes it a floor.

Measured on the 2026-07-24 batch: shipped clips opened 1.38s-17.46s before
their own trigger, mean 8.84s. Retention research puts the decision window at
1.5-3s, so the majority of these clips spent their entire hook window on
nothing. This is a more likely explanation for weak output than any prompt
weakness, and it silently reverted a decision we had already made.

The arithmetic moved into `quality.arc_window_start()` so it is testable;
`ArcWindowStartTests` pins that 30s is a cap and that every contextual_preroll
branch opens within 6s.

Replaying the same batch through the fix: mean lead-in 8.84s -> 2.76s, clips
opening within 3s 1/8 -> 7/8, mean duration 34.8s -> 28.7s.

- Benefit: the hook lands inside the window that decides retention.
- Residual: one clip still opens at 8.19s because its verified arc is short and
  the 16s minimum length drags the start backwards. Minimum length, not
  pre-roll, is the binding constraint on short arcs — treat separately.
- Containment: the crowd-peak invariant is untouched; arc_window_start still
  never starts before the editor's chosen moment window.

## 2026-07-25 — Selection constraints belong in schema or code, not in prose

The editor pass posted a slot-machine spin the founder rejected as "random
gameplay, no good reaction". Three fixes were tried and A/B'd on the same VOD
with cached scoring, so only the editor prompt varied.

The schema constraint worked. `RERANK_SCHEMA.archetype` had been free text
while `MOMENT_SCHEMA` constrained it to 12 values, so the editor invented
labels ("slot win reaction", "jumpscare / panic") that matched nothing and the
physical_fail / clutch_needs_replay rejections could never fire on the pass
that decides what ships. Sharing the enum fixed that immediately: all 15
judgments came back valid and the filter dropped three previously-shippable
candidates.

Both prose rules failed. "Loudness can only reject, never justify; never write
'loudness confirms'" produced "Loudness >0.40 **supports** the celebratory
shout." An explicit test — "with the gameplay pane blank, does the audio alone
still land?" — produced the assertion "streamer yells a joyous line that
**needs no visuals**", for a slot payout, followed by a post decision.

A prompt cannot hold a constraint while the same prompt asks the model to fill
a batch. It will assert compliance rather than reject and come up short.

Second-order effect worth remembering: constraining the enum made the model
LABEL-SHOP rather than reject. A gambling win came back as `wholesome` — the
nearest allowed value that evades the filter. Narrowing an output space
redirects behaviour; it does not by itself raise the bar.

Decision: selection constraints that must hold go in code or schema.
`quality.cap_game_triggered()` is the first — game-triggered picks capped at
half a batch, only when a verified non-game candidate exists further down the
bench, and never banning the category (jumpscares are legitimately
game-triggered).

- Benefit: the constraint cannot be argued past.
- Cost: code rules are blunt and cannot read context the model can.
- Containment: the cap defers, never rejects outright, and starves nothing —
  an all-game bench still ships. It is UNTESTED against a real run.

Standing caution: that day's selection work went 1 for 4, and the two prose
rules regressed a batch — keeping a clip the founder rejected and dropping the
one he liked. With 3 labelled clips out of 71 shipped, no selection change can
be distinguished from variance. Get labels before engineering further.

## 2026-08-03 — Selection is two jobs, and one model was doing both badly

Harness evidence, dev set of 7 VODs, crowd top-5 as the answer key:

    score_with_llm top-5 picks           recall 0.057
    its ENTIRE candidate pool (ceiling)  recall 0.286
    loudness peaks k=40 gap=30 (ceiling) recall 0.886
    loudness+chat union    (ceiling)     recall 0.829
    plain loudness top-5                 recall 0.229

Read the second line against the third. The scorer emits ~15 moments an hour
and they are usually real — measured against crowd clusters its picks land
within seconds of *a* moment humans clipped — but it systematically misses the
biggest ones, so a PERFECT re-ranking of its output still caps at 0.286. Every
score it returns is 7 or 8, which is why nothing sorts.

Decision: split generation from judgement. Cheap signals answer "where did
something happen" at ~0.89 coverage for free; the model answers "which of
these is worth posting", which is what it is good at and what the founder's
verdicts are about.

- Benefit: the ceiling rises from 0.286 to ~0.89 before any model runs.
- Cost: a judging pass over ~40-70 windows per hour of VOD.
- Contained: candidates the judge does not return are ranked last, never
  dropped, so a bad batch degrades the order instead of losing the VOD.

Deterministic ranking of the cheap pool was measured and plateaus at ~0.257
(loudness, chat-spike, rank fusion, products — none separated). That plateau
is why a judging pass exists at all: the pool contains the right moments and
only judgement lifts them.

### The judge reports facts; code decides

Same rule as the archetype enum that worked on 2026-07-25, and for the same
reason the three prose rules failed that day: the judge fills a schema
(`has_story`, `payoff_kind`, `needs_visuals`, `streamer_speaks`, `funny`) and
`rank_judged` makes the decision. A schema field cannot be rationalised
around the way "loudness may only reject" was.

### Crowd taste and founder taste disagree, and both are kept

Among candidates matching the crowd's top-5, `needs_visuals` was 36% against
17% elsewhere: the crowd LIKES on-screen moments. All six founder labels run
the other way — every rejection was a payoff on the game screen (slot spin,
wheel, loot roll), both keepers were the streamer telling a story.

So the harness is treated as measuring "did we find the moments that pop" and
the founder's labels remain the authority on which of those may ship. The
game-event cap stays a founder-taste rule in code; it is deliberately NOT
tuned away because crowd recall dislikes it.

### Silent success, again

The first judge run reported 59% of candidates judged. Not truncation —
strict json_schema responses arrive wrapped in the schema NAME
(`{"judgements": {"items": [...]}}`) while the prompt-enforced JSON fallback
returns them bare. Reading only the bare shape discarded every judgement on
~40% of batches and reported success; those candidates just ranked last.
Now unwrapped defensively and logged loudly when nothing maps.

That is the fourth defect of this exact class in two weeks (ffmpeg exiting 0
on an empty file, a timed-out call still billed, a chunk lost on every model,
now this). Standing rule: a stage that can produce nothing must say so.

### 2026-08-03 (later) — the judge did not survive the holdout

The inverted architecture was measured on the held-out set and the judging
half failed. Recorded in full because the result argues against the idea I
had just built.

    system                                   dev     holdout
    production today (score_with_llm)        0.057   0.067
    plain loudness peaks (baseline)          0.229   0.300
    candidate pool ranked by loudness        0.257   0.333
    pool + judge filter (drop "no payoff")   0.286   0.333
    pool + judge RANKING                     0.314   0.133

Ranking weights tuned on dev transferred inversely: LOUD_W=2 scored 0.343 on
dev and 0.133 on holdout. Per-feature lift against crowd top-5 membership had
already predicted it — loudness 1.30x, needs_visuals 1.36x, has_story 1.21x,
and the judge's own `funny` only 1.07x, which is no signal at all. `has_story`
as a filter scored 0.033 on holdout: worse than random.

Conclusion: the LLM judge does not improve moment selection against crowd
evidence. What DOES hold is the candidate pool and the window shape — cheap
loudness+chat peaks at a 30s gap, ranked by loudness, beat both the current
production path (by ~5x) and the loudness baseline, on both sets, with no
model in the loop.

So the shippable finding is candidate GENERATION, not judgement, and it is
free. The judge stays in the tree behind `generate.judge` because it is the
only thing that could encode taste, and crowd recall does not measure taste —
but it may not be presented as an improvement, because on the only evidence we
have it is not one.

Two process notes, both mistakes made in this session:

- A first blend measured 0.367 on what looked like the dev set. It was six
  cache files spanning dev AND holdout. Contaminated samples flatter.
- scripts/tune_rank.py read caches written before candidates carried `loud`,
  so every loudness weight scored identically and the sweep reported "no
  effect". A tuner that cannot distinguish a weight from zero is not a tuner.
