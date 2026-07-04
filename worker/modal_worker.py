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
    .apt_install("ffmpeg")
    .pip_install(
        "yt-dlp", "faster-whisper", "numpy", "pyyaml",
        "httpx", "boto3", "openai", "opencv-python-headless<5",
        "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*",
    )
    .env({"LD_LIBRARY_PATH":
          "/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:"
          "/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib"})
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
    volumes={"/root/.cache/huggingface": hf_cache,
             "/root/app/work": work_vol},
    gpu="T4",
    cpu=8.0,
    memory=8192,
    timeout=7200,
    schedule=modal.Period(minutes=1),
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

    import worker

    worker.requeue_stale()
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
