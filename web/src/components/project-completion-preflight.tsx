"use client";

import { useEffect, useState } from "react";
import {
  projectsApi,
  type ProjectCompletionPreflight,
} from "@/lib/api";

interface ProjectCompletionPreflightPanelProps {
  projectId: string;
  onCompleted?: () => void;
}

const countLabels: Array<
  [
    keyof ProjectCompletionPreflight["operational_counts"],
    string,
  ]
> = [
  ["unfinished_enrollment_count", "Unfinished enrollments"],
  ["unfinished_crop_cycle_count", "Unfinished crop cycles"],
  ["unfinished_crop_stage_count", "Unfinished crop stages"],
  ["open_query_thread_count", "Open query threads"],
];

export function ProjectCompletionPreflightPanel({
  projectId,
  onCompleted,
}: ProjectCompletionPreflightPanelProps) {
  const [preflight, setPreflight] =
    useState<ProjectCompletionPreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [completionReason, setCompletionReason] =
    useState("");
  const [confirmCompletion, setConfirmCompletion] =
    useState(false);
  const [completing, setCompleting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    projectsApi
      .getCompletionPreflight(projectId)
      .then((result) => {
        if (active) setPreflight(result);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load completion preflight",
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

  const completeProject = async () => {
    if (
      !preflight ||
      !preflight.decision.can_complete ||
      !preflight.decision.completion_supported ||
      completionReason.trim().length < 3
    ) {
      return;
    }

    setCompleting(true);
    setError("");

    try {
      const result = await projectsApi.complete(
        projectId,
        completionReason.trim(),
        preflight.decision.preflight_fingerprint,
      );

      if (
        result.project.status !== "COMPLETED" ||
        (!result.completion.completed &&
          !result.completion.idempotent)
      ) {
        throw new Error(
          "Project completion returned an unexpected result.",
        );
      }

      setConfirmCompletion(false);
      onCompleted?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message} Run a fresh preflight if the server reports a stale decision.`
          : "Failed to complete project",
      );
      setConfirmCompletion(false);
    } finally {
      setCompleting(false);
    }
  };

  if (loading) {
    return (
      <section
        aria-label="Project completion preflight"
        className="mt-4 rounded-lg border bg-gray-50 p-4"
      >
        <p className="text-sm text-gray-500">
          Checking project completion blockers…
        </p>
      </section>
    );
  }

  if (error || !preflight) {
    return (
      <section
        aria-label="Project completion preflight"
        className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4"
      >
        <p className="text-sm text-red-700">
          {error || "Completion preflight is unavailable."}
        </p>
      </section>
    );
  }

  const { decision, operational_counts: counts } = preflight;

  return (
    <section
      aria-label="Project completion preflight"
      className={`mt-4 rounded-lg border p-4 ${
        decision.can_complete
          ? "border-green-200 bg-green-50"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">
            Project completion preflight
          </h4>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {decision.can_complete
              ? "No operational blockers detected"
              : `Completion blocked by ${decision.blocker_count} check${
                  decision.blocker_count === 1 ? "" : "s"
                }`}
          </p>
        </div>
        <span
          className={`rounded px-2 py-1 text-xs font-semibold ${
            decision.can_complete
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-900"
          }`}
        >
          {decision.can_complete ? "CLEAR" : "BLOCKED"}
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
          Every enrollment, crop cycle, crop stage, and query
          thread is in an accepted terminal state.
        </p>
      )}

      {decision.can_complete &&
      decision.completion_supported ? (
        <div className="mt-4 rounded border border-amber-300 bg-white p-3">
          <label className="block text-xs font-medium text-gray-700">
            Project completion reason
            <input
              type="text"
              aria-label="Project completion reason"
              value={completionReason}
              disabled={completing}
              onChange={(event) =>
                setCompletionReason(event.target.value)
              }
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
              placeholder="Why should this project be finalized?"
            />
          </label>

          {!confirmCompletion ? (
            <button
              type="button"
              disabled={
                completing ||
                completionReason.trim().length < 3
              }
              onClick={() => setConfirmCompletion(true)}
              className="mt-3 rounded bg-amber-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              Review project completion
            </button>
          ) : (
            <div className="mt-3 rounded border border-red-200 bg-red-50 p-3">
              <p className="text-sm font-semibold text-red-900">
                Confirm ACTIVE → COMPLETED
              </p>
              <p className="mt-1 text-xs text-red-800">
                This permanently closes the active project lifecycle.
                Historical farmers, parcels, field evidence, assignments,
                boundaries, and audit records remain unchanged and
                available for traceability.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={completing}
                  onClick={() => void completeProject()}
                  className="rounded bg-red-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {completing
                    ? "Completing project…"
                    : "Confirm project completion"}
                </button>
                <button
                  type="button"
                  disabled={completing}
                  onClick={() => setConfirmCompletion(false)}
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
          Resolve every operational blocker before completion.
        </p>
      )}

      <p className="mt-3 text-[11px] text-gray-600">
        Opening this preflight does not change project status or
        operational records, boundary assignments, candidate activation
        or promotion, runtime tables, lookup behavior, or Android
        behavior. Completion requires a reason, a current preflight
        fingerprint, and explicit confirmation.
      </p>
    </section>
  );
}
