"use client";

import { useEffect, useMemo, useState } from "react";
import {
  inputCatalogApi,
  projectsApi,
  type InputCategoryDto,
  type Project,
  type ProjectInputAssignmentAuditEvent,
  type ProjectInputAssignmentDto,
  type ProjectInputAssignmentsResponse,
} from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";
import { getErrorMessage, isPermissionDenied, PermissionErrorCard } from "@/components/permission-error-card";

function statusClass(rule: string) {
  switch (rule) {
    case "ANDROID_VISIBLE":
      return "bg-green-50 text-green-700";
    case "DISABLED_BY_PROJECT":
      return "bg-red-50 text-red-700";
    case "NOT_ASSIGNED":
      return "bg-yellow-50 text-yellow-700";
    case "BLOCKED_BY_CROP_SCOPE":
      return "bg-orange-50 text-orange-700";
    case "IMPLICIT_CROP_SCOPE":
      return "bg-blue-50 text-blue-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

const AUDIT_ACTIONS = [
  "CREATE_INPUT_ASSIGNMENT",
  "ENABLE_INPUT",
  "DISABLE_INPUT",
  "UPDATE_INPUT_ASSIGNMENT",
];

function formatAuditAction(action: string) {
  return action
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function valueLabel(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function diffRows(before?: Record<string, unknown> | null, after?: Record<string, unknown> | null) {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  return Array.from(keys)
    .filter((key) => JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key]))
    .map((key) => ({ key, before: before?.[key], after: after?.[key] }));
}

export default function ProjectInputsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [categories, setCategories] = useState<InputCategoryDto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [summary, setSummary] = useState<ProjectInputAssignmentsResponse | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [category, setCategory] = useState("");
  const [cropCode, setCropCode] = useState("");
  const [query, setQuery] = useState("");
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [auditEvents, setAuditEvents] = useState<ProjectInputAssignmentAuditEvent[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [auditInputCode, setAuditInputCode] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [drafts, setDrafts] = useState<Record<string, { reason: string; displayOrder: string }>>({});
  const { profile: adminProfile, loading: loadingProfile } = useAdminProfile();

  const canEditProjectInputs = hasAdminPermission(adminProfile, "PROJECT_EDIT");

  useEffect(() => {
    Promise.all([
      projectsApi.list(),
      inputCatalogApi.categories(),
    ])
      .then(([projectItems, categoryPayload]) => {
        setProjects(projectItems);
        setSelectedProjectId(projectItems[0]?.id || "");
        setCategories(categoryPayload.categories);
      })
      .catch((e) => setError(e))
      .finally(() => {
        setLoadingProjects(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoadingSummary(true);
    setError(null);
    inputCatalogApi
      .projectAssignments(selectedProjectId, {
        category: category || undefined,
        cropCode: cropCode || undefined,
        q: query || undefined,
      })
      .then(setSummary)
      .catch((e) => setError(e))
      .finally(() => setLoadingSummary(false));
  }, [selectedProjectId, category, cropCode, query]);

  useEffect(() => {
    if (!summary) return;
    const next: Record<string, { reason: string; displayOrder: string }> = {};
    summary.inputs.forEach((item) => {
      next[item.code] = {
        reason: item.reason || "",
        displayOrder: item.display_order != null ? String(item.display_order) : "",
      };
    });
    setDrafts(next);
  }, [summary]);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoadingAudit(true);
    inputCatalogApi
      .projectAssignmentAudit(selectedProjectId, {
        inputCode: auditInputCode || undefined,
        action: auditAction || undefined,
        limit: 25,
      })
      .then((payload) => setAuditEvents(payload.events))
      .catch(() => setAuditEvents([]))
      .finally(() => setLoadingAudit(false));
  }, [selectedProjectId, summary, auditInputCode, auditAction]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const cropOptions = useMemo(() => {
    const crops = new Set<string>();
    selectedProject?.crop_scope?.forEach((crop) => crops.add(crop));
    summary?.inputs.forEach((item) => item.applicable_crops.forEach((crop) => crops.add(crop)));
    return Array.from(crops).sort();
  }, [selectedProject, summary]);

  const updateDraft = (code: string, patch: Partial<{ reason: string; displayOrder: string }>) => {
    setDrafts((current) => ({
      ...current,
      [code]: {
        reason: current[code]?.reason || "",
        displayOrder: current[code]?.displayOrder || "",
        ...patch,
      },
    }));
  };

  const updateAssignment = async (item: ProjectInputAssignmentDto, enabled: boolean) => {
    if (!selectedProjectId) return;
    if (!canEditProjectInputs) {
      setError("Your current role can view project inputs but cannot edit project input assignments.");
      return;
    }
    const draft = drafts[item.code] || { reason: item.reason || "", displayOrder: item.display_order != null ? String(item.display_order) : "" };
    const order = draft.displayOrder.trim() ? Number(draft.displayOrder) : undefined;
    setBusyCode(item.code);
    setError(null);
    try {
      const updated = await inputCatalogApi.updateProjectAssignment(selectedProjectId, item.code, {
        enabled,
        display_order: Number.isFinite(order) ? order : undefined,
        reason: draft.reason.trim() || undefined,
      });
      setSummary(updated);
      const audit = await inputCatalogApi.projectAssignmentAudit(selectedProjectId, {
        inputCode: auditInputCode || undefined,
        action: auditAction || undefined,
        limit: 25,
      });
      setAuditEvents(audit.events);
    } catch (e) {
      setError(e);
    } finally {
      setBusyCode(null);
    }
  };

  if (loadingProjects) return <div className="text-gray-500">Loading projects...</div>;
  if (error && !summary) return isPermissionDenied(error) ? <PermissionErrorCard error={error} /> : <div className="text-red-500">Error: {getErrorMessage(error)}</div>;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Project Inputs</h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure which catalog inputs are visible to Android for each project.
          </p>
        </div>
        <select
          value={selectedProjectId}
          onChange={(event) => setSelectedProjectId(event.target.value)}
          className="min-w-72 rounded-lg border px-3 py-2 text-sm"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>
      </div>

      {projects.length === 0 ? (
        <div className="rounded-lg bg-white p-10 text-center text-gray-400 shadow">No projects yet.</div>
      ) : (
        <>
          {!loadingProfile && !canEditProjectInputs ? (
            <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-semibold">Project input assignments are read-only for your role</p>
              <p className="mt-1">Your current role ({adminRoleLabel(adminProfile)}) does not include PROJECT_EDIT. You can inspect visibility and audit history, but cannot enable, disable, or reorder project inputs.</p>
            </div>
          ) : null}

          <div className="mb-6 rounded-lg bg-white p-5 shadow">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{selectedProject?.name || "Selected project"}</h2>
                <p className="mt-1 text-sm text-gray-500">
                  {selectedProject?.start_date} ? {selectedProject?.end_date}  {selectedProject?.status}
                </p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {(selectedProject?.crop_scope || []).length > 0 ? selectedProject?.crop_scope.map((crop) => (
                    <span key={crop} className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">{crop}</span>
                  )) : <span className="text-sm text-gray-400">No crop scope configured</span>}
                </div>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${summary?.explicit_assignment_scope ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-700"}`}>
                {summary?.explicit_assignment_scope ? "Explicit input allow-list" : "Implicit crop-scope defaults"}
              </span>
            </div>
          </div>

          <div className="mb-6 grid gap-4 md:grid-cols-5">
            <Stat label="Total" value={summary?.counts.total ?? 0} />
            <Stat label="Android visible" value={summary?.counts.android_visible ?? 0} tone="ok" />
            <Stat label="Disabled" value={summary?.counts.disabled_by_project ?? 0} tone="warn" />
            <Stat label="Not assigned" value={summary?.counts.not_assigned ?? 0} tone="warn" />
            <Stat label="Crop blocked" value={summary?.counts.blocked_by_crop_scope ?? 0} />
          </div>

          <div className="mb-6 grid gap-3 rounded-lg bg-white p-4 shadow md:grid-cols-[1fr_220px_180px_180px]">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search code, name, or composition"
              className="rounded-lg border px-3 py-2 text-sm"
            />
            <select value={category} onChange={(event) => setCategory(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
              <option value="">All categories</option>
              {categories.map((cat) => (
                <option key={cat.code} value={cat.code}>{cat.canonical_name}</option>
              ))}
            </select>
            <select value={cropCode} onChange={(event) => setCropCode(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
              <option value="">All crops</option>
              {cropOptions.map((crop) => (
                <option key={crop} value={crop}>{crop}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => { setQuery(""); setCategory(""); setCropCode(""); }}
              className="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Clear filters
            </button>
          </div>

          {isPermissionDenied(error) ? <PermissionErrorCard error={error} className="mb-4" /> : error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{getErrorMessage(error)}</div> : null}
          {loadingSummary || !summary ? (
            <p className="text-gray-500">Loading input assignments...</p>
          ) : (
            <>
              <div className="space-y-3">
                {summary.inputs.map((item) => (
                  <InputAssignmentCard
                    key={item.code}
                    item={item}
                    draft={drafts[item.code] || { reason: item.reason || "", displayOrder: item.display_order != null ? String(item.display_order) : "" }}
                    isBusy={busyCode === item.code}
                    onDraft={updateDraft}
                    onUpdate={updateAssignment}
                    canEdit={canEditProjectInputs}
                  />
                ))}
                {summary.inputs.length === 0 ? (
                  <div className="rounded-lg bg-white p-10 text-center text-gray-400 shadow">No inputs match this filter.</div>
                ) : null}
              </div>
              <AuditPanel
                events={auditEvents}
                loading={loadingAudit}
                summary={summary}
                inputCode={auditInputCode}
                action={auditAction}
                onInputCodeChange={setAuditInputCode}
                onActionChange={setAuditAction}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

function InputAssignmentCard({
  item,
  draft,
  isBusy,
  onDraft,
  onUpdate,
  canEdit,
}: {
  item: ProjectInputAssignmentDto;
  draft: { reason: string; displayOrder: string };
  isBusy: boolean;
  onDraft: (code: string, patch: Partial<{ reason: string; displayOrder: string }>) => void;
  onUpdate: (item: ProjectInputAssignmentDto, enabled: boolean) => void;
  canEdit: boolean;
}) {
  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-gray-900">{item.canonical_name}</h3>
            <span className={`rounded-full px-2 py-1 text-xs font-medium ${statusClass(item.assignment_rule)}`}>{item.assignment_rule}</span>
            <span className="rounded-full bg-gray-100 px-2 py-1 font-mono text-xs text-gray-600">{item.code}</span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            {item.category_code || ""}  {item.composition || "No composition"}  Unit {item.unit}
          </p>
          <p className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600">
            {item.assignment_reason || "No assignment reason supplied"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {item.applicable_crops.length > 0 ? item.applicable_crops.map((crop) => (
              <span key={crop} className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">{crop}</span>
            )) : <span className="text-xs text-gray-400">No crop restrictions</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            disabled={isBusy || !canEdit}
            title={canEdit ? undefined : "Your role cannot edit project input assignments."}
            onClick={() => onUpdate(item, true)}
            className="rounded-lg border border-green-200 px-3 py-2 font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
          >
            {isBusy ? "Saving..." : "Enable"}
          </button>
          <button
            type="button"
            disabled={isBusy || !canEdit}
            title={canEdit ? undefined : "Your role cannot edit project input assignments."}
            onClick={() => onUpdate(item, false)}
            className="rounded-lg border border-red-200 px-3 py-2 font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
          >
            {isBusy ? "Saving..." : "Disable"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 rounded-lg border bg-gray-50 p-3 md:grid-cols-[120px_1fr_auto]">
        <label className="text-xs font-medium text-gray-500">
          Order
          <input
            type="number"
            value={draft.displayOrder}
            disabled={!canEdit}
            onChange={(event) => onDraft(item.code, { displayOrder: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
            placeholder="1000"
          />
        </label>
        <label className="text-xs font-medium text-gray-500">
          Reason
          <input
            value={draft.reason}
            disabled={!canEdit}
            onChange={(event) => onDraft(item.code, { reason: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
            placeholder="Why this input is enabled/disabled"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            disabled={isBusy || !canEdit}
            title={canEdit ? undefined : "Your role cannot edit project input assignments."}
            onClick={() => onUpdate(item, item.visible)}
            className="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-wait disabled:opacity-60"
          >
            {isBusy ? "Saving..." : "Save metadata"}
          </button>
        </div>
      </div>
    </div>
  );
}


function AuditPanel({
  events,
  loading,
  summary,
  inputCode,
  action,
  onInputCodeChange,
  onActionChange,
}: {
  events: ProjectInputAssignmentAuditEvent[];
  loading: boolean;
  summary: ProjectInputAssignmentsResponse;
  inputCode: string;
  action: string;
  onInputCodeChange: (value: string) => void;
  onActionChange: (value: string) => void;
}) {
  const inputOptions = useMemo(() => {
    const items = summary.inputs.map((item) => ({ code: item.code, label: item.canonical_name }));
    const eventCodes = new Set(events.map((event) => event.input_code));
    eventCodes.forEach((code) => {
      if (!items.some((item) => item.code === code)) items.push({ code, label: code });
    });
    return items.sort((a, b) => a.code.localeCompare(b.code));
  }, [events, summary.inputs]);

  return (
    <div className="mt-6 rounded-lg bg-white p-5 shadow">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Input assignment audit</h2>
          <p className="text-sm text-gray-500">Filter change history and inspect exactly what changed.</p>
        </div>
        <span className="w-fit rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">{events.length} events</span>
      </div>

      <div className="mb-4 grid gap-3 rounded-lg border bg-gray-50 p-3 md:grid-cols-[1fr_220px_auto]">
        <label className="text-xs font-medium text-gray-500">
          Input
          <select
            value={inputCode}
            onChange={(event) => onInputCodeChange(event.target.value)}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
          >
            <option value="">All inputs</option>
            {inputOptions.map((item) => (
              <option key={item.code} value={item.code}>{item.code} - {item.label}</option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-gray-500">
          Action
          <select
            value={action}
            onChange={(event) => onActionChange(event.target.value)}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
          >
            <option value="">All actions</option>
            {AUDIT_ACTIONS.map((item) => (
              <option key={item} value={item}>{formatAuditAction(item)}</option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="button"
            onClick={() => { onInputCodeChange(""); onActionChange(""); }}
            className="w-full rounded-lg border px-3 py-2 text-sm font-medium text-gray-700 hover:bg-white"
          >
            Clear audit filters
          </button>
        </div>
      </div>

      {loading ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">Loading audit trail...</p> : null}
      {!loading && events.length === 0 ? (
        <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No input assignment changes match this filter.</p>
      ) : null}
      {!loading && events.length > 0 ? (
        <div className="max-h-[32rem] space-y-3 overflow-auto pr-1">
          {events.map((event) => (
            <AuditEventCard key={event.id} event={event} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AuditEventCard({ event }: { event: ProjectInputAssignmentAuditEvent }) {
  const rows = diffRows(event.before, event.after);
  const actor = event.actor_id || "System / unknown actor";

  return (
    <div className="rounded border p-3 text-xs">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-blue-50 px-2 py-1 font-medium text-blue-700">{formatAuditAction(event.action)}</span>
          <span className="font-mono text-gray-700">{event.input_code}</span>
          {event.created_at ? <span className="text-gray-400">{new Date(event.created_at).toLocaleString()}</span> : null}
        </div>
        <span className="rounded bg-gray-50 px-2 py-1 font-mono text-[11px] text-gray-500">Actor: {actor}</span>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <div className="rounded bg-gray-50 p-2">
          <p className="font-medium text-gray-500">Reason</p>
          <p className="mt-1 text-gray-700">{event.reason || "No reason captured"}</p>
        </div>
        <div className="rounded bg-gray-50 p-2">
          <p className="font-medium text-gray-500">Source</p>
          <p className="mt-1 text-gray-700">{valueLabel(event.metadata?.source)}</p>
        </div>
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer font-medium text-gray-600">View field-level changes</summary>
        {rows.length > 0 ? (
          <div className="mt-2 overflow-auto rounded border">
            <table className="min-w-full text-left text-[11px]">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-2 py-1 font-medium">Field</th>
                  <th className="px-2 py-1 font-medium">Before</th>
                  <th className="px-2 py-1 font-medium">After</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td className="px-2 py-1 font-mono text-gray-600">{row.key}</td>
                    <td className="max-w-xs px-2 py-1 text-gray-500">{valueLabel(row.before)}</td>
                    <td className="max-w-xs px-2 py-1 text-gray-800">{valueLabel(row.after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 rounded bg-gray-50 p-2 text-gray-400">No field-level differences available for this event.</p>
        )}
      </details>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "ok" | "warn" }) {
  const toneClass = tone === "ok" ? "bg-green-50 text-green-700" : tone === "warn" ? "bg-yellow-50 text-yellow-700" : "bg-white text-gray-900";
  return (
    <div className={`rounded-lg p-4 shadow ${toneClass}`}>
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}