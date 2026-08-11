"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { localizationApi, type LocalizationContentKeyDto, type LocalizationSummaryResponse } from "@/lib/api";

const LANGUAGES = ["en", "hi", "kn", "mr", "pa", "ta", "te", "bn"];

function labelFor(item: LocalizationContentKeyDto, language: string) {
  return item.default_labels[language] || item.default_labels.en || "-";
}

function sourceTone(source: string) {
  if (source.includes("OVERRIDE")) return "bg-green-50 text-green-700";
  if (source === "EN_FALLBACK") return "bg-amber-50 text-amber-700";
  return "bg-gray-100 text-gray-700";
}

export default function LocalizationPage() {
  const [summary, setSummary] = useState<LocalizationSummaryResponse | null>(null);
  const [items, setItems] = useState<LocalizationContentKeyDto[]>([]);
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("hi");
  const [projectId, setProjectId] = useState("");
  const [selected, setSelected] = useState<LocalizationContentKeyDto | null>(null);
  const [overrideText, setOverrideText] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reason, setReason] = useState("Admin localization override");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sourceOptions = useMemo(() => Object.keys(summary?.content_keys_by_source || {}).sort(), [summary]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [summaryPayload, keyPayload] = await Promise.all([
        localizationApi.summary(),
        localizationApi.contentKeys({
          source: source || undefined,
          q: query || undefined,
          language_code: language,
          project_id: projectId || undefined,
          include_overrides: true,
          limit: 100,
        }),
      ]);
      setSummary(summaryPayload);
      setItems(keyPayload.content_keys);
      if (selected) {
        const refreshed = keyPayload.content_keys.find((item) => item.id === selected.id) || null;
        setSelected(refreshed);
        setOverrideText(refreshed?.effective.text || "");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load localization content");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, language]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  function selectItem(item: LocalizationContentKeyDto) {
    setSelected(item);
    setOverrideText(item.effective.text || labelFor(item, language));
    setReviewNotes("");
    setNotice(null);
  }

  async function saveOverride() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload = await localizationApi.upsertOverride(selected.id, {
        project_id: projectId || null,
        language_code: language,
        override_text: overrideText,
        review_status: "PUBLISHED",
        review_notes: reviewNotes || null,
        reason,
      });
      setSelected(payload.content_key);
      setOverrideText(payload.content_key.effective.text || "");
      setNotice(`Override ${payload.action.toLowerCase()} for ${selected.content_key}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save override");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateEffectiveOverride() {
    if (!selected?.effective.override_id) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await localizationApi.deactivateOverride(selected.effective.override_id, reason || "Deactivate localization override");
      setNotice(`Override deactivated for ${selected.content_key}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to deactivate override");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Localization</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage tenant/project language overrides for backend-driven forms, options, and workflow-stage labels.
        </p>
      </div>

      {summary ? (
        <div className="mb-6 grid gap-3 md:grid-cols-4">
          <Mini label="Content keys" value={Object.values(summary.content_keys_by_source).reduce((a, b) => a + b, 0)} />
          <Mini label="Active overrides" value={summary.active_override_count} />
          <Mini label="Tenant" value={summary.tenant_id} mono />
          <Mini label="Language" value={language} />
        </div>
      ) : null}

      <form onSubmit={submitSearch} className="mb-6 rounded bg-white p-5 shadow">
        <div className="grid gap-3 md:grid-cols-[1fr_160px_120px_1fr_auto] md:items-end">
          <label className="text-xs text-gray-500">
            Search
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="label, key, crop stage..." className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
          </label>
          <label className="text-xs text-gray-500">
            Source
            <select value={source} onChange={(e) => setSource(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              <option value="">All</option>
              {sourceOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-500">
            Language
            <select value={language} onChange={(e) => setLanguage(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              {LANGUAGES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-500">
            Project ID override scope
            <input value={projectId} onChange={(e) => setProjectId(e.target.value)} placeholder="Optional project UUID" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
          </label>
          <button type="submit" className="rounded bg-green-700 px-5 py-2 text-sm font-medium text-white">Search</button>
        </div>
      </form>

      {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading localization keys...</p> : null}

      {!loading ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
          <section className="rounded bg-white shadow">
            <div className="border-b p-4">
              <h2 className="font-semibold text-gray-900">Content keys</h2>
              <p className="text-xs text-gray-500">{items.length} rows shown. Search is limited to first 100 rows.</p>
            </div>
            <div className="max-h-[720px] divide-y overflow-auto">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectItem(item)}
                  className={`block w-full p-4 text-left hover:bg-gray-50 ${selected?.id === item.id ? "bg-green-50" : ""}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-gray-100 px-2 py-1 text-[11px] text-gray-700">{item.source}</span>
                    <span className="rounded bg-gray-100 px-2 py-1 text-[11px] text-gray-700">{item.content_kind}</span>
                    <span className={`rounded px-2 py-1 text-[11px] ${sourceTone(item.effective.source)}`}>{item.effective.source}</span>
                  </div>
                  <p className="mt-2 break-all font-mono text-xs text-gray-500">{item.content_key}</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">{item.effective.text || labelFor(item, language)}</p>
                  <p className="mt-1 text-xs text-gray-500">Default EN: {item.default_labels.en || "-"}</p>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded bg-white p-5 shadow">
            {selected ? (
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Edit override</h2>
                <p className="mt-1 break-all font-mono text-xs text-gray-500">{selected.content_key}</p>

                <div className="mt-4 space-y-3 text-sm">
                  <Info label="Source" value={selected.source} />
                  <Info label="Kind" value={selected.content_kind} />
                  <Info label="Default English" value={selected.default_labels.en || "-"} />
                  <Info label={`Default ${language}`} value={selected.default_labels[language] || "-"} />
                  <Info label="Effective source" value={selected.effective.source} />
                </div>

                <label className="mt-5 block text-xs font-medium text-gray-500">
                  Override text ({language})
                  <textarea value={overrideText} onChange={(e) => setOverrideText(e.target.value)} rows={5} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
                </label>

                <label className="mt-3 block text-xs font-medium text-gray-500">
                  Review notes
                  <textarea value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} rows={3} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
                </label>

                <label className="mt-3 block text-xs font-medium text-gray-500">
                  Reason
                  <input value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
                </label>

                <div className="mt-5 flex flex-wrap gap-2">
                  <button disabled={saving || !overrideText.trim()} onClick={saveOverride} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                    Save published override
                  </button>
                  <button disabled={saving || !selected.effective.override_id} onClick={deactivateEffectiveOverride} className="rounded border border-red-200 px-4 py-2 text-sm text-red-700 disabled:opacity-50">
                    Deactivate effective override
                  </button>
                </div>

                {selected.overrides?.length ? (
                  <div className="mt-6">
                    <h3 className="text-sm font-semibold text-gray-900">Active overrides</h3>
                    <div className="mt-2 space-y-2">
                      {selected.overrides.map((override) => (
                        <div key={override.id} className="rounded border p-3 text-xs text-gray-600">
                          <p><b>{override.language_code}</b> {override.project_id ? `project ${override.project_id}` : "tenant default"} · {override.review_status}</p>
                          <p className="mt-1 text-sm text-gray-900">{override.override_text}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-gray-500">Select a content key to view defaults and create a language override.</p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function Mini({ label, value, mono = false }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div className="rounded bg-white p-4 shadow">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold text-gray-900 ${mono ? "font-mono text-xs" : ""}`}>{value}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 break-words text-gray-900">{value}</p>
    </div>
  );
}
