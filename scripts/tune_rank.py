"""Sweep `generate.rank_judged` weights over CACHED judgements. Costs nothing.

The judge call is the expensive part and its output is cached by
scripts/selection_bench.py. Everything after it — how the reported facts turn
into five picks — is arithmetic, so it can be swept exhaustively instead of
guessed at.

    python scripts/tune_rank.py --k 5

Prints the leaderboard and, for the winner, the same recall the harness would
report. Weights that win here still have to survive the holdout set.
"""

from __future__ import annotations

import argparse
import glob
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import selection_bench as sb  # noqa: E402

from clipfarm import generate  # noqa: E402


def load_cached(which: str) -> list[tuple]:
    """(vod, lo, hi, clusters, judged_candidates) for every cached slice."""
    want = set(sb.corpus(which))
    out = []
    for p in sorted(glob.glob(str(sb.BENCH / "cache" / "judge_*.json"))):
        vid = Path(p).name.split("_")[1]
        if vid not in want:
            continue
        vod = sb.load_vod(vid)
        if not vod:
            continue
        lo, hi, inside = sb.pick_slice(vod, 60.0)
        cands = json.loads(Path(p).read_text())
        if cands and inside:
            out.append((vod, lo, hi, inside, cands))
    return out


def evaluate(data, k, **kw) -> float:
    rs = []
    for _vod, _lo, _hi, inside, cands in data:
        picks = generate.rank_judged(cands, k, **kw)
        rs.append(sb.score_picks([(c["start"], c["end"]) for c in picks],
                                 inside, k)["recall"])
    return sum(rs) / len(rs) if rs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    data = load_cached(args.set)
    if not data:
        print("no cached judgements — run selection_bench.py first",
              file=sys.stderr)
        return 1
    print(f"{len(data)} cached slices from the {args.set} set\n")

    results = []
    for gap, frac in itertools.product((45.0, 60.0, 90.0, 120.0),
                                       (0.2, 0.4, 0.6, 1.0)):
        r = evaluate(data, args.k, min_gap=gap, allow_game_frac=frac)
        results.append((r, gap, frac))
    results.sort(reverse=True)
    print("  recall   min_gap  game_frac")
    for r, gap, frac in results[:10]:
        print(f"  {r:.3f}    {gap:5.0f}    {frac:.1f}")
    best = results[0]
    print(f"\nbest: recall {best[0]:.3f} at min_gap={best[1]:.0f} "
          f"allow_game_frac={best[2]:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
