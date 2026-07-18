"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { agentProfilesApi, type AgentProfileDto, type AgentProfilesResponse } from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";
import { getErrorMessage, isPermissionDenied, PermissionErrorCard } from "@/components/permission-error-card";

const ROLE_TYPES = ["", "FIELD_AGENT", "AGRONOMIST", "DEALER", "MANAGER", "ENUMERATOR"];
const STATUSES = ["", "ACTIVE", "INACTIVE", "SUSPENDED"];

export default function AgentProfilesPage() {
  const { profile: adminProfile, loading: loadingProfile, error: profileError } = useAdminProfile();
  const canManageUsers = hasAdminPermission(adminProfile, "MANAGE_USERS");
  const [roleType, setRoleType] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [payload, setPayload] = useState<AgentProfilesResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const selected = useMemo(() => payload?.agent_profiles.find((profile) => profile.id === selectedId) || payload?.agent_profiles[0] || null, [payload, selectedId]);

  async function load(preferredId?: string) {
    setLoading(true);
    setError(null);
    try {
      const next = await agentProfilesApi.list({ roleType: roleType || undefined, status: status || undefined });
      setPayload(next);
      setSelectedId((current) => {
        const target = preferredId || current;
        return next.agent_profiles.some((profile) => profile.id === target) ? target : next.agent_profiles[0]?.id || "";
      });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (loadingProfile) return;
    if (profileError) {
      setError(profileError);
      setLoading(false);
      return;
    }
    if (canManageUsers) void load();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingProfile, profileError, canManageUsers]);

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Agent Profiles</h1>
      <p className="mt-1 text-sm text-gray-500">Operational profiles for field agents, agronomists, dealers, and dual-capacity farmer-agents.</p>
    </div>

    {isPermissionDenied(error) ? <PermissionErrorCard error={error} className="mb-4" /> : error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{getErrorMessage(error)}</div> : null}
    {loadingProfile ? <div className="mb-6 rounded bg-white p-5 text-sm text-gray-500 shadow">Checking admin permissions...</div> : !canManageUsers ? <div className="mb-6 rounded border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"><p className="font-semibold">Agent profile management is read-only for your role</p><p className="mt-1">Your current role ({adminRoleLabel(adminProfile)}) does not include MANAGE_USERS.</p></div> : null}

    {canManageUsers ? <section className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-3">
        <Select label="Role type" value={roleType} onChange={setRoleType} options={ROLE_TYPES} />
        <Select label="Status" value={status} onChange={setStatus} options={STATUSES} />
        <div className="flex items-end"><button type="button" onClick={() => void load()} disabled={loading} className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Refresh</button></div>
      </div>
    </section> : null}

    {!canManageUsers ? null : loading ? <p className="text-sm text-gray-500">Loading agent profiles...</p> : <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <section className="overflow-hidden rounded bg-white shadow">
        <div className="border-b px-4 py-3 text-sm font-semibold text-gray-900">Agents ({payload?.count || 0})</div>
        <div className="divide-y">
          {(payload?.agent_profiles || []).map((profile) => <button type="button" key={profile.id} onClick={() => setSelectedId(profile.id)} className={`block w-full p-4 text-left text-sm ${selected?.id === profile.id ? "bg-green-50" : "hover:bg-gray-50"}`}>
            <p className="font-medium text-gray-900">{profile.display_name || profile.user?.display_name || profile.agent_code || profile.user_id}</p>
            <p className="mt-1 text-xs text-gray-500">{profile.mobile_number || profile.user?.mobile_number_masked || profile.user_id}</p>
            <div className="mt-2 flex flex-wrap gap-2"><Badge>{profile.role_type}</Badge><Badge tone={profile.status === "ACTIVE" ? "green" : "amber"}>{profile.status}</Badge>{profile.can_also_act_as_farmer ? <Badge tone="blue">Farmer mode</Badge> : null}</div>
          </button>)}
          {(!payload || payload.agent_profiles.length === 0) ? <div className="p-6 text-center text-sm text-gray-400">No agent profiles found.</div> : null}
        </div>
      </section>

      {selected ? <AgentProfileDetail profile={selected} /> : <section className="rounded bg-white p-5 text-sm text-gray-400 shadow">Select an agent profile.</section>}
    </div>}
  </div>;
}

function AgentProfileDetail({ profile }: { profile: AgentProfileDto }) {
  return <section className="rounded bg-white p-5 shadow">
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{profile.display_name || profile.agent_code || profile.user_id}</h2>
        <p className="mt-1 text-xs text-gray-500">{profile.role_type} · {profile.status} · {profile.agent_code || "No code"}</p>
      </div>
      {profile.can_also_act_as_farmer ? <Link href={`/farmer-trace/${profile.farmer_id}`} className="rounded bg-green-700 px-3 py-2 text-xs font-medium text-white">Open farmer mode</Link> : null}
    </div>

    <div className="mt-5 grid gap-3 md:grid-cols-3">
      <Mini label="Skills" value={profile.skills.length} />
      <Mini label="Languages" value={profile.languages.length} />
      <Mini label="Projects" value={profile.project_access.length} />
    </div>

    <Section title="Identity links">
      <KeyValue label="User ID" value={profile.user_id} />
      <KeyValue label="Linked farmer ID" value={profile.farmer_id || "-"} />
      <KeyValue label="Mobile" value={profile.mobile_number || profile.user?.mobile_number_masked || "-"} />
    </Section>

    <Section title="Capabilities">
      <ChipList values={profile.skills} empty="No skills configured." />
      <ChipList values={profile.languages} empty="No languages configured." tone="blue" />
    </Section>

    <Section title="Project access">
      {profile.project_access.map((access) => <div key={access.project_role_id} className="rounded border p-3 text-xs">
        <div className="font-semibold text-gray-900">{access.project_name}</div>
        <div className="mt-1 text-gray-500">{access.role} · {access.project_status}</div>
        <pre className="mt-2 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(access.territory_scope || {}, null, 2)}</pre>
      </div>)}
      {profile.project_access.length === 0 ? <p className="text-sm text-gray-400">No project access assigned.</p> : null}
    </Section>

    <Section title="Territory and availability">
      <pre className="overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">{JSON.stringify({ territory_scope: profile.territory_scope, availability: profile.availability, certification: profile.certification, metadata: profile.metadata }, null, 2)}</pre>
    </Section>
  </section>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{options.map((option) => <option key={option || "ALL"} value={option}>{option || "ALL"}</option>)}</select></label>;
}

function Mini({ label, value }: { label: string; value: number }) {
  return <div className="rounded border bg-gray-50 p-3"><div className="text-xs text-gray-500">{label}</div><div className="mt-1 text-xl font-bold text-gray-900">{value}</div></div>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="mt-5"><h3 className="mb-2 text-sm font-semibold text-gray-800">{title}</h3><div className="space-y-2">{children}</div></div>;
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return <div className="rounded border p-2 text-xs"><span className="font-semibold text-gray-700">{label}: </span><span className="break-all text-gray-500">{value}</span></div>;
}

function ChipList({ values, empty, tone = "green" }: { values: string[]; empty: string; tone?: "green" | "blue" }) {
  const cls = tone === "blue" ? "bg-blue-50 text-blue-800" : "bg-green-50 text-green-800";
  return values.length ? <div className="flex flex-wrap gap-2">{values.map((value) => <span key={value} className={`rounded-full px-2 py-1 text-xs ${cls}`}>{value}</span>)}</div> : <p className="text-sm text-gray-400">{empty}</p>;
}

function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "green" | "amber" | "blue" }) {
  const tones = { slate: "bg-slate-100 text-slate-800", green: "bg-green-100 text-green-800", amber: "bg-amber-100 text-amber-800", blue: "bg-blue-100 text-blue-800" };
  return <span className={`rounded-full px-2 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}
