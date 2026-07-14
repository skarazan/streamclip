"""Crowd ground truth: Twitch viewer-created clips as the humor judgment.

Viewers press the clip button live — each clip is a human marking "worth
showing someone" at a VOD offset. Clustered, that beats any LLM humor score
(see research/clip-quality-spec.md §4). All Helix calls use a free app
access token; the endpoint returns clips pre-sorted by view_count.
"""

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

HELIX = "https://api.twitch.tv/helix"
_token_cache: dict = {}


def _app_token() -> str:
    if _token_cache.get("exp", 0) > time.time() + 60:
        return _token_cache["tok"]
    r = httpx.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": os.environ["TWITCH_CLIENT_ID"],
        "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
        "grant_type": "client_credentials"}, timeout=20)
    r.raise_for_status()
    d = r.json()
    _token_cache.update(tok=d["access_token"],
                        exp=time.time() + d.get("expires_in", 3600))
    return _token_cache["tok"]


def _hx(path: str, params: dict) -> dict:
    r = httpx.get(f"{HELIX}/{path}", params=params, timeout=20, headers={
        "Client-Id": os.environ["TWITCH_CLIENT_ID"],
        "Authorization": f"Bearer {_app_token()}"})
    r.raise_for_status()
    return r.json()


def _parse_dur(s: str) -> int:
    """Helix duration '6h20m30s' -> seconds."""
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", s or "")
    h, mn, sec = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mn * 60 + sec


@dataclass
class CrowdMoment:
    start: float            # earliest clip start in cluster (VOD seconds)
    end: float              # latest clip end
    median_start: float     # crowd's consensus on where the setup begins
    clippers: int           # distinct humans who clipped this
    clip_count: int
    views: int
    featured: bool = False
    titles: list = field(default_factory=list)

    @property
    def strength(self) -> float:
        # distinct humans dominate; views confirm but can't drown (log);
        # a streamer/editor featuring it is an explicit human endorsement
        return (self.clippers + 2.0 * math.log10(1 + self.views)
                + (3.0 if self.featured else 0.0))


def fetch_vod_clips(vod_url: str, cache: Path | None = None) -> list[dict]:
    """All viewer clips of one VOD: [{offset, duration, views, creator,
    title, featured}], offset in VOD seconds."""
    if cache and cache.exists():
        return json.loads(cache.read_text())
    vid = vod_url.rstrip("/").rsplit("/", 1)[-1]
    v = _hx("videos", {"id": vid})["data"][0]
    dur = _parse_dur(v["duration"])
    import datetime as dt
    t0 = dt.datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
    t1 = t0 + dt.timedelta(seconds=dur + 600)

    clips, cursor = [], None
    for _ in range(40):  # 40 pages x 100 = plenty; big channels cap ~1k/window
        params = {"broadcaster_id": v["user_id"], "first": 100,
                  "started_at": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "ended_at": t1.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if cursor:
            params["after"] = cursor
        d = _hx("clips", params)
        for c in d.get("data", []):
            # only clips of THIS vod with a backfilled offset are usable
            if c.get("video_id") == vid and c.get("vod_offset") is not None:
                clips.append({"offset": float(c["vod_offset"]),
                              "duration": float(c.get("duration") or 30.0),
                              "views": int(c.get("view_count") or 0),
                              "creator": c.get("creator_id") or "",
                              "title": c.get("title") or "",
                              "featured": bool(c.get("is_featured"))})
        cursor = (d.get("pagination") or {}).get("cursor")
        if not cursor:
            break
    clips.sort(key=lambda c: c["offset"])
    if cache:
        tmp = cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(clips))
        tmp.replace(cache)
    return clips


def cluster_moments(clips: list[dict], gap: float = 45.0,
                    min_clippers: int = 2) -> list[CrowdMoment]:
    """1000 people clip the same beat seconds apart — the pile-up IS the
    signal. Clips whose offsets sit within `gap` seconds merge into one
    moment; strength = distinct clippers + log(views) (+featured bonus)."""
    moments: list[CrowdMoment] = []
    if not clips:
        return moments
    bucket: list[dict] = [clips[0]]
    for c in clips[1:]:
        if c["offset"] - bucket[-1]["offset"] <= gap:
            bucket.append(c)
        else:
            moments.append(_finish(bucket))
            bucket = [c]
    moments.append(_finish(bucket))
    keep = [m for m in moments if m.clippers >= min_clippers]
    keep.sort(key=lambda m: m.strength, reverse=True)
    return keep


def _finish(bucket: list[dict]) -> CrowdMoment:
    starts = sorted(c["offset"] for c in bucket)
    return CrowdMoment(
        start=starts[0],
        end=max(c["offset"] + c["duration"] for c in bucket),
        median_start=starts[len(starts) // 2],
        clippers=len({c["creator"] for c in bucket if c["creator"]}) or len(bucket),
        clip_count=len(bucket),
        views=sum(c["views"] for c in bucket),
        featured=any(c["featured"] for c in bucket),
        titles=[c["title"] for c in sorted(bucket, key=lambda x: -x["views"])[:3]],
    )
