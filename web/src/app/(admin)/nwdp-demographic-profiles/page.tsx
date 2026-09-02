"use client"

import { FormEvent, useCallback, useEffect, useState } from "react"
import {
  nwdpDemographicProfilesApi,
  type NwdpDemographicProfileRow,
  type NwdpDemographicProfilesPreviewResponse,
} from "@/lib/api"

const numberFormatter = new Intl.NumberFormat("en-IN")

function formatNumber(value: number | null | undefined) {
  return numberFormatter.format(value ?? 0)
}

function statusClass(value: string) {
  if (value === "PROMOTED" || value === "APPROVED_FOR_PROMOTION") {
    return "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
  }
  if (value === "AUTO_CANDIDATE") {
    return "bg-blue-50 text-blue-700 ring-blue-600/20"
  }
  return "bg-slate-50 text-slate-700 ring-slate-600/20"
}

function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ring-1 ring-inset ${statusClass(value)}`}>
      {value.replaceAll("_", " ")}
    </span>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-900">{formatNumber(value)}</p>
    </div>
  )
}

function promotedFirst(a: NwdpDemographicProfileRow, b: NwdpDemographicProfileRow) {
  const aPromoted = a.is_active && a.promotion_status === "PROMOTED"
  const bPromoted = b.is_active && b.promotion_status === "PROMOTED"
  if (aPromoted !== bPromoted) return aPromoted ? -1 : 1
  return a.source_village_name.localeCompare(b.source_village_name)
}

export default function NwdpDemographicProfilesPage() {
  const [stateOrUt, setStateOrUt] = useState("Andaman & Nicobar Island")
  const [district, setDistrict] = useState("South Andamans")
  const [limit, setLimit] = useState(200)
  const [data, setData] = useState<NwdpDemographicProfilesPreviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadPreview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await nwdpDemographicProfilesApi.preview({
        state_or_ut: stateOrUt.trim() || undefined,
        district: district.trim() || undefined,
        limit,
      })
      setData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load NWDP demographic profiles")
    } finally {
      setLoading(false)
    }
  }, [district, limit, stateOrUt])

  useEffect(() => {
    void loadPreview()
  }, [loadPreview])

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void loadPreview()
  }

  const summary = data?.summary
  const rows = [...(data?.items ?? [])].sort(promotedFirst)
  const promotedRows = rows.filter((row) => row.is_active && row.promotion_status === "PROMOTED")

  return (
    <main className="space-y-6 p-6">
      <div>
        <p className="text-sm font-medium uppercase tracking-wide text-emerald-700">NWDP demographic profiles</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
          Promoted village demographics
        </h1>
        <p className="mt-2 max-w-4xl text-sm text-slate-600">
          Read-only admin view for promoted and staged NWDP-derived village demographic profiles.
          Runtime lookup and Android behavior remain disabled until separately enabled.
        </p>
      </div>

      <form onSubmit={onSubmit} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-[1fr_1fr_120px_auto]">
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">State / UT</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={stateOrUt}
            onChange={(event) => setStateOrUt(event.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">District</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={district}
            onChange={(event) => setDistrict(event.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Limit</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            min={1}
            max={500}
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
          Loading demographic profiles…
        </div>
      )}

      {summary && (
        <>
          <section className="grid gap-4 md:grid-cols-5">
            <StatCard label="Profiles" value={summary.profile_row_count} />
            <StatCard label="Active" value={summary.active_profile_row_count} />
            <StatCard label="Promoted" value={summary.promoted_profile_row_count} />
            <StatCard label="Approved" value={summary.approved_for_promotion_count} />
            <StatCard label="Auto candidates" value={summary.auto_candidate_count} />
          </section>

          <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
            <p className="text-sm font-semibold text-emerald-900">
              {formatNumber(promotedRows.length)} promoted profile rows shown in this result set.
            </p>
            <p className="mt-1 text-sm text-emerald-800">{data?.claim_boundary}</p>
          </section>

          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-4 py-3">
              <h2 className="text-base font-semibold text-slate-950">Village profiles</h2>
              <p className="text-sm text-slate-500">
                Promoted and active rows are sorted first for quick verification.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Village</th>
                    <th className="px-4 py-3">Subdistrict</th>
                    <th className="px-4 py-3">Population</th>
                    <th className="px-4 py-3">Households</th>
                    <th className="px-4 py-3">Review</th>
                    <th className="px-4 py-3">Promotion</th>
                    <th className="px-4 py-3">Active</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((row) => (
                    <tr key={row.profile_id} className={row.is_active ? "bg-emerald-50/50" : "bg-white"}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-950">{row.source_village_name}</div>
                        <div className="text-xs text-slate-500">VLCode {row.source_vlcode ?? "—"}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-700">{row.source_subdistrict_name ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-700">{formatNumber(row.total_population)}</td>
                      <td className="px-4 py-3 text-slate-700">{formatNumber(row.total_households)}</td>
                      <td className="px-4 py-3"><StatusBadge value={row.review_status} /></td>
                      <td className="px-4 py-3"><StatusBadge value={row.promotion_status} /></td>
                      <td className="px-4 py-3 text-slate-700">{row.is_active ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  )
}
