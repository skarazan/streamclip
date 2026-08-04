# The signal ceiling — everything we can measure, measured

2026-08-03. Written after a full day of selection work, most of which failed.
Companion to research/clip-quality-spec.md (which predicted two of the
failures) and DECISIONS.md.

## What was measured

One question: **does signal X separate moments humans actually clipped from
ordinary moments in the same stream?** Lift = mean on crowd-clipped moments
divided by mean on controls. Base rate of a crowd-top-5 moment among
candidates is ~11%, so lift is the whole story.

| Signal | Lift | Coverage | Verdict |
|---|---|---|---|
| Self-laugh (streamer laughs at own line) | 2.02x | 3% of moments | too rare to rank on |
| Visual motion, VOD A | 1.94x | all | **reversed to 0.62x on VOD B** |
| Raw loudness | 1.25x | all | best consistent signal we have |
| Vision model looking at frames ("reaction") | 1.21x | all | blind test, n=36, $0.011 |
| Vision model ("postable") | 1.18x | all | " |
| Dead air after the moment | 1.14x | all | weak |
| Voice-energy delta vs rolling baseline | 1.05x | all | **worse than the raw dB it replaces** |
| Novelty / topic swerve | 1.04x | all | nothing |
| Disbelief cluster ("no way", "did he just") | 1.02x | all | nothing |
| Escalating repetition | 0.94x | all | nothing |
| Chat spike | 0.99x | all | nothing |
| Quiet + sincere (wholesome archetype) | 0.00x | never fires on a hit | absent |
| "Clip that" callout | 0.00x | never fires at all | absent |
| LLM `funny` score (judge pass) | 1.07x | all | no signal |
| Whole LLM scoring pass, as picks | recall 0.057 | — | below random-ish |

And at the system level, recall@5 against the crowd's top five:

    production today (score_with_llm)     dev 0.057   holdout 0.067
    plain loudness peaks                      0.229           0.300
    cheap candidate pool, loudness-ranked     0.257           0.333
    pool + LLM judge ranking                  0.314           0.133  (does not transfer)

## The conclusion

**Nothing in the transcript, the audio envelope, the chat, or a vision model
separates good moments by more than ~1.25x.** That is not a tuning problem.
Fourteen signals across four modalities all land in the same narrow band, and
the two that looked strong (visual motion, the judge blend) inverted on
held-out data.

The observed product quality follows directly. Picking 5 of ~60 candidates
with a 1.2x edge over an 11% base rate yields roughly one good clip per
batch — which is exactly the founder's report of 1 in 5.

Anyone proposing a new selection signal should predict its lift first and
then measure it, because the prior established here is that it will be ~1.1x.

## What this does NOT say

- It does not say selection is hopeless. **Crowd evidence works**: on Tier-A
  VODs the founder's own verdict was "absolute cinema" for 2 of 3 clips, and
  analytics-intel.md records that "all failures were WINDOWING/format, never
  crowd selection". Where humans have already voted, we are fine.
- It does not say these signals are useless on a Tier-C VOD. Everything here
  targets "top 5 of this hour" on a mega-streamer, a needle-in-haystack task.
  "Is this worth posting at all" on a small channel is a much easier bar and
  is **untested**.
- It does not excuse delivery defects. Framing, boundaries and captions are
  separately fixable and this week fixed several.

## Where the remaining leverage actually is

1. **Crowd, wherever it exists — including tiny amounts.** maj0r's VOD had 4
   viewer clips. Four human-selected moments on that streamer's own channel
   is calibration data, and it was being discarded for failing a
   ">=2 clusters" benchmark threshold. Use every clip a channel has.

2. **Real outcome data we already own.** 45 published Shorts with view counts
   (median 2,100, top 28,000, bottom 6). Those are labels for "did this
   actually work", which is a better target than "did the crowd clip it".
   Nothing in the pipeline reads them.

3. **Stop asking the model to judge; use it where it is strong.** Spec §0
   said this a month ago: LLMs are bad humour judges (rho=0.27) and their #1
   documented failure is over-rating loud/energetic content. Measured today:
   `funny` lift 1.07x. Its real value is boundaries, titles, captions and
   archetype classification.

4. **Change what a batch is.** If the achievable hit rate is ~1 in 5, then
   shipping 3 clips and calling them finished is the wrong product shape.
   Ship 8-10 with fast review — a grid of hover-preview thumbnails and a
   one-tap keep/discard. This does not break the automatic rule: the user
   never has to FIND anything in a 5-hour VOD, which is the actual labour
   being sold. It converts a quality problem we cannot solve into a review
   problem that takes 30 seconds.

## Method notes, so this is reproducible

- Corpus: 13 cached VODs — 11 caseoh_, 2 Jynxzi. One maj0r VOD is excluded by
  the harness because it has 4 viewer clips. **Having no crowd clips is the
  definition of the paying customer**, so this corpus is structurally unable
  to represent them.
- Controls were sampled inside the same slice, at least 90s from any cluster,
  so a "negative" is genuinely ordinary rather than an unlabelled highlight.
- The vision probe was blind: shuffled order, filenames never shown.
- Harness, caches and probes: `scripts/selection_bench.py`,
  `scripts/tune_rank.py`, `bench/runs.jsonl`.
