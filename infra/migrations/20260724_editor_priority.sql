-- CPU-neutral editor fast lane: interactive edits are claimed before the next
-- queued full-VOD analysis. This changes ordering only; it does not add worker
-- containers or allow duplicate claims.
create or replace function claim_job(p_worker text)
returns setof jobs language sql as $$
  update jobs set status='running', worker_id=p_worker, started_at=now()
  where id = (
    select id from jobs
    where status='queued' and run_after <= now()
    order by ((progress->>'kind') in ('clip_edit', 'clip_source')) desc,
             created_at
    for update skip locked
    limit 1
  )
  returning *;
$$;
