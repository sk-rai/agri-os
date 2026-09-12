"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  geographyApi,
  projectsApi,
  type ProjectGeographyActivationPreflight,
} from "@/lib/api";

interface ProjectGeographyActivationPreflightProps {
  projectId: string;
  onActivated?: () => void;
}

export function ProjectGeographyActivationPreflightPanel({
  projectId,
  onActivated,
}: ProjectGeographyActivationPreflightProps) {
  const [preflight, setPreflight] =
    useState<ProjectGeographyActivationPreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activationReason, setActivationReason] = useState("");
  const [confirmActivation, setConfirmActivation] = useState(false);
  const [activating, setActivating] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    geographyApi
      .getProjectGeographyActivationPreflight(projectId)
      .then((result) => {
        if (active) setPreflight(result);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load activation preflight",
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

  const activateProject = async () => {
    if (
      !preflight ||
      !preflight.decision.can_activate_geography ||
      activationReason.trim().length < 3
    ) {
      return;
    }

    setActivating(true);
    setError("");

    try {
      const result = await projectsApi.activate(
        projectId,
        activationReason.trim(),
        preflight.decision.preflight_fingerprint,
      );

      if (
        result.project.status !== "ACTIVE" ||
        (!result.activation.activated &&
          !result.activation.idempotent)
      ) {
        throw new Error(
          "Project activation returned an unexpected result.",
        );
      }

      setConfirmActivation(false);
      onActivated?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to activate project",
      );
      setConfirmActivation(false);
    } finally {
      setActivating(false);
    }
  };

  if (loading) {
    return (
      <section
        aria-label="Project geography activation preflight"
        className="mt-4 rounded-lg border bg-gray-50 p-4"
      >
        <p className="text-sm text-gray-500">
          Checking geography activation readiness…
        </p>
      </section>
    );
  }

  if (error || !preflight) {
    return (
      <section
        aria-label="Project geography activation preflight"
        className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4"
      >
        <p className="text-sm text-red-700">
          {error || "Activation preflight is unavailable."}
        </p>
      </section>
    );
  }

  const { summary, decision } = preflight;
  const ready = decision.can_activate_geography;

  return (
    <section
      aria-label="Project geography activation preflight"
      className={`mt-4 rounded-lg border p-4 ${
        ready
          ? "border-green-200 bg-green-50"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">
            Geography activation preflight
          </h4>
          <p
            className={`mt-1 text-sm font-semibold ${
              ready ? "text-green-800" : "text-amber-900"
            }`}
          >
            {ready
              ? "Ready for project activation"
              : `Activation blocked by ${decision.blocker_count} geography check${
                  decision.blocker_count === 1 ? "" : "s"
                }`}
          </p>
        </div>
        <span
          className={`rounded px-2 py-1 text-xs font-semibold ${
            ready
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-900"
          }`}
        >
          {ready ? "READY" : "BLOCKED"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded bg-white p-2">
          <span className="block font-semibold text-gray-900">
            {summary.resolved_village_count}/
            {summary.configured_village_code_count}
          </span>
          Canonical villages
        </div>
        <div className="rounded bg-white p-2">
          <span className="block font-semibold text-green-800">
            {summary.villages_with_eligible_boundary}
          </span>
          Eligible boundaries
        </div>
        <div className="rounded bg-white p-2">
          <span className="block font-semibold text-amber-800">
            {summary.villages_without_eligible_boundary}
          </span>
          Missing boundaries
        </div>
        <div className="rounded bg-white p-2">
          <span className="block font-semibold text-red-800">
            {summary.blocked_candidate_count +
              summary.manual_review_candidate_count}
          </span>
          Review candidates
        </div>
      </div>

      {decision.blockers.length ? (
        <ul className="mt-3 space-y-2">
          {decision.blockers.map((blocker) => (
            <li
              key={blocker.code}
              className="rounded border border-amber-200 bg-white px-3 py-2 text-xs text-amber-900"
            >
              <span className="font-semibold">
                {blocker.code.replaceAll("_", " ")}
              </span>
              <span className="ml-2">{blocker.message}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-green-800">
          Every configured canonical village has an eligible validated
          direct-code boundary candidate.
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-3 text-xs">
        <Link
          href={preflight.links.boundary_review}
          className="font-semibold text-blue-700 hover:underline"
        >
          Review project boundaries
        </Link>
        <span className="text-gray-500">
          Scope editing and history are available on this project card.
        </span>
      </div>

      {ready ? (
        <div className="mt-4 rounded border border-green-200 bg-white p-3">
          <label className="block text-xs font-medium text-gray-700">
            Project activation reason
            <input
              type="text"
              aria-label="Project activation reason"
              value={activationReason}
              onChange={(event) => {
                setActivationReason(event.target.value);
                setConfirmActivation(false);
              }}
              minLength={3}
              maxLength={500}
              disabled={activating}
              placeholder="Why this project is ready to activate"
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
            />
          </label>

          {!confirmActivation ? (
            <button
              type="button"
              disabled={
                activating ||
                activationReason.trim().length < 3
              }
              onClick={() => setConfirmActivation(true)}
              className="mt-3 rounded bg-green-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              Review project activation
            </button>
          ) : (
            <div
              role="alert"
              className="mt-3 rounded border border-amber-300 bg-amber-50 p-3"
            >
              <p className="text-xs font-semibold text-amber-900">
                Confirm PLANNED → ACTIVE
              </p>
              <p className="mt-1 text-xs text-amber-800">
                Geography will become locked for normal editing. The server
                will re-run the preflight and reject a stale decision.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={activating}
                  onClick={() => void activateProject()}
                  className="rounded bg-green-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {activating
                    ? "Activating project…"
                    : "Confirm project activation"}
                </button>
                <button
                  type="button"
                  disabled={activating}
                  onClick={() => setConfirmActivation(false)}
                  className="rounded border px-3 py-2 text-xs font-semibold text-gray-700 disabled:opacity-50"
                >
                  Cancel activation
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}

      <p className="mt-3 text-[11px] text-gray-600">
        The preflight is advisory until explicit confirmation. Opening this
        panel does not change project status, activate or promote boundary
        candidates, write runtime tables, enable lookup, or change Android
        behavior.
      </p>
    </section>
  );
}
