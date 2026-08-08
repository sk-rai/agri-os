"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type ReviewRow = {
  poly_mapping_id: string;
  poly_region_id: string;
  state_lgd_code: string;
  state_name: string;
  district_lgd_code: string;
  district_name: string;
  poly_region_system: string;
  poly_region_code: string;
  poly_region_name: string;
  poly_region_class_code?: string | null;
  poly_region_class_name?: string | null;
  overlap_percent_of_district?: number | string | null;
  crosswalk_category?: string | null;
  low_overlap_bucket?: string | null;
  active_fallback_count?: number | null;
  active_fallback_region_codes?: string | null;
  active_fallback_region_names?: string | null;
  active_fallback_region_systems?: string | null;
  active_fallback_confidences?: string | null;
  promotion_decision: string;
  poly_review_status: string;
};

type ReviewResponse = {
  schema_version: string;
  mode: string;
  filters: Record<string, string | null>;
  summary: {
    total: number;
    offset: number;
    limit: number;
    land_intelligence_behavior_changed: boolean;
    source_confidence: string;
    source_rows_active: boolean;
  };
  decision_counts: Array<{ promotion_decision: string; count: number }>;
  state_counts: Array<{ state_lgd_code: string; state_name: string; count: number }>;
  region_system_counts: Array<{ region_system: string; count: number }>;
  items: ReviewRow[];
  total: number;
  offset: number;
  limit: number;
  governance: {
    read_only: boolean;
    promotion_supported: boolean;
    promotion_requires_separate_review_workflow: boolean;
    android_maestro_required: boolean;
  };
};

type ReviewSummaryResponse = {
  schema_version: string;
  active_promoted: {
    mapping_rows: number;
    districts: number;
    states: number;
    region_codes: number;
    by_state: Array<{
      state_lgd_code: string;
      state_name: string;
      active_districts: number;
      active_mapping_rows: number;
    }>;
  };
  inactive_review_queue: {
    mapping_rows: number;
    districts: number;
    review_status_counts: Array<{
      review_status: string;
      mapping_rows: number;
      districts: number;
    }>;
  };
  fallbacks: {
    active_fallback_rows: number;
    inactive_superseded_fallback_rows: number;
  };
  readiness: {
    safe_read_only: boolean;
    active_promoted_rows_present: boolean;
    manual_review_queue_present: boolean;
  };
};


const DECISIONS = [
  "",
  "PILOT_REVIEW_REPLACES_FALLBACK",
  "GENERAL_REVIEW_REPLACES_FALLBACK",
  "GENERAL_REVIEW_NEW_MAPPING",
  "MANUAL_REVIEW_LOW_OVERLAP",
  "BLOCKED_CROSSWALK",
  "BLOCKED_SOURCE_VERSION",
];

const REVIEW_STATUSES = ["", "MANUAL_REVIEW", "APPROVED_FOR_PROMOTION", "REJECTED"];

const HELD_LOW_MARGIN_FILTER = {
  stateCode: "29",
  reviewStatus: "APPROVED_FOR_PROMOTION",
  decision: "",
  districtCodes: ["531", "535"],
};



const REGION_SYSTEMS = [
  "",
  "CORE_STACK_AGRO_CLIMATIC_ZONE",
  "CORE_STACK_AGRO_ECOLOGICAL_ZONE",
  "CORE_STACK_BIOGEOGRAPHIC_ZONE",
];

const STATES = [
  { code: "", label: "All states" },
  { code: "29", label: "Karnataka" },
  { code: "27", label: "Maharashtra" },
  { code: "3", label: "Punjab" },
];

function formatPercent(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${numeric.toFixed(1)}%`;
}

function decisionTone(decision: string) {
  if (decision.startsWith("PILOT")) return "bg-green-50 text-green-700 border-green-200";
  if (decision.startsWith("BLOCKED")) return "bg-red-50 text-red-700 border-red-200";
  if (decision.includes("LOW_OVERLAP")) return "bg-amber-50 text-amber-800 border-amber-200";
  return "bg-blue-50 text-blue-700 border-blue-200";
}

export default function CoreLgdReviewPage() {
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [summaryData, setSummaryData] = useState<ReviewSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [stateCode, setStateCode] = useState("29");
  const [districtCode, setDistrictCode] = useState("");
  const [regionSystem, setRegionSystem] = useState("");
  const [decision, setDecision] = useState("PILOT_REVIEW_REPLACES_FALLBACK");
  const [search, setSearch] = useState("");
  const [reviewStatus, setReviewStatus] = useState("MANUAL_REVIEW");
  const [message, setMessage] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const limit = 100;

  const queryPath = useMemo(() => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (stateCode) params.set("state_lgd_code", stateCode);
    if (districtCode.trim()) params.set("district_lgd_code", districtCode.trim());
    if (regionSystem) params.set("region_system", regionSystem);
    if (decision) params.set("promotion_decision", decision);
    if (reviewStatus) params.set("review_status", reviewStatus);
    if (search.trim()) params.set("search", search.trim());
    return `/api/v1/master-data/geography/core-lgd-mapping-review?${params.toString()}`;
  }, [decision, districtCode, offset, regionSystem, reviewStatus, search, stateCode]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api<ReviewResponse>(queryPath));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CoRE/LGD review queue");
    } finally {
      setLoading(false);
    }
  }, [queryPath]);

  const loadSummary = useCallback(async () => {
    try {
      setSummaryData(
        await api<ReviewSummaryResponse>(
          "/api/v1/master-data/geography/core-lgd-mapping-review/summary",
        ),
      );
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => { void loadSummary(); }, [loadSummary]);

  useEffect(() => { void load(); }, [load]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    void load();
  }

  function showHeldLowMargin() {
    setStateCode(HELD_LOW_MARGIN_FILTER.stateCode);
    setReviewStatus(HELD_LOW_MARGIN_FILTER.reviewStatus);
    setDecision(HELD_LOW_MARGIN_FILTER.decision);
    setDistrictCode("");
    setRegionSystem("");
    setSearch("");
    setOffset(0);
  }

  function isHeldLowMargin(row: ReviewRow) {
    return (
      row.state_lgd_code === HELD_LOW_MARGIN_FILTER.stateCode &&
      HELD_LOW_MARGIN_FILTER.districtCodes.includes(row.district_lgd_code) &&
      row.poly_review_status === HELD_LOW_MARGIN_FILTER.reviewStatus
    );
  }

  async function setRowReviewStatus(row: ReviewRow, status: "APPROVED_FOR_PROMOTION" | "REJECTED" | "MANUAL_REVIEW") {
    setError(null);
    setMessage(null);
    try {
      await api(`/api/v1/master-data/geography/core-lgd-mapping-review/${row.poly_mapping_id}/review`, {
        method: "PATCH",
        body: {
          review_status: status,
          review_notes: `Admin review decision from CoRE LGD review UI: ${status}`,
        },
      });
      setMessage(`Updated ${row.district_name} / ${row.poly_region_system} to ${status}. No mapping was activated.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update review decision");
    }
  }


  const canPrev = offset > 0;
  const canNext = data ? offset + limit < data.total : false;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-green-700">Reference data review</p>
        <h1 className="text-2xl font-bold text-gray-900">CoRE / LGD Mapping Review</h1>
        <p className="mt-2 max-w-4xl text-sm text-gray-600">
          Review inactive polygon-derived CoRE/LGD district mapping candidates against current fallback mappings.
          This surface is read-only: no row is promoted, activated, or used by land intelligence from here.
        </p>
      </div>

      {error ? <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {message ? <div className="rounded border border-green-200 bg-green-50 p-4 text-sm text-green-700">{message}</div> : null}

      <section className="grid gap-4 md:grid-cols-4">
        <Card label="Active promoted districts" value={summaryData?.active_promoted.districts ?? "—"} />
        <Card label="Active promoted rows" value={summaryData?.active_promoted.mapping_rows ?? "—"} />
        <Card label="Manual-review districts" value={summaryData?.inactive_review_queue.districts ?? "—"} />
        <Card label="Active fallback rows" value={summaryData?.fallbacks.active_fallback_rows ?? "—"} />
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <Card label="Rows matching filters" value={data?.total ?? "—"} />
        <Card label="Shown" value={data?.items.length ?? "—"} />
        <Card label="Source" value={data?.summary.source_confidence ?? "POLY_REV"} />
        <Card label="Behavior changed" value={data?.summary.land_intelligence_behavior_changed ? "Yes" : "No"} />
      </section>

      <form onSubmit={applyFilters} className="rounded-lg border bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={showHeldLowMargin}
            className="rounded-full border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-100"
          >
            Held low-margin
          </button>
        </div>
        <div className="grid gap-3 md:grid-cols-6">
          <label className="space-y-1 text-xs text-gray-500">
            State
            <select value={stateCode} onChange={(event) => setStateCode(event.target.value)} className="w-full rounded border p-2 text-sm text-gray-900">
              {STATES.map((state) => <option key={state.code} value={state.code}>{state.label}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-xs text-gray-500">
            District LGD
            <input value={districtCode} onChange={(event) => setDistrictCode(event.target.value)} className="w-full rounded border p-2 text-sm text-gray-900" placeholder="Optional" />
          </label>
          <label className="space-y-1 text-xs text-gray-500">
            Region system
            <select value={regionSystem} onChange={(event) => setRegionSystem(event.target.value)} className="w-full rounded border p-2 text-sm text-gray-900">
              {REGION_SYSTEMS.map((item) => <option key={item} value={item}>{item || "All systems"}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-xs text-gray-500">
            Decision
            <select value={decision} onChange={(event) => setDecision(event.target.value)} className="w-full rounded border p-2 text-sm text-gray-900">
              {DECISIONS.map((item) => <option key={item} value={item}>{item || "All decisions"}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-xs text-gray-500">
            Review status
            <select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)} className="w-full rounded border p-2 text-sm text-gray-900">
              {REVIEW_STATUSES.map((item) => <option key={item} value={item}>{item || "All statuses"}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-xs text-gray-500">
            Search
            <input value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded border p-2 text-sm text-gray-900" placeholder="District / region" />
          </label>
          <div className="flex items-end gap-2">
            <button disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm text-white disabled:opacity-50">{loading ? "Loading…" : "Apply"}</button>
            <button type="button" onClick={() => { setStateCode(""); setDistrictCode(""); setRegionSystem(""); setDecision(""); setReviewStatus(""); setSearch(""); setOffset(0); }} className="rounded border px-4 py-2 text-sm">Clear</button>
          </div>
        </div>
      </form>

      {data ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <Panel title="Decision buckets">
            {data.decision_counts.map((row) => (
              <CountRow key={row.promotion_decision} label={row.promotion_decision} value={row.count} />
            ))}
          </Panel>
          <Panel title="States">
            {data.state_counts.slice(0, 12).map((row) => (
              <CountRow key={`${row.state_lgd_code}-${row.state_name}`} label={`${row.state_name} (${row.state_lgd_code})`} value={row.count} />
            ))}
          </Panel>
          <Panel title="Region systems">
            {data.region_system_counts.map((row) => (
              <CountRow key={row.region_system} label={row.region_system} value={row.count} />
            ))}
          </Panel>
        </div>
      ) : null}

      <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
        <div className="flex items-center justify-between border-b p-5">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Review rows</h2>
            <p className="text-sm text-gray-500">Fallback is shown at district level; CoRE candidates are shown per region system.</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <button disabled={!canPrev || loading} onClick={() => setOffset(Math.max(0, offset - limit))} className="rounded border px-3 py-1 disabled:opacity-40">Prev</button>
            <span className="text-gray-500">{offset + 1}-{Math.min(offset + limit, data?.total ?? 0)}</span>
            <button disabled={!canNext || loading} onClick={() => setOffset(offset + limit)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1200px] text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="p-3">District</th>
                <th className="p-3">Decision</th>
                <th className="p-3">CoRE candidate</th>
                <th className="p-3">Overlap</th>
                <th className="p-3">Fallback</th>
                <th className="p-3">Source flags</th>
                <th className="p-3">Review action</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.map((row) => (
                <tr key={row.poly_mapping_id} className="align-top">
                  <td className="p-3">
                    <div className="font-medium text-gray-900">{row.district_name}</div>
                    <div className="text-xs text-gray-500">{row.state_name} · {row.state_lgd_code}/{row.district_lgd_code}</div>
                  </td>
                  <td className="p-3">
                    <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-semibold ${decisionTone(row.promotion_decision)}`}>
                      {row.promotion_decision}
                    </span>
                  </td>
                  <td className="p-3">
                    <div className="font-medium text-gray-900">{row.poly_region_name}</div>
                    <div className="text-xs text-gray-500">{row.poly_region_system}</div>
                    <div className="mt-1 font-mono text-[11px] text-gray-400">{row.poly_region_code}</div>
                  </td>
                  <td className="p-3 font-semibold text-gray-900">{formatPercent(row.overlap_percent_of_district)}</td>
                  <td className="p-3">
                    <div className="text-gray-900">{row.active_fallback_region_names || "—"}</div>
                    <div className="text-xs text-gray-500">{row.active_fallback_region_systems || "No active fallback"}</div>
                    <div className="mt-1 font-mono text-[11px] text-gray-400">{row.active_fallback_region_codes || ""}</div>
                  </td>
                  <td className="p-3">
                    <div>Status: {row.poly_review_status || "—"}</div>
                    <div>Crosswalk: {row.crosswalk_category || "—"}</div>
                    <div>Overlap bucket: {row.low_overlap_bucket || "—"}</div>
                      {isHeldLowMargin(row) ? (
                        <div className="mt-1 inline-flex rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-900">
                          Low-margin hold
                        </div>
                      ) : null}
                  </td>
                  <td className="p-3">
                    <div className="flex flex-col gap-2">
                      <button
                        type="button"
                        onClick={() => void setRowReviewStatus(row, "APPROVED_FOR_PROMOTION")}
                        disabled={row.poly_review_status === "APPROVED_FOR_PROMOTION"}
                        className="rounded bg-green-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-40"
                      >
                        Approve for promotion
                      </button>
                      <button
                        type="button"
                        onClick={() => void setRowReviewStatus(row, "REJECTED")}
                        disabled={row.poly_review_status === "REJECTED"}
                        className="rounded border border-red-200 px-3 py-1 text-xs font-semibold text-red-700 disabled:opacity-40"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => void setRowReviewStatus(row, "MANUAL_REVIEW")}
                        disabled={row.poly_review_status === "MANUAL_REVIEW"}
                        className="rounded border px-3 py-1 text-xs font-semibold text-gray-700 disabled:opacity-40"
                      >
                        Return to review
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && data?.items.length === 0 ? (
                <tr><td colSpan={7} className="p-8 text-center text-gray-400">No review rows match these filters.</td></tr>
              ) : null}
              {loading ? (
                <tr><td colSpan={7} className="p-8 text-center text-gray-400">Loading review rows…</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-lg border bg-white p-4 shadow-sm"><p className="text-xs uppercase text-gray-500">{label}</p><p className="mt-1 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-lg border bg-white p-5 shadow-sm"><h2 className="mb-3 text-sm font-semibold text-gray-900">{title}</h2><div className="space-y-2">{children}</div></section>;
}

function CountRow({ label, value }: { label: string; value: number }) {
  return <div className="flex items-center justify-between gap-3 text-sm"><span className="truncate text-gray-600">{label}</span><span className="font-semibold text-gray-900">{value}</span></div>;
}
