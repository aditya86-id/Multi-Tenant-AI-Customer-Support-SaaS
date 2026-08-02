# AI Customer Support SaaS (multi-tenant, RAG + agentic escalation)

Companies (tenants) upload their knowledge base. End customers chat with an
embeddable AI widget that answers from that tenant's knowledge base using
RAG, and escalates to a human (creates a ticket) when it's not confident or
the user asks for one.

## Status: Phase 1 -- scaffold, schema, auth, tenant CRUD

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
- Docker Compose: Postgres (pgvector image), Redis (ready for phase 2), API

Not yet built (coming in later phases): document ingestion, RAG query
endpoint, agentic escalation via Claude tool use, Next.js admin dashboard,
embeddable widget, rate limiting / usage logging / retries.

## Running locally

```bash
cp .env.example .env
# edit .env: set a real JWT_SECRET_KEY, and later ANTHROPIC_API_KEY

docker compose up --build
```

The API will be available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`.

## Try it

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

## Project layout

```
backend/
  app/
    core/       settings, JWT + password hashing, auth dependency
    db/         async SQLAlchemy engine/session
    models/     SQLAlchemy models (mirrors init-db schema 1:1)
    schemas/    Pydantic request/response models
    api/routes/ auth, tenants, users
    main.py     FastAPI app, CORS, global error handlers
  init-db/      raw SQL run once by Postgres on first container start
  Dockerfile
docker-compose.yml
```

## Roadmap

- [x] Phase 1: scaffold, schema, JWT auth, tenant CRUD
- [ ] Phase 2: document ingestion (upload + Celery chunk/embed into pgvector)
- [ ] Phase 3: RAG query endpoint with source citations
- [ ] Phase 4: agentic escalation via Claude tool use (create_ticket tool)
- [ ] Phase 5: Next.js admin dashboard
- [ ] Phase 6: embeddable JS widget
- [ ] Phase 7: hardening (rate limiting, usage logging, RBAC, retries)
