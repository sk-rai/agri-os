"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reportsApi, type ProductTraceResponse } from "@/lib/api";

export default function ProductTracePage({ params }: { params: { productCode: string } }) {
  const productCode = decodeURIComponent(params.productCode);
  const [trace, setTrace] = useState<ProductTraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .productTrace(productCode)
      .then(setTrace)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load product trace"))
      .finally(() => setLoading(false));
  }, [productCode]);

  if (loading) return <div className="text-gray-500">Loading product trace...</div>;
  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!trace) return <div className="text-gray-500">No trace found.</div>;

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <Link href="/activity-usage" className="text-sm text-blue-600">← Back to Activity Usage</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Product Trace</h1>
        <p className="mt-1 text-sm text-gray-500">{trace.product.brand_name} · {trace.product.code}</p>
      </div>
      <div className="rounded bg-white p-4 text-sm shadow">
        <div className="font-mono text-xs text-gray-500">{trace.product.id}</div>
        <div className="mt-1 text-gray-700">Status: <span className="font-mono">{trace.product.status}</span></div>
      </div>
    </div>

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Activities" value={trace.summary.activity_count} />
      <Card label="Total cost" value={`₹${trace.summary.total_cost}`} />
      <Card label="Variances" value={trace.summary.variance_count} />
      <Card label="Packages" value={trace.packages.length} />
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-3">
      <InfoSection title="Product" rows={[
        ["Code", trace.product.code],
        ["Brand", trace.product.brand_name],
        ["Composition", trace.product.composition],
        ["Registration", trace.product.registration_number],
        ["Authority", trace.product.registration_authority],
        ["Expiry", trace.product.registration_expiry_date],
      ]} />
      <InfoSection title="Manufacturer / input" rows={[
        ["Manufacturer", trace.manufacturer?.canonical_name],
        ["Manufacturer code", trace.manufacturer?.code],
        ["Input", `${trace.input?.code || ""} - ${trace.input?.canonical_name || ""}`],
        ["Category", `${trace.input?.category_code || ""} ${trace.input?.category_name || ""}`],
        ["Catalog status", trace.input?.catalog_status],
      ]} />
      <InfoSection title="Approvals" rows={[
        ["Approval count", String(trace.project_approvals.length)],
        ["Rule count", String(trace.input_rules.length)],
        ["Country", trace.product.country],
        ["Created", trace.product.created_at],
        ["Updated", trace.product.updated_at],
      ]} />
    </div>

    <div className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Packages</h2>
      <div className="grid gap-3 md:grid-cols-3">
        {trace.packages.map((pkg) => <div key={pkg.id} className="rounded border p-4">
          <div className="font-semibold text-gray-900">{pkg.pack_label}</div>
          <div className="font-mono text-xs text-gray-500">{pkg.sku}</div>
          <div className="mt-2 text-sm text-gray-600">{pkg.quantity} {pkg.unit} · {pkg.status}</div>
          <div className="mt-1 text-sm text-gray-600">Activities: {pkg.activity_count}</div>
        </div>)}
      </div>
    </div>

    <div className="mb-6 grid gap-4 lg:grid-cols-2">
      <SummaryList title="Quantity by package" rows={trace.summary.quantity_by_package.map(row => `${row.package_sku}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Quantity by crop" rows={trace.summary.quantity_by_crop.map(row => `${row.crop_code}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Quantity by stage" rows={trace.summary.quantity_by_stage.map(row => `${row.stage_code}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Quantity by project" rows={trace.summary.quantity_by_project.map(row => `${row.project_id}: ${row.quantity} ${row.unit}`)} />
    </div>

    <div className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-bold text-gray-900">Input rules allowing this product</h2>
      <div className="space-y-2">
        {trace.input_rules.map((rule) => <div key={rule.id} className="flex flex-col gap-2 rounded border p-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="font-semibold text-gray-900">{rule.crop_code} · {rule.stage_code} · {rule.activity_type}</div>
            <div className="font-mono text-xs text-gray-500">{rule.id}</div>
          </div>
          <Link href={`/input-rule-trace/${rule.id}`} className="text-sm text-blue-600">Open rule</Link>
        </div>)}
        {trace.input_rules.length === 0 && <p className="text-sm text-gray-400">No input rules found for this product.</p>}
      </div>
    </div>

    <div className="overflow-hidden rounded bg-white shadow">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold text-gray-900">Activities using this product</h2>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date", "Cycle", "Stage", "Input", "Package", "Qty", "Cost", "Variance"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {trace.activities.map((activity) => <tr key={activity.activity_id}>
            <td className="p-3 whitespace-nowrap">{activity.activity_date || "-"}</td>
            <td className="p-3"><Link href={`/crop-cycle-trace/${activity.crop_cycle_id}`} className="font-mono text-xs text-blue-600">{activity.crop_cycle_id}</Link></td>
            <td className="p-3">{activity.stage_name || activity.stage_code || "-"}</td>
            <td className="p-3"><div>{activity.input_name || activity.input_code || "-"}</div>{activity.input_rule_id && <Link href={`/input-rule-trace/${activity.input_rule_id}`} className="font-mono text-xs text-blue-600">{activity.input_rule_id}</Link>}</td>
            <td className="p-3"><div className="font-mono text-xs">{activity.package_sku || "-"}</div></td>
            <td className="p-3">{activity.actual_quantity || activity.quantity || "-"} {activity.actual_quantity_unit || activity.quantity_unit || ""}</td>
            <td className="p-3">{activity.cost_amount ? `₹${activity.cost_amount}` : "-"}</td>
            <td className="p-3">{activity.dosage_variance_reason || "-"}</td>
          </tr>)}
          {trace.activities.length === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-400">No activities have used this product.</td></tr>}
        </tbody>
      </table>
    </div>
  </div>;
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function InfoSection({ title, rows }: { title: string; rows: Array<[string, string | number | null | undefined]> }) {
  return <section className="rounded bg-white p-5 shadow"><h2 className="mb-3 font-bold text-gray-900">{title}</h2><dl className="space-y-2 text-sm">{rows.map(([label, value]) => <div key={label}><dt className="text-xs uppercase text-gray-400">{label}</dt><dd className="break-words font-mono text-gray-800">{value || "-"}</dd></div>)}</dl></section>;
}

function SummaryList({ title, rows }: { title: string; rows: string[] }) {
  return <section className="rounded bg-white p-5 shadow"><h2 className="font-semibold text-gray-900">{title}</h2>{rows.length ? <ul className="mt-3 space-y-1 text-sm text-gray-700">{rows.map(row => <li key={row}>{row}</li>)}</ul> : <p className="mt-3 text-sm text-gray-400">No quantities yet.</p>}</section>;
}