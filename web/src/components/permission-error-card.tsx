"use client";

import { ApiError, type ApiErrorDetail } from "@/lib/api";

function asPermissionDetail(error: unknown): Extract<ApiErrorDetail, object> | null {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object") {
    return error.detail.error === "ADMIN_PERMISSION_DENIED" ? error.detail : null;
  }
  return null;
}

export function getErrorMessage(error: unknown, fallback = "Operation failed"): string {
  return error instanceof Error ? error.message : fallback;
}

export function isPermissionDenied(error: unknown): boolean {
  return asPermissionDetail(error) !== null;
}

export function PermissionErrorCard({ error, className = "" }: { error: unknown; className?: string }) {
  const detail = asPermissionDetail(error);
  if (!detail) return null;

  const currentPermissions = Array.isArray(detail.current_permissions) ? detail.current_permissions : [];

  return (
    <div className={`rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950 ${className}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold">Permission denied</p>
          <p className="mt-1 text-amber-900">{typeof detail.message === "string" ? detail.message : "Your current admin role cannot perform this action."}</p>
        </div>
        {typeof detail.required_permission === "string" ? (
          <span className="shrink-0 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
            Requires {detail.required_permission}
          </span>
        ) : null}
      </div>

      <dl className="mt-3 grid gap-2 md:grid-cols-2">
        {typeof detail.current_role === "string" ? (
          <div>
            <dt className="text-xs uppercase tracking-wide text-amber-700">Current role</dt>
            <dd className="mt-0.5 font-medium">{detail.current_role.replaceAll("_", " ")}</dd>
          </div>
        ) : null}
        {currentPermissions.length ? (
          <div>
            <dt className="text-xs uppercase tracking-wide text-amber-700">Current permissions</dt>
            <dd className="mt-0.5 flex flex-wrap gap-1">
              {currentPermissions.map((permission) => (
                <span key={permission} className="rounded bg-white/70 px-2 py-0.5 text-xs font-medium">{permission}</span>
              ))}
            </dd>
          </div>
        ) : null}
        {typeof detail.tenant_id === "string" ? (
          <div>
            <dt className="text-xs uppercase tracking-wide text-amber-700">Tenant</dt>
            <dd className="mt-0.5 font-mono text-xs">{detail.tenant_id}</dd>
          </div>
        ) : null}
        {typeof detail.project_id === "string" ? (
          <div>
            <dt className="text-xs uppercase tracking-wide text-amber-700">Project</dt>
            <dd className="mt-0.5 break-all font-mono text-xs">{detail.project_id}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}
