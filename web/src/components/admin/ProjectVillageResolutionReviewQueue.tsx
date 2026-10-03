"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type ReviewAction =
  | "PROPOSED"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED"
  | "APPLIED"
  | "ROLLED_BACK";

type ReviewEvent = {
  event_id: string;
  action: ReviewAction;
  actor_id: string;
  approver_id: string | null;
  created_at: string;
};

type ReviewItem = {
  resolution_id: string;
  resolution_status: "DRAFT" | "APPROVED" | "ACTIVE" | "RETIRED" | "REJECTED";
  display_name: string;
  project_village_code: string;
  pin_codes: string[];
  review_notes: string | null;
  events: ReviewEvent[];
};

type ReviewQueue = {
  schema_version: "project_village_resolution_review_queue.v1";
  activation_enabled: boolean;
  items: ReviewItem[];
};

type ReviewCommand = "approve" | "reject" | "cancel" | "activate";

const confirmations: Record<ReviewCommand, string> = {
  approve: "APPROVE PROJECT CANONICAL ENRICHMENT",
  reject: "REJECT PROJECT CANONICAL ENRICHMENT",
  cancel: "CANCEL PROJECT CANONICAL ENRICHMENT",
  activate: "ACTIVATE APPROVED PROJECT CANONICAL ENRICHMENT",
};

const notices: Record<ReviewCommand, string> = {
  approve: "Proposal approved by this independently authenticated administrator.",
  reject: "Proposal rejected with an immutable review reason.",
  cancel: "Draft proposal cancelled by its proposer.",
  activate: "Approved project resolution activated.",
};

export default function ProjectVillageResolutionReviewQueue({
  projectId,
  refreshKey,
}: {
  projectId: string;
  refreshKey: number;
}) {
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [notes, setNotes] = useState("Independent enterprise-admin review completed");
  const [currentActorId, setCurrentActorId] = useState("");
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setCurrentActorId(localStorage.getItem("agrios_user_id") || "");
  }, []);

  const load = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    try {
      setQueue(
        await api<ReviewQueue>(
          `/api/v1/master-data/geography/project-village-resolutions/projects/${projectId}/resolutions`
        )
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load review queue");
    }
  }, [projectId]);

  useEffect(() => {
    if (refreshKey > 0) void load();
  }, [load, refreshKey]);

  const review = useCallback(
    async (item: ReviewItem, action: ReviewCommand) => {
      setLoadingId(item.resolution_id);
      setError(null);
      setNotice(null);
      try {
        await api(
          `/api/v1/master-data/geography/project-village-resolutions/projects/${projectId}/resolutions/${item.resolution_id}/${action}`,
          {
            method: "POST",
            body: {
              confirmation_phrase: confirmations[action],
              review_notes: notes,
            },
          }
        );
        setNotice(notices[action]);
        await load();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : `Failed to ${action} proposal`);
      } finally {
        setLoadingId(null);
      }
    },
    [load, notes, projectId]
  );

  return (
    <section className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-semibold text-indigo-950">Independent review queue</h3>
          <p className="text-xs text-indigo-800">
            A proposal must be approved or rejected in a different enterprise-admin session.
            Approval does not activate it.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={!projectId}
          className="rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-semibold text-indigo-800 disabled:text-slate-400"
        >
          Load review queue
        </button>
      </div>

      <label className="block text-sm">
        Review reason
        <input
          aria-label="Review reason"
          value={notes}
          minLength={8}
          onChange={(event) => setNotes(event.target.value)}
          className="mt-1 w-full rounded-lg border p-2"
        />
      </label>

      {queue && (
        <>
          <p className="text-xs text-slate-600">
            Activation gate:{" "}
            {queue.activation_enabled ? "enabled" : "disabled (repository-safe default)"}
          </p>
          {queue.items.length === 0 ? (
            <p className="text-sm text-slate-600">No project resolution proposals.</p>
          ) : (
            <div className="space-y-2">
              {queue.items.map((item) => {
                const proposerId = item.events.find(
                  (event) => event.action === "PROPOSED"
                )?.actor_id;
                const isProposer = Boolean(
                  currentActorId && proposerId === currentActorId
                );
                const busy =
                  loadingId === item.resolution_id || notes.trim().length < 8;
                return (
                  <article
                    key={item.resolution_id}
                    className="rounded-lg border bg-white p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <strong>{item.display_name}</strong>
                        <div className="text-xs text-slate-500">
                          {item.project_village_code} · {item.resolution_status}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {item.resolution_status === "DRAFT" && isProposer && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void review(item, "cancel")}
                            className="rounded-lg border border-slate-400 bg-white px-3 py-2 font-semibold text-slate-800 disabled:text-slate-400"
                          >
                            Cancel draft
                          </button>
                        )}
                        {item.resolution_status === "DRAFT" && !isProposer && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void review(item, "approve")}
                            className="rounded-lg bg-indigo-700 px-3 py-2 font-semibold text-white disabled:bg-slate-300"
                          >
                            Approve proposal
                          </button>
                        )}
                        {(item.resolution_status === "DRAFT" ||
                          item.resolution_status === "APPROVED") &&
                          !isProposer && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void review(item, "reject")}
                              className="rounded-lg bg-rose-700 px-3 py-2 font-semibold text-white disabled:bg-slate-300"
                            >
                              Reject proposal
                            </button>
                          )}
                        {item.resolution_status === "APPROVED" &&
                          queue.activation_enabled && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void review(item, "activate")}
                              className="rounded-lg bg-emerald-700 px-3 py-2 font-semibold text-white disabled:bg-slate-300"
                            >
                              Activate approved resolution
                            </button>
                          )}
                      </div>
                    </div>
                    <ol
                      aria-label={`Audit history for ${item.display_name}`}
                      className="mt-2 space-y-1 text-xs text-slate-600"
                    >
                      {item.events.map((event) => (
                        <li key={event.event_id}>
                          {event.action} · {new Date(event.created_at).toLocaleString()}
                        </li>
                      ))}
                    </ol>
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}
      {notice && (
        <p className="rounded-lg bg-emerald-50 p-2 text-sm text-emerald-800">
          {notice}
        </p>
      )}
      {error && (
        <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>
      )}
    </section>
  );
}
