-- Additive web/worker contract, reliability heartbeat, and atomic credits.

alter table users
  add column if not exists email text,
  add column if not exists stripe_customer_id text unique,
  add column if not exists subscription_status text,
  add column if not exists notification_email boolean not null default true,
  add column if not exists deletion_requested_at timestamptz;

alter table jobs
  add column if not exists credit_cost int not null default 0,
  add column if not exists credit_reserved_at timestamptz;

alter table credit_events
  add column if not exists external_id text;
create unique index if not exists credit_events_external_id_idx
  on credit_events (external_id) where external_id is not null;

create table if not exists worker_health (
  id text primary key,
  state text not null default 'idle',
  queue_depth int not null default 0,
  worker_version text,
  detail text,
  updated_at timestamptz not null default now()
);

create table if not exists billing_events (
  stripe_event_id text primary key,
  event_type text not null,
  status text not null default 'processing',
  error text,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create or replace function reserve_job_credits(
  p_job uuid, p_user uuid, p_amount int
) returns table(ok boolean, balance int)
language plpgsql security definer set search_path = public as $$
declare
  current_balance int;
  already_reserved boolean;
begin
  if p_amount < 1 then
    raise exception 'credit amount must be positive';
  end if;
  select credits into current_balance from users where id = p_user for update;
  if current_balance is null then
    return query select false, 0;
    return;
  end if;
  select exists(
    select 1 from credit_events
    where external_id = 'job-reserve:' || p_job::text
  ) into already_reserved;
  if already_reserved then
    return query select true, current_balance;
    return;
  end if;
  if current_balance < p_amount then
    return query select false, current_balance;
    return;
  end if;
  update users set credits = credits - p_amount where id = p_user
    returning credits into current_balance;
  insert into credit_events(user_id, delta, reason, job_id, external_id)
  values (
    p_user, -p_amount,
    case when p_amount = 1 then 'job reservation' else 'long VOD reservation' end,
    p_job, 'job-reserve:' || p_job::text
  );
  update jobs set credit_cost = p_amount, credit_reserved_at = now()
    where id = p_job and user_id = p_user;
  return query select true, current_balance;
end;
$$;

create or replace function refund_job_credits(
  p_job uuid, p_user uuid, p_reason text default 'failed job refund'
) returns int
language plpgsql security definer set search_path = public as $$
declare
  amount int;
  new_balance int;
begin
  perform 1 from users where id = p_user for update;
  select -delta into amount from credit_events
  where user_id = p_user and external_id = 'job-reserve:' || p_job::text;
  if amount is null or exists(
    select 1 from credit_events
    where external_id = 'job-refund:' || p_job::text
  ) then
    select credits into new_balance from users where id = p_user;
    return coalesce(new_balance, 0);
  end if;
  update users set credits = credits + amount where id = p_user
    returning credits into new_balance;
  insert into credit_events(user_id, delta, reason, job_id, external_id)
  values (p_user, amount, p_reason, p_job, 'job-refund:' || p_job::text);
  return new_balance;
end;
$$;

create or replace function grant_credits(
  p_user uuid, p_amount int, p_reason text, p_external_id text,
  p_plan text default null, p_stripe_customer text default null
) returns int
language plpgsql security definer set search_path = public as $$
declare
  new_balance int;
begin
  if p_amount < 0 then raise exception 'grant amount cannot be negative'; end if;
  perform 1 from users where id = p_user for update;
  if exists(select 1 from credit_events where external_id = p_external_id) then
    select credits into new_balance from users where id = p_user;
    return coalesce(new_balance, 0);
  end if;
  update users set
    credits = credits + p_amount,
    plan = coalesce(p_plan, plan),
    stripe_customer_id = coalesce(p_stripe_customer, stripe_customer_id),
    subscription_status = case when p_plan is null
      then subscription_status else 'active' end
  where id = p_user returning credits into new_balance;
  insert into credit_events(user_id, delta, reason, external_id)
  values (p_user, p_amount, p_reason, p_external_id);
  return new_balance;
end;
$$;

create or replace function claim_job(p_worker text)
returns setof jobs language sql as $$
  update jobs set status='running', worker_id=p_worker, started_at=now()
  where id = (
    select candidate.id from jobs candidate
    where candidate.status='queued' and candidate.run_after <= now()
      and not exists (
        select 1 from jobs active
        where active.user_id = candidate.user_id
          and active.status = 'running'
      )
    order by ((candidate.progress->>'kind') in ('clip_edit', 'clip_source')) desc,
             candidate.created_at
    for update skip locked
    limit 1
  )
  returning *;
$$;

revoke all on function claim_job(text) from public, anon, authenticated;
grant execute on function claim_job(text) to service_role;
revoke all on function reserve_job_credits(uuid, uuid, int)
  from public, anon, authenticated;
grant execute on function reserve_job_credits(uuid, uuid, int) to service_role;
revoke all on function refund_job_credits(uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function refund_job_credits(uuid, uuid, text) to service_role;
revoke all on function grant_credits(uuid, int, text, text, text, text)
  from public, anon, authenticated;
grant execute on function grant_credits(uuid, int, text, text, text, text)
  to service_role;

alter table worker_health enable row level security;
alter table billing_events enable row level security;
