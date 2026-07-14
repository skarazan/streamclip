"""Regression gate: how well does our selector agree with the crowd?

For a VOD with rich viewer-clip ground truth, measure what fraction of the
crowd's top-N moments our scored pool would surface. No LLM judges itself —
the crowd is the referee (research/clip-quality-spec.md §4).

Usage:
  python -m benchmark.crowd_overlap <vod_id> [--moments work/<id>/moments.X.json] [--top 10]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipfarm import crowd  # noqa: E402


def overlap(vod_id: str, moments_path: Path, top: int = 10,
            tol: float = 60.0) -> dict:
    clips = crowd.fetch_vod_clips(
        f"https://www.twitch.tv/videos/{vod_id}",
        cache=Path("work") / vod_id / "twitch_clips.json")
    truth = crowd.cluster_moments(clips)[:top]
    pool = json.loads(moments_path.read_text())
    pool.sort(key=lambda m: -m.get("score", 0))

    hits, misses = [], []
    for t in truth:
        m = next((m for m in pool
                  if abs(m["start"] - t.median_start) <= tol
                  or m["start"] <= t.median_start <= m["end"]), None)
        (hits if m else misses).append((t, m))
    top3 = pool[:3]
    top3_backed = sum(1 for m in top3 if any(
        abs(m["start"] - t.median_start) <= tol
        or m["start"] <= t.median_start <= m["end"]
        for t in truth))
    return {"truth": truth, "hits": hits, "misses": misses,
            "recall": len(hits) / max(len(truth), 1),
            "top3_backed": top3_backed, "pool_size": len(pool)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("vod_id")
    ap.add_argument("--moments", default=None)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    mp = Path(a.moments) if a.moments else next(
        Path(f"work/{a.vod_id}").glob("moments.*.json"))
    r = overlap(a.vod_id, mp, a.top)
    print(f"pool: {mp.name} ({r['pool_size']} moments)")
    print(f"crowd-top{a.top} recall: {r['recall']:.0%}  "
          f"| our top-3 crowd-backed: {r['top3_backed']}/3")
    for t, m in r["hits"]:
        print(f"  HIT  [{int(t.median_start)}s] {t.clippers} clippers "
              f"-> ours: {m['title'][:60]}")
    for t, _ in r["misses"]:
        print(f"  MISS [{int(t.median_start)}s] {t.clippers} clippers, "
              f"{t.views} views: \"{(t.titles or [''])[0][:60]}\"")
