"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { reportsApi, type ActivityUsageFilterOptionsResponse, type ActivityUsageReportResponse, type ActivityUsageRow } from "@/lib/api";
import { CopyLinkButton } from "@/components/copy-link-button";

const EMPTY_FILTERS = {
  projectId: "",
  farmerId: "",
  parcelId: "",
  cropCode: "",
  seasonCode: "",
  stageCode: "",
  activityType: "",
  inputCode: "",
  productCode: "",
  dateFrom: "",
  dateTo: "",
};

type Filters = typeof EMPTY_FILTERS;

function reportParams(filters: Filters, limit: number) {
  return {
    projectId: filters.projectId || undefined,
    farmerId: filters.farmerId || undefined,
    parcelId: filters.parcelId || undefined,
    cropCode: filters.cropCode || undefined,
    seasonCode: filters.seasonCode || undefined,
    stageCode: filters.stageCode || undefined,
    activityType: filters.activityType || undefined,
    inputCode: filters.inputCode || undefined,
    productCode: filters.productCode || undefined,
    dateFrom: filters.dateFrom || undefined,
    dateTo: filters.dateTo || undefined,
    limit,
  };
}

function activityUsageHref(filters: Filters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return `/activity-usage${query ? `?${query}` : ""}`;
}

function paramValue(searchParams: Record<string, string | string[] | undefined> | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = searchParams?.[key];
    if (Array.isArray(value)) return value[0] || "";
    if (value) return value;
  }
  return "";
}

function filtersFromSearchParams(searchParams?: Record<string, string | string[] | undefined>): Filters {
  return {
    projectId: paramValue(searchParams, "projectId", "project_id"),
    farmerId: paramValue(searchParams, "farmerId", "farmer_id"),
    parcelId: paramValue(searchParams, "parcelId", "parcel_id"),
    cropCode: paramValue(searchParams, "cropCode", "crop_code"),
    seasonCode: paramValue(searchParams, "seasonCode", "season_code"),
    stageCode: paramValue(searchParams, "stageCode", "stage_code"),
    activityType: paramValue(searchParams, "activityType", "activity_type"),
    inputCode: paramValue(searchParams, "inputCode", "input_code"),
    productCode: paramValue(searchParams, "productCode", "product_code"),
    dateFrom: paramValue(searchParams, "dateFrom", "date_from"),
    dateTo: paramValue(searchParams, "dateTo", "date_to"),
  };
}

export default function ActivityUsagePage({ searchParams }: { searchParams?: Record<string, string | string[] | undefined> }) {
  const [filters, setFilters] = useState<Filters>(() => filtersFromSearchParams(searchParams));
  const [options, setOptions] = useState<ActivityUsageFilterOptionsResponse | null>(null);
  const [report, setReport] = useState<ActivityUsageReportResponse | null>(null);
  const [selectedRow, setSelectedRow] = useState<ActivityUsageRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reportsApi
      .activityUsageFilterOptions()
      .then(setOptions)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load filter options"))
      .finally(() => setLoadingOptions(false));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await reportsApi.activityUsage(reportParams(filters, 250)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load activity usage");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);

  const exportCsv = useCallback(async () => {
    setExporting(true);
    setError(null);
    try {
      await reportsApi.downloadActivityUsageCsv(reportParams(filters, 5000));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to export activity usage CSV");
    } finally {
      setExporting(false);
    }
  }, [filters]);

  const filteredHref = activityUsageHref(filters);

  const summary = report?.summary;
  return <div>
    <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Activity Usage</h1>
        <p className="mt-1 text-sm text-gray-500">Read-only input, product and package usage across crop activities.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <CopyLinkButton href={filteredHref} label="Copy filtered link" className="rounded border px-4 py-2 text-sm hover:bg-gray-50" />
        <button onClick={exportCsv} disabled={exporting} className="rounded border px-4 py-2 text-sm disabled:opacity-50">{exporting ? "Exporting..." : "Export CSV"}</button>
        <button onClick={load} disabled={loading} className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">{loading ? "Loading..." : "Refresh"}</button>
      </div>
    </div>
    {error && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    <div className="mb-6 rounded bg-white p-5 shadow">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-gray-900">Filters</h2>
        <span className="text-xs text-gray-400">{loadingOptions ? "Loading options..." : "Options from logged activity data"}</span>
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        <SelectField label="Project" value={filters.projectId} set={v => setFilters({ ...filters, projectId: v })} options={(options?.projects || []).map(item => ({ value: item.id || "", label: item.label }))} />
        <SelectField label="Farmer" value={filters.farmerId} set={v => setFilters({ ...filters, farmerId: v })} options={(options?.farmers || []).map(item => ({ value: item.id || "", label: item.label }))} />
        <SelectField label="Parcel" value={filters.parcelId} set={v => setFilters({ ...filters, parcelId: v })} options={(options?.parcels || []).map(item => ({ value: item.id || "", label: item.label }))} />
        <SelectField label="Crop" value={filters.cropCode} set={v => setFilters({ ...filters, cropCode: v })} options={(options?.crops || []).map(value => ({ value, label: value }))} />
        <SelectField label="Season" value={filters.seasonCode} set={v => setFilters({ ...filters, seasonCode: v })} options={(options?.seasons || []).map(value => ({ value, label: value }))} />
        <SelectField label="Stage" value={filters.stageCode} set={v => setFilters({ ...filters, stageCode: v })} options={(options?.stages || []).map(item => ({ value: item.code || "", label: `${item.code} - ${item.label}` }))} />
        <SelectField label="Activity" value={filters.activityType} set={v => setFilters({ ...filters, activityType: v })} options={(options?.activity_types || []).map(value => ({ value, label: value }))} />
        <SelectField label="Input" value={filters.inputCode} set={v => setFilters({ ...filters, inputCode: v })} options={(options?.inputs || []).map(item => ({ value: item.code || "", label: `${item.code} - ${item.label}` }))} />
        <SelectField label="Product" value={filters.productCode} set={v => setFilters({ ...filters, productCode: v })} options={(options?.products || []).map(item => ({ value: item.code || "", label: item.code || item.label }))} />
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
    <p className="mb-2 text-xs text-gray-400">Click any activity row to inspect full traceability.</p>
    <div className="overflow-hidden rounded bg-white shadow">
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Date","Crop/stage","Activity","Input","Product/package","Qty","Cost","Farmer/parcel"].map(h => <th key={h} className="p-3 text-left">{h}</th>)}</tr></thead>
        <tbody className="divide-y">
          {(report?.activities || []).map(row => <tr key={row.activity_id} onClick={() => setSelectedRow(row)} className="cursor-pointer hover:bg-blue-50">
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
    {selectedRow && <ActivityUsageDetailPanel row={selectedRow} onClose={() => setSelectedRow(null)} />}
  </div>;
}

function SelectField({ label, value, set, options }: { label: string; value: string; set: (value: string) => void; options: Array<{ value: string; label: string }> }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={e => set(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">All</option>{options.filter(option => option.value).map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}
function Field({ label, value, set, type = "text" }: { label: string; value: string; set: (value: string) => void; type?: string }) {
  return <label className="text-xs text-gray-500">{label}<input type={type} value={value} onChange={e => set(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}
function Card({ label, value }: { label: string; value: string | number }) { return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>; }
function SummaryList({ title, rows }: { title: string; rows: string[] }) { return <div className="rounded bg-white p-5 shadow"><h2 className="font-semibold text-gray-900">{title}</h2>{rows.length ? <ul className="mt-3 space-y-1 text-sm text-gray-700">{rows.slice(0, 8).map(row => <li key={row}>{row}</li>)}</ul> : <p className="mt-3 text-sm text-gray-400">No quantities yet.</p>}</div>; }
function ActivityUsageDetailPanel({ row, onClose }: { row: ActivityUsageRow; onClose: () => void }) {
  return <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={onClose}>
    <aside className="h-full w-full max-w-2xl overflow-y-auto bg-white p-6 shadow-2xl" onClick={event => event.stopPropagation()}>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Activity traceability</h2>
          <p className="mt-1 text-sm text-gray-500">{row.activity_type} · {row.activity_date || "No date"}</p>
        </div>
        <button onClick={onClose} className="rounded border px-3 py-1 text-sm">Close</button>
      </div>
      <div className="space-y-4">
        <TraceSection title="Activity payload" rows={[
          ["Activity ID", row.activity_id],
          ["Activity date", row.activity_date],
          ["Type", row.activity_type],
          ["Input", [row.input_code, row.input_name].filter(Boolean).join(" - ")],
          ["Quantity", formatQuantity(row.quantity, row.quantity_unit)],
          ["Area applied", formatQuantity(row.area_applied, row.area_unit)],
          ["Cost", row.cost_amount ? `${row.cost_currency || "INR"} ${row.cost_amount}` : null],
          ["Notes", row.notes],
        ]} />
        <TraceSection title="Recommendation / rule linkage" rows={[
          ["Input rule ID", row.input_rule_id],
          ["Recommended quantity", formatQuantity(row.recommended_quantity, row.recommended_quantity_unit)],
          ["Actual quantity", formatQuantity(row.actual_quantity, row.actual_quantity_unit)],
          ["Variance reason", row.dosage_variance_reason],
        ]} action={row.input_rule_id ? <TraceActions href={`/input-rule-trace/${row.input_rule_id}`} primaryLabel="Open rule trace" /> : undefined} />
        <TraceSection title="Product / package linkage" rows={[
          ["Product ID", row.product_id],
          ["Product code", row.product_code],
          ["Package ID", row.package_id],
          ["Package SKU", row.package_sku],
        ]} action={row.product_code ? <TraceActions href={`/product-trace/${encodeURIComponent(row.product_code)}`} primaryLabel="Open product trace" /> : undefined} />
        <TraceSection title="Crop cycle / stage" rows={[
          ["Crop cycle ID", row.crop_cycle_id],
          ["Cycle status", row.crop_cycle_status],
          ["Workflow version ID", row.workflow_template_version_id],
          ["Crop", row.crop_code],
          ["Season", row.season_code],
          ["Stage code", row.stage_code],
          ["Stage instance ID", row.stage_instance_id],
          ["Stage name", row.stage_name],
          ["Stage order", row.stage_order != null ? String(row.stage_order) : null],
          ["Stage status", row.stage_status],
        ]} action={row.crop_cycle_id ? <TraceActions href={`/crop-cycle-trace/${row.crop_cycle_id}`} primaryLabel="Open cycle trace" /> : undefined} />
        <TraceSection title="Farmer / parcel" rows={[
          ["Farmer ID", row.farmer_id],
          ["Farmer name", row.farmer_name],
          ["Parcel ID", row.parcel_id],
          ["Parcel label", row.parcel_label],
          ["Project ID", row.project_id],
          ["Tenant", row.tenant_id],
        ]} action={<div className="flex flex-wrap gap-2">{row.farmer_id ? <TraceActions href={`/farmer-trace/${row.farmer_id}`} primaryLabel="Open farmer" /> : null}{row.parcel_id ? <TraceActions href={`/parcel-trace/${row.parcel_id}`} primaryLabel="Open parcel" secondary /> : null}</div>} />
        <TraceSection title="Logging / GPS" rows={[
          ["Logged by", row.logged_by],
          ["Logging method", row.logging_method],
          ["GPS", row.gps_lat && row.gps_lng ? `${row.gps_lat}, ${row.gps_lng}` : null],
          ["Created at", row.created_at],
          ["Updated at", row.updated_at],
        ]} />
        <div className="rounded border bg-gray-50 p-4">
          <h3 className="mb-2 font-semibold text-gray-900">Raw row payload</h3>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs text-gray-700">{JSON.stringify(row, null, 2)}</pre>
        </div>
      </div>
    </aside>
  </div>;
}


function TraceActions({ href, primaryLabel, secondary = false }: { href: string; primaryLabel: string; secondary?: boolean }) {
  return <div className="flex gap-2">
    <a href={href} className={secondary ? "rounded border px-3 py-1 text-xs text-gray-700" : "rounded bg-gray-900 px-3 py-1 text-xs text-white"}>{primaryLabel}</a>
    <CopyLinkButton href={href} className="rounded border px-3 py-1 text-xs text-gray-700 hover:bg-gray-50" />
  </div>;
}

function TraceSection({ title, rows, action }: { title: string; rows: Array<[string, string | number | null | undefined]>; action?: ReactNode }) {
  return <section className="rounded border p-4">
    <div className="mb-3 flex items-center justify-between gap-3"><h3 className="font-semibold text-gray-900">{title}</h3>{action}</div>
    <dl className="grid gap-2 text-sm md:grid-cols-2">
      {rows.map(([label, value]) => <div key={label}>
        <dt className="text-xs uppercase text-gray-400">{label}</dt>
        <dd className="break-words font-mono text-gray-800">{valueLabel(value)}</dd>
      </div>)}
    </dl>
  </section>;
}

function formatQuantity(quantity?: string | null, unit?: string | null) {
  if (!quantity) return null;
  return `${quantity}${unit ? ` ${unit}` : ""}`;
}

function valueLabel(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}
