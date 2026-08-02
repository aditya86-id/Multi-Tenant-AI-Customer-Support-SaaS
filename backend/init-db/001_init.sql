-- ============================================================================
-- AI Customer Support SaaS — initial schema
-- Multi-tenant: every domain table carries tenant_id and is always queried
-- scoped to it. This file is mounted into postgres's docker-entrypoint-initdb.d
-- and runs once on first container start. For schema changes after that,
-- add an Alembic migration instead of editing this file.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------------
-- tenants: one row per customer company using the SaaS
-- ----------------------------------------------------------------------------
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,           -- used in widget embed + subdomains
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- users: staff/admin/agent accounts. ALWAYS scoped by tenant_id.
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'admin',  -- 'admin' | 'agent' (RBAC hardened in phase 7)
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)                       -- same email can exist in >1 tenant
);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);

-- ----------------------------------------------------------------------------
-- documents: uploaded KB source files (docs, FAQs, past tickets) per tenant
-- ----------------------------------------------------------------------------
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    uploaded_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    filename        TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'upload', -- 'upload' | 'faq' | 'ticket_history'
    status          TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'processing' | 'ready' | 'failed'
    error_message   TEXT,
    storage_path    TEXT,                            -- where the raw file lives
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX idx_documents_tenant_status ON documents(tenant_id, status);

-- ----------------------------------------------------------------------------
-- chunks: embedded chunks of a document, used for RAG retrieval.
-- vector(1536) sized for common embedding models; adjust if you pick another.
-- ----------------------------------------------------------------------------
CREATE TABLE chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(1536),
    token_count     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunks_tenant_id ON chunks(tenant_id);
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
-- ANN index for cosine similarity search, scoped queries still filter by tenant_id first
CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ----------------------------------------------------------------------------
-- conversations: one per end-customer chat session with the widget
-- ----------------------------------------------------------------------------
CREATE TABLE conversations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    end_user_identifier TEXT,                         -- opaque id/email the tenant's site passes in
    status              TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'escalated' | 'resolved' | 'closed'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_conversations_tenant_id ON conversations(tenant_id);

-- ----------------------------------------------------------------------------
-- messages: individual turns within a conversation
-- ----------------------------------------------------------------------------
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,                    -- 'user' | 'assistant' | 'system'
    content         TEXT NOT NULL,
    retrieved_chunk_ids UUID[] DEFAULT '{}',           -- citations used to answer, if any
    confidence      REAL,                              -- retrieval/answer confidence signal (phase 4)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_tenant_id ON messages(tenant_id);
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);

-- ----------------------------------------------------------------------------
-- tickets: created when the AI escalates or the user asks for a human
-- ----------------------------------------------------------------------------
CREATE TABLE tickets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    assigned_to     UUID REFERENCES users(id) ON DELETE SET NULL,
    subject         TEXT NOT NULL,
    summary         TEXT,                               -- AI-generated summary of the issue
    status          TEXT NOT NULL DEFAULT 'open',        -- 'open' | 'in_progress' | 'resolved' | 'closed'
    priority        TEXT NOT NULL DEFAULT 'normal',      -- 'low' | 'normal' | 'high' | 'urgent'
    escalation_reason TEXT,                              -- 'low_confidence' | 'user_requested' | ...
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tickets_tenant_id ON tickets(tenant_id);
CREATE INDEX idx_tickets_tenant_status ON tickets(tenant_id, status);
