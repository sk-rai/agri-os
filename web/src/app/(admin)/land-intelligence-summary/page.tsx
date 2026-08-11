"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { landIntelligenceSummaryApi, type LandIntelligenceSummaryResponse } from "@/lib/api";

const LANGUAGES = ["en", "hi", "kn", "mr", "pa", "ta", "te", "bn"];
const SCOPE_TYPES = ["PIN", "DISTRICT", "STATE"];

function textValue(value: unknown, language = "en") {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const map = value as Record<string, unknown>;
    return String(map[language] || map.en || "-");
  }
  return "-";
}

function defaultPayload(scopeType: string, scopeCode: string, language: string) {
  return {
    title: { [language]: "Land intelligence summary" },
    subtitle: { [language]: `Informational guidance for ${scopeType} ${scopeCode}.` },
    cards: [
      {
        key: "region",
        title: { [language]: "Region" },
        value: { [language]: `${scopeType} ${scopeCode}` },
        detail: { [language]: "Editable company summary." },
      },
      {
        key: "soil_water",
        title: { [language]: "Soil & water" },
        value: { [language]: "Confirm in field" },
        detail: { [language]: "Ask soil texture, drainage, irrigation source, and water availability." },
      },
    ],
    main_crops: [
      { crop_code: "RICE", label: { [language]: "Rice" }, reason: { [language]: "Project-preferred crop." } },
    ],
    alternate_crops: [
      { crop_code: "MAIZE", label: { [language]: "Maize" }, reason: { [language]: "Backup option." } },
    ],
    caveats: [{ [language]: "This is informational guidance only and should not block onboarding." }],
    version: "admin-v1",
  };
}

export default function LandIntelligenceSummaryPage() {
  const [scopeType, setScopeType] = useState("PIN");
  const [scopeCode, setScopeCode] = useState("560001");
  const [language, setLanguage] = useState("en");
  const [projectId, setProjectId] = useState("");
  const [seasonCode, setSeasonCode] = useState("KHARIF");
  const [cropCode, setCropCode] = useState("RICE");
  const [summary, setSummary] = useState<LandIntelligenceSummaryResponse | null>(null);
  const [payloadText, setPayloadText] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reason, setReason] = useState("Admin land-intelligence summary override");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const payload = useMemo(() => summary?.summary_payload || {}, [summary]);
  const cards = Array.isArray(payload.cards) ? payload.cards as Array<Record<string, unknown>> : [];
  const mainCrops = Array.isArray(payload.main_crops) ? payload.main_crops as Array<Record<string, unknown>> : [];
  const alternateCrops = Array.isArray(payload.alternate_crops) ? payload.alternate_crops as Array<Record<string, unknown>> : [];
  const caveats = Array.isArray(payload.caveats) ? payload.caveats as unknown[] : [];

  async function load() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const data = await landIntelligenceSummaryApi.effective({
        scope_type: scopeType,
        scope_code: scopeCode,
        language_code: language,
        project_id: projectId || undefined,
        season_code: seasonCode || undefined,
        crop_code: cropCode || undefined,
      });
      setSummary(data);
      setPayloadText(JSON.stringify(data.summary_payload || defaultPayload(scopeType, scopeCode, language), null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load land-intelligence summary");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeType, language]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  function resetEditorToTemplate() {
    setPayloadText(JSON.stringify(defaultPayload(scopeType, scopeCode, language), null, 2));
  }

  async function saveOverride() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const parsed = JSON.parse(payloadText);
      const result = await landIntelligenceSummaryApi.upsertOverride({
        project_id: projectId || null,
        scope_type: scopeType,
        scope_code: scopeCode,
        language_code: language,
        summary_payload: parsed,
        review_status: "PUBLISHED",
        review_notes: reviewNotes || null,
        reason,
      });
      setSummary(result.effective);
      setPayloadText(JSON.stringify(result.effective.summary_payload, null, 2));
      setNotice(`Override ${result.action.toLowerCase()} for ${scopeType} ${scopeCode}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save override; check JSON syntax");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateOverride() {
    if (!summary?.effective_override?.id) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await landIntelligenceSummaryApi.deactivateOverride(summary.effective_override.id, reason || "Deactivate land-intelligence summary override");
      setNotice(`Override deactivated for ${scopeType} ${scopeCode}`);
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
        <h1 className="text-2xl font-bold text-gray-900">Land intelligence summary</h1>
        <p className="mt-1 text-sm text-gray-500">
          Configure simple informational region, weather, soil/water, main-crop, and alternate-crop summaries for Android.
        </p>
      </div>

      <form onSubmit={submitSearch} className="mb-6 rounded bg-white p-5 shadow">
        <div className="grid gap-3 md:grid-cols-[130px_1fr_110px_120px_120px_1fr_auto] md:items-end">
          <label className="text-xs text-gray-500">
            Scope
            <select value={scopeType} onChange={(e) => setScopeType(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              {SCOPE_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-500">
            Scope code
            <input value={scopeCode} onChange={(e) => setScopeCode(e.target.value)} placeholder="PIN / LGD code" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
          </label>
          <label className="text-xs text-gray-500">
            Language
            <select value={language} onChange={(e) => setLanguage(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              {LANGUAGES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-500">
            Season
            <input value={seasonCode} onChange={(e) => setSeasonCode(e.target.value.toUpperCase())} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
          </label>
          <label className="text-xs text-gray-500">
            Crop
            <input value={cropCode} onChange={(e) => setCropCode(e.target.value.toUpperCase())} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
          </label>
          <label className="text-xs text-gray-500">
            Project ID override scope
            <input value={projectId} onChange={(e) => setProjectId(e.target.value)} placeholder="Optional project UUID" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
          </label>
          <button type="submit" className="rounded bg-green-700 px-5 py-2 text-sm font-medium text-white">Load</button>
        </div>
      </form>

      {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="mb-4 rounded bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading land-intelligence summary...</p> : null}

      {!loading && summary ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(420px,0.95fr)]">
          <section className="space-y-5">
            <div className="rounded bg-white p-5 shadow">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{textValue(payload.title, language)}</h2>
                  <p className="mt-1 text-sm text-gray-500">{textValue(payload.subtitle, language)}</p>
                </div>
                <span className={`rounded px-3 py-1 text-xs font-medium ${summary.summary_source.includes("OVERRIDE") ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}>
                  {summary.summary_source}
                </span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <Mini label="Scope" value={`${summary.scope.scope_type} ${summary.scope.scope_code}`} />
                <Mini label="Language" value={summary.language_code} />
                <Mini label="Season" value={summary.filters.season_code || "-"} />
                <Mini label="Crop" value={summary.filters.crop_code || "-"} />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {cards.map((card) => (
                <div key={String(card.key)} className="rounded bg-white p-4 shadow">
                  <p className="text-xs uppercase tracking-wide text-gray-400">{String(card.key)}</p>
                  <h3 className="mt-1 font-semibold text-gray-900">{textValue(card.title, language)}</h3>
                  <p className="mt-1 text-sm font-medium text-green-700">{textValue(card.value, language)}</p>
                  <p className="mt-2 text-sm text-gray-600">{textValue(card.detail, language)}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <CropList title="Main crops" rows={mainCrops} language={language} />
              <CropList title="Alternate crops" rows={alternateCrops} language={language} />
            </div>

            <div className="rounded bg-white p-5 shadow">
              <h3 className="font-semibold text-gray-900">Caveats</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-600">
                {caveats.map((item, index) => <li key={index}>{textValue(item, language)}</li>)}
              </ul>
              <p className="mt-4 rounded bg-blue-50 p-3 text-xs text-blue-700">
                Android contract: informational only, do not block onboarding, detailed click-through deferred to V2.
              </p>
            </div>
          </section>

          <section className="rounded bg-white p-5 shadow">
            <h2 className="text-lg font-semibold text-gray-900">Edit summary payload</h2>
            <p className="mt-1 text-xs text-gray-500">
              Edit the Android-ready JSON payload. Keep labels as language maps, for example {`{"en": "Rice"}`} .
            </p>

            <textarea value={payloadText} onChange={(e) => setPayloadText(e.target.value)} rows={24} className="mt-4 w-full rounded border p-3 font-mono text-xs text-gray-900" />

            <label className="mt-3 block text-xs font-medium text-gray-500">
              Review notes
              <textarea value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} rows={3} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
            </label>

            <label className="mt-3 block text-xs font-medium text-gray-500">
              Reason
              <input value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" />
            </label>

            <div className="mt-5 flex flex-wrap gap-2">
              <button disabled={saving || !payloadText.trim()} onClick={saveOverride} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                Save published summary
              </button>
              <button disabled={saving} onClick={resetEditorToTemplate} className="rounded border px-4 py-2 text-sm text-gray-700 disabled:opacity-50">
                Use simple template
              </button>
              <button disabled={saving || !summary.effective_override?.id} onClick={deactivateOverride} className="rounded border border-red-200 px-4 py-2 text-sm text-red-700 disabled:opacity-50">
                Deactivate effective summary
              </button>
            </div>

            {summary.effective_override ? (
              <div className="mt-5 rounded border p-3 text-xs text-gray-600">
                <p><b>Active override:</b> {summary.effective_override.id}</p>
                <p className="mt-1">Status: {summary.effective_override.review_status}</p>
                <p className="mt-1">Updated: {summary.effective_override.updated_at || "-"}</p>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-gray-50 p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 font-mono text-xs font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function CropList({ title, rows, language }: { title: string; rows: Array<Record<string, unknown>>; language: string }) {
  return (
    <div className="rounded bg-white p-5 shadow">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <div className="mt-3 space-y-3">
        {rows.map((row, index) => (
          <div key={`${row.crop_code || index}`} className="rounded border p-3">
            <p className="font-semibold text-gray-900">{textValue(row.label, language)} <span className="font-mono text-xs text-gray-400">{String(row.crop_code || "")}</span></p>
            <p className="mt-1 text-sm text-gray-600">{textValue(row.reason, language)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
