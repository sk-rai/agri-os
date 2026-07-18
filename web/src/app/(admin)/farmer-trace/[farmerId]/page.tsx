"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type FarmerTraceResponse } from "@/lib/api";

export default function FarmerTracePage({ params }: { params: { farmerId: string } }) {
  const [trace, setTrace] = useState<FarmerTraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .farmerTrace(params.farmerId)
      .then(setTrace)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load farmer trace"))
      .finally(() => setLoading(false));
  }, [params.farmerId]);

  if (loading) return <div className="text-gray-500">Loading farmer trace...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!trace) return <div className="text-gray-500">No farmer trace found.</div>;

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href="/activity-usage" className="text-sm text-blue-600">&lt; Back to Activity Usage</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Farmer Trace</h1>
        <p className="mt-1 text-sm text-gray-500">{trace.farmer.display_name || trace.farmer.mobile_number || trace.farmer.id}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{trace.farmer.id}</div>
        <div className="mt-1 text-gray-700">Project: <span className="font-mono">{trace.project?.name || trace.project?.id || "-"}</span></div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Parcels" value={trace.summary.parcel_count} />
      <Card label="Crop cycles" value={trace.summary.crop_cycle_count} />
      <Card label="Activities" value={trace.summary.activity_count} />
      <Card label="Total cost" value={`INR ${trace.summary.total_cost}`} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-3">
      <InfoSection title="Farmer" rows={[
        ["Name", trace.farmer.display_name],
        ["Mobile", trace.farmer.mobile_number],
        ["Village", trace.farmer.village_name],
        ["Primary crop", trace.farmer.primary_crop_code],
        ["Status", trace.farmer.status],
      ]} />
      <InfoSection title="Project" rows={[
        ["Project", trace.project?.name],
        ["Project ID", trace.project?.id],
        ["Project status", trace.project?.status],
        ["Tenant", trace.tenant_id],
      ]} />
      <InfoSection title="Usage summary" rows={[
        ["Active cycles", trace.summary.active_cycle_count],
        ["Completed cycles", trace.summary.completed_cycle_count],
        ["Dosage variances", trace.summary.variance_count],
        ["Returned activities", trace.activities.length],
      ]} />
    </div>

    <section className="mb-6 rounded bg-white p-5 shadow">
      <div className="flex flex-col gap-3 border-b pb-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Project enrollment lifecycle</h2>
          <p className="text-sm text-gray-500">Shows whether this farmer is currently project-affiliated or can continue independently.</p>
        </div>
        <Link href={trace.enrollment_lifecycle.project_enrollments_url} className="rounded border px-3 py-2 text-sm text-blue-600">Open enrollments</Link>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <Mini label="Open enrollments" value={trace.enrollment_lifecycle.active_pending_count} />
        <Mini label="Active" value={trace.enrollment_lifecycle.active_count} />
        <Mini label="Pending" value={trace.enrollment_lifecycle.pending_count} />
        <Mini label="Independent mode" value={trace.enrollment_lifecycle.can_continue_independently ? "Allowed" : "Project context active"} />
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {trace.project_enrollments.map((enrollment) => <div key={enrollment.id} className="rounded border p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-semibold text-gray-900">{enrollment.project_name || enrollment.project_id}</div>
              <div className="font-mono text-xs text-gray-500">{enrollment.id}</div>
            </div>
            <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700">{enrollment.status}</span>
          </div>
          <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
            <Mini label="Project status" value={enrollment.project_status} />
            <Mini label="Method/source" value={[enrollment.enrollment_method, enrollment.enrollment_source].filter(Boolean).join(" / ")} />
            <Mini label="Parcels linked" value={enrollment.parcel_ids.length} />
            <Mini label="Updated" value={enrollment.updated_at} />
          </div>
          {enrollment.lifecycle_events.length > 0 && <div className="mt-3 rounded bg-gray-50 p-3 text-xs text-gray-600">
            Latest event: <span className="font-mono">{formatTraceValue(enrollment.lifecycle_events[0])}</span>
          </div>}
        </div>)}
        {trace.project_enrollments.length === 0 && <p className="text-sm text-gray-400">No project memberships found. This farmer is currently independent/unaffiliated.</p>}
      </div>
    </section>

    <section className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Parcels</h2>
      <div className="grid gap-3 lg:grid-cols-2">
        {trace.parcels.map((parcel) => <div key={parcel.id} className="rounded border p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-semibold text-gray-900">{parcel.display_name || parcel.survey_number || parcel.id}</div>
              <div className="font-mono text-xs text-gray-500">{parcel.id}</div>
            </div>
            <div className="flex items-center gap-2">
              <Link href={`/parcel-trace/${parcel.id}`} className="text-xs text-blue-600">Open parcel</Link>
              <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700">{parcel.status || "-"}</span>
            </div>
          </div>
          <div className="mt-3 grid gap-2 text-sm md:grid-cols-3">
            <Mini label="Area" value={[parcel.reported_area, parcel.reported_area_unit].filter(Boolean).join(" ")} />
            <Mini label="Ownership" value={parcel.ownership_type} />
            <Mini label="PIN" value={parcel.pin_code || "-"} />
            <Mini label="Geometry" value={parcel.geometry_source} />
            <Mini label="Cycles" value={`${parcel.crop_cycle_count} (${parcel.active_cycle_count} active)`} />
            <Mini label="Activities" value={parcel.activity_count} />
            <Mini label="Cost" value={`INR ${parcel.total_cost}`} />
          </div>
          {parcel.location_scope && Object.keys(parcel.location_scope).length ? <pre className="mt-3 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(parcel.location_scope, null, 2)}</pre> : null}
        </div>)}
        {trace.parcels.length === 0 && <p className="text-sm text-gray-400">No parcels found for this farmer.</p>}
      </div>
    </section>

    <section className="mb-6 overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Crop cycles</h2>
        <p className="text-sm text-gray-500">Pinned workflow version and usage counts per farmer cycle.</p>
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
          {trace.crop_cycles.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-gray-400">No crop cycles found.</td></tr>}
        </tbody>
      </table>
    </section>

    <section className="overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Recent activities</h2>
        <p className="text-sm text-gray-500">Up to 250 logged activities tied to this farmer.</p>
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
          {trace.activities.length === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-400">No activities logged.</td></tr>}
        </tbody>
      </table>
    </section>
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

function formatTraceValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
