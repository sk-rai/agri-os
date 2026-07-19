"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, companyApi, type CompanyDiscoveryCandidateDto } from "@/lib/api";

const SOURCES = ["", "PUBLIC_WEB", "BULK_IMPORT", "GOVERNMENT_REGISTRY", "PARTNER_DIRECTORY", "CLIENT_PROVIDED", "OTHER"];
const STATUSES = ["", "PENDING_REVIEW", "APPROVED", "REJECTED", "DUPLICATE", "MERGED", "STALE"];
const COMPANY_TYPES = ["FPO", "SEED_COMPANY", "FERTILIZER_COMPANY", "PESTICIDE_COMPANY", "MACHINERY_COMPANY", "INPUT_COMPANY", "COOPERATIVE", "NGO", "GOVERNMENT", "INSURER", "PROCESSOR", "BUYER", "TRADER", "WAREHOUSE", "FINANCIAL_INSTITUTION", "AGRI_TECH", "ENTERPRISE", "OTHER"];

function parseJsonObject(label: string, value: string) {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${label} must be a JSON object.`);
  return parsed as Record<string, unknown>;
}

function parseJsonArray(label: string, value: string) {
  if (!value.trim()) return [];
  const parsed = JSON.parse(value);
  if (!Array.isArray(parsed)) throw new Error(`${label} must be a JSON array.`);
  return parsed as Array<Record<string, unknown>>;
}

function parseCropFocus(value: string) {
  return value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);
}

export default function CompanyDiscoveryPage() {
  const [reviewStatus, setReviewStatus] = useState("PENDING_REVIEW");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<CompanyDiscoveryCandidateDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [candidateName, setCandidateName] = useState("");
  const [companyType, setCompanyType] = useState("FPO");
  const [candidateSource, setCandidateSource] = useState("PUBLIC_WEB");
  const [confidenceScore, setConfidenceScore] = useState("0.75");
  const [cropFocus, setCropFocus] = useState("");
  const [sourceReferences, setSourceReferences] = useState("[]");
  const [discoveredProfile, setDiscoveredProfile] = useState("{}");
  const [operatingGeography, setOperatingGeography] = useState("{}");
  const [duplicateKeys, setDuplicateKeys] = useState("{}");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const response = await companyApi.companyDiscoveryCandidates({
        reviewStatus: reviewStatus || undefined,
        source: source || undefined,
        q: search || undefined,
        limit: 100,
      });
      setItems(response.candidates || []);
      setMessage(`${response.count} candidate(s) loaded.`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Failed to load company discovery candidates.");
    } finally {
      setLoading(false);
    }
  }, [reviewStatus, source, search]);

  async function createCandidate() {
    setLoading(true);
    setMessage("");
    try {
      await companyApi.createCompanyDiscoveryCandidate({
        candidate_name: candidateName,
        company_type: companyType,
        source: candidateSource,
        confidence_score: confidenceScore ? Number(confidenceScore) : null,
        crop_focus: parseCropFocus(cropFocus),
        source_references: parseJsonArray("Source references", sourceReferences),
        discovered_profile: parseJsonObject("Discovered profile", discoveredProfile),
        operating_geography: parseJsonObject("Operating geography", operatingGeography),
        duplicate_keys: parseJsonObject("Duplicate keys", duplicateKeys),
      });
      setCandidateName("");
      setMessage("Candidate created.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to create candidate.");
    } finally {
      setLoading(false);
    }
  }

  async function applyCandidate(candidate: CompanyDiscoveryCandidateDto) {
    const tenantId = typeof window === "undefined" ? "default" : localStorage.getItem("agrios_tenant_id") || "default";
    const reason = window.prompt("Reason for applying this candidate to the live company profile", "Apply discovered company candidate") || "Apply discovered company candidate";
    setLoading(true);
    setMessage("");
    try {
      await companyApi.applyCompanyDiscoveryCandidate(candidate.id, { tenant_id: tenantId, reason, verification_status: "CLAIMED" });
      setMessage("Candidate applied to live company profile.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to apply candidate.");
    } finally {
      setLoading(false);
    }
  }

  async function reviewCandidate(candidate: CompanyDiscoveryCandidateDto, nextStatus: string) {
    const notes = window.prompt(`Review notes for ${nextStatus}`, candidate.review_notes || "");
    if (notes === null) return;
    setLoading(true);
    setMessage("");
    try {
      await companyApi.reviewCompanyDiscoveryCandidate(candidate.id, {
        review_status: nextStatus,
        matched_tenant_id: nextStatus === "APPROVED" ? candidate.matched_tenant_id : candidate.matched_tenant_id || null,
        matched_company_profile_id: candidate.matched_company_profile_id || null,
        review_notes: notes || `${nextStatus} from admin discovery queue`,
        metadata: candidate.metadata || {},
      });
      setMessage(`Candidate marked ${nextStatus}.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to review candidate.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="space-y-6 p-6">
      <div className="rounded-lg border bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-green-700">Organization</p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">Company Discovery</h1>
        <p className="mt-1 max-w-3xl text-sm text-gray-600">
          Staging queue for future public-web, government-registry, partner-directory, or bulk-import company prepopulation.
          Records stay here until reviewed, approved, rejected, merged, or marked duplicate.
        </p>
        {message ? <div className="mt-4 rounded border bg-gray-50 p-3 text-sm text-gray-700">{message}</div> : null}
      </div>

      <section className="grid gap-3 rounded-lg border bg-white p-4 shadow-sm md:grid-cols-5">
        <Select label="Review status" value={reviewStatus} onChange={setReviewStatus} options={STATUSES} />
        <Select label="Source" value={source} onChange={setSource} options={SOURCES} />
        <Input label="Search" value={search} onChange={setSearch} />
        <div className="flex items-end">
          <button type="button" onClick={() => void load()} disabled={loading} className="w-full rounded bg-slate-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
            {loading ? "Loading..." : "Apply filters"}
          </button>
        </div>
        <div className="flex items-end">
          <div className="w-full rounded border bg-gray-50 p-2 text-sm text-gray-700">{items.length} shown</div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-900">Create manual candidate</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <Input label="Candidate name" value={candidateName} onChange={setCandidateName} />
          <Select label="Company type" value={companyType} onChange={setCompanyType} options={COMPANY_TYPES} />
          <Select label="Source" value={candidateSource} onChange={setCandidateSource} options={SOURCES.filter(Boolean)} />
          <Input label="Confidence score 0-1" value={confidenceScore} onChange={setConfidenceScore} />
          <Input label="Crop focus comma-separated" value={cropFocus} onChange={setCropFocus} />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Textarea label="Source references JSON array" value={sourceReferences} onChange={setSourceReferences} />
          <Textarea label="Discovered profile JSON" value={discoveredProfile} onChange={setDiscoveredProfile} />
          <Textarea label="Operating geography JSON" value={operatingGeography} onChange={setOperatingGeography} />
          <Textarea label="Duplicate keys JSON" value={duplicateKeys} onChange={setDuplicateKeys} />
        </div>
        <button type="button" onClick={() => void createCandidate()} disabled={loading || !candidateName.trim()} className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          Create candidate
        </button>
      </section>

      <section className="space-y-3 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-900">Review queue</h2>
        <div className="space-y-3">
          {items.map((item) => <div key={item.id} className="rounded border p-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-gray-900">{item.candidate_name}</div>
                <div className="mt-1 text-xs text-gray-500">{item.company_type || "-"} · {item.source} · {item.review_status}</div>
                <div className="mt-1 text-xs text-gray-500">Confidence: {item.confidence_score ?? "-"} · Created: {item.created_at || "-"}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void applyCandidate(item)} className="rounded bg-green-700 px-2 py-1 text-xs font-semibold text-white">Apply to profile</button>
                {["APPROVED", "REJECTED", "DUPLICATE", "MERGED", "STALE"].map((status) => (
                  <button key={status} type="button" onClick={() => void reviewCandidate(item, status)} className="rounded border px-2 py-1 text-xs text-gray-700 hover:bg-gray-50">{status}</button>
                ))}
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              <pre className="max-h-40 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(item.operating_geography || {}, null, 2)}</pre>
              <pre className="max-h-40 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(item.discovered_profile || {}, null, 2)}</pre>
              <pre className="max-h-40 overflow-auto rounded bg-gray-950 p-2 text-[10px] text-gray-100">{JSON.stringify(item.source_references || [], null, 2)}</pre>
            </div>
            {item.review_notes ? <div className="mt-2 text-xs text-amber-700">Notes: {item.review_notes}</div> : null}
          </div>)}
          {items.length === 0 ? <div className="rounded border p-6 text-center text-sm text-gray-400">No company discovery candidates found.</div> : null}
        </div>
      </section>
    </main>
  );
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{options.map((item) => <option key={item || "ALL"} value={item}>{item || "ALL"}</option>)}</select></label>;
}

function Textarea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<textarea value={value} onChange={(event) => onChange(event.target.value)} rows={6} className="mt-1 w-full rounded border p-2 font-mono text-xs text-gray-900" /></label>;
}
