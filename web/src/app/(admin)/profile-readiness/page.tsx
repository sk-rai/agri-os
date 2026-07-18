"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { farmersApi, type FarmerProfileReadinessResponse, type FarmerProfileReadinessRowDto } from "@/lib/api";

const STATUSES = ["ACTIVE", "PENDING", "INACTIVE", "ARCHIVED", ""];

export default function ProfileReadinessPage() {
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [payload, setPayload] = useState<FarmerProfileReadinessResponse | null>(null);
  const [selected, setSelected] = useState<FarmerProfileReadinessRowDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await farmersApi.profileReadiness({ projectId: projectId.trim() || undefined, status, limit: 100 });
      setPayload(next);
      setSelected(next.farmers[0] || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile readiness");
    } finally {
      setLoading(false);
    }
  }, [projectId, status]);

  useEffect(() => { void load(); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Profile Readiness</h1>
      <p className="mt-1 text-sm text-gray-500">Backend-owned farmer, land, and soil completion status for admin and future field-agent summary screens.</p>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-3">
        <Input label="Project ID" value={projectId} onChange={setProjectId} />
        <label className="text-xs text-gray-500">Status<select value={status} onChange={(event) => setStatus(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{STATUSES.map((item) => <option key={item || "ALL"} value={item}>{item || "ALL"}</option>)}</select></label>
      </div>
      <div className="mt-4 flex gap-2">
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Refresh</button>
        <button type="button" onClick={() => { setProjectId(""); setStatus("ACTIVE"); }} className="rounded border px-4 py-2 text-sm">Reset</button>
      </div>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading readiness...</p> : null}

    {payload && !loading ? <>
      <div className="mb-6 grid gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Mini label="Farmers" value={payload.summary.farmer_count} />
        <Mini label="Home ready" value={payload.summary.home_ready_count} tone="green" />
        <Mini label="Advisory ready" value={payload.summary.personalized_advisory_ready_count} tone="blue" />
        <Mini label="Blocking gaps" value={payload.summary.missing_required_count} tone={payload.summary.missing_required_count ? "red" : "slate"} />
        <Mini label="Missing parcel" value={payload.summary.missing_parcel_count} tone={payload.summary.missing_parcel_count ? "amber" : "slate"} />
        <Mini label="Need soil" value={payload.summary.soil_profile_recommended_count} tone="amber" />
        <Mini label="Need location" value={payload.summary.parcel_location_recommended_count} tone="amber" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
        <section className="overflow-hidden rounded bg-white shadow">
          <div className="border-b p-5">
            <h2 className="text-lg font-bold text-gray-900">Farmers</h2>
            <p className="text-sm text-gray-500">{payload.farmers.length} row(s) returned.</p>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="p-3">Farmer</th><th className="p-3">Home</th><th className="p-3">Parcels</th><th className="p-3">Soil</th><th className="p-3">Next action</th></tr></thead>
            <tbody className="divide-y">
              {payload.farmers.map((row) => <tr key={row.farmer.id} className={`cursor-pointer hover:bg-green-50 ${selected?.farmer.id === row.farmer.id ? "bg-green-50" : ""}`} onClick={() => setSelected(row)}>
                <td className="p-3"><div className="font-medium text-gray-900">{row.farmer.display_name || row.farmer.mobile_number || row.farmer.id}</div><div className="text-xs text-gray-500">{row.farmer.mobile_number || row.farmer.id}</div></td>
                <td className="p-3"><Badge tone={row.profile_completion.is_complete_for_home ? "green" : "red"}>{row.profile_completion.is_complete_for_home ? "Ready" : "Blocked"}</Badge></td>
                <td className="p-3">{row.parcel_count}</td>
                <td className="p-3">{row.soil_profile_count}</td>
                <td className="p-3 text-xs text-gray-600">{row.profile_completion.next_actions[0]?.label || "No action"}</td>
              </tr>)}
              {payload.farmers.length === 0 ? <tr><td colSpan={5} className="p-6 text-center text-gray-400">No farmers found.</td></tr> : null}
            </tbody>
          </table>
        </section>

        <aside className="rounded bg-white p-5 shadow">
          <h2 className="text-lg font-bold text-gray-900">Readiness detail</h2>
          {selected ? <div className="mt-4 space-y-4">
            <div>
              <div className="font-semibold text-gray-900">{selected.farmer.display_name || selected.farmer.mobile_number || selected.farmer.id}</div>
              <Link href={`/farmer-trace/${selected.farmer.id}`} className="text-xs text-blue-700">Open farmer trace</Link>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <Mini label="Parcels" value={selected.parcel_count} />
              <Mini label="Soil profiles" value={selected.soil_profile_count} />
            </div>
            <Section title="Sections">
              {Object.entries(selected.profile_completion.sections).map(([key, section]) => <div key={key} className="rounded border p-2 text-xs">
                <div className="flex justify-between"><span className="font-semibold capitalize">{key.replaceAll("_", " ")}</span><Badge tone={section.status === "COMPLETE" ? "green" : section.status === "PARTIAL" ? "amber" : "red"}>{section.status}</Badge></div>
                {section.missing_required_fields.length ? <div className="mt-1 text-red-700">Required: {section.missing_required_fields.join(", ")}</div> : null}
                {section.missing_recommended_fields.length ? <div className="mt-1 text-amber-700">Recommended: {section.missing_recommended_fields.join(", ")}</div> : null}
              </div>)}
            </Section>
            <Section title="Next actions">
              {selected.profile_completion.next_actions.map((action) => <div key={action.code} className="rounded border p-2 text-xs"><div className="font-semibold">{action.label}</div><div className="text-gray-500">{action.code} - {action.priority}</div></div>)}
              {selected.profile_completion.next_actions.length === 0 ? <p className="text-xs text-gray-400">No pending action.</p> : null}
            </Section>
          </div> : <p className="mt-4 text-sm text-gray-400">Select a farmer to inspect readiness.</p>}
        </aside>
      </div>
    </> : null}
  </div>;
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Mini({ label, value, tone = "slate" }: { label: string; value: number; tone?: "slate" | "green" | "blue" | "amber" | "red" }) {
  const tones = { slate: "bg-white text-gray-900", green: "bg-green-50 text-green-900", blue: "bg-blue-50 text-blue-900", amber: "bg-amber-50 text-amber-900", red: "bg-red-50 text-red-900" };
  return <div className={`rounded border p-3 ${tones[tone]}`}><div className="text-xs opacity-70">{label}</div><div className="mt-1 text-xl font-bold">{value}</div></div>;
}

function Badge({ children, tone }: { children: React.ReactNode; tone: "green" | "amber" | "red" }) {
  const tones = { green: "bg-green-100 text-green-800", amber: "bg-amber-100 text-amber-800", red: "bg-red-100 text-red-800" };
  return <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><h3 className="mb-2 text-sm font-semibold text-gray-800">{title}</h3><div className="space-y-2">{children}</div></div>;
}
