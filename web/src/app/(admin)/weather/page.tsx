"use client";

import { useCallback, useEffect, useState } from "react";
import { weatherApi, type WeatherProviderDto, type WeatherProvidersResponse, type WeatherRefreshPlanResponse, type WeatherSnapshotsResponse } from "@/lib/api";

export default function WeatherPage() {
  const [providers, setProviders] = useState<WeatherProvidersResponse | null>(null);
  const [refreshPlan, setRefreshPlan] = useState<WeatherRefreshPlanResponse | null>(null);
  const [snapshots, setSnapshots] = useState<WeatherSnapshotsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshingProviderId, setRefreshingProviderId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextProviders, nextPlan, nextSnapshots] = await Promise.all([
        weatherApi.providers({ enabled: true }),
        weatherApi.refreshPlan({ enabled: true }),
        weatherApi.snapshots({ includeExpired: false, limit: 100 }),
      ]);
      setProviders(nextProviders);
      setRefreshPlan(nextPlan);
      setSnapshots(nextSnapshots);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load weather data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

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

    <section className="grid gap-3 md:grid-cols-4">
      <MiniStat label="Enabled providers" value={providers?.count ?? 0} tone="blue" />
      <MiniStat label="Due now" value={refreshPlan?.due_count ?? 0} tone={(refreshPlan?.due_count || 0) > 0 ? "amber" : "green"} />
      <MiniStat label="Fresh snapshots" value={freshCount} tone={freshCount > 0 ? "green" : "amber"} />
      <MiniStat label="Refresh cadence" value="Provider-defined" tone="slate" />
    </section>

    <section className="rounded bg-white p-5 shadow">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Refresh plan</h2>
          <p className="text-xs text-gray-500">Generated at {refreshPlan?.generated_at || "-"}. Real schedulers can use this to decide which providers are due.</p>
        </div>
      </div>
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
              <td className="p-3"><button type="button" onClick={() => void recordRefresh(provider)} disabled={refreshingProviderId === provider.id} className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">{refreshingProviderId === provider.id ? "Recording..." : "Record refresh"}</button></td>
            </tr>)}
            {(!loading && planProviders.length === 0) ? <tr><td colSpan={7} className="p-6 text-center text-gray-400">No enabled weather providers configured.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>

    <section className="rounded bg-white p-5 shadow">
      <h2 className="text-lg font-semibold text-gray-900">Latest non-expired snapshots</h2>
      <p className="mb-4 mt-1 text-xs text-gray-500">These are the normalized records used by WEATHER broadcast targeting. External API payloads remain server-side metadata for audit/debug.</p>
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
