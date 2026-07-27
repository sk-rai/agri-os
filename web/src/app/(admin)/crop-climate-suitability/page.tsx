"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type ClimateRegion = {
  region_code: string;
  region_name: string;
  region_system: string;
  confidence: string;
  review_status: string;
  rainfall_band_mm?: Record<string, unknown>;
  temperature_band_c?: Record<string, unknown>;
  dominant_soil_groups?: string[];
  irrigation_context?: Record<string, unknown>;
  mappings?: Array<{
    scope_level: string;
    state_lgd_code?: string | null;
    district_lgd_code?: string | null;
    metadata?: Record<string, unknown>;
  }>;
};

type SuitabilityRule = {
  rule_id: string;
  crop_code: string;
  season_code: string;
  region_code: string;
  suitability_status: string;
  confidence: string;
  irrigation_required: boolean;
  warning_rules: Array<Record<string, unknown>>;
  review_status: string;
};

type OverrideRow = {
  override_id: string;
  tenant_id: string;
  project_id?: string | null;
  crop_code: string;
  season_code: string;
  region_code: string;
  suitability_status: string;
  confidence: string;
  review_status: string;
  reason?: string | null;
};

const SEASONS = ["KHARIF", "RABI", "ZAID", "PERENNIAL"];
const STATUSES = ["HIGHLY_SUITABLE", "SUITABLE", "CONDITIONAL", "NOT_TYPICAL", "UNSUITABLE", "UNKNOWN"];

function pretty(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export default function CropClimateSuitabilityPage() {
  const [regions, setRegions] = useState<ClimateRegion[]>([]);
  const [rules, setRules] = useState<SuitabilityRule[]>([]);
  const [overrides, setOverrides] = useState<OverrideRow[]>([]);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [cropCode, setCropCode] = useState("RICE");
  const [seasonCode, setSeasonCode] = useState("KHARIF");
  const [regionCode, setRegionCode] = useState("IND_ACZ_SOUTHERN_PLATEAU_HILLS_KA");
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("CONDITIONAL");
  const [warningMessage, setWarningMessage] = useState("Client policy requires local suitability confirmation before onboarding.");
  const [reason, setReason] = useState("Client/admin customization of agro-climatic suitability intelligence.");

  const selectedRegion = useMemo(
    () => regions.find((region) => region.region_code === regionCode),
    [regions, regionCode]
  );
  const selectedStateCode = selectedRegion?.mappings?.find((mapping) => mapping.state_lgd_code)?.state_lgd_code || "";

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [regionResult, ruleResult, overrideResult] = await Promise.all([
        api<{ regions: ClimateRegion[] }>("/api/v1/crop-catalog/suitability-regions"),
        api<{ rules: SuitabilityRule[] }>("/api/v1/crop-catalog/suitability-rules?limit=300"),
        api<{ overrides: OverrideRow[] }>("/api/v1/crop-catalog/suitability-overrides"),
      ]);
      setRegions(regionResult.regions || []);
      setRules(ruleResult.rules || []);
      setOverrides(overrideResult.overrides || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load crop climate suitability metadata");
    } finally {
      setLoading(false);
    }
  }

  async function previewEffective() {
    setError(null);
    setMessage(null);
    setPreview(null);
    try {
      if (!selectedStateCode) throw new Error("Selected region has no state mapping.");
      const params = new URLSearchParams({
        crop_code: cropCode.trim().toUpperCase(),
        season_code: seasonCode,
        state_lgd_code: selectedStateCode,
      });
      if (projectId.trim()) params.set("project_id", projectId.trim());
      const result = await api<Record<string, unknown>>(`/api/v1/crop-catalog/suitability?${params.toString()}`);
      setPreview(result);
      setMessage("Effective suitability preview loaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    }
  }

  async function publishOverride() {
    setError(null);
    setMessage(null);
    try {
      const warningRules = warningMessage.trim()
        ? [{
            code: "CLIENT_CLIMATE_SUITABILITY_OVERRIDE",
            severity: status === "UNSUITABLE" || status === "NOT_TYPICAL" ? "WARNING" : "INFO",
            message: warningMessage.trim(),
          }]
        : [];
      await api("/api/v1/crop-catalog/suitability-overrides", {
        method: "POST",
        body: {
          crop_code: cropCode.trim().toUpperCase(),
          season_code: seasonCode,
          region_code: regionCode,
          project_id: projectId.trim() || null,
          suitability_status: status,
          irrigation_required: status === "CONDITIONAL",
          warning_rules: warningRules,
          reason,
          review_notes: "Published from admin crop climate suitability page.",
          metadata: { admin_ui: "crop-climate-suitability" },
        },
      });
      setMessage("Override published. Reloading effective metadata.");
      await load();
      await previewEffective();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish override failed");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="space-y-6 p-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-green-700">Configuration</p>
        <h1 className="text-2xl font-bold text-gray-900">Crop Climate Suitability</h1>
        <p className="mt-2 max-w-4xl text-sm text-gray-600">
          Backend-owned agro-climatic intelligence layer. Defaults are seeded centrally; tenant/project overrides customize
          suitability without changing reference metadata. Android should render the effective backend result and warnings.
        </p>
      </div>

      {loading && <div className="rounded-lg border bg-white p-4 text-sm text-gray-600">Loading suitability metadata…</div>}
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {message && <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-700">{message}</div>}

      <section className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border bg-white p-4">
          <p className="text-xs uppercase text-gray-500">Regions</p>
          <p className="mt-1 text-2xl font-bold">{regions.length}</p>
        </div>
        <div className="rounded-lg border bg-white p-4">
          <p className="text-xs uppercase text-gray-500">Default rules</p>
          <p className="mt-1 text-2xl font-bold">{rules.length}</p>
        </div>
        <div className="rounded-lg border bg-white p-4">
          <p className="text-xs uppercase text-gray-500">Overrides</p>
          <p className="mt-1 text-2xl font-bold">{overrides.length}</p>
        </div>
        <div className="rounded-lg border bg-white p-4">
          <p className="text-xs uppercase text-gray-500">Layer mode</p>
          <p className="mt-1 text-sm font-semibold text-green-700">Advisory intelligence</p>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-5">
        <h2 className="text-lg font-semibold">Preview / publish override</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="font-medium">Crop code</span>
            <input value={cropCode} onChange={(e) => setCropCode(e.target.value)} className="w-full rounded border px-3 py-2" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Season</span>
            <select value={seasonCode} onChange={(e) => setSeasonCode(e.target.value)} className="w-full rounded border px-3 py-2">
              {SEASONS.map((season) => <option key={season}>{season}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Region</span>
            <select value={regionCode} onChange={(e) => setRegionCode(e.target.value)} className="w-full rounded border px-3 py-2">
              {regions.map((region) => <option key={region.region_code} value={region.region_code}>{region.region_name}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Project ID optional</span>
            <input value={projectId} onChange={(e) => setProjectId(e.target.value)} className="w-full rounded border px-3 py-2" placeholder="tenant-level if blank" />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Override status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="w-full rounded border px-3 py-2">
              {STATUSES.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Mapped state LGD</span>
            <input value={selectedStateCode || "—"} readOnly className="w-full rounded border bg-gray-50 px-3 py-2" />
          </label>
        </div>
        <label className="mt-4 block space-y-1 text-sm">
          <span className="font-medium">Warning text</span>
          <textarea value={warningMessage} onChange={(e) => setWarningMessage(e.target.value)} className="h-20 w-full rounded border px-3 py-2" />
        </label>
        <label className="mt-4 block space-y-1 text-sm">
          <span className="font-medium">Reason</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded border px-3 py-2" />
        </label>
        <div className="mt-4 flex gap-3">
          <button onClick={previewEffective} className="rounded bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-700">
            Preview effective result
          </button>
          <button onClick={publishOverride} className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white hover:bg-green-600">
            Publish override
          </button>
        </div>
      </section>

      {preview && (
        <section className="rounded-lg border bg-white p-5">
          <h2 className="text-lg font-semibold">Effective preview</h2>
          <pre className="mt-3 max-h-96 overflow-auto rounded bg-gray-950 p-4 text-xs text-gray-100">
            {JSON.stringify(preview, null, 2)}
          </pre>
        </section>
      )}

      <section className="rounded-lg border bg-white p-5">
        <h2 className="text-lg font-semibold">Climate regions</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {regions.map((region) => (
            <article key={region.region_code} className="rounded border p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold">{region.region_name}</h3>
                  <p className="mt-1 text-xs text-gray-500">{region.region_code}</p>
                </div>
                <span className="rounded bg-yellow-100 px-2 py-1 text-xs font-semibold text-yellow-800">{region.review_status}</span>
              </div>
              <dl className="mt-3 grid gap-2 text-xs text-gray-700">
                <div><dt className="font-semibold">System</dt><dd>{region.region_system}</dd></div>
                <div><dt className="font-semibold">Confidence</dt><dd>{region.confidence}</dd></div>
                <div><dt className="font-semibold">Rainfall</dt><dd>{pretty(region.rainfall_band_mm)}</dd></div>
                <div><dt className="font-semibold">Temperature</dt><dd>{pretty(region.temperature_band_c)}</dd></div>
                <div><dt className="font-semibold">Dominant soils</dt><dd>{pretty(region.dominant_soil_groups)}</dd></div>
                <div><dt className="font-semibold">Mappings</dt><dd>{pretty(region.mappings)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-lg border bg-white p-5">
        <h2 className="text-lg font-semibold">Default suitability rules</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2">Crop</th>
                <th className="px-3 py-2">Season</th>
                <th className="px-3 py-2">Region</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Confidence</th>
                <th className="px-3 py-2">Review</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.rule_id} className="border-t">
                  <td className="px-3 py-2 font-medium">{rule.crop_code}</td>
                  <td className="px-3 py-2">{rule.season_code}</td>
                  <td className="px-3 py-2 text-xs">{rule.region_code}</td>
                  <td className="px-3 py-2">{rule.suitability_status}</td>
                  <td className="px-3 py-2">{rule.confidence}</td>
                  <td className="px-3 py-2">{rule.review_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
