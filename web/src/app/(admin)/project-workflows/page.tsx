"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  projectsApi,
  workflowCatalogApi,
  type Project,
  type ProjectWorkflowEnablementItem,
  type ProjectWorkflowEnablementsResponse,
} from "@/lib/api";

function labelText(value: Record<string, string> | string | undefined | null) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "";
}

export default function ProjectWorkflowsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [summary, setSummary] = useState<ProjectWorkflowEnablementsResponse | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatingWorkflowId, setUpdatingWorkflowId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { label: string; displayOrder: string }>>({});

  useEffect(() => {
    projectsApi
      .list()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId(items[0]?.id || "");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoadingSummary(true);
    workflowCatalogApi
      .projectEnablements(selectedProjectId)
      .then(setSummary)
      .catch((e) => setError(e.message))
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

  const updateWorkflow = async (workflow: ProjectWorkflowEnablementItem, enabled: boolean) => {
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
      });
      setSummary(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update workflow enablement");
    } finally {
      setUpdatingWorkflowId(null);
    }
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
  if (error) return <div className="text-red-500">Error: {error}</div>;

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
          onUpdateWorkflow={updateWorkflow}
          drafts={drafts}
          onUpdateDraft={updateDraft}
        />
      )}
    </div>
  );
}

function ProjectWorkflowSummary({
  summary,
  updatingWorkflowId,
  onUpdateWorkflow,
  drafts,
  onUpdateDraft,
}: {
  summary: ProjectWorkflowEnablementsResponse;
  updatingWorkflowId: string | null;
  onUpdateWorkflow: (workflow: ProjectWorkflowEnablementItem, enabled: boolean) => void;
  drafts: Record<string, { label: string; displayOrder: string }>;
  onUpdateDraft: (workflowId: string, patch: Partial<{ label: string; displayOrder: string }>) => void;
}) {
  const lifecycle = summary.safe_edit_lifecycle;
  const canEdit = lifecycle.can_edit_project_workflows;

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
              {canEdit ? "Workflow configuration editable" : "Workflow configuration locked"}
            </p>
            <p className={`mt-1 text-sm ${canEdit ? "text-green-700" : "text-amber-800"}`}>
              {canEdit
                ? "This project has no enrolled field data yet. Enablement and override changes are still allowed."
                : lifecycle.suggested_action || "Create a new workflow version for future cycles instead of editing this project in-place."}
            </p>
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

      <div className="grid gap-4">
        {summary.workflows.map((workflow) => (
          <WorkflowVisibilityCard
            key={workflow.workflow_template_version_id}
            workflow={workflow}
            projectId={summary.project.id}
            isUpdating={updatingWorkflowId === workflow.workflow_template_id}
            onUpdateWorkflow={onUpdateWorkflow}
            draft={drafts[workflow.workflow_template_id] || { label: labelText(workflow.label), displayOrder: workflow.display_order != null ? String(workflow.display_order) : "" }}
            onUpdateDraft={onUpdateDraft}
            canEdit={canEdit}
          />
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
  onUpdateWorkflow,
  draft,
  onUpdateDraft,
  canEdit,
}: {
  workflow: ProjectWorkflowEnablementItem;
  projectId: string;
  isUpdating: boolean;
  onUpdateWorkflow: (workflow: ProjectWorkflowEnablementItem, enabled: boolean) => void;
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
          </div>
          <p className="mt-1 text-sm text-gray-500">
            {workflow.crop_name} · {workflow.crop_code} · {workflow.season_code} · {workflow.propagation_type_code || "—"}
          </p>
          <p className="mt-2 font-mono text-xs text-gray-400">{workflow.workflow_template_code} · v{workflow.version}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          {workflow.enabled ? (
            <button
              type="button"
              disabled={isUpdating || !canEdit}
              onClick={() => onUpdateWorkflow(workflow, false)}
              className="rounded-lg border border-red-200 px-3 py-2 font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
            >
              {isUpdating ? "Updating..." : "Disable"}
            </button>
          ) : (
            <button
              type="button"
              disabled={isUpdating || !canEdit}
              onClick={() => onUpdateWorkflow(workflow, true)}
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

      <div className="mt-4 grid gap-3 md:grid-cols-4">
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
            onClick={() => onUpdateWorkflow(workflow, workflow.enabled)}
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

function Mini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded bg-gray-50 p-3">
      <p className="text-[10px] uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 font-semibold text-gray-900">{value}</p>
    </div>
  );
}
