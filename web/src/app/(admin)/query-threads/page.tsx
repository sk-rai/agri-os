"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { queryThreadsApi, type QueryThreadDto, type QueryThreadListResponse } from "@/lib/api";

const STATUSES = ["", "OPEN", "ASSIGNED", "ANSWERED", "CLOSED"];
const CATEGORIES = ["", "CROP_HEALTH", "INPUT_USAGE", "IRRIGATION", "MARKET", "INSURANCE", "TECH_SUPPORT", "OTHER"];
const PRIORITIES = ["", "LOW", "MEDIUM", "HIGH", "URGENT"];

export default function QueryThreadsPage() {
  const [projectId, setProjectId] = useState("");
  const [farmerId, setFarmerId] = useState("");
  const [parcelId, setParcelId] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [replyText, setReplyText] = useState("");
  const [assignTo, setAssignTo] = useState("");
  const [actionReason, setActionReason] = useState("");
  const [payload, setPayload] = useState<QueryThreadListResponse | null>(null);
  const [selected, setSelected] = useState<QueryThreadDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setProjectId(query.get("projectId") || "");
    setFarmerId(query.get("farmerId") || "");
    setParcelId(query.get("parcelId") || "");
    setStatus(query.get("status") || "");
    setCategory(query.get("category") || "");
    setPriority(query.get("priority") || "");
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await queryThreadsApi.list({
        projectId: projectId.trim() || undefined,
        farmerId: farmerId.trim() || undefined,
        parcelId: parcelId.trim() || undefined,
        status: status || undefined,
        category: category || undefined,
        priority: priority || undefined,
        limit: 100,
      });
      setPayload(next);
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load query threads");
    } finally {
      setLoading(false);
    }
  }, [category, farmerId, parcelId, priority, projectId, status]);

  useEffect(() => { void load(); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  async function openDetail(threadId: string) {
    setError(null);
    try {
      setSelected(await queryThreadsApi.detail(threadId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load query detail");
    }
  }

  async function clearFilters() {
    setProjectId("");
    setFarmerId("");
    setParcelId("");
    setStatus("");
    setCategory("");
    setPriority("");
    setLoading(true);
    setError(null);
    try {
      setPayload(await queryThreadsApi.list({ limit: 100 }));
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load query threads");
    } finally {
      setLoading(false);
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Query Inbox</h1>
      <p className="mt-1 text-sm text-gray-500">Read-only inbox for farmer questions and agronomist/company replies, including text, audio, photo, and document message evidence.</p>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-3">
        <Input label="Project ID" value={projectId} onChange={setProjectId} />
        <Input label="Farmer ID" value={farmerId} onChange={setFarmerId} />
        <Input label="Parcel ID" value={parcelId} onChange={setParcelId} />
        <Select label="Status" value={status} onChange={setStatus} options={STATUSES} />
        <Select label="Category" value={category} onChange={setCategory} options={CATEGORIES} />
        <Select label="Priority" value={priority} onChange={setPriority} options={PRIORITIES} />
      </div>
      <div className="mt-4 flex gap-2">
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply filters</button>
        <button type="button" onClick={() => void clearFilters()} className="rounded border px-4 py-2 text-sm">Clear</button>
      </div>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading query inbox...</p> : null}

    {payload && !loading ? <div className="grid gap-6 xl:grid-cols-[1fr_460px]">
      <section className="overflow-hidden rounded bg-white shadow">
        <div className="border-b p-5">
          <h2 className="text-lg font-bold text-gray-900">Threads</h2>
          <p className="text-sm text-gray-500">{payload.count} thread(s) returned.</p>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Last message", "Subject", "Category", "Priority", "Status", "Farmer/parcel", "Messages", "Actions"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {payload.threads.map((thread) => <tr key={thread.id}>
              <td className="p-3 whitespace-nowrap"><div>{thread.last_message_at || thread.created_at || "-"}</div><div className="font-mono text-xs text-gray-500">{thread.id}</div></td>
              <td className="p-3"><div className="font-medium text-gray-900">{thread.subject}</div><div className="text-xs text-gray-500">{thread.stage_code || "No stage"}</div></td>
              <td className="p-3"><span className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{thread.category}</span></td>
              <td className="p-3"><PriorityBadge priority={thread.priority} /></td>
              <td className="p-3">{thread.status}</td>
              <td className="p-3"><Link href={`/farmer-trace/${thread.farmer_id}`} className="font-mono text-xs text-blue-600">{thread.farmer_id}</Link>{thread.parcel_id ? <div><Link href={`/parcel-trace/${thread.parcel_id}`} className="font-mono text-xs text-blue-600">{thread.parcel_id}</Link></div> : null}</td>
              <td className="p-3">{thread.message_count}</td>
              <td className="p-3"><button onClick={() => void openDetail(thread.id)} className="text-blue-600">View</button></td>
            </tr>)}
            {payload.threads.length === 0 ? <tr><td colSpan={8} className="p-8 text-center text-gray-400">No query threads match the filters.</td></tr> : null}
          </tbody>
        </table>
      </section>

      <QueryDetail thread={selected} replyText={replyText} setReplyText={setReplyText} assignTo={assignTo} setAssignTo={setAssignTo} actionReason={actionReason} setActionReason={setActionReason} onRefresh={openDetail} />
    </div> : null}
  </div>;
}

function QueryDetail({
  thread,
  replyText,
  setReplyText,
  assignTo,
  setAssignTo,
  actionReason,
  setActionReason,
  onRefresh,
}: {
  thread: QueryThreadDto | null;
  replyText: string;
  setReplyText: (value: string) => void;
  assignTo: string;
  setAssignTo: (value: string) => void;
  actionReason: string;
  setActionReason: (value: string) => void;
  onRefresh: (threadId: string) => Promise<void>;
}) {
  async function submitReply(event: FormEvent) {
    event.preventDefault();
    if (!thread || !replyText.trim()) return;
    await queryThreadsApi.addMessage(thread.id, {
      sender_type: "ADMIN",
      message_type: "TEXT",
      body_text: replyText.trim(),
      metadata: { source: "admin_query_inbox" },
    });
    setReplyText("");
    await onRefresh(thread.id);
  }

  async function updateStatus(nextStatus: string) {
    if (!thread) return;
    await queryThreadsApi.updateStatus(thread.id, {
      status: nextStatus,
      assigned_to: assignTo.trim() || undefined,
      reason: actionReason.trim() || undefined,
    });
    await onRefresh(thread.id);
  }

  if (!thread) return <aside className="rounded bg-white p-5 text-sm text-gray-500 shadow">Select a query thread to inspect messages, media, farmer/parcel IDs, and metadata.</aside>;
  return <aside className="rounded bg-white p-5 shadow">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Query detail</h2>
        <p className="font-mono text-xs text-gray-500">{thread.id}</p>
      </div>
      <PriorityBadge priority={thread.priority} />
    </div>
    <div className="mt-4 grid gap-2 text-sm">
      <Mini label="Subject" value={thread.subject} />
      <Mini label="Category/status" value={`${thread.category} / ${thread.status}`} />
      <Mini label="Farmer" value={thread.farmer_id} />
      <Mini label="Parcel" value={thread.parcel_id || "-"} />
      <Mini label="Stage" value={thread.stage_code || "-"} />
      <Mini label="Assigned to" value={thread.assigned_to || "-"} />
    </div>
    <div className="mt-5 rounded border bg-gray-50 p-3">
      <h3 className="text-sm font-semibold text-gray-900">Admin actions</h3>
      <form onSubmit={submitReply} className="mt-3 space-y-2">
        <textarea value={replyText} onChange={(event) => setReplyText(event.target.value)} rows={3} placeholder="Write a text reply for the farmer..." className="w-full rounded border p-2 text-sm" />
        <button type="submit" disabled={!replyText.trim()} className="rounded bg-green-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">Send reply</button>
      </form>
      <div className="mt-4 grid gap-2">
        <Input label="Assign to user ID" value={assignTo} onChange={setAssignTo} />
        <Input label="Action reason" value={actionReason} onChange={setActionReason} />
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void updateStatus("ASSIGNED")} className="rounded border px-3 py-2 text-sm">Assign</button>
          <button type="button" onClick={() => void updateStatus("ANSWERED")} className="rounded border px-3 py-2 text-sm">Mark answered</button>
          <button type="button" onClick={() => void updateStatus("CLOSED")} className="rounded border px-3 py-2 text-sm">Close</button>
        </div>
      </div>
    </div>

    <div className="mt-5">
      <h3 className="text-sm font-semibold text-gray-900">Messages</h3>
      <div className="mt-3 space-y-3">
        {(thread.messages || []).map((message) => <div key={message.id} className="rounded border p-3 text-sm">
          <div className="flex items-start justify-between gap-2">
            <div><span className="font-semibold">{message.sender_type}</span> <span className="text-xs text-gray-500">{message.message_type}</span></div>
            <span className="text-xs text-gray-400">{message.created_at || "-"}</span>
          </div>
          {message.body_text ? <p className="mt-2 rounded bg-gray-50 p-2 text-gray-700">{message.body_text}</p> : null}
          <div className="mt-2 space-y-2">
            {(message.media_attachments || []).map((item) => <div key={item.id} className="rounded bg-slate-50 p-2 text-xs">{item.purpose} - {item.asset.media_type} - {item.asset.upload_status}<div className="font-mono text-gray-500">{item.media_asset_id}</div></div>)}
          </div>
        </div>)}
        {(!thread.messages || thread.messages.length === 0) ? <p className="text-sm text-gray-400">No messages.</p> : null}
      </div>
    </div>
    <div className="mt-5">
      <h3 className="text-sm font-semibold text-gray-900">Audit history</h3>
      <div className="mt-3 space-y-3">
        {(thread.audit_events || []).map((event) => <div key={event.id} className="rounded border bg-white p-3 text-xs">
          <div className="flex items-start justify-between gap-2">
            <div>
              <span className="font-semibold text-gray-900">{event.action}</span>
              <span className="ml-2 text-gray-500">{event.actor_type || "SYSTEM"}</span>
            </div>
            <span className="text-gray-400">{event.created_at || "-"}</span>
          </div>
          <div className="mt-1 font-mono text-gray-500">{event.actor_id || "No actor id"}</div>
          {event.reason ? <div className="mt-2 rounded bg-amber-50 p-2 text-amber-800">Reason: {event.reason}</div> : null}
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <JsonMini label="Before" value={event.before || {}} />
            <JsonMini label="After" value={event.after || {}} />
          </div>
        </div>)}
        {(!thread.audit_events || thread.audit_events.length === 0) ? <p className="text-sm text-gray-400">No audit events recorded.</p> : null}
      </div>
    </div>

    <details className="mt-4 text-xs">
      <summary className="cursor-pointer text-gray-500">Metadata JSON</summary>
      <pre className="mt-2 max-h-72 overflow-auto rounded bg-gray-950 p-3 text-[11px] text-gray-100">{JSON.stringify(thread.metadata || {}, null, 2)}</pre>
    </details>
  </aside>;
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{options.map((option) => <option key={option || "ALL"} value={option}>{option || "All"}</option>)}</select></label>;
}

function JsonMini({ label, value }: { label: string; value: Record<string, unknown> }) {
  return <div><div className="text-[10px] uppercase text-gray-400">{label}</div><pre className="mt-1 max-h-36 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(value, null, 2)}</pre></div>;
}

function Mini({ label, value }: { label: string; value?: string | number | null }) {
  return <div><div className="text-xs uppercase text-gray-400">{label}</div><div className="break-all font-mono text-gray-800">{value || "-"}</div></div>;
}

function PriorityBadge({ priority }: { priority: string }) {
  const tone = priority === "URGENT" ? "bg-red-100 text-red-800" : priority === "HIGH" ? "bg-orange-100 text-orange-800" : priority === "MEDIUM" ? "bg-amber-100 text-amber-800" : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-1 text-xs ${tone}`}>{priority}</span>;
}