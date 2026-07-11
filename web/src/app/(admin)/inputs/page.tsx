"use client";

import { useEffect, useMemo, useState } from "react";
import {
  authApi,
  inputCatalogApi,
  type AdminProfileResponse,
  type AgriInputAuditEvent,
  type AgriInputCreateRequest,
  type AgriInputDto,
  type AgriInputUpdateRequest,
  type InputCategoryDto,
  type InputCsvImportBatch,
  type InputCsvImportHistory,
  type InputGovernanceResponse,
  type InputReferencesResponse,
} from "@/lib/api";

type InputDraft = {
  canonical_name: string;
  brand_name: string;
  composition: string;
  unit: string;
  standard_weight: string;
  applicable_crops: string;
  application_method: string;
  safety_instructions: string;
  aliases: string;
};

type NewInputDraft = InputDraft & {
  code: string;
  category_code: string;
  change_reason: string;
};

const EMPTY_INPUT_DRAFT: InputDraft = {
  canonical_name: "",
  brand_name: "",
  composition: "",
  unit: "",
  standard_weight: "",
  applicable_crops: "",
  application_method: "",
  safety_instructions: "",
  aliases: "[]",
};

function emptyNewInputDraft(categoryCode = ""): NewInputDraft {
  return {
    ...EMPTY_INPUT_DRAFT,
    code: "",
    category_code: categoryCode,
    change_reason: "Created from admin input catalog",
  };
}

function toDraft(item: AgriInputDto): InputDraft {
  return {
    canonical_name: item.canonical_name || "",
    brand_name: item.brand_name || "",
    composition: item.composition || "",
    unit: item.unit || "",
    standard_weight: item.standard_weight || "",
    applicable_crops: (item.applicable_crops || []).join(", "),
    application_method: item.application_method || "",
    safety_instructions: item.safety_instructions || "",
    aliases: JSON.stringify(item.aliases || [], null, 2),
  };
}

function parseCsv(value: string) {
  return value
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function parseAliases(value: string) {
  if (!value.trim()) return [];
  const parsed = JSON.parse(value);
  if (!Array.isArray(parsed)) throw new Error("Aliases must be a JSON array");
  return parsed;
}

function valueLabel(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function diffRows(before?: Record<string, unknown> | null, after?: Record<string, unknown> | null) {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  return Array.from(keys)
    .filter((key) => JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key]))
    .map((key) => ({ key, before: before?.[key], after: after?.[key] }));
}

function formatAction(action: string) {
  return action
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function InputsPage() {
  const [categories, setCategories] = useState<InputCategoryDto[]>([]);
  const [inputs, setInputs] = useState<AgriInputDto[]>([]);
  const [selected, setSelected] = useState<AgriInputDto | null>(null);
  const [draft, setDraft] = useState<InputDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newDraft, setNewDraft] = useState<NewInputDraft>(() => emptyNewInputDraft());
  const [auditEvents, setAuditEvents] = useState<AgriInputAuditEvent[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [references, setReferences] = useState<InputReferencesResponse | null>(null);
  const [loadingReferences, setLoadingReferences] = useState(false);
  const [governance, setGovernance] = useState<InputGovernanceResponse | null>(null);
  const [governanceBusy, setGovernanceBusy] = useState(false);
  const [changeReason, setChangeReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [cropCode, setCropCode] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [query, setQuery] = useState("");
  const [catalogRefresh, setCatalogRefresh] = useState(0);
  const [showCsv, setShowCsv] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvBatch, setCsvBatch] = useState<InputCsvImportBatch | null>(null);
  const [csvHistory, setCsvHistory] = useState<InputCsvImportHistory | null>(null);
  const [csvReason, setCsvReason] = useState("Input catalog CSV import");
  const [csvBusy, setCsvBusy] = useState(false);
  const [adminProfile, setAdminProfile] = useState<AdminProfileResponse | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);

  const canEditInputs = adminProfile?.permissions.includes("EDIT") ?? false;
  const canPublishInputs = adminProfile?.permissions.includes("PUBLISH") ?? false;

  useEffect(() => {
    authApi.me()
      .then(setAdminProfile)
      .catch(() => setAdminProfile(null))
      .finally(() => setLoadingProfile(false));
    inputCatalogApi
      .categories()
      .then((data) => setCategories(data.categories))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    inputCatalogApi
      .inputs({
        category: category || undefined,
        cropCode: cropCode || undefined,
        q: query || undefined,
        includeInactive: showArchived,
        includeUnpublished: true,
      })
      .then((data) => {
        setInputs(data.inputs);
        setSelected((current) => {
          if (!current) return data.inputs[0] || null;
          return data.inputs.find((item) => item.code === current.code) || data.inputs[0] || null;
        });
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [category, cropCode, query, showArchived, catalogRefresh]);

  useEffect(() => {
    setDraft(selected ? toDraft(selected) : null);
    setChangeReason("");
    setNotice(null);
  }, [selected]);

  useEffect(() => {
    if (!selected) {
      setAuditEvents([]);
      setReferences(null);
      setGovernance(null);
      return;
    }
    setLoadingAudit(true);
    setLoadingReferences(true);
    inputCatalogApi
      .inputAudit(selected.code, { limit: 10 })
      .then((payload) => setAuditEvents(payload.events))
      .catch(() => setAuditEvents([]))
      .finally(() => setLoadingAudit(false));
    inputCatalogApi.governance(selected.code).then(setGovernance).catch(() => setGovernance(null));
    inputCatalogApi
      .references(selected.code)
      .then(setReferences)
      .catch(() => setReferences(null))
      .finally(() => setLoadingReferences(false));
  }, [selected]);

  const cropOptions = useMemo(() => {
    const all = new Set<string>();
    inputs.forEach((item) => item.applicable_crops.forEach((crop) => all.add(crop)));
    ["RICE", "SUGARCANE", "WHEAT", "POTATO"].forEach((crop) => all.add(crop));
    return Array.from(all).sort();
  }, [inputs]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    inputs.forEach((item) => {
      if (item.category_code) counts[item.category_code] = (counts[item.category_code] || 0) + 1;
    });
    return counts;
  }, [inputs]);

  const loadCsvHistory = () => inputCatalogApi.csvImportHistory().then(setCsvHistory).catch(() => setCsvHistory(null));

  const openCsvPanel = () => {
    setShowCsv((value) => !value);
    if (!showCsv) void loadCsvHistory();
  };

  const validateCsv = async () => {
    if (!canEditInputs) { setError("Your current role can view input CSV tools but cannot validate catalog imports."); return; }
    if (!csvFile) return;
    setCsvBusy(true); setError(null); setNotice(null);
    try {
      setCsvBatch(await inputCatalogApi.validateCsv(csvFile));
      await loadCsvHistory();
    } catch (e) { setError(e instanceof Error ? e.message : "CSV validation failed"); }
    finally { setCsvBusy(false); }
  };

  const applyCsv = async () => {
    if (!canEditInputs) { setError("Your current role can view input CSV tools but cannot apply catalog imports."); return; }
    if (!csvBatch) return;
    setCsvBusy(true); setError(null); setNotice(null);
    try {
      const applied = await inputCatalogApi.applyCsv(csvBatch.batch_id, csvReason.trim());
      setCsvBatch(applied);
      setCatalogRefresh((value) => value + 1);
      await loadCsvHistory();
      setNotice(`CSV applied: ${applied.report.applied_counts?.created || 0} created, ${applied.report.applied_counts?.updated || 0} updated.`);
    } catch (e) { setError(e instanceof Error ? e.message : "CSV apply failed"); }
    finally { setCsvBusy(false); }
  };

  const updateDraft = (patch: Partial<InputDraft>) => {
    setDraft((current) => current ? { ...current, ...patch } : current);
  };

  const updateNewDraft = (patch: Partial<NewInputDraft>) => {
    setNewDraft((current) => ({ ...current, ...patch }));
  };

  const createInput = async () => {
    if (!canEditInputs) { setError("Your current role can view inputs but cannot create input catalog records."); return; }
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      const payload: AgriInputCreateRequest = {
        code: newDraft.code.trim().toUpperCase().replace(/\s+/g, "_"),
        category_code: newDraft.category_code.trim().toUpperCase(),
        canonical_name: newDraft.canonical_name.trim(),
        brand_name: newDraft.brand_name.trim() || null,
        composition: newDraft.composition.trim() || null,
        unit: newDraft.unit.trim(),
        standard_weight: newDraft.standard_weight.trim() || null,
        applicable_crops: parseCsv(newDraft.applicable_crops),
        application_method: newDraft.application_method.trim() || null,
        safety_instructions: newDraft.safety_instructions.trim() || null,
        aliases: parseAliases(newDraft.aliases),
        change_reason: newDraft.change_reason.trim() || "Created from admin input catalog",
      };
      const created = await inputCatalogApi.create(payload);
      setInputs((current) => [created, ...current.filter((item) => item.code !== created.code)]);
      setSelected(created);
      setShowCreate(false);
      setNewDraft(emptyNewInputDraft(category || created.category_code || ""));
      const audit = await inputCatalogApi.inputAudit(created.code, { limit: 10 });
      setAuditEvents(audit.events);
      setNotice(`Input ${created.code} created.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create input");
    } finally {
      setCreating(false);
    }
  };

  const archiveSelected = async () => {
    if (!canEditInputs) { setError("Your current role can view inputs but cannot archive input catalog records."); return; }
    if (!selected) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await inputCatalogApi.archive(selected.code, changeReason.trim() || "Archived from admin input catalog");
      setInputs((current) => showArchived
        ? current.map((item) => item.code === updated.code ? updated : item)
        : current.filter((item) => item.code !== updated.code)
      );
      setSelected((current) => showArchived ? updated : inputs.find((item) => item.code !== current?.code) || null);
      setChangeReason("");
      const audit = await inputCatalogApi.inputAudit(updated.code, { limit: 10 });
      setAuditEvents(audit.events);
      setNotice(`Input ${updated.code} archived.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to archive input");
    } finally {
      setSaving(false);
    }
  };

  const restoreSelected = async () => {
    if (!canEditInputs) { setError("Your current role can view inputs but cannot restore input catalog records."); return; }
    if (!selected) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await inputCatalogApi.restore(selected.code, changeReason.trim() || "Restored from admin input catalog");
      setInputs((current) => current.map((item) => item.code === updated.code ? updated : item));
      setSelected(updated);
      setChangeReason("");
      const audit = await inputCatalogApi.inputAudit(updated.code, { limit: 10 });
      setAuditEvents(audit.events);
      setNotice(`Input ${updated.code} restored.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to restore input");
    } finally {
      setSaving(false);
    }
  };

  const transitionGovernance = async (action: "submit" | "publish" | "reject") => {
    if (!selected) return;
    if (action === "publish" ? !canPublishInputs : !canEditInputs) {
      setError(action === "publish" ? "Your current role cannot publish input catalog records." : "Your current role cannot submit or reject input catalog records.");
      return;
    }
    const reason = changeReason.trim() || `${action} input catalog item`;
    setGovernanceBusy(true); setError(null); setNotice(null);
    try {
      const result = action === "submit"
        ? await inputCatalogApi.submitReview(selected.code, reason)
        : action === "publish"
          ? await inputCatalogApi.publish(selected.code, reason)
          : await inputCatalogApi.reject(selected.code, reason);
      setGovernance(result);
      setSelected(result.input);
      setInputs((current) => current.map((item) => item.code === result.input.code ? result.input : item));
      setChangeReason("");
      setNotice(`Input ${result.input.code} is now ${result.input.catalog_status}.`);
      const audit = await inputCatalogApi.inputAudit(result.input.code, { limit: 10 });
      setAuditEvents(audit.events);
    } catch (e) { setError(e instanceof Error ? e.message : "Lifecycle action failed"); }
    finally { setGovernanceBusy(false); }
  };

  const saveSelected = async () => {
    if (!canEditInputs) { setError("Your current role can view inputs but cannot edit input catalog records."); return; }
    if (!selected || !draft) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload: AgriInputUpdateRequest = {
        canonical_name: draft.canonical_name.trim(),
        brand_name: draft.brand_name.trim() || null,
        composition: draft.composition.trim() || null,
        unit: draft.unit.trim(),
        standard_weight: draft.standard_weight.trim() || null,
        applicable_crops: parseCsv(draft.applicable_crops),
        application_method: draft.application_method.trim() || null,
        safety_instructions: draft.safety_instructions.trim() || null,
        aliases: parseAliases(draft.aliases),
        change_reason: changeReason.trim() || null,
      };
      const updated = await inputCatalogApi.update(selected.code, payload);
      setInputs((current) => current.map((item) => item.code === updated.code ? updated : item));
      setSelected(updated);
      setChangeReason("");
      const [audit, governanceResult] = await Promise.all([
        inputCatalogApi.inputAudit(updated.code, { limit: 10 }),
        inputCatalogApi.governance(updated.code),
      ]);
      setAuditEvents(audit.events);
      setGovernance(governanceResult);
      setNotice(updated.catalog_status === "PUBLISHED" ? "Published input metadata saved." : "Input saved as DRAFT; submit it for review when ready.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save input");
    } finally {
      setSaving(false);
    }
  };

  if (error && inputs.length === 0) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Input Catalog</h1>
          <p className="mt-1 text-sm text-gray-500">
            Admin master data for canonical seeds, fertilizers, crop protection, labor, machinery, and irrigation inputs.
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={openCsvPanel} className="w-fit rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
            {showCsv ? "Close CSV tools" : "CSV import / export"}
          </button>
          <button
            type="button"
            disabled={!canEditInputs}
            title={canEditInputs ? undefined : "Your role cannot create input catalog records."}
            onClick={() => { setShowCreate((value) => !value); setNewDraft(emptyNewInputDraft(category)); }}
            className="w-fit rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {showCreate ? "Close new input" : "New input"}
          </button>
        </div>
      </div>

      {!loadingProfile && !canEditInputs ? (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">Input catalog is read-only for your role</p>
          <p className="mt-1">Role {(adminProfile?.role || "UNASSIGNED").replaceAll("_", " ")}: catalog edits {canEditInputs ? "allowed" : "read-only"}; publishing {canPublishInputs ? "allowed" : "read-only"}. You can still browse inputs, usage references, and audit history.</p>
        </div>
      ) : null}

      {showCsv ? (
        <CsvCatalogPanel
          file={csvFile}
          batch={csvBatch}
          history={csvHistory}
          reason={csvReason}
          busy={csvBusy}
          onFile={(file) => { setCsvFile(file); setCsvBatch(null); }}
          onReason={setCsvReason}
          onValidate={validateCsv}
          onApply={applyCsv}
          canEdit={canEditInputs}
        />
      ) : null}

      {showCreate ? (
        <NewInputPanel
          categories={categories}
          draft={newDraft}
          creating={creating}
          onDraft={updateNewDraft}
          onCreate={createInput}
          onCancel={() => setShowCreate(false)}
          canEdit={canEditInputs}
        />
      ) : null}

      <div className="mb-6 grid gap-3 rounded-lg bg-white p-4 shadow md:grid-cols-[1fr_220px_180px_auto_auto]">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search code, name, or composition"
          className="rounded-lg border px-3 py-2 text-sm"
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="">All categories</option>
          {categories.map((cat) => (
            <option key={cat.code} value={cat.code}>{cat.canonical_name}</option>
          ))}
        </select>
        <select value={cropCode} onChange={(e) => setCropCode(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="">All crops</option>
          {cropOptions.map((crop) => (
            <option key={crop} value={crop}>{crop}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
          />
          Show archived
        </label>
        <button
          type="button"
          onClick={() => { setQuery(""); setCategory(""); setCropCode(""); setShowArchived(false); }}
          className="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Clear
        </button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {categories.slice(0, 14).map((cat) => (
          <button
            key={cat.code}
            onClick={() => setCategory(category === cat.code ? "" : cat.code)}
            className={`rounded-lg border p-3 text-left text-sm shadow-sm ${
              category === cat.code ? "border-green-500 bg-green-50" : "border-transparent bg-white hover:border-green-200"
            }`}
          >
            <p className="font-medium text-gray-900">{cat.canonical_name}</p>
            <p className="mt-1 text-xs text-gray-400">{categoryCounts[cat.code] || 0} shown</p>
          </button>
        ))}
      </div>

      {error ? <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {notice ? <div className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700">{notice}</div> : null}

      {loading ? (
        <p className="text-gray-500">Loading inputs...</p>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="overflow-hidden rounded-lg bg-white shadow">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Code</th>
                  <th className="px-4 py-3 text-left font-medium">Name</th>
                  <th className="px-4 py-3 text-left font-medium">Category</th>
                  <th className="px-4 py-3 text-left font-medium">Composition</th>
                  <th className="px-4 py-3 text-left font-medium">Unit</th>
                  <th className="px-4 py-3 text-left font-medium">Crops</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {inputs.map((item) => (
                  <tr
                    key={item.code}
                    onClick={() => setSelected(item)}
                    className={`cursor-pointer hover:bg-gray-50 ${selected?.code === item.code ? "bg-green-50" : ""}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">{item.code}</td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{item.canonical_name}</p>
                      {item.brand_name ? <p className="text-xs text-gray-400">Brand: {item.brand_name}</p> : null}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">
                        {item.category_code || "-"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{item.composition || "-"}</td>
                    <td className="px-4 py-3 text-gray-600">{item.unit}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {item.applicable_crops.length > 0 ? item.applicable_crops.map((crop) => (
                          <span key={crop} className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">{crop}</span>
                        )) : <span className="text-gray-400">-</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2 py-1 text-xs font-medium ${item.is_active === false ? "bg-gray-100 text-gray-500" : "bg-green-50 text-green-700"}`}>
                        {item.is_active === false ? "Archived" : item.catalog_status}
                      </span>
                    </td>
                  </tr>
                ))}
                {inputs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-gray-400">No inputs match this filter.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <InputEditor
            item={selected}
            draft={draft}
            saving={saving}
            onDraft={updateDraft}
            changeReason={changeReason}
            auditEvents={auditEvents}
            loadingAudit={loadingAudit}
            references={references}
            loadingReferences={loadingReferences}
            governance={governance}
            governanceBusy={governanceBusy}
            onGovernance={transitionGovernance}
            onChangeReason={setChangeReason}
            onSave={saveSelected}
            onArchive={archiveSelected}
            onRestore={restoreSelected}
            onReset={() => setDraft(selected ? toDraft(selected) : null)}
            canEdit={canEditInputs}
            canPublish={canPublishInputs}
          />
        </div>
      )}
    </div>
  );
}

function CsvCatalogPanel({ file, batch, history, reason, busy, onFile, onReason, onValidate, onApply, canEdit }: {
  file: File | null;
  batch: InputCsvImportBatch | null;
  history: InputCsvImportHistory | null;
  reason: string;
  busy: boolean;
  onFile: (file: File | null) => void;
  onReason: (value: string) => void;
  onValidate: () => void;
  onApply: () => void;
  canEdit: boolean;
}) {
  const counts = batch?.report.counts || {};
  return (
    <div className="mb-6 rounded-lg bg-white p-5 shadow">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">CSV catalog exchange</h2>
          <p className="mt-1 text-xs text-gray-500">Validation is a dry run. No catalog data changes until you inspect the report and apply it.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => inputCatalogApi.downloadCsvTemplate()} className="rounded border px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">Download template</button>
          <button type="button" onClick={() => inputCatalogApi.exportCsv()} className="rounded border px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">Export active catalog</button>
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-end">
        <label className="flex-1 text-xs font-medium text-gray-500">CSV file
          <input type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0] || null)} className="mt-1 block w-full rounded border p-2 text-sm" />
        </label>
        <button type="button" disabled={!file || busy || !canEdit} title={canEdit ? undefined : "Your role cannot validate catalog imports."} onClick={onValidate} className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? "Working..." : "Validate dry run"}</button>
      </div>
      {batch ? (
        <div className="mt-5">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded bg-gray-100 px-2 py-1">Status: {batch.status}</span>
            <span className="rounded bg-green-50 px-2 py-1 text-green-700">Create: {counts.create || 0}</span>
            <span className="rounded bg-blue-50 px-2 py-1 text-blue-700">Update: {counts.update || 0}</span>
            <span className="rounded bg-gray-50 px-2 py-1">Unchanged: {counts.unchanged || 0}</span>
            <span className="rounded bg-red-50 px-2 py-1 text-red-700">Errors: {counts.errors || 0}</span>
          </div>
          <div className="mt-3 max-h-72 overflow-auto rounded border">
            <table className="min-w-full text-left text-xs"><thead className="sticky top-0 bg-gray-50"><tr><th className="p-2">Row</th><th className="p-2">Code</th><th className="p-2">Action</th><th className="p-2">Diagnostics</th></tr></thead>
              <tbody className="divide-y">{batch.report.rows.map((row) => <tr key={`${row.row_number}-${row.code}`}><td className="p-2">{row.row_number}</td><td className="p-2 font-mono">{row.code || "-"}</td><td className="p-2">{row.action}</td><td className="p-2">{[...row.errors, ...row.warnings].map((d) => <p key={`${d.field}-${d.code}`} className={row.errors.includes(d) ? "text-red-600" : "text-amber-600"}>{d.field}: {d.message}</p>)}</td></tr>)}</tbody>
            </table>
          </div>
          {batch.can_apply ? <div className="mt-3 flex flex-col gap-2 md:flex-row"><input value={reason} onChange={(e) => onReason(e.target.value)} placeholder="Reason for import" className="flex-1 rounded border px-3 py-2 text-sm" /><button type="button" disabled={busy || !canEdit || reason.trim().length < 3} title={canEdit ? undefined : "Your role cannot apply catalog imports."} onClick={onApply} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply validated changes</button></div> : null}
        </div>
      ) : null}
      {history?.imports.length ? <details className="mt-4 text-xs"><summary className="cursor-pointer font-medium text-gray-600">Recent imports ({history.count})</summary><div className="mt-2 space-y-1">{history.imports.slice(0, 8).map((item) => <p key={item.batch_id} className="rounded bg-gray-50 p-2">{new Date(item.created_at).toLocaleString()} · {item.file_name} · {item.status}</p>)}</div></details> : null}
    </div>
  );
}

function NewInputPanel({
  categories,
  draft,
  creating,
  onDraft,
  onCreate,
  onCancel,
  canEdit,
}: {
  categories: InputCategoryDto[];
  draft: NewInputDraft;
  creating: boolean;
  onDraft: (patch: Partial<NewInputDraft>) => void;
  onCreate: () => void;
  onCancel: () => void;
  canEdit: boolean;
}) {
  return (
    <div className="mb-6 rounded-lg bg-white p-5 shadow">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Create new input</h2>
        <p className="mt-1 text-xs text-gray-500">Use stable uppercase codes because workflow recommendations and project assignments can reference them later.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <TextField label="Code" hint="e.g. ZINC_SULPHATE_21" value={draft.code} onChange={(value) => onDraft({ code: value })} />
        <label className="block text-xs font-medium text-gray-500">
          Category
          <select
            value={draft.category_code}
            onChange={(event) => onDraft({ category_code: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal text-gray-900"
          >
            <option value="">Select category</option>
            {categories.map((cat) => (
              <option key={cat.code} value={cat.code}>{cat.canonical_name}</option>
            ))}
          </select>
        </label>
        <TextField label="Canonical name" value={draft.canonical_name} onChange={(value) => onDraft({ canonical_name: value })} />
        <TextField label="Unit" hint="kg, litre, packet" value={draft.unit} onChange={(value) => onDraft({ unit: value })} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <TextField label="Brand name" value={draft.brand_name} onChange={(value) => onDraft({ brand_name: value })} />
        <TextField label="Composition" value={draft.composition} onChange={(value) => onDraft({ composition: value })} />
        <TextField label="Standard weight" value={draft.standard_weight} onChange={(value) => onDraft({ standard_weight: value })} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <TextField label="Applicable crops" hint="Comma-separated crop codes" value={draft.applicable_crops} onChange={(value) => onDraft({ applicable_crops: value })} />
        <TextField label="Change reason" value={draft.change_reason} onChange={(value) => onDraft({ change_reason: value })} />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <TextArea label="Application method" value={draft.application_method} onChange={(value) => onDraft({ application_method: value })} />
        <TextArea label="Safety instructions" value={draft.safety_instructions} onChange={(value) => onDraft({ safety_instructions: value })} />
      </div>
      <div className="mt-3">
        <TextArea label="Aliases JSON" hint='Example: [{"name":"local name","language":"hi"}]' value={draft.aliases} onChange={(value) => onDraft({ aliases: value })} rows={4} />
      </div>
      <div className="mt-5 flex gap-2">
        <button
          type="button"
          disabled={creating || !canEdit}
          title={canEdit ? undefined : "Your role cannot create input catalog records."}
          onClick={onCreate}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-wait disabled:opacity-60"
        >
          {creating ? "Creating..." : "Create input"}
        </button>
        <button
          type="button"
          disabled={creating}
          onClick={onCancel}
          className="rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function InputEditor({
  item,
  draft,
  saving,
  changeReason,
  auditEvents,
  loadingAudit,
  references,
  loadingReferences,
  governance,
  governanceBusy,
  onGovernance,
  onDraft,
  onChangeReason,
  onSave,
  onArchive,
  onRestore,
  onReset,
  canEdit,
  canPublish,
}: {
  item: AgriInputDto | null;
  draft: InputDraft | null;
  saving: boolean;
  changeReason: string;
  auditEvents: AgriInputAuditEvent[];
  loadingAudit: boolean;
  references: InputReferencesResponse | null;
  loadingReferences: boolean;
  governance: InputGovernanceResponse | null;
  governanceBusy: boolean;
  onGovernance: (action: "submit" | "publish" | "reject") => void;
  onDraft: (patch: Partial<InputDraft>) => void;
  onChangeReason: (value: string) => void;
  onSave: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onReset: () => void;
  canEdit: boolean;
  canPublish: boolean;
}) {
  if (!item || !draft) {
    return <div className="rounded-lg bg-white p-6 text-sm text-gray-400 shadow">Select an input to edit metadata.</div>;
  }

  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <div className="mb-4">
        <div className="flex items-center justify-between gap-3">
          <p className="font-mono text-xs text-gray-400">{item.code}</p>
          <span className={`rounded px-2 py-1 text-xs font-medium ${item.is_active === false ? "bg-gray-100 text-gray-500" : "bg-green-50 text-green-700"}`}>
            {item.is_active === false ? "Archived" : item.catalog_status}
          </span>
        </div>
        <h2 className="text-lg font-semibold text-gray-900">Edit input metadata</h2>
        <p className="mt-1 text-xs text-gray-500">Code and category are locked because workflow recommendations may already reference them.</p>
      </div>

      <div className="space-y-3">
        <TextField label="Canonical name" value={draft.canonical_name} onChange={(value) => onDraft({ canonical_name: value })} />
        <TextField label="Brand name" value={draft.brand_name} onChange={(value) => onDraft({ brand_name: value })} />
        <TextField label="Composition" value={draft.composition} onChange={(value) => onDraft({ composition: value })} />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-2">
          <TextField label="Unit" value={draft.unit} onChange={(value) => onDraft({ unit: value })} />
          <TextField label="Standard weight" value={draft.standard_weight} onChange={(value) => onDraft({ standard_weight: value })} />
        </div>
        <TextField label="Applicable crops" hint="Comma-separated crop codes" value={draft.applicable_crops} onChange={(value) => onDraft({ applicable_crops: value })} />
        <TextArea label="Application method" value={draft.application_method} onChange={(value) => onDraft({ application_method: value })} />
        <TextArea label="Safety instructions" value={draft.safety_instructions} onChange={(value) => onDraft({ safety_instructions: value })} />
        <TextArea label="Aliases JSON" hint='Example: [{"name":"local name","language":"hi"}]' value={draft.aliases} onChange={(value) => onDraft({ aliases: value })} rows={5} />
        <TextArea label="Change reason" hint="Shown in audit history" value={changeReason} onChange={onChangeReason} rows={2} />
      </div>

      <div className="mt-5 flex gap-2">
        <button
          type="button"
          disabled={saving || !canEdit}
          title={canEdit ? undefined : "Your role cannot edit input catalog records."}
          onClick={onSave}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-wait disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save input"}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={onReset}
          className="rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
        >
          Reset
        </button>
        {item.is_active === false ? (
          <button
            type="button"
            disabled={saving || !canEdit}
            title={canEdit ? undefined : "Your role cannot restore input catalog records."}
            onClick={onRestore}
            className="rounded-lg border border-green-200 px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-50 disabled:opacity-60"
          >
            Restore
          </button>
        ) : (
          <button
            type="button"
            disabled={saving || !canEdit}
            title={canEdit ? undefined : "Your role cannot archive input catalog records."}
            onClick={onArchive}
            className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
          >
            Archive
          </button>
        )}
      </div>

      <InputGovernancePanel governance={governance} busy={governanceBusy} onAction={onGovernance} canEdit={canEdit} canPublish={canPublish} />
      <InputUsagePanel references={references} loading={loadingReferences} />
      <InputAuditPanel events={auditEvents} loading={loadingAudit} />
    </div>
  );
}

function InputGovernancePanel({ governance, busy, onAction, canEdit, canPublish }: { governance: InputGovernanceResponse | null; busy: boolean; onAction: (action: "submit" | "publish" | "reject") => void; canEdit: boolean; canPublish: boolean }) {
  if (!governance) return <div className="mt-6 border-t pt-4 text-xs text-gray-400">Loading governance report...</div>;
  const { input, validation } = governance;
  return <div className="mt-6 border-t pt-4">
    <div className="flex items-center justify-between"><div><h3 className="text-sm font-semibold text-gray-900">Review and publishing</h3><p className="text-xs text-gray-500">Only PUBLISHED inputs are visible to Android and workflow runtime.</p></div><span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{input.catalog_status}</span></div>
    <div className="mt-3 flex gap-2 text-xs"><span className="rounded bg-red-50 px-2 py-1 text-red-700">{validation.counts.errors} errors</span><span className="rounded bg-amber-50 px-2 py-1 text-amber-700">{validation.counts.warnings} warnings</span><span className="rounded bg-gray-100 px-2 py-1">{validation.counts.duplicates} duplicates</span></div>
    {[...validation.errors, ...validation.warnings].length ? <div className="mt-2 space-y-1">{[...validation.errors, ...validation.warnings].map((finding) => <p key={`${finding.field}-${finding.code}`} className={`rounded p-2 text-xs ${validation.errors.includes(finding) ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}>{finding.field}: {finding.message}</p>)}</div> : <p className="mt-2 rounded bg-green-50 p-2 text-xs text-green-700">Validation is clear.</p>}
    {validation.duplicate_candidates.length ? <details className="mt-2 text-xs"><summary className="cursor-pointer text-gray-600">Possible duplicates</summary>{validation.duplicate_candidates.map((candidate) => <p key={candidate.code} className="mt-1 rounded bg-gray-50 p-2">{candidate.code} · {candidate.canonical_name} · {candidate.catalog_status}</p>)}</details> : null}
    <div className="mt-3 flex flex-wrap gap-2">{input.catalog_status === "DRAFT" || input.catalog_status === "REJECTED" ? <button disabled={busy || !canEdit || !validation.can_submit} title={canEdit ? undefined : "Your role cannot submit input catalog records."} onClick={() => onAction("submit")} className="rounded bg-blue-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">Submit for review</button> : null}{input.catalog_status === "REVIEW" ? <><button disabled={busy || !canPublish || !validation.can_publish} title={canPublish ? undefined : "Your role cannot publish input catalog records."} onClick={() => onAction("publish")} className="rounded bg-green-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">Publish</button><button disabled={busy || !canEdit} title={canEdit ? undefined : "Your role cannot reject input catalog records."} onClick={() => onAction("reject")} className="rounded border border-red-200 px-3 py-2 text-xs font-medium text-red-700">Reject</button></> : null}</div>
  </div>;
}

function localizedLabel(value?: Record<string, string> | string | null) {
  if (!value) return "-";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "-";
}

function InputUsagePanel({ references, loading }: { references: InputReferencesResponse | null; loading: boolean }) {
  const workflowReferences = references?.usage.workflow_recommendations || [];
  const projectReferences = references?.usage.project_assignments || [];
  const total = references?.references.total || 0;

  return (
    <div className="mt-6 border-t pt-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Used by</h3>
          <p className="text-xs text-gray-500">Active workflow recommendations and project assignments referencing this input.</p>
        </div>
        <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{total}</span>
      </div>
      {loading ? <p className="rounded bg-gray-50 p-3 text-xs text-gray-500">Loading usage references...</p> : null}
      {!loading && !references ? <p className="rounded bg-red-50 p-3 text-xs text-red-600">Usage references could not be loaded.</p> : null}
      {!loading && references && total === 0 ? (
        <p className="rounded bg-gray-50 p-3 text-xs text-gray-400">This input is not currently referenced and can be archived safely.</p>
      ) : null}
      {!loading && workflowReferences.length > 0 ? (
        <div className="mb-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
            Workflow recommendations ({workflowReferences.length})
          </p>
          <div className="max-h-64 space-y-2 overflow-auto pr-1">
            {workflowReferences.map((reference) => (
              <a
                key={reference.recommendation_id}
                href={`/workflows/preview/${reference.workflow_template_version_id}${reference.version_status === "DRAFT" ? "?draft=true" : ""}`}
                className="block rounded border p-3 text-xs hover:border-blue-200 hover:bg-blue-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-gray-800">{reference.workflow_name}</p>
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600">
                    v{reference.version_number} / {reference.version_status}
                  </span>
                </div>
                <p className="mt-1 text-gray-600">
                  {reference.crop_code} / {reference.season_code} / {localizedLabel(reference.stage_name)} ({reference.stage_code})
                </p>
                <p className="mt-1 text-gray-500">
                  {reference.activity_type} / {reference.input_name} / Day +{reference.day_offset}
                  {reference.is_critical ? " / Critical" : ""}
                </p>
              </a>
            ))}
          </div>
        </div>
      ) : null}
      {!loading && projectReferences.length > 0 ? (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
            Project assignments ({projectReferences.length})
          </p>
          <div className="max-h-48 space-y-2 overflow-auto pr-1">
            {projectReferences.map((reference) => (
              <a
                key={reference.assignment_id}
                href={`/project-inputs?project_id=${reference.project_id}`}
                className="block rounded border p-3 text-xs hover:border-blue-200 hover:bg-blue-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-gray-800">{reference.project_name}</p>
                  <span className={`rounded px-2 py-0.5 text-[10px] ${reference.enabled ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                    {reference.enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
                <p className="mt-1 text-gray-500">{reference.project_status} / Order {reference.display_order}</p>
                {reference.reason ? <p className="mt-1 text-gray-500">Reason: {reference.reason}</p> : null}
              </a>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function InputAuditPanel({ events, loading }: { events: AgriInputAuditEvent[]; loading: boolean }) {
  return (
    <div className="mt-6 border-t pt-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Change history</h3>
          <p className="text-xs text-gray-500">Recent master data edits for this input.</p>
        </div>
        <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-500">{events.length}</span>
      </div>
      {loading ? <p className="rounded bg-gray-50 p-3 text-xs text-gray-500">Loading history...</p> : null}
      {!loading && events.length === 0 ? <p className="rounded bg-gray-50 p-3 text-xs text-gray-400">No changes recorded yet.</p> : null}
      {!loading && events.length > 0 ? (
        <div className="max-h-80 space-y-3 overflow-auto pr-1">
          {events.map((event) => {
            const rows = diffRows(event.before, event.after);
            return (
              <details key={event.id} className="rounded border p-3 text-xs">
                <summary className="cursor-pointer">
                  <span className="font-medium text-gray-800">{formatAction(event.action)}</span>
                  {event.created_at ? <span className="ml-2 text-gray-400">{new Date(event.created_at).toLocaleString()}</span> : null}
                </summary>
                <div className="mt-2 rounded bg-gray-50 p-2 text-gray-600">
                  <p><span className="font-medium">Reason:</span> {event.reason || "No reason captured"}</p>
                  <p><span className="font-medium">Actor:</span> {event.actor_id || "System / unknown actor"}</p>
                </div>
                {rows.length > 0 ? (
                  <div className="mt-2 overflow-auto rounded border">
                    <table className="min-w-full text-left text-[11px]">
                      <thead className="bg-gray-50 text-gray-500">
                        <tr>
                          <th className="px-2 py-1 font-medium">Field</th>
                          <th className="px-2 py-1 font-medium">Before</th>
                          <th className="px-2 py-1 font-medium">After</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {rows.map((row) => (
                          <tr key={row.key}>
                            <td className="px-2 py-1 font-mono text-gray-600">{row.key}</td>
                            <td className="max-w-xs px-2 py-1 text-gray-500">{valueLabel(row.before)}</td>
                            <td className="max-w-xs px-2 py-1 text-gray-800">{valueLabel(row.after)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </details>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function TextField({ label, value, hint, onChange }: { label: string; value: string; hint?: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-xs font-medium text-gray-500">
      {label}
      {hint ? <span className="ml-2 font-normal text-gray-400">{hint}</span> : null}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal text-gray-900"
      />
    </label>
  );
}

function TextArea({ label, value, hint, rows = 3, onChange }: { label: string; value: string; hint?: string; rows?: number; onChange: (value: string) => void }) {
  return (
    <label className="block text-xs font-medium text-gray-500">
      {label}
      {hint ? <span className="ml-2 font-normal text-gray-400">{hint}</span> : null}
      <textarea
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded border px-3 py-2 text-sm font-normal text-gray-900"
      />
    </label>
  );
}
