"""Candidate generation + judging — the inverted selection architecture.

Measured on the selection harness, 2026-08-03, dev set of 7 VODs:

    LLM scoring, top-5 picks                recall 0.057
    ...its ENTIRE candidate pool (ceiling)  recall 0.286
    loudness peaks k=40 gap=30 (ceiling)    recall 0.886
    loudness+chat union    (ceiling)        recall 0.829

`score_with_llm` reads the transcript and emits ~15 moments an hour. Those
moments are usually real — measured against crowd clusters they land within
seconds of *a* moment humans clipped — but they systematically miss the
BIGGEST ones, and every score comes back 7 or 8, so nothing can be ranked.
A perfect re-ranker of that pool still caps at 0.286.

So stop asking one model to do both jobs. Cheap signals answer "where did
something happen" with ~0.89 coverage for free; the model answers "which of
these is worth posting", which is the part it is actually good at and the
part the founder's verdicts are about.

Deterministic ranking of the cheap pool plateaus at ~0.257 (loudness, chat,
rank-fusion and product combinations were all measured; none separated). That
plateau is the reason a judging pass exists at all: the pool contains the
right moments, and only judgement gets them to the top.

The judge reports FACTS in a schema; `rank_judged` makes the decision in
code. On 2026-07-25 three prose selection rules were written into the editor
prompt and the model argued past all three in one run — "loudness confirms
hype" when told loudness may only reject, "needs no visuals" when given an
explicit off-screen test. A schema field it must fill is not a request it can
rationalise around.
"""

from __future__ import annotations

import json

from . import usage
from .transcribe import Word

# Window shape. The crowd's own clip starts sit ~10-25s before the payoff
# (DECISIONS.md 2026-07-23), so a candidate is anchored slightly before its
# peak and runs long enough to contain a punchline.
PRE_S = 12.0
POST_S = 26.0


def _peak_times(series: list[tuple[float, float]], lo: float, hi: float,
                k: int, min_gap: float) -> list[float]:
    inside = [(t, v) for t, v in series if lo <= t < hi]
    inside.sort(key=lambda tv: tv[1], reverse=True)
    chosen: list[float] = []
    for t, _ in inside:
        if all(abs(t - c) >= min_gap for c in chosen):
            chosen.append(t)
        if len(chosen) >= k:
            break
    return chosen


def candidates(words: list[Word], profile, chat: dict | None,
               lo: float, hi: float, per_signal: int = 40,
               min_gap: float = 30.0) -> list[dict]:
    """High-recall pool of windows worth judging.

    Recall is the only job here; precision is the judge's problem. k=40 at a
    30s gap measured 0.886 coverage of the crowd's top-5 against 0.657 at a
    60s gap — a tight gap matters more than the count, because real moments
    cluster together and a wide gap suppresses the neighbour that was the
    actual payoff.
    """
    duration = words[-1].end if words else hi
    out: list[float] = []
    if profile is not None and len(profile) and duration > 0:
        hz = len(profile) / duration
        out += _peak_times([(i / hz, float(v)) for i, v in enumerate(profile)],
                           lo, hi, per_signal, min_gap)
    density = (chat or {}).get("density") or []
    series = [(float(t), float(v)) for t, v in density
              if isinstance(t, (int, float))]
    if series:
        out += _peak_times(series, lo, hi, per_signal, min_gap)

    cands: list[dict] = []
    for t in sorted(out):
        # near-duplicates across the two signals are the SAME moment found
        # twice, which is a good sign, not two candidates
        if any(abs(t - c["peak"]) < 15.0 for c in cands):
            continue
        cands.append({"peak": t,
                      "start": max(lo, t - PRE_S),
                      "end": min(hi, t + POST_S)})
    return cands


def transcript_between(words: list[Word], start: float, end: float,
                       limit: int = 900) -> str:
    txt = " ".join(w.text for w in words if start <= w.start < end)
    return txt[:limit]


JUDGE_SYS = """You rate candidate moments from a live stream for use as a
standalone vertical Short.

You are given numbered windows of transcript. For each one, report what is
actually there. Do not try to fill a quota and do not argue for a moment you
would not watch — a caller decides what ships, using your fields.

For every candidate return:
  idx            the number given
  has_story      true only if the window contains a setup and a payoff a
                 first-time viewer could follow with no prior context
  payoff_kind    speech | scream | game_event | none
                 game_event = the point of the moment is something that
                 happened on the game screen (a win, a roll, a score, a
                 killfeed, a menu). Use it even when the streamer reacts
                 loudly.
  needs_visuals  true if the moment is unintelligible without seeing the
                 game screen
  streamer_speaks true if the streamer himself is the one talking
  funny          0-10, how likely a stranger scrolling laughs or is gripped
  quote          the single funniest or most gripping line, verbatim, or ""
"""

JUDGE_SCHEMA = {
    "name": "judgements",
    "schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "idx": {"type": "integer"},
                        "has_story": {"type": "boolean"},
                        "payoff_kind": {"type": "string",
                                        "enum": ["speech", "scream",
                                                 "game_event", "none"]},
                        "needs_visuals": {"type": "boolean"},
                        "streamer_speaks": {"type": "boolean"},
                        "funny": {"type": "integer"},
                        "quote": {"type": "string"},
                    },
                    "required": ["idx", "has_story", "payoff_kind",
                                 "needs_visuals", "streamer_speaks",
                                 "funny", "quote"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _items_of(data) -> list:
    """The judged list, whatever envelope the provider chose.

    Strict json_schema responses come back wrapped in the schema name;
    prompt-enforced JSON comes back bare; some models return a bare array.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("items"), list):
        return data["items"]
    for v in data.values():
        if isinstance(v, dict) and isinstance(v.get("items"), list):
            return v["items"]
        if isinstance(v, list) and v and isinstance(v[0], dict) and "idx" in v[0]:
            return v
    return []


def judge(cands: list[dict], words: list[Word], model: str,
          base_url: str | None = None, api_key_env: str | None = None,
          fallback_models: list[str] | None = None,
          streamer: str = "the streamer", batch: int = 20,
          reasoning_effort: str | None = None,
          log=print) -> list[dict]:
    """Attach judge fields to each candidate, in place. Returns the list.

    Batched because one call rating 40 windows drifts — later items get
    terser, lazier answers. Candidates the judge never returns keep
    `judged=False` and are ranked last rather than dropped, so a truncated
    or malformed response degrades the batch instead of losing the VOD.
    """
    from . import detect

    client_for = detect._client_provider(model, base_url, api_key_env,
                                         timeout=detect.EDITOR_TIMEOUT_S)
    chain = [model] + list(fallback_models or [])
    for c in cands:
        c.setdefault("judged", False)

    for i in range(0, len(cands), batch):
        group = cands[i:i + batch]
        lines = []
        for j, c in enumerate(group):
            body = transcript_between(words, c["start"], c["end"])
            lines.append(f"[{i + j}] t={c['peak']:.0f}s  {body}")
        prompt = (f"Streamer: {streamer}\n\nCandidates:\n"
                  + "\n\n".join(lines))
        data = None
        for name in chain:
            try:
                fn = detect._fn_for(name)
                data = fn(client_for(name), name, prompt, system=JUDGE_SYS,
                          schema=JUDGE_SCHEMA,
                          reasoning_effort=reasoning_effort)
                break
            except Exception as e:
                log(f"  ! judge batch on {name} failed ({type(e).__name__}: "
                    f"{str(e)[:90]})")
        if not data:
            continue
        items = _items_of(data)
        if not items:
            # Never silent. A strict-schema response arrives wrapped in the
            # schema NAME ({"judgements": {"items": [...]}}) while the
            # prompt-enforced JSON fallback returns it bare, and reading only
            # the bare shape dropped every judgement on ~40% of batches while
            # reporting success — the batch simply ranked last.
            log(f"  ! judge batch {i}: no items in response "
                f"(keys={list(data)[:4]}) — {len(group)} candidates unjudged")
            continue
        by_idx = {c_["idx"]: c_ for c_ in items
                  if isinstance(c_, dict) and "idx" in c_}
        for j, c in enumerate(group):
            got = by_idx.get(i + j)
            if not got:
                continue
            c.update({k: got.get(k) for k in
                      ("has_story", "payoff_kind", "needs_visuals",
                       "streamer_speaks", "funny", "quote")})
            c["judged"] = True
    return cands


def rank_judged(cands: list[dict], k: int, min_gap: float = 90.0,
                allow_game_frac: float = 1.0) -> list[dict]:
    """Decide in code what the schema reported.

    A game_event payoff is NOT a defect. The founder's rejected clips read as
    "the gambling wasn't even in frame" — that is the 9:16 crop cutting the
    slot/wheel/loot UI out of the gameplay pane, not the moment being weak.
    The crowd agrees: among candidates matching the crowd's top-5, 36% were
    judged `needs_visuals` against 17% elsewhere, so on-screen payoffs are
    what people clip. Those moments are handled in RENDER (a clip whose
    payoff is visual is framed to keep the whole game frame) rather than
    demoted here. `allow_game_frac` stays as a lever but defaults to open.
    """
    def base(c: dict) -> float:
        if not c.get("judged"):
            return -1.0
        s = float(c.get("funny") or 0)
        if c.get("has_story"):
            s += 3.0
        if c.get("streamer_speaks"):
            s += 1.5
        if c.get("payoff_kind") == "none":
            s -= 4.0
        return s

    ranked = sorted(cands, key=base, reverse=True)
    picks: list[dict] = []
    game_cap = max(1, int(k * allow_game_frac))
    game_used = 0
    for c in ranked:
        if len(picks) >= k:
            break
        if any(abs(c["peak"] - p["peak"]) < min_gap for p in picks):
            continue
        is_game = c.get("payoff_kind") == "game_event"
        if is_game and game_used >= game_cap:
            # only hold the slot if a non-game candidate can still fill it
            if any(o.get("payoff_kind") != "game_event" and base(o) > -1.0
                   and o not in picks
                   and all(abs(o["peak"] - p["peak"]) >= min_gap for p in picks)
                   for o in ranked):
                continue
        picks.append(c)
        game_used += int(is_game)
    return picks
