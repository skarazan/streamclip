"""Structural signatures from research/clip-quality-spec.md §3 and §5.

Deterministic, free, no model. This exists because the canonical spec's core
finding was ignored twice and both times it cost a week:

    "LLMs are measurably bad humor judges (best model rho=0.27 with humans)
     and their documented #1 failure is over-rating loud/absurd/energetic
     content. Loudness is the weakest, most false-positive-prone signal in
     every academic study."

On 2026-08-03 an LLM humour judge was built and loudness weights were tuned
UP. Both are the failure modes above. The judge showed 1.07x lift over chance
on its `funny` score, and the tuned loudness weight inverted on the holdout
set. The spec predicted both outcomes in advance.

So: humans supply the humour judgement (crowd clips, chat), and the machine
supplies STRUCTURE — the textual and acoustic shapes that reliably accompany
a good moment. Three of the strongest archetypes in §2 are defined by the
ABSENCE of a loud signature, which is precisely why a loudness argmax cannot
find them.

Every function here returns 0..1 and takes only cached artifacts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .transcribe import Word

# §3 lexicons. Deliberately small and literal: these are signatures, not
# sentiment analysis, and a big fuzzy list would fire on everything.
DISBELIEF = ("wait", "no way", "did he just", "did you just", "what the",
             "are you kidding", "you're joking", "i can't believe",
             "hold on", "excuse me", "what just happened", "nah")
SINCERE = ("honestly", "actually love", "means a lot", "thank you so much",
           "i appreciate", "for real though", "that's beautiful",
           "i'm not gonna lie", "genuinely")
LAUGH = re.compile(r"\b(ha){2,}\b|\bhaha\w*|\blmao\w*|\blol\b|\bbruh\b", re.I)
CLIP_CALL = ("clip that", "clip it", "someone clip", "clip this")


@dataclass
class Signature:
    energy_delta: float = 0.0    # §5: delta vs rolling baseline, NOT raw dB
    escalation: float = 0.0      # §3: same phrase repeated 3+ times
    disbelief: float = 0.0       # §3: "wait / no way / did he just"
    self_laugh: float = 0.0      # §5: streamer laughs at their own line
    novelty: float = 0.0         # §3: hard topic discontinuity
    quiet_sincere: float = 0.0   # §3: wholesome = LOW energy + sincerity
    dead_air_after: float = 0.0  # §3: rage-quit signature is the SILENCE
    clip_call: float = 0.0       # §5: near-ground-truth, deliberately capped

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _words_in(words: list[Word], start: float, end: float) -> list[Word]:
    return [w for w in words if start <= w.start < end]


def _text(ws: list[Word]) -> str:
    return " ".join(w.text for w in ws).lower()


def energy_delta(profile, duration: float, start: float, end: float,
                 baseline_s: float = 180.0) -> float:
    """How far this window rises above the streamer's OWN recent level.

    §5: "Voice-energy DELTA vs streamer's rolling baseline (replaces raw dB —
    Eklipse's own fix)". Raw loudness ranks a streamer who is loud all the
    time as one long highlight, and ranks a quiet streamer's biggest moment as
    nothing. The delta is comparable across people, which is the only version
    that can work for a Tier-C customer we have never heard before.
    """
    if profile is None or not len(profile) or duration <= 0:
        return 0.0
    hz = len(profile) / duration
    a, b = int(start * hz), int(min(end, duration) * hz)
    seg = profile[max(0, a):max(a + 1, b)]
    if not len(seg):
        return 0.0
    lo = max(0, int((start - baseline_s) * hz))
    base = profile[lo:max(lo + 1, a)]
    if not len(base):
        return 0.0
    import numpy as np
    med = float(np.median(base))
    spread = float(np.percentile(base, 75) - np.percentile(base, 25)) or 0.05
    return max(0.0, min((float(seg.max()) - med) / (3.0 * spread), 1.0))


def escalation(words: list[Word], start: float, end: float) -> float:
    """§3 escalating rage: the same phrase repeated three or more times."""
    ws = _words_in(words, start, end)
    if len(ws) < 6:
        return 0.0
    toks = [re.sub(r"[^a-z']", "", w.text.lower()) for w in ws]
    toks = [t for t in toks if len(t) > 2]
    best = 0
    for n in (1, 2, 3):                      # unigram..trigram repeats
        seen: dict[tuple, int] = {}
        for i in range(len(toks) - n + 1):
            g = tuple(toks[i:i + n])
            seen[g] = seen.get(g, 0) + 1
        if seen:
            best = max(best, max(seen.values()))
    return min(max(best - 2, 0) / 3.0, 1.0)


def _lexicon_hits(text: str, phrases) -> int:
    return sum(1 for p in phrases if p in text)


def disbelief(words: list[Word], start: float, end: float) -> float:
    return min(_lexicon_hits(_text(_words_in(words, start, end)),
                             DISBELIEF) / 2.0, 1.0)


def self_laugh(words: list[Word], start: float, end: float) -> float:
    """§5: the streamer laughing after their own line reads as genuine."""
    ws = _words_in(words, start, end)
    if not ws:
        return 0.0
    return min(len(LAUGH.findall(_text(ws))) / 2.0, 1.0)


def novelty(words: list[Word], start: float, end: float,
            lookback: float = 25.0) -> float:
    """§3 non-sequitur: how little this window shares with what preceded it.

    Vocabulary overlap, not embeddings — a topic swerve shows up as new nouns
    and it costs nothing to compute.
    """
    cur = set(_text(_words_in(words, start, end)).split())
    prev = set(_text(_words_in(words, start - lookback, start)).split())
    cur = {w for w in cur if len(w) > 3}
    prev = {w for w in prev if len(w) > 3}
    if len(cur) < 4 or not prev:
        return 0.0
    return 1.0 - len(cur & prev) / len(cur)


def quiet_sincere(words: list[Word], start: float, end: float,
                  e_delta: float) -> float:
    """§3 wholesome: sincerity lexicon while energy is LOW.

    "Three strong archetypes are defined by absence of the loud signature" —
    a loudness ranker cannot reach these by construction, which is most of
    why it plateaus.
    """
    hits = _lexicon_hits(_text(_words_in(words, start, end)), SINCERE)
    if not hits:
        return 0.0
    return min(hits / 2.0, 1.0) * (1.0 - min(e_delta, 1.0))


def dead_air_after(words: list[Word], end: float, window: float = 12.0
                   ) -> float:
    """§3 rage quit: profanity/shout then a mid-word cutoff and SILENCE.

    Measured as the speech gap immediately after the window, so the signature
    is the absence of words rather than the presence of any.
    """
    after = [w for w in words if end <= w.start < end + window]
    if not after:
        return 1.0
    return max(0.0, min((after[0].start - end) / 6.0, 1.0))


def clip_call(words: list[Word], start: float, end: float,
              chat_texts: list | None = None) -> float:
    """§5 near-ground-truth, but capped on purpose: streamers say "clip that"
    to bookmark BUGS for later review, not only funny moments."""
    text = _text(_words_in(words, start - 5.0, end + 15.0))
    hits = _lexicon_hits(text, CLIP_CALL)
    return 0.5 if hits else 0.0


def signature(words: list[Word], profile, duration: float,
              start: float, end: float) -> Signature:
    ed = energy_delta(profile, duration, start, end)
    return Signature(
        energy_delta=ed,
        escalation=escalation(words, start, end),
        disbelief=disbelief(words, start, end),
        self_laugh=self_laugh(words, start, end),
        novelty=novelty(words, start, end),
        quiet_sincere=quiet_sincere(words, start, end, ed),
        dead_air_after=dead_air_after(words, end),
        clip_call=clip_call(words, start, end),
    )
