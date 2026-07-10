"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { reportsApi, type AdminLookupResponse } from "@/lib/api";

export default function AdminLookupPage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [result, setResult] = useState<AdminLookupResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (search: string) => {
    setLoading(true);
    setError(null);
    try {
      setResult(await reportsApi.lookup(search, 25));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load lookup results");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(""); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = query.trim();
    setSubmittedQuery(next);
    load(next);
  }

  const total = (result?.projects.length || 0) + (result?.farmers.length || 0) + (result?.parcels.length || 0);

  return <div>
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Admin Lookup</h1>
        <p className="mt-1 text-sm text-gray-500">Find projects, farmers, and parcels, then jump directly into traceability views.</p>
      </div>
      <button onClick={() => load(submittedQuery)} disabled={loading} className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">{loading ? "Loading..." : "Refresh"}</button>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <label className="text-xs uppercase text-gray-400">Search by name, mobile, survey number, village, crop, status, or UUID</label>
      <div className="mt-2 flex flex-col gap-3 md:flex-row">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. 9900000001, 1234/98, Rice, farmer UUID" className="flex-1 rounded border p-3 text-sm text-gray-900" />
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-5 py-3 text-sm font-medium text-white disabled:opacity-50">Search</button>
        <button type="button" onClick={() => { setQuery(""); setSubmittedQuery(""); load(""); }} className="rounded border px-5 py-3 text-sm">Clear</button>
      </div>
      <p className="mt-2 text-xs text-gray-400">Blank search shows recent records. Search is tenant-scoped and read-only.</p>
    </form>

    {error && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

    <div className="mb-6 grid gap-4 md:grid-cols-4">
      <Card label="Total matches" value={loading ? "..." : total} />
      <Card label="Projects" value={result?.projects.length || 0} />
      <Card label="Farmers" value={result?.farmers.length || 0} />
      <Card label="Parcels" value={result?.parcels.length || 0} />
    </div>

    <div className="space-y-6">
      <section className="overflow-hidden rounded bg-white shadow">
        <SectionHeader title="Projects" subtitle="Open compliance/usage summary for a project." />
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Project", "Status", "Crop scope", "Dates", "Cycles", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {(result?.projects || []).map((project) => <tr key={project.id}>
              <td className="p-3"><div className="font-medium text-gray-900">{project.name}</div><div className="font-mono text-xs text-gray-500">{project.id}</div></td>
              <td className="p-3">{project.status || "-"}</td>
              <td className="p-3">{project.crop_scope?.join(", ") || "-"}</td>
              <td className="p-3"><div>{project.start_date || "-"}</div><div className="text-xs text-gray-500">{project.end_date || "-"}</div></td>
              <td className="p-3">{project.crop_cycle_count}</td>
              <td className="p-3"><div className="flex flex-col gap-1"><Link href={project.trace_url} className="text-blue-600">Project trace</Link>{project.compliance_url && <Link href={project.compliance_url} className="text-xs text-blue-600">Compliance</Link>}</div></td>
            </tr>)}
            {!loading && result?.projects.length === 0 && <Empty colSpan={6} label="No projects found." />}
          </tbody>
        </table>
      </section>

      <section className="overflow-hidden rounded bg-white shadow">
        <SectionHeader title="Farmers" subtitle="Open farmer trace for profile, parcels, cycles, and activity usage." />
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Farmer", "Mobile", "Village/crop", "Status", "Usage", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {(result?.farmers || []).map((farmer) => <tr key={farmer.id}>
              <td className="p-3"><div className="font-medium text-gray-900">{farmer.display_name || farmer.label}</div><div className="font-mono text-xs text-gray-500">{farmer.id}</div></td>
              <td className="p-3">{farmer.mobile_number || "-"}</td>
              <td className="p-3"><div>{farmer.village_name || "-"}</div><div className="text-xs text-gray-500">{farmer.primary_crop_code || "-"}</div></td>
              <td className="p-3">{farmer.status || "-"}</td>
              <td className="p-3">{farmer.crop_cycle_count} cycles / {farmer.activity_count} activities</td>
              <td className="p-3"><Link href={farmer.trace_url} className="text-blue-600">Farmer trace</Link></td>
            </tr>)}
            {!loading && result?.farmers.length === 0 && <Empty colSpan={6} label="No farmers found." />}
          </tbody>
        </table>
      </section>

      <section className="overflow-hidden rounded bg-white shadow">
        <SectionHeader title="Parcels" subtitle="Open parcel trace for geometry, ownership, cycles, and activity usage." />
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Parcel", "Farmer", "Area/ownership", "Geometry", "Usage", "Open"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {(result?.parcels || []).map((parcel) => <tr key={parcel.id}>
              <td className="p-3"><div className="font-medium text-gray-900">{parcel.local_name || parcel.survey_number || parcel.label}</div><div className="font-mono text-xs text-gray-500">{parcel.id}</div></td>
              <td className="p-3"><div>{parcel.farmer_name || "-"}</div><Link href={`/farmer-trace/${parcel.farmer_id}`} className="font-mono text-xs text-blue-600">{parcel.farmer_id}</Link></td>
              <td className="p-3"><div>{[parcel.reported_area, parcel.reported_area_unit].filter(Boolean).join(" ") || "-"}</div><div className="text-xs text-gray-500">{parcel.ownership_type || "-"}</div></td>
              <td className="p-3">{parcel.geometry_source || "-"}</td>
              <td className="p-3">{parcel.crop_cycle_count} cycles / {parcel.activity_count} activities</td>
              <td className="p-3"><Link href={parcel.trace_url} className="text-blue-600">Parcel trace</Link></td>
            </tr>)}
            {!loading && result?.parcels.length === 0 && <Empty colSpan={6} label="No parcels found." />}
          </tbody>
        </table>
      </section>
    </div>
  </div>;
}

function Card({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white p-5 shadow"><p className="text-xs uppercase text-gray-400">{label}</p><p className="mt-2 text-2xl font-bold text-gray-900">{value}</p></div>;
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="border-b p-5"><h2 className="text-lg font-bold text-gray-900">{title}</h2><p className="text-sm text-gray-500">{subtitle}</p></div>;
}

function Empty({ colSpan, label }: { colSpan: number; label: string }) {
  return <tr><td colSpan={colSpan} className="p-8 text-center text-gray-400">{label}</td></tr>;
}
