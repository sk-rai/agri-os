"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { broadcastsApi, type BroadcastCampaignDto, type BroadcastCampaignListResponse } from "@/lib/api";

const STATUSES = ["", "DRAFT", "PUBLISHED", "EXPIRED", "ARCHIVED"];
const PRIORITIES = ["", "LOW", "NORMAL", "HIGH", "URGENT"];
const CATEGORIES = ["", "GENERAL", "ADVISORY", "WEATHER", "MARKET", "INPUT", "EMERGENCY"];
const RULE_TYPES = ["ALL", "PROJECT", "FARMER", "CROP", "STAGE", "LOCATION", "WEATHER", "FIELD_EVENT", "INPUT", "PRODUCT", "ROLE", "LANGUAGE"];

export default function BroadcastsPage() {
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [payload, setPayload] = useState<BroadcastCampaignListResponse | null>(null);
  const [selected, setSelected] = useState<BroadcastCampaignDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftCategory, setDraftCategory] = useState("ADVISORY");
  const [draftPriority, setDraftPriority] = useState("NORMAL");
  const [contentTitle, setContentTitle] = useState("");
  const [contentBody, setContentBody] = useState("");
  const [ruleType, setRuleType] = useState("ALL");
  const [ruleValues, setRuleValues] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await broadcastsApi.list({
        projectId: projectId.trim() || undefined,
        status: status || undefined,
        category: category || undefined,
        priority: priority || undefined,
        limit: 100,
      });
      setPayload(next);
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load broadcasts");
    } finally {
      setLoading(false);
    }
  }, [category, priority, projectId, status]);

  useEffect(() => { void load(); }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  async function createDraft(event: FormEvent) {
    event.preventDefault();
    if (!draftTitle.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const values = ruleValues.split(",").map((item) => item.trim()).filter(Boolean);
      const created = await broadcastsApi.create({
        title: draftTitle.trim(),
        category: draftCategory,
        priority: draftPriority,
        metadata: { source: "admin_broadcasts_page" },
        contents: [{
          language_code: "en",
          title: (contentTitle.trim() || draftTitle.trim()),
          body_text: contentBody.trim() || undefined,
        }],
        audience_rules: [{
          rule_type: ruleType,
          operator: ruleType === "ALL" ? "ANY" : "IN",
          values,
        }],
      });
      setDraftTitle("");
      setContentTitle("");
      setContentBody("");
      setRuleType("ALL");
      setRuleValues("");
      await load();
      setSelected(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create draft broadcast");
    } finally {
      setCreating(false);
    }
  }

  async function openDetail(campaignId: string) {
    setError(null);
    try {
      setSelected(await broadcastsApi.detail(campaignId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load broadcast detail");
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Broadcasts</h1>
      <p className="mt-1 text-sm text-gray-500">Read-only advisory and broadcast campaign visibility for generic and targeted multimedia communication.</p>
    </div>

    <form onSubmit={createDraft} className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="text-lg font-bold text-gray-900">Create draft broadcast</h2>
      <p className="mt-1 text-sm text-gray-500">Creates a DRAFT campaign only. Publishing and delivery generation will be added separately.</p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <Input label="Campaign title" value={draftTitle} onChange={setDraftTitle} />
        <Select label="Category" value={draftCategory} onChange={setDraftCategory} options={CATEGORIES.filter(Boolean)} />
        <Select label="Priority" value={draftPriority} onChange={setDraftPriority} options={PRIORITIES.filter(Boolean)} />
        <Input label="Content title" value={contentTitle} onChange={setContentTitle} />
        <Input label="Content body" value={contentBody} onChange={setContentBody} />
        <Select label="Audience rule" value={ruleType} onChange={setRuleType} options={RULE_TYPES} />
        <Input label="Rule values comma-separated" value={ruleValues} onChange={setRuleValues} />
      </div>
      <div className="mt-4">
        <button type="submit" disabled={creating || !draftTitle.trim()} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{creating ? "Creating..." : "Create draft"}</button>
      </div>
    </form>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <h2 className="text-lg font-bold text-gray-900">Filter broadcasts</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <Input label="Project ID" value={projectId} onChange={setProjectId} />
        <Select label="Status" value={status} onChange={setStatus} options={STATUSES} />
        <Select label="Category" value={category} onChange={setCategory} options={CATEGORIES} />
        <Select label="Priority" value={priority} onChange={setPriority} options={PRIORITIES} />
      </div>
      <div className="mt-4">
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Apply filters</button>
      </div>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading broadcasts...</p> : null}

    {payload && !loading ? <div className="grid gap-6 xl:grid-cols-[1fr_460px]">
      <section className="overflow-hidden rounded bg-white shadow">
        <div className="border-b p-5">
          <h2 className="text-lg font-bold text-gray-900">Campaigns</h2>
          <p className="text-sm text-gray-500">{payload.count} campaign(s) returned.</p>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>{["Campaign", "Category", "Priority", "Status", "Rules", "Content", "Delivery", "Actions"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
          <tbody className="divide-y">
            {payload.campaigns.map((campaign) => <tr key={campaign.id}>
              <td className="p-3"><div className="font-medium text-gray-900">{campaign.title}</div><div className="font-mono text-xs text-gray-500">{campaign.id}</div></td>
              <td className="p-3">{campaign.category}</td>
              <td className="p-3"><Badge value={campaign.priority} /></td>
              <td className="p-3">{campaign.status}</td>
              <td className="p-3">{campaign.audience_rule_count}</td>
              <td className="p-3">{campaign.content_count}</td>
              <td className="p-3">{campaign.delivery_count}</td>
              <td className="p-3"><button onClick={() => void openDetail(campaign.id)} className="text-blue-600">View</button></td>
            </tr>)}
            {payload.campaigns.length === 0 ? <tr><td colSpan={8} className="p-8 text-center text-gray-400">No broadcasts match the filters.</td></tr> : null}
          </tbody>
        </table>
      </section>

      <BroadcastDetail campaign={selected} />
    </div> : null}
  </div>;
}

function BroadcastDetail({ campaign }: { campaign: BroadcastCampaignDto | null }) {
  if (!campaign) return <aside className="rounded bg-white p-5 text-sm text-gray-500 shadow">Select a campaign to inspect content, audience rules, delivery summary, and metadata.</aside>;
  return <aside className="rounded bg-white p-5 shadow">
    <h2 className="text-lg font-bold text-gray-900">Broadcast detail</h2>
    <p className="font-mono text-xs text-gray-500">{campaign.id}</p>
    <div className="mt-4 grid gap-2 text-sm">
      <Mini label="Title" value={campaign.title} />
      <Mini label="Category / priority" value={`${campaign.category} / ${campaign.priority}`} />
      <Mini label="Status" value={campaign.status} />
      <Mini label="Project" value={campaign.project_id || "-"} />
      <Mini label="Active window" value={`${campaign.starts_at || "-"} to ${campaign.expires_at || "-"}`} />
    </div>

    <Section title="Content">
      {(campaign.contents || []).map((content) => <div key={content.id} className="rounded border p-3 text-sm">
        <div className="font-semibold">{content.language_code}: {content.title}</div>
        <p className="mt-1 text-gray-600">{content.body_text || "-"}</p>
        {content.cta_label || content.deeplink_url ? <div className="mt-2 text-xs text-blue-700">{content.cta_label || "CTA"} - {content.deeplink_url || "-"}</div> : null}
      </div>)}
      {(!campaign.contents || campaign.contents.length === 0) ? <p className="text-sm text-gray-400">No content rows.</p> : null}
    </Section>

    <Section title="Audience rules">
      {(campaign.audience_rules || []).map((rule) => <div key={rule.id} className="rounded border p-3 text-xs">
        <div className="font-semibold">{rule.rule_type} {rule.operator}</div>
        <pre className="mt-1 rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(rule.values || [], null, 2)}</pre>
      </div>)}
      {(!campaign.audience_rules || campaign.audience_rules.length === 0) ? <p className="text-sm text-gray-400">No audience rules.</p> : null}
    </Section>

    <Section title="Delivery summary">
      <div className="grid grid-cols-2 gap-2 text-xs">
        {Object.entries(campaign.delivery_summary || {}).map(([key, value]) => <Mini key={key} label={key} value={value as number} />)}
      </div>
    </Section>

    <details className="mt-4 text-xs">
      <summary className="cursor-pointer text-gray-500">Metadata JSON</summary>
      <pre className="mt-2 max-h-72 overflow-auto rounded bg-gray-950 p-3 text-[11px] text-gray-100">{JSON.stringify(campaign.metadata || {}, null, 2)}</pre>
    </details>
  </aside>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="mt-5"><h3 className="text-sm font-semibold text-gray-900">{title}</h3><div className="mt-3 space-y-3">{children}</div></div>;
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{options.map((option) => <option key={option || "ALL"} value={option}>{option || "All"}</option>)}</select></label>;
}

function Mini({ label, value }: { label: string; value?: string | number | null }) {
  return <div><div className="text-xs uppercase text-gray-400">{label}</div><div className="break-all font-mono text-gray-800">{value ?? "-"}</div></div>;
}

function Badge({ value }: { value: string }) {
  const tone = value === "URGENT" ? "bg-red-100 text-red-800" : value === "HIGH" ? "bg-orange-100 text-orange-800" : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-1 text-xs ${tone}`}>{value}</span>;
}
