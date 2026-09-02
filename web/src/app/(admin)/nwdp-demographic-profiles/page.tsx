"use client"

import { FormEvent, useCallback, useEffect, useState } from "react"
import {
  nwdpDemographicProfilesApi,
  type NwdpDemographicProfileFilterOptionsResponse,
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
  const [stateOrUt, setStateOrUt] = useState("")
  const [district, setDistrict] = useState("")
  const [villageName, setVillageName] = useState("")
  const [sourceVlcode, setSourceVlcode] = useState("")
  const [reviewStatus, setReviewStatus] = useState("")
  const [promotionStatus, setPromotionStatus] = useState("PROMOTED")
  const [activeFilter, setActiveFilter] = useState("true")
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState(100)
  const [data, setData] = useState<NwdpDemographicProfilesPreviewResponse | null>(null)
  const [filterOptions, setFilterOptions] = useState<NwdpDemographicProfileFilterOptionsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadPreview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await nwdpDemographicProfilesApi.preview({
        state_or_ut: stateOrUt.trim() || undefined,
        district: district.trim() || undefined,
        review_status: reviewStatus || undefined,
        promotion_status: promotionStatus || undefined,
        is_active: activeFilter ? activeFilter === "true" : undefined,
        source_vlcode: sourceVlcode.trim() || undefined,
        village_name: villageName.trim() || undefined,
        offset,
        limit,
      })
      setData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load NWDP demographic profiles")
    } finally {
      setLoading(false)
    }
  }, [activeFilter, district, limit, offset, promotionStatus, reviewStatus, sourceVlcode, stateOrUt, villageName])

  useEffect(() => {
    void loadPreview()
  }, [loadPreview])

  useEffect(() => {
    let ignore = false

    async function loadFilterOptions() {
      try {
        const response = await nwdpDemographicProfilesApi.filterOptions({
          state_or_ut: stateOrUt.trim() || undefined,
        })
        if (!ignore) {
          setFilterOptions(response)
        }
      } catch {
        if (!ignore) {
          setFilterOptions(null)
        }
      }
    }

    void loadFilterOptions()

    return () => {
      ignore = true
    }
  }, [stateOrUt])

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (offset === 0) {
      void loadPreview()
      return
    }
    setOffset(0)
  }

  function showPromotedProfiles() {
    setStateOrUt("")
    setDistrict("")
    setVillageName("")
    setSourceVlcode("")
    setReviewStatus("")
    setPromotionStatus("PROMOTED")
    setActiveFilter("true")
    setOffset(0)
  }

  function clearFilters() {
    setStateOrUt("")
    setDistrict("")
    setVillageName("")
    setSourceVlcode("")
    setReviewStatus("")
    setPromotionStatus("")
    setActiveFilter("")
    setOffset(0)
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

      <form onSubmit={onSubmit} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-4">
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">State / UT</span>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={stateOrUt}
            onChange={(event) => {
              setStateOrUt(event.target.value)
              setDistrict("")
              setOffset(0)
            }}
          >
            <option value="">All states</option>
            {(filterOptions?.states ?? []).map((option) => (
              <option key={option.state_or_ut} value={option.state_or_ut}>
                {option.state_or_ut} ({formatNumber(option.profile_row_count)})
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">District</span>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            value={district}
            onChange={(event) => {
              setDistrict(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">All districts</option>
            {(filterOptions?.districts ?? []).map((option) => (
              <option key={`${option.state_or_ut}:${option.district}`} value={option.district}>
                {option.district} ({formatNumber(option.profile_row_count)})
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Village name</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            placeholder="Search village"
            value={villageName}
            onChange={(event) => setVillageName(event.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">VLCode</span>
          <input
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            placeholder="Exact VLCode"
            value={sourceVlcode}
            onChange={(event) => setSourceVlcode(event.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Review status</span>
          <select className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
            <option value="">Any</option>
            <option value="AUTO_CANDIDATE">Auto candidate</option>
            <option value="APPROVED_FOR_PROMOTION">Approved</option>
            <option value="MANUAL_REVIEW">Manual review</option>
            <option value="REJECTED">Rejected</option>
            <option value="BLOCKED">Blocked</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Promotion status</span>
          <select className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" value={promotionStatus} onChange={(event) => setPromotionStatus(event.target.value)}>
            <option value="">Any</option>
            <option value="PROMOTED">Promoted</option>
            <option value="NOT_PROMOTED">Not promoted</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Active</span>
          <select className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" value={activeFilter} onChange={(event) => setActiveFilter(event.target.value)}>
            <option value="">Any</option>
            <option value="true">Active only</option>
            <option value="false">Inactive only</option>
          </select>
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
        <button type="button" onClick={showPromotedProfiles} className="self-end rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-800 hover:bg-emerald-100">
          Show promoted
        </button>
        <button type="button" onClick={clearFilters} className="self-end rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          Clear filters
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
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 shadow-sm">
            <span>Showing {formatNumber(offset + 1)}-{formatNumber(offset + rows.length)} of {formatNumber(summary.profile_row_count)} matching profiles</span>
            <div className="flex gap-2">
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="rounded-xl border border-slate-200 px-4 py-2 font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50">Previous</button>
              <button type="button" disabled={offset + rows.length >= summary.profile_row_count} onClick={() => setOffset(offset + limit)} className="rounded-xl border border-slate-200 px-4 py-2 font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50">Next</button>
            </div>
          </section>
        </>
      )}
    </main>
  )
}
