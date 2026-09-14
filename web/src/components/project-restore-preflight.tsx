"use client";

import { useEffect, useState } from "react";
import {
  projectsApi,
  type ProjectRestorePreflight,
} from "@/lib/api";

interface ProjectRestorePreflightPanelProps {
  projectId: string;
  onRestored?: () => void;
}

const countLabels: Array<
  [
    keyof ProjectRestorePreflight["retained_counts"],
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

export function ProjectRestorePreflightPanel({
  projectId,
  onRestored,
}: ProjectRestorePreflightPanelProps) {
  const [preflight, setPreflight] =
    useState<ProjectRestorePreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [restoreReason, setRestoreReason] =
    useState("");
  const [confirmRestore, setConfirmRestore] =
    useState(false);
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    projectsApi
      .getRestorePreflight(projectId)
      .then((result) => {
        if (active) setPreflight(result);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load restore preflight",
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

  const restoreProject = async () => {
    if (
      !preflight ||
      !preflight.decision.can_restore ||
      !preflight.decision.restore_supported ||
      restoreReason.trim().length < 3
    ) {
      return;
    }

    setRestoring(true);
    setError("");

    try {
      const result = await projectsApi.restore(
        projectId,
        restoreReason.trim(),
        preflight.decision.preflight_fingerprint,
      );

      if (
        result.project.status !== "COMPLETED" ||
        (!result.restore.restored &&
          !result.restore.idempotent)
      ) {
        throw new Error(
          "Project restore returned an unexpected result.",
        );
      }

      setConfirmRestore(false);
      onRestored?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message} Run a fresh preflight if the server reports a stale decision.`
          : "Failed to restore project",
      );
      setConfirmRestore(false);
    } finally {
      setRestoring(false);
    }
  };

  if (loading) {
    return (
      <section
        aria-label="Project restore preflight"
        className="mt-4 rounded-lg border bg-gray-50 p-4"
      >
        <p className="text-sm text-gray-500">
          Checking project restore blockers…
        </p>
      </section>
    );
  }

  if (error || !preflight) {
    return (
      <section
        aria-label="Project restore preflight"
        className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4"
      >
        <p className="text-sm text-red-700">
          {error || "Restore preflight is unavailable."}
        </p>
      </section>
    );
  }

  const { decision, retained_counts: counts } = preflight;

  return (
    <section
      aria-label="Project restore preflight"
      className={`mt-4 rounded-lg border p-4 ${
        decision.can_restore
          ? "border-green-200 bg-green-50"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">
            Project restore preflight
          </h4>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {decision.can_restore
              ? "No operational blockers detected"
              : `Restore blocked by ${decision.blocker_count} check${
                  decision.blocker_count === 1 ? "" : "s"
                }`}
          </p>
        </div>
        <span
          className={`rounded px-2 py-1 text-xs font-semibold ${
            decision.can_restore
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-900"
          }`}
        >
          {decision.can_restore ? "CLEAR" : "BLOCKED"}
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

      {preflight.prior_archive_event.id ? (
        <div className="mt-3 rounded border bg-white p-3 text-xs text-gray-700">
          <p className="font-semibold text-gray-900">
            Immutable archive evidence
          </p>
          <p className="mt-1">
            {preflight.prior_archive_event.reason ||
              "Archive reason retained"}
          </p>
          {preflight.prior_archive_event.created_at ? (
            <p className="mt-1 text-gray-500">
              {new Date(
                preflight.prior_archive_event.created_at,
              ).toLocaleString()}
            </p>
          ) : null}
        </div>
      ) : null}

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
          No unfinished enrollment, crop cycle, crop stage, or
          query-thread work prevents archival.
        </p>
      )}

      {decision.can_restore &&
      decision.restore_supported ? (
        <div className="mt-4 rounded border border-amber-300 bg-white p-3">
          <label className="block text-xs font-medium text-gray-700">
            Project restore reason
            <input
              type="text"
              aria-label="Project restore reason"
              value={restoreReason}
              disabled={restoring}
              onChange={(event) =>
                setRestoreReason(event.target.value)
              }
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
              placeholder="Why should this archived project be restored?"
            />
          </label>

          {!confirmRestore ? (
            <button
              type="button"
              disabled={
                restoring ||
                restoreReason.trim().length < 3
              }
              onClick={() => setConfirmRestore(true)}
              className="mt-3 rounded bg-amber-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              Review project restore
            </button>
          ) : (
            <div className="mt-3 rounded border border-red-200 bg-red-50 p-3">
              <p className="text-sm font-semibold text-red-900">
                Confirm ARCHIVED → COMPLETED
              </p>
              <p className="mt-1 text-xs text-red-800">
                This returns the archived project to completed-record visibility.
                Historical farmers, parcels, field evidence, assignments,
                boundaries, and audit records remain unchanged and
                available for traceability.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={restoring}
                  onClick={() => void restoreProject()}
                  className="rounded bg-red-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {restoring
                    ? "Restoring project…"
                    : "Confirm project restore"}
                </button>
                <button
                  type="button"
                  disabled={restoring}
                  onClick={() => setConfirmRestore(false)}
                  className="rounded border px-3 py-2 text-xs font-semibold text-gray-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-xs font-semibold text-amber-900">
          Resolve every archive-evidence blocker before restore.
        </p>
      )}

      <p className="mt-3 text-[11px] text-gray-600">
        Opening this preflight does not change project status or
        operational records, boundary assignments, candidate activation
        or promotion, runtime tables, lookup behavior, or Android
        behavior. Restore requires a reason, a current preflight
        fingerprint, and explicit confirmation.
      </p>
    </section>
  );
}
