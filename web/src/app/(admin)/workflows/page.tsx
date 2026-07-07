"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  workflowCatalogApi,
  type EnabledCropWorkflow,
  type WorkflowAuditResponse,
  type WorkflowRecommendation,
  type WorkflowStage,
  type WorkflowTemplateVersionsResponse,
} from "@/lib/api";

function labelText(value: Record<string, string> | string | undefined | null) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "";
}

function countRecommendations(workflow: EnabledCropWorkflow) {
  return (workflow.stages || []).reduce(
    (sum, stage) => sum + (stage.recommended_activities?.length || 0),
    0
  );
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<EnabledCropWorkflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cropFilter, setCropFilter] = useState("");

  useEffect(() => {
    workflowCatalogApi
      .enabledCropWorkflows({ includeStages: true })
      .then((data) => {
        setWorkflows(data.workflows);
        setSelectedId(data.workflows[0]?.workflow_template_id || null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const cropCodes = useMemo(
    () => Array.from(new Set(workflows.map((w) => w.crop_code))).sort(),
    [workflows]
  );

  const filtered = cropFilter
    ? workflows.filter((w) => w.crop_code === cropFilter)
    : workflows;

  const selected = filtered.find((w) => w.workflow_template_id === selectedId) || filtered[0];

  if (loading) return <div className="text-gray-500">Loading workflow catalog...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Crop Workflows</h1>
          <p className="mt-1 text-sm text-gray-500">
            Read-only view of enabled crop-cycle templates, stages, recommendations, and linked input codes.
          </p>
        </div>
        <select
          value={cropFilter}
          onChange={(e) => {
            setCropFilter(e.target.value);
            setSelectedId(null);
          }}
          className="rounded-lg border px-3 py-2 text-sm"
        >
          <option value="">All crops</option>
          {cropCodes.map((code) => (
            <option key={code} value={code}>{code}</option>
          ))}
        </select>
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="space-y-3">
          {filtered.map((workflow) => (
            <button
              key={workflow.workflow_template_id}
              onClick={() => setSelectedId(workflow.workflow_template_id)}
              className={`w-full rounded-lg border bg-white p-4 text-left shadow-sm transition ${
                selected?.workflow_template_id === workflow.workflow_template_id
                  ? "border-green-500 ring-2 ring-green-100"
                  : "border-transparent hover:border-green-200"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-semibold text-gray-900">{labelText(workflow.label)}</h2>
                  <p className="mt-1 text-xs text-gray-500">
                    {workflow.crop_name} · {workflow.season_code} · {workflow.propagation_type_code || "—"}
                  </p>
                </div>
                <span className="rounded bg-green-50 px-2 py-1 text-xs font-medium text-green-700">
                  {workflow.enablement_source === "explicit" ? "Explicit" : "Default"}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-gray-600">
                <Metric label="Stages" value={workflow.stages?.length || 0} />
                <Metric label="Recs" value={countRecommendations(workflow)} />
                <Metric label="Days" value={workflow.total_duration_days || 0} />
              </div>
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="rounded-lg bg-white p-8 text-center text-sm text-gray-400 shadow">
              No workflows match this filter.
            </div>
          )}
        </div>

        {selected ? <WorkflowDetail workflow={selected} /> : null}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded bg-gray-50 p-2">
      <p className="text-[10px] uppercase tracking-wide text-gray-400">{label}</p>
      <p className="font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function WorkflowDetail({ workflow }: { workflow: EnabledCropWorkflow }) {
  const [versions, setVersions] = useState<WorkflowTemplateVersionsResponse | null>(null);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versionError, setVersionError] = useState<string | null>(null);
  const [busyVersionId, setBusyVersionId] = useState<string | null>(null);
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null);
  const [audit, setAudit] = useState<WorkflowAuditResponse | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  const loadVersions = () => {
    setVersionLoading(true);
    setVersionError(null);
    workflowCatalogApi
      .templateVersions(workflow.workflow_template_id)
      .then(setVersions)
      .catch((e) => setVersionError(e instanceof Error ? e.message : "Failed to load workflow versions"))
      .finally(() => setVersionLoading(false));
  };

  const loadAudit = () => {
    setAuditLoading(true);
    setAuditError(null);
    workflowCatalogApi
      .templateAudit(workflow.workflow_template_id, { limit: 100 })
      .then(setAudit)
      .catch((e) => setAuditError(e instanceof Error ? e.message : "Failed to load workflow audit trail"))
      .finally(() => setAuditLoading(false));
  };

  useEffect(() => {
    setVersions(null);
    setAudit(null);
    setRestoreMessage(null);
    loadVersions();
    loadAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow.workflow_template_id]);

  const restoreDraft = async (versionId: string) => {
    setBusyVersionId(versionId);
    setVersionError(null);
    setRestoreMessage(null);
    try {
      const draft = await workflowCatalogApi.restoreDraftVersion(workflow.workflow_template_id, versionId);
      setRestoreMessage(`Draft ${draft.version} created from selected version.`);
      await workflowCatalogApi.templateVersions(workflow.workflow_template_id).then(setVersions);
      await workflowCatalogApi.templateAudit(workflow.workflow_template_id, { limit: 100 }).then(setAudit);
    } catch (e) {
      setVersionError(e instanceof Error ? e.message : "Failed to restore draft");
    } finally {
      setBusyVersionId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white shadow">
        <div className="border-b p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="text-xl font-bold text-gray-900">{labelText(workflow.label)}</h2>
              <p className="mt-1 text-sm text-gray-500">
                {workflow.workflow_template_code} ? version {workflow.version} ? {workflow.status}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge>{workflow.crop_code}</Badge>
              <Badge>{workflow.season_code}</Badge>
              <Badge>{workflow.propagation_type_code || "Propagation ?"}</Badge>
              <Link
                href={`/workflows/preview/${workflow.workflow_template_version_id}`}
                className="rounded-full bg-green-600 px-3 py-1 font-medium text-white hover:bg-green-700"
              >
                Preview JSON
              </Link>
            </div>
          </div>
        </div>

        <div className="divide-y">
          {(workflow.stages || []).map((stage) => (
            <StageRow key={stage.code} stage={stage} />
          ))}
        </div>
      </div>

      <div className="rounded-lg bg-white p-5 shadow">
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Version History</h3>
            <p className="text-sm text-gray-500">Published, archived, and draft workflow versions for this template.</p>
          </div>
          {versions ? (
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge>Total {versions.counts.total}</Badge>
              <Badge>Draft {versions.counts.draft}</Badge>
              <Badge>Published {versions.counts.published}</Badge>
              <Badge>Archived {versions.counts.archived}</Badge>
            </div>
          ) : null}
        </div>

        {restoreMessage ? <div className="mb-3 rounded bg-green-50 p-3 text-sm text-green-700">{restoreMessage}</div> : null}
        {versionError ? <div className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{versionError}</div> : null}
        {versionLoading ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">Loading version history...</p> : null}

        {versions && versions.versions.length > 0 ? (
          <div className="space-y-3">
            {versions.versions.map((version) => (
              <div key={version.workflow_template_version_id} className="rounded border p-3 text-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge>{version.status}</Badge>
                      {version.is_current_published ? <Badge>Android active</Badge> : null}
                      <Badge>{version.stage_count} stages</Badge>
                      <Badge>{version.recommendation_count} recs</Badge>
                    </div>
                    <p className="mt-2 font-mono text-xs text-gray-500">{version.workflow_template_version_id}</p>
                    <p className="mt-1 font-semibold text-gray-900">Version {version.version}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      Published: {version.published_at ? new Date(version.published_at).toLocaleString() : "?"} ? Updated: {version.updated_at ? new Date(version.updated_at).toLocaleString() : "?"}
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2 text-xs">
                    <Link
                      href={`/workflows/preview/${version.workflow_template_version_id}${version.status === "DRAFT" ? "?draft=true" : ""}`}
                      className="rounded border border-green-200 px-3 py-1.5 font-medium text-green-700 hover:bg-green-50"
                    >
                      Preview
                    </Link>
                    {version.status === "PUBLISHED" || version.status === "ARCHIVED" ? (
                      <button
                        type="button"
                        disabled={busyVersionId === version.workflow_template_version_id}
                        onClick={() => restoreDraft(version.workflow_template_version_id)}
                        className="rounded border border-blue-200 px-3 py-1.5 font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-wait disabled:opacity-60"
                      >
                        {busyVersionId === version.workflow_template_version_id ? "Restoring..." : "Restore as draft"}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : !versionLoading ? (
          <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No version history found.</p>
        ) : null}
      </div>

      <div className="rounded-lg bg-white p-5 shadow">
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Audit Trail</h3>
            <p className="text-sm text-gray-500">Latest workflow edit, validation, restore, and publish events.</p>
          </div>
          <button
            type="button"
            disabled={auditLoading}
            onClick={loadAudit}
            className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60"
          >
            {auditLoading ? "Refreshing..." : "Refresh audit"}
          </button>
        </div>
        {auditError ? <div className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{auditError}</div> : null}
        {auditLoading ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">Loading audit trail...</p> : null}
        {audit && audit.events.length > 0 ? (
          <div className="max-h-[520px] space-y-3 overflow-auto">
            {audit.events.map((event) => (
              <details key={event.id} className="rounded border p-3 text-sm">
                <summary className="cursor-pointer list-none">
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap gap-2 text-xs">
                        <Badge>{event.action}</Badge>
                        <Badge>{event.target_type}</Badge>
                        {event.actor_id ? <Badge>Actor {event.actor_id.slice(0, 8)}</Badge> : null}
                      </div>
                      <p className="mt-2 font-mono text-xs text-gray-500">{event.workflow_template_version_id || "No version"}</p>
                      {event.target_code ? <p className="mt-1 text-xs text-gray-600">Target: {event.target_code}</p> : null}
                    </div>
                    <p className="text-xs text-gray-500">{event.created_at ? new Date(event.created_at).toLocaleString() : "?"}</p>
                  </div>
                </summary>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  <pre className="max-h-64 overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">{JSON.stringify(event.before || {}, null, 2)}</pre>
                  <pre className="max-h-64 overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">{JSON.stringify(event.after || {}, null, 2)}</pre>
                </div>
              </details>
            ))}
          </div>
        ) : !auditLoading ? (
          <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No audit events recorded yet.</p>
        ) : null}
      </div>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-gray-100 px-3 py-1 font-medium text-gray-700">{children}</span>;
}

function StageRow({ stage }: { stage: WorkflowStage }) {
  const recs = stage.recommended_activities || [];
  return (
    <details className="group" open={stage.order === 1}>
      <summary className="cursor-pointer list-none p-5 hover:bg-gray-50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
              Stage {stage.order} · {stage.code}
            </p>
            <h3 className="mt-1 font-semibold text-gray-900">{labelText(stage.name)}</h3>
            <p className="mt-1 text-sm text-gray-500">
              {stage.duration_days} days · {recs.length} recommendations
            </p>
          </div>
          <span className="text-sm text-gray-400 group-open:rotate-180">⌄</span>
        </div>
      </summary>

      <div className="px-5 pb-5">
        {recs.length === 0 ? (
          <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No recommendations configured.</p>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Day</th>
                  <th className="px-3 py-2 text-left font-medium">Activity</th>
                  <th className="px-3 py-2 text-left font-medium">Input</th>
                  <th className="px-3 py-2 text-left font-medium">Quantity</th>
                  <th className="px-3 py-2 text-left font-medium">Critical</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {recs.map((rec, index) => <RecommendationRow key={`${rec.input_name}-${index}`} rec={rec} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}

function RecommendationRow({ rec }: { rec: WorkflowRecommendation }) {
  return (
    <tr>
      <td className="px-3 py-2 font-mono text-xs">+{rec.day_offset}</td>
      <td className="px-3 py-2">
        <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{rec.activity_type}</span>
      </td>
      <td className="px-3 py-2">
        <p className="font-medium text-gray-900">{rec.input_name}</p>
        <p className="font-mono text-xs text-gray-400">{rec.input_code || "No input_code"}</p>
      </td>
      <td className="px-3 py-2 text-gray-600">{rec.typical_quantity || "—"}</td>
      <td className="px-3 py-2">{rec.is_critical ? "✅" : "—"}</td>
    </tr>
  );
}
