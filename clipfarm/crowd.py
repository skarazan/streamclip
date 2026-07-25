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
    anchor_start: float     # local mode of clip STARTS (never the payoff)
    clippers: int           # distinct humans who clipped this
    clip_count: int
    views: int
    featured: bool = False
    titles: list = field(default_factory=list)

    @property
    def median_start(self) -> float:
        """Compatibility alias for old callers/caches.

        Twitch defines ``vod_offset`` as the start of the published clip.  It
        is useful evidence for locating the setup, but it is not the time at
        which the viewer pressed the button and must never be protected as a
        payoff timestamp.
        """
        return self.anchor_start

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
                              "id": c.get("id") or "",
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


def _dedupe(clips: list[dict], same_creator_s: float = 6.0) -> list[dict]:
    """Remove API duplicates and repeated votes by one creator.

    Helix occasionally returns the same record twice, and one person may make
    several almost-identical clips.  Distinct humans are the ground truth, so
    one creator gets at most one vote inside a six-second start neighborhood.
    """
    exact, clean = set(), []
    last_by_creator: dict[str, float] = {}
    for c in sorted(clips, key=lambda x: (float(x["offset"]),
                                          str(x.get("id") or ""))):
        key = (c.get("id") or "", float(c["offset"]),
               round(float(c.get("duration") or 30.0), 1),
               c.get("creator") or "", c.get("title") or "")
        # Old caches have no ID, so the remaining fields form the identity.
        exact_key = key if key[0] else key[1:]
        if exact_key in exact:
            continue
        exact.add(exact_key)
        creator = c.get("creator") or ""
        off = float(c["offset"])
        if creator and off - last_by_creator.get(creator, -1e9) <= same_creator_s:
            continue
        if creator:
            last_by_creator[creator] = off
        clean.append(c)
    return clean


def _start_modes(clips: list[dict], sigma_s: float = 6.0,
                 min_separation_s: float = 18.0,
                 assign_radius_s: float = 15.0) -> list[list[dict]]:
    """Find bounded local modes of Twitch clip starts.

    This deliberately is *not* single-link clustering or DBSCAN: both can
    chain A->B->C into a several-minute "moment" even when A and C are far
    apart.  A clip is assigned directly to a density peak and membership is
    capped by ``assign_radius_s``; other members cannot pull it farther away.
    """
    import numpy as np

    if not clips:
        return []
    lo = int(min(float(c["offset"]) for c in clips)) - 1
    hi = int(max(float(c["offset"]) for c in clips)) + 2
    impulses = np.zeros(max(3, hi - lo + 1), dtype=np.float32)
    for c in clips:
        i = int(round(float(c["offset"]))) - lo
        # Views only corroborate; one viral clip must not replace humans.
        views = max(0, int(c.get("views") or 0))
        weight = 1.0 + min(0.35, 0.08 * math.log10(1 + views))
        if c.get("featured"):
            weight += 0.35
        impulses[max(0, min(len(impulses) - 1, i))] += weight
    radius = max(2, int(round(4 * sigma_s)))
    xs = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (xs / max(sigma_s, 0.5)) ** 2)
    # NumPy's ``same`` returns max(len(signal), len(kernel)); for a tight
    # cluster the kernel can be longer, shifting the coordinate system and
    # leaving every vote outside its own assignment radius. Slice ``full``
    # explicitly so density always shares the impulse timeline.
    full = np.convolve(impulses, kernel, mode="full")
    center = (len(kernel) - 1) // 2
    density = full[center:center + len(impulses)]
    candidates = [
        i for i in range(1, len(density) - 1)
        if density[i] >= density[i - 1] and density[i] > density[i + 1]
    ]
    # Non-max suppression chooses independent modes, not transitive chains.
    chosen: list[int] = []
    for i in sorted(candidates, key=lambda j: float(density[j]), reverse=True):
        if all(abs(i - j) >= min_separation_s for j in chosen):
            chosen.append(i)
    if not chosen:
        chosen = [int(np.argmax(density))]

    buckets: dict[int, list[dict]] = {i: [] for i in chosen}
    for c in clips:
        p = float(c["offset"]) - lo
        nearest = min(chosen, key=lambda i: abs(p - i))
        if abs(p - nearest) <= assign_radius_s:
            buckets[nearest].append(c)
    return [buckets[i] for i in sorted(buckets) if buckets[i]]


def cluster_moments(clips: list[dict], gap: float = 45.0,
                    min_clippers: int = 2) -> list[CrowdMoment]:
    """Turn viewer clips into bounded, independent moment candidates.

    ``gap`` remains in the signature for API compatibility but is no longer
    used as a single-link merge threshold.  Starts are separated into local
    density modes with a hard diameter, preventing the multi-minute chaining
    that previously conflated unrelated jokes and jumpscares.
    """
    del gap
    clean = _dedupe(clips)
    moments = [_finish(bucket) for bucket in _start_modes(clean)]
    keep = [m for m in moments if m.clippers >= min_clippers]
    keep.sort(key=lambda m: m.strength, reverse=True)
    return keep


def _finish(bucket: list[dict]) -> CrowdMoment:
    starts = sorted(c["offset"] for c in bucket)
    # Local-mode membership has a <=30s diameter.  Median is robust to a
    # residual outlier and accurately describes start evidence, not payoff.
    anchor = float(starts[len(starts) // 2])
    return CrowdMoment(
        start=starts[0],
        end=max(c["offset"] + c["duration"] for c in bucket),
        anchor_start=anchor,
        clippers=len({c["creator"] for c in bucket if c["creator"]}) or len(bucket),
        clip_count=len(bucket),
        views=sum(c["views"] for c in bucket),
        featured=any(c["featured"] for c in bucket),
        titles=[c["title"] for c in sorted(bucket, key=lambda x: -x["views"])[:3]],
    )
