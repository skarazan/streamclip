# clipfarm

Auto-clips CaseOh Twitch VODs into captioned vertical YouTube Shorts.

Pipeline: latest VOD → viewer-clip start modes + transcript/chat evidence →
LLM proposes complete trigger/reaction/button arcs → deterministic timestamp
and speaker-role gates → archetype-aware cut plan → 9:16 render with captions
→ media/OCR QA → automatic refill from a ranked bench. Each batch includes a
`selection_manifest.json` explaining every accepted or rejected candidate.

## Retention editing rules

- A Short must contain an intelligible setup → cause → payoff. Loudness,
  facecam availability, and viewer-clip density nominate moments; none of them
  prove that a moment is complete.
- Speech-free gaps of three seconds or more are evaluated for story function,
  not just visual motion. Motion alone is not relevance.
- Silent gameplay stays when the trigger creates an unresolved action whose
  outcome must be seen, such as “I gotta save him.” Once the cause has already
  happened, unrelated gameplay or chat-reading time can be jump-cut even if
  pixels are moving.
- Cuts retain 0.35 seconds around speech boundaries. Speech payoffs retain at
  most 0.75 seconds of tail. The trigger and payoff are verified again on the
  post-cut timeline; failure rejects the candidate.
- Duration is evaluated on the final retained story, not the raw source
  window. Dense stories may run up to 45 seconds. Long irrelevant or silent
  gaps are removed even from otherwise short clips; useful setup and
  escalation are never cut merely to force a sub-30-second runtime.
- Output count is a target, never permission to ship incomplete or empty clips.

## Dashboard operations and templates

Routine operation is available from `/dashboard`; an AI coding session is not
required to change templates or run a VOD.

- Paste a Twitch VOD URL and press **Clip this VOD**.
- Choose 1–8 clips per run (five by default).
- Choose a caption preset independently from the retention template.
- Choose a title strategy: **Curiosity gap** (default), **Stakes first**,
  **Reaction tease**, or **Setup quote**.
- Choose an opening pattern: **Clean**, **Punch zoom** (default),
  **Impact hit**, or **Micro pan**.
- Monitor every pipeline stage, download finished clips, and run a processed
  VOD again from history.
- Open **Edit video timeline** on any finished clip to load a lightweight
  360×640 vertical proxy with 30 seconds of headroom on each side. Users can
  extend the start or end by 15 seconds, restore any AI-removed range, and
  mark or remove custom ranges. Playback applies that edit recipe immediately
  in the browser; it does not render a new file after every adjustment.
- The editor uses dedicated playback controls instead of the browser's native
  video chrome. **Preview edit** starts on the first retained frame and skips
  removed ranges; dragging the playhead or using ±5 seconds switches to
  **Source inspect**, where paused scrubbing never gets overridden by the cut
  recipe. Starting playback—from the video, Play button, or Space—always
  returns to **Edit preview** and skips every red range. The arrow keys inspect
  ±5 seconds while paused.
- Editor media is delivered through the authenticated same-origin
  `/api/edit-jobs/[id]/media` route. It forwards HTTP byte ranges from R2 and
  returns `206 Partial Content`, so browsers can seek without relying on a
  temporary cross-origin object URL. A black player with a permanent loading
  indicator is a delivery/player failure, not permission to render the proxy
  again; verify the media route, `Content-Range`, and the video element error
  state first.
- Timing uses a conventional editor timeline rather than form sliders:
  draggable purple trim handles set the clip bounds, the white playhead scrubs,
  removed ranges appear in red, and a temporary two-handle selection deletes
  a middle range. Every destructive timeline action stays reversible through
  an adjacent Restore control until final export.
- Timeline precision controls include 1×, 2×, 4×, and 8× zoom with horizontal
  navigation. Trim handles and every red cut boundary have large drag targets
  plus live timestamps; automatic cuts can be shortened or expanded at either
  edge instead of only being kept or restored. A normalized audio waveform is
  generated with the editor proxy and displayed below the picture track to
  make speech, silence, and impact beats visible.
- Boundary visuals and hit targets are deliberately separate: cut edges are
  exact 3px lines inside 32px invisible grab zones, while trim edges are 4px
  lines inside 40px zones. Zoom is exposed as explicit **Fit / 2× / 4× / 8×**
  choices and also supports Ctrl/Cmd-wheel or trackpad pinch around the
  playhead; the UI reports the visible time window at every level.
- While the proxy is already usable, the worker prepares the high-quality
  source and caption transcript in parallel. **Export final 1080×1920**
  performs the expensive encode once, after the edit is settled, without
  rerunning VOD analysis or consuming another stream credit.

Timeline edits are stored as absolute keep-interval recipes and rendered from
the cached Twitch master, never destructively from the finished MP4 or the
low-quality preview. Revision objects use immutable R2 keys; the clip row
changes only after the new artifact passes 9:16, CFR, audio-sync, duration,
decode, and dashboard-OCR checks. Automatic clips retain the 45-second
editorial ceiling, while deliberate user revisions may run up to 90 seconds.

In local development, submitting a VOD automatically wakes a one-job worker.
The dashboard server is therefore enough for normal operation; no separate
terminal command or AI session is needed. Hosted deployments continue using
the queue-backed Modal worker.

### CPU-only fast pipeline

Processing speed comes from bounded overlap, not more containers or a GPU:

- up to three candidate downloads run concurrently;
- up to three caption-grade Groq calls overlap;
- at most two FFmpeg renders share the existing eight-core worker;
- automatic jump cuts and manual editor cuts are composed into the final
  1080×1920 FFmpeg graph, so a cut clip is encoded once rather than twice;
- each clip is uploaded and inserted as soon as its own media QA passes.

The dashboard exposes ready clips immediately and renders 9:16 loading cards
for the outstanding requested count. A user may watch, download, or edit ready
clips while the same capped worker finishes the rest. Job progress stores
per-stage wall times, total processing seconds, and a list-price Modal compute
estimate so concurrency changes can be evaluated on minutes saved per dollar.
The dashboard also polls a lightweight state digest every three seconds and
refreshes its server-rendered clip batches only when jobs, revision keys, or
clip rows actually change. No manual page refresh is required. Fast failures
remain visible for 15 minutes with their worker explanation instead of
silently disappearing from the active section.

Editor source preparation remains a low-quality 360×640 proxy. Final export
uses the cached master and transcript when available and performs cuts,
captions, layout, opening effect, audio and final H.264 output in one encode.
The queue claim function prioritizes short `clip_edit` and `clip_source` jobs
ahead of the *next* full VOD without preempting a running VOD or adding worker
containers. Apply `infra/migrations/20260724_editor_priority.sql` to an existing
Supabase project when deploying this version.

The concurrency ceilings live in `config.yaml` as `download_workers`,
`caption_workers`, and `render_workers`. `render_workers` is hard-capped at two
in code even if configuration is accidentally raised.

The dashboard snapshots its complete template when the job is submitted.
Changing a setting while a job is queued or running affects only the next job.
The finished batch and `selection_manifest.json` record the caption, title,
and opening templates that actually rendered.

Titles and on-screen hooks are deliberately different. The title earns the
click by opening one honest question; the persistent hook gives the first
seconds a short unresolved promise. Neither may reveal the verified button or
summarize both cause and resolution. Curiosity titles containing a
plot-summary “then” are rejected.

Opening patterns settle within the first 0.8 seconds and never loop over the
story. The Impact template synthesizes its bass hit locally, so it introduces
no licensed sound asset.

## Output provenance

`selection_manifest.json` is the source of truth. Normal runs declare
`provenance.generation: automatic_pipeline` and contain no manual
interventions. Any clip altered after the run must be recorded under
`provenance.manual_interventions`; it cannot be presented as evidence that the
automatic editor made the same decision. A behavior is considered fixed only
after a fresh end-to-end run produces it without manual editing.

## Run

```bash
cd ~/streamclip
~/clipfarm/.venv/bin/python -m clipfarm run            # latest VOD
~/clipfarm/.venv/bin/python -m clipfarm run --vod URL  # specific VOD
~/clipfarm/.venv/bin/python -m clipfarm clean          # clear work/ cache
```

First full run on a long stream may need transcription and downloads.
Transcripts, loudness, crowd clips, and prompt-hashed editor judgments are
cached; unchanged reruns reuse them deterministically.

## LLM scoring (recommended)

An LLM picks the moments and writes titles + on-screen hooks. Pick a model
in `config.yaml` → `llm.model`:

| model | key needed | cost / stream |
|---|---|---|
| `gemini-3.5-flash` → `gemini-3.6-flash` (default chain) | `GEMINI_API_KEY` | free-tier model pools |
| `claude-opus-4-8` | `ANTHROPIC_API_KEY` | ~$0.50–1, best picks |
| `claude-haiku-4-5` | `ANTHROPIC_API_KEY` | ~$0.10 |
| `gpt-5-mini`, `gpt-4o-mini` | `OPENAI_API_KEY` | a few cents |

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY=sk-...
```

No key → falls back to loudness-only picking with generic titles.

The default chain tries Gemini 3.5 Flash first and Gemini 3.6 Flash second.
Quota or availability failures then fall through to the configured Claude and
Groq models. Gemini limits are model-specific, but Google treats them per
project rather than per API key.

## Style

Everything visual lives in `config.yaml` → `style:` (font, size, colors,
words per line, caption position, crop side). Colors are ASS `&HAABBGGRR`.

## Notes

- Disk-safe: only audio + chosen 30–60s segments are downloaded, never the
  full video. Aborts if free disk < `safety.min_free_gb`.
- Needs `ffmpeg-full` (brew) for caption rendering — auto-detected.
- Output goes to `out/<date>_<vod-id>/NN_title.mp4` + matching `.txt` and a
  batch manifest. MP4s are hard-checked for 1080x1920, square pixels,
  display aspect 9:16, CFR 30fps, audio, duration, A/V sync, and persistent
  creator-dashboard UI before shipping.

## Regression checks

```bash
~/clipfarm/.venv/bin/python -m unittest discover -s tests -v
~/clipfarm/.venv/bin/python -m compileall -q clipfarm
git diff --check
```

`tesseract` is optional but recommended; when installed, final artifact QA
also rejects creator-dashboard UI that persists across sampled frames.

## Postmortem: 2026-07-23 review batch

The review exposed four mistakes that must not recur:

1. **I treated motion as meaning.** The first clip retained about ten seconds
   of irrelevant chat/gameplay because the screen was moving. The rule now
   protects active silence only when it is a necessary visual bridge between
   an unresolved action and its outcome.
2. **I blurred manual and automatic work.** I manually recut the first rendered
   MP4, then described the result without clearly saying that the pipeline had
   not independently produced it. Manual intervention is now required to be
   explicit in the manifest, and only a clean rerun counts as automation proof.
3. **I used a weaker export path for the manual cut.** Although the file
   decoded in FFmpeg, the first replacement crashed in the review player.
   Every jump-cut export now uses CFR 30 fps, H.264 `yuv420p`, AAC 48 kHz
   stereo, a fixed video timescale, timestamps beginning at zero, and
   `faststart`, followed by a full decode/QA pass.
4. **The requested batch size could race the settings save.** Clicking through
   the count buttons quickly disabled later clicks, and submitting immediately
   could snapshot the previous database value. The picker now records the
   latest intent immediately and serializes saves; job submission also carries
   the visible count as its authoritative snapshot. When the crowd-derived
   bench cannot cover that count, the pipeline expands into cached whole-VOD
   scoring and merges those candidates under the same deterministic quality
   gates. Provider calls have bounded timeouts so an exhausted model cannot
   leave the dashboard stuck instead of advancing to its fallback.

The repaired review file demonstrates the editorial decision and playback
settings only. It does **not** prove autonomous selection; the next clean batch
must establish that.
