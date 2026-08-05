# Multi-Tenant AI Customer Support SaaS

A support platform where companies (tenants) upload their knowledge base and end customers get instant answers from an embeddable AI chat widget. Answers are generated with retrieval-augmented generation (RAG) over each tenant's own documents, and the AI opens a support ticket on its own judgment when a question needs a human.

## Features

- **Multi-tenant by design** — every table is scoped by `tenant_id`, enforced at the query level, not just by convention
- **Knowledge base ingestion** — upload `.txt`/`.md`/`.pdf` files; a background worker chunks, embeds, and indexes them for retrieval
- **RAG-powered answers** — responses are grounded in the tenant's own documents, with source citations
- **Agentic escalation** — the AI has a real tool to open a support ticket, deciding for itself when a question needs a human instead of following a hardcoded confidence threshold
- **Admin dashboard** — manage documents, review the ticket queue, and see basic usage analytics
- **Embeddable widget** — a single `<script>` tag, no build step, drops a chat bubble onto any site
- **Per-tenant rate limiting and usage logging** — protects against noisy neighbors and tracks token usage per tenant

## Tech stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (async), PostgreSQL + pgvector |
| Background jobs | Celery + Redis |
| LLM | Anthropic Claude (native tool use) |
| Embeddings | Voyage AI |
| Admin dashboard | Next.js, TypeScript |
| Widget | Vanilla JS, no dependencies |
| Auth | JWT |

## Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for the dashboard)
- API keys: [Anthropic](https://console.anthropic.com/) and [Voyage AI](https://www.voyageai.com/)

## Installation

Clone the repo and set up the backend:

```bash
git clone https://github.com/aditya86-id/Multi-Tenant-AI-Customer-Support-SaaS.git
cd Multi-Tenant-AI-Customer-Support-SaaS
cp .env.example .env
# set JWT_SECRET_KEY, VOYAGE_API_KEY, and ANTHROPIC_API_KEY in .env

docker compose up --build
```

The API is now running at `http://localhost:8000` (interactive docs at `/docs`), with Postgres, Redis, and the Celery worker started alongside it.

Set up the dashboard:

```bash
cd dashboard
cp .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000` and create a tenant to get started.

Try the widget locally:

```bash
cd widget
python3 -m http.server 5500
```

Open `http://localhost:5500/demo.html` with the backend running.

## Usage

Create a tenant and get an access token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"tenant_name": "Acme Inc", "tenant_slug": "acme", "admin_email": "admin@acme.com", "admin_password": "supersecret123"}'
```

Upload a knowledge base document:

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@./faq.md"
```

Ask a question (this is the same endpoint the embeddable widget calls — no auth required, scoped by `tenant_slug`):

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug": "acme", "message": "What is your refund policy?"}'
```

To embed the widget on any page, copy the `<script>` tag from `widget/demo.html`:

```html
<script
  src="https://your-domain.example/widget.js"
  data-tenant-slug="acme"
  data-api-url="https://api.your-domain.example"
></script>
```

## Project layout

```
backend/     FastAPI app, Postgres schema, Celery worker
dashboard/   Next.js admin dashboard
widget/      embeddable chat widget
```

## Contributing

Issues and pull requests are welcome. For larger changes, please open an issue first to discuss what you'd like to change.

## License

MIT
