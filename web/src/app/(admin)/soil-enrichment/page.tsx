"use client";

import { useEffect, useState } from "react";
import { farmersApi, SoilEnrichmentOperationsHealthResponse, SoilEnrichmentQueueResponse } from "@/lib/api";

const MISSING_FILTERS = ["", "ANY", "BASELINE", "MOISTURE"];

export default function SoilEnrichmentPage() {
  const [missing, setMissing] = useState("ANY");
  const [data, setData] = useState<SoilEnrichmentQueueResponse | null>(null);
  const [health, setHealth] = useState<SoilEnrichmentOperationsHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadQueue() {
    setLoading(true);
    setError(null);
    try {
      const [nextQueue, nextHealth] = await Promise.all([
        farmersApi.soilEnrichmentQueue({ missing: missing || undefined, limit: 100 }),
        farmersApi.soilEnrichmentOperationsHealth(),
      ]);
      setData(nextQueue);
      setHealth(nextHealth);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load soil enrichment queue");
    } finally {
      setLoading(false);
    }
  }

  async function recordAudit(item: SoilEnrichmentQueueResponse["items"][number], jobType: string, status: "SKIPPED" | "DEFERRED" | "FAILED") {
    const reason = window.prompt(`Reason for ${status} ${jobType}?`, status === "FAILED" ? "Manual admin failure marker" : "Manual admin queue decision");
    if (reason === null) return;
    setLoading(true);
    setError(null);
    try {
      await farmersApi.createSoilEnrichmentJobAudit({
        farmer_id: item.farmer.id,
        parcel_id: item.parcel.id,
        project_id: item.parcel.project_id,
        job_type: jobType,
        status,
        attempt_count: 1,
        reason,
        error_code: status === "FAILED" ? "MANUAL_ADMIN_MARKER" : undefined,
        metadata: { source: "admin_soil_enrichment_queue" },
      });
      await loadQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record audit event");
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missing]);

  return <main className="p-6">
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Soil enrichment queue</h1>
        <p className="mt-1 text-sm text-gray-500">Read-only operational queue for SoilGrids, SHC/SLUSI, Open-Meteo, and future satellite workers.</p>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-sm text-gray-600">Missing</label>
        <select value={missing} onChange={(event) => setMissing(event.target.value)} className="rounded border px-3 py-2 text-sm">
          {MISSING_FILTERS.map((value) => <option key={value || "ALL"} value={value}>{value || "ALL"}</option>)}
        </select>
        <button type="button" onClick={() => void loadQueue()} disabled={loading} className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{loading ? "Loading..." : "Refresh"}</button>
      </div>
    </div>

    {error ? <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

    {health ? <section className="mb-4 rounded border bg-white p-4">
      <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Operations health</h2>
          <p className="text-xs text-gray-500">Backend-wide soil enrichment readiness, snapshot, and job-audit health.</p>
        </div>
        <div className="text-xs text-gray-400">Generated {new Date(health.generated_at).toLocaleString()}</div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-5">
        <MiniStat label="Location ready" value={health.summary.location_ready_parcel_count} />
        <MiniStat label="Missing baseline" value={health.summary.missing_baseline_count} />
        <MiniStat label="Missing moisture" value={health.summary.missing_moisture_count} />
        <MiniStat label="Failed jobs" value={health.summary.failed_job_audit_count} />
        <MiniStat label="Deferred jobs" value={health.summary.deferred_job_audit_count} />
      </div>
      {health.recommended_actions.length ? <div className="mt-3 rounded border border-amber-100 bg-amber-50 p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-amber-900">Recommended actions</div>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-900">
          {health.recommended_actions.map((action) => <li key={action}>{action}</li>)}
        </ul>
      </div> : <div className="mt-3 rounded border border-green-100 bg-green-50 p-3 text-xs text-green-800">No immediate soil enrichment operations action flagged.</div>}
      <div className="mt-3 grid gap-3 text-xs md:grid-cols-3">
        <Breakdown title="Snapshot providers" values={health.provider_counts} />
        <Breakdown title="Audit statuses" values={health.audit_status_counts} />
        <Breakdown title="Audit job types" values={health.audit_job_type_counts} />
      </div>
    </section> : null}

    {data ? <div className="mb-4 grid gap-3 md:grid-cols-5">
      <MiniStat label="Queue items" value={data.count} />
      <MiniStat label="Missing baseline" value={data.reason_counts.MISSING_BASELINE || 0} />
      <MiniStat label="Missing moisture" value={data.reason_counts.MISSING_MOISTURE || 0} />
      <MiniStat label="Baseline jobs" value={data.reason_counts.READY_FOR_BASELINE_FETCH || 0} />
      <MiniStat label="Moisture jobs" value={data.reason_counts.READY_FOR_MOISTURE_FETCH || 0} />
    </div> : null}

    <div className="overflow-hidden rounded border bg-white">
      <div className="border-b bg-gray-50 p-3 text-sm font-medium text-gray-700">Queue rows</div>
      <div className="divide-y">
        {data?.items.map((item) => <div key={item.parcel.id} className="grid gap-3 p-4 text-sm lg:grid-cols-[1.2fr_1.2fr_1fr_1.4fr]">
          <div>
            <div className="font-semibold text-gray-900">{item.farmer.display_name || "Unnamed farmer"}</div>
            <div className="mt-1 text-xs text-gray-500">{item.farmer.mobile_number || "-"} · {item.farmer.village_name_manual || item.farmer.pin_code || "-"}</div>
            <div className="mt-1 break-all font-mono text-[11px] text-gray-400">{item.farmer.id}</div>
          </div>
          <div>
            <div className="font-medium text-gray-800">Parcel {item.parcel.id.slice(0, 8)}</div>
            <div className="mt-1 text-xs text-gray-500">{item.parcel.village_name_manual || item.parcel.pin_code || "-"} · {item.parcel.geometry_source || "-"}</div>
            <div className="mt-1 text-xs text-gray-500">Centroid: {item.parcel.has_centroid ? "yes" : "no"}</div>
          </div>
          <div>
            <div className="flex flex-wrap gap-1">
              {item.reasons.map((reason) => <span key={reason} className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">{reason}</span>)}
            </div>
            <div className="mt-2 text-xs text-gray-500">Baseline: {item.snapshot_counts.baseline || 0} · Moisture: {item.snapshot_counts.moisture || 0}</div>
          </div>
          <div>
            {item.recommended_jobs.length ? <div className="space-y-2">
              {item.recommended_jobs.map((job) => {
                const audit = item.latest_audit_by_job[job];
                return <div key={job} className="rounded border bg-gray-50 p-2 text-xs">
                  <div className="font-semibold text-gray-800">{job}</div>
                  {audit ? <div className="mt-1 text-gray-600">Latest: {audit.status} · {audit.provider || "-"} · attempts {audit.attempt_count}</div> : <div className="mt-1 text-gray-400">No attempts recorded</div>}
                  {audit?.error_code ? <div className="mt-1 text-red-700">{audit.error_code}</div> : null}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(["SKIPPED", "DEFERRED", "FAILED"] as const).map((status) => <button key={status} type="button" onClick={() => void recordAudit(item, job, status)} className="rounded border bg-white px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-100">{status}</button>)}
                  </div>
                </div>;
              })}
            </div> : <span className="text-xs text-green-700">No backend jobs recommended</span>}
          </div>
        </div>)}
        {data && data.items.length === 0 ? <div className="p-8 text-center text-sm text-gray-400">No queue items for current filter.</div> : null}
        {!data && !loading ? <div className="p-8 text-center text-sm text-gray-400">Load queue to begin.</div> : null}
      </div>
    </div>
  </main>;
}

function Breakdown({ title, values }: { title: string; values: Record<string, number> }) {
  const entries = Object.entries(values || {}).filter(([, value]) => value > 0);
  return <div className="rounded border bg-gray-50 p-3">
    <div className="font-semibold text-gray-700">{title}</div>
    {entries.length ? <div className="mt-2 space-y-1">{entries.map(([key, value]) => <div key={key} className="flex justify-between gap-3 text-gray-600"><span>{key}</span><span className="font-medium text-gray-900">{value}</span></div>)}</div> : <div className="mt-2 text-gray-400">No rows</div>}
  </div>;
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return <div className="rounded border bg-white p-3">
    <div className="text-xs text-gray-500">{label}</div>
    <div className="mt-1 text-xl font-semibold text-gray-900">{value}</div>
  </div>;
}
