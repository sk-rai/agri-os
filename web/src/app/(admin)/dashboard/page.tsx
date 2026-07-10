
"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { reportsApi, type AdminDashboardResponse } from "@/lib/api";

type DashboardFilters = {
  projectId: string;
  dateFrom: string;
  dateTo: string;
};

const initialFilters: DashboardFilters = { projectId: "", dateFrom: "", dateTo: "" };

export default function DashboardPage() {
  const [data, setData] = useState<AdminDashboardResponse | null>(null);
  const [filters, setFilters] = useState(initialFilters);
  const [loading, setLoading] = useState(true);
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
            <StatCard label="Projects" value={summary.project_count} tone="blue" />
            <StatCard label="Farmers" value={summary.farmer_count} tone="green" />
            <StatCard label="Parcels" value={summary.parcel_count} tone="indigo" />
            <StatCard label="Crop cycles" value={summary.crop_cycle_count} tone="purple" />
            <StatCard label="Active cycles" value={summary.active_cycle_count} tone="yellow" />
            <StatCard label="Completed cycles" value={summary.completed_cycle_count} tone="green" />
            <StatCard label="Activities" value={summary.activity_count} tone="blue" />
            <StatCard label="Activity cost" value={`?${summary.total_cost}`} tone="slate" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <SummaryList title="Crop distribution" empty="No crop cycles yet" rows={data.crop_distribution.map((row) => ({ label: row.crop_code, value: row.crop_cycle_count }))} />
            <SummaryList title="Geometry coverage" empty="No parcels yet" rows={data.geometry_coverage.map((row) => ({ label: row.geometry_source, value: row.parcel_count }))} />
            <SummaryList title="Activity types" empty="No activities yet" rows={data.activity_count_by_type.map((row) => ({ label: row.activity_type, value: row.activity_count }))} />
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

function StatCard({ label, value, tone }: { label: string; value: string | number; tone: "blue" | "green" | "indigo" | "purple" | "yellow" | "slate" }) {
  const toneMap = {
    blue: "border-blue-200 bg-blue-50 text-blue-800",
    green: "border-green-200 bg-green-50 text-green-800",
    indigo: "border-indigo-200 bg-indigo-50 text-indigo-800",
    purple: "border-purple-200 bg-purple-50 text-purple-800",
    yellow: "border-yellow-200 bg-yellow-50 text-yellow-800",
    slate: "border-slate-200 bg-slate-50 text-slate-800",
  };
  return (
    <div className={`rounded-lg border p-4 shadow-sm ${toneMap[tone]}`}>
      <p className="text-sm opacity-80">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}

function SummaryList({ title, rows, empty }: { title: string; rows: Array<{ label: string; value: number }>; empty: string }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      {rows.length === 0 ? <p className="mt-3 text-sm text-gray-500">{empty}</p> : null}
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm">
            <span className="font-medium text-gray-700">{row.label}</span>
            <span className="text-gray-900">{row.value}</span>
          </div>
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
          <td className="px-3 py-2">{activity.activity_type}</td>
          <td className="px-3 py-2">{activity.input_name || activity.input_code || "-"}</td>
          <td className="px-3 py-2 text-right">{activity.cost_amount ? `?${activity.cost_amount}` : "-"}</td>
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
