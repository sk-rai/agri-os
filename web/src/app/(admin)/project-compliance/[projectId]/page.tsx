"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type ProjectInputComplianceResponse } from "@/lib/api";

export default function ProjectCompliancePage({ params }: { params: { projectId: string } }) {
  const [report, setReport] = useState<ProjectInputComplianceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .projectInputCompliance(params.projectId)
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load project compliance"))
      .finally(() => setLoading(false));
  }, [params.projectId]);

  if (loading) return <div className="text-gray-500">Loading project compliance...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!report) return <div className="text-gray-500">No report found.</div>;

  const summary = report.summary;
  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href="/projects" className="text-sm text-blue-600">← Back to Projects</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Project Input Compliance</h1>
        <p className="mt-1 text-sm text-gray-500">{report.project.name} · {report.project.status}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{report.project.id}</div>
        <div className="mt-1 text-gray-700">{report.project.start_date || "-"} → {report.project.end_date || "-"}</div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Activities" value={summary.activity_count} />
      <Card label="Total cost" value={`₹${summary.total_cost}`} />
      <Card label="Linked to recommendations" value={`${summary.recommendation_linked_rate_percent}%`} />
      <Card label="Approved product usage" value={`${summary.product_approval_rate_percent}%`} />
    </div>
    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Custom activities" value={summary.custom_activity_count} />
      <Card label="Variances" value={`${summary.variance_count} (${summary.variance_rate_percent}%)`} />
      <Card label="Unapproved products" value={summary.product_unapproved_count} />
      <Card label="Missing product" value={summary.product_missing_count} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-2">
      <SummaryList title="Quantity by input" rows={report.quantity_by_input.map(row => `${row.input_code}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Quantity by product" rows={report.quantity_by_product.map(row => `${row.product_code}${row.package_sku ? ` / ${row.package_sku}` : ""}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Quantity by crop/stage" rows={report.quantity_by_crop_stage.map(row => `${row.crop_code} · ${row.stage_code}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Top variance reasons" rows={report.top_variance_reasons.map(row => `${row.reason}: ${row.count}`)} />
    </div>

    <div className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Activity count by crop/stage</h2>
      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
        {report.activity_count_by_crop_stage.map(row => <div key={`${row.crop_code}-${row.stage_code}`} className="rounded border p-3 text-sm">
          <div className="font-semibold text-gray-900">{row.crop_code} · {row.stage_code}</div>
          <div className="text-gray-600">{row.activity_count} activities</div>
        </div>)}
        {report.activity_count_by_crop_stage.length === 0 && <p className="text-sm text-gray-400">No activity counts yet.</p>}
      </div>
    </div>

    <div className="overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Recent activities in project</h2>
        <p className="text-sm text-gray-500">Limited to the latest 250 activities in the backend report payload.</p>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date", "Cycle", "Stage", "Input", "Product", "Qty", "Cost", "Variance"].map(head => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {report.activities.map(activity => <tr key={activity.activity_id}>
            <td className="p-3 whitespace-nowrap">{activity.activity_date || "-"}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${activity.crop_cycle_id}`} className="font-mono text-xs text-blue-600">{activity.crop_cycle_id}</Link></td>
            <td className="p-3">{activity.stage_name || activity.stage_code || "-"}</td>
            <td className="p-3"><div>{activity.input_name || activity.input_code || "-"}</div>{activity.input_rule_id && <Link href={`/input-rule-trace/${activity.input_rule_id}`} className="font-mono text-xs text-blue-600">{activity.input_rule_id}</Link>}</td>
            <td className="p-3">{activity.product_code ? <Link href={`/product-trace/${encodeURIComponent(activity.product_code)}`} className="font-mono text-xs text-blue-600">{activity.product_code}</Link> : <span>-</span>}<div className="font-mono text-xs text-gray-500">{activity.package_sku || ""}</div></td>
            <td className="p-3">{activity.actual_quantity || activity.quantity || "-"} {activity.actual_quantity_unit || activity.quantity_unit || ""}</td>
            <td className="p-3">{activity.cost_amount ? `₹${activity.cost_amount}` : "-"}</td>
            <td className="p-3">{activity.dosage_variance_reason || "-"}</td>
          </tr>)}
          {report.activities.length === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-400">No project activities yet.</td></tr>}
        </tbody>
      </table>
    </div>
  </div>;
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function SummaryList({ title, rows }: { title: string; rows: string[] }) {
  return <section className="rounded bg-white p-5 shadow"><h2 className="font-semibold text-gray-900">{title}</h2>{rows.length ? <ul className="mt-3 space-y-1 text-sm text-gray-700">{rows.slice(0, 10).map(row => <li key={row}>{row}</li>)}</ul> : <p className="mt-3 text-sm text-gray-400">No data yet.</p>}</section>;
}