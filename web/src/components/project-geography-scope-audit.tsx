"use client";

import { useEffect, useMemo, useState } from "react";
import {
  projectsApi,
  type ProjectGeographyBoundaryStatus,
  type ProjectGeographyScopeAuditResponse,
  type ProjectGeographyScopeChangeType,
} from "@/lib/api";

interface Props {
  projectId: string;
}

type ChangeFilter = "ALL" | ProjectGeographyScopeChangeType;
type BoundaryFilter = "ALL" | ProjectGeographyBoundaryStatus;

const changeTone: Record<ProjectGeographyScopeChangeType, string> = {
  ADDED: "bg-green-100 text-green-800",
  REMOVED: "bg-red-100 text-red-800",
  UNCHANGED: "bg-gray-100 text-gray-700",
};

const boundaryTone: Record<ProjectGeographyBoundaryStatus, string> = {
  ELIGIBLE: "bg-blue-100 text-blue-800",
  MISSING: "bg-amber-100 text-amber-800",
  BLOCKED: "bg-red-100 text-red-800",
};

export function ProjectGeographyScopeAudit({ projectId }: Props) {
  const [data, setData] =
    useState<ProjectGeographyScopeAuditResponse | null>(null);
  const [changeFilter, setChangeFilter] =
    useState<ChangeFilter>("ALL");
  const [boundaryFilter, setBoundaryFilter] =
    useState<BoundaryFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    projectsApi
      .geographyScopeAudit(projectId)
      .then((response) => {
        if (active) setData(response);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load geography scope history",
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

  const visibleEvents = useMemo(
    () =>
      (data?.events || [])
        .map((event) => ({
          ...event,
          changes: event.changes.filter(
            (change) =>
              (changeFilter === "ALL" ||
                change.change_type === changeFilter) &&
              (boundaryFilter === "ALL" ||
                change.boundary_status === boundaryFilter),
          ),
        }))
        .filter(
          (event) =>
            changeFilter === "ALL" && boundaryFilter === "ALL"
              ? true
              : event.changes.length > 0,
        ),
    [boundaryFilter, changeFilter, data],
  );

  return (
    <section
      aria-label="Project geography scope history"
      className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-slate-900">
            Geography scope history
          </h4>
          <p className="mt-1 text-xs text-slate-600">
            Read-only audit trail of canonical project village changes.
          </p>
        </div>
        {data ? (
          <span className="text-xs text-slate-500">
            {data.count} {data.count === 1 ? "event" : "events"}
          </span>
        ) : null}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium text-slate-700">
          Village change
          <select
            aria-label="Village change filter"
            value={changeFilter}
            onChange={(event) =>
              setChangeFilter(event.target.value as ChangeFilter)
            }
            className="mt-1 w-full rounded border bg-white px-3 py-2"
          >
            <option value="ALL">All changes</option>
            <option value="ADDED">Added</option>
            <option value="REMOVED">Removed</option>
            <option value="UNCHANGED">Unchanged</option>
          </select>
        </label>

        <label className="text-xs font-medium text-slate-700">
          Boundary readiness
          <select
            aria-label="Boundary readiness filter"
            value={boundaryFilter}
            onChange={(event) =>
              setBoundaryFilter(
                event.target.value as BoundaryFilter,
              )
            }
            className="mt-1 w-full rounded border bg-white px-3 py-2"
          >
            <option value="ALL">All statuses</option>
            <option value="ELIGIBLE">Eligible</option>
            <option value="MISSING">Missing</option>
            <option value="BLOCKED">Blocked</option>
          </select>
        </label>
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-slate-500">
          Loading geography scope history…
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 text-sm text-red-700">{error}</p>
      ) : null}

      {!loading && !error && data?.events.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No geography scope changes have been recorded.
        </p>
      ) : null}

      {!loading &&
      !error &&
      data?.events.length &&
      visibleEvents.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No audit changes match these filters.
        </p>
      ) : null}

      <div className="mt-4 space-y-3">
        {visibleEvents.map((event) => (
          <article
            key={event.id}
            className="rounded border bg-white p-3"
          >
            <div className="flex flex-wrap justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  {event.actor.display_name}
                </p>
                <p className="text-xs text-slate-500">
                  {event.actor.role || "Role unavailable"}
                  {" · "}
                  {event.created_at
                    ? new Date(event.created_at).toLocaleString()
                    : "Time unavailable"}
                </p>
              </div>
              <p className="text-xs text-slate-600">
                {event.before_village_count}
                {" → "}
                {event.after_village_count} villages
              </p>
            </div>

            <p className="mt-2 text-sm text-slate-700">
              {event.reason || "No reason recorded"}
            </p>

            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className="rounded bg-green-100 px-2 py-1 text-green-800">
                {event.summary.added_count} added
              </span>
              <span className="rounded bg-red-100 px-2 py-1 text-red-800">
                {event.summary.removed_count} removed
              </span>
              <span className="rounded bg-gray-100 px-2 py-1 text-gray-700">
                {event.summary.unchanged_count} unchanged
              </span>
            </div>

            {event.changes.length ? (
              <ul className="mt-3 divide-y rounded border">
                {event.changes.map((change) => (
                  <li
                    key={`${event.id}-${change.change_type}-${change.lgd_code}`}
                    className="flex flex-wrap items-start justify-between gap-2 px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        {change.village_name ||
                          `Unresolved LGD ${change.lgd_code}`}
                      </p>
                      <p className="text-xs text-slate-500">
                        LGD {change.lgd_code}
                        {change.resolved
                          ? ` · ${change.state_name} / ${change.district_name} / ${change.block_name}`
                          : " · Canonical village unavailable"}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <span
                        className={`rounded px-2 py-1 text-[10px] font-semibold ${
                          changeTone[change.change_type]
                        }`}
                      >
                        {change.change_type}
                      </span>
                      <span
                        className={`rounded px-2 py-1 text-[10px] font-semibold ${
                          boundaryTone[change.boundary_status]
                        }`}
                      >
                        {change.boundary_status}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-xs text-slate-500">
                This event has no changes matching the active filters.
              </p>
            )}
          </article>
        ))}
      </div>

      <p className="mt-3 text-[11px] text-slate-500">
        Viewing history does not activate or promote boundary candidates,
        enable runtime lookup, or change Android behavior.
      </p>
    </section>
  );
}
