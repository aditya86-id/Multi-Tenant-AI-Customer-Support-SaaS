# AI Customer Support SaaS (multi-tenant, RAG + agentic escalation)

Companies (tenants) upload their knowledge base. End customers chat with an
embeddable AI widget that answers from that tenant's knowledge base using
RAG, and escalates to a human (creates a ticket) when it's not confident or
the user asks for one.

## Status: Phase 7 -- hardening (feature-complete)

Implemented so far:
- FastAPI app structure (`backend/app`)
- Full Postgres schema with pgvector (`backend/init-db/001_init.sql`,
  `002_usage_logs.sql`): tenants, users, documents, chunks (embeddings),
  conversations, messages, tickets, usage_logs -- every table carries
  `tenant_id`
- JWT auth: tenant signup (creates tenant + first admin), login
- Tenant-scoped `CurrentUser` dependency (`app/core/deps.py`) used by every
  protected route -- no query in the app is allowed to skip the tenant_id
  filter
- RBAC: `admin` can create users; admin and agent can upload documents and
  update tickets (status, priority, assignment) -- ticket assignment is
  validated against the tenant so a ticket can never be assigned to a user
  outside it
- Docker Compose: Postgres (pgvector image), Redis, API, Celery worker
- Document upload endpoint (`.txt`/`.md`/`.pdf`, 10 MB limit), stored per
  tenant on disk (swap for S3/GCS in production)
- Celery ingestion task: extracts text, chunks it (~750 tokens, overlapping),
  embeds each chunk via Voyage AI, stores vectors in `chunks` -- scoped by
  `tenant_id` end to end, with retry-on-transient-failure and a `failed`
  status + `error_message` when ingestion can't succeed
- Document status tracking: `pending -> processing -> ready` or `failed`
- Public `/api/v1/query` endpoint (widget-facing, scoped by `tenant_slug`,
  no JWT since it's called by anonymous site visitors): embeds the user's
  message via Voyage, retrieves the top-5 most similar chunks scoped to
  that tenant, and generates a grounded answer with Anthropic Claude that
  cites `[Source N]` back to the retrieved chunks
- Conversations and messages are persisted (`conversation_id` lets the
  widget continue a thread), including a similarity-based `confidence`
  score per answer
- **Agentic escalation**: Claude is given a real `create_ticket` tool and
  decides for itself -- using retrieval relevance and the customer's own
  words, not a fixed similarity threshold -- whether a question needs
  human follow-up. Escalation happens *alongside* the answer, so the
  customer is never left with silence. `GET/PATCH /api/v1/tickets/{id}`
  (tenant-scoped, staff-only) manage the result
- **Next.js admin dashboard** (`dashboard/`): tenant sign up / log in,
  knowledge-base document upload with live ingestion status, a ticket
  queue view, and a basic analytics tab
- **Embeddable widget** (`widget/widget.js`): a single, dependency-free
  JavaScript file, one `<script>` tag with two data attributes
- **Per-tenant rate limiting**: `/api/v1/query` is limited to
  `RATE_LIMIT_PER_MINUTE` (default 30) requests/minute, keyed by
  `tenant_id` in Redis -- one tenant's traffic (or an abusive client)
  can never eat into another tenant's quota, and the limit holds even
  across multiple API instances since it's Redis-backed, not in-memory.
  Returns `429` with a `Retry-After` header when exceeded
- **Per-tenant token usage logging**: every `/query` call records Anthropic
  input/output token counts to `usage_logs`, scoped by `tenant_id` -- the
  foundation for real per-tenant cost tracking or billing

## Running locally

**Backend:**
```bash
cp .env.example .env
# edit .env: set a real JWT_SECRET_KEY, VOYAGE_API_KEY, and ANTHROPIC_API_KEY

docker compose up --build
```
The API will be available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`. The Celery worker starts alongside it and
picks up ingestion jobs from Redis.

**Dashboard:**
```bash
cd dashboard
cp .env.local.example .env.local
npm install
npm run dev
```
Open `http://localhost:3000` -- it'll redirect to `/login`, where you can
create a tenant or sign in to an existing one, then land on the dashboard.

**Widget:**
```bash
cd widget
python3 -m http.server 5500
```
Open `http://localhost:5500/demo.html` (with the backend already running)
to see the chat bubble live against a real tenant. To embed it on any other
page, copy the one `<script>` tag from `demo.html` and update the two data
attributes.

## Try it (API directly)

```bash
# 1. Create a tenant + admin user
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_name": "Acme Inc",
    "tenant_slug": "acme",
    "admin_email": "admin@acme.com",
    "admin_password": "supersecret123"
  }'
# -> { "access_token": "...", "token_type": "bearer" }

# 2. Use the token to fetch your tenant
curl http://localhost:8000/api/v1/tenants/me \
  -H "Authorization: Bearer <access_token>"

# 3. Log in again later
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug": "acme", "email": "admin@acme.com", "password": "supersecret123"}'

# 4. Admin invites an agent
curl -X POST http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "agent@acme.com", "password": "agentpass123", "role": "agent"}'

# 5. Upload a knowledge-base document (queues async ingestion)
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@./faq.md"
# -> { "id": "...", "status": "pending", ... }

# 6. Poll ingestion status
curl http://localhost:8000/api/v1/documents/<document_id> \
  -H "Authorization: Bearer <access_token>"
# -> status flips pending -> processing -> ready (or failed + error_message)

# 7. Ask a question (public, no auth -- this is what the widget calls)
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug": "acme", "message": "What is your refund policy?"}'
# -> { "conversation_id": "...", "answer": "... [Source 1]", "confidence": 0.83,
#      "sources": [...], "escalated": false, "ticket_id": null }

# 8. Ask something the KB doesn't cover, or explicitly ask for a human
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug": "acme", "message": "Can I talk to a real person about my account?"}'
# -> escalated: true, ticket_id set -- Claude decided to open a ticket

# 9. Verify + update the ticket as staff
curl http://localhost:8000/api/v1/tickets \
  -H "Authorization: Bearer <access_token>"

curl -X PATCH http://localhost:8000/api/v1/tickets/<ticket_id> \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved"}'

# 10. Hit /query 31+ times in a minute from the same tenant to see the
#     rate limit kick in (429 + Retry-After header)
```

## Multi-tenancy rules (enforced, not just documented)

- Every domain table has a `tenant_id` column with an index and a
  `REFERENCES tenants(id) ON DELETE CASCADE`
- The JWT embeds `tenant_id` and `role` directly; `get_current_user`
  re-fetches the user filtered by **both** `id` and `tenant_id`, so a stolen
  or forged token can't be replayed against another tenant's data even if
  the user id happened to collide
- Every route handler queries with an explicit `.where(Model.tenant_id ==
  current_user.tenant_id)` -- there is no "trusted" internal path that skips
  this
- Login requires `tenant_slug + email`, not just email, since the same
  email can exist under different tenants
- The Celery ingestion task takes `tenant_id` as an explicit argument and
  filters every query by it, rather than trusting a lookup by `document_id`
  alone
- The public `/query` endpoint (used by both the dashboard's "try it" flow
  and the widget) resolves `tenant_slug` first and scopes every subsequent
  retrieval/conversation/message/ticket/usage-log operation to that
  tenant's id -- there is no code path where a chunk or ticket from
  another tenant can be touched
- The widget only ever knows a `tenant_slug` (never a raw `tenant_id` or
  any staff credential), so embedding it on a tenant's site can't leak
  access to another tenant's data or to any authenticated dashboard route
- The rate limiter is keyed by `tenant_id`, never global, so no tenant can
  be starved by another tenant's traffic
- Ticket assignment (`PATCH /tickets/{id}`) validates that `assigned_to`
  is a user in the *same* tenant before saving it

## Project layout

```
backend/
  app/
    core/       settings, JWT + password hashing, auth dependency
    db/         async SQLAlchemy engine/session (FastAPI request path)
    models/     SQLAlchemy models (mirrors init-db schema 1:1)
    schemas/    Pydantic request/response models
    services/   text extraction, chunking, Voyage AI embeddings, retrieval,
                LLM answer generation + agentic escalation (create_ticket tool),
                per-tenant rate limiting
    worker/     Celery app, sync DB session, ingestion task
    api/routes/ auth, tenants, users, documents, query, tickets
    main.py     FastAPI app, CORS, global error handlers
  init-db/      raw SQL run once by Postgres on first container start
  Dockerfile
dashboard/
  app/          login page, dashboard page (documents/tickets/analytics tabs)
  lib/api.ts    typed client for the backend API
widget/
  widget.js     the embeddable widget itself (no dependencies, no build step)
  demo.html     example page showing the embed
docker-compose.yml
```

## Roadmap

- [x] Phase 1: scaffold, schema, JWT auth, tenant CRUD
- [x] Phase 2: document ingestion (upload + Celery chunk/embed into pgvector)
- [x] Phase 3: RAG query endpoint with source citations
- [x] Phase 4: agentic escalation via Claude tool use (create_ticket tool)
- [x] Phase 5: Next.js admin dashboard
- [x] Phase 6: embeddable JS widget
- [x] Phase 7: hardening (rate limiting, usage logging, RBAC, retries)

## Ideas for what's next (beyond the original 7 phases)

- A dashboard view for `usage_logs` (cost per tenant over time)
- Alembic migrations instead of raw numbered SQL files, once the schema
  needs to evolve on a live database instead of a fresh container
- Voyage embedding usage logging (currently only Anthropic calls are
  logged) for complete per-tenant cost visibility
- Deploying it -- see conversation history for the recommended stack
  (Railway for the backend + Postgres/Redis, Vercel for the dashboard and
  widget)
