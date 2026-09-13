"use client";

import { useEffect, useState } from "react";
import {
  projectsApi,
  type ProjectDeactivationPreflight,
} from "@/lib/api";

interface ProjectDeactivationPreflightPanelProps {
  projectId: string;
}

const countLabels: Array<
  [
    keyof ProjectDeactivationPreflight["operational_counts"],
    string,
  ]
> = [
  ["farmer_count", "Farmers"],
  ["enrollment_count", "Enrollments"],
  ["parcel_count", "Parcels"],
  ["crop_cycle_count", "Crop cycles"],
  ["project_role_count", "Project roles"],
  ["active_boundary_assignment_count", "Boundary assignments"],
  ["field_event_count", "Field events"],
];

export function ProjectDeactivationPreflightPanel({
  projectId,
}: ProjectDeactivationPreflightPanelProps) {
  const [preflight, setPreflight] =
    useState<ProjectDeactivationPreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    projectsApi
      .getDeactivationPreflight(projectId)
      .then((result) => {
        if (active) setPreflight(result);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load deactivation preflight",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [projectId]);

  if (loading) {
    return (
      <section
        aria-label="Project deactivation preflight"
        className="mt-4 rounded-lg border bg-gray-50 p-4"
      >
        <p className="text-sm text-gray-500">
          Checking project deactivation blockers…
        </p>
      </section>
    );
  }

  if (error || !preflight) {
    return (
      <section
        aria-label="Project deactivation preflight"
        className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4"
      >
        <p className="text-sm text-red-700">
          {error || "Deactivation preflight is unavailable."}
        </p>
      </section>
    );
  }

  const { decision, operational_counts: counts } = preflight;

  return (
    <section
      aria-label="Project deactivation preflight"
      className={`mt-4 rounded-lg border p-4 ${
        decision.can_deactivate
          ? "border-green-200 bg-green-50"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">
            Project deactivation preflight
          </h4>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {decision.can_deactivate
              ? "No operational blockers detected"
              : `Deactivation blocked by ${decision.blocker_count} check${
                  decision.blocker_count === 1 ? "" : "s"
                }`}
          </p>
        </div>
        <span
          className={`rounded px-2 py-1 text-xs font-semibold ${
            decision.can_deactivate
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-900"
          }`}
        >
          {decision.can_deactivate ? "CLEAR" : "BLOCKED"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        {countLabels.map(([key, label]) => (
          <div key={key} className="rounded bg-white p-2">
            <span className="block font-semibold text-gray-900">
              {counts[key]}
            </span>
            {label}
          </div>
        ))}
      </div>

      {decision.blockers.length ? (
        <ul className="mt-3 space-y-2">
          {decision.blockers.map((blocker) => (
            <li
              key={blocker.code}
              className="rounded border border-amber-200 bg-white px-3 py-2"
            >
              <p className="text-xs font-semibold text-amber-900">
                {blocker.code.replaceAll("_", " ")}
              </p>
              <p className="mt-1 text-xs text-gray-700">
                {blocker.message}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-green-800">
          No farmers, enrollments, parcels, crop cycles, project
          roles, boundary assignments, or field events are attached.
        </p>
      )}

      <p className="mt-3 text-xs font-semibold text-amber-900">
        Advisory only: project deactivation is not enabled.
      </p>
      <p className="mt-1 text-[11px] text-gray-600">
        This read-only check does not change project status, boundary
        assignments, candidate activation or promotion, runtime
        tables, lookup behavior, or Android behavior.
      </p>
    </section>
  );
}
