"use client";

import { useEffect, useState } from "react";
import {
  projectsApi,
  type ProjectArchivePreflight,
} from "@/lib/api";

interface ProjectArchivePreflightPanelProps {
  projectId: string;
  onArchived?: () => void;
}

const countLabels: Array<
  [
    keyof ProjectArchivePreflight["unfinished_counts"],
    string,
  ]
> = [
  ["unfinished_enrollment_count", "Unfinished enrollments"],
  ["unfinished_crop_cycle_count", "Unfinished crop cycles"],
  ["unfinished_crop_stage_count", "Unfinished crop stages"],
  ["open_query_thread_count", "Open query threads"],
];

export function ProjectArchivePreflightPanel({
  projectId,
  onArchived,
}: ProjectArchivePreflightPanelProps) {
  const [preflight, setPreflight] =
    useState<ProjectArchivePreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [archiveReason, setArchiveReason] =
    useState("");
  const [confirmArchive, setConfirmArchive] =
    useState(false);
  const [archiving, setArchiving] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    projectsApi
      .getArchivePreflight(projectId)
      .then((result) => {
        if (active) setPreflight(result);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load archive preflight",
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

  const archiveProject = async () => {
    if (
      !preflight ||
      !preflight.decision.can_archive ||
      !preflight.decision.archive_supported ||
      archiveReason.trim().length < 3
    ) {
      return;
    }

    setArchiving(true);
    setError("");

    try {
      const result = await projectsApi.archive(
        projectId,
        archiveReason.trim(),
        preflight.decision.preflight_fingerprint,
      );

      if (
        result.project.status !== "ARCHIVED" ||
        (!result.archive.archived &&
          !result.archive.idempotent)
      ) {
        throw new Error(
          "Project archive returned an unexpected result.",
        );
      }

      setConfirmArchive(false);
      onArchived?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message} Run a fresh preflight if the server reports a stale decision.`
          : "Failed to archive project",
      );
      setConfirmArchive(false);
    } finally {
      setArchiving(false);
    }
  };

  if (loading) {
    return (
      <section
        aria-label="Project archive preflight"
        className="mt-4 rounded-lg border bg-gray-50 p-4"
      >
        <p className="text-sm text-gray-500">
          Checking project archive blockers…
        </p>
      </section>
    );
  }

  if (error || !preflight) {
    return (
      <section
        aria-label="Project archive preflight"
        className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4"
      >
        <p className="text-sm text-red-700">
          {error || "Archive preflight is unavailable."}
        </p>
      </section>
    );
  }

  const { decision, unfinished_counts: counts } = preflight;

  return (
    <section
      aria-label="Project archive preflight"
      className={`mt-4 rounded-lg border p-4 ${
        decision.can_archive
          ? "border-green-200 bg-green-50"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">
            Project archive preflight
          </h4>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {decision.can_archive
              ? "No operational blockers detected"
              : `Archive blocked by ${decision.blocker_count} check${
                  decision.blocker_count === 1 ? "" : "s"
                }`}
          </p>
        </div>
        <span
          className={`rounded px-2 py-1 text-xs font-semibold ${
            decision.can_archive
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-900"
          }`}
        >
          {decision.can_archive ? "CLEAR" : "BLOCKED"}
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

      <div className="mt-3 rounded border bg-white p-3">
        <p className="text-xs font-semibold text-gray-800">
          Records retained after archive
        </p>
        <p className="mt-1 text-xs text-gray-600">
          {Object.values(preflight.retained_counts).reduce(
            (total, count) => total + count,
            0,
          )} linked farmer, enrollment, parcel, crop-cycle,
          role, boundary-assignment, and field-event records
          remain stored.
        </p>
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
          No unfinished enrollment, crop cycle, crop stage, or
          query-thread work prevents archival.
        </p>
      )}

      {decision.can_archive &&
      decision.archive_supported ? (
        <div className="mt-4 rounded border border-amber-300 bg-white p-3">
          <label className="block text-xs font-medium text-gray-700">
            Project archive reason
            <input
              type="text"
              aria-label="Project archive reason"
              value={archiveReason}
              disabled={archiving}
              onChange={(event) =>
                setArchiveReason(event.target.value)
              }
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
              placeholder="Why should this completed project be archived?"
            />
          </label>

          {!confirmArchive ? (
            <button
              type="button"
              disabled={
                archiving ||
                archiveReason.trim().length < 3
              }
              onClick={() => setConfirmArchive(true)}
              className="mt-3 rounded bg-amber-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              Review project archive
            </button>
          ) : (
            <div className="mt-3 rounded border border-red-200 bg-red-50 p-3">
              <p className="text-sm font-semibold text-red-900">
                Confirm COMPLETED → ARCHIVED
              </p>
              <p className="mt-1 text-xs text-red-800">
                This archives the completed project as a retained record.
                Historical farmers, parcels, field evidence, assignments,
                boundaries, and audit records remain unchanged and
                available for traceability.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archiveProject()}
                  className="rounded bg-red-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {archiving
                    ? "Archiving project…"
                    : "Confirm project archive"}
                </button>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => setConfirmArchive(false)}
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
          Resolve every unfinished-work blocker before archive.
        </p>
      )}

      <p className="mt-3 text-[11px] text-gray-600">
        Opening this preflight does not change project status or
        operational records, boundary assignments, candidate activation
        or promotion, runtime tables, lookup behavior, or Android
        behavior. Archive requires a reason, a current preflight
        fingerprint, and explicit confirmation.
      </p>
    </section>
  );
}
