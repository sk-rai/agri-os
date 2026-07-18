/**
 * Typed API client for Agri-OS backend.
 * Handles auth headers (Bearer JWT + X-Tenant-ID) and 401 redirects.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  noAuth?: boolean;
}

export type ApiErrorDetail =
  | string
  | {
      error?: string;
      message?: string;
      required_permission?: string;
      current_role?: string;
      current_permissions?: string[];
      tenant_id?: string;
      project_id?: string;
      [key: string]: unknown;
    };

export class ApiError extends Error {
  status: number;
  detail?: ApiErrorDetail;

  constructor(message: string, status: number, detail?: ApiErrorDetail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function formatApiErrorMessage(detail: ApiErrorDetail | undefined, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (!detail || typeof detail !== "object") return fallback;

  if (detail.error === "ADMIN_PERMISSION_DENIED") {
    const parts = [detail.message || "Admin permission denied."];
    if (detail.required_permission) parts.push(`Required: ${detail.required_permission}`);
    if (detail.current_role) parts.push(`Current role: ${detail.current_role}`);
    if (Array.isArray(detail.current_permissions)) {
      parts.push(`Current permissions: ${detail.current_permissions.join(", ") || "none"}`);
    }
    if (detail.project_id) parts.push(`Project: ${detail.project_id}`);
    return parts.join(" ");
  }

  if (typeof detail.message === "string") return detail.message;
  return fallback;
}

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("agrios_token");
  const tenantId = localStorage.getItem("agrios_tenant_id");
  const actorId = localStorage.getItem("agrios_user_id");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenantId) headers["X-Tenant-ID"] = tenantId;
  if (actorId) headers["X-Actor-ID"] = actorId;
  return headers;
}

export async function api<T = unknown>(
  path: string,
  options: ApiOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, noAuth = false } = options;

  const fetchHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(!noAuth ? getAuthHeaders() : {}),
    ...headers,
  };

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: fetchHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("agrios_token");
    window.location.href = "/login";
    throw new ApiError("Unauthorized", 401);
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = error.detail as ApiErrorDetail | undefined;
    throw new ApiError(formatApiErrorMessage(detail, res.statusText), res.status, detail);
  }

  return res.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  return apiUploadWithFields<T>(path, file);
}

export async function apiUploadWithFields<T>(path: string, file: File, fields?: Record<string, string>): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  Object.entries(fields || {}).forEach(([key, value]) => form.append(key, value));
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers: getAuthHeaders(), body: form });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = error.detail as ApiErrorDetail | undefined;
    throw new ApiError(formatApiErrorMessage(detail, res.statusText), res.status, detail);
  }
  return res.json() as Promise<T>;
}

export async function apiDownload(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { headers: getAuthHeaders() });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: `Download failed: ${res.statusText}` }));
    const detail = error.detail as ApiErrorDetail | undefined;
    throw new ApiError(formatApiErrorMessage(detail, `Download failed: ${res.statusText}`), res.status, detail);
  }
  const disposition = res.headers.get("content-disposition") || "";
  const name = disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}


export interface CropTaxonomyNodeDto {
  id: string;
  code: string;
  canonical_name: string;
  description?: string | null;
  node_type: string;
  level: number;
  display_order: number;
  aliases?: unknown[] | Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  parent_codes: string[];
  child_codes: string[];
}

export interface CropTaxonomyResponse {
  schema_version: string;
  nodes: CropTaxonomyNodeDto[];
  edges: Array<{ parent_code: string; child_code: string; relationship_type: string }>;
}

export interface CropPropagationTypeDto {
  id: string;
  code: string;
  canonical_name: string;
  description?: string | null;
  establishment_type: string;
  aliases?: unknown[] | Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
}

export interface CropCatalogItemDto {
  id: string;
  code: string;
  canonical_name: string;
  scientific_name?: string | null;
  typical_duration_days?: number | null;
  suitable_seasons?: string[] | null;
  taxonomy: Array<{ code: string; canonical_name: string; node_type: string; level: number; assignment_type: string; is_primary: boolean }>;
  propagation_options: Array<{ code: string; canonical_name: string; establishment_type: string; season_code?: string | null; is_default: boolean; notes?: string | null }>;
}

export interface CropCatalogResponse {
  schema_version: string;
  crops: CropCatalogItemDto[];
  count: number;
}

export interface CropTaxonomyCsvValidationRow {
  row_number: number;
  code: string;
  action: "CREATE" | "UPDATE" | "UNCHANGED" | "INVALID";
  errors: Array<{ field: string; code: string; message: string }>;
  warnings: Array<{ field: string; code: string; message: string }>;
  normalized: Record<string, unknown>;
}

export interface CropTaxonomyCsvValidationResponse {
  schema_version: string;
  mode: "VALIDATE_ONLY";
  file_name?: string | null;
  can_apply: boolean;
  summary: { total: number; create: number; update: number; unchanged: number; invalid: number; warnings: number; errors: number };
  rows: CropTaxonomyCsvValidationRow[];
  message: string;
}

export interface CropTaxonomyImportBatch {
  batch_id: string;
  file_name?: string | null;
  status: "VALIDATED" | "INVALID" | "APPLIED" | "EXPIRED" | "STALE";
  can_apply: boolean;
  expires_at: string;
  applied_at?: string | null;
  created_at: string;
  report: CropTaxonomyCsvValidationResponse & {
    applied_counts?: Record<string, number>;
    apply_reason?: string;
    applied_by?: string;
  };
}

export interface CropTaxonomyImportHistory {
  schema_version: string;
  tenant_id: string;
  status?: string | null;
  count: number;
  imports: CropTaxonomyImportBatch[];
}

export type CropPropagationCsvValidationResponse = CropTaxonomyCsvValidationResponse;
export type CropPropagationImportBatch = CropTaxonomyImportBatch;
export type CropPropagationImportHistory = CropTaxonomyImportHistory;
export type CropCatalogCsvValidationResponse = CropTaxonomyCsvValidationResponse;
export type CropCatalogImportBatch = CropTaxonomyImportBatch;
export type CropCatalogImportHistory = CropTaxonomyImportHistory;



export interface MediaAssetTrace {
  id: string;
  media_type: string;
  mime_type: string;
  upload_status: string;
  storage_url?: string | null;
  thumbnail_url?: string | null;
  sha256_hash?: string | null;
  size_bytes?: number | null;
  duration_seconds?: number | null;
  capture_lat?: string | null;
  capture_lng?: string | null;
  capture_accuracy_meters?: string | null;
  captured_at?: string | null;
  metadata?: Record<string, unknown>;
}
export interface MediaAttachmentTrace {
  id: string;
  media_asset_id: string;
  entity_type: string;
  entity_id: string;
  purpose: string;
  caption?: string | null;
  display_order: number;
  is_primary: boolean;
  metadata?: Record<string, unknown>;
  asset: MediaAssetTrace;
  created_at?: string | null;
  updated_at?: string | null;
}
export interface ActivityUsageRow {
  activity_id: string;
  activity_date?: string | null;
  tenant_id?: string | null;
  project_id?: string | null;
  farmer_id?: string | null;
  farmer_name?: string | null;
  parcel_id?: string | null;
  parcel_label?: string | null;
  crop_cycle_id: string;
  crop_cycle_status?: string | null;
  workflow_template_version_id?: string | null;
  crop_code: string;
  season_code: string;
  stage_code?: string | null;
  stage_instance_id?: string | null;
  stage_name?: string | null;
  stage_order?: number | null;
  stage_status?: string | null;
  activity_type: string;
  input_code?: string | null;
  input_name?: string | null;
  input_rule_id?: string | null;
  product_id?: string | null;
  product_code?: string | null;
  package_id?: string | null;
  package_sku?: string | null;
  recommended_quantity?: string | null;
  recommended_quantity_unit?: string | null;
  actual_quantity?: string | null;
  actual_quantity_unit?: string | null;
  dosage_variance_reason?: string | null;
  quantity?: string | null;
  quantity_unit?: string | null;
  area_applied?: string | null;
  area_unit?: string | null;
  cost_amount?: string | null;
  cost_currency?: string | null;
  gps_lat?: string | null;
  gps_lng?: string | null;
  logged_by?: string | null;
  logging_method?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  notes?: string | null;
  media_attachment_count?: number;
}

export interface ActivityUsageReportResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  summary: {
    activity_count: number;
    total_cost: string;
    variance_count: number;
    quantity_by_input: Array<{ input_code: string; unit: string; quantity: string }>;
    quantity_by_product: Array<{ product_code: string; package_sku?: string | null; unit: string; quantity: string }>;
  };
  count: number;
  activities: ActivityUsageRow[];
}

export interface ProjectInputComplianceResponse {
  schema_version: string;
  tenant_id: string;
  project: { id: string; name: string; status: string; start_date?: string | null; end_date?: string | null; crop_scope: string[] };
  summary: {
    activity_count: number;
    total_cost: string;
    recommendation_linked_count: number;
    custom_activity_count: number;
    recommendation_linked_rate_percent: string;
    variance_count: number;
    variance_rate_percent: string;
    product_approved_count: number;
    product_unapproved_count: number;
    product_preferred_count: number;
    product_missing_count: number;
    product_approval_rate_percent: string;
  };
  quantity_by_input: Array<{ input_code: string; unit: string; quantity: string }>;
  quantity_by_product: Array<{ product_code: string; package_sku?: string | null; unit: string; quantity: string }>;
  quantity_by_crop_stage: Array<{ crop_code: string; stage_code: string; unit: string; quantity: string }>;
  activity_count_by_crop_stage: Array<{ crop_code: string; stage_code: string; activity_count: number }>;
  top_variance_reasons: Array<{ reason: string; count: number }>;
  activities: ActivityUsageRow[];
}
export interface ProductTraceResponse {
  schema_version: string;
  tenant_id: string;
  product: Record<string, string | number | null> & { id: string; code: string; brand_name: string; status: string };
  manufacturer?: Record<string, string | null> | null;
  input?: Record<string, string | null> | null;
  packages: Array<Record<string, string | number | null> & { id: string; sku: string; pack_label: string; status: string; activity_count: number }>;
  project_approvals: Array<Record<string, string | number | boolean | null>>;
  input_rules: Array<Record<string, string | number | boolean | string[] | null> & { id: string; crop_code: string; stage_code: string; activity_type: string }>;
  summary: {
    activity_count: number;
    total_cost: string;
    variance_count: number;
    quantity_by_package: Array<{ package_sku: string; unit: string; quantity: string }>;
    quantity_by_crop: Array<{ crop_code: string; unit: string; quantity: string }>;
    quantity_by_stage: Array<{ stage_code: string; unit: string; quantity: string }>;
    quantity_by_project: Array<{ project_id: string; unit: string; quantity: string }>;
  };
  activities: ActivityUsageRow[];
}
export interface InputRuleTraceResponse {
  schema_version: string;
  tenant_id: string;
  rule: Record<string, string | number | boolean | string[] | null> & { id: string; input_code: string; crop_code: string; stage_code: string; activity_type: string };
  project?: Record<string, string | null> | null;
  input?: Record<string, string | string[] | null> | null;
  project_assignment?: Record<string, string | number | boolean | null> | null;
  products: Array<Record<string, unknown> & { id: string; code: string; brand_name: string; status: string }>;
  summary: { activity_count: number; total_cost: string; variance_count: number; quantity_by_product: Array<{ product_code: string; unit: string; quantity: string }> };
  activities: ActivityUsageRow[];
}
export interface CropCycleTraceStage {
  stage_instance_id: string;
  stage_code: string;
  stage_name: string;
  stage_order: number;
  status: string;
  expected_duration_days?: number | null;
  planned_start_date?: string | null;
  actual_start_date?: string | null;
  actual_end_date?: string | null;
  started_by?: string | null;
  completed_by?: string | null;
  skip_reason?: string | null;
  activity_count: number;
  total_cost: string;
}

export interface CropCycleTraceResponse {
  schema_version: string;
  tenant_id: string;
  cycle: Record<string, string | number | null> & { id: string; crop_code: string; season_code: string; status: string };
  project?: Record<string, string | null> | null;
  farmer?: Record<string, string | null> | null;
  parcel?: Record<string, string | null> | null;
  summary: { stage_count: number; activity_count: number; total_cost: string; variance_count: number };
  stages: CropCycleTraceStage[];
  activities: ActivityUsageRow[];
  media_attachments?: Record<string, MediaAttachmentTrace[]>;
}
export interface FarmerTraceParcel {
  id: string;
  project_id?: string | null;
  survey_number?: string | null;
  local_name?: string | null;
  display_name?: string | null;
  reported_area?: string | null;
  reported_area_unit?: string | null;
  ownership_type?: string | null;
  village_name?: string | null;
  current_crop_code?: string | null;
  geometry_source?: string | null;
  centroid_lat?: string | null;
  centroid_lng?: string | null;
  computed_area_hectares?: string | null;
  status?: string | null;
  crop_cycle_count: number;
  active_cycle_count: number;
  completed_cycle_count: number;
  activity_count: number;
  total_cost: string;
  media_attachments?: MediaAttachmentTrace[];
}
export interface FarmerTraceCycle {
  id: string;
  parcel_id?: string | null;
  project_id?: string | null;
  crop_code: string;
  season_code: string;
  status: string;
  lifecycle_template_id?: string | null;
  workflow_template_version_id?: string | null;
  planned_sowing_date?: string | null;
  expected_harvest_date?: string | null;
  actual_harvest_date?: string | null;
  activity_count: number;
  total_cost: string;
}
export interface FarmerTraceEnrollment {
  id: string;
  project_id: string;
  project_name?: string | null;
  project_status?: string | null;
  status: string;
  enrollment_method?: string | null;
  enrollment_source?: string | null;
  enrollment_batch_id?: string | null;
  enrolled_by?: string | null;
  parcel_ids: string[];
  assigned_user_ids: string[];
  metadata?: Record<string, unknown>;
  lifecycle_events: Array<Record<string, unknown>>;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}
export interface FarmerTraceEnrollmentLifecycle {
  status_counts: Record<string, number>;
  active_count: number;
  pending_count: number;
  active_pending_count: number;
  total_enrollment_count: number;
  has_open_enrollments: boolean;
  can_continue_independently: boolean;
  latest_event?: Record<string, unknown> | null;
  events: Array<Record<string, unknown>>;
  project_enrollments_url: string;
}
export interface FarmerTraceResponse {
  schema_version: string;
  tenant_id: string;
  farmer: Record<string, string | null> & { id: string };
  project?: Record<string, string | null> | null;
  summary: {
    parcel_count: number;
    crop_cycle_count: number;
    active_cycle_count: number;
    completed_cycle_count: number;
    activity_count: number;
    total_cost: string;
    variance_count: number;
  };
  project_enrollments: FarmerTraceEnrollment[];
  enrollment_lifecycle: FarmerTraceEnrollmentLifecycle;
  parcels: FarmerTraceParcel[];
  crop_cycles: FarmerTraceCycle[];
  activities: ActivityUsageRow[];
}
export interface ParcelTraceResponse {
  schema_version: string;
  tenant_id: string;
  parcel: FarmerTraceParcel & {
    farmer_id: string;
    soil_type_code?: string | null;
    geometry_accuracy_meters?: string | null;
    geometry_captured_at?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
  };
  farmer?: Record<string, string | null> & { id: string } | null;
  project?: Record<string, string | null> | null;
  summary: {
    crop_cycle_count: number;
    active_cycle_count: number;
    completed_cycle_count: number;
    activity_count: number;
    total_cost: string;
    variance_count: number;
  };
  crop_cycles: FarmerTraceCycle[];
  activities: ActivityUsageRow[];
}
export interface AdminLookupProject {
  id: string;
  label: string;
  name: string;
  status?: string | null;
  crop_scope: string[];
  start_date?: string | null;
  end_date?: string | null;
  crop_cycle_count: number;
  trace_url: string;
  compliance_url?: string | null;
}
export interface AdminLookupFarmer {
  id: string;
  label: string;
  display_name?: string | null;
  mobile_number?: string | null;
  village_name?: string | null;
  primary_crop_code?: string | null;
  project_id?: string | null;
  status?: string | null;
  crop_cycle_count: number;
  activity_count: number;
  trace_url: string;
}
export interface AdminLookupParcel {
  id: string;
  label: string;
  survey_number?: string | null;
  local_name?: string | null;
  farmer_id: string;
  farmer_name?: string | null;
  project_id?: string | null;
  reported_area?: string | null;
  reported_area_unit?: string | null;
  ownership_type?: string | null;
  village_name?: string | null;
  geometry_source?: string | null;
  status?: string | null;
  crop_cycle_count: number;
  activity_count: number;
  trace_url: string;
}

export interface ProfileCompletionSectionDto {
  status: "COMPLETE" | "PARTIAL" | "MISSING" | string;
  required_for_home: boolean;
  missing_required_fields: string[];
  missing_recommended_fields: string[];
}

export interface ProfileCompletionDto {
  schema_version: string;
  is_complete_for_home: boolean;
  is_ready_for_personalized_advisories: boolean;
  enrichment_readiness?: {
    has_land_location: boolean;
    has_soil_profile: boolean;
    has_weather_snapshot: boolean;
    weather_snapshot_count: number;
    ready_for_weather_advisory: boolean;
    ready_for_soil_moisture_enrichment: boolean;
    ready_for_satellite_enrichment: boolean;
    notes?: string[];
  };
  missing_fields: string[];
  recommended_missing_fields: string[];
  parcel_count: number;
  soil_profile_count: number;
  sections: Record<string, ProfileCompletionSectionDto>;
  next_actions: Array<{ code: string; label: string; priority: string }>;
}

export interface FarmerProfileReadinessRowDto {
  farmer: {
    id: string;
    tenant_id: string;
    mobile_number?: string | null;
    display_name?: string | null;
    village_id?: string | null;
    status?: string | null;
    [key: string]: unknown;
  };
  parcel_count: number;
  soil_profile_count: number;
  project_enrollment_count: number;
  profile_completion: ProfileCompletionDto;
}

export interface FarmerProfileReadinessResponse {
  schema_version: string;
  tenant_id: string;
  filters: { project_id?: string | null; status?: string | null; offset: number; limit: number };
  summary: {
    farmer_count: number;
    home_ready_count: number;
    personalized_advisory_ready_count: number;
    missing_required_count: number;
    missing_parcel_count: number;
    soil_profile_recommended_count: number;
    parcel_location_recommended_count: number;
    weather_snapshot_available_count?: number;
    weather_advisory_ready_count?: number;
    soil_moisture_enrichment_ready_count?: number;
    satellite_enrichment_ready_count?: number;
  };
  farmers: FarmerProfileReadinessRowDto[];
}


export interface ProjectEnrollmentCsvValidationRow {
  row_number: number;
  mobile_number: string;
  action: "CREATE" | "UPDATE" | "UNCHANGED" | "INVALID" | string;
  errors: Array<{ field: string; code: string; message: string }>;
  warnings: Array<{ field: string; code: string; message: string }>;
  normalized: Record<string, unknown>;
}

export interface ProjectEnrollmentCsvValidationResponse {
  schema_version: string;
  mode: "VALIDATE_ONLY" | string;
  project_id: string;
  file_name?: string | null;
  can_apply: boolean;
  summary: { total: number; create: number; update: number; unchanged: number; invalid: number; warnings: number; errors: number };
  rows: ProjectEnrollmentCsvValidationRow[];
  message: string;
  applied_counts?: Record<string, number>;
  apply_reason?: string;
  applied_by?: string;
}

export interface ProjectEnrollmentImportBatch {
  batch_id: string;
  project_id: string;
  file_name?: string | null;
  status: "VALIDATED" | "INVALID" | "APPLIED" | "EXPIRED" | "STALE" | string;
  can_apply: boolean;
  expires_at: string;
  applied_at?: string | null;
  created_at: string;
  report: ProjectEnrollmentCsvValidationResponse;
}

export interface ProjectEnrollmentImportHistory {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  status?: string | null;
  count: number;
  imports: ProjectEnrollmentImportBatch[];
}

export interface ProjectEnrollmentLifecyclePreview {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  target_status: string;
  source_statuses: string[];
  affected_count: number;
  by_status: Record<string, number>;
  can_apply: boolean;
  message: string;
}

export interface ProjectEnrollmentLifecycleApplyResponse {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  target_status: string;
  updated_count: number;
  skipped_count: number;
  updated_enrollment_ids: string[];
  reason: string;
}

export interface ProjectEnrollmentReportRow {
  id: string;
  tenant_id: string;
  farmer_id: string;
  farmer_name?: string | null;
  farmer_mobile?: string | null;
  farmer_status?: string | null;
  village?: string | null;
  project_id: string;
  project_name: string;
  project_status?: string | null;
  enrollment_method: string;
  enrollment_source?: string | null;
  enrollment_batch_id?: string | null;
  enrolled_by?: string | null;
  status: string;
  parcel_ids: string[];
  parcel_labels: string[];
  assigned_user_ids: string[];
  metadata: Record<string, unknown>;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  launch_context: {
    recommended_navigation: string;
    project_selection_required: boolean;
    active_project_count: number;
    profile_completion: { is_complete_for_home: boolean; missing_fields: string[]; parcel_count: number; soil_profile_count: number };
    bootstrap_endpoint: string;
    launch_context_endpoint: string;
  };
}

export interface ProjectEnrollmentReportResponse {
  schema_version: string;
  tenant_id: string;
  filters: { project_id?: string | null; farmer_id?: string | null; status?: string | null; enrollment_source?: string | null; q?: string; limit: number };
  summary: {
    count: number;
    active_count: number;
    pending_count: number;
    archived_count: number;
    project_picker_count: number;
    profile_completion_count: number;
    by_status: Record<string, number>;
    by_source: Record<string, number>;
    by_recommended_navigation: Record<string, number>;
  };
  enrollments: ProjectEnrollmentReportRow[];
}

export interface ProjectEnrollmentReportParams {
  query?: string;
  projectId?: string;
  farmerId?: string;
  status?: string;
  enrollmentSource?: string;
  limit?: number;
}

export interface AdminLookupResponse {
  schema_version: string;
  tenant_id: string;
  query: string;
  filters?: { project_id?: string | null; geometry_status?: string | null; geometry_source?: string | null };
  limit: number;
  projects: AdminLookupProject[];
  farmers: AdminLookupFarmer[];
  parcels: AdminLookupParcel[];
}
export interface ProjectTraceFilterOptionsResponse {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  farmers: Array<{ id: string; label: string }>;
  parcels: Array<{ id: string; label: string; farmer_id: string }>;
  crops: string[];
  seasons: string[];
  cycle_statuses: string[];
  stages: Array<{ code: string; label: string }>;
  activity_types: string[];
  inputs: Array<{ code: string; label: string }>;
  products: Array<{ code: string; label: string }>;
}
export interface ProjectTraceResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, string | number | boolean | null>;
  project: { id: string; name: string; status?: string | null; start_date?: string | null; end_date?: string | null; crop_scope: string[] };
  summary: {
    farmer_count: number;
    parcel_count: number;
    crop_cycle_count: number;
    active_cycle_count: number;
    completed_cycle_count: number;
    activity_count: number;
    total_cost: string;
    variance_count: number;
    geometry_captured_count: number;
    geometry_missing_count: number;
  };
  crop_distribution: Array<{ crop_code: string; crop_cycle_count: number }>;
  cycle_status_distribution: Array<{ status: string; crop_cycle_count: number }>;
  geometry_coverage: Array<{ geometry_source: string; parcel_count: number }>;
  activity_count_by_type: Array<{ activity_type: string; activity_count: number }>;
  activity_count_by_crop_stage: Array<{ crop_code: string; stage_code: string; activity_count: number }>;
  enrollment_lifecycle: {
    schema_version: string;
    status_counts: Array<{ status: string; count: number }>;
    active_pending_count: number;
    has_open_enrollments: boolean;
    total_enrollment_count: number;
    latest_event?: { id: string; action: string; actor_id: string; reason?: string | null; created_at?: string | null; after: Record<string, unknown> } | null;
    events: Array<{ id: string; action: string; actor_id: string; reason?: string | null; created_at?: string | null; before: Record<string, unknown>; after: Record<string, unknown>; patch: Record<string, unknown> }>;
    project_enrollments_url: string;
  };
  farmers: Array<AdminLookupFarmer & { parcel_count: number }>;
  parcels: AdminLookupParcel[];
  crop_cycles: FarmerTraceCycle[];
  activities: ActivityUsageRow[];
}


export interface SyncHealthEventRow {
  event_id: string;
  entity_type: string;
  entity_id?: string | null;
  operation?: string | null;
  status?: string | null;
  server_version?: number | null;
  processed_at?: string | null;
  materialized?: boolean | null;
  trace_url?: string | null;
}

export interface SyncMaterializationHealthResponse {
  schema_version: string;
  tenant_id: string;
  filters: { project_id?: string | null; entity_type?: string | null; status?: string | null; gap_only?: boolean; limit: number };
  summary: {
    event_count: number;
    committed_count: number;
    failed_count: number;
    conflict_count: number;
    dependency_missing_count: number;
    farmer_count: number;
    parcel_count: number;
    geometry_captured_count: number;
    geometry_missing_count: number;
    audit_chain_count: number;
    latest_audit_at?: string | null;
  };
  status_counts: Array<{ status: string; event_count: number }>;
  entity_counts: Array<{ entity_type: string; event_count: number }>;
  materialization: Array<{ entity_type: string; committed_count: number; materialized_count: number; unmaterialized_count: number }>;
  recent_events: SyncHealthEventRow[];
}

export interface SystemReadinessCheck {
  code: string;
  label: string;
  ready: boolean;
  severity: "OK" | "WARN" | "INFO";
  detail: string;
  href: string;
}

export interface SystemReadinessResponse {
  schema_version: string;
  tenant_id: string;
  filters: { project_id?: string | null };
  summary: { ready_count: number; check_count: number; blocking_count: number; info_count: number };
  checks: SystemReadinessCheck[];
}

export interface AdminDashboardResponse {
  schema_version: string;
  tenant_id: string;
  filters: { project_id?: string | null; date_from?: string | null; date_to?: string | null; limit: number };
  summary: {
    project_count: number;
    farmer_count: number;
    parcel_count: number;
    crop_cycle_count: number;
    active_cycle_count: number;
    completed_cycle_count: number;
    activity_count: number;
    field_event_count?: number;
  query_thread_count?: number;
  open_query_count?: number;
  urgent_open_query_count?: number;
    unresolved_field_event_count?: number;
    high_priority_field_event_count?: number;
    total_cost: string;
    variance_count: number;
    geometry_captured_count: number;
    geometry_missing_count: number;
    admin_backlog?: {
      draft_workflow_count: number;
      workflow_validation_blocker_count: number;
      unvalidated_draft_workflow_count: number;
      stale_validation_count: number;
      workflow_validation_error_count: number;
      input_review_count: number;
      input_draft_count: number;
      input_rejected_count: number;
      csv_import_pending_count: number;
      product_csv_import_pending_count?: number;
      product_csv_import_invalid_count?: number;
      project_enrollment_csv_import_pending_count?: number;
      project_enrollment_csv_import_invalid_count?: number;
      broadcast_draft_count?: number;
      broadcast_published_count?: number;
      broadcast_pending_delivery_count?: number;
      weather_provider_enabled_count?: number;
      weather_provider_due_count?: number;
      weather_fresh_snapshot_count?: number;
    };
  };
  crop_distribution: Array<{ crop_code: string; crop_cycle_count: number }>;
  cycle_status_distribution: Array<{ status: string; crop_cycle_count: number }>;
  geometry_coverage: Array<{ geometry_source: string; parcel_count: number }>;
  activity_count_by_type: Array<{ activity_type: string; activity_count: number }>;
  field_event_count_by_type?: Array<{ event_type: string; field_event_count: number }>;
  field_event_count_by_severity?: Array<{ severity: string; field_event_count: number }>;
  recent_field_events?: Array<{ id: string; project_id?: string | null; farmer_id: string; parcel_id?: string | null; crop_cycle_id?: string | null; stage_code?: string | null; event_type: string; severity: string; status: string; event_date: string; reported_at: string; description?: string | null }>;
  projects: AdminLookupProject[];
  farmers: AdminLookupFarmer[];
  parcels: AdminLookupParcel[];
  activities: ActivityUsageRow[];
}

export interface ActivityUsageFilterOption {
  id?: string;
  code?: string;
  label: string;
}

export interface ActivityUsageFilterOptionsResponse {
  schema_version: string;
  tenant_id: string;
  projects: ActivityUsageFilterOption[];
  farmers: ActivityUsageFilterOption[];
  parcels: ActivityUsageFilterOption[];
  crops: string[];
  seasons: string[];
  stages: ActivityUsageFilterOption[];
  activity_types: string[];
  inputs: ActivityUsageFilterOption[];
  products: ActivityUsageFilterOption[];
}
type AdminDashboardParams = { projectId?: string; dateFrom?: string; dateTo?: string; limit?: number };
type SyncHealthParams = { projectId?: string; entityType?: string; status?: string; gapOnly?: boolean; limit?: number };
type AdminLookupParams = { query?: string; projectId?: string; geometryStatus?: string; geometrySource?: string; limit?: number };
type ActivityUsageParams = { projectId?: string; farmerId?: string; parcelId?: string; cropCode?: string; seasonCode?: string; stageCode?: string; activityType?: string; inputCode?: string; productCode?: string; dateFrom?: string; dateTo?: string; limit?: number };
type ProjectTraceParams = { farmerId?: string; parcelId?: string; cropCode?: string; seasonCode?: string; stageCode?: string; activityType?: string; inputCode?: string; productCode?: string; cycleStatus?: string; hasVariance?: string; dateFrom?: string; dateTo?: string; limit?: number };




function syncHealthQuery(params?: SyncHealthParams): string {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.entityType) query.set("entity_type", params.entityType);
  if (params?.status) query.set("status", params.status);
  if (params?.gapOnly) query.set("gap_only", "true");
  if (params?.limit) query.set("limit", String(params.limit));
  return query.toString() ? `?${query.toString()}` : "";
}


function projectEnrollmentReportQuery(params?: ProjectEnrollmentReportParams): string {
  const query = new URLSearchParams();
  if (params?.query) query.set("q", params.query);
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.farmerId) query.set("farmer_id", params.farmerId);
  if (params?.status) query.set("status", params.status);
  if (params?.enrollmentSource) query.set("enrollment_source", params.enrollmentSource);
  query.set("limit", String(params?.limit || 50));
  return `?${query.toString()}`;
}

function adminLookupQuery(params?: AdminLookupParams): string {
  const query = new URLSearchParams();
  query.set("q", params?.query || "");
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.geometryStatus) query.set("geometry_status", params.geometryStatus);
  if (params?.geometrySource) query.set("geometry_source", params.geometrySource);
  query.set("limit", String(params?.limit || 25));
  return `?${query.toString()}`;
}

function adminDashboardQuery(params?: AdminDashboardParams): string {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  if (params?.limit) query.set("limit", String(params.limit));
  return query.toString() ? `?${query.toString()}` : "";
}

function systemReadinessQuery(params?: { projectId?: string }): string {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  return query.toString() ? `?${query.toString()}` : "";
}

function activityUsageQuery(params?: ActivityUsageParams): string {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.farmerId) query.set("farmer_id", params.farmerId);
  if (params?.parcelId) query.set("parcel_id", params.parcelId);
  if (params?.cropCode) query.set("crop_code", params.cropCode);
  if (params?.seasonCode) query.set("season_code", params.seasonCode);
  if (params?.stageCode) query.set("stage_code", params.stageCode);
  if (params?.activityType) query.set("activity_type", params.activityType);
  if (params?.inputCode) query.set("input_code", params.inputCode);
  if (params?.productCode) query.set("product_code", params.productCode);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  if (params?.limit) query.set("limit", String(params.limit));
  return query.toString() ? `?${query.toString()}` : "";
}

function projectTraceQuery(params?: ProjectTraceParams): string {
  const query = new URLSearchParams();
  if (params?.farmerId) query.set("farmer_id", params.farmerId);
  if (params?.parcelId) query.set("parcel_id", params.parcelId);
  if (params?.cropCode) query.set("crop_code", params.cropCode);
  if (params?.seasonCode) query.set("season_code", params.seasonCode);
  if (params?.stageCode) query.set("stage_code", params.stageCode);
  if (params?.activityType) query.set("activity_type", params.activityType);
  if (params?.inputCode) query.set("input_code", params.inputCode);
  if (params?.productCode) query.set("product_code", params.productCode);
  if (params?.cycleStatus) query.set("cycle_status", params.cycleStatus);
  if (params?.hasVariance) query.set("has_variance", params.hasVariance);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  if (params?.limit) query.set("limit", String(params.limit));
  return query.toString() ? `?${query.toString()}` : "";
}


export const cropCatalogApi = {
  taxonomy: () => api<CropTaxonomyResponse>("/api/v1/crop-catalog/taxonomy"),
  propagationTypes: () => api<CropPropagationTypeDto[]>("/api/v1/crop-catalog/propagation-types"),
  crops: (params?: { taxonomyCode?: string; propagationType?: string; season?: string }) => {
    const query = new URLSearchParams();
    if (params?.taxonomyCode) query.set("taxonomy_code", params.taxonomyCode);
    if (params?.propagationType) query.set("propagation_type", params.propagationType);
    if (params?.season) query.set("season", params.season);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<CropCatalogResponse>(`/api/v1/crop-catalog/crops${suffix}`);
  },
  downloadCropTemplate: () => apiDownload("/api/v1/crop-catalog/csv/crops/template", "agri-os-crops-template.csv"),
  downloadCropExport: () => apiDownload("/api/v1/crop-catalog/csv/crops/export", "agri-os-crops.csv"),
  validateCropCsv: (file: File) => apiUpload<CropCatalogCsvValidationResponse>("/api/v1/crop-catalog/csv/crops/validate", file),
  cropImportHistory: (params?: { status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<CropCatalogImportHistory>(`/api/v1/crop-catalog/csv/crops/imports${suffix}`);
  },
  applyCropImport: (batchId: string, reason: string) =>
    api<CropCatalogImportBatch>(`/api/v1/crop-catalog/csv/crops/imports/${batchId}/apply`, { method: "POST", body: { reason } }),
  downloadTaxonomyTemplate: () => apiDownload("/api/v1/crop-catalog/csv/taxonomy/template", "agri-os-crop-taxonomy-template.csv"),
  downloadTaxonomyExport: () => apiDownload("/api/v1/crop-catalog/csv/taxonomy/export", "agri-os-crop-taxonomy.csv"),
  validateTaxonomyCsv: (file: File) => apiUpload<CropTaxonomyCsvValidationResponse>("/api/v1/crop-catalog/csv/taxonomy/validate", file),
  taxonomyImportHistory: (params?: { status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<CropTaxonomyImportHistory>(`/api/v1/crop-catalog/csv/taxonomy/imports${suffix}`);
  },
  applyTaxonomyImport: (batchId: string, reason: string) =>
    api<CropTaxonomyImportBatch>(`/api/v1/crop-catalog/csv/taxonomy/imports/${batchId}/apply`, { method: "POST", body: { reason } }),
  downloadPropagationTemplate: () => apiDownload("/api/v1/crop-catalog/csv/propagation-types/template", "agri-os-crop-propagation-template.csv"),
  downloadPropagationExport: () => apiDownload("/api/v1/crop-catalog/csv/propagation-types/export", "agri-os-crop-propagation.csv"),
  validatePropagationCsv: (file: File) => apiUpload<CropPropagationCsvValidationResponse>("/api/v1/crop-catalog/csv/propagation-types/validate", file),
  propagationImportHistory: (params?: { status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<CropPropagationImportHistory>(`/api/v1/crop-catalog/csv/propagation-types/imports${suffix}`);
  },
  applyPropagationImport: (batchId: string, reason: string) =>
    api<CropPropagationImportBatch>(`/api/v1/crop-catalog/csv/propagation-types/imports/${batchId}/apply`, { method: "POST", body: { reason } }),
};

export const farmersApi = {
  profileReadiness: (params?: { projectId?: string; status?: string; offset?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.projectId) q.set("project_id", params.projectId);
    if (params?.status !== undefined) q.set("status", params.status);
    if (params?.offset !== undefined) q.set("offset", String(params.offset));
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<FarmerProfileReadinessResponse>(`/api/v1/farmers/profile-readiness${suffix}`);
  },
};

export const reportsApi = {
  adminDashboard: (params?: AdminDashboardParams) => api<AdminDashboardResponse>(`/api/v1/reports/admin-dashboard${adminDashboardQuery(params)}`),
  systemReadiness: (params?: { projectId?: string }) => api<SystemReadinessResponse>(`/api/v1/reports/system-readiness${systemReadinessQuery(params)}`),
  syncHealth: (params?: SyncHealthParams) => api<SyncMaterializationHealthResponse>(`/api/v1/reports/sync-health${syncHealthQuery(params)}`),
  downloadSyncHealthCsv: (params?: SyncHealthParams) =>
    apiDownload(`/api/v1/reports/sync-health.csv${syncHealthQuery(params)}`, params?.gapOnly ? "sync_health_gaps.csv" : "sync_health.csv"),
  projectInputCompliance: (projectId: string) => api<ProjectInputComplianceResponse>(`/api/v1/reports/projects/${projectId}/input-compliance`),
  projectTrace: (projectId: string, params?: ProjectTraceParams) => api<ProjectTraceResponse>(`/api/v1/reports/projects/${projectId}/trace${projectTraceQuery(params)}`),
  projectTraceFilterOptions: (projectId: string) => api<ProjectTraceFilterOptionsResponse>(`/api/v1/reports/projects/${projectId}/trace/filter-options`),
  productTrace: (productCode: string) => api<ProductTraceResponse>(`/api/v1/reports/products/${encodeURIComponent(productCode)}/trace`),
  inputRuleTrace: (ruleId: string) => api<InputRuleTraceResponse>(`/api/v1/reports/input-rules/${ruleId}/trace`),
  cropCycleTrace: (cycleId: string) => api<CropCycleTraceResponse>(`/api/v1/reports/crop-cycles/${cycleId}/trace`),
  farmerTrace: (farmerId: string) => api<FarmerTraceResponse>(`/api/v1/reports/farmers/${farmerId}/trace`),
  parcelTrace: (parcelId: string) => api<ParcelTraceResponse>(`/api/v1/reports/parcels/${parcelId}/trace`),
  projectEnrollments: (params?: ProjectEnrollmentReportParams) => api<ProjectEnrollmentReportResponse>(`/api/v1/reports/project-enrollments${projectEnrollmentReportQuery(params)}`),
  lookup: (params?: string | AdminLookupParams, limit = 25) => {
    const queryParams = typeof params === "string" ? { query: params, limit } : params;
    return api<AdminLookupResponse>(`/api/v1/reports/lookup${adminLookupQuery(queryParams)}`);
  },
  downloadLookupCsv: (params?: string | AdminLookupParams, limit = 100) => {
    const queryParams = typeof params === "string" ? { query: params, limit } : { ...params, limit: params?.limit || limit };
    return apiDownload(`/api/v1/reports/lookup.csv${adminLookupQuery(queryParams)}`, "admin_lookup.csv");
  },
  downloadProjectTraceCsv: (projectId: string, params?: ProjectTraceParams) =>
    apiDownload(`/api/v1/reports/projects/${projectId}/trace.csv${projectTraceQuery(params)}`, "project_trace.csv"),
  activityUsageFilterOptions: () => api<ActivityUsageFilterOptionsResponse>("/api/v1/reports/activity-usage/filter-options"),
  activityUsage: (params?: ActivityUsageParams) =>
    api<ActivityUsageReportResponse>(`/api/v1/reports/activity-usage${activityUsageQuery(params)}`),
  downloadActivityUsageCsv: (params?: ActivityUsageParams) =>
    apiDownload(`/api/v1/reports/activity-usage.csv${activityUsageQuery(params)}`, "activity_usage.csv"),
};
// --- Typed API functions ---

export interface Tenant {
  id: string;
  name: string;
  type: string;
  is_active: boolean;
}

export interface Project {
  id: string;
  tenant_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  geography_scope: Record<string, unknown>;
  crop_scope: string[];
}

export interface SyncHealth {
  total_events_processed: number;
  committed: number;
  conflicts_pending: number;
  conflicts_resolved: number;
  failed: number;
  last_sync_at: string | null;
  audit_chain_length: number;
  audit_chain_intact: boolean;
}

export interface Dashboard {
  tenant_id: string;
  sync_health: SyncHealth;
  generated_at: string;
}

export interface Conflict {
  id: string;
  event_id: string;
  entity_type: string;
  entity_id: string;
  conflict_type: string;
  client_payload: Record<string, unknown>;
  server_payload: Record<string, unknown> | null;
  resolution_strategy: string | null;
  status: string;
  created_at: string;
}

export interface FormFieldOptionContract {
  value: string;
  label: Record<string, string>;
}

export interface FormFieldContract {
  id: string;
  type: string;
  label: Record<string, string>;
  required: boolean;
  source?: string | null;
  options?: FormFieldOptionContract[] | null;
  depends_on?: string | null;
  depends_on_value?: string | null;
  default_value?: string | null;
  placeholder?: Record<string, string> | null;
  validation?: Record<string, unknown> | null;
  hint?: Record<string, string> | null;
  canonical_field?: string | null;
  android_hint?: Record<string, unknown> | null;
  capture_modes?: string[] | null;
  output_format?: string | null;
  min_points?: number | null;
  accuracy_required_meters?: number | null;
  allow_offline_capture?: boolean;
}

export interface FormSchemaContract {
  form_id: string;
  version: string;
  title: Record<string, string>;
  description?: Record<string, string> | null;
  fields: FormFieldContract[];
  submit_endpoint: string;
  submit_method: string;
  submit_label?: Record<string, string> | null;
}

export interface ProfileFormContractSummary {
  form_id: string;
  version: string;
  endpoint: string;
  enabled: boolean;
  feature_flag: string;
  title: Record<string, string>;
}

export interface AppBootstrapResponse {
  schema_version: string;
  generated_at: string;
  tenant: { id: string; exists: boolean; name: string; type: string };
  project?: { id: string; name: string; status: string } | null;
  feature_flags: Record<string, boolean>;
  profile_forms: Record<string, ProfileFormContractSummary>;
  forms: Array<{ form_id: string; version: string; title: Record<string, string>; endpoint: string }>;
  branding: Record<string, unknown>;
  localization: Record<string, unknown>;
  units: Record<string, unknown>;
  enabled_modules: string[];
  self_service: Record<string, unknown>;
  contracts?: Record<string, unknown>;
}

export interface EffectiveAppConfigResponse {
  schema_version: string;
  generated_at: string;
  tenant: { id: string; name: string; type: string };
  project: { id: string; name: string; status: string; crop_scope?: string[]; geography_scope?: Record<string, unknown> };
  layers: { default: Record<string, unknown>; tenant: Record<string, unknown>; project: Record<string, unknown> };
  effective_config: Record<string, unknown>;
  section_sources: Record<string, string>;
  profile_forms: Record<string, ProfileFormContractSummary>;
  forms: Array<{ form_id: string; version: string; title: Record<string, string>; endpoint: string }>;
}

export interface ProjectAppConfigAuditEvent {
  id: string;
  tenant_id: string;
  project_id: string;
  actor_id: string;
  action: string;
  patched_sections: string[];
  before_config: Record<string, unknown>;
  after_config: Record<string, unknown>;
  config_patch: Record<string, unknown>;
  reason?: string | null;
  created_at?: string | null;
}

export interface ProjectAppConfigAuditResponse {
  schema_version: string;
  tenant_id: string;
  project: { id: string; name: string; status: string };
  count: number;
  events: ProjectAppConfigAuditEvent[];
}

export interface ProfileFormValidationIssue {
  form_id: string;
  field_id?: string | null;
  code: string;
  message: string;
}

export interface ProfileFormValidationForm {
  form_id: string;
  title?: Record<string, string>;
  version?: string;
  enabled: boolean;
  ready: boolean;
  field_count: number;
  required_field_count: number;
  gps_field_count: number;
  error_count: number;
  warning_count: number;
}

export interface ProfileFormValidationResponse {
  schema_version: string;
  tenant: { id: string; name: string; type: string };
  project?: { id: string; name: string; status: string } | null;
  filters: { project_id?: string | null };
  ready: boolean;
  summary: { form_count: number; enabled_count: number; error_count: number; warning_count: number; field_count: number; gps_field_count: number };
  forms: ProfileFormValidationForm[];
  errors: ProfileFormValidationIssue[];
  warnings: ProfileFormValidationIssue[];
}

// Auth
export interface AdminProjectAccessProfile {
  project_role_id: string;
  project_id: string;
  project_name: string;
  project_status: string;
  role: string;
  territory_scope: Record<string, unknown>;
  permissions: string[];
}

export interface AdminProfileResponse {
  schema_version: string;
  user_id: string;
  tenant_id: string;
  mobile_number_masked: string;
  display_name?: string | null;
  role: string;
  permissions: string[];
  project_access: AdminProjectAccessProfile[];
}

export const authApi = {
  requestOtp: (mobile_number: string) =>
    api("/api/v1/auth/otp/request", { method: "POST", body: { mobile_number }, noAuth: true }),
  verifyOtp: (mobile_number: string, otp_code: string, device_id: string) =>
    api("/api/v1/auth/otp/verify", { method: "POST", body: { mobile_number, otp_code, device_id }, noAuth: true }),
  me: () => api<AdminProfileResponse>("/api/v1/admin/me"),
};

// Tenants
export const tenantsApi = {
  list: () => api<Tenant[]>("/api/v1/tenants", { noAuth: true }),
  create: (data: { id: string; name: string; type: string }) =>
    api<Tenant>("/api/v1/tenants", { method: "POST", body: data, noAuth: true }),
};

// Projects
export const projectsApi = {
  list: () => api<Project[]>("/api/v1/projects"),
  create: (data: Partial<Project>) => api<Project>("/api/v1/projects", { method: "POST", body: data }),
  assignRole: (projectId: string, data: { user_id: string; role: string; territory_scope: Record<string, unknown> }) =>
    api(`/api/v1/projects/${projectId}/roles`, { method: "POST", body: data }),
  downloadEnrollmentTemplate: (projectId: string) =>
    apiDownload(`/api/v1/projects/${projectId}/farmer-enrollments/csv/template`, "agri-os-project-enrollment-template.csv"),
  validateEnrollmentCsv: (projectId: string, file: File) =>
    apiUpload<ProjectEnrollmentImportBatch>(`/api/v1/projects/${projectId}/farmer-enrollments/csv/validate`, file),
  enrollmentImportHistory: (projectId: string, params?: { status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<ProjectEnrollmentImportHistory>(`/api/v1/projects/${projectId}/farmer-enrollments/csv/imports${suffix}`);
  },
  applyEnrollmentImport: (projectId: string, batchId: string, reason: string) =>
    api<ProjectEnrollmentImportBatch>(`/api/v1/projects/${projectId}/farmer-enrollments/csv/imports/${batchId}/apply`, { method: "POST", body: { reason } }),
  updateEnrollmentStatus: (enrollmentId: string, status: "COMPLETED" | "CANCELLED" | "ARCHIVED" | "ACTIVE" | "PENDING", reason: string) =>
    api(`/api/v1/farmer-project-enrollments/${enrollmentId}/status`, { method: "PATCH", body: { status, reason } }),
  previewEnrollmentLifecycle: (projectId: string, targetStatus: "COMPLETED" | "CANCELLED" | "ARCHIVED" | "ACTIVE" | "PENDING") =>
    api<ProjectEnrollmentLifecyclePreview>(`/api/v1/projects/${projectId}/farmer-enrollments/lifecycle-preview?target_status=${encodeURIComponent(targetStatus)}`),
  applyEnrollmentLifecycle: (projectId: string, targetStatus: "COMPLETED" | "CANCELLED" | "ARCHIVED" | "ACTIVE" | "PENDING", reason: string) =>
    api<ProjectEnrollmentLifecycleApplyResponse>(`/api/v1/projects/${projectId}/farmer-enrollments/lifecycle-apply`, { method: "POST", body: { target_status: targetStatus, reason } }),
};

export const appConfigApi = {
  bootstrap: (projectId?: string) => {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return api<AppBootstrapResponse>(`/api/v1/app-config/bootstrap${suffix}`);
  },
  effectiveProjectConfig: (projectId: string) =>
    api<EffectiveAppConfigResponse>(`/api/v1/app-config/projects/${projectId}/effective-app-config`),
  updateProjectConfig: (projectId: string, configPatch: Record<string, unknown>, reason: string) =>
    api<EffectiveAppConfigResponse>(`/api/v1/app-config/projects/${projectId}/config`, { method: "PATCH", body: { config_patch: configPatch, reason } }),
  projectConfigAudit: (projectId: string, limit = 20) =>
    api<ProjectAppConfigAuditResponse>(`/api/v1/app-config/projects/${projectId}/config/audit?limit=${limit}`),
  profileFormValidation: (projectId?: string) => {
    const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return api<ProfileFormValidationResponse>(`/api/v1/app-config/profile-forms/validation${suffix}`);
  },
  formSchema: (formId: string) => api<FormSchemaContract>(`/api/v1/forms/${formId}`),
};


// Dashboard
export const dashboardApi = {
  getOperational: () => api<Dashboard>("/api/v1/dashboard/operational"),
};

// Conflicts
export const conflictsApi = {
  list: (status?: string) => api<Conflict[]>(`/api/v1/sync/conflicts${status ? `?status=${status}` : ""}`),
  get: (id: string) => api<Conflict>(`/api/v1/sync/conflicts/${id}`),
  resolve: (id: string, strategy: string, comment?: string) =>
    api(`/api/v1/sync/conflicts/${id}`, { method: "PATCH", body: { strategy, comment } }),
};


// Workflow catalog
export interface RecommendationDosageRule { quantity?: string | null; unit?: string | null; area_unit: string; min_quantity?: string | null; max_quantity?: string | null; }

export interface WorkflowRecommendation {
  day_offset: number;
  activity_type: string;
  input_code?: string | null;
  input_name: string;
  typical_quantity?: string | null;
  typical_cost_per_acre?: number | string | null;
  is_critical: boolean;
  description?: Record<string, string> | null;
  metadata?: Record<string, unknown> | null;
  input_rule?: Record<string, unknown> | null;
  recommended_dosage?: RecommendationDosageRule | null;
  allowed_product_codes?: string[];
  allowed_products?: AgriculturalProductDto[];
  rule_application_method?: string | null;
  rule_timing_note?: string | null;
  rule_safety_note?: string | null;
}

export interface WorkflowStage {
  code: string;
  name: Record<string, string> | string;
  order: number;
  day_offset?: number;
  duration_days: number;
  stage_type?: string | null;
  phase?: string | null;
  propagation_step?: boolean;
  recommended_activities?: WorkflowRecommendation[];
}


export interface WorkflowPreviewWarning {
  level: "INFO" | "WARN" | "ERROR" | string;
  code: string;
  message: string;
  target?: string | null;
}

export interface WorkflowDraftFreshness {
  draft_updated_at?: string | null;
  draft_created_at?: string | null;
  last_edited_at?: string | null;
  last_validated_at?: string | null;
  validation_current: boolean;
  validation_stale: boolean;
}

export interface WorkflowDraftValidationResponse {
  schema_version: string;
  tenant_id: string;
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  version: string;
  status: string;
  can_publish: boolean;
  counts: {
    total: number;
    errors: number;
    warnings: number;
    info: number;
    stages: number;
    recommendations: number;
  };
  issues: WorkflowPreviewWarning[];
  issues_by_level: Record<string, WorkflowPreviewWarning[]>;
  freshness?: WorkflowDraftFreshness | null;
}


export interface WorkflowCsvValidationIssue {
  field: string;
  code: string;
  message: string;
}

export interface WorkflowCsvValidationRow {
  row_number: number;
  stage_code: string;
  action: string;
  errors: WorkflowCsvValidationIssue[];
  warnings: WorkflowCsvValidationIssue[];
  normalized: Record<string, unknown>;
}

export interface WorkflowCsvValidationResponse {
  schema_version: string;
  mode: string;
  apply_available: boolean;
  can_apply: boolean;
  tenant_id: string;
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  version: string;
  status: string;
  file_name?: string | null;
  summary: {
    total_rows: number;
    stages: number;
    recommendations: number;
    errors: number;
    warnings: number;
    stage_create: number;
    stage_update: number;
    stage_unchanged: number;
  };
  rows: WorkflowCsvValidationRow[];
  message: string;
}

export interface WorkflowDraftValidationBlocker {
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  workflow_name: string;
  crop_code: string;
  season_code: string;
  propagation_type_code?: string | null;
  version: string;
  status: string;
  reasons: string[];
  can_publish: boolean;
  counts: { total?: number; errors?: number; warnings?: number; info?: number; stages?: number; recommendations?: number };
  freshness: WorkflowDraftFreshness;
  preview_url: string;
  updated_at?: string | null;
  created_at?: string | null;
}

export interface WorkflowDraftValidationBlockersResponse {
  schema_version: string;
  tenant_id: string;
  count: number;
  blockers: WorkflowDraftValidationBlocker[];
}

export interface WorkflowPublishImpactVersion {
  workflow_template_version_id: string;
  version: string;
  status: string;
  action: string;
  pinned_cycle_count: number;
  active_pinned_cycle_count: number;
  is_safe_to_archive: boolean;
  retention_policy: string;
  message: string;
}

export interface WorkflowPublishImpactResponse {
  schema_version: string;
  workflow_template_id: string;
  draft_version_id: string;
  draft_version: string;
  archive_previous: boolean;
  impacted_published_versions: WorkflowPublishImpactVersion[];
  counts: {
    published_versions_impacted: number;
    pinned_cycles_impacted: number;
    active_pinned_cycles_impacted: number;
  };
  can_publish: boolean;
  blocking_reasons: string[];
  safety_message: string;
}

export interface AppliedWorkflowOverride {
  id: string;
  tenant_id?: string;
  project_id?: string | null;
  template_version_id?: string;
  target_type: string;
  target_code: string;
  operation: string;
  priority: number;
  payload: Record<string, unknown>;
  reason?: string | null;
  is_active?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}


export interface WorkflowOverrideHistoryResponse {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  template_version_id?: string | null;
  include_inactive: boolean;
  counts: {
    total: number;
    active: number;
    inactive: number;
  };
  overrides: AppliedWorkflowOverride[];
}


export interface WorkflowOverrideCreateRequest {
  template_version_id: string;
  target_type: "STAGE" | "RECOMMENDATION" | string;
  target_code: string;
  operation: "HIDE" | "RENAME" | "CHANGE_DURATION" | "CHANGE_OFFSET" | "CHANGE_QUANTITY" | "ADD_RECOMMENDATION" | string;
  override_payload?: Record<string, unknown>;
  priority?: number;
  reason?: string | null;
}

export interface WorkflowDraftCloneResponse {
  schema_version: string;
  workflow_template_id: string;
  source_version_id: string;
  draft_version_id: string;
  version: string;
  status: "DRAFT" | string;
  stage_count: number;
  recommendation_count: number;
}

export interface WorkflowTemplateVersionHistoryItem {
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  version: string;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  is_current_published: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  published_at?: string | null;
  published_by?: string | null;
  total_duration_days?: number | null;
  stage_count: number;
  recommendation_count: number;
  pinned_cycle_count?: number;
  active_pinned_cycle_count?: number;
  usage_count?: number;
  active_usage_count?: number;
  is_read_only_for_existing_cycles?: boolean;
  schema_version: string;
  metadata?: Record<string, unknown>;
  media_attachments?: BroadcastMediaAttachmentDto[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkflowTemplateVersionsResponse {
  schema_version: string;
  tenant_id: string;
  workflow_template_id: string;
  workflow_template_code: string;
  label: Record<string, string>;
  crop_code: string;
  season_code: string;
  propagation_type_code?: string | null;
  current_published_version_id?: string | null;
  counts: {
    total: number;
    draft: number;
    published: number;
    archived: number;
  };
  versions: WorkflowTemplateVersionHistoryItem[];
}

export interface WorkflowAuditEvent {
  id: string;
  tenant_id: string;
  workflow_template_id: string;
  workflow_template_version_id?: string | null;
  actor_id?: string | null;
  action: string;
  target_type: string;
  target_id?: string | null;
  target_code?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface WorkflowAuditResponse {
  schema_version: string;
  tenant_id: string;
  workflow_template_id: string;
  workflow_template_code: string;
  count: number;
  events: WorkflowAuditEvent[];
}

export interface WorkflowLegacyCyclePinRow {
  cycle_id: string;
  tenant_id: string;
  project_id?: string | null;
  farmer_id?: string | null;
  parcel_id?: string | null;
  crop_code: string;
  season_code: string;
  status: string;
  planned_sowing_date?: string | null;
  lifecycle_template_id?: string | null;
  workflow_template_id?: string | null;
  workflow_template_code?: string | null;
  workflow_template_version_id?: string | null;
  workflow_template_version?: string | null;
  eligible_for_backfill: boolean;
  reason: string;
}

export interface WorkflowLegacyCyclePinsResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  counts: {
    total: number;
    eligible: number;
    blocked: number;
    by_reason: Record<string, number>;
  };
  cycles: WorkflowLegacyCyclePinRow[];
}

export interface WorkflowLegacyCycleBackfillResponse {
  schema_version: string;
  tenant_id: string;
  dry_run: boolean;
  requested_limit: number;
  counts: {
    scanned: number;
    eligible: number;
    pinned: number;
    blocked: number;
  };
  cycles: WorkflowLegacyCyclePinRow[];
}

export interface WorkflowDraftStageUpdateRequest {
  stage_name?: Record<string, string>;
  duration_days?: number;
  description?: Record<string, string>;
  farmer_actions?: string[];
  typical_inputs?: string[];
  key_observations?: string[];
  icon?: string | null;
  color?: string | null;
  phase?: string | null;
  stage_type?: string | null;
}

export interface WorkflowDraftStageCreateRequest {
  after_stage_code?: string | null;
  stage_code: string;
  stage_name: Record<string, string>;
  duration_days?: number;
  description?: Record<string, string> | null;
  farmer_actions?: string[];
  typical_inputs?: string[];
  key_observations?: string[];
  icon?: string | null;
  color?: string | null;
  phase?: string | null;
  stage_type?: string | null;
}

export interface WorkflowDraftStageDuplicateRequest {
  after_stage_code?: string | null;
  stage_code?: string | null;
  stage_name?: Record<string, string> | null;
}

export interface WorkflowDraftStageReorderRequest {
  stage_codes: string[];
}

export interface WorkflowDeletedStageRow {
  template_stage_id: string;
  stage_code: string;
  stage_name: Record<string, string>;
  stage_order?: number | null;
  duration_days?: number | null;
  stage_type?: string | null;
  phase?: string | null;
  recommendation_count: number;
  updated_at?: string | null;
}

export interface WorkflowDeletedStagesResponse {
  schema_version: string;
  tenant_id: string;
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  count: number;
  deleted_stages: WorkflowDeletedStageRow[];
}

export interface WorkflowDraftRecommendationRequest {
  day_offset?: number;
  input_source?: "CATALOG" | "CUSTOM";
  activity_type?: string;
  input_code?: string | null;
  input_name?: string;
  typical_quantity?: string | null;
  typical_cost_per_acre?: number | null;
  is_critical?: boolean;
  description?: Record<string, string> | null;
  sort_order?: number;
}

export interface WorkflowDraftRecommendationReorderRequest {
  stage_code: string;
  recommendation_ids: string[];
}

export interface WorkflowPreviewResponse {
  schema_version: string;
  tenant_id: string;
  project_id?: string | null;
  preview_source: string;
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  version: string;
  status: string;
  enablement_source: string;
  label: Record<string, string>;
  crop_code: string;
  crop_name: string;
  season_code: string;
  catalog_selection_key?: string;
  catalog_selection_policy?: string;
  propagation_type_code?: string | null;
  total_duration_days: number;
  applied_overrides: AppliedWorkflowOverride[];
  warnings: WorkflowPreviewWarning[];
  version_created_at?: string | null;
  version_updated_at?: string | null;
  draft_freshness?: WorkflowDraftFreshness | null;
  publish_impact?: WorkflowPublishImpactResponse;
  android_preview: {
    crop_code: string;
    crop_name: string;
    season_code: string;
    total_duration_days: number;
    propagation_method?: string | null;
    stages: WorkflowStage[];
  };
}


export interface WorkflowSafeEditLifecycle {
  schema_version: string;
  project_id: string;
  tenant_id: string;
  project_status: string;
  can_edit_project_workflows: boolean;
  lock_state: "OPEN" | "LOCKED" | string;
  locked_operations: string[];
  allowed_operations: string[];
  counts: {
    farmers: number;
    parcels: number;
    crop_cycles: number;
    active_crop_cycles: number;
  };
  reasons: Array<{ code: string; message: string }>;
  warnings: Array<{ code: string; message: string }>;
  suggested_action?: string | null;
}

export interface ProjectWorkflowEnablementItem {
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  version: string;
  status: string;
  visibility_status: "ENABLED" | "DISABLED" | "IMPLICIT_DEFAULT" | "NOT_VISIBLE" | "CROP_SCOPE_BLOCKED" | string;
  assignment_rule?: string;
  assignment_reason?: string;
  crop_scope_allowed?: boolean;
  enablement_scope: "project" | "tenant" | "implicit_default" | string;
  enabled: boolean;
  configured_enabled?: boolean;
  display_order?: number | null;
  label: Record<string, string>;
  crop_code: string;
  crop_name: string;
  season_code: string;
  propagation_type_code?: string | null;
  total_duration_days?: number | null;
  usage_count?: number;
  active_usage_count?: number;
  override_count: number;
  overrides: AppliedWorkflowOverride[];
}


export interface ProjectWorkflowAssignmentAuditResponse {
  schema_version: string;
  tenant_id: string;
  project: {
    id: string;
    name: string;
    status: string;
  };
  count: number;
  events: WorkflowAuditEvent[];
}

export interface ProjectWorkflowEnablementsResponse {
  schema_version: string;
  tenant_id: string;
  project: {
    id: string;
    name: string;
    status: string;
    crop_scope: string[];
    start_date?: string | null;
    end_date?: string | null;
  };
  explicit_scope: boolean;
  safe_edit_lifecycle: WorkflowSafeEditLifecycle;
  counts: {
    total: number;
    enabled: number;
    disabled: number;
    implicit_default: number;
    not_visible: number;
    crop_scope_blocked?: number;
    android_visible?: number;
  };
  workflows: ProjectWorkflowEnablementItem[];
}

export interface EnabledCropWorkflow {
  workflow_template_id: string;
  workflow_template_version_id: string;
  workflow_template_code: string;
  version: string;
  status: string;
  tenant_id: string;
  project_id?: string | null;
  enabled: boolean;
  enablement_source: string;
  display_order?: number | null;
  label: Record<string, string>;
  crop_code: string;
  crop_name: string;
  season_code: string;
  propagation_type_code?: string | null;
  total_duration_days?: number | null;
  metadata?: Record<string, unknown>;
  stages?: WorkflowStage[];
}

export interface EnabledWorkflowCatalogResponse {
  schema_version: string;
  tenant_id: string;
  project_id?: string | null;
  count: number;
  workflows: EnabledCropWorkflow[];
}

export const workflowCatalogApi = {
  downloadWorkflowCsvTemplate: () => apiDownload("/api/v1/workflow-catalog/csv/workflows/template", "agri-os-workflow-template.csv"),
  downloadWorkflowCsvExport: (params?: { templateVersionId?: string; cropCode?: string; seasonCode?: string; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.templateVersionId) query.set("template_version_id", params.templateVersionId);
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.seasonCode) query.set("season_code", params.seasonCode);
    if (params?.status) query.set("status", params.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiDownload(`/api/v1/workflow-catalog/csv/workflows/export${suffix}`, "agri-os-workflows.csv");
  },
  enabledCropWorkflows: (params?: { projectId?: string; cropCode?: string; season?: string; includeStages?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.projectId) query.set("project_id", params.projectId);
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.projectId) query.set("project_id", params.projectId);
    if (params?.season) query.set("season", params.season);
    if (params?.includeStages) query.set("include_stages", "true");
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<EnabledWorkflowCatalogResponse>(`/api/v1/workflow-catalog/enabled-crop-workflows${suffix}`);
  },
  preview: (versionId: string, params?: { projectId?: string }) => {
    const query = new URLSearchParams();
    if (params?.projectId) query.set("project_id", params.projectId);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/workflow-preview/${versionId}${suffix}`);
  },
  templateVersions: (templateId: string) =>
    api<WorkflowTemplateVersionsResponse>(`/api/v1/workflow-catalog/templates/${templateId}/versions`),
  legacyCyclePins: (params?: { cropCode?: string; seasonCode?: string; projectId?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.seasonCode) query.set("season_code", params.seasonCode);
    if (params?.projectId) query.set("project_id", params.projectId);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<WorkflowLegacyCyclePinsResponse>(`/api/v1/workflow-catalog/legacy-cycle-pins${suffix}`);
  },
  backfillLegacyCyclePins: (data: { dry_run?: boolean; crop_code?: string; season_code?: string; project_id?: string; limit?: number; reason?: string }) =>
    api<WorkflowLegacyCycleBackfillResponse>("/api/v1/workflow-catalog/legacy-cycle-pins/backfill", {
      method: "POST",
      body: data,
    }),
  templateAudit: (templateId: string, params?: { versionId?: string; action?: string; excludeAction?: string; actorId?: string; since?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.versionId) query.set("version_id", params.versionId);
    if (params?.action) query.set("action", params.action);
    if (params?.excludeAction) query.set("exclude_action", params.excludeAction);
    if (params?.actorId) query.set("actor_id", params.actorId);
    if (params?.since) query.set("since", params.since);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<WorkflowAuditResponse>(`/api/v1/workflow-catalog/templates/${templateId}/audit${suffix}`);
  },
  cloneDraftVersion: (templateId: string, versionId: string, data?: { version_number?: string }) =>
    api<WorkflowDraftCloneResponse>(`/api/v1/workflow-catalog/templates/${templateId}/versions/${versionId}/clone-draft`, {
      method: "POST",
      body: data || {},
    }),
  restoreDraftVersion: (templateId: string, versionId: string, data?: { version_number?: string }) =>
    api<WorkflowDraftCloneResponse>(`/api/v1/workflow-catalog/templates/${templateId}/versions/${versionId}/restore-draft`, {
      method: "POST",
      body: data || {},
    }),

  draftValidationBlockers: (params?: { limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<WorkflowDraftValidationBlockersResponse>(`/api/v1/workflow-catalog/drafts/validation-blockers${suffix}`);
  },
  draftPreview: (versionId: string) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/draft-preview/${versionId}`),
  validateDraftVersion: (versionId: string) =>
    api<WorkflowDraftValidationResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/validation`),
  validateWorkflowCsvAgainstDraft: (versionId: string, file: File) =>
    apiUpload<WorkflowCsvValidationResponse>(`/api/v1/workflow-catalog/csv/workflows/drafts/${versionId}/validate`, file),
  applyWorkflowCsvToDraft: (versionId: string, file: File, reason: string) =>
    apiUploadWithFields<WorkflowCsvValidationResponse>(`/api/v1/workflow-catalog/csv/workflows/drafts/${versionId}/apply`, file, { reason }),
  deletedDraftStages: (versionId: string) =>
    api<WorkflowDeletedStagesResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/deleted-stages`),
  draftPublishImpact: (versionId: string, params?: { archivePrevious?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.archivePrevious !== undefined) query.set("archive_previous", String(params.archivePrevious));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<WorkflowPublishImpactResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/publish-impact${suffix}`);
  },
  publishDraftVersion: (versionId: string, data?: { archive_previous?: boolean }) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/publish`, {
      method: "POST",
      body: data || {},
    }),
  updateDraftStage: (versionId: string, stageCode: string, data: WorkflowDraftStageUpdateRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages/${stageCode}`, {
      method: "PATCH",
      body: data,
    }),
  createDraftStage: (versionId: string, data: WorkflowDraftStageCreateRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages`, {
      method: "POST",
      body: data,
    }),
  duplicateDraftStage: (versionId: string, stageCode: string, data: WorkflowDraftStageDuplicateRequest = {}) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages/${encodeURIComponent(stageCode)}/duplicate`, {
      method: "POST",
      body: data,
    }),
  reorderDraftStages: (versionId: string, data: WorkflowDraftStageReorderRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages/reorder`, {
      method: "PATCH",
      body: data,
    }),
  deleteDraftStage: (versionId: string, stageCode: string) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages/${encodeURIComponent(stageCode)}`, {
      method: "DELETE",
    }),
  restoreDraftStage: (versionId: string, stageCode: string, data?: { after_stage_code?: string | null }) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages/${encodeURIComponent(stageCode)}/restore`, {
      method: "POST",
      body: data || {},
    }),
  createDraftRecommendation: (versionId: string, stageCode: string, data: WorkflowDraftRecommendationRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/stages/${stageCode}/recommendations`, {
      method: "POST",
      body: data,
    }),
  updateDraftRecommendation: (versionId: string, recommendationId: string, data: WorkflowDraftRecommendationRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/recommendations/${recommendationId}`, {
      method: "PATCH",
      body: data,
    }),
  reorderDraftRecommendations: (versionId: string, data: WorkflowDraftRecommendationReorderRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/recommendations/reorder`, {
      method: "PATCH",
      body: data,
    }),
  deleteDraftRecommendation: (versionId: string, recommendationId: string) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/recommendations/${recommendationId}`, {
      method: "DELETE",
    }),
  projectEnablements: (projectId: string) =>
    api<ProjectWorkflowEnablementsResponse>(`/api/v1/workflow-catalog/projects/${projectId}/workflow-enablements`),
  projectEnablementAudit: (projectId: string, params?: { limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<ProjectWorkflowAssignmentAuditResponse>(`/api/v1/workflow-catalog/projects/${projectId}/workflow-enablements/audit${suffix}`);
  },
  updateProjectEnablement: (
    projectId: string,
    workflowTemplateId: string,
    data: { enabled: boolean; display_order?: number | null; display_label?: Record<string, string> | null; reason?: string | null }
  ) =>
    api<ProjectWorkflowEnablementsResponse>(
      `/api/v1/workflow-catalog/projects/${projectId}/workflow-enablements/${workflowTemplateId}`,
      { method: "PUT", body: data }
    ),
  createProjectOverride: (projectId: string, data: WorkflowOverrideCreateRequest) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/projects/${projectId}/workflow-overrides`, {
      method: "POST",
      body: data,
    }),
  deleteProjectOverride: (projectId: string, overrideId: string) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/projects/${projectId}/workflow-overrides/${overrideId}`, {
      method: "DELETE",
    }),
  projectOverrideHistory: (projectId: string, params?: { templateVersionId?: string; includeInactive?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.templateVersionId) query.set("template_version_id", params.templateVersionId);
    if (params?.includeInactive !== undefined) query.set("include_inactive", String(params.includeInactive));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<WorkflowOverrideHistoryResponse>(`/api/v1/workflow-catalog/projects/${projectId}/workflow-overrides${suffix}`);
  },
};

// Input catalog
export interface InputCategoryDto {
  id: string;
  code: string;
  canonical_name: string;
  description?: string | null;
  aliases: Array<Record<string, string>>;
  is_active?: boolean;
}

export interface AgriInputDto {
  id: string;
  code: string;
  category_code?: string | null;
  category_name?: string | null;
  canonical_name: string;
  brand_name?: string | null;
  composition?: string | null;
  unit: string;
  standard_weight?: string | null;
  applicable_crops: string[];
  application_method?: string | null;
  safety_instructions?: string | null;
  aliases: Array<Record<string, string>>;
  catalog_status: "DRAFT" | "REVIEW" | "PUBLISHED" | "REJECTED" | string;
  submitted_at?: string | null;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  review_reason?: string | null;
  is_active?: boolean;
}

export interface InputValidationFinding {
  field: string;
  code: string;
  message: string;
}

export interface InputGovernanceResponse {
  schema_version?: string;
  input: AgriInputDto;
  validation: {
    can_submit: boolean;
    can_publish: boolean;
    counts: { errors: number; warnings: number; duplicates: number };
    errors: InputValidationFinding[];
    warnings: InputValidationFinding[];
    duplicate_candidates: AgriInputDto[];
  };
}

export interface InputCategoriesResponse {
  schema_version: string;
  count: number;
  categories: InputCategoryDto[];
}

export interface InputsResponse {
  schema_version: string;
  project_id?: string | null;
  project_crop_scope?: string[] | null;
  filter_policy?: string;
  count: number;
  inputs: AgriInputDto[];
}

export interface AgriInputUpdateRequest {
  canonical_name?: string;
  brand_name?: string | null;
  composition?: string | null;
  unit?: string;
  standard_weight?: string | null;
  applicable_crops?: string[];
  application_method?: string | null;
  safety_instructions?: string | null;
  aliases?: Array<Record<string, string>>;
  change_reason?: string | null;
}

export interface AgriInputCreateRequest extends AgriInputUpdateRequest {
  code: string;
  category_code: string;
  canonical_name: string;
  unit: string;
}

export interface AgriInputAuditEvent {
  id: string;
  tenant_id: string;
  input_id: string;
  input_code: string;
  actor_id?: string | null;
  action: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface AgriInputAuditResponse {
  schema_version: string;
  tenant_id: string;
  input_code: string;
  count: number;
  events: AgriInputAuditEvent[];
}

export interface InputReviewQueueItem extends AgriInputDto {
  validation?: {
    can_submit?: boolean;
    can_publish?: boolean;
    counts: { errors: number; warnings: number; duplicate_candidates: number };
  };
  latest_audit?: AgriInputAuditEvent | null;
}

export interface InputReviewQueueResponse {
  schema_version: string;
  tenant_id: string;
  status: string;
  count: number;
  items: InputReviewQueueItem[];
}

export interface ProjectInputAssignmentDto extends AgriInputDto {
  visible: boolean;
  assignment_rule: "ANDROID_VISIBLE" | "DISABLED_BY_PROJECT" | "BLOCKED_BY_CROP_SCOPE" | "NOT_ASSIGNED" | "IMPLICIT_CROP_SCOPE" | string;
  assignment_reason?: string;
  crop_scope_allowed?: boolean;
  assignment_scope?: string;
  configured_enabled?: boolean | null;
  display_order?: number | null;
  reason?: string | null;
}

export interface ProjectInputAssignmentsResponse {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  project_crop_scope?: string[] | null;
  explicit_assignment_scope: boolean;
  counts: {
    total: number;
    android_visible: number;
    disabled_by_project: number;
    not_assigned: number;
    blocked_by_crop_scope: number;
    implicit_crop_scope: number;
  };
  inputs: ProjectInputAssignmentDto[];
}

export interface ProjectInputAssignmentUpdateRequest {
  enabled: boolean;
  display_order?: number | null;
  reason?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ProjectInputAssignmentAuditEvent {
  id: string;
  tenant_id: string;
  project_id: string;
  input_code: string;
  assignment_id?: string | null;
  actor_id?: string | null;
  action: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface ProjectInputAssignmentAuditResponse {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  count: number;
  events: ProjectInputAssignmentAuditEvent[];
}

export interface InputWorkflowReferenceDto {
  recommendation_id: string;
  workflow_template_id: string;
  workflow_code: string;
  workflow_name: string;
  crop_code: string;
  season_code: string;
  workflow_template_version_id: string;
  version_number: string;
  version_status: string;
  stage_id: string;
  stage_code: string;
  stage_name?: Record<string, string> | string | null;
  activity_type: string;
  input_name: string;
  day_offset: number;
  is_critical: boolean;
}

export interface InputProjectReferenceDto {
  assignment_id: string;
  project_id: string;
  project_name: string;
  project_status: string;
  tenant_id: string;
  enabled: boolean;
  display_order: number;
  reason?: string | null;
}

export interface InputReferencesResponse {
  schema_version: string;
  input_code: string;
  references: {
    workflow_recommendations: number;
    project_assignments: number;
    total: number;
  };
  usage: {
    workflow_recommendations: InputWorkflowReferenceDto[];
    project_assignments: InputProjectReferenceDto[];
  };
}


export interface CropStageInputRuleDto {
  id: string;
  tenant_id: string;
  project_id?: string | null;
  rule_scope: "GLOBAL" | "PROJECT" | string;
  crop_code: string;
  season_code?: string | null;
  stage_code: string;
  activity_type: string;
  input_code: string;
  input_name: string;
  input_category_code?: string | null;
  enabled: boolean;
  priority: number;
  dosage: { quantity?: string | null; unit?: string | null; area_unit: string; min_quantity?: string | null; max_quantity?: string | null };
  application_method?: string | null;
  timing_note?: string | null;
  safety_note?: string | null;
  allowed_product_codes: string[];
  metadata?: Record<string, unknown>;
  reason?: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CropStageInputRulesResponse {
  schema_version: string;
  tenant_id: string;
  project_id?: string | null;
  filter_policy: string;
  count: number;
  rules: CropStageInputRuleDto[];
}
export interface InputCsvDiagnostic {
  field: string;
  code: string;
  message: string;
}

export interface InputCsvRowResult {
  row_number: number;
  code: string;
  action: "CREATE" | "UPDATE" | "UNCHANGED" | "INVALID";
  errors: InputCsvDiagnostic[];
  warnings: InputCsvDiagnostic[];
}

export interface InputCsvImportBatch {
  batch_id: string;
  file_name: string;
  status: string;
  can_apply: boolean;
  expires_at: string;
  applied_at?: string | null;
  created_at: string;
  report: {
    can_apply: boolean;
    counts: Record<string, number>;
    rows: InputCsvRowResult[];
    applied_counts?: Record<string, number>;
    apply_reason?: string;
  };
}

export interface InputCsvImportHistory {
  schema_version: string;
  tenant_id: string;
  status?: string | null;
  count: number;
  imports: InputCsvImportBatch[];
}

export const inputCatalogApi = {
  downloadCsvTemplate: () => apiDownload("/api/v1/input-catalog/csv/template", "agri-os-input-catalog-template.csv"),
  exportCsv: (includeInactive = false) => apiDownload(`/api/v1/input-catalog/csv/export?include_inactive=${includeInactive}`, "agri-os-input-catalog.csv"),
  validateCsv: (file: File) => apiUpload<InputCsvImportBatch>("/api/v1/input-catalog/csv/validate", file),
  applyCsv: (batchId: string, reason: string) => api<InputCsvImportBatch>(`/api/v1/input-catalog/csv/imports/${batchId}/apply`, { method: "POST", body: { reason } }),
  csvImportHistory: (params?: { status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<InputCsvImportHistory>(`/api/v1/input-catalog/csv/imports${suffix}`);
  },
  inputRules: (params?: { cropCode?: string; seasonCode?: string; stageCode?: string; activityType?: string; inputCode?: string; projectId?: string; includeDisabled?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.seasonCode) query.set("season_code", params.seasonCode);
    if (params?.stageCode) query.set("stage_code", params.stageCode);
    if (params?.activityType) query.set("activity_type", params.activityType);
    if (params?.inputCode) query.set("input_code", params.inputCode);
    if (params?.projectId) query.set("project_id", params.projectId);
    if (params?.includeDisabled) query.set("include_disabled", "true");
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<CropStageInputRulesResponse>(`/api/v1/input-catalog/input-rules${suffix}`);
  },
  createInputRule: (data: Record<string, unknown>) => api<CropStageInputRuleDto>("/api/v1/input-catalog/input-rules", { method: "POST", body: data }),
  updateInputRule: (ruleId: string, data: Record<string, unknown>) => api<CropStageInputRuleDto>(`/api/v1/input-catalog/input-rules/${ruleId}`, { method: "PATCH", body: data }),  categories: () => api<InputCategoriesResponse>("/api/v1/input-catalog/categories"),
  inputs: (params?: { category?: string; cropCode?: string; projectId?: string; q?: string; includeInactive?: boolean; includeUnpublished?: boolean; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set("category", params.category);
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.projectId) query.set("project_id", params.projectId);
    if (params?.q) query.set("q", params.q);
    if (params?.includeInactive) query.set("include_inactive", "true");
    if (params?.includeUnpublished) query.set("include_unpublished", "true");
    if (params?.status) query.set("status", params.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<InputsResponse>(`/api/v1/input-catalog/inputs${suffix}`);
  },

  reviewQueue: (params?: { status?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<InputReviewQueueResponse>(`/api/v1/input-catalog/inputs/review-queue${suffix}`);
  },
  get: (code: string) => api<AgriInputDto>(`/api/v1/input-catalog/inputs/${code}`),
  governance: (code: string) => api<InputGovernanceResponse>(`/api/v1/input-catalog/inputs/${code}/governance`),
  submitReview: (code: string, reason: string) => api<InputGovernanceResponse>(`/api/v1/input-catalog/inputs/${code}/submit-review`, { method: "POST", body: { reason } }),
  publish: (code: string, reason: string) => api<InputGovernanceResponse>(`/api/v1/input-catalog/inputs/${code}/publish`, { method: "POST", body: { reason } }),
  reject: (code: string, reason: string) => api<InputGovernanceResponse>(`/api/v1/input-catalog/inputs/${code}/reject`, { method: "POST", body: { reason } }),
  create: (data: AgriInputCreateRequest) =>
    api<AgriInputDto>("/api/v1/input-catalog/inputs", {
      method: "POST",
      body: data,
    }),
  update: (code: string, data: AgriInputUpdateRequest) =>
    api<AgriInputDto>(`/api/v1/input-catalog/inputs/${code}`, {
      method: "PUT",
      body: data,
    }),
  archive: (code: string, reason?: string | null) =>
    api<AgriInputDto>(`/api/v1/input-catalog/inputs/${code}/archive`, {
      method: "POST",
      body: { reason: reason || null },
    }),
  restore: (code: string, reason?: string | null) =>
    api<AgriInputDto>(`/api/v1/input-catalog/inputs/${code}/restore`, {
      method: "POST",
      body: { reason: reason || null },
    }),
  references: (code: string) =>
    api<InputReferencesResponse>(`/api/v1/input-catalog/inputs/${code}/references`),
  inputAudit: (code: string, params?: { action?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.action) query.set("action", params.action);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<AgriInputAuditResponse>(`/api/v1/input-catalog/inputs/${code}/audit${suffix}`);
  },
  projectAssignments: (projectId: string, params?: { category?: string; cropCode?: string; q?: string }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set("category", params.category);
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.q) query.set("q", params.q);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<ProjectInputAssignmentsResponse>(`/api/v1/input-catalog/projects/${projectId}/input-assignments${suffix}`);
  },
  updateProjectAssignment: (projectId: string, inputCode: string, data: ProjectInputAssignmentUpdateRequest) =>
    api<ProjectInputAssignmentsResponse>(`/api/v1/input-catalog/projects/${projectId}/input-assignments/${inputCode}`, {
      method: "PUT",
      body: data,
    }),
  projectAssignmentAudit: (projectId: string, params?: { inputCode?: string; action?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.inputCode) query.set("input_code", params.inputCode);
    if (params?.action) query.set("action", params.action);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<ProjectInputAssignmentAuditResponse>(`/api/v1/input-catalog/projects/${projectId}/input-assignments/audit${suffix}`);
  },
};


export interface TenantAdminProjectAccess {
  project_role_id: string;
  project_id: string;
  project_name: string;
  project_status: string;
  role: string;
  territory_scope: Record<string, unknown>;
}

export interface TenantAdminUser {
  id: string;
  mobile_number_masked: string;
  display_name?: string | null;
  role: string;
  tenant_id: string;
  is_active: boolean;
  last_login_at?: string | null;
  login_count: number;
  project_access: TenantAdminProjectAccess[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TenantAdminUsersResponse {
  schema_version: string;
  tenant_id: string;
  available_roles: string[];
  project_roles: string[];
  count: number;
  users: TenantAdminUser[];
}

export interface UserAccessAuditEvent {
  id: string;
  target_user_id: string;
  actor_id: string;
  project_id?: string | null;
  action: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string | null;
  created_at: string;
}

export interface UserAccessAuditResponse {
  schema_version: string;
  tenant_id: string;
  count: number;
  events: UserAccessAuditEvent[];
}

export const tenantAdminUsersApi = {
  list: () => api<TenantAdminUsersResponse>("/api/v1/admin/users"),
  invite: (data: { mobile_number: string; display_name?: string | null; role: string; reason: string }) =>
    api<{ created: boolean; user: TenantAdminUser }>("/api/v1/admin/users/by-mobile", { method: "PUT", body: data }),
  changeRole: (userId: string, data: { role: string; display_name?: string | null; reason: string }) =>
    api<{ user: TenantAdminUser }>(`/api/v1/admin/users/${userId}/role`, { method: "PUT", body: data }),
  revoke: (userId: string, reason: string) =>
    api<{ status: string; user_id: string }>(`/api/v1/admin/users/${userId}`, { method: "DELETE", body: { reason } }),
  assignProject: (userId: string, projectId: string, data: { role: string; territory_scope?: Record<string, unknown>; reason: string }) =>
    api<{ user: TenantAdminUser }>(`/api/v1/admin/users/${userId}/projects/${projectId}`, { method: "PUT", body: data }),
  revokeProject: (userId: string, projectId: string, reason: string) =>
    api<{ user: TenantAdminUser }>(`/api/v1/admin/users/${userId}/projects/${projectId}`, { method: "DELETE", body: { reason } }),
  audit: (userId?: string) =>
    api<UserAccessAuditResponse>(`/api/v1/admin/user-access-audit${userId ? `?user_id=${encodeURIComponent(userId)}` : ""}`),
};

// Manufacturer and branded product catalog
export interface ManufacturerDto { id: string; code: string; canonical_name: string; short_name?: string | null; country: string; aliases: Array<Record<string,string>>; is_active: boolean }
export interface ProductPackageDto { id: string; sku: string; quantity: string; unit: string; pack_label: string; barcode?: string | null; status: string }
export interface AgriculturalProductDto { id: string; code: string; canonical_input_code: string; canonical_input_name: string; manufacturer_code: string; manufacturer_name: string; brand_name: string; composition?: string | null; registration_number?: string | null; registration_authority?: string | null; registration_expiry_date?: string | null; country: string; status: string; packages: ProductPackageDto[]; project_approval?: { enabled: boolean; preferred: boolean; display_order: number; reason?: string | null } | null }
export interface ProductCatalogAuditEventDto { id: string; entity_type: string; entity_code: string; action: string; actor_id?: string | null; before?: Record<string, unknown> | null; after?: Record<string, unknown> | null; reason?: string | null; created_at: string }
export interface ProductCatalogAuditResponse { count: number; events: ProductCatalogAuditEventDto[] }
export interface ProductCsvIssueDto { field: string; code: string; message: string }
export interface ProductCsvRowDto { row_number: number; product_code: string; package_sku: string; action: string; errors: ProductCsvIssueDto[]; warnings: ProductCsvIssueDto[]; normalized: Record<string, unknown> }
export interface ProductCsvValidationResponse { schema_version: string; mode: string; file_name?: string | null; can_apply: boolean; summary: { total: number; create: number; update: number; unchanged: number; invalid: number; warnings: number; errors: number }; rows: ProductCsvRowDto[]; message: string; applied_counts?: Record<string, number>; apply_reason?: string }
export interface ProductCsvImportBatch { batch_id: string; file_name?: string | null; status: string; can_apply: boolean; expires_at: string; applied_at?: string | null; created_at: string; report: ProductCsvValidationResponse }
export interface ProductCsvImportHistory { schema_version: string; tenant_id: string; status?: string | null; count: number; imports: ProductCsvImportBatch[] }
export const productCatalogApi = {
  downloadCsvTemplate: () => apiDownload("/api/v1/product-catalog/csv/template", "agri-os-product-catalog-template.csv"),
  exportCsv: (includeInactive = false) => apiDownload(`/api/v1/product-catalog/csv/export?include_inactive=${includeInactive}`, "agri-os-product-catalog.csv"),
  validateCsv: (file: File) => apiUpload<ProductCsvImportBatch>("/api/v1/product-catalog/csv/validate", file),
  applyCsv: (batchId: string, reason: string) => api<ProductCsvImportBatch>(`/api/v1/product-catalog/csv/imports/${batchId}/apply`, { method: "POST", body: { reason } }),
  importHistory: (params?: { status?: string; limit?: number }) => { const q=new URLSearchParams(); if(params?.status)q.set("status",params.status); if(params?.limit)q.set("limit",String(params.limit)); const suffix=q.toString()?`?${q}`:""; return api<ProductCsvImportHistory>(`/api/v1/product-catalog/csv/imports${suffix}`); },
  manufacturers: () => api<{count:number; manufacturers:ManufacturerDto[]}>("/api/v1/product-catalog/manufacturers"),
  createManufacturer: (body: Record<string, unknown>) => api<ManufacturerDto>("/api/v1/product-catalog/manufacturers", {method:"POST", body}),
  products: (params?: {inputCode?:string; manufacturerCode?:string; projectId?:string; includeInactive?:boolean}) => { const q=new URLSearchParams(); if(params?.inputCode)q.set("input_code",params.inputCode); if(params?.manufacturerCode)q.set("manufacturer_code",params.manufacturerCode); if(params?.projectId)q.set("project_id",params.projectId); if(params?.includeInactive)q.set("include_inactive","true"); return api<{count:number; approval_policy:string; products:AgriculturalProductDto[]}>(`/api/v1/product-catalog/products?${q}`); },
  createProduct: (body: Record<string, unknown>) => api<AgriculturalProductDto>("/api/v1/product-catalog/products", {method:"POST", body}),
  updateProduct: (code:string, body:Record<string,unknown>) => api<AgriculturalProductDto>(`/api/v1/product-catalog/products/${code}`, {method:"PUT", body}),
  approveProduct: (projectId:string, code:string, body:Record<string,unknown>) => api<{product:AgriculturalProductDto}>(`/api/v1/product-catalog/projects/${projectId}/products/${code}`, {method:"PUT", body}),
  audit: (params?: { entityType?: string; entityCode?: string; limit?: number }) => { const q=new URLSearchParams(); if(params?.entityType)q.set("entity_type",params.entityType); if(params?.entityCode)q.set("entity_code",params.entityCode); if(params?.limit)q.set("limit",String(params.limit)); const suffix=q.toString()?`?${q}`:""; return api<ProductCatalogAuditResponse>(`/api/v1/product-catalog/audit${suffix}`); },
};


// Field event reporting
export interface FieldEventReportDto {
  id: string;
  tenant_id: string;
  project_id?: string | null;
  farmer_id: string;
  parcel_id?: string | null;
  crop_cycle_id?: string | null;
  stage_code?: string | null;
  event_type: string;
  severity: string;
  event_date?: string | null;
  reported_at?: string | null;
  lat?: string | null;
  lng?: string | null;
  accuracy_meters?: string | null;
  description?: string | null;
  estimated_area_affected?: string | null;
  estimated_loss_percent?: string | null;
  source: string;
  external_source?: string | null;
  external_event_id?: string | null;
  status: string;
  metadata?: Record<string, unknown>;
  media_attachment_count: number;
  media_attachments?: MediaAttachmentTrace[];
  created_at?: string | null;
  updated_at?: string | null;
}
export interface FieldEventReportListResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  count: number;
  events: FieldEventReportDto[];
}
export const fieldEventsApi = {
  list: (params?: { projectId?: string; farmerId?: string; parcelId?: string; eventType?: string; severity?: string; status?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.projectId) q.set("project_id", params.projectId);
    if (params?.farmerId) q.set("farmer_id", params.farmerId);
    if (params?.parcelId) q.set("parcel_id", params.parcelId);
    if (params?.eventType) q.set("event_type", params.eventType);
    if (params?.severity) q.set("severity", params.severity);
    if (params?.status) q.set("status", params.status);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<FieldEventReportListResponse>(`/api/v1/field-events${suffix}`);
  },
  detail: (eventId: string) => api<FieldEventReportDto>(`/api/v1/field-events/${eventId}`),
};


// Farmer query threads
export interface QueryAuditEventDto {
  id: string;
  tenant_id: string;
  thread_id: string;
  action: string;
  actor_type?: string | null;
  actor_id?: string | null;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface QueryMessageDto {
  id: string;
  tenant_id: string;
  thread_id: string;
  sender_type: string;
  sender_id?: string | null;
  message_type: string;
  body_text?: string | null;
  metadata?: Record<string, unknown>;
  media_attachment_count: number;
  media_attachments?: MediaAttachmentTrace[];
  created_at?: string | null;
  updated_at?: string | null;
}
export interface QueryThreadDto {
  id: string;
  tenant_id: string;
  project_id?: string | null;
  farmer_id: string;
  parcel_id?: string | null;
  crop_cycle_id?: string | null;
  stage_code?: string | null;
  subject: string;
  category: string;
  priority: string;
  status: string;
  assigned_to?: string | null;
  last_message_at?: string | null;
  metadata?: Record<string, unknown>;
  message_count: number;
  media_attachment_count: number;
  messages?: QueryMessageDto[];
  audit_events?: QueryAuditEventDto[];
  created_at?: string | null;
  updated_at?: string | null;
}
export interface QueryThreadListResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  count: number;
  threads: QueryThreadDto[];
}
export const queryThreadsApi = {
  list: (params?: { projectId?: string; farmerId?: string; parcelId?: string; status?: string; category?: string; priority?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.projectId) q.set("project_id", params.projectId);
    if (params?.farmerId) q.set("farmer_id", params.farmerId);
    if (params?.parcelId) q.set("parcel_id", params.parcelId);
    if (params?.status) q.set("status", params.status);
    if (params?.category) q.set("category", params.category);
    if (params?.priority) q.set("priority", params.priority);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<QueryThreadListResponse>(`/api/v1/query-threads${suffix}`);
  },
  detail: (threadId: string) => api<QueryThreadDto>(`/api/v1/query-threads/${threadId}`),
  addMessage: (threadId: string, body: { sender_type?: string; sender_id?: string; message_type?: string; body_text?: string; metadata?: Record<string, unknown>; media_attachments?: unknown[] }) =>
    api<QueryMessageDto>(`/api/v1/query-threads/${threadId}/messages`, { method: "POST", body: JSON.stringify(body) }),
  updateStatus: (threadId: string, body: { status: string; assigned_to?: string | null; reason?: string }) =>
    api<QueryThreadDto>(`/api/v1/query-threads/${threadId}/status`, { method: "PATCH", body: JSON.stringify(body) }),
};


export interface BroadcastContentDto {
  id: string;
  tenant_id: string;
  campaign_id: string;
  language_code: string;
  title: string;
  body_text?: string | null;
  cta_label?: string | null;
  deeplink_url?: string | null;
  metadata?: Record<string, unknown>;
  media_attachments?: BroadcastMediaAttachmentDto[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BroadcastAudienceRuleDto {
  id: string;
  tenant_id: string;
  campaign_id: string;
  rule_type: string;
  operator: string;
  values?: unknown[];
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface BroadcastDeliverySummaryDto {
  total: number;
  pending: number;
  delivered: number;
  read: number;
  acknowledged: number;
  failed: number;
}

export interface BroadcastCampaignDto {
  id: string;
  tenant_id: string;
  project_id?: string | null;
  title: string;
  category: string;
  priority: string;
  status: string;
  starts_at?: string | null;
  expires_at?: string | null;
  created_by?: string | null;
  approved_by?: string | null;
  metadata?: Record<string, unknown>;
  is_active: boolean;
  content_count: number;
  audience_rule_count: number;
  delivery_count: number;
  contents?: BroadcastContentDto[];
  audience_rules?: BroadcastAudienceRuleDto[];
  delivery_summary?: BroadcastDeliverySummaryDto;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BroadcastMediaAttachmentDto {
  id: string;
  tenant_id: string;
  project_id?: string | null;
  farmer_id?: string | null;
  media_type: string;
  mime_type: string;
  storage_url?: string | null;
  storage_key?: string | null;
  thumbnail_url?: string | null;
  sha256_hash?: string | null;
  size_bytes?: number | null;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  upload_status: string;
  metadata?: Record<string, unknown>;
  attachment?: {
    id: string;
    entity_type: string;
    entity_id: string;
    purpose: string;
    caption?: string | null;
    display_order: number;
    is_primary: boolean;
    metadata?: Record<string, unknown>;
  };
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BroadcastCampaignListResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  count: number;
  campaigns: BroadcastCampaignDto[];
}

export interface BroadcastAudienceRulePreviewDto {
  rule_id: string;
  rule_type: string;
  operator: string;
  values?: unknown[];
  supported: boolean;
  matched_farmer_count: number;
  sample_farmer_ids: string[];
  sample_matches?: Array<{ farmer_id: string; matched_by: string[] }>;
  match_reason_counts?: Record<string, number>;
  weather_snapshot_matches?: Array<{
    snapshot_id: string;
    location_scope: string;
    location_key?: string | null;
    project_id?: string | null;
    farmer_id?: string | null;
    parcel_id?: string | null;
    condition_code?: string | null;
    risk_flags?: string[];
    matched_terms?: string[];
    fetched_at?: string | null;
    expires_at?: string | null;
  }>;
  note?: string | null;
}

export interface BroadcastAudiencePreviewResponse {
  schema_version: string;
  tenant_id: string;
  campaign_id: string;
  campaign_status: string;
  audience_match_mode?: string;
  estimated_farmer_count: number;
  sample_farmer_ids: string[];
  sample_matches?: Array<{ farmer_id: string; matched_by: string[] }>;
  match_reason_counts?: Record<string, number>;
  rule_summaries: BroadcastAudienceRulePreviewDto[];
  unsupported_rule_count: number;
  existing_delivery_count: number;
}

export interface BroadcastDeliveryDto {
  id: string;
  tenant_id: string;
  campaign_id: string;
  farmer_id?: string | null;
  user_id?: string | null;
  delivery_status: string;
  delivered_at?: string | null;
  read_at?: string | null;
  acknowledged_at?: string | null;
  failure_reason?: string | null;
  metadata?: Record<string, unknown>;
  farmer?: {
    id: string;
    display_name?: string | null;
    mobile_number?: string | null;
    village_name_manual?: string | null;
    status?: string | null;
  } | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BroadcastDeliveriesResponse {
  schema_version: string;
  tenant_id: string;
  campaign_id: string;
  filters: Record<string, unknown>;
  count: number;
  deliveries: BroadcastDeliveryDto[];
}

export interface BroadcastAuditEventDto {
  id: string;
  tenant_id: string;
  campaign_id: string;
  delivery_id?: string | null;
  action: string;
  actor_type?: string | null;
  actor_id?: string | null;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface BroadcastAuditResponse {
  schema_version: string;
  tenant_id: string;
  campaign_id: string;
  filters: Record<string, unknown>;
  count: number;
  events: BroadcastAuditEventDto[];
}

export const broadcastsApi = {
  list: (params?: { projectId?: string; status?: string; category?: string; priority?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.projectId) q.set("project_id", params.projectId);
    if (params?.status) q.set("status", params.status);
    if (params?.category) q.set("category", params.category);
    if (params?.priority) q.set("priority", params.priority);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<BroadcastCampaignListResponse>(`/api/v1/broadcasts${suffix}`);
  },
  detail: (campaignId: string) => api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}`),
  create: (body: {
    title: string;
    category?: string;
    priority?: string;
    starts_at?: string;
    expires_at?: string;
    metadata?: Record<string, unknown>;
    audience_match_mode?: "ANY" | "ALL";
    contents?: Array<{ language_code?: string; title: string; body_text?: string; cta_label?: string; deeplink_url?: string; metadata?: Record<string, unknown> }>;
    audience_rules?: Array<{ rule_type: string; operator?: string; values?: string[]; metadata?: Record<string, unknown> }>;
  }) => {
    const { audience_match_mode, metadata, ...rest } = body;
    return api<BroadcastCampaignDto>("/api/v1/broadcasts", {
      method: "POST",
      body: JSON.stringify({
        ...rest,
        metadata: { ...(metadata || {}), ...(audience_match_mode ? { audience_match_mode } : {}) },
      }),
    });
  },
  addContent: (campaignId: string, body: { language_code?: string; title: string; body_text?: string; cta_label?: string; deeplink_url?: string; metadata?: Record<string, unknown> }) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/contents`, { method: "POST", body: JSON.stringify(body) }),
  addAudienceRule: (campaignId: string, body: { rule_type: string; operator?: string; values?: string[]; metadata?: Record<string, unknown> }) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/audience-rules`, { method: "POST", body: JSON.stringify(body) }),
  publish: (campaignId: string, body?: { approved_by?: string; reason?: string }) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/publish`, { method: "POST", body: JSON.stringify(body || {}) }),
  generateDeliveries: (campaignId: string) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/generate-deliveries`, { method: "POST" }),
  retryUndelivered: (campaignId: string) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/retry-undelivered`, { method: "POST" }),
  expire: (campaignId: string, body?: { actor_id?: string; reason?: string }) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/expire`, { method: "POST", body: JSON.stringify(body || {}) }),
  cancel: (campaignId: string, body?: { actor_id?: string; reason?: string }) =>
    api<BroadcastCampaignDto>(`/api/v1/broadcasts/${campaignId}/cancel`, { method: "POST", body: JSON.stringify(body || {}) }),
  previewAudience: (campaignId: string) =>
    api<BroadcastAudiencePreviewResponse>(`/api/v1/broadcasts/${campaignId}/audience-preview`),
  deliveries: (campaignId: string, params?: { status?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<BroadcastDeliveriesResponse>(`/api/v1/broadcasts/${campaignId}/deliveries${suffix}`);
  },
  audit: (campaignId: string, params?: { action?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.action) q.set("action", params.action);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<BroadcastAuditResponse>(`/api/v1/broadcasts/${campaignId}/audit${suffix}`);
  },

};

export interface WeatherProviderDto {
  id: string;
  tenant_id: string;
  provider_code: string;
  display_name: string;
  provider_type: string;
  refresh_interval_hours: number;
  is_enabled: boolean;
  last_refresh_at?: string | null;
  next_refresh_at?: string | null;
  config?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  is_due?: boolean;
  hours_until_due?: number | null;
  refresh_status?: string | null;
  refresh_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WeatherSnapshotDto {
  id: string;
  tenant_id: string;
  provider_id?: string | null;
  project_id?: string | null;
  farmer_id?: string | null;
  parcel_id?: string | null;
  location_scope: string;
  location_key?: string | null;
  lat?: string | null;
  lng?: string | null;
  fetched_at: string;
  observed_at?: string | null;
  forecast_valid_from?: string | null;
  forecast_valid_to?: string | null;
  expires_at?: string | null;
  summary?: string | null;
  condition_code?: string | null;
  rainfall_probability_percent?: number | null;
  rainfall_mm?: string | null;
  temperature_min_c?: string | null;
  temperature_max_c?: string | null;
  humidity_percent?: number | null;
  wind_speed_kmph?: string | null;
  risk_flags?: string[];
  source_payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WeatherProvidersResponse {
  schema_version: string;
  tenant_id: string;
  count: number;
  providers: WeatherProviderDto[];
}

export interface WeatherRefreshPlanResponse {
  schema_version: string;
  tenant_id: string;
  generated_at: string;
  filters: Record<string, unknown>;
  count: number;
  due_count: number;
  providers: WeatherProviderDto[];
}

export interface WeatherSnapshotsResponse {
  schema_version: string;
  tenant_id: string;
  filters: Record<string, unknown>;
  count: number;
  snapshots: WeatherSnapshotDto[];
}

export interface WeatherProviderRefreshResponse {
  schema_version: string;
  tenant_id: string;
  provider: WeatherProviderDto;
  status: string;
  message?: string | null;
  created_snapshot_count: number;
  snapshots: WeatherSnapshotDto[];
}

export interface WeatherProviderDueRunResponse {
  schema_version: string;
  tenant_id: string;
  generated_at: string;
  dry_run: boolean;
  due_count: number;
  processed_count: number;
  created_snapshot_count: number;
  providers: Array<{
    provider_id: string;
    provider_code: string;
    status?: string | null;
    message?: string | null;
    created_snapshot_count?: number;
    snapshots?: WeatherSnapshotDto[];
    provider?: WeatherProviderDto;
    display_name?: string;
    provider_type?: string;
    refresh_interval_hours?: number;
    last_refresh_at?: string | null;
    next_refresh_at?: string | null;
    is_due?: boolean;
    hours_until_due?: number | null;
    refresh_status?: string | null;
    refresh_message?: string | null;
  }>;
}

export const weatherApi = {
  createProvider: (body: { provider_code: string; display_name: string; provider_type?: string; refresh_interval_hours?: number; is_enabled?: boolean; config?: Record<string, unknown>; metadata?: Record<string, unknown> }) =>
    api<WeatherProviderDto>("/api/v1/weather/providers", { method: "POST", body: JSON.stringify(body) }),
  providers: (params?: { enabled?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.enabled !== undefined) q.set("enabled", String(params.enabled));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<WeatherProvidersResponse>(`/api/v1/weather/providers${suffix}`);
  },
  refreshPlan: (params?: { enabled?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.enabled !== undefined) q.set("enabled", String(params.enabled));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<WeatherRefreshPlanResponse>(`/api/v1/weather/providers/refresh-plan${suffix}`);
  },
  createSnapshot: (body: { provider_id?: string; project_id?: string; farmer_id?: string; parcel_id?: string; location_scope?: string; location_key?: string; lat?: string; lng?: string; fetched_at?: string; forecast_valid_from?: string; forecast_valid_to?: string; expires_at?: string; summary?: string; condition_code?: string; rainfall_probability_percent?: number; rainfall_mm?: string; temperature_min_c?: string; temperature_max_c?: string; humidity_percent?: number; wind_speed_kmph?: string; risk_flags?: string[]; source_payload?: Record<string, unknown>; metadata?: Record<string, unknown> }) =>
    api<WeatherSnapshotDto>("/api/v1/weather/snapshots", { method: "POST", body: JSON.stringify(body) }),
  snapshots: (params?: { providerId?: string; locationScope?: string; locationKey?: string; includeExpired?: boolean; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.providerId) q.set("provider_id", params.providerId);
    if (params?.locationScope) q.set("location_scope", params.locationScope);
    if (params?.locationKey) q.set("location_key", params.locationKey);
    if (params?.includeExpired !== undefined) q.set("include_expired", String(params.includeExpired));
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<WeatherSnapshotsResponse>(`/api/v1/weather/snapshots${suffix}`);
  },
  refreshProvider: (providerId: string, body?: { status?: string; message?: string; metadata?: Record<string, unknown>; snapshots?: unknown[] }) =>
    api<WeatherProviderRefreshResponse>(`/api/v1/weather/providers/${providerId}/refresh`, { method: "POST", body: JSON.stringify(body || { status: "SUCCESS", message: "Admin manual refresh marker" }) }),
  runAdapter: (providerId: string) =>
    api<WeatherProviderRefreshResponse>(`/api/v1/weather/providers/${providerId}/run-adapter`, { method: "POST" }),
  runDueProviders: (params?: { dryRun?: boolean; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.dryRun !== undefined) q.set("dry_run", String(params.dryRun));
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api<WeatherProviderDueRunResponse>(`/api/v1/weather/providers/run-due${suffix}`, { method: "POST" });
  },
};

