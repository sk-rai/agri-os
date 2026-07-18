"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { agentProfilesApi, type AgentProfileDto, type AgentProfilesResponse, type AgentProfileWritePayload } from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";
import { getErrorMessage, isPermissionDenied, PermissionErrorCard } from "@/components/permission-error-card";

const ROLE_TYPES = ["", "FIELD_AGENT", "AGRONOMIST", "DEALER", "MANAGER", "ENUMERATOR"];
const STATUSES = ["", "ACTIVE", "INACTIVE", "SUSPENDED"];

type DraftState = {
  user_id: string;
  farmer_id: string;
  agent_code: string;
  role_type: string;
  display_name: string;
  mobile_number: string;
  status: string;
  skills: string;
  languages: string;
  territory_scope: string;
  availability: string;
  certification: string;
  metadata: string;
  reason: string;
};

const EMPTY_DRAFT: DraftState = {
  user_id: "",
  farmer_id: "",
  agent_code: "",
  role_type: "FIELD_AGENT",
  display_name: "",
  mobile_number: "",
  status: "ACTIVE",
  skills: "",
  languages: "",
  territory_scope: "{}",
  availability: "{}",
  certification: "{}",
  metadata: "{}",
  reason: "Agent profile update",
};

export default function AgentProfilesPage() {
  const { profile: adminProfile, loading: loadingProfile, error: profileError } = useAdminProfile();
  const canManageUsers = hasAdminPermission(adminProfile, "MANAGE_USERS");
  const [roleType, setRoleType] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [payload, setPayload] = useState<AgentProfilesResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [editingNew, setEditingNew] = useState(false);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);

  const selected = useMemo(() => {
    if (editingNew) return null;
    return payload?.agent_profiles.find((profile) => profile.id === selectedId) || payload?.agent_profiles[0] || null;
  }, [editingNew, payload, selectedId]);

  async function load(preferredId?: string) {
    setLoading(true);
    setError(null);
    try {
      const next = await agentProfilesApi.list({ roleType: roleType || undefined, status: status || undefined });
      setPayload(next);
      setEditingNew(false);
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

  useEffect(() => {
    if (!selected || editingNew) return;
    setDraft(profileToDraft(selected));
  }, [editingNew, selected]);

  function startNewProfile() {
    setEditingNew(true);
    setSelectedId("");
    setNotice("");
    setError(null);
    setDraft({ ...EMPTY_DRAFT });
  }

  async function saveProfile() {
    if (!canManageUsers) return;
    setSaving(true);
    setNotice("");
    setError(null);
    try {
      if (editingNew || !selected) {
        const body = buildAgentPayload(draft, true) as AgentProfileWritePayload & { user_id: string };
        const response = await agentProfilesApi.create(body);
        setNotice(response.created ? "Agent profile created." : "Existing agent profile updated from user link.");
        await load(response.agent_profile.id);
      } else {
        const body = buildAgentPayload(draft, false);
        const response = await agentProfilesApi.update(selected.id, body);
        setNotice("Agent profile updated.");
        await load(response.agent_profile.id);
      }
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Agent Profiles</h1>
      <p className="mt-1 text-sm text-gray-500">Operational profiles for field agents, agronomists, dealers, and dual-capacity farmer-agents.</p>
    </div>

    {isPermissionDenied(error) ? <PermissionErrorCard error={error} className="mb-4" /> : error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{getErrorMessage(error)}</div> : null}
    {notice ? <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700">{notice}</div> : null}
    {loadingProfile ? <div className="mb-6 rounded bg-white p-5 text-sm text-gray-500 shadow">Checking admin permissions...</div> : !canManageUsers ? <div className="mb-6 rounded border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"><p className="font-semibold">Agent profile management is read-only for your role</p><p className="mt-1">Your current role ({adminRoleLabel(adminProfile)}) does not include MANAGE_USERS.</p></div> : null}

    {canManageUsers ? <section className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-3">
        <Select label="Role type" value={roleType} onChange={setRoleType} options={ROLE_TYPES} />
        <Select label="Status" value={status} onChange={setStatus} options={STATUSES} />
        <div className="flex items-end gap-2">
          <button type="button" onClick={() => void load()} disabled={loading} className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Refresh</button>
          <button type="button" onClick={startNewProfile} className="rounded border px-4 py-2 text-sm font-medium text-gray-700">New profile</button>
        </div>
      </div>
    </section> : null}

    {canManageUsers ? <section className="mb-6 rounded bg-white p-5 shadow">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{editingNew || !selected ? "Create agent profile" : "Edit selected agent profile"}</h2>
          <p className="mt-1 text-sm text-gray-500">Link a user to an operational role. If the same user is also a farmer, set farmer ID to enable farmer/agent mode switching.</p>
        </div>
        {selected && !editingNew ? <Badge tone="blue">Editing {selected.agent_code || selected.user_id}</Badge> : <Badge tone="green">New</Badge>}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <Input label="User ID" value={draft.user_id} onChange={(value) => setDraft((current) => ({ ...current, user_id: value }))} disabled={!editingNew && !!selected} />
        <Input label="Linked farmer ID (optional)" value={draft.farmer_id} onChange={(value) => setDraft((current) => ({ ...current, farmer_id: value }))} />
        <Input label="Agent code" value={draft.agent_code} onChange={(value) => setDraft((current) => ({ ...current, agent_code: value }))} />
        <Select label="Role type" value={draft.role_type} onChange={(value) => setDraft((current) => ({ ...current, role_type: value }))} options={ROLE_TYPES.filter(Boolean)} />
        <Select label="Status" value={draft.status} onChange={(value) => setDraft((current) => ({ ...current, status: value }))} options={STATUSES.filter(Boolean)} />
        <Input label="Mobile number" value={draft.mobile_number} onChange={(value) => setDraft((current) => ({ ...current, mobile_number: value }))} />
        <Input label="Display name" value={draft.display_name} onChange={(value) => setDraft((current) => ({ ...current, display_name: value }))} />
        <Input label="Skills (comma separated)" value={draft.skills} onChange={(value) => setDraft((current) => ({ ...current, skills: value }))} />
        <Input label="Languages (comma separated)" value={draft.languages} onChange={(value) => setDraft((current) => ({ ...current, languages: value }))} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <TextArea label="Territory scope JSON" value={draft.territory_scope} onChange={(value) => setDraft((current) => ({ ...current, territory_scope: value }))} />
        <TextArea label="Availability JSON" value={draft.availability} onChange={(value) => setDraft((current) => ({ ...current, availability: value }))} />
        <TextArea label="Certification JSON" value={draft.certification} onChange={(value) => setDraft((current) => ({ ...current, certification: value }))} />
        <TextArea label="Metadata JSON" value={draft.metadata} onChange={(value) => setDraft((current) => ({ ...current, metadata: value }))} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
        <Input label="Audit reason" value={draft.reason} onChange={(value) => setDraft((current) => ({ ...current, reason: value }))} />
        <div className="flex items-end"><button type="button" onClick={() => void saveProfile()} disabled={saving} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving ? "Saving..." : editingNew || !selected ? "Create profile" : "Save changes"}</button></div>
      </div>
    </section> : null}

    {!canManageUsers ? null : loading ? <p className="text-sm text-gray-500">Loading agent profiles...</p> : <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <section className="overflow-hidden rounded bg-white shadow">
        <div className="border-b px-4 py-3 text-sm font-semibold text-gray-900">Agents ({payload?.count || 0})</div>
        <div className="divide-y">
          {(payload?.agent_profiles || []).map((profile) => <button type="button" key={profile.id} onClick={() => { setEditingNew(false); setSelectedId(profile.id); }} className={`block w-full p-4 text-left text-sm ${selected?.id === profile.id ? "bg-green-50" : "hover:bg-gray-50"}`}>
            <p className="font-medium text-gray-900">{profile.display_name || profile.user?.display_name || profile.agent_code || profile.user_id}</p>
            <p className="mt-1 text-xs text-gray-500">{profile.mobile_number || profile.user?.mobile_number_masked || profile.user_id}</p>
            <div className="mt-2 flex flex-wrap gap-2"><Badge>{profile.role_type}</Badge><Badge tone={profile.status === "ACTIVE" ? "green" : "amber"}>{profile.status}</Badge>{profile.can_also_act_as_farmer ? <Badge tone="blue">Farmer mode</Badge> : null}</div>
          </button>)}
          {(!payload || payload.agent_profiles.length === 0) ? <div className="p-6 text-center text-sm text-gray-400">No agent profiles found.</div> : null}
        </div>
      </section>

      {selected ? <AgentProfileDetail profile={selected} /> : <section className="rounded bg-white p-5 text-sm text-gray-400 shadow">Create a new profile or select an agent profile.</section>}
    </div>}
  </div>;
}

function profileToDraft(profile: AgentProfileDto): DraftState {
  return {
    user_id: profile.user_id,
    farmer_id: profile.farmer_id || "",
    agent_code: profile.agent_code || "",
    role_type: profile.role_type,
    display_name: profile.display_name || "",
    mobile_number: profile.mobile_number || "",
    status: profile.status,
    skills: profile.skills.join(", "),
    languages: profile.languages.join(", "),
    territory_scope: JSON.stringify(profile.territory_scope || {}, null, 2),
    availability: JSON.stringify(profile.availability || {}, null, 2),
    certification: JSON.stringify(profile.certification || {}, null, 2),
    metadata: JSON.stringify(profile.metadata || {}, null, 2),
    reason: "Agent profile update",
  };
}

function buildAgentPayload(draft: DraftState, includeUserId: boolean): AgentProfileWritePayload {
  if (includeUserId && !draft.user_id.trim()) throw new Error("User ID is required to create an agent profile.");
  if (!draft.reason.trim()) throw new Error("Audit reason is required.");
  const payload: AgentProfileWritePayload = {
    farmer_id: draft.farmer_id.trim() || null,
    agent_code: draft.agent_code.trim() || null,
    role_type: draft.role_type || "FIELD_AGENT",
    display_name: draft.display_name.trim() || null,
    mobile_number: draft.mobile_number.trim() || null,
    status: draft.status || "ACTIVE",
    skills: csv(draft.skills),
    languages: csv(draft.languages),
    territory_scope: parseJsonObject(draft.territory_scope, "Territory scope"),
    availability: parseJsonObject(draft.availability, "Availability"),
    certification: parseJsonObject(draft.certification, "Certification"),
    metadata: parseJsonObject(draft.metadata, "Metadata"),
    reason: draft.reason.trim(),
  };
  if (includeUserId) payload.user_id = draft.user_id.trim();
  return payload;
}

function csv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  try {
    const parsed = value.trim() ? JSON.parse(value) : {};
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("not an object");
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(`${label} must be a valid JSON object.`);
  }
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

function Input({ label, value, onChange, disabled = false }: { label: string; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} className="mt-1 w-full rounded border p-2 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500" /></label>;
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<textarea value={value} onChange={(event) => onChange(event.target.value)} rows={5} className="mt-1 w-full rounded border p-2 font-mono text-xs text-gray-900" /></label>;
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
