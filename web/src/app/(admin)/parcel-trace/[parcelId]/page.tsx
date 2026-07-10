"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type ParcelTraceResponse } from "@/lib/api";

export default function ParcelTracePage({ params }: { params: { parcelId: string } }) {
  const [trace, setTrace] = useState<ParcelTraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .parcelTrace(params.parcelId)
      .then(setTrace)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load parcel trace"))
      .finally(() => setLoading(false));
  }, [params.parcelId]);

  if (loading) return <div className="text-gray-500">Loading parcel trace...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!trace) return <div className="text-gray-500">No parcel trace found.</div>;

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href={trace.farmer?.id ? `/farmer-trace/${trace.farmer.id}` : "/activity-usage"} className="text-sm text-blue-600">&lt; Back to farmer trace</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Parcel Trace</h1>
        <p className="mt-1 text-sm text-gray-500">{trace.parcel.display_name || trace.parcel.survey_number || trace.parcel.id}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{trace.parcel.id}</div>
        <div className="mt-1 text-gray-700">Farmer: <span className="font-mono">{trace.farmer?.display_name || trace.farmer?.mobile_number || trace.farmer?.id || "-"}</span></div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Crop cycles" value={trace.summary.crop_cycle_count} />
      <Card label="Active cycles" value={trace.summary.active_cycle_count} />
      <Card label="Activities" value={trace.summary.activity_count} />
      <Card label="Total cost" value={`INR ${trace.summary.total_cost}`} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-3">
      <InfoSection title="Parcel identity" rows={[
        ["Survey", trace.parcel.survey_number],
        ["Local name", trace.parcel.local_name],
        ["Area", [trace.parcel.reported_area, trace.parcel.reported_area_unit].filter(Boolean).join(" ")],
        ["Ownership", trace.parcel.ownership_type],
        ["Village", trace.parcel.village_name],
        ["Status", trace.parcel.status],
      ]} />
      <InfoSection title="Geometry" rows={[
        ["Source", trace.parcel.geometry_source],
        ["Centroid", trace.parcel.centroid_lat && trace.parcel.centroid_lng ? `${trace.parcel.centroid_lat}, ${trace.parcel.centroid_lng}` : null],
        ["Computed area ha", trace.parcel.computed_area_hectares],
        ["Accuracy meters", trace.parcel.geometry_accuracy_meters],
        ["Captured at", trace.parcel.geometry_captured_at],
      ]} />
      <InfoSection title="Farmer / project" rows={[
        ["Farmer", trace.farmer?.display_name],
        ["Mobile", trace.farmer?.mobile_number],
        ["Farmer ID", trace.farmer?.id],
        ["Project", trace.project?.name],
        ["Project ID", trace.project?.id],
      ]} action={trace.farmer?.id ? <Link href={`/farmer-trace/${trace.farmer.id}`} className="rounded bg-gray-900 px-3 py-1 text-xs text-white">Open farmer</Link> : undefined} />
    </div>

    <section className="mb-6 overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Crop cycles on this parcel</h2>
        <p className="text-sm text-gray-500">Cycle history, pinned workflow version, and activity totals for the selected land parcel.</p>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Crop", "Season", "Status", "Dates", "Activities", "Workflow", "Trace"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.crop_cycles.map((cycle) => <tr key={cycle.id}>
            <td className="p-3">{cycle.crop_code}</td>
            <td className="p-3">{cycle.season_code}</td>
            <td className="p-3">{cycle.status}</td>
            <td className="p-3"><div>Sowing {cycle.planned_sowing_date || "-"}</div><div className="text-xs text-gray-500">Harvest {cycle.actual_harvest_date || cycle.expected_harvest_date || "-"}</div></td>
            <td className="p-3">{cycle.activity_count} / INR {cycle.total_cost}</td>
            <td className="p-3 font-mono text-xs">{cycle.workflow_template_version_id || "-"}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${cycle.id}`} className="text-blue-600">Open cycle</Link></td>
          </tr>)}
          {trace.crop_cycles.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-gray-400">No crop cycles found for this parcel.</td></tr>}
        </tbody>
      </table>
    </section>

    <section className="overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Parcel activities</h2>
        <p className="text-sm text-gray-500">Up to 250 logged activities from all crop cycles on this parcel.</p>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date", "Crop/stage", "Activity", "Input", "Product", "Qty", "Cost", "Links"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.activities.map((activity) => <tr key={activity.activity_id}>
            <td className="p-3 whitespace-nowrap">{activity.activity_date || "-"}</td>
            <td className="p-3"><div>{activity.crop_code} - {activity.season_code}</div><div className="text-xs text-gray-500">{activity.stage_code || "-"}</div></td>
            <td className="p-3">{activity.activity_type}</td>
            <td className="p-3"><div>{activity.input_name || activity.input_code || "-"}</div>{activity.input_rule_id && <Link href={`/input-rule-trace/${activity.input_rule_id}`} className="font-mono text-xs text-blue-600">{activity.input_rule_id}</Link>}</td>
            <td className="p-3">{activity.product_code ? <Link href={`/product-trace/${encodeURIComponent(activity.product_code)}`} className="font-mono text-xs text-blue-600">{activity.product_code}</Link> : <span>-</span>}<div className="font-mono text-xs text-gray-500">{activity.package_sku || ""}</div></td>
            <td className="p-3">{activity.actual_quantity || activity.quantity || "-"} {activity.actual_quantity_unit || activity.quantity_unit || ""}</td>
            <td className="p-3">{activity.cost_amount ? `INR ${activity.cost_amount}` : "-"}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${activity.crop_cycle_id}`} className="text-blue-600">Cycle</Link></td>
          </tr>)}
          {trace.activities.length === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-400">No activities logged for this parcel.</td></tr>}
        </tbody>
      </table>
    </section>
  </div>;
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function InfoSection({ title, rows, action }: { title: string; rows: Array<[string, string | number | null | undefined]>; action?: React.ReactNode }) {
  return <section className="rounded bg-white p-5 shadow">
    <div className="mb-3 flex items-center justify-between gap-3"><h2 className="font-bold text-gray-900">{title}</h2>{action}</div>
    <dl className="space-y-2 text-sm">
      {rows.map(([label, value]) => <div key={label}>
        <dt className="text-xs uppercase text-gray-400">{label}</dt>
        <dd className="break-words font-mono text-gray-800">{value || "-"}</dd>
      </div>)}
    </dl>
  </section>;
}
