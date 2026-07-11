"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  projectsApi,
  workflowCatalogApi,
  type Project,
  type ProjectWorkflowAssignmentAuditResponse,
  type ProjectWorkflowEnablementItem,
  type ProjectWorkflowEnablementsResponse,
} from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";
import { getErrorMessage, isPermissionDenied, PermissionErrorCard } from "@/components/permission-error-card";

type WorkflowVisibilityFilter = "ALL" | "ANDROID_VISIBLE" | "ENABLED" | "DISABLED" | "BLOCKED" | "OVERRIDDEN";
type WorkflowChangeIntent = "ENABLE" | "DISABLE" | "SAVE_METADATA";

type PendingWorkflowChange = { workflow: ProjectWorkflowEnablementItem; enabled: boolean; intent: WorkflowChangeIntent };

function labelText(value: Record<string, string> | string | undefined | null) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "";
}

export default function ProjectWorkflowsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [summary, setSummary] = useState<ProjectWorkflowEnablementsResponse | null>(null);
  const [assignmentAudit, setAssignmentAudit] = useState<ProjectWorkflowAssignmentAuditResponse | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [updatingWorkflowId, setUpdatingWorkflowId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { label: string; displayOrder: string }>>({});
  const [search, setSearch] = useState("");
  const [visibilityFilter, setVisibilityFilter] = useState<WorkflowVisibilityFilter>("ALL");
  const [pendingChange, setPendingChange] = useState<PendingWorkflowChange | null>(null);
  const [pendingChangeReason, setPendingChangeReason] = useState("");
  const { profile: adminProfile } = useAdminProfile();
  const canEditProjectWorkflows = hasAdminPermission(adminProfile, "PROJECT_EDIT");

  useEffect(() => {
    projectsApi
      .list()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId(items[0]?.id || "");
      })
      .catch((e) => setError(e))
      .finally(() => setLoadingProjects(false));
  }, []);

  const loadAssignmentAudit = async (projectId: string) => {
    const audit = await workflowCatalogApi.projectEnablementAudit(projectId, { limit: 50 });
    setAssignmentAudit(audit);
  };

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoadingSummary(true);
    Promise.all([
      workflowCatalogApi.projectEnablements(selectedProjectId).then(setSummary),
      loadAssignmentAudit(selectedProjectId).catch(() => setAssignmentAudit(null)),
    ])
      .catch((e) => setError(e))
      .finally(() => setLoadingSummary(false));
  }, [selectedProjectId]);



  useEffect(() => {
    if (!summary) return;
    const nextDrafts: Record<string, { label: string; displayOrder: string }> = {};
    summary.workflows.forEach((workflow) => {
      nextDrafts[workflow.workflow_template_id] = {
        label: labelText(workflow.label),
        displayOrder: workflow.display_order != null ? String(workflow.display_order) : "",
      };
    });
    setDrafts(nextDrafts);
  }, [summary]);

  const updateWorkflow = async (workflow: ProjectWorkflowEnablementItem, enabled: boolean, reason?: string) => {
    if (!summary) return;
    setUpdatingWorkflowId(workflow.workflow_template_id);
    setError(null);
    try {
      const draft = drafts[workflow.workflow_template_id];
      const displayOrder = draft?.displayOrder?.trim() ? Number(draft.displayOrder) : undefined;
      const label = draft?.label?.trim();
      const updated = await workflowCatalogApi.updateProjectEnablement(summary.project.id, workflow.workflow_template_id, {
        enabled,
        display_order: Number.isFinite(displayOrder) ? displayOrder : undefined,
        display_label: label ? { en: label, hi: label } : undefined,
        reason: reason?.trim() || undefined,
      });
      setSummary(updated);
      await loadAssignmentAudit(summary.project.id).catch(() => setAssignmentAudit(null));
    } catch (e) {
      setError(e);
    } finally {
      setUpdatingWorkflowId(null);
    }
  };

  const requestWorkflowChange = (workflow: ProjectWorkflowEnablementItem, enabled: boolean, intent: WorkflowChangeIntent) => {
    setPendingChange({ workflow, enabled, intent });
    setPendingChangeReason("");
  };

  const confirmPendingChange = async () => {
    if (!pendingChange) return;
    const change = pendingChange;
    setPendingChange(null);
    const reason = pendingChangeReason;
    await updateWorkflow(change.workflow, change.enabled, reason);
  };

  const updateDraft = (workflowId: string, patch: Partial<{ label: string; displayOrder: string }>) => {
    setDrafts((current) => ({
      ...current,
      [workflowId]: {
        label: current[workflowId]?.label || "",
        displayOrder: current[workflowId]?.displayOrder || "",
        ...patch,
      },
    }));
  };

  if (loadingProjects) return <div className="text-gray-500">Loading projects...</div>;
  if (error) return isPermissionDenied(error) ? <PermissionErrorCard error={error} /> : <div className="text-red-500">Error: {getErrorMessage(error)}</div>;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Project Workflows</h1>
          <p className="mt-1 text-sm text-gray-500">
            Effective project assignment rules: what Android can see, what is disabled, and what crop scope blocks.
          </p>
        </div>
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="min-w-72 rounded-lg border px-3 py-2 text-sm"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>
      </div>

      {projects.length === 0 ? (
        <div className="rounded-lg bg-white p-10 text-center text-gray-400 shadow">No projects yet.</div>
      ) : loadingSummary || !summary ? (
        <div className="text-gray-500">Loading workflow visibility...</div>
      ) : (
        <ProjectWorkflowSummary
          summary={summary}
          updatingWorkflowId={updatingWorkflowId}
          onRequestWorkflowChange={requestWorkflowChange}
          drafts={drafts}
          onUpdateDraft={updateDraft}
          search={search}
          onSearchChange={setSearch}
          visibilityFilter={visibilityFilter}
          onVisibilityFilterChange={setVisibilityFilter}
          assignmentAudit={assignmentAudit}
          canEditProjectWorkflows={canEditProjectWorkflows}
          adminRoleLabel={adminRoleLabel(adminProfile)}
        />
      )}
      {summary && pendingChange ? (
        <WorkflowChangeImpactModal
          summary={summary}
          change={pendingChange}
          draft={drafts[pendingChange.workflow.workflow_template_id] || { label: labelText(pendingChange.workflow.label), displayOrder: pendingChange.workflow.display_order != null ? String(pendingChange.workflow.display_order) : "" }}
          updating={updatingWorkflowId === pendingChange.workflow.workflow_template_id}
          onCancel={() => { setPendingChange(null); setPendingChangeReason(""); }}
          onConfirm={confirmPendingChange}
          reason={pendingChangeReason}
          onReasonChange={setPendingChangeReason}
        />
      ) : null}
    </div>
  );
}

function ProjectWorkflowSummary({
  summary,
  updatingWorkflowId,
  onRequestWorkflowChange,
  drafts,
  onUpdateDraft,
  search,
  onSearchChange,
  visibilityFilter,
  onVisibilityFilterChange,
  assignmentAudit,
  canEditProjectWorkflows,
  adminRoleLabel,
}: {
  summary: ProjectWorkflowEnablementsResponse;
  updatingWorkflowId: string | null;
  onRequestWorkflowChange: (workflow: ProjectWorkflowEnablementItem, enabled: boolean, intent: WorkflowChangeIntent) => void;
  drafts: Record<string, { label: string; displayOrder: string }>;
  onUpdateDraft: (workflowId: string, patch: Partial<{ label: string; displayOrder: string }>) => void;
  search: string;
  onSearchChange: (value: string) => void;
  visibilityFilter: WorkflowVisibilityFilter;
  onVisibilityFilterChange: (value: WorkflowVisibilityFilter) => void;
  assignmentAudit: ProjectWorkflowAssignmentAuditResponse | null;
  canEditProjectWorkflows: boolean;
  adminRoleLabel: string;
}) {
  const lifecycle = summary.safe_edit_lifecycle;
  const lifecycleAllowsEdit = lifecycle.can_edit_project_workflows;
  const canEdit = lifecycleAllowsEdit && canEditProjectWorkflows;
  const normalizedSearch = search.trim().toUpperCase();
  const filteredWorkflows = useMemo(() => {
    return summary.workflows.filter((workflow) => {
      const haystack = [
        labelText(workflow.label),
        workflow.workflow_template_code,
        workflow.crop_code,
        workflow.crop_name,
        workflow.season_code,
        workflow.propagation_type_code || "",
        workflow.visibility_status,
        workflow.assignment_rule || "",
      ].join(" ").toUpperCase();
      const matchesSearch = !normalizedSearch || haystack.includes(normalizedSearch);
      const matchesFilter =
        visibilityFilter === "ALL" ||
        (visibilityFilter === "ANDROID_VISIBLE" && workflow.assignment_rule === "ANDROID_VISIBLE") ||
        (visibilityFilter === "ENABLED" && workflow.enabled) ||
        (visibilityFilter === "DISABLED" && workflow.visibility_status === "DISABLED") ||
        (visibilityFilter === "BLOCKED" && workflow.visibility_status === "CROP_SCOPE_BLOCKED") ||
        (visibilityFilter === "OVERRIDDEN" && workflow.override_count > 0);
      return matchesSearch && matchesFilter;
    });
  }, [summary.workflows, normalizedSearch, visibilityFilter]);
  const androidVisible = summary.workflows.filter((workflow) => workflow.assignment_rule === "ANDROID_VISIBLE");
  const filteredAndroidVisible = filteredWorkflows.filter((workflow) => workflow.assignment_rule === "ANDROID_VISIBLE").length;

  return (
    <div>
      <div className="mb-6 rounded-lg bg-white p-5 shadow">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{summary.project.name}</h2>
            <p className="mt-1 text-sm text-gray-500">
              {summary.project.start_date} → {summary.project.end_date} · {summary.project.status}
            </p>
            <div className="mt-3 flex flex-wrap gap-1">
              {summary.project.crop_scope.length > 0 ? summary.project.crop_scope.map((crop) => (
                <span key={crop} className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">{crop}</span>
              )) : <span className="text-sm text-gray-400">No crop scope configured</span>}
            </div>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${summary.explicit_scope ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-700"}`}>
            {summary.explicit_scope ? "Explicit workflow scope" : "Implicit defaults"}
          </span>
        </div>
      </div>

      <div className={`mb-6 rounded-lg border p-4 ${canEdit ? "border-green-100 bg-green-50" : "border-amber-200 bg-amber-50"}`}>
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <p className={`text-sm font-semibold ${canEdit ? "text-green-800" : "text-amber-900"}`}>
              {canEdit ? "Workflow configuration editable" : !canEditProjectWorkflows ? "View-only project workflow access" : "Workflow configuration locked"}
            </p>
            <p className={`mt-1 text-sm ${canEdit ? "text-green-700" : "text-amber-800"}`}>
              {canEdit
                ? "This project has no enrolled field data yet. Enablement and override changes are still allowed."
                : !canEditProjectWorkflows
                  ? `Your current role (${adminRoleLabel}) can view project workflow assignments, but cannot edit them.`
                  : lifecycle.suggested_action || "Create a new workflow version for future cycles instead of editing this project in-place."}
            </p>
            {!canEditProjectWorkflows ? (
              <p className="mt-2 rounded bg-white/70 p-2 text-sm text-amber-800">Ask an Enterprise Admin, Manager, or Agronomist to make assignment changes for this project.</p>
            ) : null}
            {!canEdit && lifecycle.reasons.length > 0 ? (
              <ul className="mt-2 list-disc pl-5 text-sm text-amber-800">
                {lifecycle.reasons.map((reason) => (
                  <li key={reason.code}>{reason.message}</li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="grid grid-cols-4 gap-2 text-center text-xs md:min-w-[360px]">
            <Mini label="Farmers" value={lifecycle.counts.farmers} />
            <Mini label="Parcels" value={lifecycle.counts.parcels} />
            <Mini label="Cycles" value={lifecycle.counts.crop_cycles} />
            <Mini label="Active" value={lifecycle.counts.active_crop_cycles} />
          </div>
        </div>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-5">
        <Stat label="Total" value={summary.counts.total} />
        <Stat label="Android visible" value={summary.counts.android_visible ?? summary.counts.enabled} tone="ok" />
        <Stat label="Disabled" value={summary.counts.disabled} tone="warn" />
        <Stat label="Crop blocked" value={summary.counts.crop_scope_blocked ?? 0} tone="warn" />
        <Stat label="Not visible" value={summary.counts.not_visible} />
      </div>

      <ProjectWorkflowControls
        search={search}
        onSearchChange={onSearchChange}
        visibilityFilter={visibilityFilter}
        onVisibilityFilterChange={onVisibilityFilterChange}
        filteredCount={filteredWorkflows.length}
        totalCount={summary.workflows.length}
        androidVisibleCount={androidVisible.length}
        filteredAndroidVisibleCount={filteredAndroidVisible}
      />

      {filteredWorkflows.length === 0 ? (
        <div className="rounded-lg bg-white p-8 text-center text-sm text-gray-500 shadow">No workflows match the current project filters.</div>
      ) : (
        <div className="grid gap-4">
        {filteredWorkflows.map((workflow) => (
          <WorkflowVisibilityCard
            key={workflow.workflow_template_version_id}
            workflow={workflow}
            projectId={summary.project.id}
            isUpdating={updatingWorkflowId === workflow.workflow_template_id}
            onRequestWorkflowChange={onRequestWorkflowChange}
            draft={drafts[workflow.workflow_template_id] || { label: labelText(workflow.label), displayOrder: workflow.display_order != null ? String(workflow.display_order) : "" }}
            onUpdateDraft={onUpdateDraft}
            canEdit={canEdit}
          />
        ))}
        </div>
      )}

      <AssignmentAuditPanel audit={assignmentAudit} />
    </div>
  );
}

function ProjectWorkflowControls({
  search,
  onSearchChange,
  visibilityFilter,
  onVisibilityFilterChange,
  filteredCount,
  totalCount,
  androidVisibleCount,
  filteredAndroidVisibleCount,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  visibilityFilter: WorkflowVisibilityFilter;
  onVisibilityFilterChange: (value: WorkflowVisibilityFilter) => void;
  filteredCount: number;
  totalCount: number;
  androidVisibleCount: number;
  filteredAndroidVisibleCount: number;
}) {
  const filters: Array<{ value: WorkflowVisibilityFilter; label: string }> = [
    { value: "ALL", label: "All" },
    { value: "ANDROID_VISIBLE", label: "Android visible" },
    { value: "ENABLED", label: "Enabled" },
    { value: "DISABLED", label: "Disabled" },
    { value: "BLOCKED", label: "Crop blocked" },
    { value: "OVERRIDDEN", label: "Overrides" },
  ];
  return (
    <div className="mb-6 rounded-lg bg-white p-4 shadow">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900">Workflow assignment view</p>
          <p className="mt-1 text-xs text-gray-500">
            Showing {filteredCount}/{totalCount} workflows - {filteredAndroidVisibleCount}/{androidVisibleCount} Android-visible in current filter.
          </p>
        </div>
        <input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          className="min-w-72 rounded-lg border px-3 py-2 text-sm"
          placeholder="Search crop, season, workflow code..."
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {filters.map((filter) => (
          <button
            key={filter.value}
            type="button"
            onClick={() => onVisibilityFilterChange(filter.value)}
            className={`rounded-full px-3 py-1.5 font-medium ${visibilityFilter === filter.value ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
          >
            {filter.label}
          </button>
        ))}
      </div>
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

function WorkflowVisibilityCard({
  workflow,
  projectId,
  isUpdating,
  onRequestWorkflowChange,
  draft,
  onUpdateDraft,
  canEdit,
}: {
  workflow: ProjectWorkflowEnablementItem;
  projectId: string;
  isUpdating: boolean;
  onRequestWorkflowChange: (workflow: ProjectWorkflowEnablementItem, enabled: boolean, intent: WorkflowChangeIntent) => void;
  draft: { label: string; displayOrder: string };
  onUpdateDraft: (workflowId: string, patch: Partial<{ label: string; displayOrder: string }>) => void;
  canEdit: boolean;
}) {
  const statusClass: Record<string, string> = {
    ENABLED: "bg-green-50 text-green-700",
    DISABLED: "bg-red-50 text-red-700",
    IMPLICIT_DEFAULT: "bg-blue-50 text-blue-700",
    NOT_VISIBLE: "bg-gray-100 text-gray-600",
    CROP_SCOPE_BLOCKED: "bg-orange-50 text-orange-700",
  };
  const androidVisible = workflow.assignment_rule === "ANDROID_VISIBLE";
  const blockedByCrop = workflow.visibility_status === "CROP_SCOPE_BLOCKED";
  const editDisabledReason = !canEdit
    ? "Your role or project lifecycle does not allow project workflow assignment edits."
    : blockedByCrop
      ? "Project crop scope does not include this workflow crop."
      : undefined;

  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-gray-900">{labelText(workflow.label)}</h3>
            <span className={`rounded-full px-2 py-1 text-xs font-medium ${statusClass[workflow.visibility_status] || "bg-gray-100 text-gray-600"}`}>
              {workflow.visibility_status}
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-600">{workflow.enablement_scope}</span>
            <span className={`rounded-full px-2 py-1 text-xs font-medium ${androidVisible ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-500"}`}>
              {androidVisible ? "Android visible" : "Hidden from Android"}
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            {workflow.crop_name} · {workflow.crop_code} · {workflow.season_code} · {workflow.propagation_type_code || "—"}
          </p>
          <p className="mt-2 font-mono text-xs text-gray-400">{workflow.workflow_template_code} · v{workflow.version}</p>
          <p className="mt-2 text-xs text-gray-500">
            Rule: <span className="font-medium text-gray-700">{workflow.assignment_rule || "?"}</span>{workflow.assignment_reason ? ` - ${workflow.assignment_reason}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          {workflow.enabled ? (
            <button
              type="button"
              disabled={isUpdating || !canEdit}
              title={editDisabledReason}
              onClick={() => onRequestWorkflowChange(workflow, false, "DISABLE")}
              className="rounded-lg border border-red-200 px-3 py-2 font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
            >
              {isUpdating ? "Updating..." : "Disable"}
            </button>
          ) : (
            <button
              type="button"
              disabled={isUpdating || !canEdit || blockedByCrop}
              title={editDisabledReason}
              onClick={() => onRequestWorkflowChange(workflow, true, "ENABLE")}
              className="rounded-lg border border-green-200 px-3 py-2 font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
            >
              {isUpdating ? "Updating..." : "Enable"}
            </button>
          )}
          <Link
            href={`/workflows/preview/${workflow.workflow_template_version_id}?project_id=${projectId}`}
            className={`rounded-lg px-3 py-2 font-medium ${workflow.enabled ? "bg-green-600 text-white hover:bg-green-700" : "pointer-events-none bg-gray-100 text-gray-400"}`}
          >
            Preview for project
          </Link>
        </div>
      </div>

      {editDisabledReason ? <p className="mt-4 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">{editDisabledReason}</p> : null}

      <div className="mt-4 grid gap-3 md:grid-cols-5">
        <Mini label="Duration" value={`${workflow.total_duration_days || 0} days`} />
        <Mini label="Display order" value={workflow.display_order ?? "—"} />
        <Mini label="Overrides" value={workflow.override_count} />
        <Mini label="Cycles" value={workflow.usage_count ?? 0} />
        <Mini label="Android visible" value={workflow.assignment_rule === "ANDROID_VISIBLE" ? "Yes" : "No"} />
      </div>

      <div className="mt-4 grid gap-3 rounded-lg border bg-gray-50 p-3 md:grid-cols-[1fr_140px_auto]">
        <label className="text-xs font-medium text-gray-500">
          Display label
          <input
            value={draft.label}
            disabled={!canEdit}
            onChange={(event) => onUpdateDraft(workflow.workflow_template_id, { label: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
            placeholder="Label shown to Android/admin"
          />
        </label>
        <label className="text-xs font-medium text-gray-500">
          Order
          <input
            type="number"
            value={draft.displayOrder}
            disabled={!canEdit}
            onChange={(event) => onUpdateDraft(workflow.workflow_template_id, { displayOrder: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
            placeholder="0"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            disabled={isUpdating || !canEdit}
            onClick={() => onRequestWorkflowChange(workflow, workflow.enabled, "SAVE_METADATA")}
            className="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-wait disabled:opacity-60"
          >
            {isUpdating ? "Saving..." : "Save metadata"}
          </button>
        </div>
      </div>

      {workflow.overrides.length > 0 && (
        <div className="mt-4 rounded-lg border bg-gray-50 p-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Applied overrides</p>
          <div className="flex flex-wrap gap-2">
            {workflow.overrides.map((override) => (
              <span key={override.id} className="rounded bg-white px-2 py-1 text-xs text-gray-700 shadow-sm">
                {override.operation} {override.target_type}:{override.target_code}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}



function formatDateTime(value?: string | null) {
  if (!value) return "?";
  return new Date(value).toLocaleString();
}

function AssignmentAuditPanel({ audit }: { audit: ProjectWorkflowAssignmentAuditResponse | null }) {
  const events = audit?.events || [];
  return (
    <div className="mt-6 rounded-lg bg-white p-5 shadow">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Assignment history</h2>
          <p className="text-sm text-gray-500">Recent project workflow enablement and metadata changes.</p>
        </div>
        <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700">{events.length} event(s)</span>
      </div>
      {events.length === 0 ? (
        <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">No project workflow assignment changes have been audited yet.</p>
      ) : (
        <div className="max-h-[520px] space-y-3 overflow-auto">
          {events.map((event) => {
            const before = event.before || {};
            const after = event.after || {};
            const metadata = event.metadata || {};
            return (
              <details key={event.id} className="rounded border border-gray-200 bg-gray-50 p-3 text-sm">
                <summary className="cursor-pointer list-none">
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap gap-2 text-xs">
                        <span className="rounded bg-white px-2 py-1 font-medium text-gray-700">{event.action}</span>
                        <span className="rounded bg-white px-2 py-1 font-mono text-gray-600">{event.target_code}</span>
                        {metadata.enabled !== undefined ? <span className="rounded bg-white px-2 py-1 text-gray-700">enabled: {String(metadata.enabled)}</span> : null}
                      </div>
                      <p className="mt-2 text-gray-700">{event.reason || "Project workflow assignment updated."}</p>
                    </div>
                    <div className="text-xs text-gray-500 md:text-right">
                      <p>{formatDateTime(event.created_at)}</p>
                      {event.actor_id ? <p>Actor {event.actor_id}</p> : null}
                    </div>
                  </div>
                </summary>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <ImpactItem title="Before" detail={`enabled: ${String(before.enabled ?? "?")}; order: ${String(before.display_order ?? "?")}`} />
                  <ImpactItem title="After" detail={`enabled: ${String(after.enabled ?? "?")}; order: ${String(after.display_order ?? "?")}`} tone={after.enabled ? "ok" : "warn"} />
                </div>
                <pre className="mt-3 max-h-56 overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">{JSON.stringify({ before, after, metadata }, null, 2)}</pre>
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkflowChangeImpactModal({
  summary,
  change,
  draft,
  updating,
  onCancel,
  onConfirm,
  reason,
  onReasonChange,
}: {
  summary: ProjectWorkflowEnablementsResponse;
  change: PendingWorkflowChange;
  draft: { label: string; displayOrder: string };
  updating: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  reason: string;
  onReasonChange: (value: string) => void;
}) {
  const workflow = change.workflow;
  const currentlyAndroidVisible = workflow.assignment_rule === "ANDROID_VISIBLE";
  const willBeAndroidVisible = change.enabled && workflow.crop_scope_allowed !== false;
  const visibilityChange = currentlyAndroidVisible === willBeAndroidVisible ? "No Android visibility change" : willBeAndroidVisible ? "Will become Android visible" : "Will be hidden from Android";
  const intentLabel = change.intent === "ENABLE" ? "Enable workflow" : change.intent === "DISABLE" ? "Disable workflow" : "Save workflow metadata";
  const activeCycles = workflow.active_usage_count ?? 0;
  const totalCycles = workflow.usage_count ?? 0;
  const blockedByCrop = workflow.crop_scope_allowed === false || workflow.visibility_status === "CROP_SCOPE_BLOCKED";
  const labelChanged = draft.label.trim() && draft.label.trim() !== labelText(workflow.label);
  const orderChanged = draft.displayOrder.trim() !== String(workflow.display_order ?? "");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5 shadow-2xl">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Confirm project workflow change</h2>
            <p className="mt-1 text-sm text-gray-500">Review Android visibility and existing usage before changing this project assignment.</p>
          </div>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700">{intentLabel}</span>
        </div>

        <div className="mt-5 rounded-lg border border-gray-200 bg-gray-50 p-4">
          <p className="font-semibold text-gray-900">{labelText(workflow.label)}</p>
          <p className="mt-1 text-xs font-mono text-gray-500">{workflow.workflow_template_code} ? v{workflow.version} ? {workflow.workflow_template_version_id}</p>
          <p className="mt-2 text-sm text-gray-600">{workflow.crop_name} ? {workflow.crop_code} ? {workflow.season_code} ? {workflow.propagation_type_code || "?"}</p>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <ImpactItem title="Android visibility" detail={`${currentlyAndroidVisible ? "Currently visible" : "Currently hidden"} ? ${willBeAndroidVisible ? "visible" : "hidden"}`} tone={willBeAndroidVisible ? "ok" : currentlyAndroidVisible ? "warn" : "neutral"} />
          <ImpactItem title="Change result" detail={visibilityChange} tone={currentlyAndroidVisible && !willBeAndroidVisible ? "warn" : willBeAndroidVisible ? "ok" : "neutral"} />
          <ImpactItem title="Existing crop cycles" detail={`${totalCycles} total, ${activeCycles} active using this workflow/template.`} tone={activeCycles ? "warn" : "neutral"} />
          <ImpactItem title="Crop scope" detail={blockedByCrop ? "Blocked by project crop scope" : "Allowed by project crop scope"} tone={blockedByCrop ? "error" : "ok"} />
          <ImpactItem title="Project lifecycle" detail={summary.safe_edit_lifecycle.can_edit_project_workflows ? "Project workflow assignments are editable." : "Project is locked for in-place workflow assignment edits."} tone={summary.safe_edit_lifecycle.can_edit_project_workflows ? "ok" : "warn"} />
          <ImpactItem title="Metadata changes" detail={`${labelChanged ? "Label changed" : "Label unchanged"}; ${orderChanged ? "order changed" : "order unchanged"}.`} tone={labelChanged || orderChanged ? "warn" : "neutral"} />
        </div>

        <label className="mt-4 block text-sm font-medium text-gray-700">
          Change reason
          <textarea
            value={reason}
            onChange={(event) => onReasonChange(event.target.value)}
            className="mt-1 min-h-20 w-full rounded border px-3 py-2 text-sm font-normal text-gray-900"
            placeholder="Why is this project workflow assignment being changed?"
          />
        </label>

        {summary.safe_edit_lifecycle.reasons.length ? (
          <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-semibold">Lifecycle notes</p>
            <ul className="mt-2 list-disc pl-5">
              {summary.safe_edit_lifecycle.reasons.map((reason) => <li key={reason.code}>{reason.message}</li>)}
            </ul>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button type="button" disabled={updating} onClick={onCancel} className="rounded border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60">Cancel</button>
          <button type="button" disabled={updating || blockedByCrop && change.enabled} onClick={onConfirm} className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60">
            {updating ? "Applying..." : "Confirm change"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ImpactItem({ title, detail, tone = "neutral" }: { title: string; detail: string; tone?: "neutral" | "ok" | "warn" | "error" }) {
  const toneClass = tone === "ok" ? "border-green-200 bg-green-50 text-green-800" : tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-900" : tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-gray-200 bg-white text-gray-700";
  return (
    <div className={`rounded border p-3 text-sm ${toneClass}`}>
      <p className="text-xs font-semibold uppercase opacity-70">{title}</p>
      <p className="mt-1 font-medium">{detail}</p>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded bg-gray-50 p-3">
      <p className="text-[10px] uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 font-semibold text-gray-900">{value}</p>
    </div>
  );
}
