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
      <div className="container">
        <p className="muted">Loading...</p>
      </div>
    );
  }

  const resolvedTickets = tickets.filter((t) => t.status === "resolved" || t.status === "closed").length;
  const resolutionRate = tickets.length ? Math.round((resolvedTickets / tickets.length) * 100) : 0;
  const readyDocs = documents.filter((d) => d.status === "ready").length;
  const failedDocs = documents.filter((d) => d.status === "failed").length;

  return (
    <div className="container">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0 }}>{tenant?.name ?? "Dashboard"}</h1>
          <p className="muted" style={{ margin: 0 }}>tenant: {tenant?.slug}</p>
        </div>
        <button className="btn-secondary" onClick={handleLogout}>
          Log out
        </button>
      </div>

      {error && (
        <div className="card">
          <p className="error-text" style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      <div className="tabs">
        {(["documents", "tickets", "analytics"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "documents" && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Knowledge base documents</h2>
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
          </div>
          {documents.length === 0 ? (
            <p className="muted">No documents uploaded yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>{doc.filename}</td>
                    <td>
                      <span className={`badge badge-${doc.status}`}>{doc.status}</span>
                      {doc.status === "failed" && doc.error_message && (
                        <div className="muted" style={{ marginTop: 4 }}>{doc.error_message}</div>
                      )}
                    </td>
                    <td className="muted">{new Date(doc.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "tickets" && (
        <div className="card">
          <h2 style={{ margin: "0 0 12px", fontSize: 18 }}>Ticket queue</h2>
          {tickets.length === 0 ? (
            <p className="muted">No tickets yet -- escalations from the AI will show up here.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th>Opened</th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((ticket) => (
                  <tr key={ticket.id}>
                    <td>
                      {ticket.subject}
                      {ticket.summary && (
                        <div className="muted" style={{ marginTop: 4 }}>{ticket.summary}</div>
                      )}
                    </td>
                    <td>
                      <span className={`badge badge-${ticket.priority}`}>{ticket.priority}</span>
                    </td>
                    <td>
                      <span className={`badge badge-${ticket.status}`}>{ticket.status}</span>
                    </td>
                    <td className="muted">{ticket.escalation_reason ?? "-"}</td>
                    <td className="muted">{new Date(ticket.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "analytics" && (
        <div className="card">
          <h2 style={{ margin: "0 0 16px", fontSize: 18 }}>Overview</h2>
          <div className="stat-grid">
            <div>
              <div className="stat-value">{tickets.length}</div>
              <div className="muted">Total tickets</div>
            </div>
            <div>
              <div className="stat-value">{resolutionRate}%</div>
              <div className="muted">Resolution rate</div>
            </div>
            <div>
              <div className="stat-value">{documents.length}</div>
              <div className="muted">Documents uploaded</div>
            </div>
            <div>
              <div className="stat-value">{readyDocs}</div>
              <div className="muted">Ready for retrieval</div>
            </div>
            <div>
              <div className="stat-value">{failedDocs}</div>
              <div className="muted">Failed ingestion</div>
            </div>
          </div>
          <p className="muted" style={{ marginTop: 20 }}>
            Escalation rate and message-volume trends need a conversations/messages
            listing endpoint, which isn&apos;t built yet -- straightforward to add
            as a phase 7 follow-up once per-tenant usage logging is in place.
          </p>
        </div>
      )}
    </div>
  );
}
