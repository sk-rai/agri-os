"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { reportsApi, type FinanceAnalyticsSummaryResponse } from "@/lib/api";

const EMPTY_FILTERS = {
  projectId: "",
  farmerId: "",
  parcelId: "",
  cropCode: "",
  seasonCode: "",
  seasonYear: "",
  activityDateFrom: "",
  activityDateTo: "",
  period: "month" as "month" | "quarter" | "year",
};

type Filters = typeof EMPTY_FILTERS;

function params(filters: Filters) {
  return {
    projectId: filters.projectId || undefined,
    farmerId: filters.farmerId || undefined,
    parcelId: filters.parcelId || undefined,
    cropCode: filters.cropCode || undefined,
    seasonCode: filters.seasonCode || undefined,
    seasonYear: filters.seasonYear || undefined,
    activityDateFrom: filters.activityDateFrom || undefined,
    activityDateTo: filters.activityDateTo || undefined,
    period: filters.period,
    limit: 1000,
  };
}

export default function FinanceAnalyticsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [payload, setPayload] = useState<FinanceAnalyticsSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPayload(await reportsApi.financeAnalytics(params(filters)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load finance analytics");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  return <div>
    <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Finance Analytics</h1>
        <p className="mt-1 text-sm text-gray-500">Backend-computed income, expense, P&L, stage-cost, category, and period summaries.</p>
      </div>
      <button onClick={load} disabled={loading} className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">{loading ? "Loading..." : "Refresh"}</button>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-gray-900">Filters</h2>
        <span className="text-xs text-gray-400">Uses /api/v1/crop-cycles/finance/analytics-summary</span>
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        <Field label="Project ID" value={filters.projectId} set={v => setFilters({ ...filters, projectId: v })} />
        <Field label="Farmer ID" value={filters.farmerId} set={v => setFilters({ ...filters, farmerId: v })} />
        <Field label="Parcel ID" value={filters.parcelId} set={v => setFilters({ ...filters, parcelId: v })} />
        <Field label="Crop" value={filters.cropCode} set={v => setFilters({ ...filters, cropCode: v.toUpperCase() })} placeholder="RICE" />
        <Field label="Season" value={filters.seasonCode} set={v => setFilters({ ...filters, seasonCode: v.toUpperCase() })} placeholder="KHARIF" />
        <Field label="Season year" value={filters.seasonYear} set={v => setFilters({ ...filters, seasonYear: v })} placeholder="2026" />
        <Field label="Activity from" type="date" value={filters.activityDateFrom} set={v => setFilters({ ...filters, activityDateFrom: v })} />
        <Field label="Activity to" type="date" value={filters.activityDateTo} set={v => setFilters({ ...filters, activityDateTo: v })} />
        <label className="text-xs text-gray-500">Period<select value={filters.period} onChange={e => setFilters({ ...filters, period: e.target.value as Filters["period"] })} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="month">Month</option><option value="quarter">Quarter</option><option value="year">Year</option></select></label>
        <div className="mt-5 flex gap-2">
          <button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply</button>
          <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="rounded border px-4 py-2 text-sm">Reset</button>
        </div>
      </div>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading finance analytics...</p> : null}

    {payload && !loading ? <>
      <div className="mb-6 grid gap-4 md:grid-cols-5">
        <Card label="Cycles" value={payload.totals.cycle_count} />
        <Card label="Activities" value={payload.totals.activity_count} />
        <Card label="Income" value={money(payload.totals.total_income)} tone="green" />
        <Card label="Expenses" value={money(payload.totals.total_expenses)} tone="amber" />
        <Card label="P&L" value={money(payload.totals.profit_or_loss)} tone={Number(payload.totals.profit_or_loss) >= 0 ? "green" : "red"} />
      </div>

      <div className="mb-6 rounded bg-blue-50 p-4 text-sm text-blue-900">
        Formula is fixed by backend: <span className="font-mono">{payload.fixed_formula}</span>. Admin/web renders only; it does not compute P&L locally.
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Table title="Crop / season / year P&L" rows={payload.cycle_summary_groups} columns={["crop_code", "season_code", "season_year", "cycle_count", "total_income", "total_expenses", "profit_or_loss"]} />
        <Table title="Stage cost groups" rows={payload.stage_cost_groups} columns={["crop_code", "season_code", "season_year", "stage_code", "activity_count", "actual_expense"]} />
        <Table title="Activity period groups" rows={payload.activity_period_groups} columns={["period", "crop_code", "season_code", "activity_count", "actual_expense"]} />
        <Table title="Expense category groups" rows={payload.expense_category_groups} columns={["expense_category", "crop_code", "season_code", "activity_count", "actual_expense"]} />
      </div>

      {payload.notes?.length ? <div className="mt-6 rounded bg-white p-5 text-sm text-gray-600 shadow">
        <h2 className="mb-2 font-semibold text-gray-900">Notes</h2>
        <ul className="list-disc space-y-1 pl-5">{payload.notes.map(note => <li key={note}>{note}</li>)}</ul>
      </div> : null}
    </> : null}
  </div>;
}

function Field({ label, value, set, type = "text", placeholder }: { label: string; value: string; set: (value: string) => void; type?: string; placeholder?: string }) {
  return <label className="text-xs text-gray-500">{label}<input type={type} value={value} placeholder={placeholder} onChange={e => set(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Card({ label, value, tone = "slate" }: { label: string; value: string | number; tone?: "slate" | "green" | "amber" | "red" }) {
  const tones = { slate: "bg-white text-gray-900", green: "bg-green-50 text-green-900", amber: "bg-amber-50 text-amber-900", red: "bg-red-50 text-red-900" };
  return <div className={`rounded p-5 shadow ${tones[tone]}`}><p className="text-xs uppercase opacity-60">{label}</p><p className="mt-2 text-2xl font-bold">{value}</p></div>;
}

function Table({ title, rows, columns }: { title: string; rows: Array<Record<string, unknown>>; columns: string[] }) {
  return <section className="overflow-hidden rounded bg-white shadow">
    <div className="border-b p-5">
      <h2 className="text-lg font-bold text-gray-900">{title}</h2>
      <p className="text-sm text-gray-500">{rows.length} group(s)</p>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr>{columns.map(column => <th key={column} className="p-3">{column.replaceAll("_", " ")}</th>)}</tr></thead>
        <tbody className="divide-y">
          {rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column} className="whitespace-nowrap p-3 text-gray-800">{format(row[column])}</td>)}</tr>)}
          {rows.length === 0 ? <tr><td colSpan={columns.length} className="p-6 text-center text-gray-400">No groups found.</td></tr> : null}
        </tbody>
      </table>
    </div>
  </section>;
}

function format(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function money(value: string) {
  return `₹${value}`;
}
