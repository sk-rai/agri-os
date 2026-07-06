"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  workflowCatalogApi,
  type WorkflowPreviewResponse,
  type WorkflowRecommendation,
  type WorkflowStage,
  type WorkflowPreviewWarning,
} from "@/lib/api";

function labelText(value: Record<string, string> | string | undefined | null) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "";
}

export default function WorkflowPreviewPage() {
  const params = useParams<{ versionId: string }>();
  const [preview, setPreview] = useState<WorkflowPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.versionId) return;
    workflowCatalogApi
      .preview(params.versionId)
      .then(setPreview)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.versionId]);

  if (loading) return <div className="text-gray-500">Loading workflow preview...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!preview) return null;

  const stages = preview.android_preview.stages || [];
  const recommendations = stages.flatMap((stage) => stage.recommended_activities || []);
  const warningCounts = preview.warnings.reduce<Record<string, number>>((acc, warning) => {
    acc[warning.level] = (acc[warning.level] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <Link href="/workflows" className="text-sm text-green-700 hover:underline">← Back to workflows</Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900">Workflow Preview</h1>
          <p className="mt-1 text-sm text-gray-500">
            Final Android-rendered workflow after enablements and overrides are applied.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{preview.crop_code}</Badge>
          <Badge>{preview.season_code}</Badge>
          <Badge>{preview.propagation_type_code || "Propagation —"}</Badge>
          <Badge>{preview.enablement_source}</Badge>
        </div>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <Stat label="Stages" value={stages.length} />
        <Stat label="Recommendations" value={recommendations.length} />
        <Stat label="Duration days" value={preview.total_duration_days} />
        <Stat label="Warnings" value={preview.warnings.length} tone={preview.warnings.length ? "warn" : "ok"} />
      </div>

      <div className="mb-6 rounded-lg bg-white p-5 shadow">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{labelText(preview.label)}</h2>
            <p className="mt-1 text-sm text-gray-500">
              {preview.workflow_template_code} · version {preview.version} · {preview.status}
            </p>
          </div>
          <div className="text-right text-xs text-gray-500">
            <p>Template: <span className="font-mono">{preview.workflow_template_id}</span></p>
            <p>Version: <span className="font-mono">{preview.workflow_template_version_id}</span></p>
          </div>
        </div>
      </div>

      <div className="mb-6 grid gap-6 xl:grid-cols-[420px_1fr]">
        <WarningsPanel warnings={preview.warnings} warningCounts={warningCounts} />
        <OverridesPanel overrides={preview.applied_overrides} />
      </div>

      <div className="mb-6 rounded-lg bg-white shadow">
        <div className="border-b p-5">
          <h2 className="text-lg font-semibold text-gray-900">Rendered Stages & Recommendations</h2>
        </div>
        <div className="divide-y">
          {stages.map((stage) => <StagePreview key={stage.code} stage={stage} />)}
        </div>
      </div>

      <details className="rounded-lg bg-gray-950 p-5 text-gray-100 shadow" open>
        <summary className="cursor-pointer text-sm font-semibold">Raw Android Preview JSON</summary>
        <pre className="mt-4 max-h-[520px] overflow-auto text-xs leading-relaxed">
          {JSON.stringify(preview.android_preview, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-gray-100 px-3 py-1 font-medium text-gray-700">{children}</span>;
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "warn" | "ok" }) {
  const toneClass = tone === "warn" ? "bg-yellow-50 text-yellow-700" : tone === "ok" ? "bg-green-50 text-green-700" : "bg-white text-gray-900";
  return (
    <div className={`rounded-lg p-4 shadow ${toneClass}`}>
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}

function WarningsPanel({ warnings, warningCounts }: { warnings: WorkflowPreviewWarning[]; warningCounts: Record<string, number> }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Warnings</h2>
        <div className="flex gap-2 text-xs">
          {Object.entries(warningCounts).map(([level, count]) => <Badge key={level}>{level}: {count}</Badge>)}
        </div>
      </div>
      {warnings.length === 0 ? (
        <p className="rounded bg-green-50 p-3 text-sm text-green-700">No preview warnings.</p>
      ) : (
        <div className="max-h-80 space-y-2 overflow-auto">
          {warnings.map((warning, index) => (
            <div key={`${warning.code}-${index}`} className="rounded border p-3 text-sm">
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${warning.level === "ERROR" ? "bg-red-100 text-red-700" : warning.level === "WARN" ? "bg-yellow-100 text-yellow-700" : "bg-blue-100 text-blue-700"}`}>
                  {warning.level}
                </span>
                <span className="font-mono text-xs text-gray-500">{warning.code}</span>
              </div>
              <p className="mt-2 text-gray-800">{warning.message}</p>
              {warning.target ? <p className="mt-1 font-mono text-xs text-gray-400">{warning.target}</p> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OverridesPanel({ overrides }: { overrides: WorkflowPreviewResponse["applied_overrides"] }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Applied Overrides</h2>
      {overrides.length === 0 ? (
        <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">No tenant/project overrides applied.</p>
      ) : (
        <div className="max-h-80 space-y-2 overflow-auto">
          {overrides.map((override) => (
            <div key={override.id} className="rounded border p-3 text-sm">
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge>{override.target_type}</Badge>
                <Badge>{override.operation}</Badge>
                <Badge>Priority {override.priority}</Badge>
              </div>
              <p className="mt-2 font-mono text-xs text-gray-500">{override.target_code}</p>
              {override.reason ? <p className="mt-1 text-gray-600">{override.reason}</p> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StagePreview({ stage }: { stage: WorkflowStage }) {
  const recs = stage.recommended_activities || [];
  return (
    <details open={stage.order === 1}>
      <summary className="cursor-pointer list-none p-5 hover:bg-gray-50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Stage {stage.order} · {stage.code}</p>
            <h3 className="mt-1 font-semibold text-gray-900">{labelText(stage.name)}</h3>
            <p className="mt-1 text-sm text-gray-500">{stage.duration_days} days · {recs.length} recommendations</p>
          </div>
          <span className="text-sm text-gray-400">⌄</span>
        </div>
      </summary>
      <div className="px-5 pb-5">
        {recs.length === 0 ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No recommendations.</p> : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Day</th>
                  <th className="px-3 py-2 text-left font-medium">Activity</th>
                  <th className="px-3 py-2 text-left font-medium">Input</th>
                  <th className="px-3 py-2 text-left font-medium">Quantity</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {recs.map((rec, index) => <RecommendationPreview key={`${rec.input_name}-${index}`} rec={rec} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}

function RecommendationPreview({ rec }: { rec: WorkflowRecommendation }) {
  return (
    <tr>
      <td className="px-3 py-2 font-mono text-xs">+{rec.day_offset}</td>
      <td className="px-3 py-2"><span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{rec.activity_type}</span></td>
      <td className="px-3 py-2">
        <p className="font-medium text-gray-900">{rec.input_name}</p>
        <p className="font-mono text-xs text-gray-400">{rec.input_code || "No input_code"}</p>
      </td>
      <td className="px-3 py-2 text-gray-600">{rec.typical_quantity || "—"}</td>
    </tr>
  );
}
