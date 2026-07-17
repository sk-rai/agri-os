
"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { reportsApi, type AdminDashboardResponse, type SyncMaterializationHealthResponse, type SystemReadinessResponse } from "@/lib/api";
import { CopyLinkButton } from "@/components/copy-link-button";

type DashboardFilters = {
  projectId: string;
  dateFrom: string;
  dateTo: string;
};

const initialFilters: DashboardFilters = { projectId: "", dateFrom: "", dateTo: "" };

function compactQuery(params: Record<string, string | number | null | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}


function dashboardLookupHref(data: AdminDashboardResponse, params: Record<string, string | number | null | undefined> = {}) {
  return `/lookup${compactQuery({ projectId: data.filters.project_id, ...params })}`;
}

function geometryLookupHref(data: AdminDashboardResponse, geometrySource: string) {
  const source = geometrySource.toUpperCase();
  if (source === "MISSING" || source === "NONE") return dashboardLookupHref(data, { geometryStatus: "MISSING" });
  return dashboardLookupHref(data, { geometrySource: source });
}

function dashboardActivityHref(data: AdminDashboardResponse, params: Record<string, string | number | null | undefined> = {}) {
  return `/activity-usage${compactQuery({
    projectId: data.filters.project_id,
    dateFrom: data.filters.date_from,
    dateTo: data.filters.date_to,
    ...params,
  })}`;
}

function dashboardQueryThreadsHref(data: AdminDashboardResponse | null, params?: { status?: string; priority?: string }) {
  const q = new URLSearchParams();
  const projectId = data?.filters?.project_id;
  if (projectId) q.set("projectId", String(projectId));
  if (params?.status) q.set("status", params.status);
  if (params?.priority) q.set("priority", params.priority);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return `/query-threads${suffix}`;
}

function dashboardFieldEventsHref(data: AdminDashboardResponse | null, params: Record<string, string | number | null | undefined> = {}) {
  return `/field-events${compactQuery({ projectId: data?.filters.project_id, ...params })}`;
}

function dashboardProjectTraceHref(data: AdminDashboardResponse, params: Record<string, string | number | null | undefined> = {}) {
  if (!data.filters.project_id) return "/lookup";
  return `/project-trace/${data.filters.project_id}${compactQuery({
    dateFrom: data.filters.date_from,
    dateTo: data.filters.date_to,
    ...params,
  })}`;
}

const readinessPriority: Record<string, number> = {
  "Project setup": 1,
  "Crop setup": 2,
  "Workflow runtime": 3,
  "Workflow assignments": 4,
  "Input catalog": 5,
  "Product catalog": 6,
  "Broadcasts": 7,
  "Project enrollment imports": 8,
  "Project enrollment lifecycle": 9,
  "Farmer sync": 10,
  "Parcel geometry": 11,
  "Activity evidence": 12,
  "Sync health": 13,
};

function readinessCategory(label: string) {
  if (["Project setup", "Crop setup", "Profile forms", "Workflow runtime", "Workflow assignments", "Input catalog", "Product catalog"].includes(label)) return "Setup";
  if (["Project enrollment imports", "Project enrollment lifecycle", "Farmer sync", "Parcel geometry", "Activity evidence"].includes(label)) return "Field data";
  if (["Broadcasts"].includes(label)) return "Operations";
  return "Operations";
}

function sortReadinessItems<T extends { label: string; ready: boolean }>(items: T[]) {
  return [...items].sort((left, right) => {
    if (left.ready !== right.ready) return Number(left.ready) - Number(right.ready);
    return (readinessPriority[left.label] || 99) - (readinessPriority[right.label] || 99);
  });
}

export default function DashboardPage() {
  const [data, setData] = useState<AdminDashboardResponse | null>(null);
  const [filters, setFilters] = useState(initialFilters);
  const [loading, setLoading] = useState(true);
  const [syncHealth, setSyncHealth] = useState<SyncMaterializationHealthResponse | null>(null);
  const [readiness, setReadiness] = useState<SystemReadinessResponse | null>(null);
  const [syncLoading, setSyncLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  const loadDashboard = (nextFilters = filters) => {
    setLoading(true);
    setError(null);
    const dashboardRequest = reportsApi
      .adminDashboard({
        projectId: nextFilters.projectId.trim() || undefined,
        dateFrom: nextFilters.dateFrom || undefined,
        dateTo: nextFilters.dateTo || undefined,
        limit: 10,
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    setSyncLoading(true);
    const syncRequest = reportsApi
      .syncHealth({ projectId: nextFilters.projectId.trim() || undefined, limit: 8 })
      .then(setSyncHealth)
      .catch((e) => setError(e.message))
      .finally(() => setSyncLoading(false));
    const readinessRequest = reportsApi
      .systemReadiness({ projectId: nextFilters.projectId.trim() || undefined })
      .then(setReadiness)
      .catch(() => setReadiness(null));

    Promise.allSettled([dashboardRequest, syncRequest, readinessRequest]).then(() => setLastRefreshedAt(new Date()));
  };

  useEffect(() => {
    loadDashboard(initialFilters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    loadDashboard(filters);
  };

  const clearFilters = () => {
    setFilters(initialFilters);
    loadDashboard(initialFilters);
  };

  if (loading && !data) return <div className="text-gray-500">Loading dashboard...</div>;
  if (error && !data) return <div className="text-red-500">Error: {error}</div>;

  const summary = data?.summary;
  const refreshLabel = lastRefreshedAt ? lastRefreshedAt.toLocaleString() : "Not refreshed yet";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Lightweight operational summary from project, farmer, parcel, crop-cycle, and activity trace data.
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <div className="flex gap-2">
            <button type="button" onClick={() => loadDashboard(filters)} disabled={loading || syncLoading} className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50">
              {loading || syncLoading ? "Refreshing..." : "Refresh"}
            </button>
            <Link href="/lookup" className="rounded-md border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50">
              Search records
            </Link>
          </div>
          <p className="text-xs text-gray-500">Last refreshed: {refreshLabel}</p>
        </div>
      </div>

      <form onSubmit={applyFilters} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Project ID</span>
            <input
              value={filters.projectId}
              onChange={(event) => setFilters((current) => ({ ...current, projectId: event.target.value }))}
              placeholder="Optional UUID"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Activity from</span>
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(event) => setFilters((current) => ({ ...current, dateFrom: event.target.value }))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Activity to</span>
            <input
              type="date"
              value={filters.dateTo}
              onChange={(event) => setFilters((current) => ({ ...current, dateTo: event.target.value }))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <div className="flex items-end gap-2">
            <button type="submit" className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={loading}>
              {loading ? "Refreshing..." : "Apply"}
            </button>
            <button type="button" onClick={clearFilters} className="rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50">
              Clear
            </button>
          </div>
        </div>
        {error ? <p className="mt-3 text-sm text-red-600">Latest refresh failed: {error}</p> : null}
      </form>

      <CommandCenterPanel data={data} syncHealth={syncHealth} />
      <SystemReadinessPanel readiness={readiness} data={data} syncHealth={syncHealth} />
      <AttentionQueuePanel data={data} syncHealth={syncHealth} />

      {summary ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Projects" value={summary.project_count} tone="blue" href={dashboardLookupHref(data)} />
            <StatCard label="Farmers" value={summary.farmer_count} tone="green" href={dashboardLookupHref(data)} />
            <StatCard label="Parcels" value={summary.parcel_count} tone="indigo" href={dashboardLookupHref(data)} />
            <StatCard label="Crop cycles" value={summary.crop_cycle_count} tone="purple" href={dashboardProjectTraceHref(data)} />
            <StatCard label="Active cycles" value={summary.active_cycle_count} tone="yellow" href={dashboardProjectTraceHref(data, { cycleStatus: "ACTIVE" })} />
            <StatCard label="Completed cycles" value={summary.completed_cycle_count} tone="green" href={dashboardProjectTraceHref(data, { cycleStatus: "COMPLETED" })} />
            <StatCard label="Activities" value={summary.activity_count} tone="blue" href={dashboardActivityHref(data)} />
            <StatCard label="Field events" value={summary.field_event_count || 0} tone="yellow" href={dashboardFieldEventsHref(data)} />
            <StatCard label="Open queries" value={summary.open_query_count || 0} tone="purple" href={dashboardQueryThreadsHref(data, { status: "OPEN" })} />
            <StatCard label="Urgent queries" value={summary.urgent_open_query_count || 0} tone="yellow" href={dashboardQueryThreadsHref(data, { status: "OPEN" })} />
            <StatCard label="Activity cost" value={`INR ${summary.total_cost}`} tone="slate" href={dashboardActivityHref(data)} />
          </div>

          <SyncHealthPanel data={syncHealth} loading={syncLoading} />

          <div className="grid gap-4 lg:grid-cols-3">
            <SummaryList title="Crop distribution" empty="No crop cycles yet" rows={data.crop_distribution.map((row) => ({ label: row.crop_code, value: row.crop_cycle_count, href: data.filters.project_id ? dashboardProjectTraceHref(data, { cropCode: row.crop_code }) : dashboardActivityHref(data, { cropCode: row.crop_code }) }))} />
            <SummaryList title="Geometry coverage" empty="No parcels yet" rows={data.geometry_coverage.map((row) => ({ label: row.geometry_source, value: row.parcel_count, href: geometryLookupHref(data, row.geometry_source) }))} />
            <SummaryList title="Activity types" empty="No activities yet" rows={data.activity_count_by_type.map((row) => ({ label: row.activity_type, value: row.activity_count, href: dashboardActivityHref(data, { activityType: row.activity_type }) }))} />
          </div>

          <RecentProjects data={data} />
          <RecentFarmers data={data} />
          <RecentParcels data={data} />
          <RecentActivities data={data} />
        </>
      ) : null}
    </div>
  );
}

function SystemReadinessPanel({ readiness, data, syncHealth }: { readiness: SystemReadinessResponse | null; data: AdminDashboardResponse | null; syncHealth: SyncMaterializationHealthResponse | null }) {
  const summary = data?.summary;
  const backlog = summary?.admin_backlog;
  const syncSummary = syncHealth?.summary;
  const syncIssues = (syncSummary?.failed_count || 0) + (syncSummary?.conflict_count || 0) + (syncSummary?.dependency_missing_count || 0);
  const materializationGaps = (syncHealth?.materialization || []).reduce((sum, row) => sum + row.unmaterialized_count, 0);
  const fallbackItems = [
    {
      label: "Project setup",
      ready: (summary?.project_count || 0) > 0,
      detail: `${summary?.project_count || 0} projects available`,
      href: "/projects",
    },
    {
      label: "Workflow runtime",
      ready: (summary?.crop_cycle_count || 0) > 0 && (backlog?.workflow_validation_blocker_count || 0) === 0,
      detail: `${summary?.crop_cycle_count || 0} crop cycles, ${backlog?.workflow_validation_blocker_count || 0} blockers`,
      href: "/workflows?filter=validation-blockers",
    },
    {
      label: "Farmer sync",
      ready: (summary?.farmer_count || 0) > 0,
      detail: `${summary?.farmer_count || 0} farmers restored/materialized`,
      href: dashboardLookupHref(data || ({ filters: { limit: 10 } } as AdminDashboardResponse)),
    },
    {
      label: "Parcel geometry",
      ready: (summary?.parcel_count || 0) > 0 && (summary?.geometry_missing_count || 0) === 0,
      detail: `${summary?.geometry_captured_count || 0} captured, ${summary?.geometry_missing_count || 0} missing`,
      href: data ? geometryLookupHref(data, "MISSING") : "/lookup?geometryStatus=MISSING",
    },
    {
      label: "Activity evidence",
      ready: (summary?.activity_count || 0) > 0,
      detail: `${summary?.activity_count || 0} logged activities, ${summary?.variance_count || 0} variances`,
      href: data ? dashboardActivityHref(data) : "/activity-usage",
    },
    {
      label: "Sync health",
      ready: syncIssues === 0 && materializationGaps === 0,
      detail: `${syncIssues} failed/conflict/dependency issues, ${materializationGaps} materialization gaps`,
      href: syncIssues || materializationGaps ? "/sync-health?gapOnly=true" : "/sync-health",
    },
  ];
  const readinessItems = sortReadinessItems(readiness?.checks || fallbackItems);
  const readyCount = readiness?.summary.ready_count ?? readinessItems.filter((item) => item.ready).length;
  const checkCount = readiness?.summary.check_count ?? readinessItems.length;

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">System readiness</h2>
          <p className="mt-1 text-sm text-gray-500">Quick sanity check for whether the tenant has usable configuration, synced field data, and clean operations signals.</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${readyCount === readinessItems.length ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-900"}`}>
          {readyCount}/{checkCount} ready
        </span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {readinessItems.map((item) => <ReadinessItem key={item.label} {...item} />)}
      </div>
    </section>
  );
}

function ReadinessItem({ label, ready, detail, href }: { label: string; ready: boolean; detail: string; href: string }) {
  const category = readinessCategory(label);
  return (
    <Link href={href} className={`rounded-lg border p-3 transition hover:-translate-y-0.5 hover:shadow-md ${ready ? "border-green-200 bg-green-50 text-green-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide opacity-60">{category}</p>
          <p className="mt-1 text-sm font-semibold">{label}</p>
        </div>
        <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-bold">{ready ? "Ready" : "Check"}</span>
      </div>
      <p className="mt-2 text-xs opacity-80">{detail}</p>
      <p className="mt-3 text-xs font-medium opacity-75">Open detail -&gt;</p>
    </Link>
  );
}

function AttentionQueuePanel({ data, syncHealth }: { data: AdminDashboardResponse | null; syncHealth: SyncMaterializationHealthResponse | null }) {
  const summary = data?.summary;
  const syncSummary = syncHealth?.summary;
  const backlog = summary?.admin_backlog;
  const attentionItems = [
    {
      label: "Workflow validation blockers",
      count: backlog?.workflow_validation_blocker_count || 0,
      href: "/workflows?filter=validation-blockers",
      tone: "red",
      help: "Draft workflows that are unvalidated, stale, or blocked by validation errors.",
    },
    {
      label: "Inputs awaiting review",
      count: backlog?.input_review_count || 0,
      href: "/inputs?filter=review",
      tone: "amber",
      help: "Input catalog records submitted for approval or publishing.",
    },
    {
      label: "Pending CSV imports",
      count: backlog?.csv_import_pending_count || 0,
      href: "/inputs?filter=csv-pending",
      tone: "blue",
      help: "Validated input CSV batches waiting for admin apply.",
    },
    {
      label: "Product CSV imports",
      count: (backlog?.product_csv_import_pending_count || 0) + (backlog?.product_csv_import_invalid_count || 0),
      href: "/products",
      tone: (backlog?.product_csv_import_invalid_count || 0) ? "red" : "blue",
      help: "Validated or invalid product catalog CSV batches that need review/apply.",
    },
    {
      label: "Enrollment CSV imports",
      count: (backlog?.project_enrollment_csv_import_pending_count || 0) + (backlog?.project_enrollment_csv_import_invalid_count || 0),
      href: data?.filters.project_id ? `/project-enrollments?projectId=${data.filters.project_id}` : "/project-enrollments",
      tone: (backlog?.project_enrollment_csv_import_invalid_count || 0) ? "red" : "blue",
      help: "Validated or invalid farmer/project enrollment CSV batches that need review/apply.",
    },
    {
      label: "Weather refresh due",
      count: backlog?.weather_provider_due_count || 0,
      href: "/weather",
      tone: "amber",
      help: "Enabled weather providers whose next refresh is due or missing, affecting weather-triggered broadcasts.",
    },
    {
      label: "Fresh weather snapshots",
      count: backlog?.weather_provider_enabled_count && !(backlog?.weather_fresh_snapshot_count || 0) ? 1 : 0,
      href: "/weather",
      tone: "amber",
      help: "No fresh/non-expired weather snapshots are available even though weather providers are configured.",
    },
    {
      label: "High priority field events",
      count: summary?.high_priority_field_event_count || 0,
      href: dashboardFieldEventsHref(data),
      tone: "red",
      help: "Unresolved farmer/field-agent reports marked HIGH or CRITICAL, such as pest, hail, flood, or crop stress.",
    },
    {
      label: "Unresolved field events",
      count: summary?.unresolved_field_event_count || 0,
      href: dashboardFieldEventsHref(data),
      tone: "amber",
      help: "Ground-level rain, pest, disease, hail, locust, and stress reports still open for review.",
    },
    {
      label: "Failed sync events",
      count: syncSummary?.failed_count || 0,
      href: "/sync-health?status=FAILED",
      tone: "red",
      help: "Events accepted by sync but not successfully materialized.",
    },
    {
      label: "Sync conflicts",
      count: syncSummary?.conflict_count || 0,
      href: "/sync-health?status=CONFLICT",
      tone: "red",
      help: "Client/server conflicts waiting for admin resolution.",
    },
    {
      label: "Missing GPS parcels",
      count: summary?.geometry_missing_count || 0,
      href: data ? geometryLookupHref(data, "MISSING") : "/lookup?geometryStatus=MISSING",
      tone: "amber",
      help: "Parcels without usable geometry or centroid data.",
    },
    {
      label: "Activity variances",
      count: summary?.variance_count || 0,
      href: data ? dashboardActivityHref(data) : "/activity-usage",
      tone: "purple",
      help: "Logged activities where actual inputs differ from recommended rules.",
    },
    {
      label: "Active crop cycles",
      count: summary?.active_cycle_count || 0,
      href: data ? dashboardProjectTraceHref(data, { cycleStatus: "ACTIVE" }) : "/lookup",
      tone: "blue",
      help: "Cycles currently in progress and likely to produce field activity.",
    },
  ];
  const actionableCount = attentionItems.reduce((sum, item) => sum + item.count, 0);

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Attention queues</h2>
          <p className="mt-1 text-sm text-gray-500">Operational signals that may need admin follow-up.</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${actionableCount > 0 ? "bg-amber-100 text-amber-900" : "bg-green-100 text-green-800"}`}>
          {actionableCount > 0 ? `${actionableCount} open signals` : "No open signals"}
        </span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {attentionItems.map((item) => (
          <AttentionItem key={item.label} {...item} />
        ))}
      </div>
    </section>
  );
}

function AttentionItem({ label, count, href, tone, help }: { label: string; count: number; href: string; tone: string; help: string }) {
  const toneMap: Record<string, string> = {
    red: "border-red-200 bg-red-50 text-red-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    purple: "border-purple-200 bg-purple-50 text-purple-900",
    blue: "border-blue-200 bg-blue-50 text-blue-900",
  };
  const toneClass = toneMap[tone] || "border-gray-200 bg-gray-50 text-gray-900";

  return (
    <div className={`rounded-lg border p-3 ${toneClass}`}>
      <Link href={href} className="block transition hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-semibold">{label}</p>
          <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-bold">{count}</span>
        </div>
        <p className="mt-2 text-xs opacity-75">{help}</p>
        <p className="mt-3 rounded bg-white/60 px-2 py-1 font-mono text-[10px] opacity-70">Opens {href}</p>
      </Link>
      <CopyLinkButton href={href} className="mt-3 rounded border border-white/70 bg-white/70 px-2 py-1 text-xs font-semibold opacity-80 hover:bg-white hover:opacity-100" />
    </div>
  );
}

function CommandCenterPanel({ data, syncHealth }: { data: AdminDashboardResponse | null; syncHealth: SyncMaterializationHealthResponse | null }) {
  const summary = data?.summary;
  const syncSummary = syncHealth?.summary;
  const projectQuery = data?.filters.project_id ? `?projectId=${data.filters.project_id}` : "";
  const cards = [
    {
      title: "Workflow setup",
      description: "Design, validate, publish, and assign crop workflows.",
      href: "/workflows",
      metric: summary ? `${summary.crop_cycle_count} cycles` : "Templates",
      accent: "border-green-200 bg-green-50 text-green-900",
      destination: "Workflow catalog",
    },
    {
      title: "Crop setup & imports",
      description: "Manage crop taxonomy, propagation methods, crop catalog CSV imports, and onboarding order.",
      href: "/crop-taxonomy",
      metric: "Crops",
      accent: "border-emerald-200 bg-emerald-50 text-emerald-900",
      destination: "Crop setup",
    },
    {
      title: "Input catalog",
      description: "Manage inputs, products, dosage rules, and project input visibility.",
      href: "/inputs",
      metric: summary ? `${summary.activity_count} activities` : "Catalog",
      accent: "border-blue-200 bg-blue-50 text-blue-900",
      destination: "Input catalog",
    },
    {
      title: "Project setup",
      description: "Review tenants, projects, users, workflow enablement, and project inputs.",
      href: "/projects",
      metric: summary ? `${summary.project_count} projects` : "Projects",
      accent: "border-indigo-200 bg-indigo-50 text-indigo-900",
      destination: "Project registry",
    },
    {
      title: "Activity traceability",
      description: "Inspect logged activities, cost, variance, crop stages, inputs, and products.",
      href: `/activity-usage${projectQuery}`,
      metric: summary ? `${summary.variance_count} variance` : "Trace",
      accent: "border-purple-200 bg-purple-50 text-purple-900",
      destination: "Activity usage trace",
    },
    {
      title: "Farmer / parcel lookup",
      description: "Search farmers, parcels, projects, geometry status, and trace records.",
      href: `/lookup${projectQuery}`,
      metric: summary ? `${summary.geometry_missing_count} missing GPS` : "Search",
      accent: "border-amber-200 bg-amber-50 text-amber-900",
      destination: "Farmer and parcel lookup",
    },
    {
      title: "Field events",
      description: "Review farmer and field-agent reports for rain, pest, disease, hail, flood, crop stress, and other local events.",
      href: `/field-events${projectQuery}`,
      metric: summary ? `${summary.unresolved_field_event_count || 0} open` : "Events",
      accent: summary && (summary.high_priority_field_event_count || 0) > 0 ? "border-red-200 bg-red-50 text-red-900" : "border-orange-200 bg-orange-50 text-orange-900",
      destination: "Field event reports",
    },
    {
      title: "Sync operations",
      description: "Monitor materialization health, conflicts, failures, and recent sync events.",
      href: "/sync-health",
      metric: syncSummary ? `${syncSummary.failed_count + syncSummary.conflict_count} attention` : "Health",
      accent: syncSummary && syncSummary.failed_count + syncSummary.conflict_count > 0 ? "border-red-200 bg-red-50 text-red-900" : "border-slate-200 bg-slate-50 text-slate-900",
      destination: "Sync operations",
    },
  ];

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Command center</h2>
          <p className="mt-1 text-sm text-gray-500">Quick entry points aligned with the admin navigation groups.</p>
        </div>
        <Link href="/my-access" className="text-sm font-medium text-blue-700 hover:underline">Check my permissions</Link>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <Link key={card.title} href={card.href} className={`rounded-lg border p-4 transition hover:-translate-y-0.5 hover:shadow-md ${card.accent}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{card.title}</p>
                <p className="mt-1 text-sm opacity-80">{card.description}</p>
              </div>
              <span className="shrink-0 rounded-full bg-white/70 px-2.5 py-1 text-xs font-semibold">{card.metric}</span>
            </div>
            <p className="mt-3 text-xs font-medium opacity-75">Open {card.destination} &rarr;</p>
          </Link>
        ))}
      </div>
    </section>
  );
}

function StatCard({ label, value, tone, href }: { label: string; value: string | number; tone: "blue" | "green" | "indigo" | "purple" | "yellow" | "slate"; href?: string }) {
  const toneMap = {
    blue: "border-blue-200 bg-blue-50 text-blue-800",
    green: "border-green-200 bg-green-50 text-green-800",
    indigo: "border-indigo-200 bg-indigo-50 text-indigo-800",
    purple: "border-purple-200 bg-purple-50 text-purple-800",
    yellow: "border-yellow-200 bg-yellow-50 text-yellow-800",
    slate: "border-slate-200 bg-slate-50 text-slate-800",
  };
  const content = (
    <>
      <p className="text-sm opacity-80">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
      {href ? <p className="mt-2 text-xs font-medium opacity-75">Open drill-down</p> : null}
    </>
  );
  const className = `rounded-lg border p-4 shadow-sm transition ${toneMap[tone]} ${href ? "hover:-translate-y-0.5 hover:shadow-md" : ""}`;
  return href ? <Link href={href} className={className}>{content}</Link> : <div className={className}>{content}</div>;
}

function SummaryList({ title, rows, empty }: { title: string; rows: Array<{ label: string; value: number; href?: string }>; empty: string }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      {rows.length === 0 ? <p className="mt-3 text-sm text-gray-500">{empty}</p> : null}
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <Link key={row.label} href={row.href || "#"} className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm hover:bg-blue-50">
            <span className="font-medium text-gray-700">{row.label}</span>
            <span className="text-gray-900">{row.value}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function RecentProjects({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent projects" empty="No projects found">
      {data.projects.map((project) => (
        <tr key={project.id}>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={project.trace_url}>{project.name}</Link></td>
          <td className="px-3 py-2">{project.status || "-"}</td>
          <td className="px-3 py-2">{project.crop_scope.join(", ") || "-"}</td>
          <td className="px-3 py-2 text-right">{project.crop_cycle_count}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function RecentFarmers({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent farmers" empty="No farmers found">
      {data.farmers.map((farmer) => (
        <tr key={farmer.id}>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={farmer.trace_url}>{farmer.label}</Link></td>
          <td className="px-3 py-2">{farmer.mobile_number || "-"}</td>
          <td className="px-3 py-2">{farmer.village_name || "-"}</td>
          <td className="px-3 py-2 text-right">{farmer.activity_count}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function RecentParcels({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent parcels" empty="No parcels found">
      {data.parcels.map((parcel) => (
        <tr key={parcel.id}>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={parcel.trace_url}>{parcel.label}</Link></td>
          <td className="px-3 py-2">{parcel.farmer_name || "-"}</td>
          <td className="px-3 py-2">{parcel.geometry_source || "MISSING"}</td>
          <td className="px-3 py-2 text-right">{parcel.crop_cycle_count}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function RecentActivities({ data }: { data: AdminDashboardResponse }) {
  return (
    <TableSection title="Recent activities" empty="No activities found">
      {data.activities.map((activity) => (
        <tr key={activity.activity_id}>
          <td className="px-3 py-2">{activity.activity_date || "-"}</td>
          <td className="px-3 py-2">{activity.farmer_name || "-"}</td>
          <td className="px-3 py-2">{activity.crop_code} / {activity.stage_code || "-"}</td>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={dashboardActivityHref(data, { activityType: activity.activity_type })}>{activity.activity_type}</Link></td>
          <td className="px-3 py-2"><Link className="text-blue-700 hover:underline" href={dashboardActivityHref(data, { inputCode: activity.input_code })}>{activity.input_name || activity.input_code || "-"}</Link></td>
          <td className="px-3 py-2 text-right">{activity.cost_amount ? `INR ${activity.cost_amount}` : "-"}</td>
        </tr>
      ))}
    </TableSection>
  );
}

function TableSection({ title, empty, children }: { title: string; empty: string; children: React.ReactNode }) {
  const hasRows = Array.isArray(children) ? children.length > 0 : Boolean(children);
  return (
    <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      </div>
      {!hasRows ? <p className="p-4 text-sm text-gray-500">{empty}</p> : null}
      {hasRows ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <tbody className="divide-y divide-gray-100">{children}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}


function SyncHealthPanel({ data, loading }: { data: SyncMaterializationHealthResponse | null; loading: boolean }) {
  const summary = data?.summary;
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Sync & materialization health</h2>
          <p className="text-sm text-gray-500">Accepted mobile events compared with operational farmer, parcel, and geometry rows.</p>
        </div>
        <div className="flex gap-3"><Link href="/sync-health" className="text-sm font-medium text-blue-700 hover:underline">Open sync health</Link><Link href="/conflicts" className="text-sm font-medium text-blue-700 hover:underline">Conflicts</Link></div>
      </div>
      {loading && !data ? <p className="mt-4 text-sm text-gray-500">Loading sync health...</p> : null}
      {summary ? (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-5">
            <MiniStat label="Committed" value={summary.committed_count} />
            <MiniStat label="Failed" value={summary.failed_count} />
            <MiniStat label="Conflicts" value={summary.conflict_count} />
            <MiniStat label="Dependency missing" value={summary.dependency_missing_count} />
            <MiniStat label="Audit entries" value={summary.audit_chain_count} />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="overflow-hidden rounded-md border border-gray-100">
              <table className="min-w-full divide-y divide-gray-100 text-sm">
                <thead className="bg-gray-50"><tr>{["Entity", "Committed", "Materialized", "Gap"].map((head) => <th key={head} className="px-3 py-2 text-left font-medium text-gray-600">{head}</th>)}</tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {data.materialization.map((row) => (
                    <tr key={row.entity_type}>
                      <td className="px-3 py-2 font-medium text-gray-800">{row.entity_type}</td>
                      <td className="px-3 py-2">{row.committed_count}</td>
                      <td className="px-3 py-2">{row.materialized_count}</td>
                      <td className={row.unmaterialized_count ? "px-3 py-2 font-semibold text-red-700" : "px-3 py-2 text-green-700"}>{row.unmaterialized_count}</td>
                    </tr>
                  ))}
                  {data.materialization.length === 0 ? <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-400">No sync events yet.</td></tr> : null}
                </tbody>
              </table>
            </div>
            <div className="overflow-hidden rounded-md border border-gray-100">
              <table className="min-w-full divide-y divide-gray-100 text-sm">
                <thead className="bg-gray-50"><tr>{["Event", "Entity", "Status", "Materialized"].map((head) => <th key={head} className="px-3 py-2 text-left font-medium text-gray-600">{head}</th>)}</tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {data.recent_events.map((event) => (
                    <tr key={event.event_id}>
                      <td className="px-3 py-2 font-mono text-xs text-gray-600">{event.processed_at || event.event_id.slice(0, 8)}</td>
                      <td className="px-3 py-2">{event.trace_url ? <Link className="text-blue-700 hover:underline" href={event.trace_url}>{event.entity_type}</Link> : event.entity_type}</td>
                      <td className="px-3 py-2">{event.status || "-"}</td>
                      <td className="px-3 py-2">{event.materialized === null || event.materialized === undefined ? "n/a" : event.materialized ? "yes" : "no"}</td>
                    </tr>
                  ))}
                  {data.recent_events.length === 0 ? <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-400">No recent sync events.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return <div className="rounded-md bg-gray-50 px-3 py-2"><p className="text-xs text-gray-500">{label}</p><p className="text-xl font-bold text-gray-900">{value}</p></div>;
}
