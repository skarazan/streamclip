import argparse

from .config import load_config
from .pipeline import clean_work, run


def main() -> None:
    p = argparse.ArgumentParser(
        prog="clipfarm",
        description="Auto-clip Twitch VODs into captioned YouTube Shorts.")
    p.add_argument("command", choices=["run", "clean"],
                   help="run = full pipeline on latest VOD; clean = clear work dir")
    p.add_argument("--vod", help="specific VOD URL instead of latest")
    p.add_argument("--clips", type=int, metavar="N",
                   help="number of shorts to produce (overrides config)")
    p.add_argument("--ai-clips", type=int, metavar="M", default=None,
                   help="A/B test: make M of the clips purely AI-chosen "
                        "(whole-VOD LLM scoring), the rest crowd-chosen")
    p.add_argument("--config", help="path to config.yaml")
    args = p.parse_args()

    if args.command == "clean":
        clean_work()
        return
    cfg = load_config(args.config)
    if args.clips:
        cfg["clips"]["count"] = max(1, args.clips)
    if args.ai_clips is not None:
        cfg["clips"]["ai_count"] = max(0, args.ai_clips)
    run(cfg, vod_url=args.vod)


if __name__ == "__main__":
    main()
