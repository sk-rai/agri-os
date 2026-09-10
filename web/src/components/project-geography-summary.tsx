"use client";

import Link from "next/link";
import type {
  Project,
  ProjectGeographyReadinessItem,
} from "@/lib/api";

interface ProjectGeographySummaryProps {
  project: Project;
  summary?: ProjectGeographyReadinessItem;
  loading?: boolean;
}

export function ProjectGeographySummary({
  project,
  summary,
  loading = false,
}: ProjectGeographySummaryProps) {
  const codes = project.geography_scope?.village_lgd_codes;
  const scopedCodeCount = Array.isArray(codes) ? codes.length : 0;

  if (!scopedCodeCount) {
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
          ) : !summary ? (
            <p role="alert" className="mt-1 text-xs text-amber-700">
              Project geography summary unavailable.
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm font-medium text-gray-900">
                {summary.villages_with_eligible_boundary} of{" "}
                {summary.resolved_village_count} villages have an eligible
                boundary
              </p>

              <p className="mt-1 text-xs text-gray-600">
                {summary.state_names.length} state
                {summary.state_names.length === 1 ? "" : "s"} ·{" "}
                {summary.district_names.length} district
                {summary.district_names.length === 1 ? "" : "s"} ·{" "}
                {summary.villages_without_eligible_boundary} missing
              </p>

              {summary.district_names.length ? (
                <p className="mt-1 text-xs text-gray-500">
                  {summary.district_names.join(" · ")}
                </p>
              ) : null}

              {summary.unresolved_village_code_count ? (
                <p className="mt-1 text-xs text-amber-700">
                  {summary.unresolved_village_code_count} saved LGD code
                  {summary.unresolved_village_code_count === 1 ? "" : "s"}{" "}
                  could not be resolved.
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
