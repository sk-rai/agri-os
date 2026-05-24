/**
 * Typed API client for Agri-OS backend.
 * Handles auth headers (Bearer JWT + X-Tenant-ID) and 401 redirects.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  noAuth?: boolean;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("agrios_token");
  const tenantId = localStorage.getItem("agrios_tenant_id");
  const actorId = localStorage.getItem("agrios_user_id");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenantId) headers["X-Tenant-ID"] = tenantId;
  if (actorId) headers["X-Actor-ID"] = actorId;
  return headers;
}

export async function api<T = unknown>(
  path: string,
  options: ApiOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, noAuth = false } = options;

  const fetchHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(!noAuth ? getAuthHeaders() : {}),
    ...headers,
  };

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: fetchHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("agrios_token");
    window.location.href = "/login";
    throw new ApiError("Unauthorized", 401);
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(error.detail || res.statusText, res.status);
  }

  return res.json() as Promise<T>;
}

// --- Typed API functions ---

export interface Tenant {
  id: string;
  name: string;
  type: string;
  is_active: boolean;
}

export interface Project {
  id: string;
  tenant_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  geography_scope: Record<string, unknown>;
  crop_scope: string[];
}

export interface SyncHealth {
  total_events_processed: number;
  committed: number;
  conflicts_pending: number;
  conflicts_resolved: number;
  failed: number;
  last_sync_at: string | null;
  audit_chain_length: number;
  audit_chain_intact: boolean;
}

export interface Dashboard {
  tenant_id: string;
  sync_health: SyncHealth;
  generated_at: string;
}

export interface Conflict {
  id: string;
  event_id: string;
  entity_type: string;
  entity_id: string;
  conflict_type: string;
  client_payload: Record<string, unknown>;
  server_payload: Record<string, unknown> | null;
  resolution_strategy: string | null;
  status: string;
  created_at: string;
}

// Auth
export const authApi = {
  requestOtp: (mobile_number: string) =>
    api("/api/v1/auth/otp/request", { method: "POST", body: { mobile_number }, noAuth: true }),
  verifyOtp: (mobile_number: string, otp_code: string, device_id: string) =>
    api("/api/v1/auth/otp/verify", { method: "POST", body: { mobile_number, otp_code, device_id }, noAuth: true }),
};

// Tenants
export const tenantsApi = {
  list: () => api<Tenant[]>("/api/v1/tenants", { noAuth: true }),
  create: (data: { id: string; name: string; type: string }) =>
    api<Tenant>("/api/v1/tenants", { method: "POST", body: data, noAuth: true }),
};

// Projects
export const projectsApi = {
  list: () => api<Project[]>("/api/v1/projects"),
  create: (data: Partial<Project>) => api<Project>("/api/v1/projects", { method: "POST", body: data }),
  assignRole: (projectId: string, data: { user_id: string; role: string; territory_scope: Record<string, unknown> }) =>
    api(`/api/v1/projects/${projectId}/roles`, { method: "POST", body: data }),
};

// Dashboard
export const dashboardApi = {
  getOperational: () => api<Dashboard>("/api/v1/dashboard/operational"),
};

// Conflicts
export const conflictsApi = {
  list: (status?: string) => api<Conflict[]>(`/api/v1/sync/conflicts${status ? `?status=${status}` : ""}`),
  get: (id: string) => api<Conflict>(`/api/v1/sync/conflicts/${id}`),
  resolve: (id: string, strategy: string, comment?: string) =>
    api(`/api/v1/sync/conflicts/${id}`, { method: "PATCH", body: { strategy, comment } }),
};
