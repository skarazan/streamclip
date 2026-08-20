# Archetype-aware semantic selection and editing

**Status:** Proposal for independent review
**Date:** 2026-08-19
**Requested reviewer:** Opus
**Scope:** Clip selection, duration choice, and semantic cutting. This does not
propose another dashboard/editor redesign.

## Executive summary

Streamclip has become substantially better at rendering, framing, aligning,
editing, and delivering the moment it selected. The remaining bottleneck is
that the selected moment is frequently mediocre.

The next system must not penalize clips merely for being long or reward clips
merely for being short. A five-second reaction and a 59-second rant can both be
excellent. Their structures, context requirements, pacing, and definitions of
completion are different.

The proposed replacement is an **archetype-aware semantic editor**. It first
understands what kind of moment it is evaluating, maps the contribution of each
beat, creates several non-rendered cut recipes when appropriate, and selects
the shortest version that preserves the complete experience—not simply the
shortest version.

The universal rule is:

> Do not demand fast progression. Demand continuous contribution.

Quiet anticipation may contribute. A long section of active speech may not.
Silence, loudness, and total duration therefore cannot be used as direct
quality proxies.

## Why the current approach plateaus

The existing deterministic checks are useful correctness gates. They can prove
that a localized trigger precedes a localized button, that the final media is
valid, and that no detected silence gap violates the configured policy. They
cannot prove that:

- the premise is interesting;
- the reaction is genuine rather than ordinary performance;
- the viewer can see or hear the cause of the reaction;
- repeated material escalates rather than stalls;
- the payoff is worth the setup;
- a stranger understands why the moment is entertaining; or
- the clip ends when its value is exhausted.

The August signal audit measured fourteen signals across transcript, audio,
chat, and vision. Most produced only a small lift, and LLM judging failed to
transfer to held-out VODs. A system that verifies words in the correct order is
therefore a syntax validator, not an entertainment judge.

The latest persisted Maj0r output demonstrates the distinction:

- A countdown clip passes the ordered-arc and silence checks, although a long
  span separates the opening trigger from the final scream.
- A short spin reaction establishes its quoted trigger late and does not make
  the underlying cause sufficiently legible in the vertical presentation.
- A breaker clip is coherent and technically complete, but its payoff is too
  ordinary to justify publishing.
- A more concrete `$30 scam` candidate was benched below the vague spin
  reaction, suggesting that the ranker does not adequately value specificity,
  reversal, or self-contained stakes.

## Corrected product assumptions

### There is no universal timestamp for a good clip

Rules such as "trigger by two seconds," "a new beat every four seconds," or
"payoff by fifteen seconds" are inappropriate as universal gates. They may be
useful priors for a particular archetype, but not hard constraints.

A clip should instead retain every passage that contributes to one or more of:

- comprehension;
- anticipation;
- tension;
- surprise;
- escalation;
- specificity;
- emotional change;
- character/personality;
- reversal;
- payoff; or
- a satisfying closing button.

A passage should be removable when it is redundant, disconnected, already
implied, or occurs after the experience has ended.

### Silence is not equivalent to dead space

Silence can contain anticipation, discomfort, visual discovery, or reaction.
Conversely, active conversation can be dead space when it repeats a point,
addresses unrelated chat messages, or explains something already understood.

The relevant property is **semantic contribution**, not waveform activity.

### Not every excellent clip has a classical story arc

A facial reaction, one-word stinger, absurd statement, deadpan observation, or
brief non sequitur may be complete without setup/escalation/payoff phases.
Requiring every candidate to imitate a miniature three-act story will destroy
some of the best short clips.

## Proposed archetypes

Archetypes describe completion criteria, not duration limits.

| Archetype | Definition of completion | Common failure |
|---|---|---|
| Stinger/reaction | Cause is inherent, visible, audible, or supplied honestly by minimal packaging; reaction lands | Extra context weakens immediacy |
| Quick joke/reversal | Premise and contradiction/punchline are both legible | Starts after required setup or continues after punchline |
| Banter/roast | Target, exchange, retort, and social reaction are understandable | Missing speaker/context or too much preamble |
| Reveal/discovery | Viewer understands expectation, discovery, and reaction | Reveal is off-screen or title promises more than video shows |
| Rant/vent | Thesis is clear, successive details add novelty or escalation, and a strong closer completes it | Repetition without escalation |
| Story/confession | Necessary context, complication, turn, and resolution are preserved | Context-heavy opening or premature ending |
| Committed bit | Repetition is itself entertaining because each pass intensifies or mutates | Mechanical repetition with no change |
| Tension/scare | Anticipation and release are preserved | Silence is removed even though it creates the tension |
| Wholesome/sincere | Emotional premise and authentic change are legible | Downranked for low energy |
| Gameplay achievement/failure | Stakes and decisive event are visible, then reaction resolves it | Face-only crop hides the actual payoff |

The taxonomy must remain extensible. Classification should allow a primary and
secondary archetype, plus `unknown`, rather than forcing every moment into an
incorrect category.

## Proposed pipeline

### 1. High-recall candidate discovery

Continue using all cheap evidence as recall mechanisms:

- every available Twitch viewer clip, including sparse single examples;
- raw and baseline-relative audio events;
- self-laughter;
- chat semantics and velocity anomalies;
- transcript topic changes and unusual statements; and
- visually significant events where cheaply available.

No individual discovery signal should be treated as the final quality score.

### 2. Multimodal comprehension pass

For each shortlisted moment, inspect a generous low-resolution window—roughly
60–90 seconds where source boundaries permit—with aligned video, audio, and
transcript.

The model must return structured evidence rather than a single quality score:

- primary and secondary archetype;
- literal description of what happens;
- why a stranger might care;
- required prior context;
- the carrier of the trigger and payoff (`speech`, `face`, `gameplay`, another
  person, external media, sound, or a combination);
- strongest line, image, reaction, or reversal;
- whether the response appears genuine, performative, or indeterminate;
- proposed semantic beats;
- removable passages and the reason each is removable;
- earliest coherent opening;
- strongest valid ending; and
- uncertainty and missing evidence.

Generic explanations must fail. For example, "an energetic and relatable
reaction" does not demonstrate comprehension. A valid explanation should name
the actual expectation and change, such as: "He pays $30 expecting useful
information, discovers the download is footage of his own car and license
plate, then realizes aloud that he was scammed."

### 3. Semantic beat graph

Represent the candidate as timestamped beats with dependencies:

```text
premise ──> first example ──> escalation ──> reversal ──> closer
               └──────── required context ───────────────┘
```

Each beat records:

- start/end time;
- contribution types;
- novelty relative to earlier beats;
- required predecessors;
- payoff dependencies;
- visual/audio carrier;
- whether it can be summarized honestly by packaging; and
- confidence.

This structure lets the editor remove redundancy without removing a necessary
pause, visual observation, or contextual dependency.

### 4. Multiple virtual cut recipes

Where the content supports it, generate up to three edit-decision lists without
rendering three videos:

- **Stinger:** smallest independently satisfying experience.
- **Standard:** necessary stranger-safe context plus the complete moment.
- **Full:** complete rant, story, or escalating bit when later beats continue to
  add value.

Not every candidate needs all three. A one-line reaction may have only one valid
recipe; a long rant may have two or three.

For every recipe, the model must state:

- what context is lost;
- what value the longer version adds;
- whether discontinuities introduced by cuts are perceptible;
- whether the ending improves or merely continues; and
- whether captions/title would need to replace removed exposition.

These recipes remain timestamp instructions over a shared proxy/source until
the user requests final export. Only the automatically selected recipe is
rendered by default. Alternatives may be exposed as optional timeline presets,
not as a mandatory candidate-picking workflow.

### 5. Archetype-aware comparative ranking

Avoid absolute prompts such as "rate this clip from 1–10" or "will this go
viral?" Compare candidates and edit recipes directly:

- Which is more self-contained for a stranger?
- Which has the more specific or surprising change?
- Which reaction appears less routine for this creator?
- Which version preserves everything that makes the moment work with less
  redundancy?
- Does the long version keep adding value, or merely take longer?
- Does a short version feel powerful or contextless?
- Is the essential event legible in the proposed 9:16 composition?

The final rank should combine structured evidence, pairwise comparisons, crowd
evidence, creator-specific history, and calibrated uncertainty. The LLM's raw
"funny" or "viral" score must not be a dominant feature.

### 6. Honest packaging and dynamic composition

Generate titles, opening captions, and layout only after the cut recipe is
selected.

Packaging may replace boring exposition when it can do so truthfully. For
example, an opening caption such as "He paid $30 to download this" can allow a
clip to begin near the discovery. It must not invent stakes or make a weak
reaction sound consequential.

Composition should follow the payoff carrier:

- gameplay-dependent payoff: preserve a legible game region;
- face-dependent reaction: face may dominate;
- another person or external video: include the necessary subject if possible,
  otherwise reject;
- sound-dependent moment: preserve anticipation and make captions avoid
  obscuring visual evidence.

## Value density without a duration penalty

Duration is an output, not an optimization target.

A conceptual quality model is:

```text
value density =
    comprehension
  + anticipation/tension
  + surprise/reversal
  + escalation/novelty
  + specificity/personality
  + emotional change
  + payoff/closure
  - redundancy
  - disconnected material
  - unexplained dependencies
  - post-completion drift
```

This should not initially be implemented as a hand-tuned numerical formula.
The categories are an evidence schema for comparison and evaluation. Fixed
weights would create a new brittle proxy and invite reward hacking.

## Learning and evaluation

### Pairwise labels

Build a small founder-review tool that presents two low-resolution candidates
or two cut recipes from the same VOD. Record:

- `A`, `B`, `both`, or `neither`;
- primary rejection reason;
- whether the preferred clip is publishable; and
- optional boundary correction.

Suggested rejection taxonomy:

- no context;
- weak premise;
- weak payoff;
- routine/performed reaction;
- redundant middle;
- premature ending;
- post-payoff drift;
- essential cause not visible;
- inside joke/channel knowledge required;
- misleading packaging;
- technically broken; or
- good moment, wrong cut.

Pairwise judgments should eventually train or calibrate a small ranking model.
Evaluation splits must hold out entire creators, not merely VODs, to expose
streamer-specific leakage.

### Real outcome data

Connect each published Short to its final source and edit recipe. Ingest, where
available:

- engaged views;
- average view duration and percentage;
- audience retention curve;
- likes, comments, shares, and subscribers gained;
- publication time and channel baseline; and
- title, opening, composition, duration, archetype, and confidence.

Outcome labels are noisy. Normalize within channel and publication period, wait
for a minimum observation window/sample, and do not treat raw views alone as
quality. Titles, distribution, audience size, and posting time are confounders.

Retention curves should diagnose packaging and cut failures, while pairwise
human labels remain the cleaner early signal for whether the underlying moment
was worth publishing.

### Metrics

Track selection and editing separately:

- precision among automatically shipped clips;
- publishable clips per VOD;
- `neither` rate in pairwise review;
- archetype-specific precision;
- creator-held-out precision;
- boundary correction frequency;
- failure-reason distribution;
- retention relative to the creator/channel baseline; and
- calibration: whether high-confidence clips actually outperform lower-
  confidence clips.

## Quantity and abstention

Forcing a fixed number of clips conflicts with quality. Some VODs may contain
one strong moment; others may contain ten.

Discovery and initial shipping should remain automatic, consistent with the
current product rule. The system should, however, be allowed to return fewer
clips when remaining candidates do not clear a calibrated quality threshold.
It should state this honestly rather than filling quota with mediocre outputs.

If a fixed commercial quantity remains mandatory, treat it explicitly as a
product tradeoff: later clips in the batch will have lower confidence. Do not
silently market all eight as equally verified.

## Compute and latency strategy

This architecture does not require full-resolution multimodal analysis across
an entire VOD:

1. Discover candidates with cached cheap signals.
2. Create one shared low-resolution proxy.
3. Analyze only shortlisted windows multimodally.
4. Cache transcripts, frames, embeddings, beat maps, and model responses.
5. Represent variants as edit-decision lists rather than rendered files.
6. Render full quality only once, after automatic recipe selection or a user
   correction.

The expensive model should be reserved for ambiguous candidate comparisons,
not used uniformly across every minute.

## Failure modes and safeguards

### Archetype misclassification

Allow primary/secondary types and `unknown`. Compare multiple interpretations
when confidence is low. Never use archetype alone as a hard rejection reason.

### Model rationalization

Models can invent plausible reasons after seeing an energetic reaction.
Require timestamped audiovisual evidence and reject generic explanations. Use
blind pairwise comparison and real outcomes to test transfer.

### Overcompression

The shortest coherent version is not automatically the best. Require an
explicit lost-context analysis and preserve tension, timing, character, and
escalation when they contribute.

### Undercompression

Talking is not automatically contribution. Repeated ideas must add specificity,
intensity, contradiction, or character; otherwise they are candidates for
removal.

### Packaging leakage

Evaluate both the raw moment and the packaged version. A title may provide
minimal context but cannot substitute for an absent payoff or hidden essential
event.

### Creator cold start

Use a general creator-held-out model, available crowd evidence, and conservative
confidence. Personalize only after enough approved/published examples exist.

### Outcome-data bias

Raw platform performance is influenced by distribution and channel size. Use
engagement and retention relative to channel baselines, minimum sample sizes,
and paired experiments where practical.

## Proposed implementation order

### Phase 1 — Evaluation foundation

- Define the structured comprehension and beat-map schemas.
- Implement pairwise review and rejection-reason capture.
- Assemble a creator-diverse benchmark, including small-streamer/Tier-C VODs.
- Establish creator-held-out baseline metrics.

### Phase 2 — Semantic cut generation

- Add the multimodal comprehension pass over shortlisted low-resolution
  windows.
- Generate beat graphs and virtual stinger/standard/full recipes.
- Validate recipe continuity against actual media.
- Add archetype-aware comparative selection and calibrated abstention.

### Phase 3 — Outcome loop

- Import historical and future YouTube analytics.
- Attribute results to source candidate, recipe, archetype, and packaging.
- Build retention diagnostics and channel-relative outcome labels.
- Periodically recalibrate ranking without allowing the model to judge itself.

### Phase 4 — Adaptive packaging

- Choose composition from the payoff carrier.
- Generate titles/openings from the final recipe.
- Test packaging independently from moment selection.
- Expose alternate valid lengths as optional non-rendered editor presets.

## Explicit non-goals

- A universal ideal clip length.
- Hard timestamp gates shared by every archetype.
- Another prompt that returns a viral/funny score.
- Treating loudness, silence, or speech activity as entertainment quality.
- Rendering every candidate or duration variant.
- Reintroducing a mandatory human candidate picker.
- Using effects to compensate for a weak underlying moment.

## Questions for Opus review

Please challenge the proposal rather than merely polishing it:

1. Is archetype classification the right first abstraction, or will it create
   another brittle taxonomy before the model understands the moment?
2. What is the smallest structured representation that captures semantic
   contribution without becoming an expensive, unreliable screenplay parser?
3. How should stingers and intentionally contextless absurd moments be compared
   against complete stories without systematically favoring either?
4. Can pairwise multimodal comparison transfer across creators better than the
   failed absolute LLM judge, and what benchmark would falsify that assumption?
5. How should uncertainty and abstention be calibrated when paying users expect
   a clip count?
6. Which parts can run on cheap/free models, and where would a frontier model
   materially change selection quality?
7. How can we detect genuine semantic stasis in active speech without deleting
   comedic timing, character work, or escalation?
8. Should short/standard/full be explicit variants, or should the model search
   a larger space of edit-decision lists?
9. What information from real retention curves can legitimately supervise
   selection, versus only diagnosing the final edit and packaging?
10. What is the strongest simpler alternative to this architecture?

## Review acceptance bar

Do not recommend implementation merely because the design sounds plausible.
The proposal should proceed only if the reviewer can identify:

- a falsifiable offline evaluation;
- a creator-diverse dataset plan;
- a compute-bounded implementation path;
- safeguards against model rationalization and benchmark overfitting; and
- a measurable improvement target over the existing selector.
