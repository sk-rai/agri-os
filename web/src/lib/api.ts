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

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
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
    throw new ApiError(error.detail || res.statusText, res.status);
  }

  return res.json() as Promise<T>;
}

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

// Auth
export const authApi = {
  requestOtp: (mobile_number: string) =>
    api("/api/v1/auth/otp/request", { method: "POST", body: { mobile_number }, noAuth: true }),
  verifyOtp: (mobile_number: string, otp_code: string, device_id: string) =>
    api("/api/v1/auth/otp/verify", { method: "POST", body: { mobile_number, otp_code, device_id }, noAuth: true }),
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

export interface WorkflowDraftRecommendationRequest {
  day_offset?: number;
  activity_type?: string;
  input_code?: string | null;
  input_name?: string;
  typical_quantity?: string | null;
  typical_cost_per_acre?: number | null;
  is_critical?: boolean;
  description?: Record<string, string> | null;
  sort_order?: number;
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
  templateAudit: (templateId: string, params?: { versionId?: string; action?: string; actorId?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.versionId) query.set("version_id", params.versionId);
    if (params?.action) query.set("action", params.action);
    if (params?.actorId) query.set("actor_id", params.actorId);
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
  draftPreview: (versionId: string) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/draft-preview/${versionId}`),
  validateDraftVersion: (versionId: string) =>
    api<WorkflowDraftValidationResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/validation`),
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
  deleteDraftRecommendation: (versionId: string, recommendationId: string) =>
    api<WorkflowPreviewResponse>(`/api/v1/workflow-catalog/drafts/${versionId}/recommendations/${recommendationId}`, {
      method: "DELETE",
    }),
  projectEnablements: (projectId: string) =>
    api<ProjectWorkflowEnablementsResponse>(`/api/v1/workflow-catalog/projects/${projectId}/workflow-enablements`),
  updateProjectEnablement: (
    projectId: string,
    workflowTemplateId: string,
    data: { enabled: boolean; display_order?: number | null; display_label?: Record<string, string> | null }
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

export const inputCatalogApi = {
  categories: () => api<InputCategoriesResponse>("/api/v1/input-catalog/categories"),
  inputs: (params?: { category?: string; cropCode?: string; projectId?: string; q?: string }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set("category", params.category);
    if (params?.cropCode) query.set("crop_code", params.cropCode);
    if (params?.projectId) query.set("project_id", params.projectId);
    if (params?.q) query.set("q", params.q);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return api<InputsResponse>(`/api/v1/input-catalog/inputs${suffix}`);
  },
  get: (code: string) => api<AgriInputDto>(`/api/v1/input-catalog/inputs/${code}`),
  update: (code: string, data: AgriInputUpdateRequest) =>
    api<AgriInputDto>(`/api/v1/input-catalog/inputs/${code}`, {
      method: "PUT",
      body: data,
    }),
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
