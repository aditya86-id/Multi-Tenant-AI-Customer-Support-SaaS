const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "support_saas_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // response wasn't JSON -- fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

// ---- Types (mirror backend Pydantic response schemas) ----

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
}

export interface Document {
  id: string;
  tenant_id: string;
  filename: string;
  source_type: string;
  status: "pending" | "processing" | "ready" | "failed";
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Ticket {
  id: string;
  tenant_id: string;
  conversation_id: string | null;
  assigned_to: string | null;
  subject: string;
  summary: string | null;
  status: "open" | "in_progress" | "resolved" | "closed";
  priority: "low" | "normal" | "high" | "urgent";
  escalation_reason: string | null;
  created_at: string;
  updated_at: string;
}

// ---- Auth ----

export function login(tenant_slug: string, email: string, password: string) {
  return request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ tenant_slug, email, password }),
  });
}

export function signup(
  tenant_name: string,
  tenant_slug: string,
  admin_email: string,
  admin_password: string
) {
  return request<TokenResponse>("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify({ tenant_name, tenant_slug, admin_email, admin_password }),
  });
}

export function getMyTenant() {
  return request<Tenant>("/api/v1/tenants/me");
}

// ---- Documents ----

export function listDocuments() {
  return request<Document[]>("/api/v1/documents");
}

export async function uploadDocument(file: File): Promise<Document> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // ignore
    }
    throw new ApiError(response.status, detail);
  }
  return response.json();
}

// ---- Tickets ----

export function listTickets() {
  return request<Ticket[]>("/api/v1/tickets");
}
