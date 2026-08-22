"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type Governance = {
  read_only_runtime: boolean;
  promotion_supported: boolean;
  runtime_spatial_matching_changed: boolean;
  android_behavior_changed: boolean;
  db_write_scope: string;
  claim_boundary: string;
};

type BoundaryBatch = {
  id?: string;
  batch_id?: string;
  source_system: string;
  state_or_ut: string;
  source_format: string;
  status: string;
  review_status: string;
  is_active: boolean;
  source_feature_count?: number | null;
  candidate_count?: number | null;
  active_candidate_count?: number | null;
  promoted_candidate_count?: number | null;
};

type BatchListResponse = {
  schema_version: string;
  governance: Governance;
  items: BoundaryBatch[];
  total: number;
};

type CandidateRow = {
  candidate_id: string;
  source_feature_id: string;
  source_feature_index: number;
  candidate_bucket: string;
  confidence: string;
  review_status: string;
  promotion_status: string;
  proposed_scope: string;
  source_codes: Record<string, string | null>;
  source_names: Record<string, string | null>;
  proposed_village_lgd_code?: string | null;
  proposed_village_id?: string | null;
  is_active?: boolean;
};

type CandidateListResponse = {
  schema_version: string;
  governance: Governance;
  summary: {
    total: number;
    auto_candidate_count: number;
    manual_review_count: number;
    blocked_count: number;
    active_candidate_count: number;
    promoted_candidate_count: number;
    runtime_spatial_matching_changed: boolean;
  };
  items: CandidateRow[];
  total: number;
  offset: number;
  limit: number;
};

type CandidateDetailResponse = {
  schema_version: string;
  mode: string;
  governance: Governance;
  candidate: CandidateRow & {
    batch_id: string;
    reviewer_decision?: string | null;
    reviewer_id?: string | null;
    reviewed_at?: string | null;
    reviewer_notes?: string | null;
    is_active: boolean;
  };
  source_feature: Record<string, unknown>;
};

type ReviewResponse = {
  schema_version: string;
  candidate_id: string;
  previous_review_status: string;
  review_status: string;
  previous_reviewer_decision?: string | null;
  reviewer_decision: string;
  is_active: boolean;
  promotion_status: string;
  runtime_spatial_matching_changed: boolean;
  android_behavior_changed: boolean;
  promotion_supported: boolean;
};

const BUCKETS = [
  "",
  "DIRECT_VLCODE_MATCH",
  "DIRECT_VLCODE_PARENT_MISMATCH",
  "PARENT_MATCH_VILLAGE_UNRESOLVED",
  "PARENT_SCOPED_NAME_MATCH",
  "PARENT_SCOPED_NAME_AMBIGUOUS",
  "DISTRICT_SCOPED_AMBIGUOUS",
  "SPECIAL_REFERENCE_FEATURE",
];

const REVIEW_STATUSES = [
  "",
  "AUTO_CANDIDATE",
  "MANUAL_REVIEW",
  "BLOCKED",
  "REFERENCE_ONLY",
  "REJECTED",
  "APPROVED_FOR_PROMOTION",
];

const SCOPES = [
  "",
  "village",
  "village_review",
  "district_review",
  "district_subdistrict",
  "district_subdistrict_reference_only",
];

const DECISIONS = [
  "KEEP_PENDING",
  "ACCEPT_DIRECT_CODE_MATCH",
  "ACCEPT_REVIEWED_NAME_MATCH",
  "MARK_REFERENCE_ONLY",
  "REJECT_SOURCE_MISMATCH",
  "REJECT_SPECIAL_FEATURE",
  "BLOCK_PENDING_SOURCE_REVIEW",
];

function bucketTone(bucket: string) {
  if (bucket === "DIRECT_VLCODE_MATCH") return "border-green-200 bg-green-50 text-green-700";
  if (bucket === "SPECIAL_REFERENCE_FEATURE") return "border-red-200 bg-red-50 text-red-700";
  if (bucket.includes("AMBIGUOUS") || bucket.includes("MISMATCH")) return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function statusTone(status: string) {
  if (status === "AUTO_CANDIDATE") return "border-green-200 bg-green-50 text-green-700";
  if (status === "BLOCKED" || status === "REJECTED") return "border-red-200 bg-red-50 text-red-700";
  if (status === "REFERENCE_ONLY") return "border-purple-200 bg-purple-50 text-purple-700";
  return "border-amber-200 bg-amber-50 text-amber-800";
}

function getBatchId(batch: BoundaryBatch) {
  return batch.batch_id || batch.id || "";
}

function sourceLabel(row: CandidateRow | null) {
  if (!row) return "No candidate selected";
  const names = row.source_names || {};
  return [names.district, names.subdistrict, names.village].filter(Boolean).join(" / ") || `Feature ${row.source_feature_index}`;
}

export default function NwdpBoundaryReviewPage() {
  const [batches, setBatches] = useState<BoundaryBatch[]>([]);
  const [batchId, setBatchId] = useState("");
  const [data, setData] = useState<CandidateListResponse | null>(null);
  const [detail, setDetail] = useState<CandidateDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [bucket, setBucket] = useState("PARENT_MATCH_VILLAGE_UNRESOLVED");
  const [reviewStatus, setReviewStatus] = useState("MANUAL_REVIEW");
  const [scope, setScope] = useState("");
  const [district, setDistrict] = useState("");
  const [subdistrict, setSubdistrict] = useState("");
  const [vlcode, setVlcode] = useState("");
  const [specialOnly, setSpecialOnly] = useState(false);
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);
  const [parentMismatchOnly, setParentMismatchOnly] = useState(false);
  const [offset, setOffset] = useState(0);

  function showQueue(nextBucket: string, nextReviewStatus = "", options?: { specialOnly?: boolean; unresolvedOnly?: boolean; parentMismatchOnly?: boolean }) {
    setBucket(nextBucket);
    setReviewStatus(nextReviewStatus);
    setScope("");
    setDistrict("");
    setSubdistrict("");
    setVlcode("");
    setSpecialOnly(Boolean(options?.specialOnly));
    setUnresolvedOnly(Boolean(options?.unresolvedOnly));
    setParentMismatchOnly(Boolean(options?.parentMismatchOnly));
    setDetail(null);
    setOffset(0);
  }

  const [reviewDecision, setReviewDecision] = useState("KEEP_PENDING");
  const [reviewNotes, setReviewNotes] = useState("");
  const limit = 100;

  const selectedCandidate = detail?.candidate ?? data?.items[0] ?? null;
  const selectedMatchEvidence = detail?.candidate?.match_evidence ?? selectedCandidate?.match_evidence ?? null;

  const queryPath = useMemo(() => {
    if (!batchId) return null;
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (bucket) params.set("candidate_bucket", bucket);
    if (reviewStatus) params.set("review_status", reviewStatus);
    if (scope) params.set("proposed_scope", scope);
    if (district.trim()) params.set("district", district.trim());
    if (subdistrict.trim()) params.set("subdistrict", subdistrict.trim());
    if (vlcode.trim()) params.set("vlcode", vlcode.trim());
    if (specialOnly) params.set("special_reference_only", "true");
    if (unresolvedOnly) params.set("unresolved_only", "true");
    if (parentMismatchOnly) params.set("parent_mismatch_only", "true");
    return `/api/v1/master-data/geography/nwdp-boundary-batches/${batchId}/candidates?${params.toString()}`;
  }, [batchId, bucket, district, offset, parentMismatchOnly, reviewStatus, scope, specialOnly, subdistrict, unresolvedOnly, vlcode]);

  const loadBatches = useCallback(async () => {
    const response = await api<BatchListResponse>("/api/v1/master-data/geography/nwdp-boundary-batches?limit=25");
    setBatches(response.items);
    if (!batchId && response.items.length > 0) setBatchId(getBatchId(response.items[0]));
  }, [batchId]);

  const loadCandidates = useCallback(async () => {
    if (!queryPath) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api<CandidateListResponse>(queryPath);
      setData(response);
      setDetail(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load NWDP boundary candidates");
    } finally {
      setLoading(false);
    }
  }, [queryPath]);

  const loadDetail = useCallback(async (candidateId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const response = await api<CandidateDetailResponse>(`/api/v1/master-data/geography/nwdp-boundary-candidates/${candidateId}`);
      setDetail(response);
      setReviewDecision(response.candidate.reviewer_decision || "KEEP_PENDING");
      setReviewNotes(response.candidate.reviewer_notes || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candidate detail");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBatches().catch((err) => setError(err instanceof Error ? err.message : "Failed to load NWDP boundary batches"));
  }, [loadBatches]);

  useEffect(() => {
    const firstCandidateId = data?.items[0]?.candidate_id;
    if (!detail && firstCandidateId) {
      void loadDetail(firstCandidateId);
    }
  }, [data, detail, loadDetail]);

  useEffect(() => { void loadCandidates(); }, [loadCandidates]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    void loadCandidates();
  }

  function chooseReviewDecision(decision: string, suggestedNotes = "") {
    setReviewDecision(decision);
    if (suggestedNotes && !reviewNotes.trim()) {
      setReviewNotes(suggestedNotes);
    }
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault();
    if (!selectedCandidate) return;
    setError(null);
    setMessage(null);
    try {
      const payload = await api<ReviewResponse>(`/api/v1/master-data/geography/nwdp-boundary-candidates/${selectedCandidate.candidate_id}/review`, {
        method: "PATCH",
        body: {
          reviewer_decision: reviewDecision,
          review_notes: reviewNotes,
          evidence_summary: { source: "nwdp-boundary-review-ui", guarded_runtime: true },
        },
      });
      setMessage(`Updated review metadata to ${payload.review_status}. Candidate remains inactive and unpromoted.`);
      await loadDetail(selectedCandidate.candidate_id);
      await loadCandidates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update review metadata");
    }
  }

  const canPrev = offset > 0;
  const canNext = data ? offset + limit < data.total : false;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-green-700">Reference data review</p>
        <h1 className="text-2xl font-bold text-gray-900">NWDP Boundary Review</h1>
        <p className="mt-2 max-w-4xl text-sm text-gray-600">
          Review inactive NWDP/GSI Karnataka village-boundary crosswalk candidates. This follows the CoRE/LGD pattern:
          review metadata is allowed, but no geometry is activated, promoted, or used for runtime point-in-polygon matching here.
        </p>
      </div>

      {error ? <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {message ? <div className="rounded border border-green-200 bg-green-50 p-4 text-sm text-green-700">{message}</div> : null}

      <section className="grid gap-4 md:grid-cols-4">
        <Card label="Candidates" value={data?.summary.total ?? batches[0]?.candidate_count ?? "—"} />
        <Card label="Auto candidates" value={data?.summary.auto_candidate_count ?? "—"} />
        <Card label="Manual review" value={data?.summary.manual_review_count ?? "—"} />
        <Card label="Active / promoted" value={`${data?.summary.active_candidate_count ?? 0} / ${data?.summary.promoted_candidate_count ?? 0}`} tone="safe" />
      </section>

      <section className="rounded-xl border bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold text-gray-900">Review filters</h2>
            <p className="text-sm text-gray-500">Default view starts with unresolved parent-scoped rows.</p>
          </div>
          <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-semibold text-gray-600">
            Runtime matching: disabled
          </span>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <button type="button" className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700" onClick={() => showQueue("PARENT_MATCH_VILLAGE_UNRESOLVED", "MANUAL_REVIEW", { unresolvedOnly: true })}>
            Unresolved parent scope
          </button>
          <button type="button" className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800" onClick={() => showQueue("DIRECT_VLCODE_PARENT_MISMATCH", "MANUAL_REVIEW", { parentMismatchOnly: true })}>
            Parent mismatch
          </button>
          <button type="button" className="rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-xs font-semibold text-purple-700" onClick={() => showQueue("PARENT_SCOPED_NAME_MATCH", "MANUAL_REVIEW")}>
            Name-match review
          </button>
          <button type="button" className="rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700" onClick={() => showQueue("SPECIAL_REFERENCE_FEATURE", "BLOCKED", { specialOnly: true })}>
            Special/reference
          </button>
          <button type="button" className="rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-semibold text-green-700" onClick={() => showQueue("DIRECT_VLCODE_MATCH", "AUTO_CANDIDATE")}>
            Direct code candidates
          </button>
        </div>

        <form onSubmit={applyFilters} className="grid gap-3 md:grid-cols-4">
          <Select label="Batch" value={batchId} onChange={setBatchId} options={batches.map((batch) => ({ value: getBatchId(batch), label: `${batch.state_or_ut} / ${batch.status}` }))} />
          <Select label="Bucket" value={bucket} onChange={setBucket} options={BUCKETS.map((value) => ({ value, label: value || "All buckets" }))} />
          <Select label="Review status" value={reviewStatus} onChange={setReviewStatus} options={REVIEW_STATUSES.map((value) => ({ value, label: value || "All statuses" }))} />
          <Select label="Scope" value={scope} onChange={setScope} options={SCOPES.map((value) => ({ value, label: value || "All scopes" }))} />
          <Input label="District" value={district} onChange={setDistrict} placeholder="e.g. Hassan" />
          <Input label="Subdistrict" value={subdistrict} onChange={setSubdistrict} placeholder="e.g. Arsikere" />
          <Input label="VL code" value={vlcode} onChange={setVlcode} placeholder="e.g. 619107" />
          <div className="flex items-end gap-3">
            <button className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white hover:bg-green-800" type="submit">Apply</button>
            <button className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50" type="button" onClick={() => void loadCandidates()}>Refresh</button>
          </div>
          <Checkbox label="Special/reference only" checked={specialOnly} onChange={setSpecialOnly} />
          <Checkbox label="Unresolved only" checked={unresolvedOnly} onChange={setUnresolvedOnly} />
          <Checkbox label="Parent mismatch only" checked={parentMismatchOnly} onChange={setParentMismatchOnly} />
        </form>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <h2 className="font-semibold text-gray-900">Candidates</h2>
              <p className="text-sm text-gray-500">{loading ? "Loading…" : `${data?.total ?? 0} rows match current filters`}</p>
            </div>
            <div className="flex gap-2">
              <button disabled={!canPrev} className="rounded border px-3 py-1 text-sm disabled:opacity-40" onClick={() => setOffset(Math.max(0, offset - limit))}>Prev</button>
              <button disabled={!canNext} className="rounded border px-3 py-1 text-sm disabled:opacity-40" onClick={() => setOffset(offset + limit)}>Next</button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3">Feature</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Bucket</th>
                  <th className="px-4 py-3">Review</th>
                  <th className="px-4 py-3">Proposed LGD</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.items || []).map((row) => (
                  <tr key={row.candidate_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <button className="font-mono text-xs text-green-700 underline-offset-2 hover:underline" onClick={() => void loadDetail(row.candidate_id)}>
                        #{row.source_feature_index}
                      </button>
                      <div className="text-xs text-gray-500">{row.source_codes?.vlcode || "no vlcode"}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{row.source_names?.village || "—"}</div>
                      <div className="text-xs text-gray-500">{[row.source_names?.district, row.source_names?.subdistrict].filter(Boolean).join(" / ")}</div>
                    </td>
                    <td className="px-4 py-3"><Badge className={bucketTone(row.candidate_bucket)}>{row.candidate_bucket}</Badge></td>
                    <td className="px-4 py-3"><Badge className={statusTone(row.review_status)}>{row.review_status}</Badge></td>
                    <td className="px-4 py-3 text-xs text-gray-600">{row.proposed_village_lgd_code || "Manual scope"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="font-semibold text-gray-900">Selected candidate</h2>
            <p className="mt-1 text-sm text-gray-500">{detailLoading ? "Loading detail…" : sourceLabel(selectedCandidate)}</p>
            {selectedCandidate ? (
              <div className="mt-4 space-y-4">
                <dl className="space-y-3 text-sm">
                  <Detail label="Bucket" value={selectedCandidate.candidate_bucket} />
                  <Detail label="Confidence" value={selectedCandidate.confidence} />
                  <Detail label="Review status" value={selectedCandidate.review_status} />
                  <Detail label="Promotion status" value={selectedCandidate.promotion_status} />
                  <Detail label="Scope" value={selectedCandidate.proposed_scope} />
                  <Detail label="Active" value={String(selectedCandidate.is_active ?? false)} />
                </dl>

                <div className="rounded-lg border bg-gray-50 p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Source codes</h3>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs text-gray-700">{JSON.stringify(selectedCandidate.source_codes, null, 2)}</pre>
                </div>

                <div className="rounded-lg border bg-gray-50 p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Source names</h3>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs text-gray-700">{JSON.stringify(selectedCandidate.source_names, null, 2)}</pre>
                </div>

                {detail?.source_feature ? (
                  <div className="rounded-lg border bg-gray-50 p-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Source feature</h3>
                    <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs text-gray-700">{JSON.stringify(detail.source_feature, null, 2)}</pre>
                  </div>
                ) : null}

                {selectedMatchEvidence ? (
                  <div className="rounded-lg border bg-gray-50 p-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Match evidence</h3>
                    <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs text-gray-700">{JSON.stringify(selectedMatchEvidence, null, 2)}</pre>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <form onSubmit={submitReview} className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="font-semibold text-gray-900">Review metadata</h2>
            <p className="mt-1 text-sm text-gray-500">Updates review fields only. Promotion and runtime lookup remain unsupported.</p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button type="button" className="rounded border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50" onClick={() => chooseReviewDecision("KEEP_PENDING")}>
                Keep pending
              </button>
              <button type="button" className="rounded border border-purple-200 bg-purple-50 px-3 py-2 text-xs font-semibold text-purple-700 hover:bg-purple-100" onClick={() => chooseReviewDecision("MARK_REFERENCE_ONLY", "Marked reference-only after manual review. No runtime use approved.")}>
                Reference only
              </button>
              <button type="button" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100" onClick={() => chooseReviewDecision("REJECT_SOURCE_MISMATCH", "Rejected because source boundary candidate does not safely match the backend geography record.")}>
                Reject mismatch
              </button>
              <button type="button" className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800 hover:bg-amber-100" onClick={() => chooseReviewDecision("BLOCK_PENDING_SOURCE_REVIEW", "Blocked pending source-system or crosswalk review.")}>
                Block review
              </button>
            </div>
            <div className="mt-4 space-y-3">
              <Select label="Decision" value={reviewDecision} onChange={setReviewDecision} options={DECISIONS.map((value) => ({ value, label: value }))} />
              <p className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                Notes are required for non-pending decisions. Saving review metadata never activates geometry or changes runtime spatial matching.
              </p>
              <label className="block text-sm">
                <span className="font-medium text-gray-700">Notes</span>
                <textarea
                  className="mt-1 min-h-24 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={reviewNotes}
                  onChange={(event) => setReviewNotes(event.target.value)}
                  placeholder="Required for non-pending decisions."
                />
              </label>
              <button disabled={!selectedCandidate} className="w-full rounded bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-black disabled:opacity-40">
                Save review metadata
              </button>
            </div>
          </form>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            <strong>Governance fence:</strong> this UI can help reviewers classify rows, but it cannot activate candidates,
            promote boundaries, or change Android/runtime spatial behavior.
          </div>
        </aside>
      </section>
    </div>
  );
}

function Card({ label, value, tone }: { label: string; value: string | number; tone?: "safe" }) {
  return (
    <div className={`rounded-xl border bg-white p-5 shadow-sm ${tone === "safe" ? "border-green-200" : ""}`}>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function Badge({ children, className }: { children: string; className: string }) {
  return <span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-semibold ${className}`}>{children}</span>;
}

function Detail({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="break-words font-medium text-gray-900">{value || "—"}</dd>
    </div>
  );
}

function Input({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-gray-700">{label}</span>
      <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </label>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }> }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-gray-700">{label}</span>
      <select className="mt-1 w-full rounded border border-gray-300 px-3 py-2" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option, index) => <option key={`${option.value}-${index}`} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}
