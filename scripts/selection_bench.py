"""Selection harness — grade clip picking against what humans actually clipped.

A test bench, NOT part of the product. No rendering, no downloads, no R2, no
database, no worker. Reads cached artifacts, calls the scorer, prints numbers.

    python scripts/selection_bench.py --set dev --k 5 --max-usd 2.00
    python scripts/selection_bench.py --set dev --baselines-only     # free

Why it exists: testing one selection idea used to mean a full run (~20 min,
~$0.50, renders) ending in a founder verdict over 3 clips. On 2026-07-25 four
selection changes were tried that way — one worked, three did not, and a
controlled A/B regressed. At n=3 nothing is separable from variance.

The answer key is viewer clips. We hide them from the model, run selection on
the transcript alone (exactly a Tier-C streamer's position), and check whether
the picks land where humans actually pressed the clip button.

Known limitation, repeated in every report: VODs with heavy crowd clipping
belong to BIG streamers, while the paying customer is Tier C with almost no
viewer clips. This measures "does it find what humans found" on Tier-A
material and extrapolates. A harness win is necessary, not sufficient — the
founder's labelled batches remain the acceptance test.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from clipfarm import crowd, detect, usage  # noqa: E402
from clipfarm.config import PROJECT_ROOT, load_config  # noqa: E402
from clipfarm.transcribe import Word  # noqa: E402

WORK = PROJECT_ROOT / "work"
BENCH = PROJECT_ROOT / "bench"

# Mirrors web/app/lib/llmPrices.js. USD per 1M tokens. If these drift from the
# web app the campaign's spend numbers stop matching /admin/costs.
PRICES = {
    "gpt-5-mini": {"in": 0.25, "cached": 0.025, "out": 2.00},
    "gpt-5": {"in": 1.25, "cached": 0.125, "out": 10.00},
    "gpt-5-nano": {"in": 0.05, "cached": 0.005, "out": 0.40},
    "llama-3.3-70b-versatile": {"in": 0.59, "cached": 0.59, "out": 0.79},
    "gemini-3.5-flash": {"in": 0, "cached": 0, "out": 0},
    "gemini-3.6-flash": {"in": 0, "cached": 0, "out": 0},
}


def spend_usd(snapshot: dict) -> float:
    total = 0.0
    for model, e in (snapshot or {}).items():
        p = PRICES.get(model)
        if not p:
            continue
        total += (e.get("input_tokens", 0) * p["in"]
                  + e.get("cached_input_tokens", 0) * p["cached"]
                  + e.get("output_tokens", 0) * p["out"]) / 1e6
    return total


class BudgetExceeded(RuntimeError):
    """Hard stop. Not a warning — the sweep aborts."""


# ---------------------------------------------------------------- corpus


@dataclass
class Vod:
    vid: str
    words: list
    clusters: list
    profile: np.ndarray | None
    chat_density: list


def load_vod(vid: str) -> Vod | None:
    d = WORK / vid
    tr = sorted(d.glob("transcript*.json"))
    clips_cache = d / "twitch_clips.json"
    if not tr or not clips_cache.exists():
        return None
    words = [Word(**w) for w in json.loads(tr[0].read_text())]
    # The clustering rules are load-bearing (DECISIONS.md 2026-07-23) — reuse
    # crowd.py rather than reimplementing them here.
    clusters = crowd.cluster_moments(json.loads(clips_cache.read_text()))
    prof_path = d / "loudness.npy"
    profile = np.load(prof_path) if prof_path.exists() else None
    density = []
    chat_path = d / "chat.json"
    if chat_path.exists():
        try:
            raw = json.loads(chat_path.read_text())
            density = raw.get("density", []) if isinstance(raw, dict) else raw
        except Exception:
            density = []
    return Vod(vid, words, clusters, profile, density)


def corpus(which: str) -> list[str]:
    """Deterministic dev/holdout split so runs are comparable over time.

    Standing rule: dev set for iterating, holdout ONLY for confirming a winner.
    Mixing them overfits and re-spends the budget.
    """
    vids = sorted(p.name for p in WORK.iterdir()
                  if p.is_dir() and (p / "twitch_clips.json").exists()
                  and list(p.glob("transcript*.json")))
    dev = vids[::2]          # interleaved, not first-N: avoids any date bias
    hold = vids[1::2]
    return {"dev": dev, "holdout": hold, "all": vids}[which]


# ---------------------------------------------------------------- slicing


def pick_slice(vod: Vod, minutes: float) -> tuple[float, float, list]:
    """The densest `minutes`-long window, and the clusters inside it.

    Scoring a whole 5h VOD costs ~6x a 1h slice for the same measurement: the
    model still has to FIND the moments in an hour it knows nothing about.
    This is what makes the campaign fit in $20.
    """
    span = minutes * 60.0
    if not vod.clusters:
        return 0.0, span, []
    starts = sorted(c.anchor_start for c in vod.clusters)
    best, best_n = starts[0], 0
    for s in starts:                       # window anchored on each cluster
        n = sum(1 for c in vod.clusters if s <= c.anchor_start < s + span)
        if n > best_n:
            best, best_n = s, n
    lo = max(0.0, best - 60.0)             # a little runway before the first
    hi = lo + span
    inside = [c for c in vod.clusters if lo <= c.anchor_start < hi]
    return lo, hi, inside


# ---------------------------------------------------------------- scoring


def is_hit(pick_start: float, pick_end: float, cluster) -> bool:
    """Asymmetric on purpose.

    DECISIONS.md 2026-07-23: crowd `vod_offset` is where a viewer STARTED a
    clip, not where the payoff is — the payoff is usually after it. A
    symmetric +/-45s window (that is the CLUSTERING diameter, not a hit rule)
    would score a pick that ends before the payoff as a success.
    """
    return (pick_start - 20.0) <= cluster.anchor_start <= pick_end


def spearman(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 2:
        return 0.0

    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        for pos, i in enumerate(order):
            r[i] = pos
        return r

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra)
                    * sum((y - mb) ** 2 for y in rb))
    return num / den if den else 0.0


def score_picks(picks: list[tuple[float, float]], clusters: list, k: int
                ) -> dict:
    """picks: [(start, end)] already truncated to k, ranked best-first."""
    top = sorted(clusters, key=lambda c: c.strength, reverse=True)[:k]
    hit_by_pick, matched = [], set()
    for ps, pe in picks:
        m = next((i for i, c in enumerate(top)
                  if i not in matched and is_hit(ps, pe, c)), None)
        hit_by_pick.append(m)
        if m is not None:
            matched.add(m)
    hits = len(matched)
    total_strength = sum(c.strength for c in top) or 1.0
    found_strength = sum(top[i].strength for i in matched)
    # rank correlation: pick order vs strength of whatever it matched
    pr = [i for i, m in enumerate(hit_by_pick) if m is not None]
    cs = [top[hit_by_pick[i]].strength for i in pr]
    return {
        "recall": hits / max(len(top), 1),
        "precision": hits / max(len(picks), 1),
        "sw_recall": found_strength / total_strength,
        "rank_corr": -spearman(pr, cs) if len(pr) > 1 else 0.0,
        "hits": hits, "n_clusters": len(top), "n_picks": len(picks),
    }


# ---------------------------------------------------------------- baselines


def baseline_random(lo: float, hi: float, k: int, seed: int
                    ) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    out = []
    for _ in range(k):
        s = rng.uniform(lo, max(lo, hi - 25))
        out.append((s, s + 25))
    return out


def _peaks(series: list[tuple[float, float]], lo: float, hi: float, k: int,
           min_gap: float = 90.0) -> list[tuple[float, float]]:
    inside = [(t, v) for t, v in series if lo <= t < hi]
    inside.sort(key=lambda tv: tv[1], reverse=True)
    chosen: list[float] = []
    for t, _ in inside:
        if all(abs(t - c) >= min_gap for c in chosen):
            chosen.append(t)
        if len(chosen) == k:
            break
    return [(t - 5, t + 20) for t in chosen]


def baseline_loudness(vod: Vod, lo: float, hi: float, k: int
                      ) -> list[tuple[float, float]]:
    if vod.profile is None or not len(vod.profile):
        return []
    duration = vod.words[-1].end if vod.words else 0.0
    if duration <= 0:
        return []
    hz = len(vod.profile) / duration
    series = [(i / hz, float(v)) for i, v in enumerate(vod.profile)]
    return _peaks(series, lo, hi, k)


def baseline_chat(vod: Vod, lo: float, hi: float, k: int
                  ) -> list[tuple[float, float]]:
    series = [(float(t), float(v)) for t, v in (vod.chat_density or [])
              if isinstance(t, (int, float))]
    return _peaks(series, lo, hi, k) if series else []


# ---------------------------------------------------------------- llm


CACHE = BENCH / "cache"

_MOMENT_FIELDS = ("start", "end", "score", "title", "hook", "reason", "energy",
                  "archetype", "trigger_quote", "button_quote",
                  "trigger_role", "button_role", "button_kind")


def llm_moments(vod: Vod, lo: float, hi: float, cfg: dict,
                log=lambda *_: None) -> list:
    """The REAL scorer on the slice, crowd path hidden, CACHED to disk.

    The model is in exactly a Tier-C streamer's position: no crowd moments,
    no chat tags beyond what scoring normally gets.

    Caching is what makes a campaign affordable. The key includes the prompt
    fingerprint and model, so a prompt edit invalidates it automatically and a
    stale answer can never be scored as if it were fresh. Everything
    downstream of scoring — fusion weights, re-ranking, gap rules — then costs
    nothing to test, which is the difference between four experiments a day
    and forty.
    """
    llm = cfg["llm"]
    words = [w for w in vod.words if lo <= w.start < hi]
    if not words:
        return []
    key = (f"{vod.vid}_{lo:.0f}-{hi:.0f}_{detect.prompt_fingerprint()}"
           f"_{llm['model']}_{llm.get('reasoning_effort') or 'default'}.json")
    path = CACHE / key
    if path.exists():
        try:
            return [detect.Moment(**d) for d in json.loads(path.read_text())]
        except Exception:
            pass  # unreadable cache is not a reason to fail a sweep
    moments = detect.score_with_llm(
        words, llm["model"], llm["chunk_minutes"], log=log,
        base_url=llm.get("base_url"), api_key_env=llm.get("api_key_env"),
        streamer=cfg.get("streamer_name", "the streamer"),
        fallback_models=llm.get("fallback_models"),
        profile=vod.profile, persona="generic", chat=None,
        title_strategy=cfg.get("style", {}).get("title_strategy", "curiosity"),
        reasoning_effort=llm.get("reasoning_effort"))
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(
        [{f: getattr(m, f) for f in _MOMENT_FIELDS} for m in moments]))
    tmp.replace(path)          # atomic: an interrupted sweep leaves no half file
    return moments


def llm_picks(vod: Vod, lo: float, hi: float, k: int, cfg: dict,
              log=lambda *_: None) -> list[tuple[float, float]]:
    moments = sorted(llm_moments(vod, lo, hi, cfg, log),
                     key=lambda m: m.score, reverse=True)
    return [(m.start, m.end) for m in moments[:k]]


# ------------------------------------------------------- fusion (free to run)


def _loudness_at(vod: Vod, start: float, end: float) -> float:
    """Peak loudness inside a window, 0..1. The scorer already sees [SCREAM]
    tags, but only as text — this is the raw number it cannot argue with."""
    if vod.profile is None or not len(vod.profile):
        return 0.0
    duration = vod.words[-1].end if vod.words else 0.0
    if duration <= 0:
        return 0.0
    hz = len(vod.profile) / duration
    a, b = int(start * hz), int(min(end, duration) * hz)
    seg = vod.profile[max(0, a):max(a + 1, b)]
    return float(seg.max()) if len(seg) else 0.0


def _chat_at(vod: Vod, start: float, end: float) -> float:
    """Max chat density in a window, normalised against this VOD's own
    baseline — a 5-viewer channel spikes on the same relative scale a 50k one
    does, which is the whole reason chat generalises to Tier C."""
    series = [(float(t), float(v)) for t, v in (vod.chat_density or [])
              if isinstance(t, (int, float))]
    if not series:
        return 0.0
    vals = sorted(v for _, v in series)
    med = vals[len(vals) // 2] or 1.0
    inside = [v for t, v in series if start - 30 <= t <= end + 30]
    return (max(inside) / med) if inside else 0.0


def _spread(picks: list, k: int, min_gap: float) -> list:
    """Take the best k that are at least min_gap apart. Ranked input."""
    out = []
    for m in picks:
        if all(abs(m.start - o.start) >= min_gap for o in out):
            out.append(m)
        if len(out) == k:
            break
    return out


def fusion_picks(vod: Vod, lo: float, hi: float, k: int, cfg: dict,
                 w_loud: float = 0.0, w_chat: float = 0.0,
                 min_gap: float = 90.0, log=lambda *_: None
                 ) -> list[tuple[float, float]]:
    """LLM candidates re-ranked with the signals the model can't hear.

    The scorer's RECALL of crowd moments is what the harness measures, and it
    was losing to a loudness argmax. Two readings are possible: the model
    finds the wrong moments, or it finds reasonable moments and ranks them
    badly. Fusion tests the second — same candidates, different order.
    """
    moments = llm_moments(vod, lo, hi, cfg, log)
    if not moments:
        return []
    for m in moments:
        m.combined = (m.score
                      + w_loud * 10.0 * _loudness_at(vod, m.start, m.end)
                      + w_chat * min(_chat_at(vod, m.start, m.end), 5.0))
    ranked = sorted(moments, key=lambda m: m.combined, reverse=True)
    return [(m.start, m.end) for m in _spread(ranked, k, min_gap)]


# ------------------------------------------------- generate-then-judge (v2)


def judged_candidates(vod: Vod, lo: float, hi: float, cfg: dict,
                      log=lambda *_: None) -> list[dict]:
    """Cheap high-recall pool + LLM judgement, cached like llm_moments.

    Cached on a hash of the judge SYSTEM PROMPT, so editing the prompt
    re-runs and editing `rank_judged` (pure code) does not.
    """
    import hashlib

    from clipfarm import generate

    llm = cfg["llm"]
    words = [w for w in vod.words if lo <= w.start < hi]
    if not words:
        return []
    jh = hashlib.sha256(
        (generate.JUDGE_SYS + json.dumps(generate.JUDGE_SCHEMA)).encode()
    ).hexdigest()[:12]
    path = CACHE / (f"judge_{vod.vid}_{lo:.0f}-{hi:.0f}_{jh}"
                    f"_{llm['model']}.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    cands = generate.candidates(vod.words, vod.profile,
                               {"density": vod.chat_density}, lo, hi)
    if not cands:
        return []
    generate.judge(cands, vod.words, llm["model"],
                   base_url=llm.get("base_url"),
                   api_key_env=llm.get("api_key_env"),
                   fallback_models=llm.get("fallback_models"),
                   streamer=cfg.get("streamer_name", "the streamer"),
                   reasoning_effort=llm.get("reasoning_effort"), log=log)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cands))
    tmp.replace(path)
    return cands


def judge_picks(vod: Vod, lo: float, hi: float, k: int, cfg: dict,
                log=lambda *_: None, **rank_kw) -> list[tuple[float, float]]:
    from clipfarm import generate
    cands = judged_candidates(vod, lo, hi, cfg, log)
    picks = generate.rank_judged(cands, k, **rank_kw)
    return [(c["start"], c["end"]) for c in picks]


# ---------------------------------------------------------------- run


def fmt(row: dict) -> str:
    return (f"recall {row['recall']:.2f}  prec {row['precision']:.2f}  "
            f"sw {row['sw_recall']:.2f}  rank {row['rank_corr']:+.2f}")


def mean(rows: list[dict], key: str) -> float:
    vals = [r[key] for r in rows if r]
    return sum(vals) / len(vals) if vals else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--slice-minutes", type=float, default=60.0)
    ap.add_argument("--max-usd", type=float, default=2.00,
                    help="hard ceiling; the sweep ABORTS when exceeded")
    ap.add_argument("--baselines-only", action="store_true",
                    help="no LLM calls at all — free")
    ap.add_argument("--label", default="", help="recorded in bench/runs.jsonl")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    cfg = load_config()
    vids = corpus(args.set)
    if not vids:
        print("no cached VODs with transcript + twitch_clips.json", file=sys.stderr)
        return 1

    print(f"set={args.set}  {len(vids)} VODs  k={args.k}  "
          f"slice={args.slice_minutes:.0f}min  cap=${args.max_usd:.2f}")
    if args.baselines_only:
        print("baselines only — no LLM calls, no spend")
    print()

    usage.reset()
    started = time.time()
    # Fusion variants share the LLM cache with "llm", so adding one to this
    # dict costs nothing after the first sweep.
    variants = {
        "fuse_loud": dict(w_loud=1.0, w_chat=0.0),
        "fuse_chat": dict(w_loud=0.0, w_chat=1.0),
        "fuse_both": dict(w_loud=1.0, w_chat=0.5),
        "fuse_loud2": dict(w_loud=2.0, w_chat=0.0),
    }
    rows = {k: [] for k in
            ["llm", *variants, "judge", "loud", "chat", "rand"]}
    aborted = False

    for vid in vids:
        vod = load_vod(vid)
        if not vod or not vod.clusters:
            print(f"  {vid}  (skipped: no clusters)")
            continue
        lo, hi, inside = pick_slice(vod, args.slice_minutes)
        if len(inside) < 2:
            print(f"  {vid}  (skipped: {len(inside)} clusters in slice)")
            continue

        b = {
            "loud": baseline_loudness(vod, lo, hi, args.k),
            "chat": baseline_chat(vod, lo, hi, args.k),
            "rand": baseline_random(lo, hi, args.k, args.seed + int(vid[-4:])),
        }
        for name, picks in b.items():
            if picks:
                rows[name].append(score_picks(picks, inside, args.k))

        line = f"  {vid}  slice {lo/60:5.0f}-{hi/60:4.0f}min  {len(inside)} clusters"
        if not args.baselines_only:
            spent_before = spend_usd(usage.snapshot())
            if spent_before >= args.max_usd:
                print(f"\nABORT: ${spent_before:.2f} reached the ${args.max_usd:.2f} cap")
                aborted = True
                break
            picks = llm_picks(vod, lo, hi, args.k, cfg)
            if picks:
                r = score_picks(picks, inside, args.k)
                rows["llm"].append(r)
                line += f"  | LLM {fmt(r)}"
            for name, kw in variants.items():
                fp = fusion_picks(vod, lo, hi, args.k, cfg, **kw)
                if fp:
                    rows[name].append(score_picks(fp, inside, args.k))
            jp = judge_picks(vod, lo, hi, args.k, cfg)
            if jp:
                r = score_picks(jp, inside, args.k)
                rows["judge"].append(r)
                line += f"  | JUDGE {fmt(r)}"
            line += f"  ${spend_usd(usage.snapshot()):.3f}"
        print(line)

    spent = spend_usd(usage.snapshot())
    print(f"\n{args.set.upper()} SET  ({len(rows['llm']) or len(rows['loud'])} VODs scored)")
    order = ([k for k in rows] if not args.baselines_only
             else ["loud", "chat", "rand"])
    names = {"llm": "LLM (ours)", "loud": "baseline loudness",
             "chat": "baseline chat", "rand": "baseline random",
             "fuse_loud": "fusion +loud", "fuse_chat": "fusion +chat",
             "fuse_both": "fusion +both", "fuse_loud2": "fusion +loud x2", "judge": "GENERATE+JUDGE (v2)"}
    for key in order:
        if not rows[key]:
            continue
        print(f"  {names[key]:20s} recall@{args.k} {mean(rows[key],'recall'):.3f}"
              f"   prec {mean(rows[key],'precision'):.3f}"
              f"   sw-recall {mean(rows[key],'sw_recall'):.3f}"
              f"   rank {mean(rows[key],'rank_corr'):+.3f}")

    if rows["llm"] and rows["loud"]:
        d = mean(rows["llm"], "recall") - mean(rows["loud"], "recall")
        verdict = "BEATS" if d > 0 else "DOES NOT BEAT"
        print(f"\n  => the LLM {verdict} loudness-peak picking "
              f"({d:+.3f} recall). If it does not, it is not earning its cost.")

    print(f"\n  cost ${spent:.3f}   {time.time()-started:.0f}s"
          f"{'   [ABORTED ON BUDGET]' if aborted else ''}")
    print("  NOTE: heavy-crowd VODs are BIG streamers; the customer is Tier C. "
          "This extrapolates.")

    BENCH.mkdir(exist_ok=True)
    with (BENCH / "runs.jsonl").open("a") as fh:
        fh.write(json.dumps({
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "label": args.label, "set": args.set, "k": args.k,
            "slice_minutes": args.slice_minutes,
            "prompt_hash": detect.prompt_fingerprint(),
            "results": {k: {m: mean(v, m) for m in
                            ("recall", "precision", "sw_recall", "rank_corr")}
                        for k, v in rows.items() if v},
            "cost_usd": round(spent, 4), "aborted": aborted,
            "usage": usage.snapshot(),
        }) + "\n")
    print(f"  appended to {(BENCH / 'runs.jsonl').relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
