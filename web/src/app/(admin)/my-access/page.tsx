"use client";

import type { ReactNode } from "react";
import { adminRoleLabel, useAdminProfile } from "@/lib/admin-permissions";

const PERMISSION_HELP: Record<string, string> = {
  VIEW: "Browse admin screens, reports, previews, traceability, and read-only data.",
  EDIT: "Edit shared admin configuration such as catalogs, workflow drafts, and conflict resolution.",
  PUBLISH: "Publish reviewed workflow and input changes to runtime-facing catalogs.",
  PROJECT_EDIT: "Edit project-scoped settings such as workflow assignments, overrides, and input enablement.",
  MANAGE_USERS: "Invite tenant users, change roles, assign project access, and revoke access.",
};

function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "blue" | "amber" }) {
  const tones = {
    neutral: "bg-gray-100 text-gray-700",
    green: "bg-green-100 text-green-800",
    blue: "bg-blue-100 text-blue-800",
    amber: "bg-amber-100 text-amber-800",
  };
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg bg-white p-5 shadow">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function formatJson(value: unknown): string {
  if (!value || (typeof value === "object" && Object.keys(value as Record<string, unknown>).length === 0)) {
    return "All assigned scope";
  }
  return JSON.stringify(value, null, 2);
}

export default function MyAccessPage() {
  const { profile, loading, error } = useAdminProfile();

  const tenantPermissions = profile?.permissions || [];
  const projectAccess = profile?.project_access || [];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">My Access</h1>
        <p className="mt-1 text-sm text-gray-500">Read-only view of your tenant role, permissions, and project assignments.</p>
      </div>

      {loading ? (
        <div className="rounded-lg bg-white p-5 text-sm text-gray-500 shadow">Loading your admin access...</div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div>
      ) : !profile ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">No admin profile found for this login.</div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs uppercase tracking-wide text-gray-500">Tenant</p>
              <p className="mt-1 text-lg font-semibold text-gray-900">{profile.tenant_id}</p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs uppercase tracking-wide text-gray-500">Tenant role</p>
              <p className="mt-1 text-lg font-semibold text-gray-900">{adminRoleLabel(profile)}</p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs uppercase tracking-wide text-gray-500">Tenant permissions</p>
              <p className="mt-1 text-lg font-semibold text-gray-900">{tenantPermissions.length}</p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow">
              <p className="text-xs uppercase tracking-wide text-gray-500">Project access</p>
              <p className="mt-1 text-lg font-semibold text-gray-900">{projectAccess.length}</p>
            </div>
          </div>

          <Section title="Identity">
            <dl className="grid gap-4 text-sm md:grid-cols-2">
              <div>
                <dt className="text-gray-500">Display name</dt>
                <dd className="mt-1 font-medium text-gray-900">{profile.display_name || "Not set"}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Mobile</dt>
                <dd className="mt-1 font-medium text-gray-900">{profile.mobile_number_masked}</dd>
              </div>
              <div>
                <dt className="text-gray-500">User ID</dt>
                <dd className="mt-1 break-all font-mono text-xs text-gray-800">{profile.user_id}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Schema version</dt>
                <dd className="mt-1 font-medium text-gray-900">{profile.schema_version}</dd>
              </div>
            </dl>
          </Section>

          <Section title="Tenant permissions">
            {tenantPermissions.length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {tenantPermissions.map((permission) => (
                  <div key={permission} className="rounded-lg border border-gray-200 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <Pill tone="green">{permission}</Pill>
                    </div>
                    <p className="mt-2 text-sm text-gray-600">{PERMISSION_HELP[permission] || "Custom permission exposed by backend."}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">No tenant permissions are assigned.</p>
            )}
          </Section>

          <Section title="Project access">
            {projectAccess.length ? (
              <div className="overflow-hidden rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-4 py-3">Project</th>
                      <th className="px-4 py-3">Role</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Permissions</th>
                      <th className="px-4 py-3">Territory scope</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {projectAccess.map((project) => (
                      <tr key={project.project_role_id}>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{project.project_name}</div>
                          <div className="mt-1 break-all font-mono text-xs text-gray-500">{project.project_id}</div>
                        </td>
                        <td className="px-4 py-3"><Pill tone="blue">{project.role.replaceAll("_", " ")}</Pill></td>
                        <td className="px-4 py-3"><Pill tone={project.project_status === "ACTIVE" ? "green" : "neutral"}>{project.project_status}</Pill></td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1.5">
                            {project.permissions.map((permission) => <Pill key={permission} tone="amber">{permission}</Pill>)}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <pre className="max-w-xs whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-600">{formatJson(project.territory_scope)}</pre>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500">No explicit project assignments. Enterprise admins may still have tenant-wide access depending on backend policy.</p>
            )}
          </Section>

          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            Backend authorization remains the source of truth. This page mirrors <code className="rounded bg-blue-100 px-1">GET /api/v1/admin/me</code> so admins can quickly debug access without touching mutation screens.
          </div>
        </div>
      )}
    </div>
  );
}
