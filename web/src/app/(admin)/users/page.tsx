"use client";

import { useEffect, useMemo, useState } from "react";
import {
  authApi,
  projectsApi,
  tenantAdminUsersApi,
  type AdminProfileResponse,
  type Project,
  type TenantAdminUser,
  type UserAccessAuditEvent,
} from "@/lib/api";

export default function TenantUsersPage() {
  const [users, setUsers] = useState<TenantAdminUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [projectRoles, setProjectRoles] = useState<string[]>([]);
  const [adminProfile, setAdminProfile] = useState<AdminProfileResponse | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [selectedId, setSelectedId] = useState("");
  const [audit, setAudit] = useState<UserAccessAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [invite, setInvite] = useState({
    mobile_number: "",
    display_name: "",
    role: "ADMIN_VIEWER",
    reason: "Tenant admin invitation",
  });
  const [roleDraft, setRoleDraft] = useState({ role: "", display_name: "", reason: "" });
  const [projectDraft, setProjectDraft] = useState({ project_id: "", role: "ADMIN_VIEWER", reason: "" });

  const canManageUsers = adminProfile?.permissions.includes("MANAGE_USERS") ?? false;

  const selected = useMemo(
    () => users.find((user) => user.id === selectedId) || null,
    [users, selectedId]
  );

  const load = async (preferredId?: string) => {
    setLoading(true);
    setError("");
    try {
      const [userPayload, projectPayload] = await Promise.all([
        tenantAdminUsersApi.list(),
        projectsApi.list(),
      ]);
      setUsers(userPayload.users);
      setRoles(userPayload.available_roles);
      setProjectRoles(userPayload.project_roles);
      setProjects(projectPayload);
      setSelectedId((current) => {
        const target = preferredId || current;
        return userPayload.users.some((user) => user.id === target)
          ? target
          : userPayload.users[0]?.id || "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tenant users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    authApi.me()
      .then((profile) => {
        setAdminProfile(profile);
        if (profile.permissions.includes("MANAGE_USERS")) {
          void load();
        } else {
          setLoading(false);
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load admin profile");
        setLoading(false);
      })
      .finally(() => setLoadingProfile(false));
  }, []);

  useEffect(() => {
    if (!selected) {
      setAudit([]);
      return;
    }
    setRoleDraft({
      role: selected.role,
      display_name: selected.display_name || "",
      reason: "",
    });
    tenantAdminUsersApi.audit(selected.id).then((payload) => setAudit(payload.events)).catch(() => setAudit([]));
  }, [selected]);

  const run = async (action: () => Promise<TenantAdminUser | string>, success: string) => {
    if (!canManageUsers) {
      setError("Your current role can view admin identity but cannot manage tenant users.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await action();
      await load(typeof result === "string" ? result : result.id);
      setNotice(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setSaving(false);
    }
  };

  const inviteUser = () => run(async () => {
    const response = await tenantAdminUsersApi.invite({
      mobile_number: invite.mobile_number,
      display_name: invite.display_name || null,
      role: invite.role,
      reason: invite.reason,
    });
    setInvite({ mobile_number: "", display_name: "", role: "ADMIN_VIEWER", reason: "Tenant admin invitation" });
    return response.user;
  }, "Tenant user invited or assigned.");

  const changeRole = () => {
    if (!selected) return;
    return run(async () => {
      const response = await tenantAdminUsersApi.changeRole(selected.id, {
        role: roleDraft.role,
        display_name: roleDraft.display_name || null,
        reason: roleDraft.reason,
      });
      return response.user;
    }, "Tenant role updated.");
  };

  const revokeUser = () => {
    if (!selected || !roleDraft.reason) return;
    return run(async () => {
      await tenantAdminUsersApi.revoke(selected.id, roleDraft.reason);
      return "";
    }, "Tenant access revoked.");
  };

  const assignProject = () => {
    if (!selected) return;
    return run(async () => {
      const response = await tenantAdminUsersApi.assignProject(selected.id, projectDraft.project_id, {
        role: projectDraft.role,
        territory_scope: {},
        reason: projectDraft.reason,
      });
      setProjectDraft({ project_id: "", role: "ADMIN_VIEWER", reason: "" });
      return response.user;
    }, "Project access assigned.");
  };

  const revokeProject = (projectId: string) => {
    if (!selected) return;
    const reason = window.prompt("Reason for revoking this project access?");
    if (!reason) return;
    return run(async () => {
      const response = await tenantAdminUsersApi.revokeProject(selected.id, projectId, reason);
      return response.user;
    }, "Project access revoked.");
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tenant Users</h1>
        <p className="mt-1 text-sm text-gray-500">Delegate view, edit, publish, and project-specific access.</p>
      </div>

      {error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {notice ? <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700">{notice}</div> : null}

      {loadingProfile ? (
        <div className="mb-6 rounded-lg bg-white p-5 text-sm text-gray-500 shadow">Checking admin permissions...</div>
      ) : !canManageUsers ? (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          <p className="font-semibold">User management is read-only for your role</p>
          <p className="mt-1">Your current role ({(adminProfile?.role || "UNASSIGNED").replaceAll("_", " ")}) does not include MANAGE_USERS. Ask an Enterprise Admin to invite users, change roles, or assign project access.</p>
        </div>
      ) : null}

      {canManageUsers ? <section className="mb-6 rounded-lg bg-white p-5 shadow">
        <h2 className="font-semibold text-gray-900">Invite or assign tenant user</h2>
        <p className="mb-4 mt-1 text-xs text-gray-500">Users can be invited before their first OTP login.</p>
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Mobile number" value={invite.mobile_number} onChange={(value) => setInvite({ ...invite, mobile_number: value })} />
          <Field label="Display name" value={invite.display_name} onChange={(value) => setInvite({ ...invite, display_name: value })} />
          <RoleSelect label="Tenant role" value={invite.role} roles={roles} onChange={(value) => setInvite({ ...invite, role: value })} />
          <Field label="Reason" value={invite.reason} onChange={(value) => setInvite({ ...invite, reason: value })} />
        </div>
        <button type="button" disabled={saving || !invite.mobile_number || !invite.reason} onClick={inviteUser} className="mt-4 rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          Invite / assign
        </button>
      </section> : null}

      {!canManageUsers ? null : loading ? <p className="text-sm text-gray-500">Loading tenant users...</p> : (
        <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
          <section className="overflow-hidden rounded-lg bg-white shadow">
            <div className="border-b px-4 py-3 text-sm font-semibold text-gray-900">Users ({users.length})</div>
            <div className="divide-y">
              {users.map((user) => (
                <button type="button" key={user.id} onClick={() => setSelectedId(user.id)} className={`block w-full p-4 text-left text-sm ${selectedId === user.id ? "bg-green-50" : "hover:bg-gray-50"}`}>
                  <p className="font-medium text-gray-900">{user.display_name || "Unnamed user"}</p>
                  <p className="mt-1 text-xs text-gray-500">{user.mobile_number_masked}</p>
                  <span className="mt-2 inline-block rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{user.role}</span>
                </button>
              ))}
            </div>
          </section>

          {selected ? (
            <section className="rounded-lg bg-white p-5 shadow">
              <h2 className="text-lg font-semibold text-gray-900">{selected.display_name || selected.mobile_number_masked}</h2>
              <p className="text-xs text-gray-500">{selected.mobile_number_masked} · {selected.login_count} logins</p>
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <Field label="Display name" value={roleDraft.display_name} onChange={(value) => setRoleDraft({ ...roleDraft, display_name: value })} />
                <RoleSelect label="Tenant role" value={roleDraft.role} roles={roles} onChange={(value) => setRoleDraft({ ...roleDraft, role: value })} />
                <Field label="Change reason" value={roleDraft.reason} onChange={(value) => setRoleDraft({ ...roleDraft, reason: value })} />
              </div>
              <div className="mt-3 flex gap-2">
                <button type="button" disabled={saving || !roleDraft.reason} onClick={changeRole} className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50">Save role</button>
                <button type="button" disabled={saving || !roleDraft.reason} onClick={revokeUser} className="rounded border border-red-200 px-3 py-2 text-sm text-red-700 disabled:opacity-50">Revoke tenant access</button>
              </div>

              <div className="mt-6 border-t pt-5">
                <h3 className="text-sm font-semibold text-gray-900">Project access</h3>
                <div className="mt-3 space-y-2">
                  {selected.project_access.map((access) => (
                    <div key={access.project_id} className="flex items-center justify-between rounded border p-3 text-sm">
                      <div><p className="font-medium text-gray-800">{access.project_name}</p><p className="text-xs text-gray-500">{access.role} · {access.project_status}</p></div>
                      <button type="button" onClick={() => revokeProject(access.project_id)} className="text-xs text-red-600">Revoke</button>
                    </div>
                  ))}
                  {selected.project_access.length === 0 ? <p className="text-xs text-gray-400">No project-specific access.</p> : null}
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  <label className="text-xs font-medium text-gray-500">Project
                    <select value={projectDraft.project_id} onChange={(event) => setProjectDraft({ ...projectDraft, project_id: event.target.value })} className="mt-1 w-full rounded border px-3 py-2 text-sm text-gray-900">
                      <option value="">Select project</option>
                      {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                    </select>
                  </label>
                  <RoleSelect label="Project role" value={projectDraft.role} roles={projectRoles} onChange={(value) => setProjectDraft({ ...projectDraft, role: value })} />
                  <Field label="Reason" value={projectDraft.reason} onChange={(value) => setProjectDraft({ ...projectDraft, reason: value })} />
                </div>
                <button type="button" disabled={saving || !projectDraft.project_id || !projectDraft.reason} onClick={assignProject} className="mt-3 rounded border px-3 py-2 text-sm text-gray-700 disabled:opacity-50">Assign project</button>
              </div>

              <div className="mt-6 border-t pt-5">
                <h3 className="text-sm font-semibold text-gray-900">Access audit</h3>
                <div className="mt-3 max-h-72 space-y-2 overflow-auto">
                  {audit.map((event) => (
                    <details key={event.id} className="rounded border p-3 text-xs">
                      <summary className="cursor-pointer font-medium text-gray-800">{event.action.replaceAll("_", " ")} · {new Date(event.created_at).toLocaleString()}</summary>
                      <p className="mt-2 text-gray-600">Reason: {event.reason || "-"}</p>
                      <pre className="mt-2 overflow-auto rounded bg-gray-50 p-2 text-[10px] text-gray-600">{JSON.stringify({ before: event.before, after: event.after }, null, 2)}</pre>
                    </details>
                  ))}
                </div>
              </div>
            </section>
          ) : <section className="rounded-lg bg-white p-6 text-sm text-gray-400 shadow">Select a user.</section>}
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs font-medium text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal text-gray-900" /></label>;
}

function RoleSelect({ label, value, roles, onChange }: { label: string; value: string; roles: string[]; onChange: (value: string) => void }) {
  return <label className="text-xs font-medium text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal text-gray-900">{roles.map((role) => <option key={role} value={role}>{role.replaceAll("_", " ")}</option>)}</select></label>;
}
