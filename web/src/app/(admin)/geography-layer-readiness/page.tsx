"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

const numberFormatter = new Intl.NumberFormat("en-IN");

function formatNumber(value: number | null | undefined) {
  return numberFormatter.format(value ?? 0);
}

function formatPercent(numerator: number, denominator: number) {
  if (!denominator) return "0%";
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

type MatrixRow = {
  state_or_ut: string;
  district: string;
  state_lgd_code: string;
  district_lgd_code: string;
  lgd_village_count: number;
  pin_linked_village_count: number;
  pin_link_count: number;
  demographic_profile_row_count: number;
  demographic_active_promoted_count: number;
  demographic_blocked_count: number;
  demographic_remaining_eligible_count: number;
  boundary_candidate_count: number;
  boundary_direct_vlcode_match_count: number;
  boundary_auto_candidate_count: number;
  boundary_manual_review_count: number;
  boundary_blocked_count: number;
  boundary_promoted_candidate_count: number;
  boundary_runtime_crosswalk_count: number;
  boundary_runtime_feature_count: number;
  project_boundary_match_count: number;
  climate_mapping_count: number;
  climate_region_count: number;
  crop_climate_rule_count: number;
  lgd_runtime_ready: boolean;
  pin_code_runtime_ready: boolean;
  demographic_admin_ready: boolean;
  demographic_android_enabled: boolean;
  boundary_admin_review_ready: boolean;
  boundary_runtime_ready: boolean;
  boundary_runtime_pilot_present: boolean;
  project_boundary_matching_ready: boolean;
  climate_admin_review_ready: boolean;
  climate_runtime_ready: boolean;
  soi_direct_join_safe: boolean;
  bharatlas_operational_review_source: boolean;
};

type MatrixResponse = {
  schema_version: string;
  generated_at: string;
  healthy: boolean;
  mode: string;
  filters: {
    state_or_ut?: string | null;
    district?: string | null;
    limit: number;
  };
  summary: Record<string, number>;
  gap_accounting: Record<string, number>;
  rows: MatrixRow[];
  source_posture: Record<string, boolean>;
  guardrails: Record<string, boolean>;
  recommended_next_steps: string[];
};

function StatusPill({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ring-1 ring-inset ${
        ready
          ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
          : "bg-amber-50 text-amber-800 ring-amber-600/20"
      }`}
    >
      {ready ? "Ready" : "Not ready"} · {label}
    </span>
  );
}

function StatCard({
  label,
  value,
  note,
  tone = "slate",
}: {
  label: string;
  value: number;
  note?: string;
  tone?: "slate" | "emerald" | "amber" | "rose" | "blue";
}) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-950",
    amber: "border-amber-200 bg-amber-50 text-amber-950",
    rose: "border-rose-200 bg-rose-50 text-rose-950",
    blue: "border-blue-200 bg-blue-50 text-blue-950",
  };

  return (
    <div className={`rounded-2xl border p-4 shadow-sm ${tones[tone]}`}>
      <p className="text-sm text-slate-600">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{formatNumber(value)}</p>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

function readinessTone(row: MatrixRow) {
  if (row.project_boundary_matching_ready || row.boundary_runtime_ready) return "bg-emerald-50";
  if (row.boundary_candidate_count || row.climate_mapping_count) return "bg-blue-50";
  return "bg-white";
}

export default function GeographyLayerReadinessPage() {
  const [stateOrUt, setStateOrUt] = useState("");
  const [district, setDistrict] = useState("");
  const [limit, setLimit] = useState(5000);
  const [data, setData] = useState<MatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMatrix = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    if (stateOrUt.trim()) params.set("state_or_ut", stateOrUt.trim());
    if (district.trim()) params.set("district", district.trim());
    params.set("limit", String(limit));

    try {
      const response = await api<MatrixResponse>(`/api/v1/master-data/geography/layer-readiness?${params.toString()}`);
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load geography layer readiness");
    } finally {
      setLoading(false);
    }
  }, [district, limit, stateOrUt]);

  useEffect(() => {
    void loadMatrix();
  }, [loadMatrix]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadMatrix();
  }

  const rows = data?.rows ?? [];
  const summary = data?.summary ?? {};
  const gap = data?.gap_accounting ?? {};

  const stateOptions = useMemo(
    () => Array.from(new Set(rows.map((row) => row.state_or_ut))).sort(),
    [rows],
  );

  const districtOptions = useMemo(
    () =>
      Array.from(
        new Set(
          rows
            .filter((row) => !stateOrUt || row.state_or_ut === stateOrUt)
            .map((row) => row.district),
        ),
      ).sort(),
    [rows, stateOrUt],
  );

  const filteredRows = rows
    .filter((row) => !stateOrUt || row.state_or_ut === stateOrUt)
    .filter((row) => !district || row.district === district);

  return (
    <main className="space-y-6 p-6">
      <div>
        <p className="text-sm font-medium uppercase tracking-wide text-emerald-700">
          Geography layer readiness
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
          Cross-layer state and district matrix
        </h1>
        <p className="mt-2 max-w-5xl text-sm text-slate-600">
          Read-only admin view of LGD, PIN-code, NWDP demographic, NWDP boundary,
          project boundary, climate/agro-ecology, SOI posture, and BharatAtlas posture.
          Android runtime remains LGD plus PIN-code only; NWDP demographic and boundary
          layers stay admin/web-only until separately enabled.
        </p>
      </div>

      <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
        <h2 className="text-base font-semibold text-emerald-950">Runtime posture</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <StatusPill ready={Boolean(data?.source_posture.lgd_is_canonical_runtime_identity)} label="LGD canonical runtime identity" />
          <StatusPill ready={Boolean(data?.source_posture.village_pin_codes_android_ready)} label="Village PIN-code lookup" />
          <StatusPill ready={!data?.source_posture.nwdp_demographic_android_enabled} label="NWDP demographic Android-disabled" />
          <StatusPill ready={!data?.source_posture.nwdp_boundary_runtime_lookup_enabled} label="NWDP boundary runtime-disabled" />
          <StatusPill ready={!data?.source_posture.soi_direct_lgd_join_safe} label="SOI direct join blocked" />
          <StatusPill ready={Boolean(data?.source_posture.bharatlas_operational_review_source)} label="BharatAtlas review source" />
        </div>
      </section>

      <form onSubmit={onSubmit} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-4">
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">State / UT</span>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={stateOrUt}
            onChange={(event) => {
              setStateOrUt(event.target.value);
              setDistrict("");
            }}
          >
            <option value="">All states</option>
            {stateOptions.map((state) => (
              <option key={state} value={state}>{state}</option>
            ))}
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">District</span>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={district}
            onChange={(event) => setDistrict(event.target.value)}
          >
            <option value="">All districts</option>
            {districtOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Limit</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            min={1}
            max={5000}
            type="number"
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
          />
        </label>

        <button className="self-end rounded-xl bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800">
          Refresh
        </button>
      </form>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
          Loading geography layer readiness…
        </div>
      )}

      {data && (
        <>
          <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
            <StatCard label="LGD villages" value={summary.lgd_village_count} tone="emerald" note="Canonical runtime spine" />
            <StatCard label="PIN-linked villages" value={summary.pin_linked_village_count} tone="emerald" note={`${formatPercent(summary.pin_linked_village_count, summary.lgd_village_count)} of LGD villages`} />
            <StatCard label="Demographic profiles" value={summary.demographic_profile_row_count} tone="blue" note={`${formatNumber(summary.demographic_active_promoted_count)} active promoted`} />
            <StatCard label="Boundary candidates" value={summary.boundary_candidate_count} tone="blue" note="District-placeable matrix count" />
            <StatCard label="Climate mappings" value={summary.climate_mapping_count} tone="amber" note={`${formatNumber(summary.climate_region_count)} region touches`} />
            <StatCard label="Project boundary matches" value={summary.project_boundary_match_count} tone="rose" note="Apply not started" />
          </section>

          <section className="grid gap-4 md:grid-cols-3">
            <StatCard
              label="Boundary raw candidates"
              value={gap.boundary_candidate_raw_count}
              tone="blue"
              note="All staged NWDP boundary candidates"
            />
            <StatCard
              label="Boundary outside matrix"
              value={gap.boundary_candidate_outside_state_district_matrix_count}
              tone="amber"
              note="Needs reconciliation before broad runtime promotion"
            />
            <StatCard
              label="Demographic outside matrix"
              value={gap.demographic_profile_outside_state_district_matrix_count}
              tone="emerald"
              note="Expected zero after full admin rollout"
            />
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">Recommended next steps</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {data.recommended_next_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </section>

          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-4 py-3">
              <h2 className="text-base font-semibold text-slate-950">State/district readiness matrix</h2>
              <p className="text-sm text-slate-500">
                Showing {formatNumber(filteredRows.length)} of {formatNumber(rows.length)} district rows.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3">State / District</th>
                    <th className="px-4 py-3">LGD villages</th>
                    <th className="px-4 py-3">PIN linked</th>
                    <th className="px-4 py-3">Demographic</th>
                    <th className="px-4 py-3">Boundary</th>
                    <th className="px-4 py-3">Climate</th>
                    <th className="px-4 py-3">Project boundary</th>
                    <th className="px-4 py-3">Runtime posture</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredRows.map((row) => (
                    <tr key={`${row.state_lgd_code}:${row.district_lgd_code}`} className={readinessTone(row)}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-950">{row.district}</div>
                        <div className="text-xs text-slate-500">
                          {row.state_or_ut} · LGD {row.state_lgd_code}/{row.district_lgd_code}
                        </div>
                      </td>
                      <td className="px-4 py-3">{formatNumber(row.lgd_village_count)}</td>
                      <td className="px-4 py-3">
                        <div>{formatNumber(row.pin_linked_village_count)}</div>
                        <div className="text-xs text-slate-500">{formatPercent(row.pin_linked_village_count, row.lgd_village_count)}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div>{formatNumber(row.demographic_profile_row_count)} profiles</div>
                        <div className="text-xs text-slate-500">
                          {formatNumber(row.demographic_active_promoted_count)} active · {formatNumber(row.demographic_blocked_count)} blocked
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div>{formatNumber(row.boundary_candidate_count)} candidates</div>
                        <div className="text-xs text-slate-500">
                          {formatNumber(row.boundary_auto_candidate_count)} auto · {formatNumber(row.boundary_manual_review_count)} manual · {formatNumber(row.boundary_blocked_count)} blocked
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div>{formatNumber(row.climate_mapping_count)} mappings</div>
                        <div className="text-xs text-slate-500">{formatNumber(row.crop_climate_rule_count)} crop rules</div>
                      </td>
                      <td className="px-4 py-3">{formatNumber(row.project_boundary_match_count)}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <StatusPill ready={row.lgd_runtime_ready && row.pin_code_runtime_ready} label="Android geography" />
                          <StatusPill ready={row.demographic_admin_ready && !row.demographic_android_enabled} label="Demographic admin-only" />
                          <StatusPill ready={row.boundary_runtime_ready} label="Boundary runtime" />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
