"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type InputRuleTraceResponse } from "@/lib/api";

export default function InputRuleTracePage({ params }: { params: { ruleId: string } }) {
  const [trace, setTrace] = useState<InputRuleTraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .inputRuleTrace(params.ruleId)
      .then(setTrace)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load input rule trace"))
      .finally(() => setLoading(false));
  }, [params.ruleId]);

  if (loading) return <div className="text-gray-500">Loading input rule trace...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!trace) return <div className="text-gray-500">No trace found.</div>;

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href="/activity-usage" className="text-sm text-blue-600">← Back to Activity Usage</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Input Rule Trace</h1>
        <p className="mt-1 text-sm text-gray-500">{trace.rule.crop_code} · {trace.rule.stage_code} · {trace.rule.activity_type}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{trace.rule.id}</div>
        <div className="mt-1 text-gray-700">Input: <span className="font-mono">{trace.rule.input_code}</span></div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Activities" value={trace.summary.activity_count} />
      <Card label="Total cost" value={`₹${trace.summary.total_cost}`} />
      <Card label="Variances" value={trace.summary.variance_count} />
      <Card label="Products" value={trace.products.length} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-3">
      <InfoSection title="Rule" rows={[
        ["Enabled", String(trace.rule.enabled)],
        ["Priority", String(trace.rule.priority || "")],
        ["Crop / season", `${trace.rule.crop_code} / ${trace.rule.season_code || "-"}`],
        ["Stage", String(trace.rule.stage_code)],
        ["Activity type", String(trace.rule.activity_type)],
        ["Reason", String(trace.rule.reason || "")],
      ]} />
      <InfoSection title="Dosage" rows={[
        ["Quantity", [trace.rule.dosage_quantity, trace.rule.dosage_unit].filter(Boolean).join(" ")],
        ["Area unit", String(trace.rule.dosage_area_unit || "")],
        ["Min", [trace.rule.min_quantity, trace.rule.dosage_unit].filter(Boolean).join(" ")],
        ["Max", [trace.rule.max_quantity, trace.rule.dosage_unit].filter(Boolean).join(" ")],
        ["Timing", String(trace.rule.timing_note || "")],
        ["Safety", String(trace.rule.safety_note || "")],
      ]} />
      <InfoSection title="Input / project" rows={[
        ["Input", `${trace.input?.code || trace.rule.input_code} - ${trace.input?.canonical_name || ""}`],
        ["Category", `${trace.input?.category_code || ""} ${trace.input?.category_name || ""}`],
        ["Catalog status", String(trace.input?.catalog_status || "")],
        ["Project", trace.project?.name],
        ["Assignment", trace.project_assignment ? `Enabled: ${trace.project_assignment.enabled}` : "No explicit assignment"],
      ]} />
    </div>

    <div className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Allowed / mapped products</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {trace.products.map((product) => <div key={product.id} className="rounded border p-4">
          <div className="font-semibold text-gray-900">{String(product.brand_name || product.code)}</div>
          <div className="font-mono text-xs text-gray-500">{product.code}</div>
          <div className="mt-2 text-sm text-gray-600">Status: {String(product.status || "-")}</div>
          <div className="mt-1 text-sm text-gray-600">Approval: {product.approval ? JSON.stringify(product.approval) : "No project approval"}</div>
        </div>)}
        {trace.products.length === 0 && <p className="text-sm text-gray-400">No products mapped.</p>}
      </div>
    </div>

    <div className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Quantity by product</h2>
      {trace.summary.quantity_by_product.length ? <ul className="space-y-1 text-sm text-gray-700">
        {trace.summary.quantity_by_product.map((row) => <li key={`${row.product_code}-${row.unit}`}><span className="font-mono">{row.product_code}</span>: {row.quantity} {row.unit}</li>)}
      </ul> : <p className="text-sm text-gray-400">No product quantities yet.</p>}
    </div>

    <div className="overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Activities using this rule</h2>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date", "Cycle", "Stage", "Product", "Qty", "Cost", "Variance"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.activities.map((activity) => <tr key={activity.activity_id}>
            <td className="p-3 whitespace-nowrap">{activity.activity_date || "-"}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${activity.crop_cycle_id}`} className="font-mono text-xs text-blue-600">{activity.crop_cycle_id}</Link></td>
            <td className="p-3">{activity.stage_name || activity.stage_code || "-"}</td>
            <td className="p-3"><div className="font-mono text-xs">{activity.product_code || "-"}</div><div className="font-mono text-xs text-gray-500">{activity.package_sku || ""}</div></td>
            <td className="p-3">{activity.actual_quantity || activity.quantity || "-"} {activity.actual_quantity_unit || activity.quantity_unit || ""}</td>
            <td className="p-3">{activity.cost_amount ? `₹${activity.cost_amount}` : "-"}</td>
            <td className="p-3">{activity.dosage_variance_reason || "-"}</td>
          </tr>)}
          {trace.activities.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-gray-400">No activities have used this rule.</td></tr>}
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