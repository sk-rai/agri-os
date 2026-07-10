
"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { reportsApi, type AdminDashboardResponse, type SyncMaterializationHealthResponse } from "@/lib/api";

type DashboardFilters = {
  projectId: string;
  dateFrom: string;
  dateTo: string;
};

const initialFilters: DashboardFilters = { projectId: "", dateFrom: "", dateTo: "" };

function compactQuery(params: Record<string, string | number | null | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}


function dashboardLookupHref(data: AdminDashboardResponse, params: Record<string, string | number | null | undefined> = {}) {
  return `/lookup${compactQuery({ projectId: data.filters.project_id, ...params })}`;
}

function geometryLookupHref(data: AdminDashboardResponse, geometrySource: string) {
  const source = geometrySource.toUpperCase();
  if (source === "MISSING" || source === "NONE") return dashboardLookupHref(data, { geometryStatus: "MISSING" });
  return dashboardLookupHref(data, { geometrySource: source });
}

function dashboardActivityHref(data: AdminDashboardResponse, params: Record<string, string | number | null | undefined> = {}) {
  return `/activity-usage${compactQuery({
    projectId: data.filters.project_id,
    dateFrom: data.filters.date_from,
    dateTo: data.filters.date_to,
    ...params,
  })}`;
}

function dashboardProjectTraceHref(data: AdminDashboardResponse, params: Record<string, string | number | null | undefined> = {}) {
  if (!data.filters.project_id) return "/lookup";
  return `/project-trace/${data.filters.project_id}${compactQuery({
    dateFrom: data.filters.date_from,
    dateTo: data.filters.date_to,
    ...params,
  })}`;
}

export default function DashboardPage() {
  const [data, setData] = useState<AdminDashboardResponse | null>(null);
  const [filters, setFilters] = useState(initialFilters);
  const [loading, setLoading] = useState(true);
  const [syncHealth, setSyncHealth] = useState<SyncMaterializationHealthResponse | null>(null);
  const [syncLoading, setSyncLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = (nextFilters = filters) => {
    setLoading(true);
    setError(null);
    reportsApi
      .adminDashboard({
        projectId: nextFilters.projectId.trim() || undefined,
        dateFrom: nextFilters.dateFrom || undefined,
        dateTo: nextFilters.dateTo || undefined,
        limit: 10,
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    setSyncLoading(true);
    reportsApi
      .syncHealth({ projectId: nextFilters.projectId.trim() || undefined, limit: 8 })
      .then(setSyncHealth)
      .catch((e) => setError(e.message))
      .finally(() => setSyncLoading(false));
  };

  useEffect(() => {
    loadDashboard(initialFilters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    loadDashboard(filters);
  };

  const clearFilters = () => {
    setFilters(initialFilters);
    loadDashboard(initialFilters);
  };

  if (loading && !data) return <div className="text-gray-500">Loading dashboard...</div>;
  if (error && !data) return <div className="text-red-500">Error: {error}</div>;

  const summary = data?.summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Lightweight operational summary from project, farmer, parcel, crop-cycle, and activity trace data.
          </p>
        </div>
        <Link href="/lookup" className="rounded-md border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50">
          Search records
        </Link>
      </div>

      <form onSubmit={applyFilters} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Project ID</span>
            <input
              value={filters.projectId}
              onChange={(event) => setFilters((current) => ({ ...current, projectId: event.target.value }))}
              placeholder="Optional UUID"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Activity from</span>
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(event) => setFilters((current) => ({ ...current, dateFrom: event.target.value }))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Activity to</span>
            <input
              type="date"
              value={filters.dateTo}
              onChange={(event) => setFilters((current) => ({ ...current, dateTo: event.target.value }))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <div className="flex items-end gap-2">
            <button type="submit" className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={loading}>
              {loading ? "Refreshing..." : "Apply"}
            </button>
            <button type="button" onClick={clearFilters} className="rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50">
              Clear
            </button>
          </div>
        </div>
        {error ? <p className="mt-3 text-sm text-red-600">Latest refresh failed: {error}</p> : null}
      </form>

      {summary ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Projects" value={summary.project_count} tone="blue" href={dashboardLookupHref(data)} />
            <StatCard label="Farmers" value={summary.farmer_count} tone="green" href={dashboardLookupHref(data)} />
            <StatCard label="Parcels" value={summary.parcel_count} tone="indigo" href={dashboardLookupHref(data)} />
            <StatCard label="Crop cycles" value={summary.crop_cycle_count} tone="purple" href={dashboardProjectTraceHref(data)} />
            <StatCard label="Active cycles" value={summary.active_cycle_count} tone="yellow" href={dashboardProjectTraceHref(data, { cycleStatus: "ACTIVE" })} />
            <StatCard label="Completed cycles" value={summary.completed_cycle_count} tone="green" href={dashboardProjectTraceHref(data, { cycleStatus: "COMPLETED" })} />
            <StatCard label="Activities" value={summary.activity_count} tone="blue" href={dashboardActivityHref(data)} />
            <StatCard label="Activity cost" value={`INR ${summary.total_cost}`} tone="slate" href={dashboardActivityHref(data)} />
          </div>

          <SyncHealthPanel data={syncHealth} loading={syncLoading} />

          <div className="grid gap-4 lg:grid-cols-3">
            <SummaryList title="Crop distribution" empty="No crop cycles yet" rows={data.crop_distribution.map((row) => ({ label: row.crop_code, value: row.crop_cycle_count, href: data.filters.project_id ? dashboardProjectTraceHref(data, { cropCode: row.crop_code }) : dashboardActivityHref(data, { cropCode: row.crop_code }) }))} />
            <SummaryList title="Geometry coverage" empty="No parcels yet" rows={data.geometry_coverage.map((row) => ({ label: row.geometry_source, value: row.parcel_count, href: geometryLookupHref(data, row.geometry_source) }))} />
            <SummaryList title="Activity types" empty="No activities yet" rows={data.activity_count_by_type.map((row) => ({ label: row.activity_type, value: row.activity_count, href: dashboardActivityHref(data, { activityType: row.activity_type }) }))} />
          </div>

          <RecentProjects data={data} />
          <RecentFarmers data={data} />
          <RecentParcels data={data} />
          <RecentActivities data={data} />
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, tone, href }: { label: string; value: string | number; tone: "blue" | "green" | "indigo" | "purple" | "yellow" | "slate"; href?: string }) {
  const toneMap = {
    blue: "border-blue-200 bg-blue-50 text-blue-800",
    green: "border-green-200 bg-green-50 text-green-800",
    indigo: "border-indigo-200 bg-indigo-50 text-indigo-800",
    purple: "border-purple-200 bg-purple-50 text-purple-800",
    yellow: "border-yellow-200 bg-yellow-50 text-yellow-800",
    slate: "border-slate-200 bg-slate-50 text-slate-800",
  };
  const content = (
    <>
      <p className="text-sm opacity-80">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
      {href ? <p className="mt-2 text-xs font-medium opacity-75">Open drill-down</p> : null}
    </>
  );
  const className = `rounded-lg border p-4 shadow-sm transition ${toneMap[tone]} ${href ? "hover:-translate-y-0.5 hover:shadow-md" : ""}`;
  return href ? <Link href={href} className={className}>{content}</Link> : <div className={className}>{content}</div>;
}

function SummaryList({ title, rows, empty }: { title: string; rows: Array<{ label: string; value: number; href?: string }>; empty: string }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      {rows.length === 0 ? <p className="mt-3 text-sm text-gray-500">{empty}</p> : null}
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <Link key={row.label} href={row.href || "#"} className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm hover:bg-blue-50">
            <span className="font-medium text-gray-700">{row.label}</span>
            <span className="text-gray-900">{row.value}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function RecentProjects({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent projects" empty="No projects found">
      {data.projects.map((project) => (
        <tr key={project.id}>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={project.trace_url}>{project.name}</Link></td>
          <td className="px-3 py-2">{project.status || "-"}</td>
          <td className="px-3 py-2">{project.crop_scope.join(", ") || "-"}</td>
          <td className="px-3 py-2 text-right">{project.crop_cycle_count}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function RecentFarmers({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent farmers" empty="No farmers found">
      {data.farmers.map((farmer) => (
        <tr key={farmer.id}>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={farmer.trace_url}>{farmer.label}</Link></td>
          <td className="px-3 py-2">{farmer.mobile_number || "-"}</td>
          <td className="px-3 py-2">{farmer.village_name || "-"}</td>
          <td className="px-3 py-2 text-right">{farmer.activity_count}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function RecentParcels({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent parcels" empty="No parcels found">
      {data.parcels.map((parcel) => (
        <tr key={parcel.id}>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={parcel.trace_url}>{parcel.label}</Link></td>
          <td className="px-3 py-2">{parcel.farmer_name || "-"}</td>
          <td className="px-3 py-2">{parcel.geometry_source || "MISSING"}</td>
          <td className="px-3 py-2 text-right">{parcel.crop_cycle_count}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function RecentActivities({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent activities" empty="No activities found">
      {data.activities.map((activity) => (
        <tr key={activity.activity_id}>
          <td className="px-3 py-2">{activity.activity_date || "-"}</td>
          <td className="px-3 py-2">{activity.farmer_name || "-"}</td>
          <td className="px-3 py-2">{activity.crop_code} / {activity.stage_code || "-"}</td>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={dashboardActivityHref(data, { activityType: activity.activity_type })}>{activity.activity_type}</Link></td>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={dashboardActivityHref(data, { inputCode: activity.input_code })}>{activity.input_name || activity.input_code || "-"}</Link></td>
          <td className="px-3 py-2 text-right">{activity.cost_amount ? `INR ${activity.cost_amount}` : "-"}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function TableSection({ title, empty, children }: { title: string; empty: string; children: React.ReactNode }) {
  const hasRows = Array.isArray(children) ? children.length > 0 : Boolean(children);
  return (
    <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      </div>
      {!hasRows ? <p className="p-4 text-sm text-gray-500">{empty}</p> : null}
      {hasRows ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <tbody className="divide-y divide-gray-100">{children}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}


function SyncHealthPanel({ data, loading }: { data: SyncMaterializationHealthResponse | null; loading: boolean }) {
  const summary = data?.summary;
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Sync & materialization health</h2>
          <p className="text-sm text-gray-500">Accepted mobile events compared with operational farmer, parcel, and geometry rows.</p>
        </div>
        <Link href="/conflicts" className="text-sm font-medium text-blue-700 hover:underline">Open conflicts</Link>
      </div>
      {loading && !data ? <p className="mt-4 text-sm text-gray-500">Loading sync health...</p> : null}
      {summary ? (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-5">
            <MiniStat label="Committed" value={summary.committed_count} />
            <MiniStat label="Failed" value={summary.failed_count} />
            <MiniStat label="Conflicts" value={summary.conflict_count} />
            <MiniStat label="Dependency missing" value={summary.dependency_missing_count} />
            <MiniStat label="Audit entries" value={summary.audit_chain_count} />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="overflow-hidden rounded-md border border-gray-100">
              <table className="min-w-full divide-y divide-gray-100 text-sm">
                <thead className="bg-gray-50"><tr>{["Entity", "Committed", "Materialized", "Gap"].map((head) => <th key={head} className="px-3 py-2 text-left font-medium text-gray-600">{head}</th>)}</tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {data.materialization.map((row) => (
                    <tr key={row.entity_type}>
                      <td className="px-3 py-2 font-medium text-gray-800">{row.entity_type}</td>
                      <td className="px-3 py-2">{row.committed_count}</td>
                      <td className="px-3 py-2">{row.materialized_count}</td>
                      <td className={row.unmaterialized_count ? "px-3 py-2 font-semibold text-red-700" : "px-3 py-2 text-green-700"}>{row.unmaterialized_count}</td>
                    </tr>
                  ))}
                  {data.materialization.length === 0 ? <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-400">No sync events yet.</td></tr> : null}
                </tbody>
              </table>
            </div>
            <div className="overflow-hidden rounded-md border border-gray-100">
              <table className="min-w-full divide-y divide-gray-100 text-sm">
                <thead className="bg-gray-50"><tr>{["Event", "Entity", "Status", "Materialized"].map((head) => <th key={head} className="px-3 py-2 text-left font-medium text-gray-600">{head}</th>)}</tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {data.recent_events.map((event) => (
                    <tr key={event.event_id}>
                      <td className="px-3 py-2 font-mono text-xs text-gray-600">{event.processed_at || event.event_id.slice(0, 8)}</td>
                      <td className="px-3 py-2">{event.trace_url ? <Link className="text-blue-700 hover:underline" href={event.trace_url}>{event.entity_type}</Link> : event.entity_type}</td>
                      <td className="px-3 py-2">{event.status || "-"}</td>
                      <td className="px-3 py-2">{event.materialized === null || event.materialized === undefined ? "n/a" : event.materialized ? "yes" : "no"}</td>
                    </tr>
                  ))}
                  {data.recent_events.length === 0 ? <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-400">No recent sync events.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return <div className="rounded-md bg-gray-50 px-3 py-2"><p className="text-xs text-gray-500">{label}</p><p className="text-xl font-bold text-gray-900">{value}</p></div>;
}
