-- StreamClip core schema (Supabase / Postgres)

create table users (
  id uuid primary key references auth.users(id) on delete cascade,
  twitch_id text unique not null,
  twitch_login text not null,
  yt_channel_id text,
  plan text not null default 'trial',          -- trial | starter | churned
  credits int not null default 2,              -- trial = 2 VOD credits
  clips_per_stream int not null default 3,
  auto_clip boolean not null default true,
  style_profile jsonb not null default '{}',   -- renderer style overrides
  created_at timestamptz not null default now()
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  vod_url text not null,
  status text not null default 'queued',       -- queued|running|done|failed
  run_after timestamptz not null default now(),-- EventSub sets now()+2h
  error text,
  worker_id text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);
create index jobs_claim_idx on jobs (status, run_after);

create table clips (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references jobs(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  r2_key text not null,
  title text not null,
  hook text,
  score numeric,
  start_s numeric not null,
  end_s numeric not null,
  feedback int,                                -- 1 / -1 / null
  created_at timestamptz not null default now()
);

create table credit_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references users(id) on delete cascade,
  delta int not null,                          -- -1 job, +8 monthly, +N topup
  reason text not null,                        -- job|grant|topup|refund
  job_id uuid references jobs(id),
  created_at timestamptz not null default now()
);

-- atomic claim: N workers never double-claim
create or replace function claim_job(p_worker text)
returns setof jobs language sql as $$
  update jobs set status='running', worker_id=p_worker, started_at=now()
  where id = (
    select id from jobs
    where status='queued' and run_after <= now()
    order by created_at
    for update skip locked
    limit 1
  )
  returning *;
$$;

-- RLS: users see only their own rows; worker uses service key (bypasses RLS)
alter table users enable row level security;
alter table jobs enable row level security;
alter table clips enable row level security;
alter table credit_events enable row level security;
create policy own_user on users for select using (auth.uid() = id);
create policy own_jobs on jobs for select using (auth.uid() = user_id);
create policy own_clips on clips for select using (auth.uid() = user_id);
create policy own_credits on credit_events for select using (auth.uid() = user_id);
create policy clip_feedback on clips for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
