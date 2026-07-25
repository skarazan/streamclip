-- Admin access is an account property, not a billing state.
--
-- `plan` is owned by billing: Stripe sets it to starter/creator on checkout
-- and to churned on cancellation. Overloading it to also mean "this account
-- bypasses the own-channel rule and can see house financials" meant a single
-- test checkout silently stripped the founder's admin rights — including
-- access to /admin/costs, which 404s anyone without them.
--
-- Additive and idempotent; safe to run twice.

alter table users
  add column if not exists is_admin boolean not null default false;

-- Backfill from the plan values that carried this meaning until now.
update users set is_admin = true
  where plan in ('founder', 'internal') and is_admin = false;

-- Billing must never write this column. grant_credits() already touches only
-- credits/plan/stripe_customer_id/subscription_status; this comment is the
-- reminder that adding is_admin to it would re-create the bug.
comment on column users.is_admin is
  'Admin bypass (own-channel rule, /admin/costs). Never written by billing.';
