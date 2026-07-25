# streamclip-web

Next.js customer and marketing service for StreamClip. It deploys separately
from the CPU worker and communicates only through the Supabase/R2 contract in
`CONTRACT.md`.

## Local

Requires Node.js 20.9 or newer. The lockfile pins the audited Next/React
runtime and safe PostCSS/Sharp transitive versions; use `npm ci` rather than
regenerating dependency ranges during deployment.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

The web service queues work; a worker poll loop must be running separately.
For the legacy monorepo-only development bridge, explicitly set
`STREAMCLIP_LOCAL_WORKER=1`. Hosted deployments must not spawn worker code.

## Deployment order

1. Apply `infra/migrations/20260725_service_contract.sql` from the worker repo.
2. Deploy the worker so heartbeat and atomic credit RPCs are active.
3. Configure the environment variables listed in `.env.example`.
4. Deploy this directory to Vercel.
5. Register Stripe’s webhook at `/api/billing/webhook`.
6. Set the Twitch EventSub callback to `/api/twitch/eventsub`, then reconnect
   existing Twitch accounts once so their offline subscription is ensured.
7. Point an uptime monitor at `/api/status`; alert when `ok` is false.

Stripe routes return a safe configuration error until every selected product
has a price ID. With Managed Payments enabled, every Stripe Product must also
use an eligible tax code. StreamClip is classified as business-use SaaS
(`txcd_10103001`) because creators use the hosted tool to produce publishing
assets; apply that code to both plans and both credit packs. No development
action creates a charge.
