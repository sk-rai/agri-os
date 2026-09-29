"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  geographyApi,
  projectsApi,
  type GeographyVillageDetails,
  type Project,
} from "@/lib/api";

type RegionOption = {
  region_id: string;
  region_code: string;
  region_name: string;
  region_system: string;
  confidence: string;
  review_status: string;
};

type ActiveOverride = RegionOption & {
  override_id: string;
  tenant_id: string;
  project_id: string;
  village_id: string;
  village_lgd_code: string;
  village_name: string;
  assignment_status: string;
  evidence_basis: string;
  rollback_token: string;
  is_active: boolean;
};

type OverrideContext = {
  schema_version: string;
  mode: string;
  project: {
    project_id: string;
    tenant_id: string;
    name: string;
    status: string;
  };
  village: {
    village_id: string;
    village_lgd_code: string;
    village_name: string;
  };
  allowed_region_systems: string[];
  region_option_count: number;
  region_options: RegionOption[];
  active_overrides: ActiveOverride[];
  guardrails: Record<string, boolean>;
};

type EffectiveRegion = RegionOption & {
  override_id?: string | null;
  resolution_source:
    | "PROJECT_OVERRIDE"
    | "GLOBAL_MAPPING_FALLBACK";
  resolution_scope: string;
  global_fallback_available: boolean;
  global_fallback_region_code?: string | null;
  global_fallback_region_name?: string | null;
  global_fallback_scope?: string | null;
};

type EffectiveResolution = {
  schema_version: string;
  mode: string;
  precedence: string[];
  effective_region_count: number;
  project_override_count: number;
  global_fallback_count: number;
  unresolved_region_systems: string[];
  effective_regions: EffectiveRegion[];
  guardrails: Record<string, boolean>;
};

type MutationResponse = {
  schema_version: string;
  mode: string;
  status?: string;
  action?: string;
  preview?: {
    action: string;
    assignment_scope: string;
    region_id: string;
    region_code: string;
    region_name: string;
    region_system: string;
    would_supersede_existing: boolean;
  };
  assignment?: ActiveOverride;
  guardrails: Record<string, boolean>;
};

type PendingDryRun = {
  regionId: string;
  rollbackToken: string;
  response: MutationResponse;
};

const SYSTEM_LABELS: Record<string, string> = {
  CORE_STACK_AGRO_CLIMATIC_ZONE: "Agro-climatic zone",
  CORE_STACK_AGRO_ECOLOGICAL_ZONE: "Agro-ecological zone",
  CORE_STACK_BIOGEOGRAPHIC_ZONE: "Biogeographic zone",
};

function createRollbackToken(
  projectId: string,
  villageId: string,
  regionSystem: string,
) {
  return [
    "core",
    projectId.slice(0, 8),
    villageId.slice(0, 8),
    regionSystem.replace("CORE_STACK_", "").slice(0, 8),
    Date.now().toString(36),
  ].join("-");
}

export default function CoreLayerProjectOverridePanel() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [villageId, setVillageId] = useState("");
  const [villageQuery, setVillageQuery] = useState("");
  const [projectVillages, setProjectVillages] = useState<
    GeographyVillageDetails[]
  >([]);
  const [loadingVillages, setLoadingVillages] = useState(false);
  const [context, setContext] = useState<OverrideContext | null>(null);
  const [effectiveResolution, setEffectiveResolution] =
    useState<EffectiveResolution | null>(null);
  const [selectedRegions, setSelectedRegions] = useState<
    Record<string, string>
  >({});
  const [pending, setPending] = useState<
    Record<string, PendingDryRun>
  >({});
  const [reason, setReason] = useState(
    "Project-specific Core geography review",
  );
  const [evidenceBasis, setEvidenceBasis] = useState(
    "ADMIN_PROJECT_REVIEW",
  );
  const [loading, setLoading] = useState(false);
  const [busySystem, setBusySystem] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void projectsApi
      .list()
      .then((rows) => {
        setProjects(rows);
        if (rows.length > 0) setProjectId(rows[0].id);
      })
      .catch((err) => {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load projects",
        );
      });
  }, []);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId) || null,
    [projectId, projects],
  );

  const selectedVillage = useMemo(
    () =>
      projectVillages.find((village) => village.id === villageId) ||
      null,
    [projectVillages, villageId],
  );

  const filteredProjectVillages = useMemo(() => {
    const normalized = villageQuery.trim().toLocaleLowerCase();
    if (normalized.length < 2) return [];

    return projectVillages
      .filter((village) =>
        [
          village.canonical_name,
          village.lgd_code,
          village.block_name,
          village.district_name,
          village.state_name,
        ].some((value) =>
          String(value || "")
            .toLocaleLowerCase()
            .includes(normalized),
        ),
      )
      .slice(0, 30);
  }, [projectVillages, villageQuery]);

  useEffect(() => {
    const rawCodes =
      selectedProject?.geography_scope?.village_lgd_codes;
    const codes = Array.isArray(rawCodes)
      ? rawCodes.map(String).filter(Boolean)
      : [];

    setVillageId("");
    setVillageQuery("");
    setProjectVillages([]);
    setContext(null);
    setPending({});

    if (!codes.length) {
      setLoadingVillages(false);
      return;
    }

    let active = true;
    setLoadingVillages(true);
    setError(null);

    void geographyApi
      .resolveVillagesByLgdCodes(codes)
      .then((rows) => {
        if (!active) return;
        setProjectVillages(
          [...rows].sort((left, right) =>
            [
              left.state_name,
              left.district_name,
              left.block_name,
              left.canonical_name,
              left.lgd_code,
            ]
              .join("|")
              .localeCompare(
                [
                  right.state_name,
                  right.district_name,
                  right.block_name,
                  right.canonical_name,
                  right.lgd_code,
                ].join("|"),
              ),
          ),
        );
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load project villages",
        );
      })
      .finally(() => {
        if (active) setLoadingVillages(false);
      });

    return () => {
      active = false;
    };
  }, [selectedProject]);

  const loadContext = useCallback(async () => {
    if (!projectId || !villageId.trim()) return;

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const baseUrl =
        `/api/v1/master-data/geography/core-layer-project-overrides/projects/${projectId}/villages/${villageId.trim()}`;

      const [response, effective] = await Promise.all([
        api<OverrideContext>(baseUrl),
        api<EffectiveResolution>(`${baseUrl}/effective`),
      ]);

      setContext(response);
      setEffectiveResolution(effective);
      setPending({});

      const nextSelections: Record<string, string> = {};
      response.allowed_region_systems.forEach((system) => {
        const active = response.active_overrides.find(
          (item) => item.region_system === system,
        );
        const first = response.region_options.find(
          (item) => item.region_system === system,
        );
        nextSelections[system] =
          active?.region_id || first?.region_id || "";
      });
      setSelectedRegions(nextSelections);
    } catch (err) {
      setContext(null);
      setEffectiveResolution(null);
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load project Core-layer options",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId, villageId]);

  const optionsBySystem = useMemo(() => {
    const grouped: Record<string, RegionOption[]> = {};
    context?.region_options.forEach((option) => {
      (grouped[option.region_system] ||= []).push(option);
    });
    return grouped;
  }, [context]);

  const dryRun = useCallback(
    async (regionSystem: string) => {
      const regionId = selectedRegions[regionSystem];
      if (!context || !regionId) return;
      if (reason.trim().length < 3) {
        setError("A review reason of at least 3 characters is required.");
        return;
      }

      const rollbackToken = createRollbackToken(
        projectId,
        villageId.trim(),
        regionSystem,
      );

      setBusySystem(regionSystem);
      setError(null);
      setMessage(null);

      try {
        const response = await api<MutationResponse>(
          `/api/v1/master-data/geography/core-layer-project-overrides/projects/${projectId}/villages/${villageId.trim()}`,
          {
            method: "PUT",
            body: {
              region_id: regionId,
              rollback_token: rollbackToken,
              reason: reason.trim(),
              evidence_basis: evidenceBasis,
              dry_run: true,
              confirm_apply: false,
              supersede_existing: false,
            },
          },
        );

        setPending((current) => ({
          ...current,
          [regionSystem]: {
            regionId,
            rollbackToken,
            response,
          },
        }));
        setMessage(
          `${SYSTEM_LABELS[regionSystem]} dry run: ${
            response.preview?.action || response.status
          }`,
        );
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Dry run failed",
        );
      } finally {
        setBusySystem("");
      }
    },
    [
      context,
      evidenceBasis,
      projectId,
      reason,
      selectedRegions,
      villageId,
    ],
  );

  const applyOverride = useCallback(
    async (regionSystem: string) => {
      const dryRunResult = pending[regionSystem];
      if (!context || !dryRunResult) return;

      const active = context.active_overrides.find(
        (item) => item.region_system === regionSystem,
      );
      const supersede = Boolean(
        active && active.region_id !== dryRunResult.regionId,
      );

      if (
        !window.confirm(
          supersede
            ? "Supersede the current project-only Core-layer override? History will be retained and global mappings remain unchanged."
            : "Apply this Core-layer selection only to this project village? Global mappings and runtime behavior remain unchanged.",
        )
      ) {
        return;
      }

      setBusySystem(regionSystem);
      setError(null);

      try {
        const response = await api<MutationResponse>(
          `/api/v1/master-data/geography/core-layer-project-overrides/projects/${projectId}/villages/${villageId.trim()}`,
          {
            method: "PUT",
            body: {
              region_id: dryRunResult.regionId,
              rollback_token: dryRunResult.rollbackToken,
              reason: reason.trim(),
              evidence_basis: evidenceBasis,
              dry_run: false,
              confirm_apply: true,
              supersede_existing: supersede,
            },
          },
        );

        setMessage(
          `${SYSTEM_LABELS[regionSystem]}: ${
            response.action || "APPLIED"
          }`,
        );
        await loadContext();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Override apply failed",
        );
      } finally {
        setBusySystem("");
      }
    },
    [
      context,
      evidenceBasis,
      loadContext,
      pending,
      projectId,
      reason,
      villageId,
    ],
  );

  const rollbackOverride = useCallback(
    async (assignment: ActiveOverride) => {
      if (
        !window.confirm(
          "Roll back this project-only Core-layer override? Immutable assignment history will be retained.",
        )
      ) {
        return;
      }

      setBusySystem(assignment.region_system);
      setError(null);

      try {
        const params = new URLSearchParams({
          region_system: assignment.region_system,
          rollback_token: assignment.rollback_token,
        });
        const response = await api<MutationResponse>(
          `/api/v1/master-data/geography/core-layer-project-overrides/projects/${projectId}/villages/${assignment.village_id}?${params.toString()}`,
          { method: "DELETE" },
        );
        setMessage(
          `${SYSTEM_LABELS[assignment.region_system]}: ${
            response.action || "ROLLED_BACK"
          }`,
        );
        await loadContext();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Override rollback failed",
        );
      } finally {
        setBusySystem("");
      }
    },
    [loadContext, projectId],
  );

  return (
    <div className="mt-5 rounded-xl border border-blue-200 bg-blue-50/40 p-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-950">
          Project-specific Core-layer overrides
        </h3>
        <p className="mt-1 text-xs text-slate-600">
          Assign an agro-climatic, agro-ecological, or biogeographic
          region to one canonical village for this project only.
          Every apply requires a dry run. Canonical LGD, global Core
          mappings, runtime activation, and Android behavior remain
          unchanged.
        </p>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">
            Project
          </span>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            value={projectId}
            onChange={(event) => {
              setProjectId(event.target.value);
            }}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name} / {project.status}
              </option>
            ))}
          </select>
        </label>

        <div className="relative space-y-1">
          <label
            htmlFor="core-project-village-search"
            className="block text-xs font-medium text-slate-600"
          >
            Search project village
          </label>
          <input
            id="core-project-village-search"
            type="search"
            role="combobox"
            aria-expanded={filteredProjectVillages.length > 0}
            aria-controls="core-project-village-results"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            value={villageQuery}
            disabled={!projectId || loadingVillages}
            onChange={(event) => {
              setVillageQuery(event.target.value);
              setVillageId("");
              setContext(null);
              setPending({});
            }}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                filteredProjectVillages.length > 0
              ) {
                event.preventDefault();
                const village = filteredProjectVillages[0];
                setVillageId(village.id);
                setVillageQuery(village.canonical_name);
                setContext(null);
                setPending({});
              } else if (event.key === "Escape") {
                setVillageQuery("");
                setVillageId("");
                setContext(null);
                setPending({});
              }
            }}
            placeholder={
              loadingVillages
                ? "Loading project villages…"
                : projectVillages.length
                  ? "Village name, LGD code, block, or district"
                  : "Selected project has no canonical village scope"
            }
          />

          {villageQuery.trim().length >= 2 &&
          !selectedVillage &&
          !loadingVillages ? (
            <div
              id="core-project-village-results"
              role="listbox"
              aria-label="Project village search results"
              className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg"
            >
              {filteredProjectVillages.length ? (
                filteredProjectVillages.map((village) => (
                  <button
                    key={village.id}
                    type="button"
                    role="option"
                    aria-selected={false}
                    className="block w-full border-b border-slate-100 px-3 py-2 text-left last:border-b-0 hover:bg-blue-50"
                    onClick={() => {
                      setVillageId(village.id);
                      setVillageQuery(village.canonical_name);
                      setContext(null);
                      setPending({});
                    }}
                  >
                    <span className="block text-sm font-medium text-slate-950">
                      {village.canonical_name}
                    </span>
                    <span className="block text-xs text-slate-500">
                      LGD {village.lgd_code} · {village.block_name} ·{" "}
                      {village.district_name} · {village.state_name}
                    </span>
                  </button>
                ))
              ) : (
                <p className="px-3 py-3 text-xs text-slate-500">
                  No villages in this project match the search.
                </p>
              )}
            </div>
          ) : null}

          {selectedVillage ? (
            <div className="rounded-lg border border-blue-200 bg-white px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-950">
                    {selectedVillage.canonical_name}
                  </p>
                  <p className="text-xs text-slate-500">
                    LGD {selectedVillage.lgd_code} ·{" "}
                    {selectedVillage.block_name} ·{" "}
                    {selectedVillage.district_name} ·{" "}
                    {selectedVillage.state_name}
                  </p>
                </div>
                <button
                  type="button"
                  className="text-xs font-semibold text-blue-700 hover:underline"
                  onClick={() => {
                    setVillageId("");
                    setVillageQuery("");
                    setContext(null);
                    setPending({});
                  }}
                >
                  Change
                </button>
              </div>
            </div>
          ) : null}

          <p className="text-xs text-slate-500">
            {loadingVillages
              ? "Resolving canonical project villages…"
              : `${projectVillages.length} canonical project villages available`}
          </p>
        </div>

        <button
          type="button"
          disabled={!projectId || !villageId.trim() || loading}
          onClick={() => void loadContext()}
          className="self-end rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load Core-layer options"}
        </button>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">
            Review reason
          </span>
          <input
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>

        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">
            Evidence basis
          </span>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            value={evidenceBasis}
            onChange={(event) =>
              setEvidenceBasis(event.target.value)
            }
          >
            <option value="ADMIN_PROJECT_REVIEW">
              Admin project review
            </option>
            <option value="AUTHORITATIVE_AGRO_CLIMATE_SOURCE">
              Authoritative agro-climate source
            </option>
            <option value="POLYGON_OVERLAP_MANUAL_REVIEW">
              Reviewed polygon overlap
            </option>
            <option value="OTHER_DOCUMENTED_EVIDENCE">
              Other documented evidence
            </option>
          </select>
        </label>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {message && (
        <p className="mt-3 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-blue-800">
          {message}
        </p>
      )}

      {context && (
        <>
          <div className="mt-4 rounded-lg border border-blue-100 bg-white px-3 py-2 text-sm text-slate-700">
            <span className="font-semibold text-slate-950">
              {context.village.village_name}
            </span>{" "}
            · LGD {context.village.village_lgd_code} · Project{" "}
            {context.project.name}
          </div>

          <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-950">
                  Effective Core layers
                </h4>
                <p className="mt-1 text-xs text-slate-500">
                  Read-only project context. Project overrides win per
                  layer; unresolved layers remain explicit.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-blue-50 px-2 py-1 text-blue-700">
                  {effectiveResolution?.project_override_count ?? 0} project overrides
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-700">
                  {effectiveResolution?.global_fallback_count ?? 0} global fallbacks
                </span>
              </div>
            </div>

            <div className="mt-3 overflow-x-auto rounded-lg border border-slate-100">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Core layer</th>
                    <th className="px-3 py-2">Effective region</th>
                    <th className="px-3 py-2">Source</th>
                    <th className="px-3 py-2">Fallback after rollback</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {context.allowed_region_systems.map((system) => {
                    const effective =
                      effectiveResolution?.effective_regions.find(
                        (item) => item.region_system === system,
                      );
                    const unresolved =
                      effectiveResolution?.unresolved_region_systems.includes(
                        system,
                      );

                    return (
                      <tr key={`effective-${system}`}>
                        <td className="px-3 py-2 font-medium text-slate-900">
                          {SYSTEM_LABELS[system] || system}
                        </td>
                        <td className="px-3 py-2 text-slate-700">
                          {effective ? (
                            <>
                              <span className="font-medium">
                                {effective.region_name}
                              </span>
                              <span className="block text-xs text-slate-500">
                                {effective.region_code}
                              </span>
                            </>
                          ) : unresolved ? (
                            <span className="font-medium text-amber-700">
                              Unresolved
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {effective ? (
                            <>
                              <span
                                className={
                                  effective.resolution_source ===
                                  "PROJECT_OVERRIDE"
                                    ? "rounded-full bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700"
                                    : "rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700"
                                }
                              >
                                {effective.resolution_source ===
                                "PROJECT_OVERRIDE"
                                  ? "Project override"
                                  : "Global fallback"}
                              </span>
                              <span className="mt-1 block text-xs text-slate-500">
                                Scope: {effective.resolution_scope}
                              </span>
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3 py-2 text-slate-700">
                          {effective?.resolution_source ===
                          "PROJECT_OVERRIDE" ? (
                            effective.global_fallback_available ? (
                              <>
                                <span className="font-medium">
                                  {effective.global_fallback_region_name}
                                </span>
                                <span className="block text-xs text-slate-500">
                                  {effective.global_fallback_region_code} ·{" "}
                                  {effective.global_fallback_scope}
                                </span>
                              </>
                            ) : (
                              <span className="text-amber-700">
                                No global fallback
                              </span>
                            )
                          ) : effective ? (
                            <span className="text-xs text-slate-500">
                              Already using global fallback
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {effectiveResolution?.unresolved_region_systems.length ? (
              <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Unresolved layers:{" "}
                {effectiveResolution.unresolved_region_systems
                  .map((system) => SYSTEM_LABELS[system] || system)
                  .join(", ")}
              </p>
            ) : (
              <p className="mt-3 text-xs text-slate-500">
                All Core layers resolve for this project village.
              </p>
            )}
          </div>

          <div className="mt-4 grid gap-3 xl:grid-cols-3">
            {context.allowed_region_systems.map((system) => {
              const active = context.active_overrides.find(
                (item) => item.region_system === system,
              );
              const dryRunResult = pending[system];
              const options = optionsBySystem[system] || [];
              const busy = busySystem === system;

              return (
                <div
                  key={system}
                  className="rounded-lg border border-slate-200 bg-white p-3"
                >
                  <h4 className="text-sm font-semibold text-slate-950">
                    {SYSTEM_LABELS[system] || system}
                  </h4>

                  <div className="mt-2 min-h-12 text-xs text-slate-600">
                    {active ? (
                      <>
                        <span className="font-semibold text-blue-700">
                          Project override active:
                        </span>{" "}
                        {active.region_name}
                      </>
                    ) : (
                      "No project override. Global/default resolution remains in effect."
                    )}
                  </div>

                  <select
                    className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    value={selectedRegions[system] || ""}
                    onChange={(event) => {
                      setSelectedRegions((current) => ({
                        ...current,
                        [system]: event.target.value,
                      }));
                      setPending((current) => {
                        const next = { ...current };
                        delete next[system];
                        return next;
                      });
                    }}
                  >
                    {options.map((option) => (
                      <option
                        key={option.region_id}
                        value={option.region_id}
                      >
                        {option.region_name} / {option.region_code}
                      </option>
                    ))}
                  </select>

                  {dryRunResult?.response.preview && (
                    <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800">
                      Dry run:{" "}
                      {dryRunResult.response.preview.action}
                      {dryRunResult.response.preview
                        .would_supersede_existing
                        ? " · supersedes active project override"
                        : ""}
                    </p>
                  )}

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={
                        busy ||
                        !selectedRegions[system] ||
                        options.length === 0
                      }
                      onClick={() => void dryRun(system)}
                      className="rounded border border-blue-300 px-2 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                    >
                      {busy ? "Working…" : "Dry run"}
                    </button>

                    <button
                      type="button"
                      disabled={busy || !dryRunResult}
                      onClick={() => void applyOverride(system)}
                      className="rounded bg-blue-700 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                    >
                      Use for this project
                    </button>

                    {active && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void rollbackOverride(active)
                        }
                        className="rounded border border-red-200 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                      >
                        Roll back
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <p className="mt-3 text-xs text-slate-500">
            Project overrides take precedence only inside the selected
            project context. They do not promote inactive global
            mappings or alter canonical geography.
          </p>
        </>
      )}
    </div>
  );
}
