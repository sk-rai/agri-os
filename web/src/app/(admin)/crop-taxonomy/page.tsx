
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  cropCatalogApi,
  type CropCatalogCsvValidationResponse,
  type CropCatalogImportHistory,
  type CropCatalogItemDto,
  type CropCatalogResponse,
  type CropPropagationCsvValidationResponse,
  type CropPropagationImportHistory,
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
  const [catalogRefresh, setCatalogRefresh] = useState(0);
  const [cropCsvFile, setCropCsvFile] = useState<File | null>(null);
  const [cropCsvReport, setCropCsvReport] = useState<CropCatalogCsvValidationResponse | null>(null);
  const [cropImportHistory, setCropImportHistory] = useState<CropCatalogImportHistory | null>(null);
  const [cropHistoryStatus, setCropHistoryStatus] = useState("");
  const [cropHistoryLoading, setCropHistoryLoading] = useState(false);
  const [cropCsvBusy, setCropCsvBusy] = useState(false);
  const [cropCsvError, setCropCsvError] = useState<string | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvReport, setCsvReport] = useState<CropTaxonomyCsvValidationResponse | null>(null);
  const [importHistory, setImportHistory] = useState<CropTaxonomyImportHistory | null>(null);
  const [historyStatus, setHistoryStatus] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [propCsvFile, setPropCsvFile] = useState<File | null>(null);
  const [propCsvReport, setPropCsvReport] = useState<CropPropagationCsvValidationResponse | null>(null);
  const [propImportHistory, setPropImportHistory] = useState<CropPropagationImportHistory | null>(null);
  const [propHistoryStatus, setPropHistoryStatus] = useState("");
  const [propHistoryLoading, setPropHistoryLoading] = useState(false);
  const [propCsvBusy, setPropCsvBusy] = useState(false);
  const [propCsvError, setPropCsvError] = useState<string | null>(null);
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
  }, [taxonomyFilter, propagationFilter, seasonFilter, catalogRefresh]);

  useEffect(() => {
    loadCropImportHistory(cropHistoryStatus || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cropHistoryStatus]);

  useEffect(() => {
    loadImportHistory(historyStatus || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyStatus]);

  useEffect(() => {
    loadPropagationImportHistory(propHistoryStatus || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propHistoryStatus]);

  const loadCropImportHistory = (status?: string) => {
    setCropHistoryLoading(true);
    cropCatalogApi
      .cropImportHistory({ status, limit: 10 })
      .then(setCropImportHistory)
      .catch(() => setCropImportHistory(null))
      .finally(() => setCropHistoryLoading(false));
  };

  const loadImportHistory = (status?: string) => {
    setHistoryLoading(true);
    cropCatalogApi
      .taxonomyImportHistory({ status, limit: 10 })
      .then(setImportHistory)
      .catch(() => setImportHistory(null))
      .finally(() => setHistoryLoading(false));
  };

  const loadPropagationImportHistory = (status?: string) => {
    setPropHistoryLoading(true);
    cropCatalogApi
      .propagationImportHistory({ status, limit: 10 })
      .then(setPropImportHistory)
      .catch(() => setPropImportHistory(null))
      .finally(() => setPropHistoryLoading(false));
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

  const validateCropCsv = async () => {
    if (!cropCsvFile) {
      setCropCsvError("Choose a crop catalog CSV file first.");
      return;
    }
    setCropCsvBusy(true);
    setCropCsvError(null);
    setCropCsvReport(null);
    try {
      setCropCsvReport(await cropCatalogApi.validateCropCsv(cropCsvFile));
      loadCropImportHistory(cropHistoryStatus || undefined);
    } catch (e) {
      setCropCsvError(e instanceof Error ? e.message : "Failed to validate crop CSV");
    } finally {
      setCropCsvBusy(false);
    }
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

  const validatePropagationCsv = async () => {
    if (!propCsvFile) {
      setPropCsvError("Choose a crop propagation CSV file first.");
      return;
    }
    setPropCsvBusy(true);
    setPropCsvError(null);
    setPropCsvReport(null);
    try {
      setPropCsvReport(await cropCatalogApi.validatePropagationCsv(propCsvFile));
      loadPropagationImportHistory(propHistoryStatus || undefined);
    } catch (e) {
      setPropCsvError(e instanceof Error ? e.message : "Failed to validate propagation CSV");
    } finally {
      setPropCsvBusy(false);
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
        <p className="mt-1">Crop, taxonomy, and propagation CSV uploads validate row-level diagnostics, persist import batches, and require an explicit admin apply step before mutating master data.</p>
      </section>

      <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="font-semibold">Recommended import order</p>
            <p className="mt-1 text-amber-900">Use this order when onboarding a new client/project so reference links validate cleanly and Android receives a coherent published contract.</p>
          </div>
          <a href="https://github.com/sk-rai/agri-os/blob/main/docs/admin-import-configuration-roadmap.md" target="_blank" rel="noreferrer" className="text-xs font-semibold text-amber-800 underline">Docs: admin import roadmap</a>
        </div>
        <ol className="mt-3 grid gap-2 md:grid-cols-4">
          <li className="rounded bg-white/70 p-3"><span className="font-semibold">1. Taxonomy</span><br /><span className="text-xs">Crop groups, economic class, botanical or client tags.</span></li>
          <li className="rounded bg-white/70 p-3"><span className="font-semibold">2. Propagation</span><br /><span className="text-xs">Direct seeded, nursery transplant, sett, tuber, cutting, sapling, etc.</span></li>
          <li className="rounded bg-white/70 p-3"><span className="font-semibold">3. Crops</span><br /><span className="text-xs">Crop rows link to category, taxonomy, seasons, soils, and propagation options.</span></li>
          <li className="rounded bg-white/70 p-3"><span className="font-semibold">4. Workflows</span><br /><span className="text-xs">Create draft stages/recommendations, validate, then publish for Android.</span></li>
        </ol>
      </section>

      <section className="rounded bg-white p-4 shadow">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="font-semibold text-gray-900">Crop catalog CSV validation</h2>
            <p className="mt-1 text-sm text-gray-500">Create or update crops and link them to category, taxonomy nodes, and allowed propagation options.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => cropCatalogApi.downloadCropTemplate().catch((e) => setCropCsvError(e instanceof Error ? e.message : "Failed to download crop template"))} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Download template</button>
            <button onClick={() => cropCatalogApi.downloadCropExport().catch((e) => setCropCsvError(e instanceof Error ? e.message : "Failed to export crops"))} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Export crops</button>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input type="file" accept=".csv,text/csv" onChange={(event) => setCropCsvFile(event.target.files?.[0] || null)} className="text-sm" />
          <button onClick={validateCropCsv} disabled={cropCsvBusy || !cropCsvFile} className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300">
            {cropCsvBusy ? "Validating..." : "Validate CSV"}
          </button>
          {cropCsvFile ? <span className="text-xs text-gray-500">Selected: {cropCsvFile.name}</span> : null}
        </div>
        {cropCsvError ? <p className="mt-3 rounded bg-red-50 p-3 text-sm text-red-700">{cropCsvError}</p> : null}
        {cropCsvReport ? <CsvValidationReport report={cropCsvReport} /> : null}
        <ImportHistoryPanel
          title="Recent crop imports"
          description="Persisted crop validation batches. Applying creates/updates crops plus taxonomy and propagation linkages."
          applyReasonDefault="Apply validated crop catalog import"
          applyHint="Only VALIDATED batches can be applied. Applying updates crop master data and link tables, then marks the batch APPLIED."
          history={cropImportHistory}
          loading={cropHistoryLoading}
          status={cropHistoryStatus}
          onStatusChange={setCropHistoryStatus}
          onRefresh={() => loadCropImportHistory(cropHistoryStatus || undefined)}
          applyImport={(batchId, reason) => cropCatalogApi.applyCropImport(batchId, reason)}
          onApplied={() => {
            loadCropImportHistory(cropHistoryStatus || undefined);
            setCatalogRefresh((value) => value + 1);
          }}
        />
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
        <ImportHistoryPanel
          title="Recent taxonomy imports"
          description="Persisted taxonomy validation batches, including invalid uploads, for review and controlled apply."
          applyReasonDefault="Apply validated crop taxonomy import"
          applyHint="Only VALIDATED batches can be applied. Applying creates/updates taxonomy nodes and parent edges, then marks the batch APPLIED."
          history={importHistory}
          loading={historyLoading}
          status={historyStatus}
          onStatusChange={setHistoryStatus}
          onRefresh={() => loadImportHistory(historyStatus || undefined)}
          applyImport={(batchId, reason) => cropCatalogApi.applyTaxonomyImport(batchId, reason)}
          onApplied={() => {
            loadImportHistory(historyStatus || undefined);
            setCatalogRefresh((value) => value + 1);
          }}
        />
      </section>

      <section className="rounded bg-white p-4 shadow">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="font-semibold text-gray-900">Propagation CSV validation</h2>
            <p className="mt-1 text-sm text-gray-500">Manage crop establishment methods such as direct seeding, nursery transplant, vegetative sett, tuber, cutting, sapling, grafted plant, bulb, and rhizome.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => cropCatalogApi.downloadPropagationTemplate().catch((e) => setPropCsvError(e instanceof Error ? e.message : "Failed to download propagation template"))} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Download template</button>
            <button onClick={() => cropCatalogApi.downloadPropagationExport().catch((e) => setPropCsvError(e instanceof Error ? e.message : "Failed to export propagation catalog"))} className="rounded border px-3 py-2 text-sm hover:bg-gray-50">Export propagation</button>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input type="file" accept=".csv,text/csv" onChange={(event) => setPropCsvFile(event.target.files?.[0] || null)} className="text-sm" />
          <button onClick={validatePropagationCsv} disabled={propCsvBusy || !propCsvFile} className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300">
            {propCsvBusy ? "Validating..." : "Validate CSV"}
          </button>
          {propCsvFile ? <span className="text-xs text-gray-500">Selected: {propCsvFile.name}</span> : null}
        </div>
        {propCsvError ? <p className="mt-3 rounded bg-red-50 p-3 text-sm text-red-700">{propCsvError}</p> : null}
        {propCsvReport ? <CsvValidationReport report={propCsvReport} /> : null}
        <ImportHistoryPanel
          title="Recent propagation imports"
          description="Persisted propagation validation batches for crop establishment type changes."
          applyReasonDefault="Apply validated crop propagation import"
          applyHint="Only VALIDATED batches can be applied. Applying creates/updates propagation types, then marks the batch APPLIED."
          history={propImportHistory}
          loading={propHistoryLoading}
          status={propHistoryStatus}
          onStatusChange={setPropHistoryStatus}
          onRefresh={() => loadPropagationImportHistory(propHistoryStatus || undefined)}
          applyImport={(batchId, reason) => cropCatalogApi.applyPropagationImport(batchId, reason)}
          onApplied={() => {
            loadPropagationImportHistory(propHistoryStatus || undefined);
            setCatalogRefresh((value) => value + 1);
          }}
        />
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

function ImportHistoryPanel({ title, description, applyReasonDefault, applyHint, history, loading, status, onStatusChange, onRefresh, applyImport, onApplied }: { title: string; description: string; applyReasonDefault: string; applyHint: string; history: CropTaxonomyImportHistory | null; loading: boolean; status: string; onStatusChange: (value: string) => void; onRefresh: () => void; applyImport: (batchId: string, reason: string) => Promise<{ report: { applied_counts?: Record<string, number> } }>; onApplied: () => void }) {
  const imports = history?.imports || [];
  const statusCounts = imports.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});
  const aggregateSummary = imports.reduce(
    (acc, item) => {
      const summary = item.report?.summary || {};
      const applied = item.report?.applied_counts || {};
      acc.rows += Number(summary.total || 0);
      acc.create += Number(summary.create || 0);
      acc.update += Number(summary.update || 0);
      acc.invalid += Number(summary.invalid || 0);
      acc.errors += Number(summary.errors || 0);
      acc.appliedCreated += Number(applied.created || 0);
      acc.appliedUpdated += Number(applied.updated || 0);
      return acc;
    },
    { rows: 0, create: 0, update: 0, invalid: 0, errors: 0, appliedCreated: 0, appliedUpdated: 0 },
  );
  const latestImport = imports[0];
  const [applyReason, setApplyReason] = useState(applyReasonDefault);
  const [applyingBatchId, setApplyingBatchId] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applyNotice, setApplyNotice] = useState<string | null>(null);

  const applyBatch = async (batchId: string) => {
    if (applyReason.trim().length < 3) {
      setApplyError("Enter an apply reason with at least 3 characters.");
      return;
    }
    setApplyingBatchId(batchId);
    setApplyError(null);
    setApplyNotice(null);
    try {
      const applied = await applyImport(batchId, applyReason.trim());
      const counts = applied.report.applied_counts || {};
      setApplyNotice(`Applied ${batchId.slice(0, 8)}: ${counts.created || 0} created, ${counts.updated || 0} updated, ${counts.unchanged || 0} unchanged.`);
      onApplied();
    } catch (e) {
      setApplyError(e instanceof Error ? e.message : "Failed to apply taxonomy import batch");
    } finally {
      setApplyingBatchId(null);
    }
  };

  return <div className="mt-6 border-t pt-4">
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h3 className="font-semibold text-gray-900">{title}</h3>
        <p className="mt-1 text-xs text-gray-500">{description}</p>
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
    <div className="mt-4 rounded border bg-amber-50 p-3 text-sm text-amber-900">
      <p className="font-semibold">Apply is immediate</p>
      <p className="mt-1 text-xs">{applyHint}</p>
      <input value={applyReason} onChange={(event) => setApplyReason(event.target.value)} className="mt-3 w-full rounded border px-3 py-2 text-sm text-gray-900" placeholder="Reason for applying this taxonomy import" />
    </div>
    {applyError ? <p className="mt-3 rounded bg-red-50 p-3 text-sm text-red-700">{applyError}</p> : null}
    {applyNotice ? <p className="mt-3 rounded bg-green-50 p-3 text-sm text-green-700">{applyNotice}</p> : null}
    {loading ? <p className="mt-3 text-sm text-gray-500">Loading import history...</p> : null}
    {!loading && imports.length === 0 ? <p className="mt-3 rounded bg-gray-50 p-3 text-sm text-gray-500">No import batches found.</p> : null}
    {imports.length ? (
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <ImportHistoryMetric label="Batches" value={imports.length} detail={`${statusCounts.VALIDATED || 0} validated / ${statusCounts.APPLIED || 0} applied / ${statusCounts.INVALID || 0} invalid`} />
        <ImportHistoryMetric label="Rows reviewed" value={aggregateSummary.rows} detail={`${aggregateSummary.create} create, ${aggregateSummary.update} update`} />
        <ImportHistoryMetric label="Issues" value={aggregateSummary.errors} detail={`${aggregateSummary.invalid} invalid rows across shown batches`} tone={aggregateSummary.errors ? "warn" : "ok"} />
        <ImportHistoryMetric label="Applied changes" value={aggregateSummary.appliedCreated + aggregateSummary.appliedUpdated} detail={`${aggregateSummary.appliedCreated} created, ${aggregateSummary.appliedUpdated} updated`} tone={aggregateSummary.appliedCreated + aggregateSummary.appliedUpdated ? "info" : "neutral"} />
      </div>
    ) : null}
    {latestImport ? <p className="mt-2 text-xs text-gray-500">Latest batch: <span className="font-mono">{latestImport.batch_id.slice(0, 8)}</span> - {latestImport.status} - {new Date(latestImport.created_at).toLocaleString()}</p> : null}
    {imports.length ? <div className="mt-4 overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="text-gray-500">
          <tr>
            <th className="px-2 py-2">Created</th>
            <th className="px-2 py-2">File</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2">Summary</th>
            <th className="px-2 py-2">Batch</th>
            <th className="px-2 py-2">Action</th>
          </tr>
        </thead>
        <tbody>
          {imports.map((item) => {
            const canApply = item.status === "VALIDATED" && item.can_apply;
            const appliedCounts = item.report?.applied_counts;
            return <tr key={item.batch_id} className="border-t bg-white">
              <td className="px-2 py-2 whitespace-nowrap">{new Date(item.created_at).toLocaleString()}</td>
              <td className="px-2 py-2">{item.file_name || "-"}</td>
              <td className="px-2 py-2"><StatusPill status={item.status} /></td>
              <td className="px-2 py-2">
                <span>{item.report?.summary?.total ?? 0} rows</span>
                <span className="ml-2 text-green-700">+{item.report?.summary?.create ?? 0}</span>
                <span className="ml-2 text-amber-700">~{item.report?.summary?.update ?? 0}</span>
                <span className="ml-2 text-red-700">{item.report?.summary?.errors ?? 0} errors</span>
                {appliedCounts ? <span className="ml-2 text-blue-700">applied {appliedCounts.created || 0}/{appliedCounts.updated || 0}</span> : null}
              </td>
              <td className="px-2 py-2 font-mono text-[11px] text-gray-500">{item.batch_id.slice(0, 8)}</td>
              <td className="px-2 py-2">
                <button
                  onClick={() => applyBatch(item.batch_id)}
                  disabled={!canApply || applyingBatchId === item.batch_id}
                  className="rounded bg-green-700 px-3 py-1 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                  title={canApply ? "Apply this validated taxonomy import" : `Cannot apply ${item.status} batch`}
                >
                  {applyingBatchId === item.batch_id ? "Applying..." : item.status === "APPLIED" ? "Applied" : "Apply"}
                </button>
              </td>
            </tr>;
          })}
        </tbody>
      </table>
    </div> : null}
  </div>;
}

function ImportHistoryMetric({ label, value, detail, tone = "neutral" }: { label: string; value: string | number; detail: string; tone?: "neutral" | "ok" | "warn" | "info" }) {
  const toneClass = tone === "ok" ? "border-green-100 bg-green-50" : tone === "warn" ? "border-amber-100 bg-amber-50" : tone === "info" ? "border-blue-100 bg-blue-50" : "border-gray-100 bg-gray-50";
  return <div className={`rounded border p-3 ${toneClass}`}>
    <p className="text-xs uppercase tracking-wide text-gray-500">{label}</p>
    <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
    <p className="mt-1 text-xs text-gray-500">{detail}</p>
  </div>;
}

function StatusPill({ status }: { status: string }) {
  const tone = status === "VALIDATED" ? "bg-green-50 text-green-700" : status === "INVALID" ? "bg-red-50 text-red-700" : status === "APPLIED" ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-1 font-semibold ${tone}`}>{status}</span>;
}
