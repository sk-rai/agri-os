"use client";

import { useEffect, useMemo, useState } from "react";
import {
  inputCatalogApi,
  projectsApi,
  type InputCategoryDto,
  type Project,
  type ProjectInputAssignmentDto,
  type ProjectInputAssignmentsResponse,
} from "@/lib/api";

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

export default function ProjectInputsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [categories, setCategories] = useState<InputCategoryDto[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [summary, setSummary] = useState<ProjectInputAssignmentsResponse | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [cropCode, setCropCode] = useState("");
  const [query, setQuery] = useState("");
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { reason: string; displayOrder: string }>>({});

  useEffect(() => {
    Promise.all([projectsApi.list(), inputCatalogApi.categories()])
      .then(([projectItems, categoryPayload]) => {
        setProjects(projectItems);
        setSelectedProjectId(projectItems[0]?.id || "");
        setCategories(categoryPayload.categories);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load project inputs"))
      .finally(() => setLoadingProjects(false));
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
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load input assignments"))
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update input assignment");
    } finally {
      setBusyCode(null);
    }
  };

  if (loadingProjects) return <div className="text-gray-500">Loading projects...</div>;
  if (error && !summary) return <div className="text-red-500">Error: {error}</div>;

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

          {error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
          {loadingSummary || !summary ? (
            <p className="text-gray-500">Loading input assignments...</p>
          ) : (
            <div className="space-y-3">
              {summary.inputs.map((item) => (
                <InputAssignmentCard
                  key={item.code}
                  item={item}
                  draft={drafts[item.code] || { reason: item.reason || "", displayOrder: item.display_order != null ? String(item.display_order) : "" }}
                  isBusy={busyCode === item.code}
                  onDraft={updateDraft}
                  onUpdate={updateAssignment}
                />
              ))}
              {summary.inputs.length === 0 ? (
                <div className="rounded-lg bg-white p-10 text-center text-gray-400 shadow">No inputs match this filter.</div>
              ) : null}
            </div>
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
}: {
  item: ProjectInputAssignmentDto;
  draft: { reason: string; displayOrder: string };
  isBusy: boolean;
  onDraft: (code: string, patch: Partial<{ reason: string; displayOrder: string }>) => void;
  onUpdate: (item: ProjectInputAssignmentDto, enabled: boolean) => void;
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
            disabled={isBusy}
            onClick={() => onUpdate(item, true)}
            className="rounded-lg border border-green-200 px-3 py-2 font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
          >
            {isBusy ? "Saving..." : "Enable"}
          </button>
          <button
            type="button"
            disabled={isBusy}
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
            onChange={(event) => onDraft(item.code, { displayOrder: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
            placeholder="1000"
          />
        </label>
        <label className="text-xs font-medium text-gray-500">
          Reason
          <input
            value={draft.reason}
            onChange={(event) => onDraft(item.code, { reason: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal"
            placeholder="Why this input is enabled/disabled"
          />
        </label>
        <div className="flex items-end">
          <button
            type="button"
            disabled={isBusy}
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

function Stat({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "ok" | "warn" }) {
  const toneClass = tone === "ok" ? "bg-green-50 text-green-700" : tone === "warn" ? "bg-yellow-50 text-yellow-700" : "bg-white text-gray-900";
  return (
    <div className={`rounded-lg p-4 shadow ${toneClass}`}>
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}