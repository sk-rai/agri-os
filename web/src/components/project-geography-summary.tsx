"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  geographyApi,
  type GeographyVillageDetails,
  type Project,
} from "@/lib/api";

type BoundaryPreview = {
  summary: {
    project_village_count: number;
    villages_with_eligible_boundary: number;
    villages_without_eligible_boundary: number;
    eligible_candidate_count: number;
    coverage_ratio: number;
  };
};

interface ProjectGeographySummaryProps {
  project: Project;
}

export function ProjectGeographySummary({
  project,
}: ProjectGeographySummaryProps) {
  const villageCodes = useMemo(() => {
    const codes = project.geography_scope?.village_lgd_codes;
    return Array.isArray(codes) ? codes.map(String) : [];
  }, [project.geography_scope]);

  const [villages, setVillages] = useState<GeographyVillageDetails[]>([]);
  const [preview, setPreview] = useState<BoundaryPreview | null>(null);
  const [loading, setLoading] = useState(villageCodes.length > 0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!villageCodes.length) {
      setVillages([]);
      setPreview(null);
      setLoading(false);
      setError("");
      return;
    }

    let active = true;
    const params = new URLSearchParams({
      project_id: project.id,
      limit: "1",
    });

    setLoading(true);
    setError("");

    Promise.all([
      geographyApi.resolveVillagesByLgdCodes(villageCodes),
      api<BoundaryPreview>(
        `/api/v1/master-data/geography/` +
          `nwdp-boundary-project-matching/project-preview?${params.toString()}`,
      ),
    ])
      .then(([resolvedVillages, boundaryPreview]) => {
        if (!active) return;
        setVillages(resolvedVillages);
        setPreview(boundaryPreview);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof Error
            ? err.message
            : "Project geography summary unavailable",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [project.id, villageCodes]);

  const states = Array.from(
    new Set(villages.map((row) => row.state_name)),
  );
  const districts = Array.from(
    new Set(
      villages.map((row) => `${row.district_name}, ${row.state_name}`),
    ),
  );
  const unresolvedCount = Math.max(villageCodes.length - villages.length, 0);

  if (!villageCodes.length) {
    return (
      <div className="mt-3 rounded border border-dashed px-3 py-2 text-xs text-gray-500">
        No canonical village scope configured.
      </div>
    );
  }

  return (
    <div
      aria-label="Project geography summary"
      className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Geography and boundary readiness
          </p>
          {loading ? (
            <p className="mt-1 text-sm text-gray-500">Loading summary…</p>
          ) : error ? (
            <p role="alert" className="mt-1 text-xs text-red-600">
              {error}
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm font-medium text-gray-900">
                {preview?.summary.villages_with_eligible_boundary ?? 0} of{" "}
                {preview?.summary.project_village_count ?? villageCodes.length}{" "}
                villages have an eligible boundary
              </p>
              <p className="mt-1 text-xs text-gray-600">
                {states.length} state{states.length === 1 ? "" : "s"} ·{" "}
                {districts.length} district
                {districts.length === 1 ? "" : "s"} ·{" "}
                {preview?.summary.villages_without_eligible_boundary ?? 0} missing
              </p>
              {districts.length ? (
                <p className="mt-1 text-xs text-gray-500">
                  {districts.join(" · ")}
                </p>
              ) : null}
              {unresolvedCount ? (
                <p className="mt-1 text-xs text-amber-700">
                  {unresolvedCount} saved LGD code
                  {unresolvedCount === 1 ? "" : "s"} could not be resolved.
                </p>
              ) : null}
            </>
          )}
        </div>

        <Link
          href={`/nwdp-boundary-review?project_id=${encodeURIComponent(project.id)}#project-coverage-preview`}
          className="text-xs font-semibold text-blue-700 hover:underline"
        >
          Review boundaries
        </Link>
      </div>
    </div>
  );
}
