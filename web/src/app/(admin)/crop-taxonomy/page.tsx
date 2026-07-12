
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  cropCatalogApi,
  type CropCatalogItemDto,
  type CropCatalogResponse,
  type CropPropagationTypeDto,
  type CropTaxonomyCsvValidationResponse,
  type CropTaxonomyImportHistory,
  type CropTaxonomyResponse,
} from "@/lib/api";

export default function CropTaxonomyPage() {
  const [taxonomy, setTaxonomy] = useState<CropTaxonomyResponse | null>(null);
  const [propagationTypes, setPropagationTypes] = useState<CropPropagationTypeDto[]>([]);
  const [catalog, setCatalog] = useState<CropCatalogResponse | null>(null);
  const [taxonomyFilter, setTaxonomyFilter] = useState("");
  const [propagationFilter, setPropagationFilter] = useState("");
  const [seasonFilter, setSeasonFilter] = useState("");
  const [selectedCropCode, setSelectedCropCode] = useState<string | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvReport, setCsvReport] = useState<CropTaxonomyCsvValidationResponse | null>(null);
  const [importHistory, setImportHistory] = useState<CropTaxonomyImportHistory | null>(null);
  const [historyStatus, setHistoryStatus] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      cropCatalogApi.taxonomy(),
      cropCatalogApi.propagationTypes(),
      cropCatalogApi.crops({ taxonomyCode: taxonomyFilter || undefined, propagationType: propagationFilter || undefined, season: seasonFilter || undefined }),
    ])
      .then(([taxonomyPayload, propagationPayload, cropPayload]) => {
        setTaxonomy(taxonomyPayload);
        setPropagationTypes(propagationPayload);
        setCatalog(cropPayload);
        setSelectedCropCode((current) => current && cropPayload.crops.some((crop) => crop.code === current) ? current : cropPayload.crops[0]?.code || null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load crop taxonomy"))
      .finally(() => setLoading(false));
  }, [taxonomyFilter, propagationFilter, seasonFilter]);

  useEffect(() => {
    loadImportHistory(historyStatus || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyStatus]);

  const loadImportHistory = (status?: string) => {
    setHistoryLoading(true);
    cropCatalogApi
      .taxonomyImportHistory({ status, limit: 10 })
      .then(setImportHistory)
      .catch(() => setImportHistory(null))
      .finally(() => setHistoryLoading(false));
  };

  const taxonomyNodes = useMemo(() => taxonomy?.nodes || [], [taxonomy]);
  const crops = catalog?.crops || [];
  const selectedCrop = crops.find((crop) => crop.code === selectedCropCode) || crops[0];
  const taxonomyByLevel = useMemo(() => {
    const groups = new Map<number, typeof taxonomyNodes>();
    taxonomyNodes.forEach((node) => {
      const existing = groups.get(node.level) || [];
      groups.set(node.level, [...existing, node]);
    });
    return Array.from(groups.entries()).sort(([left], [right]) => left - right);
  }, [taxonomyNodes]);
  const seasons = Array.from(new Set(crops.flatMap((crop) => crop.suitable_seasons || []))).sort();

  const downloadTemplate = () => {
    setCsvError(null);
    cropCatalogApi.downloadTaxonomyTemplate().catch((e) => setCsvError(e instanceof Error ? e.message : "Failed to download taxonomy template"));
  };

  const downloadExport = () => {
    setCsvError(null);
    cropCatalogApi.downloadTaxonomyExport().catch((e) => setCsvError(e instanceof Error ? e.message : "Failed to export taxonomy catalog"));
  };

  const validateCsv = async () => {
    if (!csvFile) {
      setCsvError("Choose a crop taxonomy CSV file first.");
      return;
    }
    setCsvBusy(true);
    setCsvError(null);
    setCsvReport(null);
    try {
      setCsvReport(await cropCatalogApi.validateTaxonomyCsv(csvFile));
      loadImportHistory(historyStatus || undefined);
    } catch (e) {
      setCsvError(e instanceof Error ? e.message : "Failed to validate taxonomy CSV");
    } finally {
      setCsvBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Crop Taxonomy</h1>
          <p className="mt-1 text-sm text-gray-500">Read-only crop classification, propagation options, and crop catalog metadata used by workflow templates.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select value={taxonomyFilter} onChange={(event) => setTaxonomyFilter(event.target.value)} className="rounded border px-3 py-2 text-sm">
            <option value="">All taxonomy</option>
            {taxonomyNodes.map((node) => <option key={node.code} value={node.code}>{node.code}</option>)}
          </select>
          <select value={propagationFilter} onChange={(event) => setPropagationFilter(event.target.value)} className="rounded border px-3 py-2 text-sm">
            <option value="">All propagation</option>
            {propagationTypes.map((type) => <option key={type.code} value={type.code}>{type.code}</option>)}
          </select>
          <select value={seasonFilter} onChange={(event) => setSeasonFilter(event.target.value)} className="rounded border px-3 py-2 text-sm">
            <option value="">All seasons</option>
            {seasons.map((season) => <option key={season} value={season}>{season}</option>)}
          </select>
        </div>
      </div>

      {error ? <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {loading ? <p className="text-sm text-gray-500">Loading crop taxonomy...</p> : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Taxonomy nodes" value={taxonomyNodes.length} />
        <Metric label="Relationships" value={taxonomy?.edges.length || 0} />
        <Metric label="Propagation types" value={propagationTypes.length} />
        <Metric label="Crops" value={catalog?.count || 0} />
      </div>

      <section className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        <p className="font-semibold">Safe import foundation</p>
        <p className="mt-1">Taxonomy CSV upload is validate-only for now. Backend reports planned creates/updates/errors, but does not mutate published taxonomy yet.</p>
      </section>

      <section className="rounded bg-white p-4 shadow">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="font-semibold text-gray-900">Taxonomy CSV validation</h2>
            <p className="mt-1 text-sm text-gray-500">Download the template, upload a CSV, and inspect row-level diagnostics before any future apply flow exists.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={downloadTemplate} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Download template</button>
            <button onClick={downloadExport} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Export current taxonomy</button>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input type="file" accept=".csv,text/csv" onChange={(event) => setCsvFile(event.target.files?.[0] || null)} className="text-sm" />
          <button onClick={validateCsv} disabled={csvBusy || !csvFile} className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300">
            {csvBusy ? "Validating..." : "Validate CSV"}
          </button>
          {csvFile ? <span className="text-xs text-gray-500">Selected: {csvFile.name}</span> : null}
        </div>
        {csvError ? <p className="mt-3 rounded bg-red-50 p-3 text-sm text-red-700">{csvError}</p> : null}
        {csvReport ? <CsvValidationReport report={csvReport} /> : null}
        <ImportHistoryPanel history={importHistory} loading={historyLoading} status={historyStatus} onStatusChange={setHistoryStatus} onRefresh={() => loadImportHistory(historyStatus || undefined)} />
      </section>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <section className="rounded bg-white p-4 shadow">
          <h2 className="font-semibold text-gray-900">Crop catalog</h2>
          <p className="mt-1 text-xs text-gray-500">Filtered by taxonomy, propagation, and season.</p>
          <div className="mt-4 space-y-2">
            {crops.map((crop) => (
              <button key={crop.code} onClick={() => setSelectedCropCode(crop.code)} className={`w-full rounded border p-3 text-left text-sm ${selectedCrop?.code === crop.code ? "border-green-500 bg-green-50" : "border-gray-100 hover:bg-gray-50"}`}>
                <p className="font-semibold text-gray-900">{crop.canonical_name}</p>
                <p className="font-mono text-xs text-gray-500">{crop.code}</p>
                <p className="mt-1 text-xs text-gray-500">{crop.suitable_seasons?.join(", ") || "No seasons"}</p>
              </button>
            ))}
            {!loading && crops.length === 0 ? <p className="rounded bg-gray-50 p-4 text-center text-sm text-gray-400">No crops match this filter.</p> : null}
          </div>
        </section>

        <div className="space-y-6">
          {selectedCrop ? <CropDetail crop={selectedCrop} /> : null}
          <section className="rounded bg-white p-4 shadow">
            <h2 className="font-semibold text-gray-900">Taxonomy hierarchy</h2>
            <div className="mt-4 space-y-4">
              {taxonomyByLevel.map(([level, nodes]) => (
                <div key={level}>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Level {level}</p>
                  <div className="flex flex-wrap gap-2">
                    {nodes.map((node) => <TaxonomyBadge key={node.code} node={node} />)}
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded bg-white p-4 shadow">
            <h2 className="font-semibold text-gray-900">Propagation types</h2>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {propagationTypes.map((type) => (
                <div key={type.code} className="rounded border p-3 text-sm">
                  <p className="font-semibold text-gray-900">{type.code}</p>
                  <p className="mt-1 text-gray-700">{type.canonical_name}</p>
                  <p className="mt-1 text-xs text-gray-500">{type.establishment_type}</p>
                  {type.description ? <p className="mt-2 text-xs text-gray-500">{type.description}</p> : null}
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-4 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function TaxonomyBadge({ node }: { node: CropTaxonomyResponse["nodes"][number] }) {
  return <div className="rounded border bg-gray-50 px-3 py-2 text-xs">
    <p className="font-semibold text-gray-900">{node.code}</p>
    <p className="text-gray-600">{node.canonical_name}</p>
    <p className="mt-1 text-gray-400">{node.node_type}</p>
  </div>;
}

function CropDetail({ crop }: { crop: CropCatalogItemDto }) {
  return <section className="rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-xl font-bold text-gray-900">{crop.canonical_name}</h2>
        <p className="mt-1 font-mono text-xs text-gray-500">{crop.code}</p>
        {crop.scientific_name ? <p className="mt-1 text-sm italic text-gray-600">{crop.scientific_name}</p> : null}
      </div>
      <span className="rounded bg-green-50 px-3 py-1 text-xs font-semibold text-green-800">{crop.typical_duration_days || "?"} days</span>
    </div>
    <div className="mt-4 grid gap-4 md:grid-cols-2">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">Taxonomy assignments</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {crop.taxonomy.map((node) => <span key={node.code} className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-800">{node.code}{node.is_primary ? " ? primary" : ""}</span>)}
        </div>
      </div>
      <div>
        <h3 className="text-sm font-semibold text-gray-900">Propagation options</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {crop.propagation_options.map((option) => <span key={`${option.code}-${option.season_code || "all"}`} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{option.code}{option.is_default ? " ? default" : ""}</span>)}
        </div>
      </div>
    </div>
  </section>;
}

function CsvValidationReport({ report }: { report: CropTaxonomyCsvValidationResponse }) {
  const rowsWithIssues = report.rows.filter((row) => row.errors.length || row.warnings.length);
  return <div className="mt-4 rounded border bg-gray-50 p-4">
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <p className="font-semibold text-gray-900">Validation result: {report.can_apply ? "Ready for future apply" : "Needs fixes"}</p>
        <p className="mt-1 text-xs text-gray-500">{report.message}</p>
      </div>
      <span className="rounded bg-white px-3 py-1 text-xs font-semibold text-gray-700">{report.mode}</span>
    </div>
    <div className="mt-4 grid gap-2 md:grid-cols-6">
      <Metric label="Rows" value={report.summary.total} />
      <Metric label="Create" value={report.summary.create} />
      <Metric label="Update" value={report.summary.update} />
      <Metric label="Unchanged" value={report.summary.unchanged} />
      <Metric label="Invalid" value={report.summary.invalid} />
      <Metric label="Errors" value={report.summary.errors} />
    </div>
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="text-gray-500">
          <tr>
            <th className="px-2 py-2">Row</th>
            <th className="px-2 py-2">Code</th>
            <th className="px-2 py-2">Action</th>
            <th className="px-2 py-2">Diagnostics</th>
          </tr>
        </thead>
        <tbody>
          {report.rows.slice(0, 25).map((row) => (
            <tr key={`${row.row_number}-${row.code}`} className="border-t bg-white">
              <td className="px-2 py-2">{row.row_number}</td>
              <td className="px-2 py-2 font-mono">{row.code || "-"}</td>
              <td className="px-2 py-2"><span className={`rounded px-2 py-1 ${row.action === "INVALID" ? "bg-red-50 text-red-700" : row.action === "CREATE" ? "bg-green-50 text-green-700" : row.action === "UPDATE" ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-600"}`}>{row.action}</span></td>
              <td className="px-2 py-2">
                {[...row.errors, ...row.warnings].length ? (
                  <ul className="space-y-1">
                    {[...row.errors, ...row.warnings].map((item, index) => <li key={`${item.code}-${index}`}><span className="font-semibold">{item.field}/{item.code}:</span> {item.message}</li>)}
                  </ul>
                ) : <span className="text-gray-400">No issues</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {report.rows.length > 25 ? <p className="mt-2 text-xs text-gray-500">Showing first 25 rows of {report.rows.length}.</p> : null}
      {rowsWithIssues.length ? <p className="mt-2 text-xs text-amber-700">{rowsWithIssues.length} row(s) contain warnings or errors.</p> : null}
    </div>
  </div>;
}

function ImportHistoryPanel({ history, loading, status, onStatusChange, onRefresh }: { history: CropTaxonomyImportHistory | null; loading: boolean; status: string; onStatusChange: (value: string) => void; onRefresh: () => void }) {
  const imports = history?.imports || [];
  return <div className="mt-6 border-t pt-4">
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h3 className="font-semibold text-gray-900">Recent taxonomy imports</h3>
        <p className="mt-1 text-xs text-gray-500">Persisted validation batches, including invalid uploads, for review and future apply support.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <select value={status} onChange={(event) => onStatusChange(event.target.value)} className="rounded border px-3 py-2 text-sm">
          <option value="">All statuses</option>
          <option value="VALIDATED">Validated</option>
          <option value="INVALID">Invalid</option>
          <option value="APPLIED">Applied</option>
          <option value="EXPIRED">Expired</option>
          <option value="STALE">Stale</option>
        </select>
        <button onClick={onRefresh} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Refresh</button>
      </div>
    </div>
    {loading ? <p className="mt-3 text-sm text-gray-500">Loading import history...</p> : null}
    {!loading && imports.length === 0 ? <p className="mt-3 rounded bg-gray-50 p-3 text-sm text-gray-500">No taxonomy import batches found.</p> : null}
    {imports.length ? <div className="mt-4 overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="text-gray-500">
          <tr>
            <th className="px-2 py-2">Created</th>
            <th className="px-2 py-2">File</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2">Summary</th>
            <th className="px-2 py-2">Batch</th>
          </tr>
        </thead>
        <tbody>
          {imports.map((item) => (
            <tr key={item.batch_id} className="border-t bg-white">
              <td className="px-2 py-2 whitespace-nowrap">{new Date(item.created_at).toLocaleString()}</td>
              <td className="px-2 py-2">{item.file_name || "-"}</td>
              <td className="px-2 py-2"><StatusPill status={item.status} /></td>
              <td className="px-2 py-2">
                <span>{item.report?.summary?.total ?? 0} rows</span>
                <span className="ml-2 text-green-700">+{item.report?.summary?.create ?? 0}</span>
                <span className="ml-2 text-amber-700">~{item.report?.summary?.update ?? 0}</span>
                <span className="ml-2 text-red-700">{item.report?.summary?.errors ?? 0} errors</span>
              </td>
              <td className="px-2 py-2 font-mono text-[11px] text-gray-500">{item.batch_id.slice(0, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div> : null}
  </div>;
}

function StatusPill({ status }: { status: string }) {
  const tone = status === "VALIDATED" ? "bg-green-50 text-green-700" : status === "INVALID" ? "bg-red-50 text-red-700" : status === "APPLIED" ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-1 font-semibold ${tone}`}>{status}</span>;
}
