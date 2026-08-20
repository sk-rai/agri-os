"use client";

/* eslint-disable @next/next/no-img-element */

import { useMemo, useState } from "react";

type TabId = "overview" | "product" | "graph" | "operations" | "geography" | "roadmap";

const tabs: Array<{ id: TabId; label: string; eyebrow: string }> = [
  { id: "overview", label: "Overview", eyebrow: "Start here" },
  { id: "product", label: "Product", eyebrow: "Six pillars" },
  { id: "graph", label: "Evidence graph", eyebrow: "Relationships" },
  { id: "operations", label: "Operations", eyebrow: "Field flow" },
  { id: "geography", label: "Geography", eyebrow: "PIN + DigiPin" },
  { id: "roadmap", label: "Roadmap", eyebrow: "Boundaries" },
];

const pillars = [
  {
    title: "Capture",
    icon: "/landing-assets/product-pillar-capture.svg",
    body: "Farmer profiles, parcels, crop cycles, activities, media, and field events from Android.",
  },
  {
    title: "Coordinate",
    icon: "/landing-assets/product-pillar-coordinate.svg",
    body: "FPO/project enrollment, farmer cohorts, field-agent workflows, project trace, and admin visibility.",
  },
  {
    title: "Sync",
    icon: "/landing-assets/product-pillar-sync.svg",
    body: "Offline queue persistence, replay ordering, idempotency, conflict recovery, and backlog draining.",
  },
  {
    title: "Advise",
    icon: "/landing-assets/product-pillar-advise.svg",
    body: "Targeted advisories with media, language fallback, delivery analytics, and read/ack audit.",
  },
  {
    title: "Govern",
    icon: "/landing-assets/product-pillar-govern.svg",
    body: "Backend-owned contracts, labels, options, localization overrides, land intelligence, and audit trails.",
  },
  {
    title: "Extend",
    icon: "/landing-assets/product-pillar-extend.svg",
    body: "Roadmap foundation for insurance, subsidy, credit, weather, soil, satellite, and risk review.",
    roadmap: true,
  },
];

const proofBadges = [
  "Android MVP closed",
  "Offline sync verified",
  "FPO/project workflows verified",
  "Backend-owned advisories",
  "Localization fallback verified",
  "DigiPin backend materialization",
];

const demoSlots = [
  ["Android onboarding", "Android-only", "Farmer/profile/parcel capture and backend-owned labels."],
  ["FPO admin workflow", "Web-only", "Project cohorts, farmer search, and traceability."],
  ["Offline sync resilience", "Android-only", "Queue persistence, replay, conflicts, and backlog draining."],
  ["Broadcast analytics", "Web-only", "Delivery/read/ack lifecycle and admin drilldown."],
  ["Field event to advisory", "Mixed", "Android field event, backend advisory, web analytics."],
  ["Localization + land intelligence", "Mixed", "Backend override in admin, Android rendering proof."],
];

function Badge({
  children,
  tone = "blue",
}: {
  children: React.ReactNode;
  tone?: "blue" | "green" | "purple" | "amber" | "gray";
}) {
  const toneClass =
    tone === "green"
      ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-100"
      : tone === "purple"
        ? "border-violet-400/40 bg-violet-400/10 text-violet-100"
        : tone === "amber"
          ? "border-amber-400/50 bg-amber-400/10 text-amber-100"
          : tone === "gray"
            ? "border-slate-400/40 bg-slate-400/10 text-slate-100"
            : "border-sky-400/40 bg-sky-400/10 text-sky-100";

  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${toneClass}`}>{children}</span>;
}

function SectionHeader({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="mb-8 max-w-4xl">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.28em] text-sky-300">{eyebrow}</p>
      <h2 className="text-3xl font-bold tracking-tight text-white md:text-5xl">{title}</h2>
      <p className="mt-4 text-base leading-7 text-slate-300 md:text-lg">{body}</p>
    </div>
  );
}

function VisualCard({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-slate-950/70 shadow-2xl shadow-sky-950/30">
      <img src={src} alt={alt} className="h-auto w-full" />
    </div>
  );
}

function TabButton({
  id,
  label,
  eyebrow,
  active,
  onClick,
}: {
  id: string;
  label: string;
  eyebrow: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-w-[10rem] rounded-2xl border px-4 py-3 text-left transition ${
        active
          ? "border-sky-300 bg-sky-300 text-slate-950 shadow-lg shadow-sky-500/20"
          : "border-white/10 bg-slate-950/70 text-slate-300 hover:border-sky-300/50 hover:bg-white/10 hover:text-white"
      }`}
      aria-pressed={active}
      aria-controls={`agrifabric-panel-${id}`}
    >
      <span className={`block text-[10px] font-black uppercase tracking-[0.22em] ${active ? "text-slate-800" : "text-sky-300"}`}>
        {eyebrow}
      </span>
      <span className="mt-1 block text-sm font-black">{label}</span>
    </button>
  );
}

function OverviewTab({ setActiveTab }: { setActiveTab: (tab: TabId) => void }) {
  return (
    <div id="agrifabric-panel-overview" className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
      <div>
        <div className="mb-5 flex flex-wrap gap-2">
          <Badge>Verified MVP</Badge>
          <Badge tone="green">Offline-first</Badge>
          <Badge tone="purple">Backend-owned</Badge>
        </div>
        <h1 className="text-5xl font-black leading-[1.02] tracking-tight text-white md:text-7xl">
          Offline-first field intelligence for agriculture programs.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
          Capture farmer, parcel, crop, activity, media, and field-event data in low-connectivity environments, then sync safely with backend audit, conflict recovery, project traceability, and targeted advisories.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setActiveTab("operations")}
            className="rounded-full bg-sky-400 px-6 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-sky-500/20 hover:bg-sky-300"
          >
            Explore demo flows
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("product")}
            className="rounded-full border border-white/15 px-6 py-3 text-sm font-bold text-white hover:bg-white/10"
          >
            Review capabilities
          </button>
        </div>
        <div className="mt-8 flex flex-wrap gap-2">
          {proofBadges.map((badge) => (
            <Badge key={badge}>{badge}</Badge>
          ))}
        </div>
      </div>
      <VisualCard src="/landing-assets/hero-composite-compact.svg" alt="AgriFabric hero composite" />
    </div>
  );
}

function ProductTab() {
  return (
    <div id="agrifabric-panel-product">
      <SectionHeader
        eyebrow="Product pillars"
        title="Six verbs, one operating fabric."
        body="AgriFabric connects Android field capture, project operations, offline sync, advisories, governance, and future intelligence without pretending the roadmap is already live."
      />
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {pillars.map((pillar) => (
          <article key={pillar.title} className="rounded-[2rem] border border-white/10 bg-slate-950/60 p-6 shadow-xl shadow-slate-950/20">
            <div className="mb-5 flex items-center gap-4">
              <img src={pillar.icon} alt="" className="h-16 w-16 rounded-2xl" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-2xl font-bold text-white">{pillar.title}</h3>
                  {pillar.roadmap ? <Badge tone="amber">Roadmap</Badge> : null}
                </div>
              </div>
            </div>
            <p className="text-sm leading-6 text-slate-300">{pillar.body}</p>
          </article>
        ))}
      </div>
      <div className="mt-8">
        <VisualCard src="/landing-assets/product-pillars.svg" alt="AgriFabric six product pillars" />
      </div>
    </div>
  );
}

function GraphTab() {
  return (
    <div id="agrifabric-panel-graph" className="grid gap-8 lg:grid-cols-[0.78fr_1.22fr] lg:items-center">
      <div>
        <SectionHeader
          eyebrow="Relationship graph"
          title="Every field interaction becomes a typed relationship."
          body="Farmers, agents, companies, projects, parcels, crop cycles, media, advisories, sync events, and audit trails form the graph underneath the platform."
        />
        <div className="space-y-4 rounded-[2rem] border border-white/10 bg-slate-950/60 p-6 text-sm leading-7 text-slate-300">
          <p>Implemented traceability supports project operations today.</p>
          <p>Agent benchmarking, assignment planning, risk review, and claim evidence bundles are roadmap analytics built on the same evidence graph.</p>
          <Badge tone="amber">Roadmap analytics are bounded</Badge>
        </div>
      </div>
      <VisualCard src="/landing-assets/relationship-graph-overview.svg" alt="Relationship graph overview" />
    </div>
  );
}

function OperationsTab() {
  return (
    <div id="agrifabric-panel-operations">
      <SectionHeader
        eyebrow="Field operations"
        title="From field capture to governed operations."
        body="Android captures and displays. Backend owns validation, labels, workflow rules, targeting, conflict interpretation, summaries, and audit history."
      />
      <VisualCard src="/landing-assets/field-evidence-pipeline.svg" alt="Field evidence pipeline" />
      <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {demoSlots.map(([title, mode, body]) => (
          <div key={title} className="rounded-3xl border border-white/10 bg-slate-950/60 p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="font-bold text-white">{title}</p>
              <Badge tone={mode === "Mixed" ? "purple" : mode === "Web-only" ? "green" : "blue"}>{mode}</Badge>
            </div>
            <p className="text-sm leading-6 text-slate-400">{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function GeographyTab() {
  return (
    <div id="agrifabric-panel-geography">
      <SectionHeader
        eyebrow="Geography and DigiPin"
        title="PIN is context. GPS and DigiPin are precision evidence."
        body="AgriFabric keeps administrative geography, postal context, parcel GPS/polygon evidence, backend-generated DigiPin, and land-intelligence summaries conceptually separate."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <VisualCard src="/landing-assets/geography-digipin-overview.svg" alt="Geography and DigiPin overview" />
        <VisualCard src="/landing-assets/geography-global-extension-layer.svg" alt="Global geography extension roadmap" />
      </div>
      <div className="mt-6">
        <VisualCard src="/landing-assets/geography-digipin-layered-model.svg" alt="Layered geography model" />
      </div>
    </div>
  );
}

function RoadmapTab() {
  return (
    <div id="agrifabric-panel-roadmap">
      <SectionHeader
        eyebrow="Roadmap boundaries"
        title="Evidence foundation today. Review intelligence tomorrow."
        body="Insurance, subsidy, credit, NDVI, live weather/soil, and global geography are positioned as future or approval-gated modules, not current automated decisioning."
      />
      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-start">
        <VisualCard src="/landing-assets/insurance-risk-roadmap.svg" alt="Insurance and subsidy integrity roadmap" />
        <div className="space-y-4 rounded-[2rem] border border-amber-300/30 bg-amber-400/10 p-6">
          <Badge tone="amber">Claim boundary</Badge>
          <h3 className="text-2xl font-bold text-white">Review-assistive, not auto-decisioning.</h3>
          <p className="text-sm leading-7 text-amber-50/85">
            AgriFabric can assemble trusted field evidence and flag inconsistencies for human review. It should not be positioned as a live fraud score, automated claim approval/rejection engine, or live NDVI/provider system until those modules are separately implemented and governed.
          </p>
          <VisualCard src="/landing-assets/insurance-risk-roadmap-compact.svg" alt="Compact insurance roadmap" />
        </div>
      </div>
    </div>
  );
}

function ActivePanel({ activeTab, setActiveTab }: { activeTab: TabId; setActiveTab: (tab: TabId) => void }) {
  switch (activeTab) {
    case "overview":
      return <OverviewTab setActiveTab={setActiveTab} />;
    case "product":
      return <ProductTab />;
    case "graph":
      return <GraphTab />;
    case "operations":
      return <OperationsTab />;
    case "geography":
      return <GeographyTab />;
    case "roadmap":
      return <RoadmapTab />;
    default:
      return <OverviewTab setActiveTab={setActiveTab} />;
  }
}

export function AgriFabricLandingClient() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const activeMeta = useMemo(() => tabs.find((tab) => tab.id === activeTab) ?? tabs[0], [activeTab]);

  return (
    <main className="agrifabric-landing min-h-screen bg-[#061826] text-white">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -right-36 -top-44 h-[34rem] w-[34rem] rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="absolute -bottom-44 -left-32 h-[30rem] w-[30rem] rounded-full bg-sky-500/10 blur-3xl" />
      </div>

      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-6">
        <button type="button" onClick={() => setActiveTab("overview")} className="text-xl font-black tracking-tight text-white">
          AgriFabric
        </button>
        <nav className="hidden items-center gap-6 text-sm text-slate-300 md:flex">
          {tabs.slice(1).map((tab) => (
            <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} className="hover:text-white">
              {tab.label}
            </button>
          ))}
          <a href="/login" className="rounded-full bg-white px-4 py-2 font-semibold text-slate-950 hover:bg-sky-100">
            Admin app
          </a>
        </nav>
      </header>

      <section className="relative z-10 mx-auto max-w-7xl px-6 pb-8 pt-4">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.28em] text-sky-300">{activeMeta.eyebrow}</p>
            <p className="mt-1 text-sm text-slate-400">Use tabs to keep the platform story digestible.</p>
          </div>
          <Badge tone={activeTab === "roadmap" ? "amber" : "green"}>
            {activeTab === "roadmap" ? "Roadmap bounded" : "Verified foundation"}
          </Badge>
        </div>

        <div className="mb-8 flex gap-3 overflow-x-auto rounded-[2rem] border border-white/10 bg-slate-950/50 p-3">
          {tabs.map((tab) => (
            <TabButton
              key={tab.id}
              id={tab.id}
              label={tab.label}
              eyebrow={tab.eyebrow}
              active={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
            />
          ))}
        </div>

        <div className="rounded-[2rem] border border-white/10 bg-white/[0.03] p-4 shadow-2xl shadow-slate-950/30 md:p-6">
          <ActivePanel activeTab={activeTab} setActiveTab={setActiveTab} />
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-5xl px-6 py-16 text-center">
        <Badge tone="green">Pilot-ready deterministic demo</Badge>
        <h2 className="mt-5 text-4xl font-black tracking-tight text-white md:text-6xl">
          Ready to pilot a field evidence fabric?
        </h2>
        <p className="mx-auto mt-5 max-w-3xl text-lg leading-8 text-slate-300">
          Use AgriFabric to demonstrate offline field capture, backend-governed workflows, FPO/project traceability, targeted advisories, geography precision, and audit-backed operations.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <a href="/login" className="rounded-full bg-white px-6 py-3 text-sm font-bold text-slate-950 hover:bg-sky-100">
            Open admin app
          </a>
          <button
            type="button"
            onClick={() => setActiveTab("operations")}
            className="rounded-full border border-white/15 px-6 py-3 text-sm font-bold text-white hover:bg-white/10"
          >
            Review demo slots
          </button>
        </div>
      </section>

      <footer className="relative z-10 border-t border-white/10 px-6 py-8 text-center text-sm text-slate-500">
        AgriFabric landing draft. Roadmap modules are explicitly claim-bounded.
      </footer>
    </main>
  );
}
