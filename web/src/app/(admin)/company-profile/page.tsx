"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, companyApi, type CompanyProfileAuditEventDto, type CompanyProfileDto } from "@/lib/api";

const COMPANY_TYPES = ["ENTERPRISE", "FPO", "COOPERATIVE", "NGO", "GOVERNMENT", "INSURER", "PROCESSOR", "INPUT_COMPANY", "SEED_COMPANY", "FERTILIZER_COMPANY", "PESTICIDE_COMPANY", "MACHINERY_COMPANY", "BUYER", "TRADER", "WAREHOUSE", "FINANCIAL_INSTITUTION", "AGRI_TECH", "OTHER"];
const PROFILE_SOURCES = ["MANUAL", "PUBLIC_WEB", "BULK_IMPORT", "CLIENT_PROVIDED", "GOVERNMENT_REGISTRY", "PARTNER_DIRECTORY", "OTHER"];
const VERIFICATION_STATUSES = ["UNVERIFIED", "CLAIMED", "VERIFIED", "REJECTED", "STALE"];

function getTenantId() {
  if (typeof window === "undefined") return "default";
  return localStorage.getItem("agrios_tenant_id") || "default";
}

function jsonText(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseJsonObject(label: string, value: string) {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function parseCropFocus(value: string) {
  return value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);
}

function parseJsonArray(label: string, value: string) {
  if (!value.trim()) return [];
  const parsed = JSON.parse(value);
  if (!Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON array.`);
  }
  return parsed as Array<Record<string, unknown>>;
}

export default function CompanyProfilePage() {
  const [tenantId, setTenantId] = useState("default");
  const [profile, setProfile] = useState<CompanyProfileDto>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [legalName, setLegalName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [companyType, setCompanyType] = useState("ENTERPRISE");
  const [profileSource, setProfileSource] = useState("MANUAL");
  const [verificationStatus, setVerificationStatus] = useState("UNVERIFIED");
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [gstin, setGstin] = useState("");
  const [pan, setPan] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [supportEmail, setSupportEmail] = useState("");
  const [supportPhone, setSupportPhone] = useState("");
  const [cropFocus, setCropFocus] = useState("");
  const [sourceReferences, setSourceReferences] = useState("[]");
  const [headOffice, setHeadOffice] = useState("{}");
  const [operatingGeography, setOperatingGeography] = useState("{}");
  const [serviceModel, setServiceModel] = useState("{}");
  const [config, setConfig] = useState("{}");
  const [metadata, setMetadata] = useState("{}");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [auditEvents, setAuditEvents] = useState<CompanyProfileAuditEventDto[]>([]);

  const configured = useMemo(() => Boolean(profile.id), [profile.id]);

  function loadIntoForm(next: CompanyProfileDto) {
    setProfile(next || {});
    setLegalName(next?.legal_name || "");
    setDisplayName(next?.display_name || "");
    setCompanyType(next?.company_type || "ENTERPRISE");
    setProfileSource(next?.profile_source || "MANUAL");
    setVerificationStatus(next?.verification_status || "UNVERIFIED");
    setRegistrationNumber(next?.registration_number || "");
    setGstin(next?.gstin || "");
    setPan(next?.pan || "");
    setWebsiteUrl(next?.website_url || "");
    setSupportEmail(next?.support_email || "");
    setSupportPhone(next?.support_phone || "");
    setCropFocus((next?.crop_focus || []).join(", "));
    setSourceReferences(JSON.stringify(next?.source_references || [], null, 2));
    setHeadOffice(jsonText(next?.head_office));
    setOperatingGeography(jsonText(next?.operating_geography));
    setServiceModel(jsonText(next?.service_model));
    setConfig(jsonText(next?.config));
    setMetadata(jsonText(next?.metadata));
  }

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const activeTenant = getTenantId();
      setTenantId(activeTenant);
      const response = await companyApi.companyProfile(activeTenant);
      loadIntoForm(response.profile || {});
      const audit = await companyApi.companyProfileAudit(activeTenant, { limit: 20 });
      setAuditEvents(audit.events || []);
      setMessage(response.message || "Company profile loaded.");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Failed to load company profile.");
    } finally {
      setLoading(false);
    }
  }, []);

  async function saveProfile() {
    setSaving(true);
    setMessage("");
    try {
      const body = {
        legal_name: legalName || null,
        display_name: displayName || null,
        company_type: companyType,
        profile_source: profileSource,
        verification_status: verificationStatus,
        source_references: parseJsonArray("Source references", sourceReferences),
        registration_number: registrationNumber || null,
        gstin: gstin || null,
        pan: pan || null,
        website_url: websiteUrl || null,
        support_email: supportEmail || null,
        support_phone: supportPhone || null,
        crop_focus: parseCropFocus(cropFocus),
        head_office: parseJsonObject("Head office", headOffice),
        operating_geography: parseJsonObject("Operating geography", operatingGeography),
        service_model: parseJsonObject("Service model", serviceModel),
        config: parseJsonObject("Config", config),
        metadata: parseJsonObject("Metadata", metadata),
        reason: reason || "Company profile admin update",
      };
      const response = await companyApi.upsertCompanyProfile(tenantId, body);
      loadIntoForm(response.profile || {});
      setMessage(response.message || "Company profile saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save company profile.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  return (
    <main className="space-y-6 p-6">
      <div className="rounded-lg border bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-green-700">Organization</p>
            <h1 className="mt-1 text-2xl font-bold text-gray-900">Company Profile</h1>
            <p className="mt-1 max-w-3xl text-sm text-gray-600">
              Backend-only tenant profile for the company, FPO, NGO, insurer, processor, or agri-tech customer using Agri-OS.
              Android MVP does not own this data.
            </p>
          </div>
          <button type="button" onClick={() => void loadProfile()} disabled={loading} className="rounded bg-slate-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
            {loading ? "Loading..." : "Reload"}
          </button>
        </div>
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
          <Stat label="Tenant" value={tenantId} />
          <Stat label="Configured" value={configured ? "Yes" : "No"} />
          <Stat label="Last updated" value={profile.updated_at || "-"} />
        </div>
        {message ? <div className="mt-4 rounded border bg-gray-50 p-3 text-sm text-gray-700">{message}</div> : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Identity">
          <Input label="Legal name" value={legalName} onChange={setLegalName} />
          <Input label="Display name" value={displayName} onChange={setDisplayName} />
          <label className="text-xs text-gray-500">Company type
            <select value={companyType} onChange={(event) => setCompanyType(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              {COMPANY_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-500">Profile source
            <select value={profileSource} onChange={(event) => setProfileSource(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              {PROFILE_SOURCES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-500">Verification status
            <select value={verificationStatus} onChange={(event) => setVerificationStatus(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
              {VERIFICATION_STATUSES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <Input label="Registration number" value={registrationNumber} onChange={setRegistrationNumber} />
          <Input label="GSTIN" value={gstin} onChange={setGstin} />
          <Input label="PAN" value={pan} onChange={setPan} />
        </Section>

        <Section title="Support and focus">
          <Input label="Website URL" value={websiteUrl} onChange={setWebsiteUrl} />
          <Input label="Support email" value={supportEmail} onChange={setSupportEmail} />
          <Input label="Support phone" value={supportPhone} onChange={setSupportPhone} />
          <Input label="Crop focus, comma-separated" value={cropFocus} onChange={setCropFocus} />
          <Textarea label="Source references JSON array" value={sourceReferences} onChange={setSourceReferences} />
          <Textarea label="Head office JSON" value={headOffice} onChange={setHeadOffice} />
        </Section>

        <Section title="Operating model">
          <Textarea label="Operating geography JSON" value={operatingGeography} onChange={setOperatingGeography} />
          <Textarea label="Service model JSON" value={serviceModel} onChange={setServiceModel} />
        </Section>

        <Section title="Backend config">
          <Textarea label="Config JSON" value={config} onChange={setConfig} />
          <Textarea label="Metadata JSON" value={metadata} onChange={setMetadata} />
          <Input label="Reason for change" value={reason} onChange={setReason} />
        </Section>
      </div>

      <div className="flex justify-end">
        <button type="button" onClick={() => void saveProfile()} disabled={saving} className="rounded bg-green-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {saving ? "Saving..." : "Save company profile"}
        </button>
      </div>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-gray-900">Audit history</h2>
          <button type="button" onClick={() => void loadProfile()} className="rounded border px-3 py-1 text-xs text-gray-700">Refresh</button>
        </div>
        <div className="mt-3 divide-y rounded border">
          {auditEvents.map((event) => <div key={event.id} className="p-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-gray-900">{event.action}</span>
              <span className="text-gray-400">{event.created_at || "-"}</span>
            </div>
            <div className="mt-1 text-gray-600">Source: {event.source || "-"} · Actor: {event.actor_id || "-"}</div>
            <div className="mt-1 text-gray-600">Fields: {(event.patched_fields || []).join(", ") || "-"}</div>
            {event.reason ? <div className="mt-1 text-amber-700">Reason: {event.reason}</div> : null}
          </div>)}
          {auditEvents.length === 0 ? <div className="p-4 text-center text-xs text-gray-400">No audit events yet.</div> : null}
        </div>
      </section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="space-y-3 rounded-lg border bg-white p-4 shadow-sm"><h2 className="text-sm font-semibold text-gray-900">{title}</h2>{children}</section>;
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded border bg-gray-50 p-3"><div className="text-xs text-gray-500">{label}</div><div className="mt-1 break-all font-medium text-gray-900">{value}</div></div>;
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}

function Textarea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<textarea value={value} onChange={(event) => onChange(event.target.value)} rows={7} className="mt-1 w-full rounded border p-2 font-mono text-xs text-gray-900" /></label>;
}
