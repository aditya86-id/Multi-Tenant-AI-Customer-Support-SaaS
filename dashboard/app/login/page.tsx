"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, signup, setToken, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [tenantSlug, setTenantSlug] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result =
        mode === "login"
          ? await login(tenantSlug, email, password)
          : await signup(tenantName, tenantSlug, email, password);
      setToken(result.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container" style={{ maxWidth: 420, paddingTop: 80 }}>
      <div className="card">
        <h1 style={{ marginTop: 0 }}>
          {mode === "login" ? "Sign in" : "Create your tenant"}
        </h1>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {mode === "signup" && (
            <label>
              Company name
              <input
                type="text"
                required
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                style={{ width: "100%", marginTop: 4 }}
              />
            </label>
          )}
          <label>
            Tenant slug
            <input
              type="text"
              required
              pattern="[a-z0-9-]+"
              placeholder="acme"
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
          {error && <p className="error-text">{error}</p>}
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create tenant"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: 16 }}>
          {mode === "login" ? "New here?" : "Already have a tenant?"}{" "}
          <button
            type="button"
            className="btn-secondary"
            style={{ padding: "2px 8px" }}
            onClick={() => {
              setError(null);
              setMode(mode === "login" ? "signup" : "login");
            }}
          >
            {mode === "login" ? "Create one" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}
