"""StreamClip worker: claims jobs from Supabase, runs the clipfarm pipeline,
uploads results to R2, records clips, burns credits.

Runs anywhere Python runs. Env:
  SUPABASE_URL, SUPABASE_SERVICE_KEY          (service key bypasses RLS)
  R2_ENDPOINT, R2_KEY, R2_SECRET, R2_BUCKET
Optional:
  WORKER_ID (default hostname), POLL_SECONDS (default 30)

Local dry run (no cloud, prints what would happen):
  python worker.py --local '{"vod_url": "https://twitch.tv/videos/123", "clips": 2}'
"""

import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipfarm import pipeline  # noqa: E402
from clipfarm import usage  # noqa: E402
from clipfarm.config import load_config  # noqa: E402


def _load_local_env() -> None:
    """Make direct local worker commands self-contained.

    Modal supplies real environment variables, so this is a no-op there.
    Local dashboard runs load the gitignored project .env without requiring a
    human to source it in a terminal first.
    """
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if os.environ.get("SUPABASE_URL") or not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(
            key, value.strip().strip('"').strip("'"))


_load_local_env()

WORKER_ID = os.environ.get("WORKER_ID", socket.gethostname())
POLL = int(os.environ.get("POLL_SECONDS", "30"))


def sb(method: str, path: str, **kwargs) -> httpx.Response:
    url = os.environ["SUPABASE_URL"].rstrip("/") + path
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
    headers.update(kwargs.pop("headers", {}))
    r = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
    r.raise_for_status()
    return r


def requeue_stale(minutes: int = 150) -> None:  # must exceed function timeout
    """Jobs stuck 'running' with no live worker (container killed) go back."""
    import datetime
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sb("PATCH", f"/rest/v1/jobs?status=eq.running&started_at=lt.{cutoff}",
       json={"status": "queued", "worker_id": None, "started_at": None})


def has_ready_job() -> bool:
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = sb("GET", "/rest/v1/jobs?status=eq.queued"
           f"&or=(run_after.is.null,run_after.lte.{now})&select=id&limit=1")
    return bool(r.json())


def has_running_job() -> bool:
    r = sb("GET", "/rest/v1/jobs?status=eq.running&select=id&limit=1")
    return bool(r.json())


def heartbeat(state: str = "idle", detail: str = "") -> None:
    """Publish worker availability without coupling web to worker HTTP."""
    try:
        import datetime
        queued = sb(
            "GET", "/rest/v1/jobs?status=eq.queued&select=id&limit=1000").json()
        sb(
            "POST", "/rest/v1/worker_health?on_conflict=id",
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json={
                "id": WORKER_ID,
                "state": state,
                "queue_depth": len(queued),
                "worker_version": getattr(pipeline, "PIPELINE_VERSION", "unknown"),
                "detail": detail[:240],
                "updated_at": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            },
        )
    except Exception as error:
        print(f"heartbeat warning: {error}")


def claim_job() -> dict | None:
    r = sb("POST", "/rest/v1/rpc/claim_job", json={"p_worker": WORKER_ID})
    rows = r.json()
    return rows[0] if rows else None


def get_user(user_id: str) -> dict:
    return sb("GET", f"/rest/v1/users?id=eq.{user_id}").json()[0]


# Legacy admin marker. `plan` belongs to billing — Stripe rewrites it on
# checkout and cancellation — so admin rights live in `users.is_admin`.
# These plan values stay the fallback until 20260725_admin_flag.sql is applied
# (get_user selects *, so the key is simply absent on the old schema).
LEGACY_ADMIN_PLANS = ("founder", "internal")


def is_admin(user: dict) -> bool:
    if "is_admin" in user:
        return bool(user["is_admin"])
    return user.get("plan") in LEGACY_ADMIN_PLANS


def reserve_job_credits(job: dict, amount: int) -> tuple[bool, int]:
    try:
        rows = sb("POST", "/rest/v1/rpc/reserve_job_credits", json={
            "p_job": job["id"], "p_user": job["user_id"], "p_amount": amount,
        }).json()
        result = rows[0] if rows else {}
        return bool(result.get("ok")), int(result.get("balance") or 0)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 404:
            raise
        # Two-step deployment bridge: the current single local worker must
        # keep operating while the additive RPC migration is applied. Hosted
        # multi-worker production must have the RPC; this fallback is marked
        # on the in-memory job and retains the old success-time charge.
        print(f"atomic credit RPC unavailable, legacy bridge active: {error}")
        current = get_user(job["user_id"])
        balance = int(current.get("credits") or 0)
        if balance >= amount:
            job["_legacy_credit_cost"] = amount
            return True, balance - amount
        return False, balance


def refund_job_credits(job: dict, reason: str = "failed job refund") -> None:
    sb("POST", "/rest/v1/rpc/refund_job_credits", json={
        "p_job": job["id"], "p_user": job["user_id"], "p_reason": reason,
    })


def purge_due_accounts() -> int:
    """Delete R2 objects, then the auth user after the 7-day grace period."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    due = sb(
        "GET", "/rest/v1/users?deletion_requested_at=lte."
        f"{now}&select=id&limit=25").json()
    if not due:
        return 0
    import boto3
    s3 = boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET"])
    removed = 0
    for account in due:
        user_id = account["id"]
        token = None
        while True:
            page = s3.list_objects_v2(
                Bucket=os.environ["R2_BUCKET"],
                Prefix=f"{user_id}/",
                ContinuationToken=token) if token else s3.list_objects_v2(
                    Bucket=os.environ["R2_BUCKET"], Prefix=f"{user_id}/")
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                s3.delete_objects(
                    Bucket=os.environ["R2_BUCKET"],
                    Delete={"Objects": objects, "Quiet": True})
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
        url = (os.environ["SUPABASE_URL"].rstrip("/")
               + f"/auth/v1/admin/users/{user_id}")
        key = os.environ["SUPABASE_SERVICE_KEY"]
        response = httpx.delete(
            url,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=30)
        response.raise_for_status()
        removed += 1
    return removed


def send_ready_notification(user: dict, job: dict, clip_count: int) -> None:
    """Best-effort completion email; processing success never depends on it."""
    if not user.get("notification_email") or not user.get("email"):
        return
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        return
    site = os.environ.get("STREAMCLIP_SITE_URL", "https://streamclip.app")
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={
                "from": os.environ.get(
                    "RESEND_FROM", "StreamClip <clips@streamclip.app>"),
                "to": [user["email"]],
                "subject": f"{clip_count} StreamClip "
                           f"{'clip is' if clip_count == 1 else 'clips are'} ready",
                "html": (
                    f"<h1>Your clips are ready.</h1><p>{clip_count} verified "
                    "clip"
                    f"{'' if clip_count == 1 else 's'} finished processing."
                    f"</p><p><a href=\"{site}/app\">Open your dashboard</a></p>"
                ),
            },
            timeout=20,
        )
        response.raise_for_status()
    except Exception as error:
        print(f"notification warning for {job['id']}: {error}")


def upload_r2(local: Path, key: str) -> None:
    import boto3
    s3 = boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET"])
    s3.upload_file(str(local), os.environ["R2_BUCKET"], key,
                   ExtraArgs={"ContentType": "video/mp4"})


def download_r2(key: str, local: Path) -> Path:
    import boto3
    s3 = boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET"])
    local.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(os.environ["R2_BUCKET"], key, str(local))
    return local


def cached_cam(vod_url: str, segment: Path, fallback=None):
    if fallback:
        return tuple(fallback)
    try:
        import numpy as np
        from clipfarm import facecam
        vod_id = vod_url.rstrip("/").rsplit("/", 1)[-1]
        cam_cache = (Path(__file__).resolve().parent.parent /
                     "work" / vod_id / "cam_box.json")
        cached = json.loads(cam_cache.read_text())
        if cached.get("emb"):
            matched = facecam.match_segment(segment, np.array(cached["emb"]))
            if matched:
                return matched
        if cached.get("pos_box"):
            return tuple(cached["pos_box"])
    except Exception:
        pass
    return None


def get_clip(clip_id: str, user_id: str) -> dict:
    rows = sb("GET", f"/rest/v1/clips?id=eq.{clip_id}&user_id=eq.{user_id}").json()
    if not rows:
        raise RuntimeError("clip not found")
    return rows[0]


def process_clip_source(job: dict) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from clipfarm import fetch, render, transcribe
    p = job.get("progress") or {}
    clip = get_clip(p["clip_id"], job["user_id"])
    user = get_user(job["user_id"])
    cfg = load_config()
    style = cfg["style"]
    for k, v in (user.get("style_profile") or {}).items():
        if isinstance(v, dict) and isinstance(style.get(k), dict):
            style[k].update(v)
        else:
            style[k] = v
    work = Path(__file__).resolve().parent.parent / "work" / "edits" / job["id"]
    work.mkdir(parents=True, exist_ok=True)
    source = fetch.download_segment(
        job["vod_url"], float(p["source_start"]), float(p["source_end"]),
        work / "source_360.mp4", "best[height<=360]")
    cam = cached_cam(job["vod_url"], source, (p.get("recipe") or {}).get("cam"))
    proxy = render.render_editor_proxy(
        source, work / "editor_9x16.mp4", cam=cam,
        top_frac=style.get("split_top", .42),
        crop=style.get("crop", "center"))
    waveform = render.audio_waveform_peaks(source)
    key = f"{job['user_id']}/{clip['id']}/editor/source-{job['id']}.mp4"
    upload_r2(proxy, key)
    ready = {**p, "stage": "done", "proxy_key": key,
             "proxy_version": 3,
             "proxy_width": 360, "proxy_height": 640,
             "waveform": waveform,
             "cam": list(cam) if cam else None,
             "recipe": {
                 **(p.get("recipe") or {}),
                 "cam": list(cam) if cam else None,
             }}
    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}", json={
        "status": "done", "finished_at": "now()",
        "progress": ready,
    })

    # The UI is already usable. Prepare final-export inputs concurrently so
    # pressing Export later does not redownload or retranscribe the segment.
    def prepare_master():
        master = fetch.download_segment(
            job["vod_url"], float(p["source_start"]), float(p["source_end"]),
            work / "source_1080.mp4", cfg["clips"]["quality"])
        master_key = (
            f"{job['user_id']}/{clip['id']}/editor/master-{job['id']}.mp4")
        upload_r2(master, master_key)
        return master_key

    def prepare_words():
        ctx = f"Twitch gaming stream by {user.get('twitch_login', 'a streamer')}."
        try:
            ws = transcribe.transcribe_clips_groq(
                [(source, float(p["source_start"]))], context=ctx)[0]
            return [{"start": w.start, "end": w.end, "text": w.text} for w in ws]
        except Exception:
            return []

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            master_future = pool.submit(prepare_master)
            words_future = pool.submit(prepare_words)
            master_key = master_future.result()
            words = words_future.result()
        ready.update({"master_key": master_key, "transcript": words})
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
           json={"progress": ready})
    except Exception as e:
        ready["cache_warning"] = str(e)[:240]
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
           json={"progress": ready})
    for f in work.glob("*"):
        f.unlink(missing_ok=True)


def process_clip_edit(job: dict) -> None:
    from clipfarm import fetch, quality, render, transcribe
    p = job.get("progress") or {}
    clip = get_clip(p["clip_id"], job["user_id"])
    user = get_user(job["user_id"])
    cfg = load_config()
    style = cfg["style"]
    for k, v in (p.get("style_profile") or user.get("style_profile") or {}).items():
        if isinstance(v, dict) and isinstance(style.get(k), dict):
            style[k].update(v)
        else:
            style[k] = v
    start, end = float(p["source_start"]), float(p["source_end"])
    keep = [[max(start, float(a)), min(end, float(b))]
            for a, b in p["keep_intervals"] if float(b) > float(a)]
    keep = [x for x in keep if x[1] > x[0]]
    if not keep:
        raise RuntimeError("edit removes the entire clip")
    work = Path(__file__).resolve().parent.parent / "work" / "edits" / job["id"]
    work.mkdir(parents=True, exist_ok=True)
    source_job = None
    if p.get("source_job_id"):
        rows = sb("GET", f"/rest/v1/jobs?id=eq.{p['source_job_id']}").json()
        source_job = rows[0] if rows else None
    source_progress = (source_job or {}).get("progress") or {}
    media_start = start
    if source_progress.get("master_key"):
        source = download_r2(
            source_progress["master_key"], work / "source.mp4")
        media_start = float(source_progress["source_start"])
    else:
        source = fetch.download_segment(
            job["vod_url"], start, end, work / "source.mp4",
            cfg["clips"]["quality"])
    if source_progress.get("transcript"):
        words = [transcribe.Word(**w) for w in source_progress["transcript"]
                 if start <= float(w["start"]) < end]
    else:
        ctx = f"Twitch gaming stream by {cfg.get('streamer_name', 'a streamer')}."
        try:
            words = transcribe.transcribe_clips_groq([(source, start)], context=ctx)[0]
        except Exception:
            words = transcribe.transcribe_clips(
                [(source, start)], cfg["transcribe"]["caption_model"],
                cfg["transcribe"]["compute_type"])[0]
    # Final export uses one ffmpeg graph for cuts + layout + captions. The old
    # bounded/cut intermediates encoded the same revision up to three times.
    relative = [(a - media_start, b - media_start) for a, b in keep]
    words = pipeline.detect.remap_words(words, keep)
    ass_start, ass_end = 0.0, sum(b-a for a, b in keep)
    ass = render.build_ass(
        words, ass_start, ass_end, style, work / "captions.ass",
        hook=p.get("hook") or clip.get("hook") or "",
        hook_pos=style.get("split_top", .42))
    cam = cached_cam(job["vod_url"], source, p.get("cam"))
    final = render.render_short(
        source, ass, work / "final.mp4", style.get("crop", "center"),
        cam=cam, top_frac=style.get("split_top", .42),
        opening_effect=style.get("opening_effect", "punch_zoom"),
        keep=relative)
    expected = sum(b-a for a, b in keep)
    qa = quality.inspect_media(
        final, expected_duration=expected, max_duration=90.0)
    if not qa.passed:
        raise RuntimeError("revision QA failed: " + "; ".join(qa.errors))
    key = f"{job['user_id']}/{clip['id']}/revisions/{job['id']}.mp4"
    upload_r2(final, key)
    if not p.get("validation"):
        sb("PATCH", f"/rest/v1/clips?id=eq.{clip['id']}", json={
            "r2_key": key, "start_s": start, "end_s": end,
        })
    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}", json={
        "status": "done", "finished_at": "now()",
        "progress": {**p, "stage": "done", "r2_key": key,
                     "previous_r2_key": clip["r2_key"],
                     "duration": qa.duration},
    })
    for f in work.glob("*"):
        f.unlink(missing_ok=True)


def build_job_config(user: dict, job: dict) -> dict:
    cfg = load_config()
    snapshot = (job.get("progress") or {}).get("settings_snapshot") or {}
    cfg["clips"]["count"] = snapshot.get(
        "clips_per_stream", user.get("clips_per_stream", 3))
    cfg["streamer_name"] = user.get("twitch_login", "the streamer")
    # Jobs use the dashboard template captured when the user pressed Run.
    # Falling back to the live profile keeps old pre-snapshot jobs compatible.
    style_profile = snapshot.get(
        "style_profile", user.get("style_profile") or {})
    for k, v in style_profile.items():
        if isinstance(v, dict) and isinstance(cfg["style"].get(k), dict):
            cfg["style"][k].update(v)
        else:
            cfg["style"][k] = v
    return cfg


def set_progress(job_id: str, stage: str, detail: str = "") -> None:
    import datetime
    try:
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job_id}",
           json={"progress": {"stage": stage, "detail": detail,
                 "at": datetime.datetime.now(datetime.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ")}})
    except Exception:
        pass  # progress is cosmetic; never fail a job over it


# cost guards: a job must be affordable BEFORE any GPU work happens.
# 1 credit covers a VOD up to LONG_VOD_H hours; longer costs 2 (compute is
# roughly linear in VOD length); above MAX_VOD_H we refuse outright.
LONG_VOD_H = float(os.environ.get("LONG_VOD_HOURS", "8"))
MAX_VOD_H = float(os.environ.get("MAX_VOD_HOURS", "16"))


def resolve_auto_vod(job: dict) -> str | None:
    """Resolve an EventSub offline marker after Twitch publishes the archive."""
    if not str(job.get("vod_url", "")).startswith("twitch://latest/"):
        return job.get("vod_url")
    import datetime
    broadcaster_id = job["vod_url"].rsplit("/", 1)[-1]
    client_id = os.environ.get("TWITCH_CLIENT_ID")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Twitch EventSub VOD resolution is not configured")
    token_response = httpx.post(
        "https://id.twitch.tv/oauth2/token",
        params={"client_id": client_id, "client_secret": client_secret,
                "grant_type": "client_credentials"},
        timeout=20)
    token_response.raise_for_status()
    token = token_response.json()["access_token"]
    videos_response = httpx.get(
        "https://api.twitch.tv/helix/videos",
        params={"user_id": broadcaster_id, "type": "archive", "first": 1},
        headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"},
        timeout=20)
    videos_response.raise_for_status()
    video = (videos_response.json().get("data") or [None])[0]
    if video:
        created = datetime.datetime.fromisoformat(
            video["created_at"].replace("Z", "+00:00"))
        queued = datetime.datetime.fromisoformat(
            str(job["created_at"]).replace("Z", "+00:00"))
        if created >= queued - datetime.timedelta(hours=20):
            vod_url = f"https://www.twitch.tv/videos/{video['id']}"
            progress = dict(job.get("progress") or {})
            progress.update({"stage": "queued", "detail": "",
                             "resolved_vod_id": video["id"]})
            sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
               json={"vod_url": vod_url, "progress": progress})
            job["vod_url"] = vod_url
            job["progress"] = progress
            return vod_url
    later = (datetime.datetime.now(datetime.timezone.utc)
             + datetime.timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    progress = dict(job.get("progress") or {})
    progress.update({"stage": "finding_vod",
                     "detail": "Twitch is still publishing the archive"})
    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
       json={"status": "queued", "worker_id": None, "started_at": None,
             "run_after": later, "progress": progress})
    print(f"{job['id']}: Twitch archive not ready, deferred 15min")
    return None


def process(job: dict) -> None:
    # A Modal container is reused across jobs; without this the next job
    # inherits the previous one's token counts.
    usage.reset()
    kind = (job.get("progress") or {}).get("kind")
    if kind == "clip_source":
        process_clip_source(job)
        return
    if kind == "clip_edit":
        process_clip_edit(job)
        return
    if not resolve_auto_vod(job):
        return
    from clipfarm import fetch
    info = {}
    try:
        info = fetch.vod_info(job["vod_url"])
        if info["live"]:
            import datetime
            later = (datetime.datetime.now(datetime.timezone.utc)
                     + datetime.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
            sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
               json={"status": "queued", "worker_id": None, "started_at": None,
                     "run_after": later,
                     "progress": {"stage": "finding_vod",
                                  "detail": "stream is still live — waiting for it to end"}})
            print(f"{job['id']}: VOD still live, deferred 45min")
            return
    except Exception:
        pass  # metadata probe is advisory; proceed if it can't tell

    user = get_user(job["user_id"])

    # own-content rule: the connected Twitch account is the abuse moat AND
    # the clean-IP position — you clip your channel, not someone else's.
    # Admin accounts bypass for cross-streamer testing.
    vod_chan = (info.get("channel") or "").lower()
    own_login = (user.get("twitch_login") or "").lower()
    if (vod_chan and own_login and vod_chan != own_login
            and not is_admin(user)):
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
           json={"status": "failed", "finished_at": "now()",
                 "error": f"VOD belongs to '{vod_chan}', account is '{own_login}'",
                 "progress": {"stage": "failed",
                              "detail": "StreamClip clips your own channel's "
                                        "VODs — this one belongs to another streamer"}})
        print(f"{job['id']}: refused, VOD channel {vod_chan} != {own_login}")
        return

    dur_h = (info.get("duration_s") or 0) / 3600
    if dur_h > MAX_VOD_H:
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
           json={"status": "failed", "finished_at": "now()",
                 "error": f"VOD is {dur_h:.1f}h — the maximum is {MAX_VOD_H:.0f}h",
                 "progress": {"stage": "failed",
                              "detail": f"this VOD is {dur_h:.1f}h long — "
                                        f"we can process up to {MAX_VOD_H:.0f}h"}})
        print(f"{job['id']}: refused, VOD {dur_h:.1f}h > {MAX_VOD_H:.0f}h cap")
        return
    credits_needed = 1 if dur_h <= LONG_VOD_H else 2
    if user.get("credits", 0) < credits_needed:
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
           json={"status": "failed", "finished_at": "now()",
                 "error": "insufficient credits",
                 "progress": {"stage": "failed",
                              "detail": f"not enough gigawatts (this VOD needs "
                                        f"{credits_needed} GW) — top up to keep clipping"}})
        print(f"{job['id']}: refused, {user.get('credits', 0)} GW "
              f"< {credits_needed} needed")
        return
    reserved, balance = reserve_job_credits(job, credits_needed)
    if not reserved:
        sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
           json={"status": "failed", "finished_at": "now()",
                 "error": "insufficient credits",
                 "progress": {"stage": "failed",
                              "version": getattr(
                                  pipeline, "PIPELINE_VERSION", "unknown"),
                              "detail": f"not enough gigawatts — current "
                                        f"balance is {balance} GW"}})
        print(f"{job['id']}: atomic credit reservation refused")
        return

    cfg = build_job_config(user, job)
    processing_started = time.monotonic()
    progress_lock = threading.Lock()
    progress = dict(job.get("progress") or {})
    progress.update({
        "stage": "finding_vod", "detail": "",
        "version": getattr(pipeline, "PIPELINE_VERSION", "unknown"),
        "requested": int(cfg["clips"]["count"]),
        "published": 0, "ready_clip_ids": [],
    })
    stage_started = time.monotonic()
    current_stage = "finding_vod"
    substage_started = stage_started
    current_substage = "finding_vod"

    def update_root_progress(stage: str, detail: str = "",
                             substage: str | None = None, **extra) -> None:
        nonlocal stage_started, current_stage
        nonlocal substage_started, current_substage
        with progress_lock:
            now = time.monotonic()
            timings = dict(progress.get("timings_s") or {})
            if stage != current_stage:
                timings[current_stage] = round(
                    timings.get(current_stage, 0) + now - stage_started, 2)
                stage_started = now
                current_stage = stage
            # `stage` is the customer-facing label and must stay coarse.
            # `substage_s` is the engineering breakdown: "rendering" bundles
            # facecam, the caption pass, master downloads and OCR QA with the
            # actual encodes, so the coarse number can't tell us what to
            # optimize. Additive key — web ignores what it doesn't know.
            substages = dict(progress.get("substage_s") or {})
            marker = substage or stage
            if marker != current_substage:
                substages[current_substage] = round(
                    substages.get(current_substage, 0)
                    + now - substage_started, 2)
                substage_started = now
                current_substage = marker
            progress.update({
                "stage": stage, "detail": detail, "timings_s": timings,
                "substage_s": substages,
                # Piggyback on the existing per-stage PATCH instead of adding
                # a write path: the founder cost page then sees a running
                # job's spend grow without the worker knowing any prices.
                "llm_usage": usage.snapshot(),
                **extra,
            })
            sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
               json={"progress": progress})

    published_rows = []

    def publish_ready(rendered: dict) -> None:
        # Serialize the small upload/insert bookkeeping section while the two
        # expensive renders remain parallel. A completed clip becomes visible
        # immediately; the rest of the batch keeps processing.
        with progress_lock:
            # Preserve editorial rank even when candidate 2 finishes rendering
            # before candidate 1. Gaps are acceptable when an earlier bench
            # candidate fails QA; reordering the visible winners is not.
            slot = int(rendered.get("_candidate_index", len(published_rows))) + 1
            key = f"{job['user_id']}/{job['id']}/{slot:02d}.mp4"
            upload_r2(Path(rendered["file"]), key)
            row = sb("POST", "/rest/v1/clips", json={
                "job_id": job["id"], "user_id": job["user_id"],
                "r2_key": key, "title": rendered["title"],
                "hook": rendered["hook"], "score": rendered["score"],
                "start_s": rendered["start_s"], "end_s": rendered["end_s"],
            }).json()[0]
            rendered["_published"] = True
            rendered["_clip_id"] = row["id"]
            rendered["_r2_key"] = key
            published_rows.append(row)
            recipes = dict(progress.get("clip_recipes") or {})
            recipes[row["id"]] = rendered.get("edit_recipe")
            progress.update({
                "published": len(published_rows),
                "ready_clip_ids": [r["id"] for r in published_rows],
                "clip_recipes": recipes,
                "llm_usage": usage.snapshot(),
                "detail": (
                    f"{len(published_rows)} clip"
                    f"{'s' if len(published_rows) != 1 else ''} ready — "
                    "finishing the rest"
                ),
            })
            sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
               json={"progress": progress})

    cfg["_progress"] = update_root_progress
    cfg["_clip_ready"] = publish_ready
    update_root_progress("finding_vod")
    result = pipeline.run(cfg, vod_url=job["vod_url"])
    update_root_progress("uploading", "finalizing the batch")

    clip_rows = []
    for i, c in enumerate(result["clips"], 1):
        if c.get("_published"):
            continue
        key = f"{job['user_id']}/{job['id']}/{i:02d}.mp4"
        upload_r2(Path(c["file"]), key)
        clip_rows.append({
            "job_id": job["id"], "user_id": job["user_id"], "r2_key": key,
            "title": c["title"], "hook": c["hook"], "score": c["score"],
            "start_s": c["start_s"], "end_s": c["end_s"],
        })
    inserted = list(published_rows)
    if clip_rows:
        inserted.extend(sb("POST", "/rest/v1/clips", json=clip_rows).json())
    recipes = {}
    rendered_by_id = {
        c.get("_clip_id"): c for c in result["clips"] if c.get("_clip_id")}
    unpublished = iter([c for c in result["clips"] if not c.get("_published")])
    for row in inserted:
        rendered = rendered_by_id.get(row["id"]) or next(unpublished)
        recipes[row["id"]] = rendered.get("edit_recipe") or {
            "source_start": rendered["start_s"],
            "source_end": rendered["end_s"],
            "keep_intervals": [[rendered["start_s"], rendered["end_s"]]],
            "cam": None,
        }

    processing_seconds = round(time.monotonic() - processing_started, 2)
    # Modal's public per-second CPU + memory rates for this fixed 8-core/8-GiB
    # function. This is observability, not billing authority.
    estimated_compute = round(
        processing_seconds * ((8 * 0.0000131) + (8 * 0.00000222)), 4)
    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
       json={"status": "done", "finished_at": "now()",
             "progress": {**progress, "stage": "done", "detail": "",
                          "preset": (cfg["style"].get("preset") or "classic"),
                          "title_strategy": cfg["style"].get(
                              "title_strategy", "curiosity"),
                          "opening_effect": cfg["style"].get(
                              "opening_effect", "punch_zoom"),
                          "requested": result.get(
                              "requested", cfg["clips"]["count"]),
                          "shipped": len(result["clips"]),
                          "published": len(inserted),
                          "processing_seconds": processing_seconds,
                          "estimated_modal_compute_usd": estimated_compute,
                          # Final flush: the caption pass and any late editor
                          # calls land after the last stage transition.
                          "llm_usage": usage.snapshot(),
                          "fulfilled": result.get("fulfilled"),
                          "candidates": result.get("candidate_count"),
                          "verified": result.get("verified_count"),
                          "rejected": result.get("rejected_count"),
                          "rejection_reasons": result.get(
                              "rejection_reasons", []),
                          "clip_recipes": recipes}})
    if job.get("_legacy_credit_cost"):
        legacy_cost = int(job["_legacy_credit_cost"])
        sb("POST", "/rest/v1/credit_events",
           json={"user_id": job["user_id"], "delta": -legacy_cost,
                 "reason": "job (migration bridge)", "job_id": job["id"]})
        sb("PATCH", f"/rest/v1/users?id=eq.{job['user_id']}",
           json={"credits": max(0, int(user["credits"]) - legacy_cost)})
    send_ready_notification(user, job, len(result["clips"]))


def fail(job: dict, err: str) -> None:
    # Preserve the visible settings/progress and leave a useful dashboard
    # explanation. Previously a fast failure disappeared from ActiveJobs and
    # looked as if clicking Run had done nothing.
    try:
        rows = sb(
            "GET", f"/rest/v1/jobs?id=eq.{job['id']}&select=progress").json()
        progress = dict((rows[0] if rows else {}).get("progress") or {})
    except Exception:
        progress = dict(job.get("progress") or {})
    lines = [line.strip() for line in err.splitlines() if line.strip()]
    detail = lines[-1] if lines else "Processing stopped unexpectedly."
    if "free disk" in err.lower():
        disk_line = next(
            (line.strip() for line in lines if "free disk" in line.lower()),
            detail,
        )
        detail = disk_line.removeprefix("SystemExit: ")
    # A job that died halfway still burned tokens; the cost page must show
    # them, so flush whatever the ledger holds for this job.
    progress.update({"stage": "failed", "detail": detail[:500],
                     "llm_usage": usage.snapshot()})
    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
       json={"status": "failed", "error": err[-1500:],
             "progress": progress, "finished_at": "now()"})
    if not (job.get("progress") or {}).get("kind"):
        try:
            refund_job_credits(job)
        except Exception as error:
            print(f"credit refund warning: {error}")


def main_loop() -> None:
    print(f"worker {WORKER_ID} polling every {POLL}s")
    while True:
        heartbeat("polling")
        try:
            job = claim_job()
        except Exception as e:
            print(f"claim error: {e}")
            time.sleep(POLL)
            continue
        if not job:
            heartbeat("idle")
            time.sleep(POLL)
            continue
        heartbeat("processing", f"job {job['id']}")
        print(f"claimed job {job['id']} ({job['vod_url']})")
        try:
            process(job)
            print(f"job {job['id']} done")
        except (Exception, SystemExit):
            err = traceback.format_exc()
            print(f"job {job['id']} FAILED:\n{err}")
            try:
                fail(job, err)
            except Exception as e2:
                print(f"couldn't mark failed: {e2}")
        heartbeat("idle")


def local_run(spec: dict) -> None:
    """Dry run without any cloud: pipeline only, results printed."""
    cfg = load_config()
    if "clips" in spec:
        cfg["clips"]["count"] = spec["clips"]
    result = pipeline.run(cfg, vod_url=spec.get("vod_url"))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--local":
        local_run(json.loads(sys.argv[2]))
    elif len(sys.argv) > 1 and sys.argv[1] == "--once":
        job = claim_job()
        if not job:
            print("no queued jobs")
        else:
            print(f"claimed {job['id']}")
            try:
                process(job)
                print("done")
            except (Exception, SystemExit):
                err = traceback.format_exc()
                print(err)
                fail(job, err)
    else:
        main_loop()
