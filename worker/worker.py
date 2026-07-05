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
import time
import traceback
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipfarm import pipeline  # noqa: E402
from clipfarm.config import load_config  # noqa: E402

WORKER_ID = os.environ.get("WORKER_ID", socket.gethostname())
POLL = int(os.environ.get("POLL_SECONDS", "30"))


def sb(method: str, path: str, **kwargs) -> httpx.Response:
    url = os.environ["SUPABASE_URL"].rstrip("/") + path
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
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


def claim_job() -> dict | None:
    r = sb("POST", "/rest/v1/rpc/claim_job", json={"p_worker": WORKER_ID})
    rows = r.json()
    return rows[0] if rows else None


def get_user(user_id: str) -> dict:
    return sb("GET", f"/rest/v1/users?id=eq.{user_id}").json()[0]


def upload_r2(local: Path, key: str) -> None:
    import boto3
    s3 = boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET"])
    s3.upload_file(str(local), os.environ["R2_BUCKET"], key,
                   ExtraArgs={"ContentType": "video/mp4"})


def build_job_config(user: dict, job: dict) -> dict:
    cfg = load_config()
    cfg["clips"]["count"] = user.get("clips_per_stream", 3)
    cfg["streamer_name"] = user.get("twitch_login", "the streamer")
    # per-customer style profile overrides the default style block
    for k, v in (user.get("style_profile") or {}).items():
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


def process(job: dict) -> None:
    from clipfarm import fetch
    try:
        if fetch.vod_still_live(job["vod_url"]):
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
        pass  # liveness check is advisory; proceed if it can't tell

    user = get_user(job["user_id"])
    cfg = build_job_config(user, job)
    cfg["_progress"] = lambda stage, detail="": set_progress(job["id"], stage, detail)
    result = pipeline.run(cfg, vod_url=job["vod_url"])
    set_progress(job["id"], "uploading")

    clip_rows = []
    for i, c in enumerate(result["clips"], 1):
        key = f"{job['user_id']}/{job['id']}/{i:02d}.mp4"
        upload_r2(Path(c["file"]), key)
        clip_rows.append({
            "job_id": job["id"], "user_id": job["user_id"], "r2_key": key,
            "title": c["title"], "hook": c["hook"], "score": c["score"],
            "start_s": c["start_s"], "end_s": c["end_s"],
        })
    if clip_rows:
        sb("POST", "/rest/v1/clips", json=clip_rows)

    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
       json={"status": "done", "finished_at": "now()",
             "progress": {"stage": "done", "detail": ""}})
    sb("POST", "/rest/v1/credit_events",
       json={"user_id": job["user_id"], "delta": -1, "reason": "job",
             "job_id": job["id"]})
    sb("PATCH", f"/rest/v1/users?id=eq.{job['user_id']}",
       json={"credits": max(0, user["credits"] - 1)})


def fail(job: dict, err: str) -> None:
    sb("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}",
       json={"status": "failed", "error": err[-1500:], "finished_at": "now()"})


def main_loop() -> None:
    print(f"worker {WORKER_ID} polling every {POLL}s")
    while True:
        try:
            job = claim_job()
        except Exception as e:
            print(f"claim error: {e}")
            time.sleep(POLL)
            continue
        if not job:
            time.sleep(POLL)
            continue
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
