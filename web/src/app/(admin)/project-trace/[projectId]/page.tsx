"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type ProjectTraceResponse } from "@/lib/api";

export default function ProjectTracePage({ params }: { params: { projectId: string } }) {
  const [trace, setTrace] = useState<ProjectTraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .projectTrace(params.projectId, 25)
      .then(setTrace)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load project trace"))
      .finally(() => setLoading(false));
  }, [params.projectId]);

  if (loading) return <div className="text-gray-500">Loading project trace...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!trace) return <div className="text-gray-500">No project trace found.</div>;

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href="/lookup" className="text-sm text-blue-600">&lt; Back to Lookup</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Project Trace</h1>
        <p className="mt-1 text-sm text-gray-500">{trace.project.name} ? {trace.project.status || "-"}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{trace.project.id}</div>
        <div className="mt-1"><Link href={`/project-compliance/${trace.project.id}`} className="text-blue-600">Open input compliance</Link></div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Farmers" value={trace.summary.farmer_count} />
      <Card label="Parcels" value={trace.summary.parcel_count} />
      <Card label="Crop cycles" value={trace.summary.crop_cycle_count} />
      <Card label="Activities" value={trace.summary.activity_count} />
      <Card label="Active cycles" value={trace.summary.active_cycle_count} />
      <Card label="Completed cycles" value={trace.summary.completed_cycle_count} />
      <Card label="Total cost" value={`INR ${trace.summary.total_cost}`} />
      <Card label="Variances" value={trace.summary.variance_count} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-3">
      <SummaryList title="Crop distribution" rows={trace.crop_distribution.map((row) => `${row.crop_code}: ${row.crop_cycle_count} cycles`)} />
      <SummaryList title="Geometry coverage" rows={trace.geometry_coverage.map((row) => `${row.geometry_source}: ${row.parcel_count} parcels`)} footer={`${trace.summary.geometry_captured_count} captured / ${trace.summary.geometry_missing_count} missing`} />
      <SummaryList title="Activity types" rows={trace.activity_count_by_type.map((row) => `${row.activity_type}: ${row.activity_count}`)} />
    </div>

    <section className="mb-6 overflow-hidden rounded bg-white shadow">
      <SectionHeader title="Farmers" subtitle="Recent farmers in this project with parcel, cycle, and activity counts." />
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Farmer", "Mobile", "Village/crop", "Usage", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.farmers.map((farmer) => <tr key={farmer.id}>
            <td className="p-3"><div>{farmer.display_name || farmer.label}</div><div className="font-mono text-xs text-gray-500">{farmer.id}</div></td>
            <td className="p-3">{farmer.mobile_number || "-"}</td>
            <td className="p-3"><div>{farmer.village_name || "-"}</div><div className="text-xs text-gray-500">{farmer.primary_crop_code || "-"}</div></td>
            <td className="p-3">{farmer.parcel_count} parcels / {farmer.crop_cycle_count} cycles / {farmer.activity_count} activities</td>
            <td className="p-3"><Link href={farmer.trace_url} className="text-blue-600">Farmer trace</Link></td>
          </tr>)}
          {trace.farmers.length === 0 && <Empty colSpan={5} label="No farmers found." />}
        </tbody>
      </table>
    </section>

    <section className="mb-6 overflow-hidden rounded bg-white shadow">
      <SectionHeader title="Parcels" subtitle="Recent parcels in this project with geometry and ownership state." />
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Parcel", "Farmer", "Area/ownership", "Geometry", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.parcels.map((parcel) => <tr key={parcel.id}>
            <td className="p-3"><div>{parcel.local_name || parcel.survey_number || parcel.label}</div><div className="font-mono text-xs text-gray-500">{parcel.id}</div></td>
            <td className="p-3"><Link href={`/farmer-trace/${parcel.farmer_id}`} className="font-mono text-xs text-blue-600">{parcel.farmer_id}</Link></td>
            <td className="p-3"><div>{[parcel.reported_area, parcel.reported_area_unit].filter(Boolean).join(" ") || "-"}</div><div className="text-xs text-gray-500">{parcel.ownership_type || "-"}</div></td>
            <td className="p-3">{parcel.geometry_source || "-"}</td>
            <td className="p-3"><Link href={parcel.trace_url} className="text-blue-600">Parcel trace</Link></td>
          </tr>)}
          {trace.parcels.length === 0 && <Empty colSpan={5} label="No parcels found." />}
        </tbody>
      </table>
    </section>

    <section className="mb-6 overflow-hidden rounded bg-white shadow">
      <SectionHeader title="Crop cycles" subtitle="Recent crop cycles with pinned workflow versions and activity cost totals." />
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Crop", "Season", "Status", "Dates", "Activities", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.crop_cycles.map((cycle) => <tr key={cycle.id}>
            <td className="p-3"><div>{cycle.crop_code}</div><div className="font-mono text-xs text-gray-500">{cycle.id}</div></td>
            <td className="p-3">{cycle.season_code}</td>
            <td className="p-3">{cycle.status}</td>
            <td className="p-3"><div>Sowing {cycle.planned_sowing_date || "-"}</div><div className="text-xs text-gray-500">Harvest {cycle.actual_harvest_date || cycle.expected_harvest_date || "-"}</div></td>
            <td className="p-3">{cycle.activity_count} / INR {cycle.total_cost}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${cycle.id}`} className="text-blue-600">Cycle trace</Link></td>
          </tr>)}
          {trace.crop_cycles.length === 0 && <Empty colSpan={6} label="No crop cycles found." />}
        </tbody>
      </table>
    </section>

    <section className="overflow-hidden rounded bg-white shadow">
      <SectionHeader title="Recent activities" subtitle="Most recent logged activities across the project." />
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date", "Crop/stage", "Activity", "Input", "Product", "Qty", "Cost", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.activities.map((activity) => <tr key={activity.activity_id}>
            <td className="p-3 whitespace-nowrap">{activity.activity_date || "-"}</td>
            <td className="p-3"><div>{activity.crop_code} - {activity.season_code}</div><div className="text-xs text-gray-500">{activity.stage_code || "-"}</div></td>
            <td className="p-3">{activity.activity_type}</td>
            <td className="p-3"><div>{activity.input_name || activity.input_code || "-"}</div>{activity.input_rule_id && <Link href={`/input-rule-trace/${activity.input_rule_id}`} className="font-mono text-xs text-blue-600">{activity.input_rule_id}</Link>}</td>
            <td className="p-3">{activity.product_code ? <Link href={`/product-trace/${encodeURIComponent(activity.product_code)}`} className="font-mono text-xs text-blue-600">{activity.product_code}</Link> : <span>-</span>}</td>
            <td className="p-3">{activity.actual_quantity || activity.quantity || "-"} {activity.actual_quantity_unit || activity.quantity_unit || ""}</td>
            <td className="p-3">{activity.cost_amount ? `INR ${activity.cost_amount}` : "-"}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${activity.crop_cycle_id}`} className="text-blue-600">Cycle</Link></td>
          </tr>)}
          {trace.activities.length === 0 && <Empty colSpan={8} label="No activities found." />}
        </tbody>
      </table>
    </section>
  </div>;
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}
function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="border-b p-5"><h2 className="text-lg font-bold text-gray-900">{title}</h2><p className="text-sm text-gray-500">{subtitle}</p></div>;
}
function SummaryList({ title, rows, footer }: { title: string; rows: string[]; footer?: string }) {
  return <div className="rounded bg-white p-5 shadow"><h2 className="font-semibold text-gray-900">{title}</h2>{rows.length ? <ul className="mt-3 space-y-1 text-sm text-gray-700">{rows.slice(0, 8).map((row) => <li key={row}>{row}</li>)}</ul> : <p className="mt-3 text-sm text-gray-400">No data yet.</p>}{footer && <p className="mt-3 text-xs text-gray-400">{footer}</p>}</div>;
}
function Empty({ colSpan, label }: { colSpan: number; label: string }) {
  return <tr><td colSpan={colSpan} className="p-8 text-center text-gray-400">{label}</td></tr>;
}
