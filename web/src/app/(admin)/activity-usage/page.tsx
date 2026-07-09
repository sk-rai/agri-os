"use client";

import { useCallback, useEffect, useState } from "react";
import { reportsApi, type ActivityUsageReportResponse } from "@/lib/api";

const EMPTY_FILTERS = {
  projectId: "",
  cropCode: "",
  seasonCode: "",
  stageCode: "",
  activityType: "",
  inputCode: "",
  productCode: "",
  dateFrom: "",
  dateTo: "",
};

export default function ActivityUsagePage() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [report, setReport] = useState<ActivityUsageReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await reportsApi.activityUsage({
        projectId: filters.projectId || undefined,
        cropCode: filters.cropCode || undefined,
        seasonCode: filters.seasonCode || undefined,
        stageCode: filters.stageCode || undefined,
        activityType: filters.activityType || undefined,
        inputCode: filters.inputCode || undefined,
        productCode: filters.productCode || undefined,
        dateFrom: filters.dateFrom || undefined,
        dateTo: filters.dateTo || undefined,
        limit: 250,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load activity usage");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);

  const summary = report?.summary;
  return <div>
    <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Activity Usage</h1>
        <p className="mt-1 text-sm text-gray-500">Read-only input, product and package usage across crop activities.</p>
      </div>
      <button onClick={load} disabled={loading} className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">{loading ? "Loading..." : "Refresh"}</button>
    </div>
    {error && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    <div className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-5">
        <Field label="Project ID" value={filters.projectId} set={v => setFilters({ ...filters, projectId: v })} />
        <Field label="Crop" value={filters.cropCode} set={v => setFilters({ ...filters, cropCode: v })} />
        <Field label="Season" value={filters.seasonCode} set={v => setFilters({ ...filters, seasonCode: v })} />
        <Field label="Stage" value={filters.stageCode} set={v => setFilters({ ...filters, stageCode: v })} />
        <Field label="Activity" value={filters.activityType} set={v => setFilters({ ...filters, activityType: v })} />
        <Field label="Input code" value={filters.inputCode} set={v => setFilters({ ...filters, inputCode: v })} />
        <Field label="Product code" value={filters.productCode} set={v => setFilters({ ...filters, productCode: v })} />
        <Field label="From" type="date" value={filters.dateFrom} set={v => setFilters({ ...filters, dateFrom: v })} />
        <Field label="To" type="date" value={filters.dateTo} set={v => setFilters({ ...filters, dateTo: v })} />
        <button onClick={() => { setFilters(EMPTY_FILTERS); }} className="mt-5 rounded border px-3 py-2 text-sm">Clear filters</button>
      </div>
    </div>
    <div className="mb-6 grid gap-4 md:grid-cols-3">
      <Card label="Activities" value={summary?.activity_count ?? 0} />
      <Card label="Total cost" value={`₹${summary?.total_cost ?? "0"}`} />
      <Card label="Dosage variances" value={summary?.variance_count ?? 0} />
    </div>
    <div className="mb-6 grid gap-4 lg:grid-cols-2">
      <SummaryList title="Quantity by input" rows={(summary?.quantity_by_input || []).map(row => `${row.input_code}: ${row.quantity} ${row.unit}`)} />
      <SummaryList title="Quantity by product" rows={(summary?.quantity_by_product || []).map(row => `${row.product_code}${row.package_sku ? ` / ${row.package_sku}` : ""}: ${row.quantity} ${row.unit}`)} />
    </div>
    <div className="overflow-hidden rounded bg-white shadow">
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date","Crop/stage","Activity","Input","Product/package","Qty","Cost","Farmer/parcel"].map(h => <th key={h} className="p-3 text-left">{h}</th>)}</tr></thead>
        <tbody className="divide-y">
          {(report?.activities || []).map(row => <tr key={row.activity_id}>
            <td className="p-3 whitespace-nowrap">{row.activity_date || "-"}</td>
            <td className="p-3"><div>{row.crop_code} · {row.season_code}</div><div className="text-xs text-gray-500">{row.stage_code || "-"}</div></td>
            <td className="p-3">{row.activity_type}</td>
            <td className="p-3"><div>{row.input_name || row.input_code || "-"}</div><div className="font-mono text-xs text-gray-500">{row.input_code || ""}</div></td>
            <td className="p-3"><div className="font-mono text-xs">{row.product_code || "-"}</div><div className="font-mono text-xs text-gray-500">{row.package_sku || ""}</div></td>
            <td className="p-3"><div>{row.actual_quantity || row.quantity || "-"} {row.actual_quantity_unit || row.quantity_unit || ""}</div>{row.recommended_quantity && <div className="text-xs text-gray-500">Rec {row.recommended_quantity} {row.recommended_quantity_unit}</div>}</td>
            <td className="p-3">{row.cost_amount ? `₹${row.cost_amount}` : "-"}</td>
            <td className="p-3"><div>{row.farmer_name || row.farmer_id || "-"}</div><div className="text-xs text-gray-500">{row.parcel_label || row.parcel_id || ""}</div></td>
          </tr>)}
          {report && report.activities.length === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-400">No activity usage found.</td></tr>}
        </tbody>
      </table>
    </div>
  </div>;
}

function Field({ label, value, set, type = "text" }: { label: string; value: string; set: (value: string) => void; type?: string }) {
  return <label className="text-xs text-gray-500">{label}<input type={type} value={value} onChange={e => set(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}
function Card({ label, value }: { label: string; value: string | number }) { return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>; }
function SummaryList({ title, rows }: { title: string; rows: string[] }) { return <div className="rounded bg-white p-5 shadow"><h2 className="font-semibold text-gray-900">{title}</h2>{rows.length ? <ul className="mt-3 space-y-1 text-sm text-gray-700">{rows.slice(0, 8).map(row => <li key={row}>{row}</li>)}</ul> : <p className="mt-3 text-sm text-gray-400">No quantities yet.</p>}</div>; }
