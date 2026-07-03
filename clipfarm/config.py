import shutil
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")


def ffmpeg_path() -> str:
    """Prefer ffmpeg-full (has libass for captions) over the stripped brew build."""
    return str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


def load_env() -> None:
    """Load KEY=value lines from project .env into the environment."""
    import os
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def load_config(path: str | None = None) -> dict:
    load_env()
    cfg_path = Path(path) if path else PROJECT_ROOT / "config.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def free_gb(path: Path = PROJECT_ROOT) -> float:
    return shutil.disk_usage(path).free / 1e9


def check_disk(cfg: dict) -> None:
    need = cfg["safety"]["min_free_gb"]
    have = free_gb()
    if have < need:
        raise SystemExit(
            f"Only {have:.1f} GB free disk (need {need} GB). "
            "Free up space before running — clipfarm downloads audio + video segments."
        )
