"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { appConfigApi, farmersApi, type FieldAgentCaptureActionDto, type FieldAgentWorklistResponse, type FieldAgentWorklistRowDto, type FormFieldOptionContract } from "@/lib/api";

const STATUSES = ["ACTIVE", "PENDING", "INACTIVE", "ARCHIVED", ""];
const PROFILE_OPTION_SETS = ["languages", "land_units", "soil_types", "soil_textures", "soil_colors"] as const;
type ProfileOptionSetKey = typeof PROFILE_OPTION_SETS[number];

export default function FieldAgentWorklistPage() {
  const [projectId, setProjectId] = useState("");
  const [actorId, setActorId] = useState("");
  const [assignedOnly, setAssignedOnly] = useState(false);
  const [status, setStatus] = useState("ACTIVE");
  const [payload, setPayload] = useState<FieldAgentWorklistResponse | null>(null);
  const [selected, setSelected] = useState<FieldAgentWorklistRowDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editMessage, setEditMessage] = useState<string | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const [farmerName, setFarmerName] = useState("");
  const [farmerVillage, setFarmerVillage] = useState("");
  const [farmerLanguage, setFarmerLanguage] = useState("");
  const [farmerLandUnit, setFarmerLandUnit] = useState("");
  const [parcelLocalName, setParcelLocalName] = useState("");
  const [parcelArea, setParcelArea] = useState("");
  const [parcelUnit, setParcelUnit] = useState("");
  const [parcelSoilType, setParcelSoilType] = useState("");
  const [soilTexture, setSoilTexture] = useState("");
  const [soilColor, setSoilColor] = useState("");
  const [profileOptions, setProfileOptions] = useState<Partial<Record<ProfileOptionSetKey, FormFieldOptionContract[]>>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await farmersApi.fieldAgentWorklist({
        projectId: projectId.trim() || undefined,
        actorId: actorId.trim() || undefined,
        assignedOnly,
        status,
        limit: 100,
      });
      setPayload(next);
      setSelected(next.farmers[0] || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load field-agent worklist");
    } finally {
      setLoading(false);
    }
  }, [projectId, actorId, assignedOnly, status]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    let cancelled = false;
    async function loadProfileOptions() {
      const next: Partial<Record<ProfileOptionSetKey, FormFieldOptionContract[]>> = {};
      await Promise.all(PROFILE_OPTION_SETS.map(async (optionSet) => {
        try {
          const detail = await appConfigApi.profileOptionSet(optionSet, projectId.trim() || undefined);
          next[optionSet] = detail.options || [];
        } catch {
          next[optionSet] = [];
        }
      }));
      if (!cancelled) setProfileOptions(next);
    }
    void loadProfileOptions();
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    setEditMessage(null);
    setFarmerName(String(selected?.farmer.display_name || ""));
    setFarmerVillage(String(selected?.farmer.village_name_manual || ""));
    setFarmerLanguage(String(selected?.farmer.language_preference || ""));
    setFarmerLandUnit(String(selected?.farmer.total_land_unit || ""));
    const parcel = selected?.parcels?.[0];
    setParcelLocalName(String(parcel?.local_name || ""));
    setParcelArea(parcel?.reported_area !== undefined && parcel?.reported_area !== null ? String(parcel.reported_area) : "");
    setParcelUnit(String(parcel?.reported_area_unit || ""));
    setParcelSoilType(String(parcel?.soil_type_code || ""));
    const soil = selected?.soil_profiles?.[0];
    setSoilTexture(String(soil?.soil_texture || ""));
    setSoilColor(String(soil?.soil_color || ""));
  }, [selected]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  async function saveSelectedProfileEdits() {
    if (!selected) return;
    setEditBusy(true);
    setError(null);
    setEditMessage(null);
    try {
      await farmersApi.updateFarmer(selected.farmer.id, {
        display_name: farmerName || null,
        village_name_manual: farmerVillage || null,
        language_preference: farmerLanguage || null,
        total_land_unit: farmerLandUnit || null,
      });
      let parcelId: string | null = selected.parcels?.[0]?.id || null;
      const hasParcelInput = Boolean(parcelArea || parcelLocalName || parcelUnit || parcelSoilType || farmerVillage);
      if (parcelId) {
        await farmersApi.updateParcel(parcelId, {
          local_name: parcelLocalName || null,
          reported_area: parcelArea ? Number(parcelArea) : undefined,
          reported_area_unit: parcelUnit || undefined,
          soil_type_code: parcelSoilType || null,
        });
      } else if (hasParcelInput && parcelArea) {
        const created = await farmersApi.createParcel({
          farmer_id: selected.farmer.id,
          village_name_manual: farmerVillage || null,
          reported_area: Number(parcelArea),
          reported_area_unit: parcelUnit || farmerLandUnit || "ACRE",
          soil_type_code: parcelSoilType || null,
          local_name: parcelLocalName || null,
          ownership_type: "OWNED",
        }) as { id?: string };
        parcelId = created.id || null;
      }
      const soil = selected.soil_profiles?.[0];
      const hasSoilInput = Boolean(soilTexture || soilColor || parcelSoilType);
      if (soil) {
        await farmersApi.updateSoilProfile(soil.id, {
          soil_type_code: parcelSoilType || null,
          soil_texture: soilTexture || null,
          soil_color: soilColor || null,
        });
      } else if (parcelId && hasSoilInput) {
        await farmersApi.createSoilProfile({
          parcel_id: parcelId,
          farmer_id: selected.farmer.id,
          soil_type_code: parcelSoilType || null,
          soil_texture: soilTexture || null,
          soil_color: soilColor || null,
          data_source: "MANUAL",
        });
      }
      setEditMessage("Profile updates saved. Refreshing worklist...");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save profile edits");
    } finally {
      setEditBusy(false);
    }
  }

  return <div>
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900">Agent Worklist</h1>
      <p className="mt-1 text-sm text-gray-500">Backend-owned assisted-capture queue for field agents, agronomists, dealers, and admins collecting farmer/land/soil data.</p>
    </div>

    <form onSubmit={submit} className="mb-6 rounded bg-white p-5 shadow">
      <div className="grid gap-3 md:grid-cols-4">
        <Input label="Project ID" value={projectId} onChange={setProjectId} />
        <Input label="Actor/Agent ID" value={actorId} onChange={setActorId} />
        <label className="text-xs text-gray-500">Status<select value={status} onChange={(event) => setStatus(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">{STATUSES.map((item) => <option key={item || "ALL"} value={item}>{item || "ALL"}</option>)}</select></label>
        <label className="flex items-end gap-2 rounded border p-2 text-sm text-gray-700"><input type="checkbox" checked={assignedOnly} onChange={(event) => setAssignedOnly(event.target.checked)} /> Assigned only</label>
      </div>
      <div className="mt-4 flex gap-2">
        <button type="submit" disabled={loading} className="rounded bg-green-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Refresh</button>
        <button type="button" onClick={() => { setProjectId(""); setActorId(""); setAssignedOnly(false); setStatus("ACTIVE"); }} className="rounded border px-4 py-2 text-sm">Reset</button>
      </div>
      <p className="mt-3 text-xs text-gray-500">When assigned-only is enabled, backend filters through farmer project enrollment assignments. If Actor ID is blank, the API uses the logged-in user header when available.</p>
    </form>

    {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {loading ? <p className="rounded bg-white p-5 text-sm text-gray-500 shadow">Loading worklist...</p> : null}

    {payload && !loading ? <>
      {payload.agent_profile || payload.mode_switch ? <div className="mb-6 rounded bg-blue-50 p-4 text-sm text-blue-900">
        <div className="font-semibold">Agent context</div>
        {payload.agent_profile ? <div className="mt-1">{payload.agent_profile.display_name || payload.agent_profile.user_id} / {payload.agent_profile.role_type || "AGENT"} / {payload.agent_profile.status || "-"}</div> : <div className="mt-1">No active agent profile found for the actor id; showing worklist by requested filters.</div>}
        {payload.mode_switch?.personal_farmer_mode_available ? <div className="mt-1 text-xs">This user can also switch to personal farmer mode: {payload.mode_switch.personal_farmer_id}</div> : null}
      </div> : null}
      <div className="mb-6 grid gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Mini label="Farmers" value={payload.summary.farmer_count} />
        <Mini label="Home ready" value={payload.summary.home_ready_count} tone="green" />
        <Mini label="Blocking gaps" value={payload.summary.missing_required_count} tone={payload.summary.missing_required_count ? "red" : "slate"} />
        <Mini label="Capture actions" value={payload.summary.capture_action_count} tone="amber" />
        <Mini label="Weather ready" value={payload.summary.weather_advisory_ready_count} tone="blue" />
        <Mini label="Soil moisture" value={payload.summary.soil_moisture_enrichment_ready_count} tone="blue" />
        <Mini label="Satellite ready" value={payload.summary.satellite_enrichment_ready_count} tone="green" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_460px]">
        <section className="overflow-hidden rounded bg-white shadow">
          <div className="border-b p-5">
            <h2 className="text-lg font-bold text-gray-900">Assigned capture queue</h2>
            <p className="text-sm text-gray-500">{payload.farmers.length} farmer row(s) returned.</p>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="p-3">Farmer</th><th className="p-3">Home</th><th className="p-3">Land</th><th className="p-3">Crop</th><th className="p-3">Top action</th></tr></thead>
            <tbody className="divide-y">
              {payload.farmers.map((row) => <tr key={row.farmer.id} className={`cursor-pointer hover:bg-green-50 ${selected?.farmer.id === row.farmer.id ? "bg-green-50" : ""}`} onClick={() => setSelected(row)}>
                <td className="p-3"><div className="font-medium text-gray-900">{row.farmer.display_name || row.farmer.mobile_number || row.farmer.id}</div><div className="text-xs text-gray-500">{row.farmer.mobile_number || row.farmer.id}</div></td>
                <td className="p-3"><Badge tone={row.profile_completion.is_complete_for_home ? "green" : "red"}>{row.profile_completion.is_complete_for_home ? "Ready" : "Blocked"}</Badge></td>
                <td className="p-3 text-xs text-gray-600">{row.parcel_count} parcel(s)<br />{row.soil_profile_count} soil</td>
                <td className="p-3 text-xs text-gray-600">{row.active_crop_cycle_count} cycle(s)<br />{row.active_stage_count} stage(s)</td>
                <td className="p-3 text-xs text-gray-600">{row.capture_actions[0]?.label || "No action"}</td>
              </tr>)}
              {payload.farmers.length === 0 ? <tr><td colSpan={5} className="p-6 text-center text-gray-400">No farmers found.</td></tr> : null}
            </tbody>
          </table>
        </section>

        <aside className="rounded bg-white p-5 shadow">
          <h2 className="text-lg font-bold text-gray-900">Worklist detail</h2>
          {selected ? <div className="mt-4 space-y-4">
            <div>
              <div className="font-semibold text-gray-900">{selected.farmer.display_name || selected.farmer.mobile_number || selected.farmer.id}</div>
              <div className="mt-1 flex flex-wrap gap-3 text-xs">
                <Link href={`/farmer-trace/${selected.farmer.id}`} className="text-blue-700">Open farmer trace</Link>
                {selected.endpoints.profile_hydration ? <span className="text-gray-400">Hydration: {selected.endpoints.profile_hydration}</span> : null}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <Mini label="Parcels" value={selected.parcel_count} />
              <Mini label="Soil profiles" value={selected.soil_profile_count} />
              <Mini label="Crop cycles" value={selected.active_crop_cycle_count} />
              <Mini label="Active stages" value={selected.active_stage_count} />
            </div>

            <Section title="Quick profile edit">
              <div className="space-y-3 rounded border bg-gray-50 p-3 text-xs">
                <div className="grid gap-2 md:grid-cols-2">
                  <Input label="Farmer name" value={farmerName} onChange={setFarmerName} />
                  <Input label="Village" value={farmerVillage} onChange={setFarmerVillage} />
                  <OptionSelect label="Language" value={farmerLanguage} onChange={setFarmerLanguage} options={profileOptions.languages || []} />
                  <OptionSelect label="Land unit" value={farmerLandUnit} onChange={setFarmerLandUnit} options={profileOptions.land_units || []} />
                </div>
                <div>
                  <p className="mb-2 text-gray-500">{selected.parcels?.[0] ? "Edit first parcel" : "Create first parcel"}</p>
                  <div className="grid gap-2 md:grid-cols-2">
                    <Input label="Parcel local name" value={parcelLocalName} onChange={setParcelLocalName} />
                    <Input label="Parcel area" value={parcelArea} onChange={setParcelArea} />
                    <OptionSelect label="Parcel unit" value={parcelUnit} onChange={setParcelUnit} options={profileOptions.land_units || []} />
                    <OptionSelect label="Parcel soil type" value={parcelSoilType} onChange={setParcelSoilType} options={profileOptions.soil_types || []} />
                  </div>
                  {!selected.parcels?.[0] ? <p className="mt-1 text-gray-500">Parcel area is required before creating the first land record.</p> : null}
                </div>
                <div>
                  <p className="mb-2 text-gray-500">{selected.soil_profiles?.[0] ? "Edit first soil profile" : "Create first soil profile after parcel exists"}</p>
                  <div className="grid gap-2 md:grid-cols-2">
                    <OptionSelect label="Soil texture" value={soilTexture} onChange={setSoilTexture} options={profileOptions.soil_textures || []} />
                    <OptionSelect label="Soil color" value={soilColor} onChange={setSoilColor} options={profileOptions.soil_colors || []} />
                  </div>
                  {!selected.soil_profiles?.[0] ? <p className="mt-1 text-gray-500">Soil type, texture, or color will create a manual soil profile once a parcel exists.</p> : null}
                </div>
                <button type="button" onClick={() => void saveSelectedProfileEdits()} disabled={editBusy} className="rounded bg-green-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{editBusy ? "Saving..." : "Save profile edits"}</button>
                {editMessage ? <p className="text-green-700">{editMessage}</p> : null}
              </div>
            </Section>

            <Section title="Capture actions">
              {selected.capture_actions.map((action) => <ActionRow key={action.code} action={action} />)}
              {selected.capture_actions.length === 0 ? <p className="text-xs text-gray-400">No pending capture action.</p> : null}
            </Section>

            <Section title="Assignment context">
              {selected.project_enrollments.map((enrollment) => <div key={enrollment.id} className="rounded border p-2 text-xs">
                <div className="font-semibold text-gray-900">{enrollment.project_name || enrollment.project_id}</div>
                <div className="mt-1 text-gray-500">{enrollment.status || "-"} / {enrollment.enrollment_method || "-"}</div>
                <div className="mt-1 break-all text-gray-500">Assigned: {enrollment.assigned_user_ids.length ? enrollment.assigned_user_ids.join(", ") : "none"}</div>
              </div>)}
              {selected.project_enrollments.length === 0 ? <p className="text-xs text-gray-400">No project enrollment context.</p> : null}
            </Section>

            {selected.profile_completion.enrichment_readiness ? <Section title="Enrichment readiness">
              <ReadinessFlag label="Land location" ready={selected.profile_completion.enrichment_readiness.has_land_location} />
              <ReadinessFlag label="Weather snapshot" ready={selected.profile_completion.enrichment_readiness.has_weather_snapshot} detail={`${selected.profile_completion.enrichment_readiness.weather_snapshot_count} snapshot(s)`} />
              <ReadinessFlag label="Weather advisory" ready={selected.profile_completion.enrichment_readiness.ready_for_weather_advisory} />
              <ReadinessFlag label="Soil moisture enrichment" ready={selected.profile_completion.enrichment_readiness.ready_for_soil_moisture_enrichment} />
              <ReadinessFlag label="Satellite enrichment" ready={selected.profile_completion.enrichment_readiness.ready_for_satellite_enrichment} />
            </Section> : null}
          </div> : <p className="mt-4 text-sm text-gray-400">Select a farmer to inspect the assisted-capture checklist.</p>}
        </aside>
      </div>
    </> : null}
  </div>;
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-500">{label}<input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>;
}


function OptionSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: FormFieldOptionContract[] }) {
  return <label className="text-xs text-gray-500">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900">
    <option value="">Select...</option>
    {options.map((option) => <option key={option.value} value={option.value}>{option.label?.en || option.value}</option>)}
  </select></label>;
}

function Mini({ label, value, tone = "slate" }: { label: string; value: number; tone?: "slate" | "green" | "blue" | "amber" | "red" }) {
  const tones = { slate: "bg-white text-gray-900", green: "bg-green-50 text-green-900", blue: "bg-blue-50 text-blue-900", amber: "bg-amber-50 text-amber-900", red: "bg-red-50 text-red-900" };
  return <div className={`rounded border p-3 ${tones[tone]}`}><div className="text-xs opacity-70">{label}</div><div className="mt-1 text-xl font-bold">{value}</div></div>;
}

function ActionRow({ action }: { action: FieldAgentCaptureActionDto }) {
  const tone = action.priority === "HIGH" ? "red" : action.priority === "MEDIUM" ? "amber" : "green";
  return <div className="rounded border p-2 text-xs"><div className="flex items-center justify-between gap-2"><span className="font-semibold text-gray-900">{action.label}</span><Badge tone={tone}>{action.priority}</Badge></div><div className="mt-1 font-mono text-[10px] text-gray-400">{action.code}</div></div>;
}

function ReadinessFlag({ label, ready, detail }: { label: string; ready: boolean; detail?: string }) {
  return <div className="flex items-center justify-between rounded border p-2 text-xs"><div><span className="font-semibold text-gray-800">{label}</span>{detail ? <span className="ml-2 text-gray-400">{detail}</span> : null}</div><Badge tone={ready ? "green" : "amber"}>{ready ? "Ready" : "Pending"}</Badge></div>;
}

function Badge({ children, tone }: { children: React.ReactNode; tone: "green" | "amber" | "red" }) {
  const tones = { green: "bg-green-100 text-green-800", amber: "bg-amber-100 text-amber-800", red: "bg-red-100 text-red-800" };
  return <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><h3 className="mb-2 text-sm font-semibold text-gray-800">{title}</h3><div className="space-y-2">{children}</div></div>;
}
