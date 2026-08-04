# AI Customer Support SaaS (multi-tenant, RAG + agentic escalation)

Companies (tenants) upload their knowledge base. End customers chat with an
embeddable AI widget that answers from that tenant's knowledge base using
RAG, and escalates to a human (creates a ticket) when it's not confident or
the user asks for one.

## Status: Phase 6 -- embeddable widget

Implemented so far:
- FastAPI app structure (`backend/app`)
- Full Postgres schema with pgvector (`backend/init-db/001_init.sql`):
  tenants, users, documents, chunks (embeddings), conversations, messages,
  tickets -- every table carries `tenant_id`
- JWT auth: tenant signup (creates tenant + first admin), login
- Tenant-scoped `CurrentUser` dependency (`app/core/deps.py`) used by every
  protected route -- no query in the app is allowed to skip the tenant_id
  filter
- Basic RBAC: `admin` can create users, everyone can read their own tenant's
  data
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
  customer is never left with silence. `GET /api/v1/tickets` and
  `GET /api/v1/tickets/{id}` (tenant-scoped, staff-only) expose the result
- **Next.js admin dashboard** (`dashboard/`): tenant sign up / log in,
  knowledge-base document upload with live ingestion status, a ticket
  queue view, and a basic analytics tab
- **Embeddable widget** (`widget/widget.js`): a single, dependency-free
  JavaScript file a tenant drops into their site as one `<script>` tag
  with two data attributes (`data-tenant-slug`, `data-api-url`). Renders a
  floating chat bubble, talks directly to the public `/query` endpoint,
  persists the conversation in `sessionStorage` so a page reload doesn't
  lose context, and shows a subtle note when the AI has escalated to a
  human. `widget/demo.html` shows the full integration on a mock page

Not yet built (coming in phase 7): per-tenant rate limiting, token usage
logging, deeper RBAC hardening, ingestion retry policy beyond what's
already in the Celery task.

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

# 9. Verify the ticket as staff
curl http://localhost:8000/api/v1/tickets \
  -H "Authorization: Bearer <access_token>"
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
  retrieval/conversation/message/ticket operation to that tenant's id --
  there is no code path where a chunk or ticket from another tenant can be
  touched
- The widget only ever knows a `tenant_slug` (never a raw `tenant_id` or
  any staff credential), so embedding it on a tenant's site can't leak
  access to another tenant's data or to any authenticated dashboard route

## Project layout

```
backend/
  app/
    core/       settings, JWT + password hashing, auth dependency
    db/         async SQLAlchemy engine/session (FastAPI request path)
    models/     SQLAlchemy models (mirrors init-db schema 1:1)
    schemas/    Pydantic request/response models
    services/   text extraction, chunking, Voyage AI embeddings, retrieval,
                LLM answer generation + agentic escalation (create_ticket tool)
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
- [ ] Phase 7: hardening (rate limiting, usage logging, RBAC, retries)
