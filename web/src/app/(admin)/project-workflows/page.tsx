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

  if (loadingProjects) return <div className="text-gray-500">Loading projects...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Project Workflows</h1>
          <p className="mt-1 text-sm text-gray-500">
            Read-only view of which crop workflows are visible to each project and what overrides apply.
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
        <ProjectWorkflowSummary summary={summary} />
      )}
    </div>
  );
}

function ProjectWorkflowSummary({ summary }: { summary: ProjectWorkflowEnablementsResponse }) {
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

      <div className="mb-6 grid gap-4 md:grid-cols-5">
        <Stat label="Total" value={summary.counts.total} />
        <Stat label="Enabled" value={summary.counts.enabled} tone="ok" />
        <Stat label="Disabled" value={summary.counts.disabled} tone="warn" />
        <Stat label="Implicit" value={summary.counts.implicit_default} />
        <Stat label="Not visible" value={summary.counts.not_visible} />
      </div>

      <div className="grid gap-4">
        {summary.workflows.map((workflow) => (
          <WorkflowVisibilityCard key={workflow.workflow_template_version_id} workflow={workflow} projectId={summary.project.id} />
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

function WorkflowVisibilityCard({ workflow, projectId }: { workflow: ProjectWorkflowEnablementItem; projectId: string }) {
  const statusClass: Record<string, string> = {
    ENABLED: "bg-green-50 text-green-700",
    DISABLED: "bg-red-50 text-red-700",
    IMPLICIT_DEFAULT: "bg-blue-50 text-blue-700",
    NOT_VISIBLE: "bg-gray-100 text-gray-600",
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
        <Mini label="Enabled" value={workflow.enabled ? "Yes" : "No"} />
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
