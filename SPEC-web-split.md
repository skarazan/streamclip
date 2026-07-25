# SPEC: Web/worker split + conversion frontend

For: CTO (Sol 5.6 / Codex). From: COO. Date: 2026-07-24.
Context docs: PROJECT.md (pipeline), BUSINESS.md (pricing, gaps, priorities).

Two workstreams: (A) split the dashboard out of the worker repo into its own
deployable service; (B) build the full conversion-grade frontend around it.

---

## A. Service split — two repos, two services

### Why

- **Availability**: when workers are down or Modal misbehaves, users must
  still be able to log in, see their jobs/clips history, download old clips,
  and see an honest status banner — not a dead site. Web on Vercel and worker
  on Modal fail independently.
- **Deploy isolation**: pipeline changes currently sit in the same repo as
  the dashboard; a broken worker commit shouldn't block a landing-page fix,
  and vice versa.
- **Team split**: web work and pipeline work are now separate owners.

### Target shape

```
streamclip-web    (new repo)      Vercel   — Next.js dashboard + landing + all pages
streamclip        (existing repo) Modal    — clipfarm/, worker/, benchmark/, research/
```

The two services NEVER import each other's code. The entire contract between
them is the Supabase schema + R2 key layout:

- `jobs` (status, progress jsonb incl. template snapshot, error)
- `clips` (r2_key, title, duration, score, source, manifest fields)
- `users` (plan, credits, twitch identity)
- `credit_events` (append-only ledger)
- R2 keys: `user_id/job_id/NN.mp4`, presigned by web, written by worker.

### Contract rules (put these in a `CONTRACT.md` in BOTH repos)

1. Schema changes are additive-only (new columns/tables); removals need a
   two-step deprecation across both repos.
2. Web reads worker state ONLY via DB rows; worker learns of new work ONLY
   via `claim_job()` RPC. No HTTP between them, no shared code package.
3. `jobs.progress.version` records the pipeline version that ran; web renders
   unknown future fields defensively (ignore, don't crash).
4. Worker heartbeat: `worker_health` row upserted each poll tick (timestamp,
   queue depth). Web shows a "processing delayed" banner when heartbeat is
   stale >5 min — this is the "workers down, people still see stuff" feature.

### v11 additions that move with the web repo

The dashboard now includes API routes (`app/api/edit-jobs/[id]`, `.../media`,
`app/api/clips/[id]/editor-source`, `.../revisions`) that stream the editing
proxy same-origin with Range support. Two flags for the split:

- These routes are part of the WEB service (they only read Supabase + R2);
  they move to `streamclip-web` unchanged.
- **Cost/limit watch**: proxy video streams through Vercel functions →
  function egress + duration limits. Fine for 360×640 proxies; revisit if
  usage grows (Cloudflare Worker in front of R2 is the escape hatch). Final
  clip downloads stay direct-presigned — keep it that way.

### Migration steps

1. Run `scripts/extract-web-repo.sh` from a clean committed tree. It performs
   the `web/app` subtree split into a local sibling `streamclip-web`, removes
   the inherited origin, and leaves external GitHub/Vercel creation as an
   explicit founder-authorized deployment action. The old static
   `web/landing` is superseded by the Next.js conversion routes.
2. Add `CONTRACT.md` + `worker_health` table + heartbeat in worker poll fn.
3. Remove `web/` from the worker repo once Vercel serves from the new one.
4. Sentry DSNs: one project per service.

---

## B. Frontend: every page needed for conversion + compliance

Stack stays Next.js (JS, Tailwind). Design language: dark, gaming-native,
clips-first — the product output IS the hero asset. Mobile-first: streamers
check this from their phone after a stream.

### Pages inventory

**Public (marketing)**
| Route | Purpose / key content |
|---|---|
| `/` | Landing. Hero: autoplaying muted example Short next to "Your community already marks the funny moments." One CTA: Connect Twitch (or Join waitlist pre-launch). Sections: 3-step how-it-works, before/after demo clips, small-streamer proof, pricing teaser, FAQ teaser, final CTA. |
| `/pricing` | Starter $14.99 / Creator $29.99 / trial 2 credits. Credit explainer ("1 credit = 1 full VOD → 3 shorts"). Comparison row vs Opus/Eklipse. FAQ anchors for billing questions. |
| `/faq` | Sections: how picking works (crowd + AI, arc-verified — this is a SALES page, explain the moat plainly), supported platforms (Twitch now, Kick later), what happens with small channels, credits/billing, cancellation/refunds, content rights, data handled (chat, VODs). |
| `/demo` | Gallery of real output batches (founder's channel), grouped by streamer, with the WHY line from each clip's manifest shown — the transparency is a differentiator. |
| `/changelog` | Public log; feeds trust + SEO. |
| `/legal/terms` | ToS: content ownership stays with streamer; we process on their behalf; acceptable use; credit/refund terms; liability caps. |
| `/legal/privacy` | GDPR-grade: what we store (transcripts, chat samples, clips, Twitch identity), retention windows, processor list (Supabase, Modal, Groq, Google, Cloudflare, Stripe, Twilio), deletion rights + how to exercise. |
| `/legal/cookies` | Cookie policy + the consent banner behavior. |
| `/status` | Reads `worker_health` + last N job completion times. Public. |

**Auth**
| Route | Purpose |
|---|---|
| `/login` | Twitch OAuth only (no passwords to store). Error states: OAuth denied, Twitch down. Post-login redirect to `/app`. |
| `/logout`, session expiry | Supabase session refresh; handle revoked Twitch tokens gracefully (re-auth prompt, not a crash). |
| Account deletion | In settings: full cascade delete (DB rows + R2 objects), confirmation flow, 7-day grace. GDPR art. 17. |

**App (authed)**
| Route | Purpose |
|---|---|
| `/app` | Dashboard: jobs list with live stage progress, clips grid with hover-preview, download, "Run again". Empty state = onboarding (below). Stale-heartbeat banner. |
| `/app/onboarding` | First-run: pick template (title strategy + opening pattern presets already in v11) → auto-enqueue most recent VOD → progress screen. Target: first clip visible <20 min from signup. |
| `/app/settings` | Template selection, notification prefs, plan + credit balance, billing portal link (Stripe), danger zone (delete account). |
| `/app/billing` | Stripe Checkout for plans/credit packs; invoice history via Stripe customer portal. |

### Compliance & conversion chrome

- **Cookie consent banner**: minimal-cookie posture — Supabase auth cookie is
  strictly necessary (no consent needed); analytics via Plausible (cookieless,
  no banner burden). So the banner only appears if/when a non-essential
  cookie exists. Do NOT add Google Analytics; it drags the whole consent
  apparatus in.
- **SEO**: per-page meta + OG images (an example Short frame as og:image),
  sitemap, `/faq` structured data (FAQPage schema).
- **Analytics events** (Plausible custom events): landing CTA click, OAuth
  started/completed, onboarding template picked, first job enqueued, first
  clip downloaded, checkout started/completed. This is the funnel BUSINESS.md
  §7 measures.
- **Performance**: landing must be static/ISR, <1s LCP on mobile — the hero
  video lazy-loads poster-first.

### Priorities (build order)

1. Repo split + heartbeat/status banner (availability story, unblocks
   everything else being iterated safely)
2. `/login` hardening + `/app` onboarding flow (activation)
3. Legal trio + cookie posture (unblocks Stripe + trials)
4. `/pricing` + Stripe checkout + credit enforcement hook (revenue)
5. Landing conversion pass + `/faq` + `/demo` (traffic → signup)
6. `/status`, `/changelog`, notification emails (retention)

### CTO implementation checkpoint — 2026-07-25

Implemented in the current repository:

- additive `CONTRACT.md`, progress versioning, `worker_health`, per-user claim
  isolation, atomic reserve/refund/grant credit RPCs, and billing-event
  idempotency;
- public/dash status surfaces and stale-worker banner;
- hardened Twitch OAuth errors, onboarding, EventSub offline ingestion and
  delayed latest-archive resolution;
- pricing, Stripe Checkout/Portal/webhook code, credit ledger UI;
- legal trio, cookie-minimal posture, FAQ schema, demo, changelog,
  sitemap/robots, Plausible event hooks, responsive landing;
- Resend completion notification hook and seven-day account-deletion workflow;
- `scripts/extract-web-repo.sh`, a clean-history local extraction tool.

Deliberately not performed by code:

- creating/pushing the private GitHub `streamclip-web` repository;
- creating a Vercel project or production deployment;
- creating Stripe products/prices or enabling live charges;
- applying the production Supabase migration;
- registering production webhook URLs, Resend domain, Sentry, or uptime monitor;
- representing legal drafts as counsel-approved.

Those are external-state/credential decisions. The implementation stays inert
or uses a safe compatibility bridge until the founder explicitly performs the
deployment checklist in `web/app/README.md`.

### Acceptance checks (per workstream)

- Kill the Modal poll fn on staging → dashboard still serves, banner appears
  within 5 min, old clips downloadable.
- Fresh account → first clip downloaded in <20 min without touching anything
  but the onboarding screen.
- Stripe test-mode: subscribe, credits appear in ledger; burn to 0, next job
  refused with a clear upsell message, purchase pack, job accepted.
- All legal pages reachable from footer on every route; account deletion
  actually cascades (verify R2 empty for that user).
