"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { reportsApi, type SyncMaterializationHealthResponse } from "@/lib/api";

type Filters = { projectId: string; entityType: string; status: string; gapOnly: boolean };
const EMPTY_FILTERS: Filters = { projectId: "", entityType: "", status: "", gapOnly: false };

function paramValue(searchParams: Record<string, string | string[] | undefined> | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = searchParams?.[key];
    if (Array.isArray(value)) return value[0] || "";
    if (value) return value;
  }
  return "";
}

function filtersFromSearchParams(searchParams?: Record<string, string | string[] | undefined>): Filters {
  return {
    projectId: paramValue(searchParams, "projectId", "project_id"),
    entityType: paramValue(searchParams, "entityType", "entity_type"),
    status: paramValue(searchParams, "status"),
    gapOnly: paramValue(searchParams, "gapOnly", "gap_only") === "true",
  };
}

export default function SyncHealthPage({ searchParams }: { searchParams?: Record<string, string | string[] | undefined> }) {
  const [filters, setFilters] = useState<Filters>(() => filtersFromSearchParams(searchParams));
  const [appliedFilters, setAppliedFilters] = useState<Filters>(() => filtersFromSearchParams(searchParams));
  const [data, setData] = useState<SyncMaterializationHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await reportsApi.syncHealth({
        projectId: appliedFilters.projectId || undefined,
        entityType: appliedFilters.entityType || undefined,
        status: appliedFilters.status || undefined,
        gapOnly: appliedFilters.gapOnly,
        limit: 100,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sync health");
    } finally {
      setLoading(false);
    }
  }, [appliedFilters]);

  useEffect(() => {
    const browserFilters = filtersFromSearchParams(Object.fromEntries(new URLSearchParams(window.location.search).entries()));
    if (browserFilters.projectId || browserFilters.entityType || browserFilters.status || browserFilters.gapOnly) {
      setFilters(browserFilters);
      setAppliedFilters(browserFilters);
    }
    // set URL filters from browser once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { void load(); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setAppliedFilters({ ...filters });
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
  }

  async function exportCsv() {
    setExporting(true);
    setError(null);
    try {
      await reportsApi.downloadSyncHealthCsv({
        projectId: appliedFilters.projectId || undefined,
        entityType: appliedFilters.entityType || undefined,
        status: appliedFilters.status || undefined,
        gapOnly: appliedFilters.gapOnly,
        limit: 1000,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to export sync health CSV");
    } finally {
      setExporting(false);
    }
  }

  const summary = data?.summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sync Health</h1>
          <p className="mt-1 text-sm text-gray-500">Inspect mobile sync events, materialization gaps, conflicts, and audit-chain coverage.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportCsv} disabled={exporting} className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">{exporting ? "Exporting..." : "Export CSV"}</button>
          <Link href="/dashboard" className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">Dashboard</Link>
          <Link href="/conflicts" className="rounded bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-800">Open conflicts</Link>
        </div>
      </div>

      {(appliedFilters.status || appliedFilters.entityType || appliedFilters.gapOnly || appliedFilters.projectId) ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="font-semibold">Sync health drill-down active</p>
              <p className="mt-1">Showing filtered sync events from dashboard/operations context. Adjust filters below or clear them to return to all sync events.</p>
            </div>
            <Link href="/sync-health" className="shrink-0 rounded bg-white/80 px-3 py-1 text-xs font-semibold text-blue-800 hover:bg-white">Clear drill-down</Link>
          </div>
        </div>
      ) : null}

      <form onSubmit={submit} className="rounded bg-white p-5 shadow">
        <div className="grid gap-3 md:grid-cols-5">
          <label className="text-xs text-gray-500">Project ID<input value={filters.projectId} onChange={(event) => setFilters({ ...filters, projectId: event.target.value })} placeholder="Optional project UUID" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
          <label className="text-xs text-gray-500">Entity type<select value={filters.entityType} onChange={(event) => setFilters({ ...filters, entityType: event.target.value })} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">All</option><option value="FARMER">FARMER</option><option value="PARCEL">PARCEL</option><option value="PARCEL_GEOMETRY">PARCEL_GEOMETRY</option></select></label>
          <label className="text-xs text-gray-500">Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">All</option><option value="COMMITTED">COMMITTED</option><option value="FAILED">FAILED</option><option value="CONFLICT">CONFLICT</option><option value="DEPENDENCY_MISSING">DEPENDENCY_MISSING</option></select></label>
          <label className="flex items-end gap-2 rounded border p-2 text-sm text-gray-700"><input type="checkbox" checked={filters.gapOnly} onChange={(event) => setFilters({ ...filters, gapOnly: event.target.checked })} /> Gap only</label>
          <div className="flex items-end gap-2"><button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm text-white disabled:opacity-50">{loading ? "Loading..." : "Apply"}</button><button type="button" onClick={clearFilters} className="rounded border px-4 py-2 text-sm">Clear</button></div>
        </div>
      </form>

      {error ? <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {loading && !data ? <p className="text-sm text-gray-500">Loading sync health...</p> : null}

      {summary ? (
        <>
          <div className="grid gap-4 md:grid-cols-5">
            <Card label="Events" value={summary.event_count} />
            <Card label="Committed" value={summary.committed_count} />
            <Card label="Failed" value={summary.failed_count} />
            <Card label="Conflicts" value={summary.conflict_count} />
            <Card label="Audit entries" value={summary.audit_chain_count} />
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            <Card label="Farmers" value={summary.farmer_count} />
            <Card label="Parcels" value={summary.parcel_count} />
            <Card label="Geometry captured" value={summary.geometry_captured_count} />
            <Card label="Geometry missing" value={summary.geometry_missing_count} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Materialization by entity" subtitle="Committed sync events compared with operational table state.">
              <table className="w-full text-sm"><thead className="bg-gray-50"><tr>{["Entity", "Committed", "Materialized", "Gap"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead><tbody className="divide-y">{data.materialization.map((row) => <tr key={row.entity_type}><td className="p-3 font-medium">{row.entity_type}</td><td className="p-3">{row.committed_count}</td><td className="p-3">{row.materialized_count}</td><td className={row.unmaterialized_count ? "p-3 font-semibold text-red-700" : "p-3 text-green-700"}>{row.unmaterialized_count}</td></tr>)}{data.materialization.length === 0 && <Empty colSpan={4} label="No materialization rows." />}</tbody></table>
            </Panel>
            <Panel title="Status counts" subtitle="Sync event status distribution.">
              <table className="w-full text-sm"><thead className="bg-gray-50"><tr>{["Status", "Events"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead><tbody className="divide-y">{data.status_counts.map((row) => <tr key={row.status}><td className="p-3 font-medium">{row.status}</td><td className="p-3">{row.event_count}</td></tr>)}{data.status_counts.length === 0 && <Empty colSpan={2} label="No sync statuses." />}</tbody></table>
            </Panel>
          </div>

          <Panel title={appliedFilters.gapOnly ? "Unmaterialized sync gaps" : "Recent sync events"} subtitle={appliedFilters.gapOnly ? "Committed events that have not materialized into the expected operational record/state." : "Most recent events with materialization state and trace links where possible."}>
            <table className="w-full text-sm">
              <thead className="bg-gray-50"><tr>{["Processed", "Entity", "Operation", "Status", "Materialized", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
              <tbody className="divide-y">
                {data.recent_events.map((event) => <tr key={event.event_id}>
                  <td className="p-3"><div>{event.processed_at ? new Date(event.processed_at).toLocaleString() : "-"}</div><div className="font-mono text-xs text-gray-500">{event.event_id}</div></td>
                  <td className="p-3"><div>{event.entity_type}</div><div className="font-mono text-xs text-gray-500">{event.entity_id || "-"}</div></td>
                  <td className="p-3">{event.operation || "-"}</td>
                  <td className="p-3">{event.status || "-"}</td>
                  <td className="p-3">{event.materialized === null || event.materialized === undefined ? "n/a" : event.materialized ? "yes" : "no"}</td>
                  <td className="p-3">{event.trace_url ? <Link href={event.trace_url} className="text-blue-600">Trace</Link> : <span className="text-gray-400">-</span>}</td>
                </tr>)}
                {data.recent_events.length === 0 && <Empty colSpan={6} label="No recent sync events." />}
              </tbody>
            </table>
          </Panel>
        </>
      ) : null}
    </div>
  );
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="overflow-hidden rounded bg-white shadow"><div className="border-b p-5"><h2 className="text-lg font-bold text-gray-900">{title}</h2><p className="text-sm text-gray-500">{subtitle}</p></div><div className="overflow-x-auto">{children}</div></section>;
}

function Empty({ colSpan, label }: { colSpan: number; label: string }) {
  return <tr><td colSpan={colSpan} className="p-8 text-center text-gray-400">{label}</td></tr>;
}
