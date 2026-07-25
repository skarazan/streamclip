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
