"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  workflowCatalogApi,
  type WorkflowPreviewResponse,
  type WorkflowRecommendation,
  type WorkflowStage,
  type WorkflowPreviewWarning,
} from "@/lib/api";

type WorkflowTargetType = "STAGE" | "RECOMMENDATION";
type WorkflowOverrideOperation = "HIDE" | "RENAME" | "CHANGE_DURATION" | "CHANGE_OFFSET" | "CHANGE_QUANTITY";

function labelText(value: Record<string, string> | string | undefined | null) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "";
}

export default function WorkflowPreviewPage() {
  const params = useParams<{ versionId: string }>();
  const searchParams = useSearchParams();
  const [preview, setPreview] = useState<WorkflowPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyTarget, setBusyTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!params.versionId) return;
    const projectId = searchParams.get("project_id") || undefined;
    workflowCatalogApi
      .preview(params.versionId, { projectId })
      .then(setPreview)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.versionId, searchParams]);


  const createOverride = async (
    targetType: WorkflowTargetType,
    targetCode: string,
    operation: WorkflowOverrideOperation,
    overridePayload: Record<string, unknown>,
    reason: string,
  ) => {
    if (!preview?.project_id) return;
    setBusyTarget(`${targetType}:${targetCode}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.createProjectOverride(preview.project_id, {
        template_version_id: preview.workflow_template_version_id,
        target_type: targetType,
        target_code: targetCode,
        operation,
        override_payload: overridePayload,
        priority: 100,
        reason,
      });
      setPreview(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create override");
    } finally {
      setBusyTarget(null);
    }
  };

  const removeOverride = async (overrideId: string) => {
    if (!preview?.project_id) return;
    setBusyTarget(`OVERRIDE:${overrideId}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.deleteProjectOverride(preview.project_id, overrideId);
      setPreview(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove override");
    } finally {
      setBusyTarget(null);
    }
  };

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
          {preview.project_id ? <Badge>Project scoped preview</Badge> : null}
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
        <OverridesPanel
          overrides={preview.applied_overrides}
          projectScoped={Boolean(preview.project_id)}
          busyTarget={busyTarget}
          onRemoveOverride={removeOverride}
        />
      </div>

      <div className="mb-6 rounded-lg bg-white shadow">
        <div className="border-b p-5">
          <h2 className="text-lg font-semibold text-gray-900">Rendered Stages & Recommendations</h2>
        </div>
        <div className="divide-y">
          {stages.map((stage) => (
            <StagePreview
              key={stage.code}
              stage={stage}
              projectScoped={Boolean(preview.project_id)}
              busyTarget={busyTarget}
              onCreateOverride={createOverride}
            />
          ))}
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

function OverridesPanel({
  overrides,
  projectScoped,
  busyTarget,
  onRemoveOverride,
}: {
  overrides: WorkflowPreviewResponse["applied_overrides"];
  projectScoped: boolean;
  busyTarget: string | null;
  onRemoveOverride: (overrideId: string) => void;
}) {
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
              {projectScoped ? (
                <button
                  type="button"
                  disabled={busyTarget === `OVERRIDE:${override.id}`}
                  onClick={() => onRemoveOverride(override.id)}
                  className="mt-3 rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                >
                  {busyTarget === `OVERRIDE:${override.id}` ? "Removing..." : "Remove override"}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StagePreview({
  stage,
  projectScoped,
  busyTarget,
  onCreateOverride,
}: {
  stage: WorkflowStage;
  projectScoped: boolean;
  busyTarget: string | null;
  onCreateOverride: (
    targetType: WorkflowTargetType,
    targetCode: string,
    operation: WorkflowOverrideOperation,
    overridePayload: Record<string, unknown>,
    reason: string,
  ) => void;
}) {
  const recs = stage.recommended_activities || [];
  const [stageName, setStageName] = useState(labelText(stage.name));
  const [durationDays, setDurationDays] = useState(String(stage.duration_days));

  useEffect(() => {
    setStageName(labelText(stage.name));
    setDurationDays(String(stage.duration_days));
  }, [stage.name, stage.duration_days]);

  const stageBusy = busyTarget === `STAGE:${stage.code}`;

  return (
    <details open={stage.order === 1}>
      <summary className="cursor-pointer list-none p-5 hover:bg-gray-50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Stage {stage.order} ? {stage.code}</p>
            <h3 className="mt-1 font-semibold text-gray-900">{labelText(stage.name)}</h3>
            <p className="mt-1 text-sm text-gray-500">{stage.duration_days} days ? {recs.length} recommendations</p>
          </div>
          <div className="flex items-center gap-3">
            {projectScoped ? (
              <button
                type="button"
                disabled={stageBusy}
                onClick={(event) => {
                  event.preventDefault();
                  onCreateOverride("STAGE", stage.code, "HIDE", {}, `Hide stage ${stage.code}`);
                }}
                className="rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
              >
                {stageBusy ? "Saving..." : "Hide stage"}
              </button>
            ) : null}
            <span className="text-sm text-gray-400">?</span>
          </div>
        </div>
      </summary>
      <div className="px-5 pb-5">
        {projectScoped ? (
          <div className="mb-4 grid gap-3 rounded-lg border border-dashed bg-gray-50 p-3 md:grid-cols-[1fr_140px_auto_auto]">
            <label className="text-xs font-medium text-gray-500">
              Stage label
              <input
                value={stageName}
                onChange={(event) => setStageName(event.target.value)}
                className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
              />
            </label>
            <label className="text-xs font-medium text-gray-500">
              Duration
              <input
                type="number"
                min="0"
                value={durationDays}
                onChange={(event) => setDurationDays(event.target.value)}
                className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
              />
            </label>
            <button
              type="button"
              disabled={stageBusy || !stageName.trim()}
              onClick={() => onCreateOverride("STAGE", stage.code, "RENAME", { name: { en: stageName.trim(), hi: stageName.trim() } }, `Rename stage ${stage.code}`)}
              className="self-end rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
            >
              Rename stage
            </button>
            <button
              type="button"
              disabled={stageBusy || durationDays === ""}
              onClick={() => onCreateOverride("STAGE", stage.code, "CHANGE_DURATION", { duration_days: Number(durationDays) }, `Change duration for ${stage.code}`)}
              className="self-end rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
            >
              Save duration
            </button>
          </div>
        ) : null}

        {recs.length === 0 ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No recommendations.</p> : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Day</th>
                  <th className="px-3 py-2 text-left font-medium">Activity</th>
                  <th className="px-3 py-2 text-left font-medium">Input</th>
                  <th className="px-3 py-2 text-left font-medium">Quantity</th>
                  {projectScoped ? <th className="px-3 py-2 text-right font-medium">Override editor</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y">
                {recs.map((rec, index) => (
                  <RecommendationPreview
                    key={`${rec.input_name}-${index}`}
                    stageCode={stage.code}
                    rec={rec}
                    projectScoped={projectScoped}
                    busyTarget={busyTarget}
                    onCreateOverride={onCreateOverride}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}

function RecommendationPreview({
  stageCode,
  rec,
  projectScoped,
  busyTarget,
  onCreateOverride,
}: {
  stageCode: string;
  rec: WorkflowRecommendation;
  projectScoped: boolean;
  busyTarget: string | null;
  onCreateOverride: (
    targetType: WorkflowTargetType,
    targetCode: string,
    operation: WorkflowOverrideOperation,
    overridePayload: Record<string, unknown>,
    reason: string,
  ) => void;
}) {
  const targetCode = rec.input_code ? `${stageCode}|${rec.input_code}` : `${stageCode}|${rec.activity_type}|${rec.input_name}`;
  const [inputName, setInputName] = useState(rec.input_name || "");
  const [dayOffset, setDayOffset] = useState(String(rec.day_offset ?? 0));
  const [quantity, setQuantity] = useState(rec.typical_quantity || "");

  useEffect(() => {
    setInputName(rec.input_name || "");
    setDayOffset(String(rec.day_offset ?? 0));
    setQuantity(rec.typical_quantity || "");
  }, [rec.input_name, rec.day_offset, rec.typical_quantity]);

  const recBusy = busyTarget === `RECOMMENDATION:${targetCode}`;

  return (
    <tr>
      <td className="px-3 py-2 font-mono text-xs">+{rec.day_offset}</td>
      <td className="px-3 py-2"><span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{rec.activity_type}</span></td>
      <td className="px-3 py-2">
        <p className="font-medium text-gray-900">{rec.input_name}</p>
        <p className="font-mono text-xs text-gray-400">{rec.input_code || "No input_code"}</p>
      </td>
      <td className="px-3 py-2 text-gray-600">{rec.typical_quantity || "?"}</td>
      {projectScoped ? (
        <td className="min-w-[360px] px-3 py-2 text-right">
          <div className="grid gap-2 text-left">
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <input
                value={inputName}
                onChange={(event) => setInputName(event.target.value)}
                className="rounded border px-2 py-1 text-xs text-gray-900"
                aria-label="Recommendation label"
              />
              <button
                type="button"
                disabled={recBusy || !inputName.trim()}
                onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "RENAME", { input_name: inputName.trim() }, `Rename recommendation ${targetCode}`)}
                className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
              >
                Rename
              </button>
            </div>
            <div className="grid grid-cols-[80px_1fr_auto_auto_auto] gap-2">
              <input
                type="number"
                value={dayOffset}
                onChange={(event) => setDayOffset(event.target.value)}
                className="rounded border px-2 py-1 text-xs text-gray-900"
                aria-label="Day offset"
              />
              <input
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                className="rounded border px-2 py-1 text-xs text-gray-900"
                aria-label="Typical quantity"
              />
              <button
                type="button"
                disabled={recBusy || dayOffset === ""}
                onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "CHANGE_OFFSET", { day_offset: Number(dayOffset) }, `Change offset for ${targetCode}`)}
                className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
              >
                Offset
              </button>
              <button
                type="button"
                disabled={recBusy || !quantity.trim()}
                onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "CHANGE_QUANTITY", { typical_quantity: quantity.trim() }, `Change quantity for ${targetCode}`)}
                className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
              >
                Quantity
              </button>
              <button
                type="button"
                disabled={recBusy}
                onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "HIDE", {}, `Hide recommendation ${targetCode}`)}
                className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
              >
                {recBusy ? "Saving..." : "Hide"}
              </button>
            </div>
          </div>
        </td>
      ) : null}
    </tr>
  );
}
