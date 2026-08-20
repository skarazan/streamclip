# Review — archetype-aware semantic selection and editing

**Reviewer:** Opus
**Date:** 2026-08-19
**Reviewing:** research/2026-08-19-archetype-aware-semantic-editor.md
**Verdict:** Do not proceed to Phases 2-4 as written. Phase 1 is the right
instinct and cannot be executed on the corpus we have. Three cheaper things
should come first, each with a number predicted in advance.

## Verdict against the proposal's own acceptance bar

The proposal asks not to be approved merely for sounding plausible. Applying
its five criteria:

| Criterion | Status |
|---|---|
| A falsifiable offline evaluation | **Partial.** `selection_bench` exists and the metric (recall@5 vs crowd top-5) is real, but the document never states what lift would falsify it. |
| A creator-diverse dataset plan | **Fails.** See finding 1. The corpus is two creators. "Creator-held-out metrics" is not currently computable. |
| A compute-bounded implementation path | **Fails.** See finding 5. The shortlist is never bounded, and at current candidate rates the multimodal pass is 3-7 hours of video per VOD. |
| Safeguards against rationalization/overfitting | **Partial.** It names the failure mode and requires timestamped evidence, but the specific recorded failure of this exact mechanism is not addressed. See finding 2. |
| A measurable improvement target | **Fails.** No predicted lift. The standing rule from the signal-ceiling memo is explicit: predict first, then measure. |

Two of five pass partially, three fail. The failures are not fatal to the
idea — they are fatal to starting at Phase 2.

## What the proposal gets right

These are worth keeping regardless of what happens to the architecture.

- **The diagnosis.** "A system that verifies words in the correct order is a
  syntax validator, not an entertainment judge" is exactly right, and it is
  the honest reading of the arc gate's history: it stopped shipping clips
  whose story was absent and never touched clips whose story was trivial.
- **Semantic contribution over waveform activity.** The duration-primary
  silence rule was adopted because loudness could not separate a quiet NPC
  line from dead air. Generalising that to "silence may contribute" is the
  same lesson one level up.
- **Duration as an output, not a target.** Correct as an engineering stance,
  though see finding 4 for where the evidence pushes back.
- **Refusing to hand-tune the value-density formula.** The document proposes
  the formula and then explicitly declines to weight it. That is the right
  call and shows the author has internalised why the prose rules failed.
- **Abstention.** Allowing fewer clips when candidates do not clear the bar is
  compatible with the automatic-shipping rule and is the honest product shape.

## Five findings that should change the plan

### 1. Phase 1 cannot be completed. The corpus is two creators.

The proposal's Phase 1 ends with "establish creator-held-out baseline
metrics". The cached corpus is 13 VODs: **11 caseoh_, 2 Jynxzi**, plus one
maj0r VOD the harness excludes because it has only 4 viewer clips. Holding out
a creator from a set of two leaves a single-creator training set.

This is worse than it looks, because having no viewer clips is the definition
of the Tier-C paying customer, so the benchmark excludes the target user *by
construction*. Every selection number we have — 0.057 production, 0.229
loudness, 0.333 pool — is a claim about two mega-streamers.

The binding constraint is therefore data acquisition, not architecture. No
amount of beat-graph design changes it. Until there are ~6-8 creators with
labels, "creator-held-out precision" is a metric we can name but not compute.

### 2. Archetypes already exist, and their recorded failure is adversarial

`detect.py` has carried a 12-value archetype enum since 2026-07-25, and three
values (`physical_fail`, `destructive_rage`, `clutch_needs_replay`) already
reject a candidate on the pass that decides what ships. The proposal's
ten-archetype table substantially re-derives it without citing it.

More importantly, DECISIONS.md records what happened when the enum was
constrained:

> Constraining the enum made the model LABEL-SHOP rather than reject. A
> gambling win came back as `wholesome` — the nearest allowed value that
> evades the filter. Narrowing an output space redirects behaviour; it does
> not by itself raise the bar.

The proposal expands this surface: ten types, plus a secondary archetype, plus
`unknown`. That is strictly more room to shop for a label that evades whatever
gate is attached, and the document proposes attaching completion criteria to
exactly those labels. The failure mode is not classifier inaccuracy, which
better prompting could fix — it is that the classifier is being asked to
produce the label that will be used against it, by the same pass that is
being asked to fill a batch.

This is the same shape as the three prose rules that failed on 2026-07-25.
A taxonomy is only safe where nothing downstream rewards a particular label.

### 3. The core mechanism has a measured prior of ~1.2x, and the proposal predicts nothing

The multimodal comprehension pass is the engine of the whole design. Related
measurements already exist:

    vision model on frames, "is this a reaction"    1.21x   (blind, n=36)
    vision model on frames, "is this postable"      1.18x
    LLM judge `funny`                               1.07x
    LLM judge ranking, dev -> holdout        0.314 -> 0.133  (inverts)

To be fair to the proposal: what was tested was a still-frame classifier
answering a one-word question, and what is proposed is 60-90s of aligned
video, audio and transcript returning a structured beat map. Those are
genuinely different, and the earlier result does not refute the newer idea.

But the standing rule exists precisely for this: *anyone proposing a new
selection signal should predict its lift first, because the prior established
here is that it will be ~1.1x*. Fourteen signals across four modalities all
landed in a narrow band, and both signals that looked strong inverted on
held-out data. The proposal must name the number it expects and the number
below which it is abandoned, before anyone builds it.

Suggested falsification: on a creator-held-out split, the multimodal pass must
beat **loudness-ranked candidate pool at 0.333 holdout recall** — not beat
production's 0.067, which is a low bar it could clear while being useless.

### 4. The only real outcome data we own points at packaging, which the proposal schedules last

45 published Shorts have view counts (median 2,100, top 28,000, bottom 6) and
nothing in the pipeline reads them. Inside that set is a near-controlled
experiment, same creator, same game, same week:

    JYNXZI AMAZING GOAL IN ROCKETLEAGUE   0:14   21,164 views
    JYNXZI scores a POWER SHOT            0:22       26 views

Roughly 800x, attributed in analytics-intel.md to title stakes and length, not
to which moment was selected. If that reading survives a proper look at all 45,
then **selection is not the dominant term in the outcome** and the proposal is
optimising the wrong stage — or at least optimising the second-most important
one first. Packaging is Phase 4 of 4 here.

This does not mean selection is fine. It means the ordering is backwards
relative to the evidence, and the cheapest way to find out is to read data we
already own.

### 5. The compute path is unbounded, and founder time is unpriced

Two resources are treated as free.

**Model compute.** The judging pass runs over ~40-70 windows per hour of VOD.
A 4-hour stream is 160-280 windows; at the proposed 60-90s each, that is
**3-7 hours of video** through a multimodal model per VOD, against a hard
budget that currently refuses a GPU and runs one 8-core CPU worker. The
proposal says "analyze only shortlisted windows" but never defines the
shortlist size. It needs a hard cap (e.g. top 20 windows) and a cost per VOD
stated in dollars before Phase 2.

**Founder attention.** Phase 1 is a pairwise labelling tool. Pairwise
preference models need hundreds of comparisons to calibrate; there are
currently 6 labels. This is a solo founder working evenings. Label throughput
is the scarcest input in the entire plan and the document does not mention it
as a cost at all.

## Answers to the ten questions

**1. Is archetype classification the right first abstraction?**
No. It is an existing abstraction whose failure is documented and adversarial
(finding 2). Keep archetypes where they already earn their place — budgets,
boundaries, captions — and stop attaching rejection gates to a label the same
model chooses.

**2. Smallest structured representation that captures contribution?**
Not a beat graph. Three fields would carry most of the value: *payoff carrier*
(speech / face / gameplay / other-person / sound), *earliest coherent start*,
*strongest valid end*. The first is a founder-taste discriminator (finding
below); the other two are boundary work, which is where the model has always
been strong. Dependencies, novelty scores and confidence per beat are a
screenplay parser and will not survive contact with held-out data.

**3. Stingers vs complete stories without favouring either?**
Do not compare them. Compare within archetype and let the batch composition
rule decide the mix — the same containment `cap_game_triggered` uses. Any
single ranking that must order a 5s reaction against a 45s story will encode
a length preference whether or not one is intended.

**4. Can pairwise comparison transfer where the absolute judge failed?**
Plausibly, and it is the one genuinely new idea here — pairwise removes the
calibration problem that made every score come back 7 or 8. But it must be
tested on held-out *creators*, which we cannot currently do (finding 1). The
falsifying benchmark: pairwise agreement with founder labels on a creator
never seen in training, against a coin-flip baseline of 0.5. If it lands under
~0.65 there, it has not transferred.

**5. Calibrating abstention when users expect a count?**
Ship the count, rank by confidence, and mark the tail honestly — the proposal
already says this and it is right. The recorded alternative is better still:
ship 8-10 with a one-tap keep/discard grid. At a ~1-in-5 hit rate, that
converts an unsolved quality problem into a 30-second review problem without
making the user find anything in a 5-hour VOD.

**6. Cheap vs frontier models?**
Frontier only for pairwise comparison of the final ~10 candidates, which is
where calibration matters and volume is low. Everything upstream — discovery,
boundaries, captions, archetype labelling — stays on the Flash/Groq chain.
Never run a frontier model per-window across a VOD.

**7. Detecting semantic stasis without deleting timing?**
This is the hardest question in the document and it is currently unanswered by
anyone's evidence. Escalating repetition measured **0.94x** — nothing. I would
not build on it until something separates "repeating with escalation" from
"repeating" on real data. Treat it as a research question, not a Phase 2 item.

**8. Explicit variants or a searched EDL space?**
Explicit, and fewer than three. Two recipes (tight / full) with a stated
lost-context analysis is testable; a searched space multiplies model calls
against a quality metric we cannot yet measure.

**9. What can retention legitimately supervise?**
Retention curves diagnose *packaging and boundaries* — where viewers leave
tells you the hook failed or the tail ran long. They cannot supervise
selection without heavy confounding by title, thumbnail, posting time and
channel size. Use them for the edit; use pairwise labels for the moment. The
proposal already says this and it is the most defensible paragraph in it.

**10. The strongest simpler alternative.**
See below. It is materially smaller and it is falsifiable this week.

## The simpler alternative, in priority order

Each step states what it predicts, so it can fail.

**Step 1 — Read the 45 Shorts we already own. (~1 evening, $0)**
Attribute every published Short to its source moment, archetype, duration,
title strategy and composition. Ask one question: how much outcome variance is
selection, and how much is packaging? *Prediction: packaging dominates.* If it
does, the whole roadmap reorders and Phase 4 becomes Phase 1. This costs
nothing and is currently the largest unexamined evidence we hold.

**Step 2 — One narrow vision signal, not a comprehension pass. (~1-2 days)**
All six founder labels turn on a single axis: every rejection was a payoff on
the game screen (slot spin, wheel, loot roll); both keepers were the streamer
telling a story. `needs_visuals` already measures 1.36x — the strongest
non-rare signal in the audit — but with the sign *reversed* between crowd
taste (36% vs 17%, the crowd likes on-screen payoffs) and founder taste.

So the question is not "is this moment good". It is:

> Is the payoff carrier actually visible inside the 9:16 composition we are
> about to render?

That is a geometry question about a crop we already compute, combined with a
classification we already emit. It targets the exact failure the founder has
rejected three times, and it strengthens `cap_game_triggered` from a blunt
batch quota into a per-clip check. *Prediction: this converts more of the
current 1-in-5 into keepers than any ranking change, because it removes a
failure class rather than reordering a list.*

**Step 3 — Ship 8-10 with fast review.**
Already the standing recommendation and still unbuilt. At a measured ~1.2x
edge over an 11% base rate, batch size beats ranking. Marginal cost per clip
is ~$0.011.

**Step 4 — Only then, pairwise labels.**
Build the review tool from the proposal — it is well designed — but point it
at the batch the user is already reviewing in step 3, so labels are a
by-product of work the founder does anyway rather than a separate chore. This
is the only path I can see to the hundreds of labels the learning plan needs.

**Step 5 — Revisit the comprehension pass** once there are >=6 creators and
>=200 labels, with a predicted lift and a holdout that includes Tier-C VODs.

## What would change my mind

If step 1 shows selection, not packaging, dominates outcome variance across
the 45 Shorts, then the case for a richer selection model gets much stronger
and I would support bringing Phase 2 forward — still with a predicted lift, a
bounded shortlist, and a creator-diverse holdout.

The proposal's instincts are good and its diagnosis is correct. My objection
is sequencing and evidence discipline, not direction: it proposes the most
expensive and least certain component first, on a benchmark that cannot
currently validate it, against a prior that says to expect ~1.1x.
