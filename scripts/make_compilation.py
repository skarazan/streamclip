"""Build one long-form 16:9 compilation locally, scored on the Claude CLI.

    python scripts/make_compilation.py --channel caseoh_ --clips 15 \
        --title "CaseOh's Funniest Moments"

Local only — this does not touch Modal, Supabase or R2. Selection runs through
the `claude-code` rung, which uses the founder's Claude subscription, so the
LLM cost is $0; the only spend is Groq transcription for VODs not already
cached in work/ (~$0.13 each).

`compile.compile_video` calls `load_config()` with no argument, so it would
otherwise pick up config.yaml's gpt-5-mini. This runner overrides the model
(and nothing else) for the duration of the run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipfarm import compile as compile_mod  # noqa: E402
from clipfarm import usage  # noqa: E402
from clipfarm.config import free_gb, load_config  # noqa: E402
from scripts.selection_bench import PRICES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channel", default="caseoh_")
    ap.add_argument("--clips", type=int, default=15)
    ap.add_argument("--streams", type=int, default=4,
                    help="how many recent VODs to draw moments from")
    ap.add_argument("--title", default="CaseOh's Funniest Moments")
    ap.add_argument("--model", default="claude-code:haiku",
                    help="'claude-code:<model>' runs on the Claude "
                         "subscription via the CLI — no API spend")
    ap.add_argument("--min-free-gb", type=float, default=4.0)
    args = ap.parse_args()

    have = free_gb()
    if have < args.min_free_gb:
        print(f"only {have:.1f} GB free, need {args.min_free_gb:.1f} — a "
              f"compilation downloads ~1 GB of 1080p segments. Free space "
              f"first (work/ caches are safe to keep, out/ is not needed).",
              file=sys.stderr)
        return 1

    base = load_config()
    llm = {**base["llm"], "model": args.model}
    if args.model.startswith("claude-code"):
        llm["reasoning_effort"] = None      # the CLI rung has no such knob
        # If the Claude subscription limit runs out mid-run, the configured
        # chain is Gemini (at quota) -> Gemini (at quota) -> Groq (429s), so
        # the job would die rather than degrade. Put the paid API first so it
        # falls back to something that actually answers.
        llm["fallback_models"] = ["gpt-5-mini"] + [
            m for m in (llm.get("fallback_models") or [])
            if not m.startswith("claude-code")]
    base["llm"] = llm

    def patched(path: str | None = None) -> dict:
        return {**base}

    compile_mod.load_config = patched          # only for this process

    # CLIP_LEN is 60s, so target minutes == clip count.
    target_min = float(args.clips) * compile_mod.CLIP_LEN / 60.0
    print(f"channel   {args.channel}")
    print(f"clips     {args.clips}  (~{target_min:.0f} min finished, 1920x1080)")
    print(f"scorer    {args.model}  -> $0 LLM (Claude subscription)")
    print(f"streams   last {args.streams} VODs")
    print(f"disk      {have:.1f} GB free\n")

    usage.reset()
    try:
        result = compile_mod.compile_video(
            channel=args.channel,
            title=args.title,
            streams=args.streams,
            target_min=target_min,
        )
    finally:
        snap = usage.snapshot()
        if snap:
            print("\nAPI usage this run:")
            for model, e in snap.items():
                if model.startswith("claude-code"):
                    print(f"  {model:26s} {e.get('calls',0)} calls  "
                          f"$0 (Claude subscription)")
                elif "whisper" in model:
                    hrs = e.get("audio_seconds", 0) / 3600
                    print(f"  {model:26s} {hrs:.1f}h audio  "
                          f"~${hrs * 0.04:.2f}")
                else:
                    p = PRICES.get(model)
                    cost = ((e.get("input_tokens", 0) * p["in"]
                             + e.get("cached_input_tokens", 0) * p["cached"]
                             + e.get("output_tokens", 0) * p["out"]) / 1e6
                            ) if p else 0.0
                    note = "  <- fell back off the Claude CLI" if (
                        args.model.startswith("claude-code")
                        and model == "gpt-5-mini") else ""
                    print(f"  {model:26s} {e.get('calls',0)} calls  "
                          f"~${cost:.3f}{note}")
    out = result.get("file") if isinstance(result, dict) else result
    print(f"\nDONE -> {out}")
    print(f"       {free_gb():.1f} GB free after")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
