# StreamClip service contract

This file is the compatibility boundary between the web service and the worker.
Copy it unchanged into the extracted `streamclip-web` repository.

## Ownership

- Web owns authentication, customer-facing pages, billing endpoints, signed
  downloads, editor proxy streaming, and creation of queued jobs.
- Worker owns job claiming, Twitch/VOD processing, rendering, R2 writes,
  artifact QA, progress updates, and completion/failure state.
- Neither service imports the other. Supabase rows and R2 keys are the only
  runtime contract.

## Database contract

- Schema changes are additive. Removing or changing a field requires a
  two-release deprecation: readers tolerate both shapes before writers stop
  producing the old shape.
- `jobs.progress.version` identifies the worker/pipeline contract. Web ignores
  unknown fields and displays a safe generic stage for unknown versions.
- `jobs.progress.kind` is absent for root VOD jobs and is `clip_source` or
  `clip_edit` for editor work.
- `worker_health` is updated by every poll loop. Web considers processing
  delayed when the newest heartbeat is more than five minutes old.
- Credits move only through database RPCs. A balance read is advisory; an RPC
  reservation is authoritative.

## R2 contract

- Root clip: `{user_id}/{job_id}/{rank:02d}.mp4`
- Editor proxy: `{user_id}/{clip_id}/editor/source-{job_id}.mp4`
- Editor master: `{user_id}/{clip_id}/editor/master-{job_id}.mp4`
- Revision: `{user_id}/{clip_id}/revisions/{job_id}.mp4`
- Worker writes objects. Web reads them and creates downloads.
- Final clip downloads stay direct-presigned. The low-resolution editor proxy
  is streamed through the authenticated web media route with HTTP Range/206.

## Job state

`queued → running → done|failed`. Workers claim only through `claim_job()`.
One root VOD job may run per user; interactive editor jobs may be prioritized
but never preempt running work or create unbounded compute.
