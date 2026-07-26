# SPEC: Selection harness — a grading machine for clip picking

For: CTO (Sol 5.6). From: VP Eng (Opus), 2026-07-25. Concept: COO (Fable).
Budget: **$20 hard cap.** Not part of the product — a test bench.

## Why

Testing one selection idea currently costs a full run (~20 min, ~$0.50,
renders) and ends in a founder verdict over 3 clips. On 2026-07-25 four
selection changes were tried that way: one worked, three did not, and a
controlled A/B **regressed** — and none of it was knowable until the founder
watched clips. At n=3 no result is separable from variance.

The harness replaces that inner loop. Change a prompt → run script → number
moves → keep or discard. Founder taste stays the final exam; this is the
practice test.

## What it is

`scripts/selection_bench.py` — one script. No rendering, no downloads, no R2,
no database, no worker. Reads cached artifacts, calls the LLM, prints a score.

### The answer key

Viewer clips are human selection behaviour we already have. `crowd.py` fetches
them from Helix (free) and clusters them; `work/<vod>/twitch_clips.json`
caches the raw data. **10 VODs are cached today holding 4,642 viewer clips.**

Procedure per VOD:

1. Build crowd clusters with the existing `crowd.cluster_moments()` — do not
   reimplement, the clustering rules are load-bearing (DECISIONS.md 2026-07-23).
2. **Hide them from the model.** Run selection on the transcript alone, with
   the crowd path disabled, so the model is in exactly a Tier-C position.
3. Score the model's picks against the hidden clusters.

## Metrics — recall alone is not enough

Report all of these. A single number will get gamed.

- **recall@k** — of the top `k` crowd clusters, how many did the model's `k`
  picks land on. Fix `k` (default 5) or a model that returns 40 moments
  "wins" trivially.
- **precision@k** — of the model's `k` picks, how many are crowd moments.
- **strength-weighted recall** — clusters carry
  `clippers + 2·log10(1+views) + 3·featured`. Finding the strongest cluster
  must count for more than finding the weakest.
- **rank correlation** — Spearman between the model's ordering and cluster
  strength. Catches "finds them but ranks them badly".

### Hit rule (get this right or the number is noise)

DECISIONS.md 2026-07-23: *"Crowd evidence is start evidence, not payoff
truth."* `vod_offset` is where a viewer STARTED their clip, so the payoff is
usually after it.

A pick counts as a hit when the cluster's `median_start` falls inside
`[pick.start − 20s, pick.end]`. Asymmetric on purpose. Do not use symmetric
±45s — that is the clustering window, not a hit window, and it would score a
pick that ends before the payoff as a success.

### Mandatory baselines

Print these every run or the headline number is meaningless:

- **random** — k random non-overlapping windows.
- **loudness top-k** — peaks from the cached `loudness.npy`.
- **chat top-k** — density peaks from cached `chat.json`.

If the LLM cannot beat loudness top-k, the LLM is not earning its cost. That
comparison alone is worth building this.

## Budget: how $20 works

The cost driver is scoring, and it scales with transcript length. **Do not
score whole VODs.**

Per VOD, extract a **60-minute slice** containing 3–5 crowd clusters plus the
surrounding stream as distractors. The model still has to FIND them in an hour
of material it knows nothing about — the measurement survives; the token count
drops ~6x.

Measured today (real job, `reasoning_effort: low`): 46 chunks over a 5h VOD
cost **$0.156**, so ~$0.0034/chunk.

| item | math | cost |
|---|---|---|
| one-time: 20 more VODs transcribed | 20 × $0.13 Groq | $2.60 |
| dev iteration (10 VODs × 60min ≈ 8 chunks) | 80 × $0.0034 | **$0.27** |
| 25 dev iterations | | $6.80 |
| validation sweep (20 held-out VODs) | | $0.54 |
| 4 validation sweeps | | $2.20 |
| **total** | | **≈ $12** |

$20 is the cap with ~40% headroom, not a stretch. Fable's $50–70 assumed full
VODs; slicing is what closes the gap.

Further savings, already available:

- **Prompt caching.** Same transcripts every sweep. Measured 96% of input
  tokens cached on repeat calls, at a 10x discount. Warm the cache with one
  serial call before fanning out — production currently captures only 8.8%
  because six parallel workers all miss simultaneously.
- **Cache by prompt hash.** Key scorer output on
  `sha256(system_prompt + transcript_slice)`. An editor-only change must never
  re-pay for scoring — that is the difference between a $0.27 and a $0.02
  iteration.

### Guardrails

1. `--max-usd` argument, default **2.00**. The harness tracks spend live via
   `clipfarm/usage.py` + `web/app/lib/llmPrices.js` rates and **aborts
   mid-sweep** when exceeded. Not a warning — a stop.
2. Every run prints its own cost and appends to `bench/runs.jsonl` alongside
   the prompt hash and scores, so the campaign's total spend is a `sum()`.
3. Set a hard usage limit in the OpenAI dashboard (~$25). Founder action,
   two minutes, makes overspend physically impossible.
4. **Dev set for iterating, held-out set only for confirming winners.** Stops
   overfitting and stops re-spending on the big set.

## Interface

    python -m scripts.selection_bench --set dev --k 5 --max-usd 2.00
    python -m scripts.selection_bench --set holdout --k 5 --label "stakes-title-v2"

Output:

    VOD 2820731859   recall@5 3/5   precision@5 3/5   sw-recall 0.61
    ...
    DEV SET (10 VODs)
      recall@5           0.37   (baseline: loudness 0.22 · chat 0.19 · random 0.06)
      precision@5        0.41
      strength-weighted  0.44
      rank correlation   0.31
      cost               $0.27      cumulative campaign $6.80

## Known limitation — state it in every report

VODs with heavy crowd clipping belong to **big** streamers. The paying
customer is Tier C with near-zero viewer clips. So this measures "does it find
what humans found" on Tier-A material and extrapolates to Tier C.

That is the same confound as the CheeseDip channel data and it is not
resolvable with available data. It is still far better than n=3 taste. Treat a
harness win as necessary-not-sufficient: **the founder's labelled batches
remain the acceptance test.** When the harness plateaus, that is this
architecture's ceiling, and the decision becomes whether it is sellable as-is
or needs a bigger swing.

## Build order

1. Answer key + hit rule + baselines, scored against the CURRENT prompt.
   Produces the number everything else is measured against. Do this before
   changing any prompt.
2. Prompt-hash caching and the `--max-usd` abort.
3. Held-out split and `bench/runs.jsonl`.
4. Only then start the campaign.

Step 1 alone answers a question nobody can answer today: **does our LLM
selection beat picking the loudest moments?**

## Ideas queued for the harness to judge

Not to be shipped before it can score them:

- crowd few-shot examples in the scorer prompt
- speaker attribution (0/17 and 2/15 triggers attributed to the streamer
  across two batches — the largest known selection defect)
- chat-density baseline as a feature rather than a tag
- payoff-forward vs withholding titles (§3.1 of the VP Eng review)
- `reasoning_effort` low vs default, on quality rather than cost
