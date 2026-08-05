"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  getMyTenant,
  listDocuments,
  uploadDocument,
  listTickets,
  clearToken,
  getToken,
  ApiError,
  type Tenant,
  type Document,
  type Ticket,
} from "@/lib/api";

type Tab = "documents" | "tickets" | "analytics";

const NAV_ITEMS: { id: Tab; label: string; icon: string }[] = [
  { id: "documents", label: "Documents", icon: "\u25A4" },
  { id: "tickets", label: "Tickets", icon: "\u2691" },
  { id: "analytics", label: "Analytics", icon: "\u25B3" },
];

// Maps backend status strings to the rail's three-state visual language.
function railClass(status: string): "rail-good" | "rail-warn" | "rail-bad" {
  if (status === "ready" || status === "resolved" || status === "closed") return "rail-good";
  if (status === "failed" || status === "urgent" || status === "high") return "rail-bad";
  return "rail-warn";
}
function statusWordClass(status: string): "good" | "warn" | "bad" {
  const rail = railClass(status);
  if (rail === "rail-good") return "good";
  if (rail === "rail-bad") return "bad";
  return "warn";
}

export default function DashboardPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [tab, setTab] = useState<Tab>("documents");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const loadAll = useCallback(async () => {
    setError(null);
    try {
      const [tenantRes, docsRes, ticketsRes] = await Promise.all([
        getMyTenant(),
        listDocuments(),
        listTickets(),
      ]);
      setTenant(tenantRes);
      setDocuments(docsRes);
      setTickets(ticketsRes);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        router.push("/login");
        return;
      }
      setError(err instanceof ApiError ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    loadAll();
  }, [loadAll, router]);

  // Poll every 5s while any document is still ingesting, so status updates
  // (pending -> processing -> ready) show up without a manual refresh.
  useEffect(() => {
    const hasInFlight = documents.some((d) => d.status === "pending" || d.status === "processing");
    if (!hasInFlight) return;
    const interval = setInterval(loadAll, 5000);
    return () => clearInterval(interval);
  }, [documents, loadAll]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDocument(file);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  if (loading) {
    return (
      <div className="shell">
        <div className="content">
          <p className="empty-state">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  const resolvedTickets = tickets.filter((t) => t.status === "resolved" || t.status === "closed").length;
  const resolutionRate = tickets.length ? Math.round((resolvedTickets / tickets.length) * 100) : 0;
  const readyDocs = documents.filter((d) => d.status === "ready").length;
  const failedDocs = documents.filter((d) => d.status === "failed").length;
  const openTickets = tickets.filter((t) => t.status === "open" || t.status === "in_progress").length;

  const activeLabel = NAV_ITEMS.find((n) => n.id === tab)?.label ?? "";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="tenant-name">{tenant?.name ?? "Dashboard"}</div>
          <div className="tenant-slug">{tenant?.slug}</div>
        </div>

        <nav className="nav-group">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${tab === item.id ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
              {item.id === "tickets" && openTickets > 0 && (
                <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  {openTickets}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="nav-item" onClick={handleLogout}>
            <span className="nav-icon">&larr;</span>
            Log out
          </button>
        </div>
      </aside>

      <main className="content">
        <div className="page-header">
          <div>
            <h1>{activeLabel}</h1>
            <div className="page-sub">
              {tab === "documents" && "Files powering this tenant's AI answers"}
              {tab === "tickets" && "Conversations the AI escalated to a human"}
              {tab === "analytics" && "Usage at a glance"}
            </div>
          </div>
          {tab === "documents" && (
            <label className="btn" style={{ display: "inline-block" }}>
              {uploading ? "Uploading..." : "Upload document"}
              <input
                type="file"
                accept=".txt,.md,.pdf"
                onChange={handleUpload}
                disabled={uploading}
                style={{ display: "none" }}
              />
            </label>
          )}
        </div>

        {error && <div className="error-banner">{error}</div>}

        {tab === "documents" && (
          <div className="card">
            {documents.length === 0 ? (
              <div className="empty-state">
                No documents yet. Upload a .txt, .md, or .pdf to give the AI something to answer from.
              </div>
            ) : (
              documents.map((doc) => (
                <div key={doc.id} className={`rail-row ${railClass(doc.status)}`}>
                  <div className="rail-main">
                    <div className="rail-title">{doc.filename}</div>
                    {doc.status === "failed" && doc.error_message && (
                      <div className="rail-sub">{doc.error_message}</div>
                    )}
                  </div>
                  <span className={`status-word ${statusWordClass(doc.status)}`}>{doc.status}</span>
                  <span className="rail-meta">{new Date(doc.created_at).toLocaleDateString()}</span>
                </div>
              ))
            )}
          </div>
        )}

        {tab === "tickets" && (
          <div className="card">
            {tickets.length === 0 ? (
              <div className="empty-state">
                No tickets yet. The AI opens one automatically when it can&apos;t answer confidently
                or a customer asks for a human.
              </div>
            ) : (
              tickets.map((ticket) => (
                <div key={ticket.id} className={`rail-row ${railClass(ticket.priority)}`}>
                  <div className="rail-main">
                    <div className="rail-title">{ticket.subject}</div>
                    {ticket.summary && <div className="rail-sub">{ticket.summary}</div>}
                  </div>
                  <span className={`status-word ${statusWordClass(ticket.status)}`}>{ticket.status}</span>
                  <span className="rail-meta">{new Date(ticket.created_at).toLocaleDateString()}</span>
                </div>
              ))
            )}
          </div>
        )}

        {tab === "analytics" && (
          <div className="card">
            <div className="stat-grid">
              <div className="stat-block">
                <div className="stat-value">{tickets.length}</div>
                <div className="stat-label">Total tickets</div>
              </div>
              <div className="stat-block">
                <div className="stat-value">{resolutionRate}%</div>
                <div className="stat-label">Resolution rate</div>
              </div>
              <div className="stat-block">
                <div className="stat-value">{documents.length}</div>
                <div className="stat-label">Documents</div>
              </div>
              <div className="stat-block">
                <div className="stat-value">{readyDocs}</div>
                <div className="stat-label">Ready for retrieval</div>
              </div>
              <div className="stat-block">
                <div className="stat-value">{failedDocs}</div>
                <div className="stat-label">Failed ingestion</div>
              </div>
            </div>
            <p className="page-sub" style={{ marginTop: 20 }}>
              Escalation rate and message-volume trends need a conversations listing endpoint,
              which isn&apos;t built yet.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
