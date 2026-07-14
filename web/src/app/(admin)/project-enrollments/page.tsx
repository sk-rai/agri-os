"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { projectsApi, reportsApi, type ProjectEnrollmentImportBatch, type ProjectEnrollmentImportHistory, type ProjectEnrollmentReportResponse } from "@/lib/api";

function paramValue(searchParams: Record<string, string | string[] | undefined> | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = searchParams?.[key];
    if (Array.isArray(value)) return value[0] || "";
    if (value) return value;
  }
  return "";
}

type Filters = { query: string; projectId: string; farmerId: string; status: string; enrollmentSource: string };

function filtersFromSearch(searchParams?: Record<string, string | string[] | undefined>): Filters {
  return {
    query: paramValue(searchParams, "q", "query"),
    projectId: paramValue(searchParams, "projectId", "project_id"),
    farmerId: paramValue(searchParams, "farmerId", "farmer_id"),
    status: paramValue(searchParams, "status"),
    enrollmentSource: paramValue(searchParams, "enrollmentSource", "enrollment_source"),
  };
}

export default function ProjectEnrollmentsPage({ searchParams }: { searchParams?: Record<string, string | string[] | undefined> }) {
  const [filters, setFilters] = useState<Filters>(() => filtersFromSearch(searchParams));
  const [submitted, setSubmitted] = useState<Filters>(() => filtersFromSearch(searchParams));
  const [report, setReport] = useState<ProjectEnrollmentReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importHistory, setImportHistory] = useState<ProjectEnrollmentImportHistory | null>(null);
  const [latestImport, setLatestImport] = useState<ProjectEnrollmentImportBatch | null>(null);
  const [importReason, setImportReason] = useState("Bulk project enrollment from CSV");
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setReport(await reportsApi.projectEnrollments({
        query: next.query || undefined,
        projectId: next.projectId || undefined,
        farmerId: next.farmerId || undefined,
        status: next.status || undefined,
        enrollmentSource: next.enrollmentSource || undefined,
        limit: 100,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project enrollments");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(submitted); }, [load, submitted]);

  const loadImportHistory = useCallback(async (projectId: string) => {
    if (!projectId) {
      setImportHistory(null);
      return;
    }
    try {
      setImportHistory(await projectsApi.enrollmentImportHistory(projectId, { limit: 10 }));
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Failed to load enrollment import history");
    }
  }, []);

  useEffect(() => { loadImportHistory(submitted.projectId); }, [loadImportHistory, submitted.projectId]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted({ ...filters });
  }

  function clear() {
    const empty = { query: "", projectId: "", farmerId: "", status: "", enrollmentSource: "" };
    setFilters(empty);
    setSubmitted(empty);
  }

  async function downloadTemplate() {
    if (!submitted.projectId) {
      setImportError("Set a Project ID filter before downloading the project enrollment template.");
      return;
    }
    setImportError(null);
    await projectsApi.downloadEnrollmentTemplate(submitted.projectId);
  }

  async function validateCsv() {
    if (!submitted.projectId) {
      setImportError("Set a Project ID filter before validating a project enrollment CSV.");
      return;
    }
    if (!selectedFile) {
      setImportError("Choose a CSV file first.");
      return;
    }
    setImportBusy(true);
    setImportError(null);
    try {
      const batch = await projectsApi.validateEnrollmentCsv(submitted.projectId, selectedFile);
      setLatestImport(batch);
      await loadImportHistory(submitted.projectId);
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Failed to validate enrollment CSV");
    } finally {
      setImportBusy(false);
    }
  }

  async function applyImport(batchId: string) {
    if (!submitted.projectId) return;
    setImportBusy(true);
    setImportError(null);
    try {
      const applied = await projectsApi.applyEnrollmentImport(submitted.projectId, batchId, importReason || "Bulk project enrollment from CSV");
      setLatestImport(applied);
      await loadImportHistory(submitted.projectId);
      await load(submitted);
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Failed to apply enrollment import");
    } finally {
      setImportBusy(false);
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Project Enrollments</h1>
      <p className="mt-1 text-sm text-gray-500">Read-only visibility into farmer/project memberships, source, linked parcels, and Android launch routing.</p>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-5">
        <label className="text-xs text-gray-500 md:col-span-2">Search<input value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} placeholder="Farmer, mobile, project, source, UUID" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Project ID<input value={filters.projectId} onChange={(event) => setFilters({ ...filters, projectId: event.target.value })} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Farmer ID<input value={filters.farmerId} onChange={(event) => setFilters({ ...filters, farmerId: event.target.value })} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">All</option><option value="ACTIVE">ACTIVE</option><option value="PENDING">PENDING</option><option value="COMPLETED">COMPLETED</option><option value="CANCELLED">CANCELLED</option><option value="ARCHIVED">ARCHIVED</option></select></label>
      </div>
      <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-end">
        <label className="flex-1 text-xs text-gray-500">Enrollment source<input value={filters.enrollmentSource} onChange={(event) => setFilters({ ...filters, enrollmentSource: event.target.value })} placeholder="sync, import, invite, web" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-5 py-2 text-sm font-medium text-white disabled:opacity-50">{loading ? "Loading..." : "Apply filters"}</button>
        <button type="button" onClick={clear} className="rounded border px-5 py-2 text-sm">Clear</button>
      </div>
    </form>

    {error && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}



    <section className="mb-6 rounded bg-white p-5 shadow">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Bulk enrollment CSV</h2>
          <p className="mt-1 text-sm text-gray-500">Validate and apply farmer enrollments for one project. Set the Project ID filter above to activate this panel.</p>
        </div>
        <button type="button" onClick={downloadTemplate} disabled={!submitted.projectId || importBusy} className="rounded border px-4 py-2 text-sm disabled:opacity-50">Download template</button>
      </div>

      {!submitted.projectId ? <p className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-800">Choose a Project ID filter, then apply filters. CSV imports are intentionally project-scoped.</p> : null}
      {importError ? <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{importError}</p> : null}

      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <label className="text-xs text-gray-500">CSV file<input type="file" accept=".csv,text/csv" onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} disabled={!submitted.projectId || importBusy} className="mt-1 w-full rounded border p-2 text-sm text-gray-900 disabled:opacity-50" /></label>
        <label className="text-xs text-gray-500">Apply reason<input value={importReason} onChange={(event) => setImportReason(event.target.value)} disabled={!submitted.projectId || importBusy} className="mt-1 w-full rounded border p-2 text-sm text-gray-900 disabled:opacity-50" /></label>
        <button type="button" onClick={validateCsv} disabled={!submitted.projectId || !selectedFile || importBusy} className="rounded bg-gray-900 px-5 py-2 text-sm font-medium text-white disabled:opacity-50">{importBusy ? "Working..." : "Validate CSV"}</button>
      </div>

      {latestImport ? <ImportSummary batch={latestImport} onApply={applyImport} busy={importBusy} /> : null}

      {importHistory?.imports.length ? <div className="mt-5 overflow-hidden rounded border">
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Batch", "Status", "Summary", "Created", "Action"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {importHistory.imports.map((batch) => <tr key={batch.batch_id}>
              <td className="p-3"><div className="font-medium text-gray-900">{batch.file_name || "CSV import"}</div><div className="font-mono text-[11px] text-gray-400">{batch.batch_id}</div></td>
              <td className="p-3"><span className={`rounded px-2 py-1 text-xs ${batch.status === "VALIDATED" ? "bg-blue-50 text-blue-700" : batch.status === "APPLIED" ? "bg-green-50 text-green-700" : batch.status === "INVALID" ? "bg-red-50 text-red-700" : "bg-gray-100 text-gray-600"}`}>{batch.status}</span></td>
              <td className="p-3 text-xs text-gray-600">{batch.report.summary.total} rows - {batch.report.summary.create} create - {batch.report.summary.update} update - {batch.report.summary.errors} errors</td>
              <td className="p-3 text-xs text-gray-500">{batch.created_at}</td>
              <td className="p-3">{batch.can_apply ? <button type="button" onClick={() => applyImport(batch.batch_id)} disabled={importBusy} className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">Apply</button> : <span className="text-xs text-gray-400">No action</span>}</td>
            </tr>)}
          </tbody>
        </table>
      </div> : submitted.projectId ? <p className="mt-4 text-sm text-gray-400">No CSV import history for this project yet.</p> : null}
    </section>
    <div className="mb-6 grid gap-4 md:grid-cols-5">
      <Metric label="Enrollments" value={report?.summary.count ?? 0} />
      <Metric label="Active" value={report?.summary.active_count ?? 0} />
      <Metric label="Pending" value={report?.summary.pending_count ?? 0} />
      <Metric label="Project picker" value={report?.summary.project_picker_count ?? 0} />
      <Metric label="Profile completion" value={report?.summary.profile_completion_count ?? 0} />
    </div>

    <div className="overflow-hidden rounded bg-white shadow">
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Farmer", "Project", "Status/source", "Parcels", "Launch", "Trace"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {(report?.enrollments || []).map((row) => <tr key={row.id}>
            <td className="p-3"><div className="font-medium text-gray-900">{row.farmer_name || "Unnamed farmer"}</div><div className="text-xs text-gray-500">{row.farmer_mobile || "-"}</div><div className="font-mono text-[11px] text-gray-400">{row.farmer_id}</div></td>
            <td className="p-3"><div className="font-medium text-gray-900">{row.project_name}</div><div className="text-xs text-gray-500">{row.project_status || "-"}</div><div className="font-mono text-[11px] text-gray-400">{row.project_id}</div></td>
            <td className="p-3"><span className={`rounded px-2 py-1 text-xs ${row.status === "ACTIVE" ? "bg-green-50 text-green-700" : row.status === "PENDING" ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-600"}`}>{row.status}</span><div className="mt-2 text-xs text-gray-500">{row.enrollment_method}</div><div className="text-xs text-gray-400">{row.enrollment_source || "No source"}</div></td>
            <td className="p-3"><div>{row.parcel_labels.length ? row.parcel_labels.join(", ") : "No linked parcel"}</div><div className="text-xs text-gray-400">{row.parcel_ids.length} linked</div></td>
            <td className="p-3"><div className="font-medium text-gray-900">{row.launch_context.recommended_navigation}</div><div className="text-xs text-gray-500">{row.launch_context.active_project_count} active project(s)</div>{row.launch_context.profile_completion.missing_fields.length ? <div className="text-xs text-amber-700">Missing: {row.launch_context.profile_completion.missing_fields.join(", ")}</div> : <div className="text-xs text-green-700">Profile ready</div>}</td>
            <td className="p-3"><div className="flex flex-col gap-1"><Link href={`/farmer-trace/${row.farmer_id}`} className="text-blue-600 hover:underline">Farmer trace</Link><Link href={`/project-trace/${row.project_id}`} className="text-blue-600 hover:underline">Project trace</Link></div></td>
          </tr>)}
          {!loading && (report?.enrollments.length || 0) === 0 && <tr><td colSpan={6} className="p-8 text-center text-gray-400">No project enrollments match these filters.</td></tr>}
        </tbody>
      </table>
    </div>
  </div>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded bg-white p-4 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p></div>;
}


function ImportSummary({ batch, onApply, busy }: { batch: ProjectEnrollmentImportBatch; onApply: (batchId: string) => void; busy: boolean }) {
  const rowsWithIssues = batch.report.rows.filter((row) => row.errors.length || row.warnings.length).slice(0, 8);
  return <div className="mt-5 rounded border bg-gray-50 p-4">
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <p className="font-medium text-gray-900">Latest validation: {batch.status}</p>
        <p className="mt-1 text-sm text-gray-600">{batch.report.message}</p>
        <p className="mt-1 text-xs text-gray-500">{batch.report.summary.total} rows - {batch.report.summary.create} create - {batch.report.summary.update} update - {batch.report.summary.invalid} invalid - {batch.report.summary.errors} errors</p>
      </div>
      {batch.can_apply ? <button type="button" onClick={() => onApply(batch.batch_id)} disabled={busy} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply import</button> : null}
    </div>
    {batch.report.applied_counts ? <div className="mt-3 grid gap-2 text-xs md:grid-cols-4">
      {Object.entries(batch.report.applied_counts).map(([key, value]) => <div key={key} className="rounded bg-white p-2"><span className="text-gray-400">{key}</span><div className="font-semibold text-gray-900">{String(value)}</div></div>)}
    </div> : null}
    {rowsWithIssues.length ? <div className="mt-4 space-y-2">
      <p className="text-xs font-semibold uppercase text-gray-400">Rows needing attention</p>
      {rowsWithIssues.map((row) => <div key={row.row_number} className="rounded bg-white p-3 text-xs">
        <div className="font-medium text-gray-800">Row {row.row_number} - {row.mobile_number || "No mobile"} - {row.action}</div>
        {row.errors.map((issue) => <div key={`e-${issue.field}-${issue.code}`} className="mt-1 text-red-700">Error: {issue.field} - {issue.message}</div>)}
        {row.warnings.map((issue) => <div key={`w-${issue.field}-${issue.code}`} className="mt-1 text-amber-700">Warning: {issue.field} - {issue.message}</div>)}
      </div>)}
    </div> : null}
  </div>;
}
