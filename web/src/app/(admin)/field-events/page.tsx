"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { fieldEventsApi, type FieldEventReportDto, type FieldEventReportListResponse } from "@/lib/api";

const EVENT_TYPES = ["", "RAIN", "PEST", "DISEASE", "HAILSTORM", "LOCUST", "FLOOD", "DROUGHT_STRESS", "THUNDERSTORM_WIND", "HEAT_STRESS", "COLD_STRESS", "IRRIGATION_FAILURE", "OTHER"];
const SEVERITIES = ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
const STATUSES = ["", "REPORTED", "UNDER_REVIEW", "ADVISORY_SENT", "RESOLVED", "DISMISSED"];

export default function FieldEventsPage() {
  const [projectId, setProjectId] = useState("");
  const [farmerId, setFarmerId] = useState("");
  const [parcelId, setParcelId] = useState("");
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [payload, setPayload] = useState<FieldEventReportListResponse | null>(null);
  const [selected, setSelected] = useState<FieldEventReportDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setProjectId(query.get("projectId") || "");
    setFarmerId(query.get("farmerId") || "");
    setParcelId(query.get("parcelId") || "");
    setEventType(query.get("eventType") || "");
    setSeverity(query.get("severity") || "");
    setStatus(query.get("status") || "");
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fieldEventsApi.list({
        projectId: projectId.trim() || undefined,
        farmerId: farmerId.trim() || undefined,
        parcelId: parcelId.trim() || undefined,
        eventType: eventType || undefined,
        severity: severity || undefined,
        status: status || undefined,
        limit: 100,
      });
      setPayload(next);
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load field events");
    } finally {
      setLoading(false);
    }
  }, [eventType, farmerId, parcelId, projectId, severity, status]);

  useEffect(() => { void load(); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  async function openDetail(eventId: string) {
    setError(null);
    try {
      setSelected(await fieldEventsApi.detail(eventId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load event detail");
    }
  }

  async function clearFilters() {
    setProjectId("");
    setFarmerId("");
    setParcelId("");
    setEventType("");
    setSeverity("");
    setStatus("");
    setLoading(true);
    setError(null);
    try {
      setPayload(await fieldEventsApi.list({ limit: 100 }));
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load field events");
    } finally {
      setLoading(false);
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Field Events</h1>
      <p className="mt-1 text-sm text-gray-500">Read-only view of farmer/field-agent ground reports such as pest, rain, hailstorm, flood, and crop stress events.</p>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-3">
        <Input label="Project ID" value={projectId} onChange={setProjectId} />
        <Input label="Farmer ID" value={farmerId} onChange={setFarmerId} />
        <Input label="Parcel ID" value={parcelId} onChange={setParcelId} />
        <Select label="Event type" value={eventType} onChange={setEventType} options={EVENT_TYPES} />
        <Select label="Severity" value={severity} onChange={setSeverity} options={SEVERITIES} />
        <Select label="Status" value={status} onChange={setStatus} options={STATUSES} />
      </div>
      <div className="mt-4 flex gap-2">
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply filters</button>
        <button type="button" onClick={() => void clearFilters()} className="rounded border px-4 py-2 text-sm">Clear</button>
      </div>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading field events...</p> : null}

    {payload && !loading ? <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
      <section className="overflow-hidden rounded bg-white shadow">
        <div className="border-b p-5">
          <h2 className="text-lg font-bold text-gray-900">Reports</h2>
          <p className="text-sm text-gray-500">{payload.count} event(s) returned.</p>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Reported", "Type", "Severity", "Status", "Farmer/parcel", "Media", "Actions"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {payload.events.map((event) => <tr key={event.id}>
              <td className="p-3 whitespace-nowrap"><div>{event.event_date || "-"}</div><div className="text-xs text-gray-500">{event.source}</div></td>
              <td className="p-3"><span className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{event.event_type}</span><div className="mt-1 text-xs text-gray-500">{event.stage_code || "-"}</div></td>
              <td className="p-3"><SeverityBadge severity={event.severity} /></td>
              <td className="p-3">{event.status}</td>
              <td className="p-3"><Link href={`/farmer-trace/${event.farmer_id}`} className="font-mono text-xs text-blue-600">{event.farmer_id}</Link>{event.parcel_id ? <div><Link href={`/parcel-trace/${event.parcel_id}`} className="font-mono text-xs text-blue-600">{event.parcel_id}</Link></div> : null}</td>
              <td className="p-3">{event.media_attachment_count}</td>
              <td className="p-3"><button onClick={() => void openDetail(event.id)} className="text-blue-600">View</button></td>
            </tr>)}
            {payload.events.length === 0 ? <tr><td colSpan={7} className="p-8 text-center text-gray-400">No field events match the filters.</td></tr> : null}
          </tbody>
        </table>
      </section>

      <EventDetail event={selected} />
    </div> : null}
  </div>;
}

function EventDetail({ event }: { event: FieldEventReportDto | null }) {
  if (!event) return <aside className="rounded bg-white p-5 text-sm text-gray-500 shadow">Select an event to inspect details, media, GPS, and metadata.</aside>;
  return <aside className="rounded bg-white p-5 shadow">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Event detail</h2>
        <p className="font-mono text-xs text-gray-500">{event.id}</p>
      </div>
      <SeverityBadge severity={event.severity} />
    </div>
    <div className="mt-4 grid gap-2 text-sm">
      <Mini label="Type/status" value={`${event.event_type} / ${event.status}`} />
      <Mini label="Date/source" value={`${event.event_date || "-"} / ${event.source}`} />
      <Mini label="GPS" value={event.lat && event.lng ? `${event.lat}, ${event.lng} (${event.accuracy_meters || "?"}m)` : "-"} />
      <Mini label="Area/loss" value={[event.estimated_area_affected, event.estimated_loss_percent ? `${event.estimated_loss_percent}%` : null].filter(Boolean).join(" / ") || "-"} />
      <Mini label="Crop cycle" value={event.crop_cycle_id || "-"} />
    </div>
    {event.description ? <p className="mt-4 rounded bg-gray-50 p-3 text-sm text-gray-700">{event.description}</p> : null}
    <div className="mt-4">
      <h3 className="text-sm font-semibold text-gray-900">Media attachments</h3>
      <div className="mt-2 space-y-2">
        {(event.media_attachments || []).map((item) => <div key={item.id} className="rounded border p-2 text-xs">{item.purpose} - {item.asset.media_type} - {item.asset.upload_status}<div className="font-mono text-gray-500">{item.media_asset_id}</div></div>)}
        {(!event.media_attachments || event.media_attachments.length === 0) ? <p className="text-sm text-gray-400">No media attachments.</p> : null}
      </div>
    </div>
    <details className="mt-4 text-xs">
      <summary className="cursor-pointer text-gray-500">Metadata JSON</summary>
      <pre className="mt-2 max-h-72 overflow-auto rounded bg-gray-950 p-3 text-[11px] text-gray-100">{JSON.stringify(event.metadata || {}, null, 2)}</pre>
    </details>
  </aside>;
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{options.map((option) => <option key={option || "ALL"} value={option}>{option || "All"}</option>)}</select></label>;
}

function Mini({ label, value }: { label: string; value?: string | number | null }) {
  return <div><div className="text-xs uppercase text-gray-400">{label}</div><div className="break-all font-mono text-gray-800">{value || "-"}</div></div>;
}

function SeverityBadge({ severity }: { severity: string }) {
  const tone = severity === "CRITICAL" ? "bg-red-100 text-red-800" : severity === "HIGH" ? "bg-orange-100 text-orange-800" : severity === "MEDIUM" ? "bg-amber-100 text-amber-800" : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-1 text-xs ${tone}`}>{severity}</span>;
}
