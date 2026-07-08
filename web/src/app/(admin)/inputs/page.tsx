"use client";

import { useEffect, useMemo, useState } from "react";
import {
  inputCatalogApi,
  type AgriInputAuditEvent,
  type AgriInputCreateRequest,
  type AgriInputDto,
  type AgriInputUpdateRequest,
  type InputCategoryDto,
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
  const [changeReason, setChangeReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [cropCode, setCropCode] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    inputCatalogApi
      .categories()
      .then((data) => setCategories(data.categories))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    inputCatalogApi
      .inputs({ category: category || undefined, cropCode: cropCode || undefined, q: query || undefined })
      .then((data) => {
        setInputs(data.inputs);
        setSelected((current) => {
          if (!current) return data.inputs[0] || null;
          return data.inputs.find((item) => item.code === current.code) || data.inputs[0] || null;
        });
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [category, cropCode, query]);

  useEffect(() => {
    setDraft(selected ? toDraft(selected) : null);
    setChangeReason("");
    setNotice(null);
  }, [selected]);

  useEffect(() => {
    if (!selected) {
      setAuditEvents([]);
      return;
    }
    setLoadingAudit(true);
    inputCatalogApi
      .inputAudit(selected.code, { limit: 10 })
      .then((payload) => setAuditEvents(payload.events))
      .catch(() => setAuditEvents([]))
      .finally(() => setLoadingAudit(false));
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

  const updateDraft = (patch: Partial<InputDraft>) => {
    setDraft((current) => current ? { ...current, ...patch } : current);
  };

  const updateNewDraft = (patch: Partial<NewInputDraft>) => {
    setNewDraft((current) => ({ ...current, ...patch }));
  };

  const createInput = async () => {
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

  const saveSelected = async () => {
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
      const audit = await inputCatalogApi.inputAudit(updated.code, { limit: 10 });
      setAuditEvents(audit.events);
      setNotice("Input catalog item saved.");
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
        <button
          type="button"
          onClick={() => { setShowCreate((value) => !value); setNewDraft(emptyNewInputDraft(category)); }}
          className="w-fit rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
        >
          {showCreate ? "Close new input" : "New input"}
        </button>
      </div>

      {showCreate ? (
        <NewInputPanel
          categories={categories}
          draft={newDraft}
          creating={creating}
          onDraft={updateNewDraft}
          onCreate={createInput}
          onCancel={() => setShowCreate(false)}
        />
      ) : null}

      <div className="mb-6 grid gap-3 rounded-lg bg-white p-4 shadow md:grid-cols-[1fr_220px_180px_auto]">
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
        <button
          type="button"
          onClick={() => { setQuery(""); setCategory(""); setCropCode(""); }}
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
                  </tr>
                ))}
                {inputs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-gray-400">No inputs match this filter.</td>
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
            onChangeReason={setChangeReason}
            onSave={saveSelected}
            onReset={() => setDraft(selected ? toDraft(selected) : null)}
          />
        </div>
      )}
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
}: {
  categories: InputCategoryDto[];
  draft: NewInputDraft;
  creating: boolean;
  onDraft: (patch: Partial<NewInputDraft>) => void;
  onCreate: () => void;
  onCancel: () => void;
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
          disabled={creating}
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
  onDraft,
  onChangeReason,
  onSave,
  onReset,
}: {
  item: AgriInputDto | null;
  draft: InputDraft | null;
  saving: boolean;
  changeReason: string;
  auditEvents: AgriInputAuditEvent[];
  loadingAudit: boolean;
  onDraft: (patch: Partial<InputDraft>) => void;
  onChangeReason: (value: string) => void;
  onSave: () => void;
  onReset: () => void;
}) {
  if (!item || !draft) {
    return <div className="rounded-lg bg-white p-6 text-sm text-gray-400 shadow">Select an input to edit metadata.</div>;
  }

  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <div className="mb-4">
        <p className="font-mono text-xs text-gray-400">{item.code}</p>
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
          disabled={saving}
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
      </div>

      <InputAuditPanel events={auditEvents} loading={loadingAudit} />
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
