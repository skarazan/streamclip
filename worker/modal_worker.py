"""StreamClip worker on Modal — serverless, $0 idle, no local machine.

Deploy:   modal deploy worker/modal_worker.py     (from repo root)
Manual:   modal run worker/modal_worker.py::drain
Schedule: drains the job queue every 5 minutes automatically.
"""

from pathlib import Path

import modal

REPO = Path(__file__).resolve().parent.parent

app = modal.App("streamclip-worker")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "fontconfig", "fonts-liberation")
    .pip_install(
        "yt-dlp", "faster-whisper", "numpy", "pyyaml",
        "httpx", "boto3", "openai", "opencv-python-headless<5",
    )
    .add_local_dir(str(REPO / "clipfarm"), remote_path="/root/app/clipfarm")
    .add_local_file(str(REPO / "config.yaml"), remote_path="/root/app/config.yaml")
    .add_local_file(str(REPO / "worker/worker.py"),
                    remote_path="/root/app/worker/worker.py")
)

hf_cache = modal.Volume.from_name("streamclip-hf-cache", create_if_missing=True)
work_vol = modal.Volume.from_name("streamclip-work", create_if_missing=True)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("streamclip")],
    cpu=0.125,
    memory=256,
    timeout=120,
    schedule=modal.Period(minutes=1),
)
def poll():
    """Cheap scheduled heartbeat. NEVER attach a GPU to a schedule — a
    1-min GPU schedule + idle keep-alive is a 24/7 T4 (~$25/day) doing
    nothing. This poll is a fraction of a CPU core doing two REST calls."""
    import os
    import sys

    os.chdir("/root/app")
    sys.path.insert(0, "/root/app")
    sys.path.insert(0, "/root/app/worker")

    import worker

    worker.requeue_stale()
    removed = worker.purge_due_accounts()
    if removed:
        print(f"purged {removed} expired account(s)")
    worker.heartbeat("polling")
    if worker.has_ready_job() and not worker.has_running_job():
        drain.spawn()
        print("ready job found -> CPU drain spawned")
    else:
        worker.heartbeat("idle")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("streamclip")],
    volumes={"/root/.cache/huggingface": hf_cache,
             "/root/app/work": work_vol},
    # CPU-only since transcription moved to the Groq API: ~$0.45/h vs
    # ~$1.03/h with the T4, and nothing left in the job needs a GPU.
    # (faster-whisper stays importable as the local fallback — slow on CPU
    # but only runs if Groq is down.)
    cpu=8.0,
    memory=8192,
    timeout=7200,
    scaledown_window=10,  # container dies seconds after the queue empties
)
def drain():
    """Claim and process queued jobs until the queue is empty."""
    import os
    import sys
    import traceback

    os.chdir("/root/app")
    sys.path.insert(0, "/root/app")
    sys.path.insert(0, "/root/app/worker")
    os.environ.setdefault("WORKER_ID", "modal")

    # style-preset fonts ride in the clipfarm mount; register them with
    # fontconfig once per container so libass can resolve them by name
    import subprocess
    fonts = Path("/root/app/clipfarm/fonts")
    dest = Path("/usr/share/fonts/truetype/streamclip")
    if fonts.is_dir() and not dest.exists():
        dest.mkdir(parents=True)
        for f in fonts.glob("*.ttf"):
            (dest / f.name).write_bytes(f.read_bytes())
        subprocess.run(["fc-cache", "-f"], capture_output=True)

    import worker
    from clipfarm.pipeline import PIPELINE_VERSION

    # stale pre-deploy containers can claim jobs and silently run old code;
    # this line in every drain makes the running version verifiable
    print(f"drain code: {PIPELINE_VERSION}")
    worker.heartbeat("processing", f"drain {PIPELINE_VERSION}")

    n = 0
    while True:
        job = worker.claim_job()
        if not job:
            break
        print(f"claimed {job['id']} ({job['vod_url']})")
        try:
            worker.process(job)
            print(f"{job['id']} done")
        except (Exception, SystemExit):
            err = traceback.format_exc()
            print(f"{job['id']} FAILED:\n{err}")
            try:
                worker.fail(job, err)
            except Exception as e2:
                print(f"couldn't mark failed: {e2}")
        n += 1
        hf_cache.commit()
        work_vol.commit()
    print(f"queue drained, {n} job(s) processed")
    worker.heartbeat("idle")
