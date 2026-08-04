-- ============================================================================
-- Phase 7 addition: per-tenant token usage logging.
-- Kept as a separate numbered file rather than editing 001_init.sql, so
-- anyone who already has a running Postgres volume from an earlier phase
-- can apply just this file instead of wiping their data. On a fresh
-- container both 001 and 002 run automatically, in filename order.
-- ============================================================================

CREATE TABLE usage_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,          -- 'anthropic' | 'voyage'
    model           TEXT NOT NULL,
    request_type    TEXT NOT NULL,          -- 'query_answer' | 'embedding'
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_usage_logs_tenant_id ON usage_logs(tenant_id);
CREATE INDEX idx_usage_logs_tenant_created ON usage_logs(tenant_id, created_at);
