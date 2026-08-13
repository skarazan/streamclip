# Handoff prompt — paste this into a new session

You are the engineer on **StreamClip** (`~/streamclip`), a SaaS that turns a
Twitch VOD into ready-to-upload vertical Shorts. Solo founder, evenings, tight
budget. Read `PROJECT.md`, then `DECISIONS.md`, then `research/2026-08-03-signal-ceiling.md`
before touching selection code — those files record experiments that already
failed, and repeating one costs a week.

Interpreter for everything: `~/clipfarm/.venv/bin/python`. Do not develop in
`~/clipfarm` — it only supplies the venv.

## Where things stand (2026-08-11)

Production is live and healthy: Vercel web (`streamclip-alpha.vercel.app`,
deploys from the MONOREPO, root dir `web/app`, via `npx vercel --prod`) and a
Modal worker (`~/clipfarm/.venv/bin/modal deploy worker/modal_worker.py`).
`main` is deployed. Nothing is pending.

Last session was almost entirely incident work on the clip editor. Four bugs,
all found and fixed, in the order they were masking each other:

1. Exported revisions never updated `clip_recipes` on the root job.
2. The editor actually reads the recipe off the **clip_source** job, so fixing
   (1) alone changed nothing. Both are written on export now.
3. `ClipPlayer` captured its video URL on play and never followed prop changes,
   so a new revision never appeared. It now compares the object path and
   ignores the presigned query string.
4. **The real one.** `process_clip_source` downloads the same range twice —
   proxy at `best[height<=360]`, master at `best[height<=1080]`. Twitch's
   renditions have independent segment boundaries, so the two files were
   **10.4s apart** in content while both being exactly the requested length.
   The user edited the proxy timeline; the export cut the master with those
   numbers. `render.audio_lag_seconds` now measures the offset (audio is the
   only comparable channel — the proxy is a composed 9:16 preview, the master
   is raw 16:9), `prepare_master` stores it as `master_lag_s`, and `clip_edit`
   applies it.

## The open risk — FIXED 2026-08-12, and the diagnosis above was backwards

The exposure was real: a clip can ship ~10s from the moment that was selected
with nothing detecting it. The cause named above was wrong in every part, and
the fix it recommended would have deleted the only accurate route we have.
Full record in DECISIONS.md; the short version:

- the 10.4s belongs to VOD **2842062490** (job 559b8a20), not 2837569636 —
  both code comments named a failed job from six days earlier;
- those playlists have **zero** discontinuities and their summed EXTINF equals
  Twitch's declared total exactly, so there is no clock to correct;
- they are MPEG-TS with no `#EXT-X-MAP`, so `baseMediaDecodeTime` does not
  exist and option one was unimplementable;
- the renditions have **identical** fragment boundaries, contrary to the
  comment in `render.audio_lag_seconds`;
- the misaligned file was the **yt-dlp** proxy, and the fragment route was
  exact everywhere it was measured — 40 downloads over 20 offsets at two
  renditions, of which 5 yt-dlp cuts missed by more than 0.5s.

One of those five was at **1080p**, so the master rendition is not immune and
this was never only an editor problem — a normal clip render can ship
off-target too, exactly the exposure described below.

`--download-sections` hands the playlist to ffmpeg, which decides for itself
where to start and sometimes does not trim — reproducibly, when the requested
second sits deep inside an over-length fragment.

So `download_segment` now fetches fragments first and verifies every route
against a cheap audio probe, failing the candidate rather than shipping a
moment nobody selected. The fragment route also turned out to be ~2.5x FASTER
than yt-dlp on a 40s 1080p range, so the "slower fallback" note in
DECISIONS.md was never measured either.

Grep worker logs for `backup yt-dlp route` — that path is now the exceptional
one and announces itself.

Still open, and worth a look before the next editor session:

- `master_lag_s` should read 0.00 on new clip_source jobs now. If it does not,
  the fragment route is disagreeing with the audio probe and that is a real
  finding, not noise.
- Only VOD 2842062490 misbehaved out of the three tested. Every whole-fragment
  miss asked for a second more than 10s into an over-length fragment, and
  every offset at most 9.08s in was exact — but the one 1080p miss (0.80s,
  1.27s into a normal fragment) does not fit that rule, so the mechanism is
  uncharacterised. The fix does not depend on the answer.

## Standing rules, learned the hard way

- **Verify artifacts, not logs.** Extract frames, run ffprobe, query the DB.
  Several bugs printed a healthy log while shipping a broken file.
- **Deploy the worker only when idle** — a killed container orphans its job for
  150 minutes. And note: `/api/status` has reported `idle` while a job was
  actively rendering, so check the `jobs` table directly, not the banner.
- **Never claim a bug is pre-existing without measuring.** That mistake was
  made last session and the founder was right to push back.
- Selection: nothing measurable separates good moments by more than ~1.25x
  over chance (fourteen signals, four modalities — see the signal-ceiling
  memo). Do not add another scoring signal without predicting its lift first.
  The lever that works is shipping MORE clips (marginal cost $0.011) with fast
  review, not better ranking.
- The founder's labelled clips are the only real acceptance test, and there
  are only 6. Crowd recall is a proxy measured on CaseOh/Jynxzi, who are not
  the customer.

## Useful commands

```bash
# what production is running
curl -s https://streamclip-alpha.vercel.app/api/status | python3 -m json.tool

# recent jobs incl. editor jobs (kind = clip_source | clip_edit | root)
# secrets live in ~/streamclip/.env — never echo their values
cd ~/streamclip && set -a && source .env && set +a && \
curl -s "${SUPABASE_URL}/rest/v1/jobs?select=id,status,error,created_at,progress&order=created_at.desc&limit=8" \
  -H "apikey: ${SUPABASE_SERVICE_KEY}" -H "Authorization: Bearer ${SUPABASE_SERVICE_KEY}"

# selection harness (free with --baselines-only; caches make reruns cheap)
~/clipfarm/.venv/bin/python scripts/selection_bench.py --set dev --baselines-only
```

## Ask the founder before

Spending on Modal beyond normal jobs, changing pricing or plan shape, anything
that touches Stripe live mode, or a residential-proxy/egress change for the
Twitch refusals. Legal pages are drafts, not counsel-reviewed.
