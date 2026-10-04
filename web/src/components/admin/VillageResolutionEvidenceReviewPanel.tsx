"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Selection = {
  evidenceItemId: string;
  villageName: string;
  villageLgdCode: string;
  snapshotId: string | null;
  canonicalHierarchy: string;
  sourceFeatureId: string | null;
  sourceVillageName: string | null;
  sourceHierarchy: string;
  sourceCode: string | null;
  matchRank: number | null;
  matchBasis: string | null;
  priorEvidence: string | null;
  sourceReuseCount: number | null;
};

type ReviewEvent = {
  event_id: string;
  action: string;
  actor_id: string;
  created_at: string;
};

type ReviewItem = {
  review_id: string;
  evidence_item_id: string;
  village_name: string;
  village_lgd_code: string;
  status: "PENDING_SECOND_REVIEW" | "APPROVED" | "REJECTED" | "HELD";
  primary_decision: string;
  primary_reviewer_id: string;
  second_decision: string | null;
  second_reviewer_id: string | null;
  events: ReviewEvent[];
};

type Queue = {
  schema_version: "village_resolution_evidence_review_queue.v1";
  mode: "REVIEW_ONLY_NO_APPLY";
  items: ReviewItem[];
};

export default function VillageResolutionEvidenceReviewPanel({
  selection,
  onClearSelection,
}: {
  selection: Selection | null;
  onClearSelection: () => void;
}) {
  const [queue, setQueue] = useState<Queue | null>(null);
  const [primaryDecision, setPrimaryDecision] =
    useState("ACCEPT_FOR_SECOND_REVIEW");
  const [primaryNotes, setPrimaryNotes] =
    useState("Primary admin reviewed the local evidence.");
  const [secondDecision, setSecondDecision] = useState("APPROVE");
  const [secondNotes, setSecondNotes] =
    useState("Independent enterprise admin confirmed the evidence.");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [currentActorId, setCurrentActorId] = useState("");

  useEffect(() => {
    setCurrentActorId(localStorage.getItem("agrios_user_id") || "");
  }, []);

  const loadQueue = useCallback(async () => {
    setError(null);
    try {
      setQueue(await api<Queue>(
        "/api/v1/master-data/geography/village-resolution/reviews"
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load evidence reviews");
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  async function submitPrimary() {
    if (!selection) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api<{ status: string }>(
        "/api/v1/master-data/geography/village-resolution/reviews",
        {
          method: "POST",
          body: {
            evidence_item_id: selection.evidenceItemId,
            decision: primaryDecision,
            notes: primaryNotes,
          },
        }
      );
      setNotice(`Primary evidence decision recorded: ${result.status}`);
      onClearSelection();
      await loadQueue();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Primary review failed");
    } finally {
      setLoading(false);
    }
  }

  async function submitSecond(reviewId: string) {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api<{ status: string }>(
        `/api/v1/master-data/geography/village-resolution/reviews/${reviewId}/second-review`,
        {
          method: "POST",
          body: {
            decision: secondDecision,
            notes: secondNotes,
            confirmation_phrase: confirmation,
          },
        }
      );
      setNotice(`Independent evidence decision recorded: ${result.status}`);
      setConfirmation("");
      await loadQueue();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Second review failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section data-testid="village-evidence-review-panel" className="space-y-4 rounded-2xl border border-violet-200 bg-violet-50 p-4">
      <div>
        <h3 className="font-semibold text-violet-950">Two-session evidence review</h3>
        <p className="text-sm text-violet-800">
          Review decisions never apply canonical geography, PIN links, runtime mappings, or Android visibility.
        </p>
      </div>

      {selection && (
        <div className="space-y-3 rounded-xl border border-violet-200 bg-white p-3">
          <div className="font-medium">
            {selection.villageName} · LGD {selection.villageLgdCode}
          </div>
          <div data-testid="village-evidence-comparison" className="grid gap-3 text-sm md:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs font-semibold uppercase text-slate-500">Canonical LGD village</div>
              <div className="mt-1 font-medium">{selection.villageName}</div>
              <div className="text-slate-600">{selection.canonicalHierarchy || "Hierarchy unavailable"}</div>
              <div className="text-xs text-slate-500">LGD {selection.villageLgdCode}</div>
            </div>
            <div className="rounded-lg bg-blue-50 p-3">
              <div className="text-xs font-semibold uppercase text-blue-700">NWDP source candidate</div>
              <div className="mt-1 font-medium">{selection.sourceVillageName || "Source name unavailable"}</div>
              <div className="text-slate-600">{selection.sourceHierarchy || "Hierarchy unavailable"}</div>
              <div className="text-xs text-slate-500">Source village code {selection.sourceCode || "—"}</div>
            </div>
          </div>
          <dl className="grid gap-x-4 gap-y-1 rounded-lg border border-violet-100 p-3 text-xs sm:grid-cols-2">
            <div><dt className="font-medium text-slate-500">Match rank / basis</dt><dd>{selection.matchRank ?? "—"} / {selection.matchBasis || "—"}</dd></div>
            <div><dt className="font-medium text-slate-500">Source reuse count</dt><dd>{selection.sourceReuseCount ?? "—"}</dd></div>
            <div><dt className="font-medium text-slate-500">Prior candidate evidence</dt><dd>{selection.priorEvidence || "—"}</dd></div>
            <div><dt className="font-medium text-slate-500">Evidence identity</dt><dd className="break-all">{selection.snapshotId || "—"} / {selection.sourceFeatureId || "—"}</dd></div>
          </dl>
          <label className="block space-y-1">
            <span className="text-xs font-medium">Primary decision</span>
            <select aria-label="Primary evidence decision" value={primaryDecision} onChange={event => setPrimaryDecision(event.target.value)} className="w-full rounded-lg border px-3 py-2">
              <option value="ACCEPT_FOR_SECOND_REVIEW">Accept for second review</option>
              <option value="REJECT">Reject</option>
              <option value="HOLD">Hold</option>
            </select>
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium">Primary review notes</span>
            <textarea aria-label="Primary review notes" value={primaryNotes} onChange={event => setPrimaryNotes(event.target.value)} className="w-full rounded-lg border px-3 py-2" />
          </label>
          <div className="flex gap-2">
            <button type="button" disabled={loading || primaryNotes.trim().length < 8} onClick={() => void submitPrimary()} className="rounded-lg bg-violet-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">
              Record primary decision
            </button>
            <button type="button" onClick={onClearSelection} className="rounded-lg border px-3 py-2 text-sm">Cancel selection</button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h4 className="font-medium text-violet-950">Active-snapshot review queue</h4>
        <button type="button" onClick={() => void loadQueue()} className="rounded-lg border bg-white px-3 py-1.5 text-sm">Refresh review queue</button>
      </div>
      <label className="block space-y-1">
        <span className="text-xs font-medium">Second decision</span>
        <select aria-label="Second evidence decision" value={secondDecision} onChange={event => setSecondDecision(event.target.value)} className="w-full rounded-lg border bg-white px-3 py-2">
          <option value="APPROVE">Approve</option>
          <option value="REJECT">Reject</option>
          <option value="HOLD">Hold</option>
        </select>
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium">Second review notes</span>
        <textarea aria-label="Second review notes" value={secondNotes} onChange={event => setSecondNotes(event.target.value)} className="w-full rounded-lg border bg-white px-3 py-2" />
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium">Second review confirmation</span>
        <input aria-label="Second review confirmation" value={confirmation} onChange={event => setConfirmation(event.target.value)} placeholder="COMPLETE SECOND VILLAGE EVIDENCE REVIEW" className="w-full rounded-lg border bg-white px-3 py-2" />
      </label>

      <div className="space-y-2">
        {(queue?.items || []).map(item => (
          <article key={item.review_id} className="rounded-xl border border-violet-200 bg-white p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-medium">{item.village_name} · LGD {item.village_lgd_code}</div>
                <div className="text-xs text-slate-600">{item.status.replaceAll("_", " ")} · {item.events.map(event => event.action.replaceAll("_", " ")).join(" → ")}</div>
              </div>
              {item.status === "PENDING_SECOND_REVIEW" && (
                <button
                  type="button"
                  disabled={
                    loading ||
                    confirmation !== "COMPLETE SECOND VILLAGE EVIDENCE REVIEW" ||
                    secondNotes.trim().length < 8 ||
                    item.primary_reviewer_id === currentActorId
                  }
                  onClick={() => void submitSecond(item.review_id)}
                  className="rounded-lg bg-violet-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  Complete independent review
                </button>
              )}
            </div>
            {item.status === "PENDING_SECOND_REVIEW" && item.primary_reviewer_id === currentActorId && (
              <p className="mt-2 text-xs font-medium text-amber-700">Sign in as a different enterprise administrator to complete this review.</p>
            )}
          </article>
        ))}
        {queue && queue.items.length === 0 && (
          <p className="text-sm text-violet-800">No evidence reviews have been recorded.</p>
        )}
      </div>
      {notice && <p className="text-sm font-medium text-emerald-700">{notice}</p>}
      {error && <p className="text-sm font-medium text-rose-700">{error}</p>}
    </section>
  );
}
