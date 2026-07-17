"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { broadcastsApi, type BroadcastAuditResponse, type BroadcastAudiencePreviewResponse, type BroadcastCampaignDto, type BroadcastCampaignListResponse, type BroadcastDeliveriesResponse } from "@/lib/api";

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
  const [publishReason, setPublishReason] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [generatingDeliveries, setGeneratingDeliveries] = useState(false);
  const [audiencePreview, setAudiencePreview] = useState<BroadcastAudiencePreviewResponse | null>(null);
  const [previewingAudience, setPreviewingAudience] = useState(false);
  const [deliveries, setDeliveries] = useState<BroadcastDeliveriesResponse | null>(null);
  const [deliveryStatus, setDeliveryStatus] = useState("");
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);
  const [audit, setAudit] = useState<BroadcastAuditResponse | null>(null);
  const [loadingAudit, setLoadingAudit] = useState(false);

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
      setAudiencePreview(null);
      setDeliveries(null);
      setAudit(null);
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
      setAudiencePreview(null);
      setDeliveries(null);
      setAudit(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create draft broadcast");
    } finally {
      setCreating(false);
    }
  }

  async function publishSelected(campaignId: string) {
    setPublishing(true);
    setError(null);
    try {
      const published = await broadcastsApi.publish(campaignId, {
        reason: publishReason.trim() || undefined,
      });
      setSelected(published);
      setAudiencePreview(null);
      setDeliveries(null);
      setAudit(null);
      setPublishReason("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to publish broadcast");
    } finally {
      setPublishing(false);
    }
  }

  async function generateDeliveries(campaignId: string) {
    setGeneratingDeliveries(true);
    setError(null);
    try {
      const updated = await broadcastsApi.generateDeliveries(campaignId);
      setSelected(updated);
      setAudiencePreview(null);
      setDeliveries(null);
      setAudit(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate deliveries");
    } finally {
      setGeneratingDeliveries(false);
    }
  }

  async function previewAudience(campaignId: string) {
    setPreviewingAudience(true);
    setError(null);
    try {
      setAudiencePreview(await broadcastsApi.previewAudience(campaignId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to preview broadcast audience");
    } finally {
      setPreviewingAudience(false);
    }
  }

  async function loadDeliveries(campaignId: string, nextStatus = deliveryStatus) {
    setLoadingDeliveries(true);
    setError(null);
    try {
      setDeliveries(await broadcastsApi.deliveries(campaignId, { status: nextStatus || undefined, limit: 100 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load broadcast deliveries");
    } finally {
      setLoadingDeliveries(false);
    }
  }

  async function loadAudit(campaignId: string) {
    setLoadingAudit(true);
    setError(null);
    try {
      setAudit(await broadcastsApi.audit(campaignId, { limit: 100 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load broadcast audit history");
    } finally {
      setLoadingAudit(false);
    }
  }

  async function openDetail(campaignId: string) {
    setError(null);
    try {
      setSelected(await broadcastsApi.detail(campaignId));
      setAudiencePreview(null);
      setDeliveries(null);
      setAudit(null);
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

      <BroadcastDetail campaign={selected} publishReason={publishReason} setPublishReason={setPublishReason} publishing={publishing} onPublish={publishSelected} generatingDeliveries={generatingDeliveries} onGenerateDeliveries={generateDeliveries} audiencePreview={audiencePreview} previewingAudience={previewingAudience} onPreviewAudience={previewAudience} deliveries={deliveries} deliveryStatus={deliveryStatus} setDeliveryStatus={setDeliveryStatus} loadingDeliveries={loadingDeliveries} onLoadDeliveries={loadDeliveries} audit={audit} loadingAudit={loadingAudit} onLoadAudit={loadAudit} />
    </div> : null}
  </div>;
}

function BroadcastDetail({
  campaign,
  publishReason,
  setPublishReason,
  publishing,
  onPublish,
  generatingDeliveries,
  onGenerateDeliveries,
  audiencePreview,
  previewingAudience,
  onPreviewAudience,
  deliveries,
  deliveryStatus,
  setDeliveryStatus,
  loadingDeliveries,
  onLoadDeliveries,
  audit,
  loadingAudit,
  onLoadAudit,
}: {
  campaign: BroadcastCampaignDto | null;
  publishReason: string;
  setPublishReason: (value: string) => void;
  publishing: boolean;
  onPublish: (campaignId: string) => Promise<void>;
  generatingDeliveries: boolean;
  onGenerateDeliveries: (campaignId: string) => Promise<void>;
  audiencePreview: BroadcastAudiencePreviewResponse | null;
  previewingAudience: boolean;
  onPreviewAudience: (campaignId: string) => Promise<void>;
  deliveries: BroadcastDeliveriesResponse | null;
  deliveryStatus: string;
  setDeliveryStatus: (value: string) => void;
  loadingDeliveries: boolean;
  onLoadDeliveries: (campaignId: string, status?: string) => Promise<void>;
  audit: BroadcastAuditResponse | null;
  loadingAudit: boolean;
  onLoadAudit: (campaignId: string) => Promise<void>;
}) {
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

    {campaign.status === "DRAFT" ? <div className="mt-5 rounded border bg-amber-50 p-3">
      <h3 className="text-sm font-semibold text-amber-900">Publish broadcast</h3>
      <p className="mt-1 text-xs text-amber-800">Publishing changes status to PUBLISHED and sets starts_at. Delivery generation is still a separate future step.</p>
      <Input label="Publish reason" value={publishReason} onChange={setPublishReason} />
      <button type="button" onClick={() => void onPublish(campaign.id)} disabled={publishing} className="mt-3 rounded bg-green-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{publishing ? "Publishing..." : "Publish"}</button>
    </div> : null}

    {campaign.status === "PUBLISHED" ? <div className="mt-5 rounded border bg-blue-50 p-3">
      <h3 className="text-sm font-semibold text-blue-900">Generate deliveries</h3>
      <p className="mt-1 text-xs text-blue-800">Creates pending delivery rows for currently supported audience rules. This is idempotent.</p>
      <button type="button" onClick={() => void onGenerateDeliveries(campaign.id)} disabled={generatingDeliveries} className="mt-3 rounded bg-blue-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{generatingDeliveries ? "Generating..." : "Generate deliveries"}</button>
    </div> : null}

    <div className="mt-5 rounded border bg-emerald-50 p-3">
      <h3 className="text-sm font-semibold text-emerald-900">Audience preview</h3>
      <p className="mt-1 text-xs text-emerald-800">Estimate unique farmer recipients before publishing or generating delivery rows. Unsupported rules are shown separately.</p>
      <button type="button" onClick={() => void onPreviewAudience(campaign.id)} disabled={previewingAudience} className="mt-3 rounded bg-emerald-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{previewingAudience ? "Previewing..." : "Preview audience"}</button>
      {audiencePreview ? <div className="mt-3 space-y-3 text-xs">
        <div className="grid grid-cols-3 gap-2">
          <DeliveryMini label="Estimated" value={audiencePreview.estimated_farmer_count} tone="green" />
          <DeliveryMini label="Existing" value={audiencePreview.existing_delivery_count} tone="blue" />
          <DeliveryMini label="Unsupported" value={audiencePreview.unsupported_rule_count} tone={audiencePreview.unsupported_rule_count ? "amber" : "slate"} />
        </div>
        <div className="space-y-2">
          {audiencePreview.rule_summaries.map((rule) => <div key={rule.rule_id} className="rounded border bg-white p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{rule.rule_type} {rule.operator}</span>
              <span className={rule.supported ? "text-green-700" : "text-amber-700"}>{rule.supported ? `${rule.matched_farmer_count} match(es)` : "Not expanded"}</span>
            </div>
            {rule.note ? <p className="mt-1 text-amber-700">{rule.note}</p> : null}
            {rule.sample_farmer_ids.length ? <p className="mt-1 break-all font-mono text-[10px] text-gray-500">Sample: {rule.sample_farmer_ids.join(", ")}</p> : null}
          </div>)}
        </div>
        {audiencePreview.match_reason_counts && Object.keys(audiencePreview.match_reason_counts).length ? <div className="rounded border bg-white p-2">
          <div className="font-semibold text-gray-700">Why farmers matched</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(audiencePreview.match_reason_counts).map(([ruleType, count]) => <span key={ruleType} className="rounded-full bg-blue-50 px-2 py-1 text-blue-800">{ruleType}: {count}</span>)}
          </div>
          {audiencePreview.sample_matches?.length ? <div className="mt-2 space-y-1 text-[10px] text-gray-500">
            {audiencePreview.sample_matches.slice(0, 5).map((match) => <div key={match.farmer_id} className="break-all">
              <span className="font-mono">{match.farmer_id}</span> matched by {match.matched_by.join(", ")}
            </div>)}
          </div> : null}
        </div> : null}
      </div> : null}
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

    <Section title="Delivery lifecycle">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <DeliveryMini label="Total" value={campaign.delivery_summary?.total || 0} tone="slate" />
        <DeliveryMini label="Pending" value={campaign.delivery_summary?.pending || 0} tone="amber" />
        <DeliveryMini label="Delivered" value={campaign.delivery_summary?.delivered || 0} tone="blue" />
        <DeliveryMini label="Read" value={campaign.delivery_summary?.read || 0} tone="purple" />
        <DeliveryMini label="Acknowledged" value={campaign.delivery_summary?.acknowledged || 0} tone="green" />
        <DeliveryMini label="Failed" value={campaign.delivery_summary?.failed || 0} tone="red" />
      </div>
      <div className="mt-3 rounded bg-gray-50 p-3 text-xs">
        <Mini label="Generation status" value={String(campaign.metadata?.delivery_generation || "NOT_STARTED")} />
        <Mini label="Last generated at" value={String(campaign.metadata?.last_delivery_generation_at || "-")} />
        <Mini label="Last generated rows" value={String(campaign.metadata?.last_delivery_generation_created ?? "-")} />
      </div>
    </Section>

    <Section title="Delivery drilldown">
      <div className="flex items-end gap-2">
        <Select label="Status" value={deliveryStatus} onChange={setDeliveryStatus} options={["", "PENDING", "DELIVERED", "ACKNOWLEDGED", "FAILED"]} />
        <button type="button" onClick={() => void onLoadDeliveries(campaign.id, deliveryStatus)} disabled={loadingDeliveries} className="rounded bg-slate-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{loadingDeliveries ? "Loading..." : "Load deliveries"}</button>
      </div>
      {deliveries ? <div className="rounded border">
        <div className="border-b bg-gray-50 p-2 text-xs text-gray-500">{deliveries.count} delivery row(s) returned.</div>
        <div className="max-h-72 overflow-auto divide-y">
          {deliveries.deliveries.map((row) => <div key={row.id} className="p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-gray-900">{row.farmer?.display_name || row.farmer_id || "Unknown recipient"}</span>
              <span className="rounded bg-gray-100 px-2 py-1 text-[10px] text-gray-700">{row.delivery_status}</span>
            </div>
            <div className="mt-1 text-gray-500">{row.farmer?.mobile_number || "-"} / {row.farmer?.village_name_manual || "-"}</div>
            <div className="mt-1 break-all font-mono text-[10px] text-gray-400">{row.id}</div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] text-gray-500">
              <Mini label="Delivered" value={row.delivered_at || "-"} />
              <Mini label="Read" value={row.read_at || "-"} />
              <Mini label="Ack" value={row.acknowledged_at || "-"} />
            </div>
          </div>)}
          {deliveries.deliveries.length === 0 ? <div className="p-4 text-center text-xs text-gray-400">No delivery rows match this filter.</div> : null}
        </div>
      </div> : <p className="text-xs text-gray-400">Load deliveries to inspect recipient-level status.</p>}
    </Section>


    <Section title="Audit history">
      <button type="button" onClick={() => void onLoadAudit(campaign.id)} disabled={loadingAudit} className="rounded bg-slate-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{loadingAudit ? "Loading..." : "Load audit"}</button>
      {audit ? <div className="rounded border">
        <div className="border-b bg-gray-50 p-2 text-xs text-gray-500">{audit.count} audit event(s) returned.</div>
        <div className="max-h-72 overflow-auto divide-y">
          {audit.events.map((event) => <div key={event.id} className="p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-gray-900">{event.action}</span>
              <span className="text-gray-400">{event.created_at || "-"}</span>
            </div>
            <div className="mt-1 text-gray-500">{event.actor_type || "-"} / {event.actor_id || "-"}</div>
            {event.reason ? <div className="mt-1 text-amber-700">Reason: {event.reason}</div> : null}
            <details className="mt-2">
              <summary className="cursor-pointer text-gray-500">Payload</summary>
              <pre className="mt-1 max-h-36 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify({ before: event.before, after: event.after, metadata: event.metadata }, null, 2)}</pre>
            </details>
          </div>)}
          {audit.events.length === 0 ? <div className="p-4 text-center text-xs text-gray-400">No audit events.</div> : null}
        </div>
      </div> : <p className="text-xs text-gray-400">Load audit to inspect create/publish/delivery/read/ack history.</p>}
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

function DeliveryMini({ label, value, tone }: { label: string; value: number; tone: "slate" | "amber" | "blue" | "purple" | "green" | "red" }) {
  const tones = {
    slate: "bg-slate-50 text-slate-700",
    amber: "bg-amber-50 text-amber-800",
    blue: "bg-blue-50 text-blue-800",
    purple: "bg-purple-50 text-purple-800",
    green: "bg-green-50 text-green-800",
    red: "bg-red-50 text-red-800",
  };
  return <div className={`rounded p-3 ${tones[tone]}`}><div className="text-[10px] uppercase opacity-70">{label}</div><div className="text-lg font-bold">{value}</div></div>;
}

function Mini({ label, value }: { label: string; value?: string | number | null }) {
  return <div><div className="text-xs uppercase text-gray-400">{label}</div><div className="break-all font-mono text-gray-800">{value ?? "-"}</div></div>;
}

function Badge({ value }: { value: string }) {
  const tone = value === "URGENT" ? "bg-red-100 text-red-800" : value === "HIGH" ? "bg-orange-100 text-orange-800" : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-1 text-xs ${tone}`}>{value}</span>;
}
