"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { appConfigApi, type AppBootstrapResponse, type EffectiveAppConfigResponse, type FormFieldContract, type FormSchemaContract, type ProfileFormContractSummary, type ProjectAppConfigAuditResponse, type ProfileFormValidationResponse, type ProfileOptionSetsResponse } from "@/lib/api";

const PROFILE_FORM_ORDER = ["farmer_registration", "parcel_registration", "soil_profile"];

type EffectiveContext = AppBootstrapResponse | EffectiveAppConfigResponse;

function label(value?: Record<string, string> | null) {
  return value?.en || Object.values(value || {})[0] || "-";
}

function fieldTypeTone(type: string) {
  if (type.startsWith("GPS")) return "bg-blue-50 text-blue-700";
  if (type === "PHOTO") return "bg-purple-50 text-purple-700";
  if (type.includes("select") || type === "dropdown") return "bg-green-50 text-green-700";
  if (type === "number" || type === "date") return "bg-amber-50 text-amber-700";
  return "bg-gray-100 text-gray-700";
}

export default function ProfileFormsPage() {
  const [projectIdInput, setProjectIdInput] = useState("");
  const [projectId, setProjectId] = useState("");
  const [context, setContext] = useState<EffectiveContext | null>(null);
  const [schemas, setSchemas] = useState<Record<string, FormSchemaContract>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updateReason, setUpdateReason] = useState("Enable backend-driven profile forms for project testing");
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);
  const [audit, setAudit] = useState<ProjectAppConfigAuditResponse | null>(null);
  const [validation, setValidation] = useState<ProfileFormValidationResponse | null>(null);
  const [optionSets, setOptionSets] = useState<ProfileOptionSetsResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const nextContext = projectId ? await appConfigApi.effectiveProjectConfig(projectId) : await appConfigApi.bootstrap();
        const profileForms = Object.values(nextContext.profile_forms || {});
        const loadedSchemas = await Promise.all(profileForms.map((form) => appConfigApi.formSchema(form.form_id)));
        const auditPayload = projectId ? await appConfigApi.projectConfigAudit(projectId, 10) : null;
        const validationPayload = await appConfigApi.profileFormValidation(projectId || undefined);
        const optionSetPayload = await appConfigApi.profileOptionSets(projectId || undefined);
        if (!cancelled) {
          setContext(nextContext);
          setSchemas(Object.fromEntries(loadedSchemas.map((schema) => [schema.form_id, schema])));
          setAudit(auditPayload);
          setValidation(validationPayload);
      setOptionSets(optionSetPayload);
          setOptionSets(optionSetPayload);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load profile form contracts");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [projectId]);

  const orderedForms = useMemo(() => {
    const profileForms = context?.profile_forms || {};
    return Object.values(profileForms).sort((a, b) => {
      const ai = PROFILE_FORM_ORDER.indexOf(a.form_id);
      const bi = PROFILE_FORM_ORDER.indexOf(b.form_id);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
  }, [context]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setProjectId(projectIdInput.trim());
  }

  function clearProject() {
    setProjectIdInput("");
    setProjectId("");
    setUpdateMessage(null);
    setAudit(null);
    setValidation(null);
    setOptionSets(null);
  }

  async function toggleProfileFlag(flag: string, enabled: boolean) {
    if (!projectId) return;
    setUpdateBusy(true);
    setError(null);
    setUpdateMessage(null);
    try {
      const updated = await appConfigApi.updateProjectConfig(projectId, { feature_flags: { [flag]: enabled } }, updateReason || "Update project profile form feature flag");
      const auditPayload = await appConfigApi.projectConfigAudit(projectId, 10);
      const validationPayload = await appConfigApi.profileFormValidation(projectId);
      const optionSetPayload = await appConfigApi.profileOptionSets(projectId);
      setContext(updated);
      setAudit(auditPayload);
      setValidation(validationPayload);
      setOptionSets(optionSetPayload);
      setUpdateMessage(`${flag} ${enabled ? "enabled" : "disabled"} for this project.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update project profile form flag");
    } finally {
      setUpdateBusy(false);
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Profile Forms</h1>
      <p className="mt-1 text-sm text-gray-500">Read-only view of backend-driven farmer, parcel, and soil profile schemas that Android can render.</p>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-[1fr_auto_auto] md:items-end">
        <label className="text-xs text-gray-500">Project ID for effective config<input value={projectIdInput} onChange={(event) => setProjectIdInput(event.target.value)} placeholder="Optional project UUID" className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-5 py-2 text-sm font-medium text-white disabled:opacity-50">Inspect</button>
        <button type="button" onClick={clearProject} disabled={loading && !projectId} className="rounded border px-5 py-2 text-sm disabled:opacity-50">Tenant/default</button>
      </div>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading profile form contracts...</p> : null}

    {context && !loading ? <>
      <ContextPanel context={context} />
      <RuntimeConfigPanel context={context} />
      <ProfileFlagControls
        context={context}
        projectId={projectId}
        reason={updateReason}
        onReasonChange={setUpdateReason}
        onToggle={toggleProfileFlag}
        busy={updateBusy}
        message={updateMessage}
      />
      {validation ? <ProfileFormValidationPanel validation={validation} /> : null}
      {optionSets ? <ProfileOptionSetsPanel payload={optionSets} /> : null}
      {audit ? <ProjectConfigAuditPanel audit={audit} /> : null}
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {orderedForms.map((form) => <FormSummaryCard key={form.form_id} form={form} schema={schemas[form.form_id]} />)}
      </div>
      <div className="mt-6 space-y-5">
        {orderedForms.map((form) => schemas[form.form_id] ? <FormSchemaPanel key={form.form_id} summary={form} schema={schemas[form.form_id]} /> : null)}
      </div>
    </> : null}
  </div>;
}

function ContextPanel({ context }: { context: EffectiveContext }) {
  const isProjectContext = "section_sources" in context;
  const tenantName = context.tenant.name;
  const project = context.project;
  const sources = isProjectContext ? context.section_sources : null;
  return <section className="rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Effective render context</h2>
        <p className="mt-1 text-sm text-gray-500">{isProjectContext ? "Project-level config after default + tenant + project merge." : "Tenant/default bootstrap config used when no project is selected."}</p>
      </div>
      <span className="rounded bg-gray-100 px-3 py-1 text-xs text-gray-700">{context.schema_version}</span>
    </div>
    <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
      <Mini label="Tenant" value={tenantName} />
      <Mini label="Tenant ID" value={context.tenant.id} mono />
      <Mini label="Project" value={project?.name || "No project selected"} />
      <Mini label="Generated" value={context.generated_at} />
    </div>
    {sources ? <div className="mt-4 rounded bg-gray-50 p-3">
      <p className="text-xs font-semibold uppercase text-gray-400">Config section sources</p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {Object.entries(sources).map(([section, source]) => <span key={section} className="rounded bg-white px-2 py-1 text-gray-700">{section}: <b>{source}</b></span>)}
      </div>
    </div> : null}
  </section>;
}

function RuntimeConfigPanel({ context }: { context: EffectiveContext }) {
  const isProjectContext = "effective_config" in context;
  const effective = isProjectContext ? context.effective_config : context;
  const branding = (effective.branding || {}) as Record<string, unknown>;
  const localization = (effective.localization || {}) as Record<string, unknown>;
  const units = (effective.units || {}) as Record<string, unknown>;
  const selfService = (effective.self_service || {}) as Record<string, unknown>;
  const featureFlags = ((isProjectContext ? effective.feature_flags : context.feature_flags) || {}) as Record<string, boolean>;
  const enabledModules = ((effective.enabled_modules || []) as string[]);
  const sources = isProjectContext ? context.section_sources : null;
  const flags = Object.entries(featureFlags).sort(([a], [b]) => a.localeCompare(b));

  return <section className="mt-6 rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Runtime app configuration</h2>
        <p className="mt-1 text-sm text-gray-500">Read-only Android/web bootstrap view for white-labelling, locale, units, modules, and feature flags.</p>
      </div>
      <span className="rounded bg-blue-50 px-3 py-1 text-xs text-blue-700">{isProjectContext ? "Effective project config" : "Tenant/default bootstrap"}</span>
    </div>
    <div className="mt-4 grid gap-3 md:grid-cols-4">
      <Mini label="App name" value={textValue(branding.app_name)} />
      <Mini label="Primary color" value={textValue(branding.primary_color)} />
      <Mini label="Default language" value={textValue(localization.default_language)} />
      <Mini label="Country/timezone" value={[textValue(localization.country_code), textValue(localization.timezone)].filter((value) => value !== "-").join(" / ") || "-"} />
      <Mini label="Currency" value={textValue(units.currency)} />
      <Mini label="Area unit" value={textValue(units.default_area_unit)} />
      <Mini label="Self registration" value={selfService.allow_direct_farmer_registration === false ? "Disabled" : "Allowed"} />
      <Mini label="Project invite required" value={selfService.requires_project_invite ? "Yes" : "No"} />
    </div>
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <div className="rounded border p-4">
        <p className="text-xs font-semibold uppercase text-gray-400">Enabled modules</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {enabledModules.map((module) => <span key={module} className="rounded bg-green-50 px-2 py-1 text-xs text-green-700">{module}</span>)}
          {enabledModules.length === 0 ? <span className="text-sm text-gray-400">No modules advertised.</span> : null}
        </div>
      </div>
      <div className="rounded border p-4">
        <p className="text-xs font-semibold uppercase text-gray-400">Feature flags</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {flags.map(([flag, enabled]) => <span key={flag} className={`rounded px-2 py-1 text-xs ${enabled ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"}`}>{flag}: <b>{enabled ? "ON" : "OFF"}</b></span>)}
        </div>
      </div>
    </div>
    {sources ? <div className="mt-4 rounded bg-gray-50 p-3">
      <p className="text-xs font-semibold uppercase text-gray-400">Effective section source</p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {Object.entries(sources).map(([section, source]) => <span key={section} className="rounded bg-white px-2 py-1 text-gray-700">{section}: <b>{source}</b></span>)}
      </div>
    </div> : null}
  </section>;
}

function ProfileFlagControls({ context, projectId, reason, onReasonChange, onToggle, busy, message }: { context: EffectiveContext; projectId: string; reason: string; onReasonChange: (value: string) => void; onToggle: (flag: string, enabled: boolean) => void; busy: boolean; message: string | null }) {
  const forms = Object.values(context.profile_forms || {}).sort((a, b) => PROFILE_FORM_ORDER.indexOf(a.form_id) - PROFILE_FORM_ORDER.indexOf(b.form_id));
  return <section className="mt-6 rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Project profile form activation</h2>
        <p className="mt-1 text-sm text-gray-500">Toggle backend-driven farmer, parcel, and soil profile forms for the selected project. Tenant/default flags remain read-only here.</p>
      </div>
      <span className={`rounded px-3 py-1 text-xs ${projectId ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}>{projectId ? "Project scoped" : "Read-only until Project ID is selected"}</span>
    </div>
    {!projectId ? <p className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-800">Enter a Project ID above to enable project-level feature flag controls. This avoids accidental tenant-wide rollout.</p> : null}
    {projectId ? <label className="mt-4 block text-xs text-gray-500">Change reason<input value={reason} onChange={(event) => onReasonChange(event.target.value)} disabled={busy} className="mt-1 w-full rounded border p-2 text-sm text-gray-900 disabled:opacity-50" /></label> : null}
    {message ? <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-700">{message}</p> : null}
    <div className="mt-4 grid gap-3 md:grid-cols-3">
      {forms.map((form) => <div key={form.form_id} className="rounded border p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold text-gray-900">{label(form.title)}</p>
            <p className="mt-1 font-mono text-[11px] text-gray-400">{form.feature_flag}</p>
          </div>
          <span className={`rounded px-2 py-1 text-xs ${form.enabled ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"}`}>{form.enabled ? "Enabled" : "Disabled"}</span>
        </div>
        <button
          type="button"
          onClick={() => onToggle(form.feature_flag, !form.enabled)}
          disabled={!projectId || busy}
          className={`mt-4 w-full rounded px-3 py-2 text-sm font-medium disabled:opacity-50 ${form.enabled ? "border text-gray-700" : "bg-green-700 text-white"}`}
        >
          {busy ? "Saving..." : form.enabled ? "Disable for project" : "Enable for project"}
        </button>
      </div>)}
    </div>
  </section>;
}


function ProfileOptionSetsPanel({ payload }: { payload: ProfileOptionSetsResponse }) {
  return <section className="mt-6 rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Backend option sets</h2>
        <p className="mt-1 text-sm text-gray-500">Effective configurable values Android should use for farmer, land, soil, language, season, and agent-mode capture.</p>
      </div>
      <span className="rounded bg-blue-50 px-3 py-1 text-xs text-blue-700">{payload.count} option set(s)</span>
    </div>
    <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-4">
      {payload.option_sets.map((optionSet) => <div key={optionSet.option_set} className="rounded border p-3 text-xs">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-gray-900">{label(optionSet.title)}</p>
            <p className="font-mono text-[11px] text-gray-400">{optionSet.option_set}</p>
          </div>
          <span className={`rounded px-2 py-1 ${optionSet.source === "project" ? "bg-green-50 text-green-700" : optionSet.source === "tenant" ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-600"}`}>{optionSet.source || "default"}</span>
        </div>
        <div className="mt-2 text-gray-500">{optionSet.option_count} values · version {optionSet.version}</div>
      </div>)}
    </div>
  </section>;
}

function ProfileFormValidationPanel({ validation }: { validation: ProfileFormValidationResponse }) {
  return <section className="mt-6 rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Profile form validation</h2>
        <p className="mt-1 text-sm text-gray-500">Backend contract checks for Android-renderable farmer, parcel, and soil profile forms.</p>
      </div>
      <span className={`rounded px-3 py-1 text-xs ${validation.ready ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>{validation.ready ? "Ready" : "Needs attention"}</span>
    </div>
    <div className="mt-4 grid gap-2 text-xs md:grid-cols-6">
      <Mini label="Forms" value={String(validation.summary.form_count)} />
      <Mini label="Enabled" value={String(validation.summary.enabled_count)} />
      <Mini label="Fields" value={String(validation.summary.field_count)} />
      <Mini label="GPS" value={String(validation.summary.gps_field_count)} />
      <Mini label="Errors" value={String(validation.summary.error_count)} />
      <Mini label="Warnings" value={String(validation.summary.warning_count)} />
    </div>
    <div className="mt-4 grid gap-3 md:grid-cols-3">
      {validation.forms.map((form) => <div key={form.form_id} className="rounded border p-3 text-xs">
        <div className="flex items-start justify-between gap-2">
          <div><p className="font-semibold text-gray-900">{label(form.title)}</p><p className="font-mono text-[11px] text-gray-400">{form.form_id}</p></div>
          <span className={`rounded px-2 py-1 ${form.ready ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>{form.ready ? "OK" : "Issue"}</span>
        </div>
        <div className="mt-2 text-gray-500">{form.field_count} fields, {form.required_field_count} required, {form.gps_field_count} GPS, {form.error_count} errors, {form.warning_count} warnings</div>
      </div>)}
    </div>
    {validation.errors.length || validation.warnings.length ? <div className="mt-4 space-y-2">
      {[...validation.errors.map((issue) => ({ ...issue, severity: "Error" })), ...validation.warnings.map((issue) => ({ ...issue, severity: "Warning" }))].map((issue, index) => <div key={`${issue.severity}-${issue.form_id}-${issue.field_id || "form"}-${issue.code}-${index}`} className={`rounded p-3 text-xs ${issue.severity === "Error" ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-800"}`}>
        <span className="font-semibold">{issue.severity}: {issue.code}</span> <span className="font-mono">{issue.form_id}{issue.field_id ? `.${issue.field_id}` : ""}</span> - {issue.message}
      </div>)}
    </div> : <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-700">No validation errors or warnings.</p>}
  </section>;
}

function ProjectConfigAuditPanel({ audit }: { audit: ProjectAppConfigAuditResponse }) {
  return <section className="mt-6 rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Project app-config audit</h2>
        <p className="mt-1 text-sm text-gray-500">Recent project runtime configuration changes, including profile form flag toggles.</p>
      </div>
      <span className="rounded bg-gray-100 px-3 py-1 text-xs text-gray-700">{audit.count} event(s)</span>
    </div>
    {audit.events.length ? <div className="mt-4 overflow-hidden rounded border">
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["When", "Action", "Reason", "Sections", "Patch"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {audit.events.map((event) => <tr key={event.id}>
            <td className="p-3 text-xs text-gray-500">{event.created_at || "-"}<div className="mt-1 font-mono text-[11px] text-gray-400">{event.actor_id}</div></td>
            <td className="p-3"><span className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{event.action}</span></td>
            <td className="p-3 text-xs text-gray-700">{event.reason || "-"}</td>
            <td className="p-3 text-xs text-gray-600">{event.patched_sections.join(", ") || "-"}</td>
            <td className="p-3"><details className="text-xs"><summary className="cursor-pointer text-gray-500">View JSON</summary><pre className="mt-2 max-h-72 overflow-auto rounded bg-gray-950 p-3 text-[11px] text-gray-100">{JSON.stringify(event.config_patch, null, 2)}</pre></details></td>
          </tr>)}
        </tbody>
      </table>
    </div> : <p className="mt-4 rounded bg-gray-50 p-3 text-sm text-gray-500">No project app-config audit events yet.</p>}
  </section>;
}

function FormSummaryCard({ form, schema }: { form: ProfileFormContractSummary; schema?: FormSchemaContract }) {
  const requiredCount = schema?.fields.filter((field) => field.required).length || 0;
  const gpsCount = schema?.fields.filter((field) => field.type.startsWith("GPS")).length || 0;
  return <div className="rounded bg-white p-4 shadow">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h3 className="font-semibold text-gray-900">{label(form.title)}</h3>
        <p className="mt-1 font-mono text-xs text-gray-400">{form.form_id}</p>
      </div>
      <span className={`rounded px-2 py-1 text-xs ${form.enabled ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"}`}>{form.enabled ? "Enabled" : "Disabled"}</span>
    </div>
    <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
      <Mini label="Version" value={form.version} />
      <Mini label="Fields" value={String(schema?.fields.length || 0)} />
      <Mini label="Required" value={String(requiredCount)} />
    </div>
    <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
      <Mini label="GPS widgets" value={String(gpsCount)} />
      <Mini label="Flag" value={form.feature_flag} />
    </div>
  </div>;
}

function FormSchemaPanel({ summary, schema }: { summary: ProfileFormContractSummary; schema: FormSchemaContract }) {
  return <section className="rounded bg-white p-5 shadow">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{label(schema.title)}</h2>
        <p className="mt-1 text-sm text-gray-500">{label(schema.description)} Endpoint: <span className="font-mono">{summary.endpoint}</span></p>
      </div>
      <span className={`rounded px-2 py-1 text-xs ${summary.enabled ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-600"}`}>{summary.feature_flag}: {summary.enabled ? "ON" : "OFF"}</span>
    </div>
    <div className="mt-4 overflow-hidden rounded border">
      <table className="w-full text-sm">
        <thead className="bg-gray-50"><tr>{["Field", "Type", "Required", "Binding", "Dependency", "Source/options"].map((head) => <th key={head} className="p-3 text-left">{head}</th>)}</tr></thead>
        <tbody className="divide-y">
          {schema.fields.map((field) => <FieldRow key={field.id} field={field} />)}
        </tbody>
      </table>
    </div>
  </section>;
}

function FieldRow({ field }: { field: FormFieldContract }) {
  const dependency = field.depends_on ? `${field.depends_on}${field.depends_on_value ? ` = ${field.depends_on_value}` : " has any value"}` : "-";
  const source = field.source || (field.options?.length ? `${field.options.length} options` : "-");
  return <tr>
    <td className="p-3"><div className="font-medium text-gray-900">{label(field.label)}</div><div className="font-mono text-[11px] text-gray-400">{field.id}</div>{field.hint ? <div className="mt-1 text-xs text-gray-500">{label(field.hint)}</div> : null}</td>
    <td className="p-3"><span className={`rounded px-2 py-1 text-xs ${fieldTypeTone(field.type)}`}>{field.type}</span>{field.capture_modes?.length ? <div className="mt-2 text-xs text-gray-500">{field.capture_modes.join(", ")}</div> : null}</td>
    <td className="p-3"><span className={`rounded px-2 py-1 text-xs ${field.required ? "bg-red-50 text-red-700" : "bg-gray-100 text-gray-600"}`}>{field.required ? "Required" : "Optional"}</span></td>
    <td className="p-3"><div className="font-mono text-xs text-gray-600">{field.canonical_field || "-"}</div>{field.output_format ? <div className="mt-1 text-xs text-gray-400">{field.output_format}</div> : null}</td>
    <td className="p-3 text-xs text-gray-600">{dependency}</td>
    <td className="p-3"><div className="break-all text-xs text-gray-600">{source}</div>{field.validation ? <details className="mt-1 text-xs"><summary className="cursor-pointer text-gray-400">validation</summary><pre className="mt-1 overflow-auto rounded bg-gray-950 p-2 text-[11px] text-gray-100">{JSON.stringify(field.validation, null, 2)}</pre></details> : null}</td>
  </tr>;
}

function Mini({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="rounded bg-gray-50 p-2"><div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div><div className={`mt-1 break-all font-medium text-gray-900 ${mono ? "font-mono text-[11px]" : ""}`}>{value}</div></div>;
}

function textValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
