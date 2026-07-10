"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type CropCycleTraceResponse } from "@/lib/api";

export default function CropCycleTracePage({ params }: { params: { cycleId: string } }) {
  const [trace, setTrace] = useState<CropCycleTraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .cropCycleTrace(params.cycleId)
      .then(setTrace)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load crop cycle trace"))
      .finally(() => setLoading(false));
  }, [params.cycleId]);

  if (loading) return <div className="text-gray-500">Loading crop cycle trace...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!trace) return <div className="text-gray-500">No trace found.</div>;

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href="/activity-usage" className="text-sm text-blue-600">← Back to Activity Usage</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Crop Cycle Trace</h1>
        <p className="mt-1 text-sm text-gray-500">{trace.cycle.crop_code} · {trace.cycle.season_code} · {trace.cycle.status}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{trace.cycle.id}</div>
        <div className="mt-1 text-gray-700">Workflow version: <span className="font-mono">{String(trace.cycle.workflow_template_version_id || "-")}</span></div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Stages" value={trace.summary.stage_count} />
      <Card label="Activities" value={trace.summary.activity_count} />
      <Card label="Total cost" value={`₹${trace.summary.total_cost}`} />
      <Card label="Variances" value={trace.summary.variance_count} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-3">
      <InfoSection title="Farmer" rows={[
        ["Name", trace.farmer?.display_name],
        ["Mobile", trace.farmer?.mobile_number],
        ["Village", trace.farmer?.village_name],
        ["Farmer ID", trace.farmer?.id],
      ]} />
      <InfoSection title="Parcel" rows={[
        ["Survey", trace.parcel?.survey_number],
        ["Area", [trace.parcel?.reported_area, trace.parcel?.reported_area_unit].filter(Boolean).join(" ")],
        ["Ownership", trace.parcel?.ownership_type],
        ["Geometry", trace.parcel?.geometry_source],
        ["Parcel ID", trace.parcel?.id],
      ]} />
      <InfoSection title="Project / cycle" rows={[
        ["Project", trace.project?.name],
        ["Project ID", trace.project?.id],
        ["Planned sowing", String(trace.cycle.planned_sowing_date || "")],
        ["Actual harvest", String(trace.cycle.actual_harvest_date || "")],
        ["Lifecycle template", String(trace.cycle.lifecycle_template_id || "")],
      ]} />
    </div>

    <div className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Stage timeline</h2>
      <div className="space-y-3">
        {trace.stages.map((stage) => <div key={stage.stage_instance_id} className="rounded border p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="font-semibold text-gray-900">{stage.stage_order}. {stage.stage_name}</div>
              <div className="font-mono text-xs text-gray-500">{stage.stage_code} · {stage.stage_instance_id}</div>
            </div>
            <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700">{stage.status}</span>
          </div>
          <div className="mt-3 grid gap-2 text-sm md:grid-cols-4">
            <Mini label="Planned start" value={stage.planned_start_date} />
            <Mini label="Actual start" value={stage.actual_start_date} />
            <Mini label="Actual end" value={stage.actual_end_date} />
            <Mini label="Activities / cost" value={`${stage.activity_count} / ₹${stage.total_cost}`} />
          </div>
        </div>)}
      </div>
    </div>

    <div className="overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Activities</h2>
        <p className="text-sm text-gray-500">All logged activities for this crop cycle, ordered by activity date.</p>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date", "Stage", "Activity", "Input", "Product", "Qty", "Cost", "Variance"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.activities.map((activity) => <tr key={activity.activity_id}>
            <td className="p-3 whitespace-nowrap">{activity.activity_date || "-"}</td>
            <td className="p-3"><div>{activity.stage_name || activity.stage_code || "-"}</div><div className="font-mono text-xs text-gray-500">{activity.stage_instance_id || ""}</div></td>
            <td className="p-3">{activity.activity_type}</td>
            <td className="p-3"><div>{activity.input_name || activity.input_code || "-"}</div><div className="font-mono text-xs text-gray-500">{activity.input_rule_id || ""}</div></td>
            <td className="p-3"><div className="font-mono text-xs">{activity.product_code || "-"}</div><div className="font-mono text-xs text-gray-500">{activity.package_sku || ""}</div></td>
            <td className="p-3">{activity.actual_quantity || activity.quantity || "-"} {activity.actual_quantity_unit || activity.quantity_unit || ""}</td>
            <td className="p-3">{activity.cost_amount ? `₹${activity.cost_amount}` : "-"}</td>
            <td className="p-3">{activity.dosage_variance_reason || "-"}</td>
          </tr>)}
          {trace.activities.length === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-400">No activities logged.</td></tr>}
        </tbody>
      </table>
    </div>
  </div>;
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function InfoSection({ title, rows }: { title: string; rows: Array<[string, string | number | null | undefined]> }) {
  return <section className="rounded bg-white p-5 shadow">
    <h2 className="mb-3 font-bold text-gray-900">{title}</h2>
    <dl className="space-y-2 text-sm">
      {rows.map(([label, value]) => <div key={label}>
        <dt className="text-xs uppercase text-gray-400">{label}</dt>
        <dd className="break-words font-mono text-gray-800">{value || "-"}</dd>
      </div>)}
    </dl>
  </section>;
}

function Mini({ label, value }: { label: string; value?: string | number | null }) {
  return <div><div className="text-xs uppercase text-gray-400">{label}</div><div className="font-mono text-gray-800">{value || "-"}</div></div>;
}