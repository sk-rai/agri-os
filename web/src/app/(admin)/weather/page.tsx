"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { broadcastsApi, weatherApi, type WeatherProviderDto, type WeatherProviderDueRunResponse, type WeatherProvidersResponse, type WeatherRefreshPlanResponse, type WeatherSnapshotDto, type WeatherSnapshotsResponse } from "@/lib/api";

const PROVIDER_TYPES = ["EXTERNAL_API", "MANUAL", "INTERNAL_MODEL", "SATELLITE", "IOT_STATION"];
const LOCATION_SCOPES = ["TENANT", "PROJECT", "FARMER", "PARCEL", "GEOPOINT", "PINCODE", "VILLAGE", "DISTRICT", "STATE", "WEATHER_GRID"];
const DEFAULT_RISK_THRESHOLDS = {
  heavy_rain_mm: 20,
  heavy_rain_probability_percent: 80,
  fungal_humidity_percent: 80,
  fungal_rain_probability_percent: 60,
  heat_stress_temperature_max_c: 38,
  high_wind_kmph: 40,
};
const OPEN_METEO_SAMPLE_CONFIG = {
  adapter: "open_meteo",
  refresh_strategy: "SNAPSHOT_6H",
  risk_thresholds: DEFAULT_RISK_THRESHOLDS,
  locations: [
    { location_scope: "VILLAGE", location_key: "Broadcast Village", lat: "12.9716", lng: "77.5946" },
  ],
  sample_payload: {
    fetched_at: "2026-07-17T12:00:00+00:00",
    current: {
      time: "2026-07-17T12:00:00+00:00",
      temperature_2m: 29.4,
      relative_humidity_2m: 88,
      rain: 22.5,
      weather_code: 63,
      wind_speed_10m: 18,
    },
    hourly: {
      precipitation_probability: [86],
      rain: [22.5],
    },
  },
};

export default function WeatherPage() {
  const [providers, setProviders] = useState<WeatherProvidersResponse | null>(null);
  const [refreshPlan, setRefreshPlan] = useState<WeatherRefreshPlanResponse | null>(null);
  const [snapshots, setSnapshots] = useState<WeatherSnapshotsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshingProviderId, setRefreshingProviderId] = useState<string | null>(null);
  const [runningAdapterProviderId, setRunningAdapterProviderId] = useState<string | null>(null);
  const [runningDueProviders, setRunningDueProviders] = useState(false);
  const [dueRunResult, setDueRunResult] = useState<WeatherProviderDueRunResponse | null>(null);
  const [savingProvider, setSavingProvider] = useState(false);
  const [providerCode, setProviderCode] = useState("");
  const [providerName, setProviderName] = useState("");
  const [providerType, setProviderType] = useState("EXTERNAL_API");
  const [refreshInterval, setRefreshInterval] = useState("6");
  const [providerEnabled, setProviderEnabled] = useState(true);
  const [providerConfig, setProviderConfig] = useState("{}");
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [creatingBroadcastSnapshotId, setCreatingBroadcastSnapshotId] = useState<string | null>(null);
  const [createdBroadcastId, setCreatedBroadcastId] = useState<string | null>(null);
  const [snapshotProviderId, setSnapshotProviderId] = useState("");
  const [snapshotScope, setSnapshotScope] = useState("VILLAGE");
  const [snapshotLocationKey, setSnapshotLocationKey] = useState("");
  const [snapshotSummary, setSnapshotSummary] = useState("");
  const [snapshotCondition, setSnapshotCondition] = useState("HEAVY_RAIN");
  const [snapshotRiskFlags, setSnapshotRiskFlags] = useState("HEAVY_RAIN_NEXT_24H");
  const [snapshotRainProbability, setSnapshotRainProbability] = useState("");
  const [snapshotRainfallMm, setSnapshotRainfallMm] = useState("");
  const [snapshotHumidity, setSnapshotHumidity] = useState("");
  const [snapshotExpiresAt, setSnapshotExpiresAt] = useState("");
  const [filterProviderId, setFilterProviderId] = useState("");
  const [filterScope, setFilterScope] = useState("");
  const [filterLocationKey, setFilterLocationKey] = useState("");
  const [includeExpired, setIncludeExpired] = useState(false);
  const [snapshotLimit, setSnapshotLimit] = useState("100");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextProviders, nextPlan, nextSnapshots] = await Promise.all([
        weatherApi.providers({ enabled: true }),
        weatherApi.refreshPlan({ enabled: true }),
        weatherApi.snapshots({
          providerId: filterProviderId || undefined,
          locationScope: filterScope || undefined,
          locationKey: filterLocationKey.trim() || undefined,
          includeExpired,
          limit: Number(snapshotLimit) || 100,
        }),
      ]);
      setProviders(nextProviders);
      setRefreshPlan(nextPlan);
      setSnapshots(nextSnapshots);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load weather data");
    } finally {
      setLoading(false);
    }
  }, [filterLocationKey, filterProviderId, filterScope, includeExpired, snapshotLimit]);

  useEffect(() => { void load(); }, [load]);

  function parseProviderConfigForEditor(): Record<string, unknown> {
    if (!providerConfig.trim()) return {};
    const parsed = JSON.parse(providerConfig);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("Provider config must be a JSON object");
    }
    return parsed as Record<string, unknown>;
  }

  function useOpenMeteoTemplate() {
    setProviderType("EXTERNAL_API");
    setRefreshInterval("6");
    setProviderEnabled(true);
    if (!providerCode.trim()) setProviderCode("open_meteo_sample");
    if (!providerName.trim()) setProviderName("Open-Meteo Sample");
    setProviderConfig(JSON.stringify(OPEN_METEO_SAMPLE_CONFIG, null, 2));
  }

  function mergeDefaultRiskThresholds() {
    try {
      const parsedConfig = parseProviderConfigForEditor();
      const existingThresholds = (parsedConfig.risk_thresholds && typeof parsedConfig.risk_thresholds === "object" && !Array.isArray(parsedConfig.risk_thresholds))
        ? parsedConfig.risk_thresholds as Record<string, unknown>
        : {};
      setProviderConfig(JSON.stringify({
        ...parsedConfig,
        risk_thresholds: { ...DEFAULT_RISK_THRESHOLDS, ...existingThresholds },
      }, null, 2));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Provider config must be valid JSON before thresholds can be merged");
    }
  }

  async function saveProvider(event: FormEvent) {
    event.preventDefault();
    if (!providerCode.trim() || !providerName.trim()) return;
    setSavingProvider(true);
    setError(null);
    try {
      const parsedConfig = parseProviderConfigForEditor();
      await weatherApi.createProvider({
        provider_code: providerCode.trim(),
        display_name: providerName.trim(),
        provider_type: providerType,
        refresh_interval_hours: Number(refreshInterval) || 6,
        is_enabled: providerEnabled,
        config: parsedConfig,
        metadata: { source: "admin_weather_page" },
      });
      setProviderCode("");
      setProviderName("");
      setProviderType("EXTERNAL_API");
      setRefreshInterval("6");
      setProviderEnabled(true);
      setProviderConfig("{}");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save provider");
    } finally {
      setSavingProvider(false);
    }
  }

  function editProvider(provider: WeatherProviderDto) {
    setProviderCode(provider.provider_code);
    setProviderName(provider.display_name);
    setProviderType(provider.provider_type);
    setRefreshInterval(String(provider.refresh_interval_hours || 6));
    setProviderEnabled(provider.is_enabled);
    setProviderConfig(JSON.stringify(provider.config || {}, null, 2));
  }

  async function saveSnapshot(event: FormEvent) {
    event.preventDefault();
    setSavingSnapshot(true);
    setError(null);
    try {
      const now = new Date();
      const expiresAt = snapshotExpiresAt ? new Date(snapshotExpiresAt) : new Date(now.getTime() + 6 * 60 * 60 * 1000);
      await weatherApi.createSnapshot({
        provider_id: snapshotProviderId || undefined,
        location_scope: snapshotScope,
        location_key: snapshotLocationKey.trim() || undefined,
        fetched_at: now.toISOString(),
        forecast_valid_from: now.toISOString(),
        expires_at: expiresAt.toISOString(),
        summary: snapshotSummary.trim() || undefined,
        condition_code: snapshotCondition.trim() || undefined,
        rainfall_probability_percent: snapshotRainProbability ? Number(snapshotRainProbability) : undefined,
        rainfall_mm: snapshotRainfallMm.trim() || undefined,
        humidity_percent: snapshotHumidity ? Number(snapshotHumidity) : undefined,
        risk_flags: snapshotRiskFlags.split(",").map((flag) => flag.trim()).filter(Boolean),
        metadata: { source: "admin_weather_page", manual_entry: true },
      });
      setSnapshotSummary("");
      setSnapshotLocationKey("");
      setSnapshotRainProbability("");
      setSnapshotRainfallMm("");
      setSnapshotHumidity("");
      setSnapshotExpiresAt("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save weather snapshot");
    } finally {
      setSavingSnapshot(false);
    }
  }

  async function recordRefresh(provider: WeatherProviderDto) {
    setRefreshingProviderId(provider.id);
    setError(null);
    try {
      await weatherApi.refreshProvider(provider.id, {
        status: "SUCCESS",
        message: "Admin manual refresh marker",
        metadata: { source: "admin_weather_page" },
        snapshots: [],
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to record refresh");
    } finally {
      setRefreshingProviderId(null);
    }
  }

  async function runAdapter(provider: WeatherProviderDto) {
    setRunningAdapterProviderId(provider.id);
    setError(null);
    try {
      await weatherApi.runAdapter(provider.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run weather adapter");
    } finally {
      setRunningAdapterProviderId(null);
    }
  }

  async function createBroadcastFromSnapshot(snapshot: WeatherSnapshotDto) {
    const riskValues = (snapshot.risk_flags && snapshot.risk_flags.length > 0)
      ? snapshot.risk_flags
      : [snapshot.condition_code].filter(Boolean) as string[];
    if (riskValues.length === 0) {
      setError("Snapshot needs condition_code or risk_flags before a weather broadcast can be targeted.");
      return;
    }
    setCreatingBroadcastSnapshotId(snapshot.id);
    setCreatedBroadcastId(null);
    setError(null);
    try {
      const titleRisk = riskValues[0].replaceAll("_", " ").toLowerCase();
      const created = await broadcastsApi.create({
        title: `Weather advisory: ${titleRisk}`,
        category: "WEATHER",
        priority: riskValues.some((flag) => ["HEAVY_RAIN_NEXT_24H", "HEAT_STRESS", "HIGH_WIND"].includes(flag)) ? "URGENT" : "HIGH",
        expires_at: snapshot.expires_at || undefined,
        metadata: {
          source: "weather_snapshot_admin_action",
          weather_snapshot_id: snapshot.id,
          location_scope: snapshot.location_scope,
          location_key: snapshot.location_key,
        },
        contents: [{
          language_code: "en",
          title: `Weather advisory: ${titleRisk}`,
          body_text: snapshot.summary || `Weather risk detected for ${snapshot.location_scope}${snapshot.location_key ? ` ${snapshot.location_key}` : ""}.`,
          deeplink_url: "agrios://broadcast/weather-advisory",
          metadata: { weather_snapshot_id: snapshot.id },
        }],
        audience_rules: [{
          rule_type: "WEATHER",
          operator: "IN",
          values: riskValues,
          metadata: { weather_snapshot_id: snapshot.id },
        }],
      });
      setCreatedBroadcastId(created.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create weather broadcast draft");
    } finally {
      setCreatingBroadcastSnapshotId(null);
    }
  }

  async function runDueProviders(dryRun: boolean) {
    setRunningDueProviders(true);
    setError(null);
    try {
      const result = await weatherApi.runDueProviders({ dryRun, limit: 50 });
      setDueRunResult(result);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run due weather providers");
    } finally {
      setRunningDueProviders(false);
    }
  }

  const planProviders = refreshPlan?.providers || [];
  const freshCount = snapshots?.count || 0;

  return <main className="space-y-6 p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Weather operations</h1>
        <p className="mt-1 text-sm text-gray-600">Backend-owned weather provider refresh planning and normalized snapshot visibility for weather-driven broadcasts.</p>
      </div>
      <button type="button" onClick={() => void load()} disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{loading ? "Refreshing..." : "Refresh"}</button>
    </div>

    {error ? <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}
    {createdBroadcastId ? <div className="rounded border border-green-200 bg-green-50 p-3 text-sm text-green-900">Weather broadcast draft created. <a className="font-semibold underline" href="/broadcasts">Open Broadcasts</a> to preview audience, publish, and generate deliveries.</div> : null}

    <section className="grid gap-3 md:grid-cols-4">
      <MiniStat label="Enabled providers" value={providers?.count ?? 0} tone="blue" />
      <MiniStat label="Due now" value={refreshPlan?.due_count ?? 0} tone={(refreshPlan?.due_count || 0) > 0 ? "amber" : "green"} />
      <MiniStat label="Fresh snapshots" value={freshCount} tone={freshCount > 0 ? "green" : "amber"} />
      <MiniStat label="Refresh cadence" value="Provider-defined" tone="slate" />
    </section>

    <section className="rounded bg-white p-5 shadow">
      <h2 className="text-lg font-semibold text-gray-900">Provider configuration</h2>
      <p className="mt-1 text-xs text-gray-500">Create or update backend weather providers. Provider code is the stable key; submitting the same code updates that provider.</p>
      <form onSubmit={saveProvider} className="mt-4 grid gap-3 md:grid-cols-6">
        <label className="text-xs text-gray-500 md:col-span-2">Provider code<input value={providerCode} onChange={(event) => setProviderCode(event.target.value)} placeholder="open-meteo" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500 md:col-span-2">Display name<input value={providerName} onChange={(event) => setProviderName(event.target.value)} placeholder="Open-Meteo" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Type<select value={providerType} onChange={(event) => setProviderType(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{PROVIDER_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
        <label className="text-xs text-gray-500">Interval hours<input type="number" min={1} max={168} value={refreshInterval} onChange={(event) => setRefreshInterval(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="flex items-center gap-2 text-sm text-gray-700 md:col-span-2"><input type="checkbox" checked={providerEnabled} onChange={(event) => setProviderEnabled(event.target.checked)} /> Enabled</label>
        <div className="rounded border border-blue-100 bg-blue-50 p-3 text-xs text-blue-900 md:col-span-6">
          <div className="font-semibold">Config helpers</div>
          <p className="mt-1">Use these to avoid hand-writing weather adapter JSON. Thresholds stay editable after insertion.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={useOpenMeteoTemplate} className="rounded bg-blue-700 px-3 py-1.5 font-medium text-white">Use Open-Meteo sample config</button>
            <button type="button" onClick={mergeDefaultRiskThresholds} className="rounded border border-blue-200 bg-white px-3 py-1.5 font-medium text-blue-800">Merge default risk thresholds</button>
          </div>
        </div>
        <label className="text-xs text-gray-500 md:col-span-6">Config JSON<textarea value={providerConfig} onChange={(event) => setProviderConfig(event.target.value)} rows={10} className="mt-1 w-full rounded border p-2 font-mono text-xs text-gray-900" /></label>
        <div className="grid gap-2 text-xs text-gray-500 md:col-span-6 lg:grid-cols-3">
          <div className="rounded bg-gray-50 p-2">Heavy rain: {DEFAULT_RISK_THRESHOLDS.heavy_rain_mm}mm or {DEFAULT_RISK_THRESHOLDS.heavy_rain_probability_percent}% probability</div>
          <div className="rounded bg-gray-50 p-2">Fungal risk: {DEFAULT_RISK_THRESHOLDS.fungal_humidity_percent}% humidity + {DEFAULT_RISK_THRESHOLDS.fungal_rain_probability_percent}% rain probability</div>
          <div className="rounded bg-gray-50 p-2">Heat/wind: {DEFAULT_RISK_THRESHOLDS.heat_stress_temperature_max_c} C / {DEFAULT_RISK_THRESHOLDS.high_wind_kmph} kmph</div>
        </div>
        <div className="flex items-end gap-2 md:col-span-6">
          <button type="submit" disabled={savingProvider || !providerCode.trim() || !providerName.trim()} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{savingProvider ? "Saving..." : "Save provider"}</button>
          <button type="button" onClick={() => { setProviderCode(""); setProviderName(""); setProviderType("EXTERNAL_API"); setRefreshInterval("6"); setProviderEnabled(true); setProviderConfig("{}"); }} className="rounded border px-4 py-2 text-sm text-gray-700">Clear</button>
        </div>
      </form>
    </section>

    <section className="rounded bg-white p-5 shadow">
      <h2 className="text-lg font-semibold text-gray-900">Manual weather snapshot</h2>
      <p className="mt-1 text-xs text-gray-500">Seed a normalized weather snapshot for testing or manual operations. WEATHER broadcasts consume these saved snapshots.</p>
      <form onSubmit={saveSnapshot} className="mt-4 grid gap-3 md:grid-cols-6">
        <label className="text-xs text-gray-500 md:col-span-2">Provider<select value={snapshotProviderId} onChange={(event) => setSnapshotProviderId(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">No provider/manual</option>{(providers?.providers || []).map((provider) => <option key={provider.id} value={provider.id}>{provider.display_name}</option>)}</select></label>
        <label className="text-xs text-gray-500">Scope<select value={snapshotScope} onChange={(event) => setSnapshotScope(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{LOCATION_SCOPES.map((scope) => <option key={scope} value={scope}>{scope}</option>)}</select></label>
        <label className="text-xs text-gray-500 md:col-span-2">Location key<input value={snapshotLocationKey} onChange={(event) => setSnapshotLocationKey(event.target.value)} placeholder="Village / pincode / grid key" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Expires at<input type="datetime-local" value={snapshotExpiresAt} onChange={(event) => setSnapshotExpiresAt(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500 md:col-span-2">Condition code<input value={snapshotCondition} onChange={(event) => setSnapshotCondition(event.target.value)} placeholder="HEAVY_RAIN" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500 md:col-span-2">Risk flags<input value={snapshotRiskFlags} onChange={(event) => setSnapshotRiskFlags(event.target.value)} placeholder="HEAVY_RAIN_NEXT_24H,FUNGAL_RISK" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Rain %<input type="number" min={0} max={100} value={snapshotRainProbability} onChange={(event) => setSnapshotRainProbability(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Rain mm<input value={snapshotRainfallMm} onChange={(event) => setSnapshotRainfallMm(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Humidity %<input type="number" min={0} max={100} value={snapshotHumidity} onChange={(event) => setSnapshotHumidity(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500 md:col-span-4">Summary<input value={snapshotSummary} onChange={(event) => setSnapshotSummary(event.target.value)} placeholder="Heavy rainfall likely in next 24 hours" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <div className="flex items-end md:col-span-2"><button type="submit" disabled={savingSnapshot} className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{savingSnapshot ? "Saving..." : "Save snapshot"}</button></div>
      </form>
    </section>

    <section className="rounded bg-white p-5 shadow">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Refresh plan</h2>
          <p className="text-xs text-gray-500">Generated at {refreshPlan?.generated_at || "-"}. Cron or workers can call the due-run endpoint; admin can preview and trigger it here.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void runDueProviders(true)} disabled={runningDueProviders} className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900 disabled:opacity-50">Preview due</button>
          <button type="button" onClick={() => void runDueProviders(false)} disabled={runningDueProviders} className="rounded bg-amber-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">{runningDueProviders ? "Running..." : "Run due providers"}</button>
        </div>
      </div>
      {dueRunResult ? <div className="mb-4 rounded border border-amber-100 bg-amber-50 p-3 text-xs text-amber-950">
        <div className="font-semibold">Last due-run {dueRunResult.dry_run ? "preview" : "execution"}: {dueRunResult.due_count} due, {dueRunResult.processed_count} processed, {dueRunResult.created_snapshot_count} snapshot(s) created.</div>
        {dueRunResult.providers.length ? <div className="mt-2 grid gap-2 md:grid-cols-2">
          {dueRunResult.providers.slice(0, 6).map((row) => <div key={row.provider_id} className="rounded bg-white p-2">
            <div className="font-semibold text-gray-900">{row.provider?.display_name || row.display_name || row.provider_code}</div>
            <div className="mt-1 text-gray-600">{row.status || row.refresh_status || (row.is_due ? "DUE" : "SCHEDULED")}: {row.message || row.refresh_message || "-"}</div>
            {row.created_snapshot_count !== undefined ? <div className="mt-1 text-gray-500">Created snapshots: {row.created_snapshot_count}</div> : null}
          </div>)}
        </div> : <div className="mt-2 text-amber-800">No providers are due right now.</div>}
      </div> : null}
      {loading ? <p className="text-sm text-gray-500">Loading providers...</p> : null}
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500"><tr><th className="p-3">Provider</th><th className="p-3">Type</th><th className="p-3">Interval</th><th className="p-3">Last refresh</th><th className="p-3">Next refresh</th><th className="p-3">Status</th><th className="p-3">Action</th></tr></thead>
          <tbody className="divide-y">
            {planProviders.map((provider) => <tr key={provider.id}>
              <td className="p-3"><div className="font-semibold text-gray-900">{provider.display_name}</div><div className="text-xs text-gray-500">{provider.provider_code}</div></td>
              <td className="p-3 text-gray-700">{provider.provider_type}</td>
              <td className="p-3 text-gray-700">{provider.refresh_interval_hours}h</td>
              <td className="p-3 text-gray-700">{provider.last_refresh_at || "Never"}</td>
              <td className="p-3 text-gray-700">{provider.next_refresh_at || "Due now"}</td>
              <td className="p-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${provider.is_due ? "bg-amber-100 text-amber-800" : "bg-green-100 text-green-800"}`}>{provider.is_due ? "Due" : "Scheduled"}</span>{provider.refresh_status ? <div className="mt-1 text-xs text-gray-500">{provider.refresh_status}: {provider.refresh_message || "-"}</div> : null}</td>
              <td className="p-3"><div className="flex flex-wrap gap-2"><button type="button" onClick={() => editProvider(provider)} className="rounded border px-3 py-1.5 text-xs font-medium text-gray-700">Edit</button><button type="button" onClick={() => void runAdapter(provider)} disabled={runningAdapterProviderId === provider.id} className="rounded bg-blue-700 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">{runningAdapterProviderId === provider.id ? "Running..." : "Run adapter"}</button><button type="button" onClick={() => void recordRefresh(provider)} disabled={refreshingProviderId === provider.id} className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">{refreshingProviderId === provider.id ? "Recording..." : "Record refresh"}</button></div></td>
            </tr>)}
            {(!loading && planProviders.length === 0) ? <tr><td colSpan={7} className="p-6 text-center text-gray-400">No enabled weather providers configured.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>

    <section className="rounded bg-white p-5 shadow">
      <h2 className="text-lg font-semibold text-gray-900">Weather snapshots</h2>
      <p className="mt-1 text-xs text-gray-500">These are the normalized records used by WEATHER broadcast targeting. External API payloads remain server-side metadata for audit/debug.</p>
      <form onSubmit={(event) => { event.preventDefault(); void load(); }} className="my-4 grid gap-3 md:grid-cols-6">
        <label className="text-xs text-gray-500 md:col-span-2">Provider<select value={filterProviderId} onChange={(event) => setFilterProviderId(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">All providers</option>{(providers?.providers || []).map((provider) => <option key={provider.id} value={provider.id}>{provider.display_name}</option>)}</select></label>
        <label className="text-xs text-gray-500">Scope<select value={filterScope} onChange={(event) => setFilterScope(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900"><option value="">All scopes</option>{LOCATION_SCOPES.map((scope) => <option key={scope} value={scope}>{scope}</option>)}</select></label>
        <label className="text-xs text-gray-500 md:col-span-2">Location key<input value={filterLocationKey} onChange={(event) => setFilterLocationKey(event.target.value)} placeholder="Exact location key" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="text-xs text-gray-500">Limit<input type="number" min={1} max={500} value={snapshotLimit} onChange={(event) => setSnapshotLimit(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <label className="flex items-center gap-2 text-sm text-gray-700 md:col-span-2"><input type="checkbox" checked={includeExpired} onChange={(event) => setIncludeExpired(event.target.checked)} /> Include expired snapshots</label>
        <div className="flex items-end gap-2 md:col-span-4">
          <button type="submit" disabled={loading} className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply filters</button>
          <button type="button" onClick={() => { setFilterProviderId(""); setFilterScope(""); setFilterLocationKey(""); setIncludeExpired(false); setSnapshotLimit("100"); }} className="rounded border px-4 py-2 text-sm text-gray-700">Clear filters</button>
        </div>
      </form>
      <div className="mb-4 rounded bg-gray-50 p-2 text-xs text-gray-500">Showing {snapshots?.count ?? 0} snapshot(s). Filters: provider {filterProviderId || "all"}, scope {filterScope || "all"}, location {filterLocationKey || "all"}, expired {includeExpired ? "included" : "excluded"}.</div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(snapshots?.snapshots || []).map((snapshot) => <article key={snapshot.id} className="rounded border p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-gray-900">{snapshot.location_scope}{snapshot.location_key ? ` / ${snapshot.location_key}` : ""}</span>
            <span className="rounded bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-800">{snapshot.condition_code || "UNKNOWN"}</span>
          </div>
          <p className="mt-2 text-gray-600">{snapshot.summary || "No summary"}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-500">
            <div>Fetched: {snapshot.fetched_at || "-"}</div>
            <div>Expires: {snapshot.expires_at || "-"}</div>
            <div>Rain: {snapshot.rainfall_probability_percent ?? "-"}% / {snapshot.rainfall_mm || "-"}mm</div>
            <div>Humidity: {snapshot.humidity_percent ?? "-"}%</div>
          </div>
          {snapshot.risk_flags?.length ? <div className="mt-3 flex flex-wrap gap-1">{snapshot.risk_flags.map((flag) => <span key={flag} className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">{flag}</span>)}</div> : null}
          <button type="button" onClick={() => void createBroadcastFromSnapshot(snapshot)} disabled={creatingBroadcastSnapshotId === snapshot.id} className="mt-3 rounded bg-green-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">{creatingBroadcastSnapshotId === snapshot.id ? "Creating draft..." : "Create broadcast draft"}</button>
        </article>)}
        {(!loading && (!snapshots || snapshots.snapshots.length === 0)) ? <p className="rounded border border-dashed p-6 text-center text-sm text-gray-400">No fresh snapshots yet.</p> : null}
      </div>
    </section>
  </main>;
}

function MiniStat({ label, value, tone }: { label: string; value: string | number; tone: "blue" | "green" | "amber" | "slate" }) {
  const tones = {
    blue: "border-blue-200 bg-blue-50 text-blue-900",
    green: "border-green-200 bg-green-50 text-green-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    slate: "border-slate-200 bg-slate-50 text-slate-900",
  };
  return <div className={`rounded border p-4 ${tones[tone]}`}><div className="text-xs uppercase tracking-wide opacity-70">{label}</div><div className="mt-2 text-2xl font-bold">{value}</div></div>;
}
