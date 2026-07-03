# clipfarm

Auto-clips CaseOh Twitch VODs into captioned vertical YouTube Shorts.

Pipeline: latest VOD → audio-only download → local Whisper transcript →
Claude scores funny moments (+ audio loudness) → downloads only the winning
segments → renders 9:16 with word-highlight captions → saves MP4 + title +
description to `out/`. You review and upload.

## Run

```bash
cd ~/clipfarm
.venv/bin/python -m clipfarm run            # latest VOD
.venv/bin/python -m clipfarm run --vod URL  # specific VOD
.venv/bin/python -m clipfarm clean          # clear work/ cache
```

First full run on a long stream: expect ~30–60 min of local transcription.
Transcript is cached — reruns on the same VOD skip it.

## LLM scoring (recommended)

An LLM picks the moments and writes titles + on-screen hooks. Pick a model
in `config.yaml` → `llm.model`:

| model | key needed | cost / stream |
|---|---|---|
| `claude-opus-4-8` (default) | `ANTHROPIC_API_KEY` | ~$0.50–1, best picks |
| `claude-haiku-4-5` | `ANTHROPIC_API_KEY` | ~$0.10 |
| `gpt-5-mini`, `gpt-4o-mini` | `OPENAI_API_KEY` | a few cents |

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY=sk-...
```

No key → falls back to loudness-only picking with generic titles.

## Style

Everything visual lives in `config.yaml` → `style:` (font, size, colors,
words per line, caption position, crop side). Colors are ASS `&HAABBGGRR`.

## Notes

- Disk-safe: only audio + chosen 30–60s segments are downloaded, never the
  full video. Aborts if free disk < `safety.min_free_gb`.
- Needs `ffmpeg-full` (brew) for caption rendering — auto-detected.
- Output goes to `out/<date>_<vod-id>/NN_title.mp4` + matching `.txt` with
  title/description ready to paste into YouTube Studio.
