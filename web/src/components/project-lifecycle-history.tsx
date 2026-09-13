"use client";

import { useEffect, useState } from "react";
import {
  projectsApi,
  type ProjectLifecycleAuditResponse,
} from "@/lib/api";

interface ProjectLifecycleHistoryProps {
  projectId: string;
}

export function ProjectLifecycleHistory({
  projectId,
}: ProjectLifecycleHistoryProps) {
  const [data, setData] =
    useState<ProjectLifecycleAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    projectsApi
      .lifecycleAudit(projectId)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load project lifecycle history",
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

  return (
    <section
      aria-label="Project lifecycle history"
      className="mt-4 rounded-lg border border-purple-200 bg-purple-50 p-4"
    >
      <h4 className="text-sm font-semibold text-purple-950">
        Project lifecycle history
      </h4>
      <p className="mt-1 text-xs text-purple-800">
        Immutable project status transitions and their approved
        preflight evidence.
      </p>

      {loading ? (
        <p className="mt-3 text-sm text-gray-500">
          Loading project lifecycle history…
        </p>
      ) : null}

      {error ? (
        <p className="mt-3 text-sm text-red-700">{error}</p>
      ) : null}

      {!loading && !error && data?.events.length === 0 ? (
        <p className="mt-3 text-sm text-gray-600">
          No lifecycle transitions have been recorded.
        </p>
      ) : null}

      <div className="mt-3 space-y-3">
        {data?.events.map((event) => (
          <article
            key={event.id}
            className="rounded border border-purple-100 bg-white p-3"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  {event.transition.from_status || "Unknown"}
                  {" → "}
                  {event.transition.to_status || "Unknown"}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  {event.actor.display_name || "Unknown actor"}
                  {" · "}
                  {event.actor.role || "Role unavailable"}
                  {" · "}
                  {event.created_at
                    ? new Date(event.created_at).toLocaleString()
                    : "Time unavailable"}
                </p>
              </div>
              <span className="rounded bg-purple-100 px-2 py-1 text-[10px] font-semibold text-purple-800">
                {event.action.replaceAll("_", " ")}
              </span>
            </div>

            <p className="mt-2 text-sm text-gray-700">
              {event.reason || "No reason recorded"}
            </p>

            {event.preflight_fingerprint ? (
              <p className="mt-2 break-all font-mono text-[10px] text-gray-500">
                Preflight fingerprint: {event.preflight_fingerprint}
              </p>
            ) : null}

            {Object.keys(event.geography_summary || {}).length ? (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-semibold text-purple-800">
                  Geography evidence
                </summary>
                <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-2 text-[10px] text-gray-700">
                  {JSON.stringify(event.geography_summary, null, 2)}
                </pre>
              </details>
            ) : null}
          </article>
        ))}
      </div>

      <p className="mt-3 text-[11px] text-gray-500">
        {"Viewing lifecycle history performs no database write and does not change project status."}
      </p>
    </section>
  );
}
