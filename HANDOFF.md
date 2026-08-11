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

## The open risk — start here

(4) was a REGRESSION we introduced, verified by measurement: an editor session
from 2026-08-04 has a proxy/master lag of **0.00s**; the 2026-08-11 session has
**10.4s**.

Cause: the husk fix (`c30fb32`) added `_fragment_segment`, a fallback that
fetches HLS fragments directly and computes its cut offset from summed
`EXTINF` durations. Twitch playlists carry discontinuities (ads, muted spans),
so that clock drifts from real VOD time and the route can land a fragment
(~10s) from the requested start. Widening the retries (`d5279e3`) then made
that fallback succeed where it used to error out, so it started being used.

**The editor self-corrects because it has two files to compare. A normal clip
render does not.** If the fragment route is used during a regular job, the
shipped clip can be ~10s from the moment that was selected, and nothing
detects it. Not yet observed in the wild, but it is the same exposure — and it
would look exactly like "why is this clip random", which the founder has
reported before.

Fix it properly. Options, roughly in order of soundness:

- derive the cut offset from the fragments' own `baseMediaDecodeTime` rather
  than summed EXTINF;
- or verify alignment after download (fetch a couple of seconds via the
  yt-dlp route and cross-correlate) and correct;
- or refuse the fragment route for final renders and fail the job instead,
  which is worse UX but never ships a wrong clip silently.

The route already logs whenever it is used — grep worker logs for
`fragment-route download` to see how often this actually happens.

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
