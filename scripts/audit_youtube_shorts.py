#!/usr/bin/env python3
"""Create a reproducible public-metadata audit for a YouTube Shorts channel.

Public metadata cannot identify retention drops or prove whether packaging
caused an outcome. It can still replace hand-copied anecdotes with a complete,
dated snapshot and expose duration/title associations worth testing with the
private YouTube Analytics API later.

Examples:
    python scripts/audit_youtube_shorts.py --channel @CheeseDipClips
    python scripts/audit_youtube_shorts.py --input metadata.jsonl
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


PAYOFF_WORDS = re.compile(
    r"\b(goal|scores?|wins?|diamond|world cup|doctor|hacked|leaked|"
    r"jumpscared?|panicked|catches?|fails?|shoots?|hunts?|eats?|"
    r"saves?|killed?|broke|crashes?|snaps?|loses?|wrong)\b",
    re.I,
)
WITHHOLDING_WORDS = re.compile(
    r"\b(this|that|what happened|wait for|reaction|reacts?|crazy|"
    r"unexpected|you won.t believe|not ready)\b|\?{2,}",
    re.I,
)


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("id"):
            rows.append(item)
    return rows


def _fetch(channel: str, limit: int) -> list[dict]:
    url = channel if channel.startswith("http") else (
        f"https://www.youtube.com/{channel}/shorts")
    with tempfile.NamedTemporaryFile(suffix=".jsonl") as tmp:
        cmd = [
            sys.executable, "-m", "yt_dlp", "--skip-download",
            "--ignore-errors", "--dump-json", "--playlist-end", str(limit),
            url,
        ]
        result = subprocess.run(cmd, stdout=tmp, stderr=subprocess.PIPE,
                                text=True)
        tmp.flush()
        rows = _load_jsonl(Path(tmp.name))
    if not rows:
        detail = (result.stderr or "no metadata returned")[-800:]
        raise SystemExit(f"YouTube metadata fetch failed: {detail}")
    return rows


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + j - 1) / 2 + 1
        for k in order[i:j]:
            ranks[k] = rank
        i = j
    return ranks


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3 or len(a) != len(b):
        return None
    am, bm = statistics.mean(a), statistics.mean(b)
    num = sum((x - am) * (y - bm) for x, y in zip(a, b))
    den = math.sqrt(sum((x - am) ** 2 for x in a)
                    * sum((y - bm) ** 2 for y in b))
    return num / den if den else None


def spearman(a: list[float], b: list[float]) -> float | None:
    """Tie-aware Spearman correlation used by the generated report."""
    return _pearson(_rank(a), _rank(b))


def duration_bucket(seconds: int | float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = float(seconds)
    if seconds < 10:
        return "0-9s"
    if seconds < 15:
        return "10-14s"
    if seconds < 20:
        return "15-19s"
    if seconds < 30:
        return "20-29s"
    return "30-60s"


def title_features(title: str) -> dict:
    clean = re.sub(r"#\w+", "", title or "").strip()
    words = re.findall(r"[A-Za-z0-9$]+", clean)
    alpha = [word for word in words if any(c.isalpha() for c in word)]
    caps = [word for word in alpha if len(word) > 1 and word.isupper()]
    return {
        "title_chars": len(clean),
        "title_words": len(words),
        "caps_share": round(len(caps) / max(1, len(alpha)), 4),
        "question": "?" in clean,
        "payoff_named": bool(PAYOFF_WORDS.search(clean)),
        "withholding": bool(WITHHOLDING_WORDS.search(clean)),
    }


def normalize(rows: list[dict], as_of: dt.date) -> list[dict]:
    normalized = []
    seen = set()
    for item in rows:
        video_id = str(item.get("id") or "")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        upload = item.get("upload_date")
        try:
            published = dt.datetime.strptime(str(upload), "%Y%m%d").date()
        except (TypeError, ValueError):
            published = None
        age = (as_of - published).days if published else None
        title = str(item.get("title") or "").strip()
        duration = item.get("duration")
        view_count = item.get("view_count")
        row = {
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
            "published": published.isoformat() if published else "",
            "age_days": age if age is not None else "",
            "mature_7d": bool(age is not None and age >= 7),
            "title": title,
            "duration_s": int(round(float(duration))) if duration is not None else "",
            "duration_bucket": duration_bucket(duration),
            "views": int(view_count) if view_count is not None else "",
            "likes": int(item["like_count"]) if item.get("like_count") is not None else "",
            "comments": int(item["comment_count"]) if item.get("comment_count") is not None else "",
            **title_features(title),
        }
        if row["views"] != "" and row["likes"] != "":
            row["likes_per_1k_views"] = round(
                1000 * row["likes"] / max(1, row["views"]), 3)
        else:
            row["likes_per_1k_views"] = ""
        normalized.append(row)
    normalized.sort(key=lambda row: (row["published"], row["video_id"]),
                    reverse=True)
    return normalized


def _fmt_int(value: float) -> str:
    return f"{int(round(value)):,}"


def _group_table(rows: list[dict], key: str) -> list[tuple[str, int, int, int]]:
    groups = defaultdict(list)
    for row in rows:
        if row["views"] != "":
            groups[str(row[key])].append(int(row["views"]))
    result = []
    for name, values in groups.items():
        result.append((name, len(values), int(statistics.median(values)),
                       int(statistics.mean(values))))
    return sorted(result)


def _find(rows: list[dict], phrase: str) -> dict | None:
    phrase = phrase.lower()
    return next((row for row in rows if phrase in row["title"].lower()), None)


def render_report(rows: list[dict], as_of: dt.date, channel: str) -> str:
    complete = [row for row in rows if row["views"] != ""
                and row["duration_s"] != ""]
    mature = [row for row in complete if row["mature_7d"]]
    views = [row["views"] for row in mature]
    rho = spearman([float(row["duration_s"]) for row in mature],
                   [math.log1p(float(row["views"])) for row in mature])
    dated = [row for row in mature if row["age_days"] != ""]
    age_rho = spearman(
        [float(row["age_days"]) for row in dated],
        [math.log1p(float(row["views"])) for row in dated],
    )
    lines = [
        "# CheeseDipClips public Shorts outcome audit",
        "",
        f"**Snapshot:** {as_of.isoformat()}",
        f"**Channel:** `{channel}`",
        f"**Videos discovered:** {len(rows)}",
        f"**Complete public rows:** {len(complete)}",
        f"**Mature rows (at least 7 days old):** {len(mature)}",
        "",
        "## What this audit can and cannot answer",
        "",
        "This snapshot replaces the earlier hand-copied winner/flop list with",
        "complete public title, duration, date, view, like, and comment fields.",
        "It can reveal associations and matched examples. It **cannot** identify",
        "retention drops or causally separate moment selection from title, edit,",
        "posting time, audience distribution, or channel growth. Private YouTube",
        "Analytics and source-manifest attribution are still required for that.",
        "",
    ]
    if views:
        lines += [
            "## Mature-public baseline",
            "",
            f"- Median views: **{_fmt_int(statistics.median(views))}**",
            f"- Mean views: **{_fmt_int(statistics.mean(views))}**",
            f"- Duration vs log-views Spearman rho: **{rho:.3f}**"
            if rho is not None else "- Duration correlation: insufficient data",
            f"- Post age vs log-views Spearman rho: **{age_rho:.3f}**"
            if age_rho is not None else "- Post-age correlation: insufficient data",
            "",
            "The correlation is descriptive, not a duration penalty. A good long",
            "clip may outperform a weak short clip; this only tests whether length",
            "is associated with outcomes in this small channel snapshot. Post age",
            "is reported beside it so channel growth/exposure time is visible as a",
            "basic confound rather than silently ignored.",
            "",
        ]

    lines += ["## Views by duration bucket", "",
              "| Duration | N | Median views | Mean views |",
              "|---|---:|---:|---:|"]
    for name, n, median, mean in _group_table(mature, "duration_bucket"):
        lines.append(f"| {name} | {n} | {_fmt_int(median)} | {_fmt_int(mean)} |")

    lines += ["", "## Views by transparent title feature", "",
              "| Feature | N | Median views | Mean views |",
              "|---|---:|---:|---:|"]
    for key, label in (("payoff_named", "Names a concrete outcome"),
                       ("withholding", "Uses withholding/generic tease"),
                       ("question", "Contains a question")):
        for value in (True, False):
            subset = [row for row in mature if row[key] is value]
            vals = [row["views"] for row in subset]
            if vals:
                lines.append(
                    f"| {label}: {str(value).lower()} | {len(vals)} | "
                    f"{_fmt_int(statistics.median(vals))} | "
                    f"{_fmt_int(statistics.mean(vals))} |")
    lines += [
        "",
        "Feature labels come from explicit regexes in",
        "`scripts/audit_youtube_shorts.py`; they are inspectable heuristics, not",
        "an LLM verdict.",
        "",
        "## Highest-view mature Shorts",
        "",
        "| Views | Length | Title |",
        "|---:|---:|---|",
    ]
    for row in sorted(mature, key=lambda r: r["views"], reverse=True)[:10]:
        title = row["title"].replace("|", "\\|")
        lines.append(f"| {_fmt_int(row['views'])} | {row['duration_s']}s | "
                     f"[{title}]({row['url']}) |")

    lines += ["", "## Lowest-view mature Shorts", "",
              "| Views | Length | Title |", "|---:|---:|---|"]
    for row in sorted(mature, key=lambda r: r["views"])[:10]:
        title = row["title"].replace("|", "\\|")
        lines.append(f"| {_fmt_int(row['views'])} | {row['duration_s']}s | "
                     f"[{title}]({row['url']}) |")

    pairs = [
        ("amazing goal", "power shot", "Same creator and game; adjacent days"),
        ("panicked so hard", "summons a tornado", "Same creator and tornado topic"),
    ]
    lines += ["", "## Near-matched examples", ""]
    for winner_phrase, other_phrase, note in pairs:
        a, b = _find(rows, winner_phrase), _find(rows, other_phrase)
        if not a or not b or a["views"] == "" or b["views"] == "":
            continue
        high, low = (a, b) if a["views"] >= b["views"] else (b, a)
        ratio = high["views"] / max(1, low["views"])
        lines += [
            f"- **{ratio:.1f}x gap.** {note}: “{a['title']}” "
            f"({_fmt_int(a['views'])}) vs “{b['title']}” "
            f"({_fmt_int(b['views'])}). This is useful evidence but still not a",
            "  controlled experiment because the underlying moments differ.",
        ]

    lines += [
        "",
        "## Decision",
        "",
        "1. Do not introduce a universal duration penalty from this snapshot.",
        "2. Preserve payoff-forward packaging as a testable hypothesis, not a",
        "   proven cause.",
        "3. Capture keep/discard reasons on every newly shipped clip so moment",
        "   quality and cut quality stop being collapsed into one view count.",
        "4. Add private YouTube Analytics ingestion before using retention as a",
        "   training label. Store `engagedViews`, average view duration/percentage,",
        "   and per-video retention curves against the final edit recipe.",
        "5. Re-run this public snapshot regularly; compare only mature posts and",
        "   keep the raw CSV so every claim is reproducible.",
        "",
    ]
    return "\n".join(lines)


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="@CheeseDipClips")
    parser.add_argument("--input", type=Path,
                        help="Replay yt-dlp JSONL instead of fetching")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--expect-at-least", type=int,
        help=("Fail instead of publishing a suspiciously short snapshot. "
              "Defaults to 60 for @CheeseDipClips and 1 for other channels."),
    )
    parser.add_argument("--as-of", type=dt.date.fromisoformat,
                        default=dt.date.today())
    parser.add_argument("--csv", type=Path,
                        default=Path("research/data/cheesedip-shorts.csv"))
    parser.add_argument("--report", type=Path,
                        default=Path("research/2026-08-19-shorts-outcome-audit.md"))
    args = parser.parse_args()
    raw = _load_jsonl(args.input) if args.input else _fetch(args.channel, args.limit)
    rows = normalize(raw, args.as_of)
    expected = args.expect_at_least
    if expected is None:
        channel_key = args.channel.lower().rstrip("/")
        expected = 60 if channel_key.endswith("cheesedipclips") else 1
    if len(rows) < expected:
        raise SystemExit(
            f"Incomplete YouTube snapshot: expected at least {expected} usable "
            f"Shorts, received {len(rows)}. Refusing to overwrite the audit."
        )
    write_csv(rows, args.csv)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(rows, args.as_of, args.channel),
                           encoding="utf-8")
    print(f"{len(rows)} Shorts -> {args.csv} and {args.report}")


if __name__ == "__main__":
    main()
