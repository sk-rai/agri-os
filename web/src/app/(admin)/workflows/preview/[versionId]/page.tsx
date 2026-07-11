"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  inputCatalogApi,
  workflowCatalogApi,
  type AgriInputDto,
  type WorkflowDeletedStagesResponse,
  type WorkflowDraftRecommendationRequest,
  type WorkflowDraftStageCreateRequest,
  type WorkflowDraftStageDuplicateRequest,
  type WorkflowDraftStageUpdateRequest,
  type WorkflowDraftValidationResponse,
  type WorkflowAuditResponse,
  type WorkflowOverrideHistoryResponse,
  type WorkflowPreviewResponse,
  type WorkflowPublishImpactResponse,
  type WorkflowRecommendation,
  type WorkflowStage,
  type WorkflowPreviewWarning,
} from "@/lib/api";

type WorkflowTargetType = "STAGE" | "RECOMMENDATION";
type WorkflowOverrideOperation = "HIDE" | "RENAME" | "CHANGE_DURATION" | "CHANGE_OFFSET" | "CHANGE_QUANTITY" | "ADD_RECOMMENDATION";
type StageActionMode = "CREATE" | "DUPLICATE";
type StageDesignHint = { level: "ERROR" | "WARN" | "INFO"; message: string };
type DirtyTargets = { stageCodes: Set<string>; recommendationIds: Set<string> };
type PublishOutcome = { published: WorkflowPreviewResponse; impact: WorkflowPublishImpactResponse | null };

function labelText(value: Record<string, string> | string | undefined | null) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.en || Object.values(value)[0] || "";
}

function activityTypeFromCategory(categoryCode?: string | null) {
  const category = (categoryCode || "").toUpperCase();
  if (["SEED", "FERTILIZER", "ORGANIC_MANURE", "FUNGICIDE", "HERBICIDE", "PESTICIDE", "IRRIGATION", "LABOR", "MACHINERY"].includes(category)) {
    return category;
  }
  return "OTHER";
}

function normalizeStageCode(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9_]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50);
}

function recommendationId(rec: WorkflowRecommendation) {
  return typeof rec.metadata?.recommendation_id === "string" ? rec.metadata.recommendation_id : null;
}

function recommendationAnchorId(stageCode: string, rec: WorkflowRecommendation, index: number) {
  const raw = recommendationId(rec) || `${stageCode}-${rec.input_code || rec.input_name || rec.activity_type}-${index}`;
  return raw.replace(/[^A-Za-z0-9_-]+/g, "_");
}

function recommendationSource(rec: WorkflowRecommendation): "CATALOG" | "CUSTOM" | "UNCODED" {
  const metadataSource = typeof rec.metadata?.input_source === "string" ? rec.metadata.input_source.toUpperCase() : "";
  if (metadataSource === "CATALOG" || metadataSource === "CUSTOM") return metadataSource;
  const code = (rec.input_code || "").toUpperCase();
  if (!code) return "UNCODED";
  return code.startsWith("CUSTOM") ? "CUSTOM" : "CATALOG";
}


function dirtyTargetsFromAudit(audit: WorkflowAuditResponse | null, stages: WorkflowStage[]): DirtyTargets {
  const stageCodes = new Set<string>();
  const recommendationIds = new Set<string>();
  const recommendationStage = new Map<string, string>();
  for (const stage of stages) {
    for (const rec of stage.recommended_activities || []) {
      const recId = recommendationId(rec);
      if (recId) recommendationStage.set(recId, stage.code);
    }
  }
  for (const event of audit?.events || []) {
    const targetType = String(event.target_type || "").toUpperCase();
    const action = String(event.action || "").toUpperCase();
    const metadata = event.metadata || {};
    if (targetType === "STAGE" && event.target_code) stageCodes.add(event.target_code);
    if (targetType === "VERSION" && action.includes("REORDER_DRAFT_STAGES")) {
      stages.forEach((stage) => stageCodes.add(stage.code));
    }
    if (targetType === "RECOMMENDATION") {
      if (event.target_id) recommendationIds.add(event.target_id);
      const stageFromMetadata = typeof metadata.stage_code === "string" ? metadata.stage_code : null;
      const stageFromTarget = typeof event.target_code === "string" && event.target_code.includes("|") ? event.target_code.split("|")[0] : null;
      const stageFromRecommendation = event.target_id ? recommendationStage.get(event.target_id) : null;
      const stageCode = stageFromMetadata || stageFromTarget || stageFromRecommendation;
      if (stageCode) stageCodes.add(stageCode);
    }
  }
  return { stageCodes, recommendationIds };
}

function moveItem<T>(items: T[], fromIndex: number, toIndex: number) {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= items.length || toIndex >= items.length) return items;
  const next = [...items];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

function stageDesignHints(stage: WorkflowStage): StageDesignHint[] {
  const hints: StageDesignHint[] = [];
  const recs = stage.recommended_activities || [];
  const duration = stage.duration_days || 0;
  if (!labelText(stage.name).trim()) hints.push({ level: "ERROR", message: "Stage display name is missing." });
  if (duration <= 0) hints.push({ level: "ERROR", message: "Stage duration should be greater than zero." });
  if ((stage.day_offset ?? 0) < 0) hints.push({ level: "ERROR", message: "Stage starts before crop-cycle day zero." });
  if (recs.length === 0) hints.push({ level: "WARN", message: "No recommendations configured for this stage." });
  if (recs.length > 0 && !recs.some((rec) => rec.is_critical)) hints.push({ level: "INFO", message: "No critical recommendation is marked for this stage." });
  const seenKeys = new Set<string>();
  recs.forEach((rec, index) => {
    if (!rec.input_name?.trim()) hints.push({ level: "ERROR", message: `Recommendation ${index + 1} is missing an input name.` });
    if (!rec.activity_type?.trim()) hints.push({ level: "ERROR", message: `Recommendation ${index + 1} is missing an activity type.` });
    if (rec.day_offset < 0) hints.push({ level: "ERROR", message: `${rec.input_name || `Recommendation ${index + 1}`} has a negative day offset.` });
    if (duration > 0 && rec.day_offset > duration) hints.push({ level: "WARN", message: `${rec.input_name || `Recommendation ${index + 1}`} is scheduled after this stage duration.` });
    const key = `${rec.day_offset}:${(rec.input_code || rec.input_name || "").toUpperCase()}`;
    if (seenKeys.has(key)) hints.push({ level: "INFO", message: `${rec.input_name || `Recommendation ${index + 1}`} looks duplicated on the same day.` });
    seenKeys.add(key);
  });
  return hints;
}

function hintClasses(level: StageDesignHint["level"]) {
  if (level === "ERROR") return "border-red-200 bg-red-50 text-red-800";
  if (level === "WARN") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-800";
}

export default function WorkflowPreviewPage() {
  const params = useParams<{ versionId: string }>();
  const searchParams = useSearchParams();
  const [preview, setPreview] = useState<WorkflowPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyTarget, setBusyTarget] = useState<string | null>(null);
  const [overrideHistory, setOverrideHistory] = useState<WorkflowOverrideHistoryResponse | null>(null);
  const [draftCloneMessage, setDraftCloneMessage] = useState<string | null>(null);
  const [draftCloneId, setDraftCloneId] = useState<string | null>(null);
  const [draftCloning, setDraftCloning] = useState(false);
  const [draftPublishing, setDraftPublishing] = useState(false);
  const [publishMessage, setPublishMessage] = useState<string | null>(null);
  const [draftValidation, setDraftValidation] = useState<WorkflowDraftValidationResponse | null>(null);
  const [draftValidating, setDraftValidating] = useState(false);
  const [publishImpact, setPublishImpact] = useState<WorkflowPublishImpactResponse | null>(null);
  const [publishOutcome, setPublishOutcome] = useState<PublishOutcome | null>(null);
  const [postValidationAudit, setPostValidationAudit] = useState<WorkflowAuditResponse | null>(null);
  const [postValidationAuditLoading, setPostValidationAuditLoading] = useState(false);
  const [deletedStages, setDeletedStages] = useState<WorkflowDeletedStagesResponse | null>(null);
  const [selectedStageCode, setSelectedStageCode] = useState<string | null>(null);
  const [showPublishConfirm, setShowPublishConfirm] = useState(false);
  const [publishConfirmChecked, setPublishConfirmChecked] = useState(false);

  const loadDeletedStages = async (templateVersionId: string) => {
    const deleted = await workflowCatalogApi.deletedDraftStages(templateVersionId);
    setDeletedStages(deleted);
  };

  const loadOverrideHistory = async (projectId: string, templateVersionId: string) => {
    const history = await workflowCatalogApi.projectOverrideHistory(projectId, {
      templateVersionId,
      includeInactive: true,
    });
    setOverrideHistory(history);
  };

  useEffect(() => {
    if (!params.versionId) return;
    const projectId = searchParams.get("project_id") || undefined;
    const isDraftPreview = searchParams.get("draft") === "true";
    const request = isDraftPreview
      ? workflowCatalogApi.draftPreview(params.versionId)
      : workflowCatalogApi.preview(params.versionId, { projectId });
    request
      .then((payload) => {
        setPreview(payload);
        if (isDraftPreview) {
          workflowCatalogApi
            .draftPublishImpact(payload.workflow_template_version_id, { archivePrevious: true })
            .then(setPublishImpact)
            .catch(() => setPublishImpact(null));
          loadDeletedStages(payload.workflow_template_version_id).catch(() => setDeletedStages(null));
        } else {
          setPublishImpact(null);
          setPostValidationAudit(null);
          setDeletedStages(null);
        }
        if (payload.project_id) {
          return loadOverrideHistory(payload.project_id, payload.workflow_template_version_id).catch((e) => {
            setError(e instanceof Error ? e.message : "Failed to load override history");
          });
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.versionId, searchParams]);

  useEffect(() => {
    if (!preview || preview.status !== "DRAFT" || preview.preview_source !== "workflow_template_draft") {
      setPostValidationAudit(null);
      return;
    }
    const freshness = draftValidation?.freshness ?? preview.draft_freshness ?? null;
    if (!freshness?.last_validated_at) {
      setPostValidationAudit(null);
      return;
    }
    setPostValidationAuditLoading(true);
    workflowCatalogApi
      .templateAudit(preview.workflow_template_id, {
        versionId: preview.workflow_template_version_id,
        since: freshness.last_validated_at,
        excludeAction: "VALIDATE_DRAFT",
        limit: 25,
      })
      .then(setPostValidationAudit)
      .catch(() => setPostValidationAudit(null))
      .finally(() => setPostValidationAuditLoading(false));
  }, [preview, draftValidation?.freshness]);


  const createOverride = async (
    targetType: WorkflowTargetType,
    targetCode: string,
    operation: WorkflowOverrideOperation,
    overridePayload: Record<string, unknown>,
    reason: string,
  ) => {
    if (!preview?.project_id) return;
    setBusyTarget(`${targetType}:${targetCode}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.createProjectOverride(preview.project_id, {
        template_version_id: preview.workflow_template_version_id,
        target_type: targetType,
        target_code: targetCode,
        operation,
        override_payload: overridePayload,
        priority: 100,
        reason,
      });
      setPreview(updated);
      await loadOverrideHistory(preview.project_id, preview.workflow_template_version_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create override");
    } finally {
      setBusyTarget(null);
    }
  };

  const validateDraft = async () => {
    if (!preview) return null;
    setDraftValidating(true);
    setError(null);
    try {
      const validation = await workflowCatalogApi.validateDraftVersion(preview.workflow_template_version_id);
      setDraftValidation(validation);
      return validation;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to validate draft version");
      return null;
    } finally {
      setDraftValidating(false);
    }
  };

  const cloneDraft = async () => {
    if (!preview) return;
    setDraftCloning(true);
    setDraftCloneMessage(null);
    setDraftCloneId(null);
    setError(null);
    try {
      const draft = await workflowCatalogApi.cloneDraftVersion(preview.workflow_template_id, preview.workflow_template_version_id);
      setDraftCloneId(draft.draft_version_id);
      setDraftCloneMessage(`Draft ${draft.version} created with ${draft.stage_count} stages and ${draft.recommendation_count} recommendations. ID: ${draft.draft_version_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clone draft version");
    } finally {
      setDraftCloning(false);
    }
  };

  const publishDraft = async () => {
    if (!preview) return;
    setDraftPublishing(true);
    setPublishMessage(null);
    setPublishOutcome(null);
    setError(null);
    try {
      const validation = await workflowCatalogApi.validateDraftVersion(preview.workflow_template_version_id);
      const impact = await workflowCatalogApi.draftPublishImpact(preview.workflow_template_version_id, { archivePrevious: true });
      setDraftValidation(validation);
      setPublishImpact(impact);
      if (!validation.can_publish) {
        setError("Draft has blocking validation errors. Fix ERROR items before publishing.");
        return;
      }
      const published = await workflowCatalogApi.publishDraftVersion(preview.workflow_template_version_id, { archive_previous: true });
      setPreview(published);
      setDraftValidation(null);
      const finalImpact = published.publish_impact || impact;
      setPublishImpact(finalImpact);
      setPublishOutcome({ published, impact: finalImpact });
      setShowPublishConfirm(false);
      setPublishConfirmChecked(false);
      setPublishMessage(`Published ${published.workflow_template_code} version ${published.version}. Android catalog will now serve this version.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to publish draft version");
    } finally {
      setDraftPublishing(false);
    }
  };

  const updateDraftStage = async (stageCode: string, data: WorkflowDraftStageUpdateRequest) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_STAGE:${stageCode}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.updateDraftStage(preview.workflow_template_version_id, stageCode, data);
      setPreview(updated);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update draft stage");
    } finally {
      setBusyTarget(null);
    }
  };

  const createDraftRecommendation = async (stageCode: string, data: WorkflowDraftRecommendationRequest) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_STAGE:${stageCode}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.createDraftRecommendation(preview.workflow_template_version_id, stageCode, data);
      setPreview(updated);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add draft recommendation");
    } finally {
      setBusyTarget(null);
    }
  };

  const createDraftStage = async (afterStageCode: string, data: WorkflowDraftStageCreateRequest) => {
    if (!preview) return;
    const nextCode = normalizeStageCode(data.stage_code);
    setBusyTarget(`DRAFT_STAGE:${afterStageCode}:CREATE`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.createDraftStage(preview.workflow_template_version_id, {
        ...data,
        after_stage_code: afterStageCode,
        stage_code: nextCode,
      });
      setPreview(updated);
      setSelectedStageCode(nextCode);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create draft stage");
    } finally {
      setBusyTarget(null);
    }
  };

  const duplicateDraftStage = async (stageCode: string, data: WorkflowDraftStageDuplicateRequest) => {
    if (!preview) return;
    const nextCode = data.stage_code ? normalizeStageCode(data.stage_code) : undefined;
    setBusyTarget(`DRAFT_STAGE:${stageCode}:DUPLICATE`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.duplicateDraftStage(preview.workflow_template_version_id, stageCode, {
        ...data,
        after_stage_code: data.after_stage_code || stageCode,
        stage_code: nextCode,
      });
      setPreview(updated);
      if (nextCode) setSelectedStageCode(nextCode);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to duplicate draft stage");
    } finally {
      setBusyTarget(null);
    }
  };

  const reorderDraftStages = async (stageCodes: string[]) => {
    if (!preview) return;
    setBusyTarget("DRAFT_STAGE:REORDER");
    setError(null);
    try {
      const updated = await workflowCatalogApi.reorderDraftStages(preview.workflow_template_version_id, { stage_codes: stageCodes });
      setPreview(updated);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reorder draft stages");
    } finally {
      setBusyTarget(null);
    }
  };

  const deleteDraftStage = async (stageCode: string) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_STAGE:${stageCode}:DELETE`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.deleteDraftStage(preview.workflow_template_version_id, stageCode);
      setPreview(updated);
      setSelectedStageCode(updated.android_preview.stages[0]?.code || null);
      await loadDeletedStages(preview.workflow_template_version_id).catch(() => setDeletedStages(null));
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete draft stage");
    } finally {
      setBusyTarget(null);
    }
  };

  const updateDraftRecommendation = async (recommendationId: string, data: WorkflowDraftRecommendationRequest) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_REC:${recommendationId}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.updateDraftRecommendation(preview.workflow_template_version_id, recommendationId, data);
      setPreview(updated);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update draft recommendation");
    } finally {
      setBusyTarget(null);
    }
  };

  const reorderDraftRecommendations = async (stageCode: string, recommendationIds: string[]) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_REC_REORDER:${stageCode}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.reorderDraftRecommendations(preview.workflow_template_version_id, {
        stage_code: stageCode,
        recommendation_ids: recommendationIds,
      });
      setPreview(updated);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reorder draft recommendations");
    } finally {
      setBusyTarget(null);
    }
  };

  const restoreDraftStage = async (stageCode: string) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_STAGE:${stageCode}:RESTORE`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.restoreDraftStage(preview.workflow_template_version_id, stageCode);
      setPreview(updated);
      setSelectedStageCode(stageCode);
      await loadDeletedStages(preview.workflow_template_version_id).catch(() => setDeletedStages(null));
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to restore draft stage");
    } finally {
      setBusyTarget(null);
    }
  };

  const deleteDraftRecommendation = async (recommendationId: string) => {
    if (!preview) return;
    setBusyTarget(`DRAFT_REC:${recommendationId}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.deleteDraftRecommendation(preview.workflow_template_version_id, recommendationId);
      setPreview(updated);
      setDraftValidation(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete draft recommendation");
    } finally {
      setBusyTarget(null);
    }
  };

  const removeOverride = async (overrideId: string) => {
    if (!preview?.project_id) return;
    setBusyTarget(`OVERRIDE:${overrideId}`);
    setError(null);
    try {
      const updated = await workflowCatalogApi.deleteProjectOverride(preview.project_id, overrideId);
      setPreview(updated);
      await loadOverrideHistory(preview.project_id, preview.workflow_template_version_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove override");
    } finally {
      setBusyTarget(null);
    }
  };

  if (loading) return <div className="text-gray-500">Loading workflow preview...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!preview) return null;

  const isDraftPreview = preview.status === "DRAFT" && preview.preview_source === "workflow_template_draft";
  const draftFreshness = draftValidation?.freshness ?? preview.draft_freshness ?? null;
  const validationMissing = isDraftPreview && (!draftValidation || draftFreshness?.validation_current === false);
  const publishBlocked = isDraftPreview && (!draftValidation || draftFreshness?.validation_current === false || !draftValidation.can_publish);
  const publishBlockedReason = validationMissing ? "Run validation before opening publish confirmation" : "Fix blocking validation errors before publishing";
  const stages = preview.android_preview.stages || [];
  const selectedStage = stages.find((stage) => stage.code === selectedStageCode) || stages[0] || null;
  const recommendations = stages.flatMap((stage) => stage.recommended_activities || []);
  const dirtyTargets = dirtyTargetsFromAudit(postValidationAudit, stages);
  const warningCounts = preview.warnings.reduce<Record<string, number>>((acc, warning) => {
    acc[warning.level] = (acc[warning.level] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <Link href="/workflows" className="text-sm text-green-700 hover:underline">← Back to workflows</Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900">Workflow Preview</h1>
          <p className="mt-1 text-sm text-gray-500">
            Final Android-rendered workflow after enablements and overrides are applied.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{preview.crop_code}</Badge>
          <Badge>{preview.season_code}</Badge>
          <Badge>{preview.propagation_type_code || "Propagation —"}</Badge>
          <Badge>{preview.enablement_source}</Badge>
          {preview.project_id ? <Badge>Project scoped preview</Badge> : null}
        </div>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <Stat label="Stages" value={stages.length} />
        <Stat label="Recommendations" value={recommendations.length} />
        <Stat label="Duration days" value={preview.total_duration_days} />
        <Stat label="Warnings" value={preview.warnings.length} tone={preview.warnings.length ? "warn" : "ok"} />
      </div>

      {isDraftPreview ? (
        <DraftFreshnessCard
          freshness={draftFreshness}
          validation={draftValidation}
          postValidationAudit={postValidationAudit}
          auditLoading={postValidationAuditLoading}
          validating={draftValidating}
          onValidate={validateDraft}
        />
      ) : null}

      {validationMissing ? (
        <div className="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800 shadow-sm">
          <p className="font-semibold">Draft validation is missing or stale.</p>
          <p className="mt-1">Recent draft edits clear validation. Run validation again before publishing this workflow to Android.</p>
        </div>
      ) : null}

      {publishOutcome ? <PublishOutcomeCard outcome={publishOutcome} /> : null}

      <div className="mb-6 rounded-lg bg-white p-5 shadow">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{labelText(preview.label)}</h2>
            <p className="mt-1 text-sm text-gray-500">
              {preview.workflow_template_code} · version {preview.version} · {preview.status}
            </p>
            {draftCloneMessage ? (
              <div className="mt-3 rounded bg-green-50 p-3 text-sm text-green-700">
                <p>{draftCloneMessage}</p>
                {draftCloneId ? <Link className="mt-2 inline-block font-medium underline" href={`/workflows/preview/${draftCloneId}?draft=true`}>Open draft preview</Link> : null}
              </div>
            ) : null}
            {publishMessage ? (
              <div className="mt-3 rounded bg-green-50 p-3 text-sm text-green-700">{publishMessage}</div>
            ) : null}
          </div>
          <div className="text-right text-xs text-gray-500">
            <p>Template: <span className="font-mono">{preview.workflow_template_id}</span></p>
            <p>Version: <span className="font-mono">{preview.workflow_template_version_id}</span></p>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                disabled={draftCloning || preview.status !== "PUBLISHED"}
                onClick={cloneDraft}
                className="rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
              >
                {draftCloning ? "Cloning draft..." : "Clone draft"}
              </button>
              <button
                type="button"
                disabled={draftValidating || !isDraftPreview}
                onClick={validateDraft}
                className="rounded border border-yellow-200 px-3 py-1.5 text-xs font-medium text-yellow-700 hover:bg-yellow-50 disabled:cursor-wait disabled:opacity-60"
              >
                {draftValidating ? "Validating..." : "Validate draft"}
              </button>
              <button
                type="button"
                disabled={draftPublishing || draftValidating || !isDraftPreview || publishBlocked}
                onClick={() => {
                  setPublishConfirmChecked(false);
                  setShowPublishConfirm(true);
                }}
                className="rounded border border-blue-200 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-wait disabled:opacity-60"
                title={publishBlocked ? publishBlockedReason : undefined}
              >
                {draftPublishing ? "Publishing..." : validationMissing ? "Validate before publish" : "Publish draft"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {isDraftPreview && showPublishConfirm ? (
        <PublishConfirmationModal
          preview={preview}
          stages={stages}
          validation={draftValidation}
          impact={publishImpact}
          publishing={draftPublishing || draftValidating}
          confirmed={publishConfirmChecked}
          onConfirmedChange={setPublishConfirmChecked}
          onCancel={() => {
            setShowPublishConfirm(false);
            setPublishConfirmChecked(false);
          }}
          onPublish={publishDraft}
        />
      ) : null}

      {isDraftPreview ? (
        <div className="space-y-4">
          <PublishReadinessChecklist
            stages={stages}
            validation={draftValidation}
            freshness={draftFreshness}
            validating={draftValidating}
            impact={publishImpact}
            onValidate={validateDraft}
          />
          <PublishImpactPanel impact={publishImpact} />
          <DraftValidationPanel validation={draftValidation} validating={draftValidating} onValidate={validateDraft} />
          <DeletedStagesPanel deletedStages={deletedStages} busyTarget={busyTarget} onRestoreStage={restoreDraftStage} />
        </div>
      ) : null}


      <VisualWorkflowBuilder
        stages={stages}
        dirtyTargets={dirtyTargets}
        selectedStageCode={selectedStage?.code || null}
        onSelectStage={setSelectedStageCode}
        cropCode={preview.crop_code}
        projectId={preview.project_id || undefined}
        draftEditable={isDraftPreview}
        projectScoped={Boolean(preview.project_id)}
        busyTarget={busyTarget}
        onCreateDraftStage={createDraftStage}
        onDuplicateDraftStage={duplicateDraftStage}
        onReorderDraftStages={reorderDraftStages}
        onDeleteDraftStage={deleteDraftStage}
        onReorderDraftRecommendations={reorderDraftRecommendations}
        onUpdateDraftStage={updateDraftStage}
        onCreateDraftRecommendation={createDraftRecommendation}
        onUpdateDraftRecommendation={updateDraftRecommendation}
        onDeleteDraftRecommendation={deleteDraftRecommendation}
      />

      <div className="mb-6 grid gap-6 xl:grid-cols-[420px_1fr]">
        <WarningsPanel warnings={preview.warnings} warningCounts={warningCounts} />
        <OverridesPanel
          overrides={preview.applied_overrides}
          projectScoped={Boolean(preview.project_id)}
          busyTarget={busyTarget}
          onRemoveOverride={removeOverride}
        />
      </div>

      {preview.project_id ? (
        <OverrideHistoryPanel
          history={overrideHistory}
          busyTarget={busyTarget}
          onRemoveOverride={removeOverride}
        />
      ) : null}

      <div className="mb-6 rounded-lg bg-white shadow">
        <div className="border-b p-5">
          <h2 className="text-lg font-semibold text-gray-900">Rendered Stages & Recommendations</h2>
        </div>
        <div className="divide-y">
          {stages.map((stage) => (
            <StagePreview
              key={stage.code}
              stage={stage}
              cropCode={preview.crop_code}
              projectId={preview.project_id || undefined}
              projectScoped={Boolean(preview.project_id)}
              draftEditable={preview.status === "DRAFT" && preview.preview_source === "workflow_template_draft"}
              busyTarget={busyTarget}
              onCreateOverride={createOverride}
              onUpdateDraftStage={updateDraftStage}
              onCreateDraftRecommendation={createDraftRecommendation}
              onUpdateDraftRecommendation={updateDraftRecommendation}
              onDeleteDraftRecommendation={deleteDraftRecommendation}
            />
          ))}
        </div>
      </div>

      <details className="rounded-lg bg-gray-950 p-5 text-gray-100 shadow" open>
        <summary className="cursor-pointer text-sm font-semibold">Raw Android Preview JSON</summary>
        <pre className="mt-4 max-h-[520px] overflow-auto text-xs leading-relaxed">
          {JSON.stringify(preview.android_preview, null, 2)}
        </pre>
      </details>
    </div>
  );
}


function scrollToStageEditor(stageCode: string, intent: "stage" | "recommendation" = "stage", recommendationAnchor?: string) {
  const element = document.getElementById(`stage-editor-${stageCode}`);
  if (element instanceof HTMLDetailsElement) element.open = true;
  if (recommendationAnchor) {
    const canvasTarget = document.getElementById(`canvas-recommendation-${recommendationAnchor}`);
    if (canvasTarget) {
      canvasTarget.scrollIntoView({ behavior: "smooth", block: "center" });
      canvasTarget.classList.add("ring-2", "ring-green-300");
      window.setTimeout(() => canvasTarget.classList.remove("ring-2", "ring-green-300"), 1600);
      return;
    }
  }
  if (!element) return;
  element.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    const target = recommendationAnchor
      ? document.getElementById(`recommendation-${recommendationAnchor}`)
      : document.getElementById(`stage-${intent}-${stageCode}`);
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (target && recommendationAnchor) {
      target.classList.add("ring-2", "ring-green-300");
      window.setTimeout(() => target.classList.remove("ring-2", "ring-green-300"), 1600);
    }
  }, 250);
}

function DeletedStagesPanel({
  deletedStages,
  busyTarget,
  onRestoreStage,
}: {
  deletedStages: WorkflowDeletedStagesResponse | null;
  busyTarget: string | null;
  onRestoreStage: (stageCode: string) => void;
}) {
  const rows = deletedStages?.deleted_stages || [];
  return (
    <div className="mb-6 rounded-lg bg-white p-5 shadow">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Deleted draft stages</h2>
          <p className="text-sm text-gray-500">Soft-deleted stages can be restored before the draft is published.</p>
        </div>
        <Badge>{rows.length} deleted</Badge>
      </div>
      {rows.length === 0 ? (
        <p className="mt-4 rounded bg-gray-50 p-3 text-sm text-gray-500">No deleted stages in this draft.</p>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {rows.map((stage) => {
            const restoring = busyTarget === `DRAFT_STAGE:${stage.stage_code}:RESTORE`;
            return (
              <div key={stage.template_stage_id} className="rounded border border-gray-200 bg-gray-50 p-4 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900">{labelText(stage.stage_name) || stage.stage_code}</p>
                    <p className="mt-1 font-mono text-xs text-gray-500">{stage.stage_code}</p>
                  </div>
                  <Badge>{stage.recommendation_count} recs</Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                  <Badge>{stage.duration_days || 0} days</Badge>
                  {stage.stage_type ? <Badge>{stage.stage_type}</Badge> : null}
                  {stage.phase ? <Badge>{stage.phase}</Badge> : null}
                </div>
                <button
                  type="button"
                  disabled={Boolean(busyTarget)}
                  onClick={() => onRestoreStage(stage.stage_code)}
                  className="mt-4 rounded border border-blue-200 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-wait disabled:opacity-60"
                >
                  {restoring ? "Restoring..." : "Restore stage"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function VisualWorkflowBuilder({
  stages,
  dirtyTargets,
  selectedStageCode,
  onSelectStage,
  cropCode,
  projectId,
  draftEditable,
  projectScoped,
  busyTarget,
  onCreateDraftStage,
  onDuplicateDraftStage,
  onReorderDraftStages,
  onDeleteDraftStage,
  onReorderDraftRecommendations,
  onUpdateDraftStage,
  onCreateDraftRecommendation,
  onUpdateDraftRecommendation,
  onDeleteDraftRecommendation,
}: {
  stages: WorkflowStage[];
  dirtyTargets: DirtyTargets;
  selectedStageCode: string | null;
  onSelectStage: (stageCode: string) => void;
  cropCode: string;
  projectId?: string;
  draftEditable: boolean;
  projectScoped: boolean;
  busyTarget: string | null;
  onCreateDraftStage: (afterStageCode: string, data: WorkflowDraftStageCreateRequest) => void;
  onDuplicateDraftStage: (stageCode: string, data: WorkflowDraftStageDuplicateRequest) => void;
  onReorderDraftStages: (stageCodes: string[]) => void;
  onDeleteDraftStage: (stageCode: string) => void;
  onReorderDraftRecommendations: (stageCode: string, recommendationIds: string[]) => void;
  onUpdateDraftStage: (stageCode: string, data: WorkflowDraftStageUpdateRequest) => void;
  onCreateDraftRecommendation: (stageCode: string, data: WorkflowDraftRecommendationRequest) => void;
  onUpdateDraftRecommendation: (recommendationId: string, data: WorkflowDraftRecommendationRequest) => void;
  onDeleteDraftRecommendation: (recommendationId: string) => void;
}) {
  const selectedStage = stages.find((stage) => stage.code === selectedStageCode) || stages[0];
  const selectedStageIndex = selectedStage ? stages.findIndex((stage) => stage.code === selectedStage.code) : -1;
  const [stageAction, setStageAction] = useState<StageActionMode | null>(null);
  const [draggedStageCode, setDraggedStageCode] = useState<string | null>(null);
  const [draggedRecommendationIndex, setDraggedRecommendationIndex] = useState<number | null>(null);
  const totalDuration = stages.reduce((sum, stage) => sum + (stage.duration_days || 0), 0);
  const submitRecommendationOrder = (stage: WorkflowStage, recs: WorkflowRecommendation[]) => {
    const ids = recs.map(recommendationId).filter((id): id is string => Boolean(id));
    if (ids.length !== recs.length) return;
    onReorderDraftRecommendations(stage.code, ids);
  };
  const moveRecommendation = (stage: WorkflowStage, recommendationIndex: number, direction: -1 | 1) => {
    const recs = stage.recommended_activities || [];
    const targetIndex = recommendationIndex + direction;
    if (targetIndex < 0 || targetIndex >= recs.length) return;
    submitRecommendationOrder(stage, moveItem(recs, recommendationIndex, targetIndex));
  };
  const dragRecommendationTo = (stage: WorkflowStage, toIndex: number) => {
    const recs = stage.recommended_activities || [];
    if (draggedRecommendationIndex === null || draggedRecommendationIndex === toIndex) return;
    submitRecommendationOrder(stage, moveItem(recs, draggedRecommendationIndex, toIndex));
    setDraggedRecommendationIndex(null);
  };
  const submitStageOrder = (orderedStages: WorkflowStage[]) => {
    onReorderDraftStages(orderedStages.map((stage) => stage.code));
  };
  const moveSelectedStage = (direction: -1 | 1) => {
    if (!selectedStage || selectedStageIndex < 0) return;
    const targetIndex = selectedStageIndex + direction;
    if (targetIndex < 0 || targetIndex >= stages.length) return;
    submitStageOrder(moveItem(stages, selectedStageIndex, targetIndex));
  };
  const dragStageTo = (toIndex: number) => {
    if (!draggedStageCode) return;
    const fromIndex = stages.findIndex((stage) => stage.code === draggedStageCode);
    if (fromIndex < 0 || fromIndex === toIndex) return;
    submitStageOrder(moveItem(stages, fromIndex, toIndex));
    setDraggedStageCode(null);
  };
  const maxRecommendations = Math.max(1, ...stages.map((stage) => stage.recommended_activities?.length || 0));
  const stageHintMap = new Map(stages.map((stage) => [stage.code, stageDesignHints(stage)]));
  const totalDesignHints = Array.from(stageHintMap.values()).reduce((sum, hints) => sum + hints.length, 0);
  const blockingDesignHints = Array.from(stageHintMap.values()).reduce((sum, hints) => sum + hints.filter((hint) => hint.level === "ERROR").length, 0);
  const dirtyStageCount = dirtyTargets.stageCodes.size;
  const dirtyRecommendationCount = dirtyTargets.recommendationIds.size;

  return (
    <div id="visual-workflow-builder" className="mb-6 rounded-xl border border-green-100 bg-white shadow">
      <div className="border-b border-green-100 p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Visual Workflow Builder</h2>
            <p className="mt-1 text-sm text-gray-500">Stage canvas for the Android-rendered crop cycle. Select a stage to inspect recommendations and timing.</p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge>{stages.length} stages</Badge>
            <Badge>{totalDuration} days</Badge>
            <Badge>{draftEditable ? "Draft editable" : "Read-only published"}</Badge>
            {dirtyStageCount || dirtyRecommendationCount ? <Badge>{dirtyStageCount} dirty stage(s), {dirtyRecommendationCount} dirty rec(s)</Badge> : null}
            {totalDesignHints ? <Badge>{blockingDesignHints ? `${blockingDesignHints} blocking hints` : `${totalDesignHints} design hints`}</Badge> : <Badge>No design hints</Badge>}
            {projectScoped ? <Badge>Project overrides visible</Badge> : null}
          </div>
        </div>
      </div>

      <div className="p-5">
        {stages.length === 0 ? (
          <p className="rounded bg-gray-50 p-4 text-sm text-gray-500">No stages are present in this workflow version.</p>
        ) : (
          <div className="space-y-5">
            <WorkflowSummaryMetrics stages={stages} />
            <div className="overflow-x-auto pb-3">
              <div className="flex min-w-max items-stretch gap-3">
                {stages.map((stage, index) => {
                  const recCount = stage.recommended_activities?.length || 0;
                  const selected = stage.code === selectedStage?.code;
                  const recIntensity = Math.max(8, Math.round((recCount / maxRecommendations) * 36));
                  const hints = stageHintMap.get(stage.code) || [];
                  const errorCount = hints.filter((hint) => hint.level === "ERROR").length;
                  const warnCount = hints.filter((hint) => hint.level === "WARN").length;
                  const dirtyStage = dirtyTargets.stageCodes.has(stage.code);
                  const dirtyRecCount = (stage.recommended_activities || []).filter((rec) => {
                    const recId = recommendationId(rec);
                    return recId ? dirtyTargets.recommendationIds.has(recId) : false;
                  }).length;
                  return (
                    <button
                      key={stage.code}
                      type="button"
                      draggable={draftEditable && !busyTarget}
                      onDragStart={(event) => {
                        if (!draftEditable || busyTarget) return;
                        setDraggedStageCode(stage.code);
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", stage.code);
                      }}
                      onDragOver={(event) => {
                        if (!draftEditable || !draggedStageCode || draggedStageCode === stage.code) return;
                        event.preventDefault();
                        event.dataTransfer.dropEffect = "move";
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        dragStageTo(index);
                      }}
                      onDragEnd={() => setDraggedStageCode(null)}
                      onClick={() => onSelectStage(stage.code)}
                      onDoubleClick={() => scrollToStageEditor(stage.code)}
                      title={draftEditable ? "Drag to reorder; double-click to edit details" : "Double-click to inspect details"}
                      className={`group relative flex w-56 flex-col rounded-xl border p-4 text-left transition ${selected ? "border-green-500 bg-green-50 shadow-md ring-2 ring-green-100" : dirtyStage || dirtyRecCount ? "border-orange-300 bg-orange-50 hover:border-orange-400" : "border-gray-200 bg-white hover:border-green-300 hover:bg-green-50/40"} ${draggedStageCode === stage.code ? "opacity-50" : ""}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Stage {index + 1}</p>
                          <h3 className="mt-1 line-clamp-2 font-semibold text-gray-900">{labelText(stage.name)}</h3>
                        </div>
                        <span className="rounded-full bg-gray-100 px-2 py-1 text-[10px] font-medium text-gray-600">{stage.code}</span>
                      </div>
                      {hints.length ? (
                        <div className="mt-3 flex flex-wrap gap-1">
                          {errorCount ? <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">{errorCount} error</span> : null}
                          {warnCount ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">{warnCount} warn</span> : null}
                          {!errorCount && !warnCount ? <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">{hints.length} info</span> : null}
                        </div>
                      ) : null}
                      {dirtyStage || dirtyRecCount ? (
                        <div className="mt-3 flex flex-wrap gap-1">
                          {dirtyStage ? <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold text-orange-700">Edited after validation</span> : null}
                          {dirtyRecCount ? <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold text-orange-700">{dirtyRecCount} dirty rec</span> : null}
                        </div>
                      ) : null}
                      <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                        <MiniMetric label="Start" value={`D+${stage.day_offset ?? 0}`} />
                        <MiniMetric label="Days" value={stage.duration_days || 0} />
                        <MiniMetric label="Recs" value={recCount} />
                      </div>
                      <div className="mt-4 h-2 rounded-full bg-gray-100">
                        <div className="h-2 rounded-full bg-green-500" style={{ width: `${recIntensity}%` }} />
                      </div>
                      <p className="mt-2 text-[11px] text-gray-400">{draftEditable ? "Drag to reorder" : "Recommendation density"}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <WorkflowTimeline
              stages={stages}
              dirtyTargets={dirtyTargets}
              selectedStageCode={selectedStage?.code || null}
              onSelectStage={onSelectStage}
              onSelectRecommendation={(stageCode, anchorId) => {
                onSelectStage(stageCode);
                window.setTimeout(() => scrollToStageEditor(stageCode, "recommendation", anchorId), 80);
              }}
            />

            {selectedStage ? (
              <div className="space-y-4">
                <StageInspector
                  stage={selectedStage}
                  hints={stageHintMap.get(selectedStage.code) || []}
                  dirtyTargets={dirtyTargets}
                  cropCode={cropCode}
                  projectId={projectId}
                  draftEditable={draftEditable}
                  busyTarget={busyTarget}
                  activeStageAction={stageAction}
                  onEditStage={() => scrollToStageEditor(selectedStage.code, "stage")}
                  onAddRecommendation={() => scrollToStageEditor(selectedStage.code, "recommendation")}
                  onCreateStageAfter={() => setStageAction(stageAction === "CREATE" ? null : "CREATE")}
                  onDuplicateStage={() => setStageAction(stageAction === "DUPLICATE" ? null : "DUPLICATE")}
                  onMoveEarlier={() => moveSelectedStage(-1)}
                  onMoveLater={() => moveSelectedStage(1)}
                  canMoveEarlier={draftEditable && selectedStageIndex > 0}
                  canMoveLater={draftEditable && selectedStageIndex >= 0 && selectedStageIndex < stages.length - 1}
                  draggedRecommendationIndex={draggedRecommendationIndex}
                  onRecommendationDragStart={setDraggedRecommendationIndex}
                  onRecommendationDragEnd={() => setDraggedRecommendationIndex(null)}
                  onRecommendationDrop={(recommendationIndex) => dragRecommendationTo(selectedStage, recommendationIndex)}
                  onMoveRecommendation={(recommendationIndex, direction) => moveRecommendation(selectedStage, recommendationIndex, direction)}
                  onDeleteStage={() => {
                    if (window.confirm(`Delete stage ${selectedStage.code} from this draft? Its recommendations will also be deactivated.`)) {
                      onDeleteDraftStage(selectedStage.code);
                    }
                  }}
                  canDeleteStage={draftEditable && stages.length > 1}
                  onUpdateDraftStage={onUpdateDraftStage}
                  onCreateDraftRecommendation={onCreateDraftRecommendation}
                  onUpdateDraftRecommendation={onUpdateDraftRecommendation}
                  onDeleteDraftRecommendation={onDeleteDraftRecommendation}
                />
                {draftEditable && stageAction ? (
                  <StageActionPanel
                    key={`${selectedStage.code}-${stageAction}`}
                    mode={stageAction}
                    stage={selectedStage}
                    busy={Boolean(busyTarget)}
                    onCancel={() => setStageAction(null)}
                    onSubmit={(payload) => {
                      if (stageAction === "CREATE") {
                        onCreateDraftStage(selectedStage.code, payload as WorkflowDraftStageCreateRequest);
                      } else {
                        onDuplicateDraftStage(selectedStage.code, payload as WorkflowDraftStageDuplicateRequest);
                      }
                      setStageAction(null);
                    }}
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded bg-white/80 p-2"><p className="text-[10px] uppercase text-gray-400">{label}</p><p className="font-semibold text-gray-900">{value}</p></div>;
}

function WorkflowSummaryMetrics({ stages }: { stages: WorkflowStage[] }) {
  const allRecommendations = stages.flatMap((stage) => stage.recommended_activities || []);
  const totalRecommendations = allRecommendations.length;
  const criticalCount = allRecommendations.filter((rec) => rec.is_critical).length;
  const catalogCount = allRecommendations.filter((rec) => recommendationSource(rec) === "CATALOG").length;
  const customCount = allRecommendations.filter((rec) => recommendationSource(rec) === "CUSTOM").length;
  const uncodedCount = allRecommendations.filter((rec) => recommendationSource(rec) === "UNCODED").length;
  const stageHints = stages.map((stage) => stageDesignHints(stage));
  const stagesWithHints = stageHints.filter((hints) => hints.length > 0).length;
  const stagesWithErrors = stageHints.filter((hints) => hints.some((hint) => hint.level === "ERROR")).length;
  const stagesWithWarnings = stageHints.filter((hints) => hints.some((hint) => hint.level === "WARN")).length;
  const totalHints = stageHints.reduce((sum, hints) => sum + hints.length, 0);
  const catalogPercent = totalRecommendations ? Math.round((catalogCount / totalRecommendations) * 100) : 0;
  const criticalPercent = totalRecommendations ? Math.round((criticalCount / totalRecommendations) * 100) : 0;

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Workflow summary metrics</h3>
          <p className="text-xs text-gray-500">At-a-glance draft health before publish validation.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{totalHints} total hints</Badge>
          {stagesWithErrors ? <Badge>{stagesWithErrors} stages with errors</Badge> : <Badge>No stage errors</Badge>}
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        <SummaryMetric label="Stages" value={stages.length} tone="neutral" />
        <SummaryMetric label="Recommendations" value={totalRecommendations} tone="neutral" />
        <SummaryMetric label="Critical" value={criticalCount} detail={`${criticalPercent}%`} tone={criticalCount ? "danger" : "muted"} />
        <SummaryMetric label="Catalog" value={catalogCount} detail={`${catalogPercent}%`} tone="success" />
        <SummaryMetric label="Custom" value={customCount} tone={customCount ? "warning" : "muted"} />
        <SummaryMetric label="Uncoded" value={uncodedCount} tone={uncodedCount ? "warning" : "muted"} />
        <SummaryMetric label="Hint stages" value={stagesWithHints} tone={stagesWithHints ? "warning" : "success"} />
        <SummaryMetric label="Error stages" value={stagesWithErrors} detail={stagesWithWarnings ? `${stagesWithWarnings} warn` : undefined} tone={stagesWithErrors ? "danger" : "success"} />
      </div>
    </div>
  );
}

function SummaryMetric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone: "neutral" | "success" | "warning" | "danger" | "muted";
}) {
  const toneClass = {
    neutral: "border-gray-200 bg-white text-gray-900",
    success: "border-green-200 bg-green-50 text-green-800",
    warning: "border-amber-200 bg-amber-50 text-amber-800",
    danger: "border-red-200 bg-red-50 text-red-800",
    muted: "border-gray-200 bg-gray-100 text-gray-500",
  }[tone];
  return (
    <div className={`rounded-lg border p-3 ${toneClass}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{label}</p>
      <div className="mt-1 flex items-baseline gap-2">
        <p className="text-xl font-bold">{value}</p>
        {detail ? <p className="text-[11px] font-medium opacity-70">{detail}</p> : null}
      </div>
    </div>
  );
}

function WorkflowTimeline({
  stages,
  dirtyTargets,
  selectedStageCode,
  onSelectStage,
  onSelectRecommendation,
}: {
  stages: WorkflowStage[];
  dirtyTargets: DirtyTargets;
  selectedStageCode: string | null;
  onSelectStage: (stageCode: string) => void;
  onSelectRecommendation: (stageCode: string, recommendationAnchor: string) => void;
}) {
  const [showRecommendations, setShowRecommendations] = useState(true);
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [stageFilter, setStageFilter] = useState<"ALL" | "HINTS" | "ERRORS">("ALL");
  const stageEndDays = stages.map((stage) => (stage.day_offset ?? 0) + Math.max(1, stage.duration_days || 1));
  const recommendationDays = stages.flatMap((stage) =>
    (stage.recommended_activities || []).map((rec) => (stage.day_offset ?? 0) + rec.day_offset),
  );
  const timelineEndDay = Math.max(1, ...stageEndDays, ...recommendationDays);
  const toPercent = (day: number) => `${Math.min(100, Math.max(0, (day / timelineEndDay) * 100))}%`;
  const visibleStages = stages.filter((stage) => {
    const hints = stageDesignHints(stage);
    if (stageFilter === "ERRORS") return hints.some((hint) => hint.level === "ERROR");
    if (stageFilter === "HINTS") return hints.length > 0;
    return true;
  });

  return (
    <div id="workflow-timeline" className="rounded-xl border border-gray-200 bg-gray-50 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Workflow timing timeline</h3>
          <p className="text-xs text-gray-500">Stage spans use cycle day offsets; dots show recommendation timing inside each stage.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>D0</Badge>
          <Badge>D+{timelineEndDay}</Badge>
          <Badge>{visibleStages.length}/{stages.length} stages</Badge>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 rounded-lg border border-gray-200 bg-white p-2 text-xs">
        <button type="button" onClick={() => setShowRecommendations((value) => !value)} className={`rounded px-3 py-1.5 font-medium ${showRecommendations ? "bg-green-700 text-white" : "border text-gray-700"}`}>{showRecommendations ? "Dots on" : "Dots off"}</button>
        <button type="button" disabled={!showRecommendations} onClick={() => setCriticalOnly((value) => !value)} className={`rounded px-3 py-1.5 font-medium disabled:cursor-not-allowed disabled:opacity-50 ${criticalOnly ? "bg-red-600 text-white" : "border text-gray-700"}`}>Critical only</button>
        <button type="button" onClick={() => setStageFilter("ALL")} className={`rounded px-3 py-1.5 font-medium ${stageFilter === "ALL" ? "bg-gray-900 text-white" : "border text-gray-700"}`}>All stages</button>
        <button type="button" onClick={() => setStageFilter("HINTS")} className={`rounded px-3 py-1.5 font-medium ${stageFilter === "HINTS" ? "bg-amber-600 text-white" : "border text-gray-700"}`}>With hints</button>
        <button type="button" onClick={() => setStageFilter("ERRORS")} className={`rounded px-3 py-1.5 font-medium ${stageFilter === "ERRORS" ? "bg-red-600 text-white" : "border text-gray-700"}`}>Errors only</button>
      </div>
      <div className="mt-4 min-w-[760px] space-y-2 overflow-x-auto pb-1">
        <div className="relative h-7 rounded bg-white">
          {[0, 25, 50, 75, 100].map((tick) => (
            <div key={tick} className="absolute top-0 h-7 border-l border-gray-200" style={{ left: `${tick}%` }}>
              <span className="ml-1 text-[10px] text-gray-400">D+{Math.round((tick / 100) * timelineEndDay)}</span>
            </div>
          ))}
        </div>
        {visibleStages.length === 0 ? <p className="rounded bg-white p-3 text-sm text-gray-500">No stages match the selected timeline filter.</p> : null}
        {visibleStages.map((stage) => {
          const originalIndex = stages.findIndex((candidate) => candidate.code === stage.code);
          const startDay = stage.day_offset ?? 0;
          const duration = Math.max(1, stage.duration_days || 1);
          const selected = selectedStageCode === stage.code;
          const hints = stageDesignHints(stage);
          const hasError = hints.some((hint) => hint.level === "ERROR");
          const hasWarn = hints.some((hint) => hint.level === "WARN");
          const dirtyStage = dirtyTargets.stageCodes.has(stage.code);
          const visibleRecommendations = showRecommendations
            ? (stage.recommended_activities || [])
                .map((rec, originalRecommendationIndex) => ({ rec, originalRecommendationIndex }))
                .filter(({ rec }) => !criticalOnly || rec.is_critical)
            : [];
          return (
            <button
              key={stage.code}
              type="button"
              onClick={() => onSelectStage(stage.code)}
              className={`relative block h-14 w-full rounded-lg border bg-white text-left transition hover:border-green-300 hover:bg-green-50/40 ${selected ? "border-green-500 ring-2 ring-green-100" : dirtyStage ? "border-orange-300" : hasError ? "border-red-200" : hasWarn ? "border-amber-200" : "border-gray-200"}`}
            >
              <div
                className={`absolute top-3 h-8 rounded ${selected ? "bg-green-600" : dirtyStage ? "bg-orange-500" : hasError ? "bg-red-500" : hasWarn ? "bg-amber-500" : "bg-green-500"}`}
                style={{ left: toPercent(startDay), width: `max(32px, ${Math.max(2, (duration / timelineEndDay) * 100)}%)` }}
              />
              <div className="absolute left-3 top-1 z-10 flex items-center gap-2 text-[11px]">
                <span className="rounded bg-white/90 px-2 py-0.5 font-semibold text-gray-800">{originalIndex + 1}. {labelText(stage.name) || stage.code}</span>
                <span className="rounded bg-white/80 px-2 py-0.5 font-mono text-gray-500">{stage.code}</span>
                <span className="rounded bg-white/80 px-2 py-0.5 text-gray-500">D+{startDay} / {duration}d</span>
                {hints.length ? <span className={`rounded px-2 py-0.5 ${hasError ? "bg-red-100 text-red-700" : hasWarn ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"}`}>{hints.length} hint</span> : null}
                {dirtyStage ? <span className="rounded bg-orange-100 px-2 py-0.5 text-orange-700">dirty</span> : null}
              </div>
              {visibleRecommendations.slice(0, 18).map(({ rec, originalRecommendationIndex }) => {
                const recDay = startDay + rec.day_offset;
                const anchorId = recommendationAnchorId(stage.code, rec, originalRecommendationIndex);
                const recId = recommendationId(rec);
                const dirtyRec = recId ? dirtyTargets.recommendationIds.has(recId) : false;
                return (
                  <span
                    key={`${stage.code}-${rec.input_code || rec.input_name}-${originalRecommendationIndex}`}
                    role="button"
                    tabIndex={0}
                    title={`${rec.input_name || rec.activity_type} - D+${recDay}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectRecommendation(stage.code, anchorId);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        event.stopPropagation();
                        onSelectRecommendation(stage.code, anchorId);
                      }
                    }}
                    className={`absolute top-8 z-20 h-3 w-3 rounded-full border-2 border-white shadow outline-none ring-offset-2 hover:ring-2 hover:ring-green-300 focus:ring-2 focus:ring-green-400 ${dirtyRec ? "bg-orange-500 ring-2 ring-orange-200" : rec.is_critical ? "bg-red-500" : "bg-blue-500"}`}
                    style={{ left: toPercent(recDay) }}
                  />
                );
              })}
              {visibleRecommendations.length > 18 ? (
                <span className="absolute right-2 top-8 rounded bg-gray-900 px-2 py-0.5 text-[10px] font-medium text-white">+{visibleRecommendations.length - 18}</span>
              ) : null}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-gray-500">
        <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-blue-500" /> Recommendation</span>
        <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-red-500" /> Critical recommendation</span>
        <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-amber-500" /> Stage with warning</span>
        <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-orange-500" /> Edited after validation</span>
        <span>Click a row to inspect that stage.</span>
      </div>
    </div>
  );
}

function StageInspector({
  stage,
  hints,
  dirtyTargets,
  cropCode,
  projectId,
  draftEditable,
  busyTarget,
  activeStageAction,
  onEditStage,
  onAddRecommendation,
  onCreateStageAfter,
  onDuplicateStage,
  onMoveEarlier,
  onMoveLater,
  canMoveEarlier,
  canMoveLater,
  draggedRecommendationIndex,
  onRecommendationDragStart,
  onRecommendationDragEnd,
  onRecommendationDrop,
  onMoveRecommendation,
  onDeleteStage,
  canDeleteStage,
  onUpdateDraftStage,
  onCreateDraftRecommendation,
  onUpdateDraftRecommendation,
  onDeleteDraftRecommendation,
}: {
  stage: WorkflowStage;
  hints: StageDesignHint[];
  dirtyTargets: DirtyTargets;
  cropCode: string;
  projectId?: string;
  draftEditable: boolean;
  busyTarget: string | null;
  activeStageAction: StageActionMode | null;
  onEditStage: () => void;
  onAddRecommendation: () => void;
  onCreateStageAfter: () => void;
  onDuplicateStage: () => void;
  onMoveEarlier: () => void;
  onMoveLater: () => void;
  canMoveEarlier: boolean;
  canMoveLater: boolean;
  draggedRecommendationIndex: number | null;
  onRecommendationDragStart: (recommendationIndex: number) => void;
  onRecommendationDragEnd: () => void;
  onRecommendationDrop: (recommendationIndex: number) => void;
  onMoveRecommendation: (recommendationIndex: number, direction: -1 | 1) => void;
  onDeleteStage: () => void;
  canDeleteStage: boolean;
  onUpdateDraftStage: (stageCode: string, data: WorkflowDraftStageUpdateRequest) => void;
  onCreateDraftRecommendation: (stageCode: string, data: WorkflowDraftRecommendationRequest) => void;
  onUpdateDraftRecommendation: (recommendationId: string, data: WorkflowDraftRecommendationRequest) => void;
  onDeleteDraftRecommendation: (recommendationId: string) => void;
}) {
  const recs = stage.recommended_activities || [];
  const dirtyStage = dirtyTargets.stageCodes.has(stage.code);
  const [stageNameDraft, setStageNameDraft] = useState(labelText(stage.name));
  const [durationDraft, setDurationDraft] = useState(String(stage.duration_days || 0));
  const [showInlineRecommendationForm, setShowInlineRecommendationForm] = useState(false);

  useEffect(() => {
    setStageNameDraft(labelText(stage.name));
    setDurationDraft(String(stage.duration_days || 0));
    setShowInlineRecommendationForm(false);
  }, [stage.code, stage.name, stage.duration_days]);
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <div className="flex flex-wrap gap-2 text-xs"><Badge>{stage.code}</Badge><Badge>{stage.stage_type || "Stage"}</Badge><Badge>{stage.phase || "Phase ?"}</Badge>{dirtyStage ? <Badge>Edited after validation</Badge> : null}</div>
        <h3 className="mt-3 text-xl font-bold text-gray-900">{labelText(stage.name)}</h3>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-xs uppercase text-gray-400">Day offset</dt><dd className="font-semibold text-gray-900">D+{stage.day_offset ?? 0}</dd></div>
          <div><dt className="text-xs uppercase text-gray-400">Duration</dt><dd className="font-semibold text-gray-900">{stage.duration_days || 0} days</dd></div>
          <div><dt className="text-xs uppercase text-gray-400">Recommendations</dt><dd className="font-semibold text-gray-900">{recs.length}</dd></div>
          <div><dt className="text-xs uppercase text-gray-400">Mode</dt><dd className="font-semibold text-gray-900">{draftEditable ? "Editable draft" : "Read only"}</dd></div>
        </dl>
        <StageDesignHintsPanel hints={hints} />
        {draftEditable ? (
          <div className="mt-4 rounded border border-green-100 bg-white p-3">
            <p className="text-xs font-semibold uppercase text-gray-400">Quick edit</p>
            <div className="mt-2 grid gap-2 md:grid-cols-[1fr_90px_auto]">
              <input value={stageNameDraft} onChange={(event) => setStageNameDraft(event.target.value)} className="rounded border px-2 py-1 text-xs text-gray-900" aria-label="Stage display name" />
              <input type="number" min={0} value={durationDraft} onChange={(event) => setDurationDraft(event.target.value)} className="rounded border px-2 py-1 text-xs text-gray-900" aria-label="Stage duration days" />
              <button
                type="button"
                disabled={Boolean(busyTarget) || !stageNameDraft.trim() || durationDraft === ""}
                onClick={() => onUpdateDraftStage(stage.code, { stage_name: { en: stageNameDraft.trim() }, duration_days: Number(durationDraft) })}
                className="rounded bg-green-700 px-3 py-1 text-xs font-medium text-white hover:bg-green-800 disabled:cursor-wait disabled:opacity-60"
              >
                Save stage
              </button>
            </div>
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={onEditStage} className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-800">Open full editor</button>
          {draftEditable ? (
            <button
              type="button"
              disabled={Boolean(busyTarget)}
              onClick={() => setShowInlineRecommendationForm((current) => !current)}
              className={`rounded border px-3 py-1.5 text-xs font-medium disabled:cursor-wait disabled:opacity-60 ${showInlineRecommendationForm ? "border-green-500 bg-green-50 text-green-800" : "border-green-200 text-green-700 hover:bg-green-50"}`}
            >
              Add on canvas
            </button>
          ) : null}
          <button type="button" onClick={onAddRecommendation} className="rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50">Open full add form</button>
          {draftEditable ? (
            <>
              <button type="button" disabled={Boolean(busyTarget)} onClick={onCreateStageAfter} className={`rounded border px-3 py-1.5 text-xs font-medium disabled:cursor-wait disabled:opacity-60 ${activeStageAction === "CREATE" ? "border-blue-500 bg-blue-50 text-blue-800" : "border-blue-200 text-blue-700 hover:bg-blue-50"}`}>Add stage after</button>
              <button type="button" disabled={Boolean(busyTarget)} onClick={onDuplicateStage} className={`rounded border px-3 py-1.5 text-xs font-medium disabled:cursor-wait disabled:opacity-60 ${activeStageAction === "DUPLICATE" ? "border-purple-500 bg-purple-50 text-purple-800" : "border-purple-200 text-purple-700 hover:bg-purple-50"}`}>Duplicate stage</button>
              <button type="button" disabled={Boolean(busyTarget) || !canMoveEarlier} onClick={onMoveEarlier} className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50">Move earlier</button>
              <button type="button" disabled={Boolean(busyTarget) || !canMoveLater} onClick={onMoveLater} className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50">Move later</button>
              <button type="button" disabled={Boolean(busyTarget) || !canDeleteStage} onClick={onDeleteStage} className="rounded border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50">Delete stage</button>
            </>
          ) : null}
        </div><p className="mt-3 text-xs text-gray-500">Double-click any stage card or use these shortcuts to jump to the detailed editor below.</p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between"><h3 className="font-semibold text-gray-900">Recommendations in this stage</h3><span className="text-xs text-gray-400">{recs.length} items</span></div>
        {draftEditable && showInlineRecommendationForm ? (
          <QuickRecommendationCreateForm
            stageCode={stage.code}
            cropCode={cropCode}
            projectId={projectId}
            busy={Boolean(busyTarget)}
            onCancel={() => setShowInlineRecommendationForm(false)}
            onCreate={(payload) => {
              onCreateDraftRecommendation(stage.code, payload);
              setShowInlineRecommendationForm(false);
            }}
          />
        ) : null}
        {recs.length === 0 ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">No recommendations configured for this stage.</p> : null}
        <div className="grid gap-3 md:grid-cols-2">
          {recs.map((rec, index) => (
            <RecommendationCanvasCard
              key={`${stage.code}-${rec.input_code || rec.input_name}-${index}`}
              stageCode={stage.code}
              recommendation={rec}
              index={index}
              draftEditable={draftEditable}
              dirty={Boolean(recommendationId(rec) && dirtyTargets.recommendationIds.has(recommendationId(rec) || ""))}
              busy={busyTarget === `DRAFT_REC_REORDER:${stage.code}`}
              dragging={draggedRecommendationIndex === index}
              canMoveEarlier={draftEditable && index > 0 && Boolean(recommendationId(rec))}
              canMoveLater={draftEditable && index < recs.length - 1 && Boolean(recommendationId(rec))}
              onDragStart={() => onRecommendationDragStart(index)}
              onDragEnd={onRecommendationDragEnd}
              onDrop={() => onRecommendationDrop(index)}
              onMoveEarlier={() => onMoveRecommendation(index, -1)}
              onMoveLater={() => onMoveRecommendation(index, 1)}
              onUpdateDraftRecommendation={onUpdateDraftRecommendation}
              onDeleteDraftRecommendation={onDeleteDraftRecommendation}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function StageDesignHintsPanel({ hints }: { hints: StageDesignHint[] }) {
  if (hints.length === 0) {
    return <p className="mt-4 rounded border border-green-100 bg-green-50 p-2 text-xs font-medium text-green-700">No obvious design hints for this stage.</p>;
  }
  return (
    <div className="mt-4 space-y-2">
      <p className="text-xs font-semibold uppercase text-gray-400">Design hints</p>
      {hints.slice(0, 5).map((hint, index) => (
        <p key={`${hint.level}-${index}`} className={`rounded border px-2 py-1 text-xs ${hintClasses(hint.level)}`}>
          {hint.level}: {hint.message}
        </p>
      ))}
      {hints.length > 5 ? <p className="text-xs text-gray-400">+{hints.length - 5} more hints. Run publish validation for the full report.</p> : null}
    </div>
  );
}

function StageActionPanel({
  mode,
  stage,
  busy,
  onCancel,
  onSubmit,
}: {
  mode: StageActionMode;
  stage: WorkflowStage;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (payload: WorkflowDraftStageCreateRequest | WorkflowDraftStageDuplicateRequest) => void;
}) {
  const isDuplicate = mode === "DUPLICATE";
  const stageName = labelText(stage.name) || stage.code;
  const defaultCode = normalizeStageCode(`${stage.code}_${isDuplicate ? "COPY" : "NEXT"}`);
  const [stageCode, setStageCode] = useState(defaultCode);
  const [name, setName] = useState(isDuplicate ? `${stageName} Copy` : "New stage");
  const [durationDays, setDurationDays] = useState(String(Math.max(1, stage.duration_days || 1)));
  const [phase, setPhase] = useState(stage.phase || "");
  const [stageType, setStageType] = useState(stage.stage_type || "");
  const normalizedCode = normalizeStageCode(stageCode);
  const duration = Number.parseInt(durationDays, 10);
  const canSubmit = Boolean(normalizedCode && name.trim()) && (isDuplicate || (Number.isFinite(duration) && duration >= 0));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!canSubmit || busy) return;
        if (isDuplicate) {
          onSubmit({
            after_stage_code: stage.code,
            stage_code: normalizedCode,
            stage_name: { en: name.trim() },
          });
        } else {
          onSubmit({
            after_stage_code: stage.code,
            stage_code: normalizedCode,
            stage_name: { en: name.trim() },
            duration_days: duration,
            phase: phase.trim() || undefined,
            stage_type: stageType.trim() || undefined,
          });
        }
      }}
      className={`rounded-lg border p-4 shadow-sm ${isDuplicate ? "border-purple-200 bg-purple-50/60" : "border-blue-200 bg-blue-50/60"}`}
    >
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">{isDuplicate ? "Duplicate stage" : "Add stage after selected"}</h3>
          <p className="mt-1 text-sm text-gray-600">
            {isDuplicate ? "Copies the selected stage and its recommendations into this draft." : `Creates a new stage immediately after ${stage.code}.`}
          </p>
        </div>
        <Badge>After {stage.code}</Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        <label className="text-sm lg:col-span-1">
          <span className="text-xs font-medium uppercase text-gray-500">Stage code</span>
          <input value={stageCode} onChange={(event) => setStageCode(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 font-mono text-sm" placeholder="CUSTOM_STAGE" />
          {stageCode !== normalizedCode ? <span className="mt-1 block text-[11px] text-gray-500">Will save as {normalizedCode || "?"}</span> : null}
        </label>
        <label className="text-sm lg:col-span-2">
          <span className="text-xs font-medium uppercase text-gray-500">Display name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm" placeholder="Stage name" />
        </label>
        {!isDuplicate ? (
          <>
            <label className="text-sm">
              <span className="text-xs font-medium uppercase text-gray-500">Duration</span>
              <input type="number" min={0} value={durationDays} onChange={(event) => setDurationDays(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm" />
            </label>
            <label className="text-sm">
              <span className="text-xs font-medium uppercase text-gray-500">Stage type</span>
              <input value={stageType} onChange={(event) => setStageType(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm" placeholder="CUSTOM" />
            </label>
            <label className="text-sm lg:col-span-2">
              <span className="text-xs font-medium uppercase text-gray-500">Phase</span>
              <input value={phase} onChange={(event) => setPhase(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 text-sm" placeholder="VEGETATIVE" />
            </label>
          </>
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="submit" disabled={!canSubmit || busy} className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-wait disabled:opacity-60">
          {busy ? "Saving..." : isDuplicate ? "Duplicate stage" : "Create stage"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel} className="rounded border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-white disabled:cursor-wait disabled:opacity-60">Cancel</button>
        {!canSubmit ? <span className="text-xs text-red-600">Stage code and name are required; duration must be 0 or more.</span> : null}
      </div>
    </form>
  );
}


function QuickRecommendationCreateForm({
  stageCode,
  cropCode,
  projectId,
  busy,
  onCreate,
  onCancel,
}: {
  stageCode: string;
  cropCode: string;
  projectId?: string;
  busy: boolean;
  onCreate: (data: WorkflowDraftRecommendationRequest) => void;
  onCancel: () => void;
}) {
  const [dayOffset, setDayOffset] = useState("0");
  const [activityType, setActivityType] = useState("LABOR");
  const [inputSource, setInputSource] = useState<"CATALOG" | "CUSTOM">("CATALOG");
  const [selectedCatalogInput, setSelectedCatalogInput] = useState<AgriInputDto | null>(null);
  const [inputSearch, setInputSearch] = useState("labour");
  const [inputCategory, setInputCategory] = useState("");
  const [inputResults, setInputResults] = useState<AgriInputDto[]>([]);
  const [inputLoading, setInputLoading] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [inputName, setInputName] = useState("Custom labour activity");
  const [quantity, setQuantity] = useState("1 labour-day/acre");
  const [cost, setCost] = useState("");
  const [isCritical, setIsCritical] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setInputLoading(true);
    setInputError(null);
    inputCatalogApi
      .inputs({
        cropCode,
        projectId,
        category: inputCategory || undefined,
        q: inputSearch.trim() || undefined,
      })
      .then((response) => {
        if (!cancelled) setInputResults(response.inputs.slice(0, 8));
      })
      .catch((e) => {
        if (!cancelled) setInputError(e instanceof Error ? e.message : "Failed to search inputs");
      })
      .finally(() => {
        if (!cancelled) setInputLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cropCode, projectId, inputCategory, inputSearch]);

  const selectCatalogInput = (input: AgriInputDto) => {
    setInputSource("CATALOG");
    setSelectedCatalogInput(input);
    setInputName(input.canonical_name);
    setActivityType(activityTypeFromCategory(input.category_code));
    if (!quantity.trim() && input.unit) {
      setQuantity(`1 ${input.unit}/acre`);
    }
  };
  const switchToCustom = () => {
    setInputSource("CUSTOM");
    setSelectedCatalogInput(null);
    if (!inputName.trim()) setInputName("Custom labour activity");
  };
  const day = Number(dayOffset);
  const costValue = cost.trim() ? Number(cost) : null;
  const canSubmit = !busy
    && dayOffset !== ""
    && Number.isFinite(day)
    && inputName.trim().length > 0
    && activityType.trim().length > 0
    && (!cost.trim() || Number.isFinite(Number(cost)))
    && (inputSource === "CUSTOM" || Boolean(selectedCatalogInput));

  return (
    <div className="mb-4 rounded-lg border border-green-200 bg-green-50/50 p-3">
      <div className="flex flex-col gap-1 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900">Add draft recommendation on canvas</p>
          <p className="text-xs text-gray-500">Select an eligible catalog input or enter a custom local input for {stageCode}.</p>
        </div>
        <Badge>{inputSource}</Badge>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={() => setInputSource("CATALOG")} className={`rounded px-3 py-1.5 text-xs font-medium ${inputSource === "CATALOG" ? "bg-green-700 text-white" : "border bg-white text-gray-700"}`}>Catalog input</button>
        <button type="button" onClick={switchToCustom} className={`rounded px-3 py-1.5 text-xs font-medium ${inputSource === "CUSTOM" ? "bg-amber-600 text-white" : "border bg-white text-gray-700"}`}>Custom / unlisted</button>
      </div>

      {inputSource === "CATALOG" ? (
        <div className="mt-3 rounded-lg bg-white p-3">
          <div className="grid gap-2 md:grid-cols-[150px_1fr]">
            <label className="text-xs font-medium text-gray-500">
              Category
              <select value={inputCategory} onChange={(event) => setInputCategory(event.target.value)} className="mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900">
                <option value="">All categories</option>
                <option value="SEED">Seed</option>
                <option value="FERTILIZER">Fertilizer</option>
                <option value="ORGANIC_MANURE">Organic manure</option>
                <option value="FUNGICIDE">Fungicide</option>
                <option value="HERBICIDE">Herbicide</option>
                <option value="PESTICIDE">Pesticide</option>
                <option value="LABOR">Labor</option>
                <option value="MACHINERY">Machinery</option>
                <option value="IRRIGATION">Irrigation</option>
              </select>
            </label>
            <label className="text-xs font-medium text-gray-500">
              Search catalog
              <input value={inputSearch} onChange={(event) => setInputSearch(event.target.value)} placeholder="Search seed, fertilizer, labour, pesticide..." className="mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900" />
            </label>
          </div>
          <div className="mt-3 max-h-40 overflow-auto rounded border bg-white">
            {inputLoading ? <p className="p-3 text-xs text-gray-500">Searching input catalog...</p> : null}
            {inputError ? <p className="p-3 text-xs text-red-600">{inputError}</p> : null}
            {!inputLoading && !inputError && inputResults.length === 0 ? <p className="p-3 text-xs text-gray-500">No eligible catalog matches. Switch to custom if needed.</p> : null}
            {inputResults.map((input) => (
              <button
                key={input.id}
                type="button"
                onClick={() => selectCatalogInput(input)}
                className={`flex w-full items-center justify-between gap-3 border-b px-3 py-2 text-left text-xs hover:bg-green-50 last:border-b-0 ${selectedCatalogInput?.id === input.id ? "bg-green-50" : ""}`}
              >
                <span>
                  <span className="font-semibold text-gray-900">{input.canonical_name}</span>
                  <span className="ml-2 font-mono text-gray-400">{input.code}</span>
                  <span className="ml-2 text-gray-400">{input.category_name || input.category_code || "Uncategorized"}</span>
                  <span className="mt-1 block text-gray-400">{[input.composition, input.unit, input.applicable_crops.join(", ")].filter(Boolean).join(" / ")}</span>
                </span>
                <span className="rounded border border-green-200 px-2 py-0.5 font-medium text-green-700">{selectedCatalogInput?.id === input.id ? "Selected" : "Use"}</span>
              </button>
            ))}
          </div>
          {selectedCatalogInput ? (
            <p className="mt-2 rounded border border-green-200 bg-green-50 p-2 text-xs text-green-800">Selected: {selectedCatalogInput.canonical_name} / {selectedCatalogInput.composition || "No composition"} / Unit {selectedCatalogInput.unit || "n/a"}</p>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 rounded bg-amber-50 p-2 text-xs text-amber-700">Custom inputs are accepted for local practices; backend will assign a stable CUSTOM_* code for Android and audit.</p>
      )}

      <div className="mt-3 grid gap-2 md:grid-cols-[80px_120px_1fr]">
        <label className="text-xs font-medium text-gray-500">
          Day
          <input type="number" value={dayOffset} onChange={(event) => setDayOffset(event.target.value)} className="mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900" />
        </label>
        <label className="text-xs font-medium text-gray-500">
          Activity
          <input value={activityType} onChange={(event) => setActivityType(event.target.value)} className="mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900" />
        </label>
        <label className="text-xs font-medium text-gray-500">
          Recommendation / input name
          <input value={inputName} onChange={(event) => setInputName(event.target.value)} readOnly={inputSource === "CATALOG"} className={`mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900 ${inputSource === "CATALOG" ? "bg-gray-50" : ""}`} />
        </label>
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-[1fr_120px_auto]">
        <label className="text-xs font-medium text-gray-500">
          Quantity
          <input value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900" placeholder="e.g. 1 labour-day/acre" />
        </label>
        <label className="text-xs font-medium text-gray-500">
          Cost/acre
          <input type="number" value={cost} onChange={(event) => setCost(event.target.value)} className="mt-1 w-full rounded border px-2 py-1 text-xs text-gray-900" />
        </label>
        <label className="flex items-center gap-2 self-end pb-1 text-xs font-medium text-gray-600">
          <input type="checkbox" checked={isCritical} onChange={(event) => setIsCritical(event.target.checked)} />
          Critical
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => onCreate({
            day_offset: day,
            activity_type: activityType.trim().toUpperCase(),
            input_source: inputSource,
            input_code: inputSource === "CATALOG" ? selectedCatalogInput?.code || null : null,
            input_name: inputName.trim(),
            typical_quantity: quantity.trim() || null,
            typical_cost_per_acre: costValue,
            is_critical: isCritical,
            description: { en: `${inputSource === "CATALOG" ? "Catalog" : "Custom"} ${activityType.trim().toLowerCase()} recommendation for ${stageCode}` },
          })}
          className="rounded bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-800 disabled:cursor-wait disabled:opacity-60"
        >
          {busy ? "Saving..." : "Add recommendation"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel} className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-white disabled:cursor-wait disabled:opacity-60">Cancel</button>
        {!canSubmit ? <span className="self-center text-xs text-red-600">Select a catalog item or enter a custom name; day/activity/cost must be valid.</span> : null}
      </div>
    </div>
  );
}

function RecommendationCanvasCard({
  stageCode,
  recommendation,
  index,
  draftEditable,
  dirty,
  busy,
  dragging,
  canMoveEarlier,
  canMoveLater,
  onDragStart,
  onDragEnd,
  onDrop,
  onMoveEarlier,
  onMoveLater,
  onUpdateDraftRecommendation,
  onDeleteDraftRecommendation,
}: {
  stageCode: string;
  recommendation: WorkflowRecommendation;
  index: number;
  draftEditable: boolean;
  dirty: boolean;
  busy: boolean;
  dragging: boolean;
  canMoveEarlier: boolean;
  canMoveLater: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDrop: () => void;
  onMoveEarlier: () => void;
  onMoveLater: () => void;
  onUpdateDraftRecommendation: (recommendationId: string, data: WorkflowDraftRecommendationRequest) => void;
  onDeleteDraftRecommendation: (recommendationId: string) => void;
}) {
  const recId = recommendationId(recommendation);
  const [inputNameDraft, setInputNameDraft] = useState(recommendation.input_name || "");
  const [dayOffsetDraft, setDayOffsetDraft] = useState(String(recommendation.day_offset ?? 0));
  const [quantityDraft, setQuantityDraft] = useState(recommendation.typical_quantity || "");

  useEffect(() => {
    setInputNameDraft(recommendation.input_name || "");
    setDayOffsetDraft(String(recommendation.day_offset ?? 0));
    setQuantityDraft(recommendation.typical_quantity || "");
  }, [recommendation.input_name, recommendation.day_offset, recommendation.typical_quantity]);

  return (
    <div
      id={`canvas-recommendation-${recommendationAnchorId(stageCode, recommendation, index)}`}
      draggable={draftEditable && !busy && Boolean(recommendationId(recommendation))}
      onDragStart={(event) => {
        if (!draftEditable || busy || !recommendationId(recommendation)) return;
        onDragStart();
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", recommendationId(recommendation) || "");
      }}
      onDragOver={(event) => {
        if (!draftEditable || busy) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDrop();
      }}
      onDragEnd={onDragEnd}
      title={draftEditable ? "Drag to reorder this recommendation" : undefined}
      className={`rounded-lg border p-3 text-sm transition ${dirty ? "border-orange-200 bg-orange-50" : "border-gray-100 bg-gray-50"} ${dragging ? "opacity-50 ring-2 ring-green-200" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div><p className="text-xs font-medium uppercase text-gray-400">Recommendation {index + 1}</p><h4 className="mt-1 font-semibold text-gray-900">{recommendation.input_name || recommendation.input_code || recommendation.activity_type}</h4></div>
        <div className="flex flex-col items-end gap-2">
          {dirty ? <span className="rounded bg-orange-100 px-2 py-1 text-[10px] font-semibold text-orange-700">Edited</span> : null}
          {recommendation.is_critical ? <span className="rounded bg-red-100 px-2 py-1 text-[10px] font-semibold text-red-700">Critical</span> : null}
          {draftEditable ? (
            <div className="flex gap-1">
              <button type="button" disabled={busy || !canMoveEarlier} onClick={onMoveEarlier} className="rounded border border-gray-200 px-2 py-1 text-[10px] font-medium text-gray-600 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40">Earlier</button>
              <button type="button" disabled={busy || !canMoveLater} onClick={onMoveLater} className="rounded border border-gray-200 px-2 py-1 text-[10px] font-medium text-gray-600 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40">Later</button>
            </div>
          ) : null}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs"><Badge>{recommendation.activity_type}</Badge><Badge>D+{recommendation.day_offset}</Badge>{recommendation.input_code ? <Badge>{recommendation.input_code}</Badge> : null}</div>
      {recommendation.typical_quantity ? <p className="mt-3 text-xs text-gray-600">Qty: {recommendation.typical_quantity}</p> : null}
      {recommendation.typical_cost_per_acre ? <p className="mt-1 text-xs text-gray-600">Cost/acre: {recommendation.typical_cost_per_acre}</p> : null}
      {recommendation.allowed_product_codes?.length ? <p className="mt-2 font-mono text-[11px] text-gray-500">Products: {recommendation.allowed_product_codes.slice(0, 3).join(", ")}{recommendation.allowed_product_codes.length > 3 ? "..." : ""}</p> : null}
      {draftEditable ? (
        <div className="mt-3 rounded border border-gray-200 bg-white p-2">
          <p className="text-[10px] font-semibold uppercase text-gray-400">Quick edit recommendation</p>
          <div className="mt-2 grid gap-2 md:grid-cols-[1fr_70px]">
            <input value={inputNameDraft} onChange={(event) => setInputNameDraft(event.target.value)} className="rounded border px-2 py-1 text-xs text-gray-900" aria-label="Recommendation name" />
            <input type="number" value={dayOffsetDraft} onChange={(event) => setDayOffsetDraft(event.target.value)} className="rounded border px-2 py-1 text-xs text-gray-900" aria-label="Recommendation day offset" />
          </div>
          <input value={quantityDraft} onChange={(event) => setQuantityDraft(event.target.value)} className="mt-2 w-full rounded border px-2 py-1 text-xs text-gray-900" aria-label="Recommendation quantity" placeholder="Typical quantity" />
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !recId || !inputNameDraft.trim() || dayOffsetDraft === ""}
              onClick={() => recId && onUpdateDraftRecommendation(recId, { input_name: inputNameDraft.trim(), day_offset: Number(dayOffsetDraft), typical_quantity: quantityDraft.trim() || null })}
              className="rounded border border-green-200 px-2 py-1 text-[10px] font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-50"
            >
              Save
            </button>
            <button
              type="button"
              disabled={busy || !recId}
              onClick={() => recId && window.confirm(`Delete recommendation ${recommendation.input_name}?`) && onDeleteDraftRecommendation(recId)}
              className="rounded border border-red-200 px-2 py-1 text-[10px] font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-gray-100 px-3 py-1 font-medium text-gray-700">{children}</span>;
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "warn" | "ok" }) {
  const toneClass = tone === "warn" ? "bg-yellow-50 text-yellow-700" : tone === "ok" ? "bg-green-50 text-green-700" : "bg-white text-gray-900";
  return (
    <div className={`rounded-lg p-4 shadow ${toneClass}`}>
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}


function PublishOutcomeCard({ outcome }: { outcome: PublishOutcome }) {
  const impact = outcome.impact;
  const published = outcome.published;
  const archivedCount = impact?.counts.published_versions_impacted ?? 0;
  const pinnedCycles = impact?.counts.pinned_cycles_impacted ?? 0;
  const activePinnedCycles = impact?.counts.active_pinned_cycles_impacted ?? 0;
  return (
    <div className="mb-6 rounded-lg border border-green-200 bg-green-50 p-5 text-sm text-green-900 shadow-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-base font-semibold">Workflow published successfully</p>
          <p className="mt-1">
            {published.workflow_template_code} version {published.version} is now the Android-facing catalog version for new crop cycles.
          </p>
        </div>
        <Badge>{published.status}</Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <ReadinessItem title="Published version" detail={`${published.version} / ${published.workflow_template_version_id}`} status="ok" />
        <ReadinessItem title="Previous versions" detail={`${archivedCount} published version(s) archived/replaced.`} status={archivedCount ? "warn" : "ok"} />
        <ReadinessItem title="Pinned cycles" detail={`${pinnedCycles} pinned, ${activePinnedCycles} active pinned remain on stored versions.`} status={activePinnedCycles ? "warn" : "ok"} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <Link href={`/workflows/preview/${published.workflow_template_version_id}`} className="rounded border border-green-300 bg-white/70 px-3 py-1.5 font-semibold text-green-800 hover:bg-white">Open published preview</Link>
        <Link href="/workflows" className="rounded border border-green-300 bg-white/70 px-3 py-1.5 font-semibold text-green-800 hover:bg-white">Open workflow catalog</Link>
        <button type="button" onClick={() => document.getElementById("visual-workflow-builder")?.scrollIntoView({ behavior: "smooth", block: "start" })} className="rounded border border-green-300 bg-white/70 px-3 py-1.5 font-semibold text-green-800 hover:bg-white">Review rendered workflow</button>
      </div>
      <p className="mt-3 text-xs text-green-800/80">Existing crop cycles pinned to older workflow versions remain renderable and read-only on their stored version.</p>
    </div>
  );
}

function PublishConfirmationModal({
  preview,
  stages,
  validation,
  impact,
  publishing,
  confirmed,
  onConfirmedChange,
  onCancel,
  onPublish,
}: {
  preview: WorkflowPreviewResponse;
  stages: WorkflowStage[];
  validation: WorkflowDraftValidationResponse | null;
  impact: WorkflowPublishImpactResponse | null;
  publishing: boolean;
  confirmed: boolean;
  onConfirmedChange: (value: boolean) => void;
  onCancel: () => void;
  onPublish: () => void;
}) {
  const recommendations = stages.flatMap((stage) => stage.recommended_activities || []);
  const activePinned = impact?.counts.active_pinned_cycles_impacted ?? 0;
  const pinned = impact?.counts.pinned_cycles_impacted ?? 0;
  const previousVersions = impact?.counts.published_versions_impacted ?? 0;
  const validationStatus = !validation ? "Missing/stale validation - run validation first" : validation.can_publish ? "Validation passed" : `${validation.counts.errors} validation error(s)`;
  const canConfirm = confirmed && !publishing && Boolean(validation?.can_publish);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5 shadow-2xl">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Confirm workflow publish</h2>
            <p className="mt-1 text-sm text-gray-500">This publishes the draft to the Android-facing workflow catalog for new crop cycles.</p>
          </div>
          <Badge>{preview.workflow_template_code}</Badge>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <ReadinessItem title="Draft version" detail={`${preview.version} / ${preview.workflow_template_version_id}`} status="pending" />
          <ReadinessItem title="Validation" detail={validationStatus} status={!validation ? "pending" : validation.can_publish ? "ok" : "error"} />
          <ReadinessItem title="Rendered content" detail={`${stages.length} stages, ${recommendations.length} recommendations.`} status="ok" />
          <ReadinessItem title="Previous published versions" detail={`${previousVersions} version(s) will be archived/replaced for Android catalog selection.`} status={previousVersions ? "warn" : "ok"} />
          <ReadinessItem title="Pinned crop cycles" detail={`${pinned} total pinned cycle(s), ${activePinned} active pinned cycle(s).`} status={activePinned ? "warn" : "ok"} />
          <ReadinessItem title="Android effect" detail="New crop cycles will use the newly published version; existing pinned cycles remain on their stored version." status="warn" />
        </div>

        {!validation ? (
          <div className="mt-4 rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
            Run validation before confirming publish. The final publish call will validate again, but this confirmation requires a visible passing validation result.
          </div>
        ) : null}

        {impact?.blocking_reasons?.length ? (
          <div className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            <p className="font-semibold">Publish impact blockers</p>
            <ul className="mt-2 list-disc pl-5">
              {impact.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          </div>
        ) : null}

        <label className="mt-5 flex items-start gap-3 rounded border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => onConfirmedChange(event.target.checked)}
            className="mt-1"
          />
          <span>I understand this publishes the currently validated draft workflow to the Android catalog for future crop-cycle creation.</span>
        </label>

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button type="button" disabled={publishing} onClick={onCancel} className="rounded border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60">Cancel</button>
          <button type="button" disabled={!canConfirm} onClick={onPublish} className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60">
            {publishing ? "Publishing..." : "Confirm publish"}
          </button>
        </div>
      </div>
    </div>
  );
}

function DraftFreshnessCard({
  freshness,
  validation,
  postValidationAudit,
  auditLoading,
  validating,
  onValidate,
}: {
  freshness: WorkflowPreviewResponse["draft_freshness"] | null;
  validation: WorkflowDraftValidationResponse | null;
  postValidationAudit: WorkflowAuditResponse | null;
  auditLoading: boolean;
  validating: boolean;
  onValidate: () => void;
}) {
  const hasValidation = Boolean(freshness?.last_validated_at || validation);
  const current = Boolean(freshness?.validation_current && validation?.can_publish);
  const editsSinceValidation = postValidationAudit?.events || [];
  const tone = current ? "border-green-200 bg-green-50 text-green-800" : "border-yellow-200 bg-yellow-50 text-yellow-800";
  return (
    <div className={`mb-6 rounded-lg border p-4 text-sm shadow-sm ${tone}`}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-semibold">Draft freshness</p>
          <p className="mt-1">
            {current
              ? "This draft has a current passing validation result."
              : hasValidation
                ? "This draft has changed since its last visible validation, or validation did not pass."
                : "This draft has not been validated yet."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{current ? "Validation current" : "Validation required"}</Badge>
          {hasValidation ? <Badge>{auditLoading ? "Checking edits..." : `${editsSinceValidation.length} edit(s) since validation`}</Badge> : null}
          <button
            type="button"
            disabled={validating}
            onClick={onValidate}
            className="rounded border border-current/30 bg-white/70 px-3 py-1 text-xs font-semibold hover:bg-white disabled:cursor-wait disabled:opacity-60"
          >
            {validating ? "Validating..." : current ? "Revalidate now" : "Validate now"}
          </button>
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-xs md:grid-cols-3">
        <p><span className="font-medium">Draft created:</span> {formatDateTime(freshness?.draft_created_at)}</p>
        <p><span className="font-medium">Last edited:</span> {formatDateTime(freshness?.last_edited_at || freshness?.draft_updated_at)}</p>
        <p><span className="font-medium">Last validated:</span> {formatDateTime(freshness?.last_validated_at)}</p>
      </div>
      {hasValidation ? (
        <details className="mt-3 rounded border border-current/20 bg-white/50 p-3 text-xs">
          <summary className="cursor-pointer font-medium">View edits since last validation</summary>
          {auditLoading ? (
            <p className="mt-2 opacity-80">Loading edit trace...</p>
          ) : editsSinceValidation.length === 0 ? (
            <p className="mt-2 opacity-80">No edit audit events after the last validation.</p>
          ) : (
            <div className="mt-3 max-h-72 space-y-2 overflow-auto">
              {editsSinceValidation.map((event) => (
                <details key={event.id} className="rounded border border-gray-200 bg-white p-2 text-gray-700">
                  <summary className="cursor-pointer list-none">
                    <div className="flex flex-col gap-1 md:flex-row md:items-start md:justify-between">
                      <div>
                        <span className="font-semibold">{event.action}</span>
                        <span className="ml-2 font-mono text-gray-500">{event.target_code || event.target_id || event.target_type}</span>
                        {event.reason ? <p className="mt-1 text-gray-600">{event.reason}</p> : null}
                      </div>
                      <div className="text-gray-500 md:text-right">
                        <p>{formatDateTime(event.created_at)}</p>
                        {event.actor_id ? <p>Actor {event.actor_id}</p> : null}
                      </div>
                    </div>
                  </summary>
                  <pre className="mt-2 max-h-48 overflow-auto rounded bg-gray-950 p-2 text-[11px] text-gray-100">
                    {JSON.stringify({ before: event.before, after: event.after, metadata: event.metadata }, null, 2)}
                  </pre>
                </details>
              ))}
            </div>
          )}
        </details>
      ) : null}
    </div>
  );
}

function PublishReadinessChecklist({
  stages,
  validation,
  freshness,
  validating,
  impact,
  onValidate,
}: {
  stages: WorkflowStage[];
  validation: WorkflowDraftValidationResponse | null;
  freshness: WorkflowPreviewResponse["draft_freshness"] | null;
  validating: boolean;
  impact: WorkflowPublishImpactResponse | null;
  onValidate: () => void;
}) {
  const allRecommendations = stages.flatMap((stage) => stage.recommended_activities || []);
  const criticalCount = allRecommendations.filter((rec) => rec.is_critical).length;
  const catalogCount = allRecommendations.filter((rec) => recommendationSource(rec) === "CATALOG").length;
  const customCount = allRecommendations.filter((rec) => recommendationSource(rec) === "CUSTOM").length;
  const uncodedCount = allRecommendations.filter((rec) => recommendationSource(rec) === "UNCODED").length;
  const stagesWithoutRecommendations = stages.filter((stage) => (stage.recommended_activities || []).length === 0);
  const stageHints = stages.map((stage) => stageDesignHints(stage));
  const stagesWithErrors = stageHints.filter((hints) => hints.some((hint) => hint.level === "ERROR")).length;
  const stagesWithWarnings = stageHints.filter((hints) => hints.some((hint) => hint.level === "WARN")).length;
  const validationErrors = validation?.counts.errors || 0;
  const validationWarnings = validation?.counts.warnings || 0;
  const validationReady = Boolean(validation?.can_publish && freshness?.validation_current !== false);
  const localErrorCount = stagesWithErrors + stagesWithoutRecommendations.length;
  const publishLooksReady = validationReady && Boolean(impact?.can_publish) && localErrorCount === 0;
  const scrollToPanel = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className={`rounded-lg border p-5 shadow ${publishLooksReady ? "border-green-200 bg-green-50" : "border-blue-100 bg-white"}`}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Publish readiness checklist</h2>
          <p className="mt-1 text-sm text-gray-500">Fast admin check before the backend publish gate. Validation remains the source of truth.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{publishLooksReady ? "Looks publish ready" : "Review before publish"}</Badge>
          <Badge>{allRecommendations.length} recommendations</Badge>
          <Badge>{criticalCount} critical</Badge>
        </div>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        <ReadinessItem
          title="Backend validation"
          detail={validation ? `${validationErrors} errors, ${validationWarnings} warnings - last validated ${formatDateTime(freshness?.last_validated_at)}` : "Missing/stale after edits. Run validation before publish."}
          status={!validation || freshness?.validation_current === false ? "pending" : validation.can_publish ? "ok" : "error"}
        />
        <ReadinessItem
          title="Draft freshness"
          detail={`Last edited ${formatDateTime(freshness?.last_edited_at || freshness?.draft_updated_at)}`}
          status={freshness?.validation_current && validation?.can_publish ? "ok" : "pending"}
        />
        <ReadinessItem
          title="Stage recommendation coverage"
          detail={stagesWithoutRecommendations.length ? `${stagesWithoutRecommendations.length} stage(s) have no recommendations.` : "Every stage has at least one recommendation."}
          status={stagesWithoutRecommendations.length ? "warn" : "ok"}
        />
        <ReadinessItem
          title="Local design hints"
          detail={stagesWithErrors || stagesWithWarnings ? `${stagesWithErrors} error stage(s), ${stagesWithWarnings} warning stage(s).` : "No local stage design errors or warnings."}
          status={stagesWithErrors ? "error" : stagesWithWarnings ? "warn" : "ok"}
        />
        <ReadinessItem
          title="Critical recommendations"
          detail={criticalCount ? `${criticalCount} critical recommendation(s) marked.` : "No critical recommendations are marked."}
          status={criticalCount ? "ok" : "warn"}
        />
        <ReadinessItem
          title="Catalog/custom split"
          detail={`${catalogCount} catalog, ${customCount} custom, ${uncodedCount} uncoded.`}
          status={uncodedCount ? "warn" : "ok"}
        />
        <ReadinessItem
          title="Publish impact"
          detail={impact ? `${impact.counts.pinned_cycles_impacted} pinned cycle(s), ${impact.counts.active_pinned_cycles_impacted} active pinned.` : "Publish impact is still loading."}
          status={!impact ? "pending" : impact.can_publish ? "ok" : "error"}
        />
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <button type="button" disabled={validating} onClick={onValidate} className="rounded border border-yellow-200 px-3 py-1.5 font-medium text-yellow-700 hover:bg-yellow-50 disabled:cursor-wait disabled:opacity-60">
          {validating ? "Validating..." : validation ? "Revalidate" : "Run validation"}
        </button>
        <button type="button" onClick={() => scrollToPanel("draft-validation-panel")} className="rounded border border-gray-200 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50">Jump to validation</button>
        <button type="button" onClick={() => scrollToPanel("visual-workflow-builder")} className="rounded border border-green-200 px-3 py-1.5 font-medium text-green-700 hover:bg-green-50">Jump to builder</button>
        <button type="button" onClick={() => scrollToPanel("workflow-timeline")} className="rounded border border-blue-200 px-3 py-1.5 font-medium text-blue-700 hover:bg-blue-50">Jump to timeline</button>
        <button type="button" onClick={() => scrollToPanel("publish-impact-panel")} className="rounded border border-amber-200 px-3 py-1.5 font-medium text-amber-700 hover:bg-amber-50">Jump to impact</button>
      </div>
    </div>
  );
}

function ReadinessItem({
  title,
  detail,
  status,
}: {
  title: string;
  detail: string;
  status: "ok" | "warn" | "error" | "pending";
}) {
  const tone = {
    ok: { label: "OK", className: "border-green-200 bg-green-50 text-green-800" },
    warn: { label: "Review", className: "border-amber-200 bg-amber-50 text-amber-800" },
    error: { label: "Blocker", className: "border-red-200 bg-red-50 text-red-800" },
    pending: { label: "Pending", className: "border-gray-200 bg-gray-50 text-gray-700" },
  }[status];
  return (
    <div className={`rounded border p-3 ${tone.className}`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="rounded bg-white/70 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide">{tone.label}</span>
      </div>
      <p className="mt-2 text-xs opacity-80">{detail}</p>
    </div>
  );
}

function PublishImpactPanel({ impact }: { impact: WorkflowPublishImpactResponse | null }) {
  if (!impact) {
    return (
      <div id="publish-impact-panel" className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="text-lg font-semibold text-gray-900">Publish Impact</h2>
        <p className="mt-1 text-sm text-gray-500">Loading impacted workflow version and pinned-cycle counts...</p>
      </div>
    );
  }

  return (
    <div id="publish-impact-panel" className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-amber-950">Publish Impact</h2>
          <p className="mt-1 text-sm text-amber-800">{impact.safety_message}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{impact.counts.published_versions_impacted} previous versions</Badge>
          <Badge>{impact.counts.pinned_cycles_impacted} pinned cycles</Badge>
          <Badge>{impact.counts.active_pinned_cycles_impacted} active pinned</Badge>
        </div>
      </div>
      {impact.impacted_published_versions.length > 0 ? (
        <div className="mt-3 space-y-2">
          {impact.impacted_published_versions.map((item) => (
            <div key={item.workflow_template_version_id} className="rounded border border-amber-200 bg-white p-3 text-xs text-amber-900">
              <div className="flex flex-wrap gap-2">
                <Badge>Version {item.version}</Badge>
                <Badge>{item.action}</Badge>
                <Badge>{item.pinned_cycle_count} pinned</Badge>
                <Badge>{item.active_pinned_cycle_count} active</Badge>
              </div>
              <p className="mt-2">{item.message}</p>
              <p className="mt-1 font-mono text-amber-700">{item.workflow_template_version_id}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DraftValidationPanel({
  validation,
  validating,
  onValidate,
}: {
  validation: WorkflowDraftValidationResponse | null;
  validating: boolean;
  onValidate: () => void;
}) {
  const errors = validation?.issues_by_level.ERROR || [];
  const warnings = validation?.issues_by_level.WARN || [];
  const info = validation?.issues_by_level.INFO || [];
  return (
    <div id="draft-validation-panel" className="mb-6 rounded-lg bg-white p-5 shadow">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Draft Validation</h2>
          <p className="text-sm text-gray-500">Run before publishing. ERROR items block publish; warnings are advisory.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {validation ? (
            <>
              <Badge>Errors {validation.counts.errors}</Badge>
              <Badge>Warnings {validation.counts.warnings}</Badge>
              <Badge>Info {validation.counts.info}</Badge>
              <Badge>{validation.can_publish ? "Publish ready" : "Publish blocked"}</Badge>
            </>
          ) : null}
          <button
            type="button"
            disabled={validating}
            onClick={onValidate}
            className="rounded border border-yellow-200 px-3 py-1.5 font-medium text-yellow-700 hover:bg-yellow-50 disabled:cursor-wait disabled:opacity-60"
          >
            {validating ? "Validating..." : validation ? "Revalidate" : "Validate now"}
          </button>
        </div>
      </div>

      {!validation ? (
        <p className="rounded bg-yellow-50 p-3 text-sm text-yellow-700">Draft has not been validated, or validation was cleared after the latest edit.</p>
      ) : validation.issues.length === 0 ? (
        <p className="rounded bg-green-50 p-3 text-sm text-green-700">No validation issues. Draft can be published.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-3">
          <ValidationIssueGroup title="Blocking errors" tone="error" issues={errors} />
          <ValidationIssueGroup title="Warnings" tone="warn" issues={warnings} />
          <ValidationIssueGroup title="Info" tone="info" issues={info} />
        </div>
      )}
    </div>
  );
}

function ValidationIssueGroup({
  title,
  tone,
  issues,
}: {
  title: string;
  tone: "error" | "warn" | "info";
  issues: WorkflowPreviewWarning[];
}) {
  const toneClass = tone === "error" ? "border-red-200 bg-red-50" : tone === "warn" ? "border-yellow-200 bg-yellow-50" : "border-blue-200 bg-blue-50";
  return (
    <div className={`rounded border p-3 ${toneClass}`}>
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      {issues.length === 0 ? (
        <p className="mt-2 text-xs text-gray-500">None</p>
      ) : (
        <div className="mt-2 max-h-56 space-y-2 overflow-auto">
          {issues.map((issue, index) => (
            <div key={`${issue.code}-${issue.target || index}`} className="rounded bg-white/70 p-2 text-xs">
              <div className="flex flex-wrap gap-2">
                <span className="font-mono text-gray-500">{issue.code}</span>
                {issue.target ? <span className="font-mono text-gray-400">{issue.target}</span> : null}
              </div>
              <p className="mt-1 text-gray-800">{issue.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WarningsPanel({ warnings, warningCounts }: { warnings: WorkflowPreviewWarning[]; warningCounts: Record<string, number> }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Warnings</h2>
        <div className="flex gap-2 text-xs">
          {Object.entries(warningCounts).map(([level, count]) => <Badge key={level}>{level}: {count}</Badge>)}
        </div>
      </div>
      {warnings.length === 0 ? (
        <p className="rounded bg-green-50 p-3 text-sm text-green-700">No preview warnings.</p>
      ) : (
        <div className="max-h-80 space-y-2 overflow-auto">
          {warnings.map((warning, index) => (
            <div key={`${warning.code}-${index}`} className="rounded border p-3 text-sm">
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${warning.level === "ERROR" ? "bg-red-100 text-red-700" : warning.level === "WARN" ? "bg-yellow-100 text-yellow-700" : "bg-blue-100 text-blue-700"}`}>
                  {warning.level}
                </span>
                <span className="font-mono text-xs text-gray-500">{warning.code}</span>
              </div>
              <p className="mt-2 text-gray-800">{warning.message}</p>
              {warning.target ? <p className="mt-1 font-mono text-xs text-gray-400">{warning.target}</p> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OverridesPanel({
  overrides,
  projectScoped,
  busyTarget,
  onRemoveOverride,
}: {
  overrides: WorkflowPreviewResponse["applied_overrides"];
  projectScoped: boolean;
  busyTarget: string | null;
  onRemoveOverride: (overrideId: string) => void;
}) {
  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Applied Overrides</h2>
      {overrides.length === 0 ? (
        <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">No tenant/project overrides applied.</p>
      ) : (
        <div className="max-h-80 space-y-2 overflow-auto">
          {overrides.map((override) => (
            <div key={override.id} className="rounded border p-3 text-sm">
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge>{override.target_type}</Badge>
                <Badge>{override.operation}</Badge>
                <Badge>Priority {override.priority}</Badge>
              </div>
              <p className="mt-2 font-mono text-xs text-gray-500">{override.target_code}</p>
              {override.reason ? <p className="mt-1 text-gray-600">{override.reason}</p> : null}
              {projectScoped ? (
                <button
                  type="button"
                  disabled={busyTarget === `OVERRIDE:${override.id}`}
                  onClick={() => onRemoveOverride(override.id)}
                  className="mt-3 rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                >
                  {busyTarget === `OVERRIDE:${override.id}` ? "Removing..." : "Remove override"}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return "?";
  return new Date(value).toLocaleString();
}

function OverrideHistoryPanel({
  history,
  busyTarget,
  onRemoveOverride,
}: {
  history: WorkflowOverrideHistoryResponse | null;
  busyTarget: string | null;
  onRemoveOverride: (overrideId: string) => void;
}) {
  return (
    <div className="mb-6 rounded-lg bg-white p-5 shadow">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Override History / Audit</h2>
          <p className="text-sm text-gray-500">Active and removed project overrides for this workflow version.</p>
        </div>
        {history ? (
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge>Total {history.counts.total}</Badge>
            <Badge>Active {history.counts.active}</Badge>
            <Badge>Removed {history.counts.inactive}</Badge>
          </div>
        ) : null}
      </div>

      {!history ? (
        <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">Loading override history...</p>
      ) : history.overrides.length === 0 ? (
        <p className="rounded bg-gray-50 p-3 text-sm text-gray-500">No override history for this project workflow yet.</p>
      ) : (
        <div className="max-h-[520px] space-y-3 overflow-auto">
          {history.overrides.map((override) => (
            <details key={override.id} className={`rounded border p-3 text-sm ${override.is_active ? "border-green-200 bg-green-50/40" : "border-gray-200 bg-gray-50"}`}>
              <summary className="cursor-pointer list-none">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge>{override.is_active ? "ACTIVE" : "REMOVED"}</Badge>
                      <Badge>{override.target_type}</Badge>
                      <Badge>{override.operation}</Badge>
                      <Badge>Priority {override.priority}</Badge>
                    </div>
                    <p className="mt-2 font-mono text-xs text-gray-600">{override.target_code}</p>
                    {override.reason ? <p className="mt-1 text-gray-700">{override.reason}</p> : null}
                  </div>
                  <div className="text-xs text-gray-500 md:text-right">
                    <p>Created: {formatDateTime(override.created_at)}</p>
                    <p>Updated: {formatDateTime(override.updated_at)}</p>
                    {override.is_active ? (
                      <button
                        type="button"
                        disabled={busyTarget === `OVERRIDE:${override.id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          onRemoveOverride(override.id);
                        }}
                        className="mt-2 rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                      >
                        {busyTarget === `OVERRIDE:${override.id}` ? "Removing..." : "Remove"}
                      </button>
                    ) : null}
                  </div>
                </div>
              </summary>
              <pre className="mt-3 max-h-64 overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">
                {JSON.stringify(override.payload || {}, null, 2)}
              </pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function StagePreview({
  stage,
  cropCode,
  projectId,
  projectScoped,
  draftEditable,
  busyTarget,
  onCreateOverride,
  onUpdateDraftStage,
  onCreateDraftRecommendation,
  onUpdateDraftRecommendation,
  onDeleteDraftRecommendation,
}: {
  stage: WorkflowStage;
  cropCode: string;
  projectId?: string;
  projectScoped: boolean;
  draftEditable: boolean;
  busyTarget: string | null;
  onCreateOverride: (
    targetType: WorkflowTargetType,
    targetCode: string,
    operation: WorkflowOverrideOperation,
    overridePayload: Record<string, unknown>,
    reason: string,
  ) => void;
  onUpdateDraftStage: (stageCode: string, data: WorkflowDraftStageUpdateRequest) => void;
  onCreateDraftRecommendation: (stageCode: string, data: WorkflowDraftRecommendationRequest) => void;
  onUpdateDraftRecommendation: (recommendationId: string, data: WorkflowDraftRecommendationRequest) => void;
  onDeleteDraftRecommendation: (recommendationId: string) => void;
}) {
  const recs = stage.recommended_activities || [];
  const [stageName, setStageName] = useState(labelText(stage.name));
  const [durationDays, setDurationDays] = useState(String(stage.duration_days));
  const [newRecDayOffset, setNewRecDayOffset] = useState("0");
  const [newRecActivityType, setNewRecActivityType] = useState("LABOR");
  const [newRecInputCode, setNewRecInputCode] = useState("");
  const [newRecInputName, setNewRecInputName] = useState("Custom labour activity");
  const [newRecQuantity, setNewRecQuantity] = useState("1 labour-day/acre");
  const [newRecCost, setNewRecCost] = useState("");
  const [newRecCritical, setNewRecCritical] = useState(false);
  const [inputSource, setInputSource] = useState<"CATALOG" | "CUSTOM">("CUSTOM");
  const [selectedCatalogInput, setSelectedCatalogInput] = useState<AgriInputDto | null>(null);
  const [inputSearch, setInputSearch] = useState("labour");
  const [inputCategory, setInputCategory] = useState("");
  const [inputResults, setInputResults] = useState<AgriInputDto[]>([]);
  const [inputLoading, setInputLoading] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);

  useEffect(() => {
    setStageName(labelText(stage.name));
    setDurationDays(String(stage.duration_days));
  }, [stage.name, stage.duration_days]);

  useEffect(() => {
    if (!projectScoped && !draftEditable) return;
    let cancelled = false;
    setInputLoading(true);
    setInputError(null);
    inputCatalogApi
      .inputs({
        cropCode,
        projectId,
        category: inputCategory || undefined,
        q: inputSearch.trim() || undefined,
      })
      .then((response) => {
        if (!cancelled) setInputResults(response.inputs.slice(0, 8));
      })
      .catch((e) => {
        if (!cancelled) setInputError(e instanceof Error ? e.message : "Failed to search inputs");
      })
      .finally(() => {
        if (!cancelled) setInputLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cropCode, projectId, inputCategory, inputSearch, projectScoped, draftEditable]);

  const stageBusy = busyTarget === `STAGE:${stage.code}`;
  const draftStageBusy = busyTarget === `DRAFT_STAGE:${stage.code}`;

  const selectCatalogInput = (input: AgriInputDto) => {
    setInputSource("CATALOG");
    setSelectedCatalogInput(input);
    setNewRecInputCode(input.code);
    setNewRecInputName(input.canonical_name);
    setNewRecActivityType(activityTypeFromCategory(input.category_code));
    if (!newRecQuantity.trim() && input.unit) {
      setNewRecQuantity(`1 ${input.unit}/acre`);
    }
  };

  const addCustomRecommendation = () => {
    const payload: Record<string, unknown> = {
      day_offset: Number(newRecDayOffset),
      activity_type: newRecActivityType.trim().toUpperCase(),
      input_source: inputSource,
      input_code: newRecInputCode.trim() || null,
      input_name: newRecInputName.trim(),
      typical_quantity: newRecQuantity.trim() || null,
      is_critical: newRecCritical,
      description: { en: `Custom ${newRecActivityType.trim().toLowerCase()} recommendation for ${stage.code}` },
    };
    if (newRecCost.trim()) payload.typical_cost_per_acre = Number(newRecCost);
    if (draftEditable) {
      onCreateDraftRecommendation(stage.code, payload);
    } else {
      onCreateOverride("STAGE", stage.code, "ADD_RECOMMENDATION", payload, `Add recommendation to ${stage.code}`);
    }
  };

  return (
    <details id={`stage-editor-${stage.code}`} open={stage.order === 1}>
      <summary className="cursor-pointer list-none p-5 hover:bg-gray-50">
        <div className="flex items-start justify-between gap-4">
          <div id={`stage-stage-${stage.code}`}>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Stage {stage.order} ? {stage.code}</p>
            <h3 className="mt-1 font-semibold text-gray-900">{labelText(stage.name)}</h3>
            <p className="mt-1 text-sm text-gray-500">{stage.duration_days} days ? {recs.length} recommendations</p>
          </div>
          <div className="flex items-center gap-3">
            {projectScoped ? (
              <button
                type="button"
                disabled={stageBusy}
                onClick={(event) => {
                  event.preventDefault();
                  onCreateOverride("STAGE", stage.code, "HIDE", {}, `Hide stage ${stage.code}`);
                }}
                className="rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
              >
                {stageBusy ? "Saving..." : "Hide stage"}
              </button>
            ) : null}
            <span className="text-sm text-gray-400">?</span>
          </div>
        </div>
      </summary>
      <div className="px-5 pb-5">
        {projectScoped || draftEditable ? (
          <div className={`mb-4 grid gap-3 rounded-lg border border-dashed bg-gray-50 p-3 ${projectScoped ? "md:grid-cols-[1fr_140px_auto_auto]" : "md:grid-cols-[1fr_140px_auto]"}`}>
            <label className="text-xs font-medium text-gray-500">
              Stage label
              <input
                value={stageName}
                onChange={(event) => setStageName(event.target.value)}
                className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
              />
            </label>
            <label className="text-xs font-medium text-gray-500">
              Duration
              <input
                type="number"
                min="0"
                value={durationDays}
                onChange={(event) => setDurationDays(event.target.value)}
                className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
              />
            </label>
            {projectScoped ? (
              <>
                <button
                  type="button"
                  disabled={stageBusy || !stageName.trim()}
                  onClick={() => onCreateOverride("STAGE", stage.code, "RENAME", { name: { en: stageName.trim(), hi: stageName.trim() } }, `Rename stage ${stage.code}`)}
                  className="self-end rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                >
                  Rename stage
                </button>
                <button
                  type="button"
                  disabled={stageBusy || durationDays === ""}
                  onClick={() => onCreateOverride("STAGE", stage.code, "CHANGE_DURATION", { duration_days: Number(durationDays) }, `Change duration for ${stage.code}`)}
                  className="self-end rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                >
                  Save duration
                </button>
              </>
            ) : null}
            {draftEditable ? (
              <button
                type="button"
                disabled={draftStageBusy || !stageName.trim() || durationDays === ""}
                onClick={() => onUpdateDraftStage(stage.code, { stage_name: { en: stageName.trim(), hi: stageName.trim() }, duration_days: Number(durationDays) })}
                className="self-end rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
              >
                {draftStageBusy ? "Saving draft..." : "Save draft stage"}
              </button>
            ) : null}
          </div>
        ) : null}

        {projectScoped || draftEditable ? (
          <details id={`stage-recommendation-${stage.code}`} className="mb-4 rounded-lg border border-dashed bg-white p-3">
            <summary className="cursor-pointer text-sm font-semibold text-gray-800">Add custom recommendation</summary>
            <div className="mt-3 rounded-lg bg-gray-50 p-3">
              <div className="mb-3 flex gap-2">
                <button type="button" onClick={() => setInputSource("CATALOG")} className={`rounded px-3 py-1.5 text-xs font-medium ${inputSource === "CATALOG" ? "bg-green-700 text-white" : "border bg-white text-gray-700"}`}>Catalog input</button>
                <button type="button" onClick={() => { setInputSource("CUSTOM"); setSelectedCatalogInput(null); setNewRecInputCode(""); }} className={`rounded px-3 py-1.5 text-xs font-medium ${inputSource === "CUSTOM" ? "bg-amber-600 text-white" : "border bg-white text-gray-700"}`}>Custom / unlisted input</button>
              </div>
              <div className="grid gap-3 md:grid-cols-[160px_1fr]">
                <label className="text-xs font-medium text-gray-500">
                  Catalog category
                  <select
                    value={inputCategory}
                    onChange={(event) => setInputCategory(event.target.value)}
                    className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                  >
                    <option value="">All categories</option>
                    <option value="SEED">Seed</option>
                    <option value="FERTILIZER">Fertilizer</option>
                    <option value="ORGANIC_MANURE">Organic manure</option>
                    <option value="FUNGICIDE">Fungicide</option>
                    <option value="HERBICIDE">Herbicide</option>
                    <option value="PESTICIDE">Pesticide</option>
                    <option value="LABOR">Labor</option>
                    <option value="MACHINERY">Machinery</option>
                    <option value="IRRIGATION">Irrigation</option>
                  </select>
                </label>
                <label className="text-xs font-medium text-gray-500">
                  Search input catalog
                  <input
                    value={inputSearch}
                    onChange={(event) => setInputSearch(event.target.value)}
                    placeholder="Search seed, fertilizer, labour, pesticide..."
                    className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                  />
                </label>
              </div>
              <div className="mt-3 max-h-44 overflow-auto rounded border bg-white">
                {inputLoading ? <p className="p-3 text-xs text-gray-500">Searching input catalog...</p> : null}
                {inputError ? <p className="p-3 text-xs text-red-600">{inputError}</p> : null}
                {!inputLoading && !inputError && inputResults.length === 0 ? <p className="p-3 text-xs text-gray-500">No catalog matches. Use the manual fields below.</p> : null}
                {inputResults.map((input) => (
                  <button
                    key={input.id}
                    type="button"
                    onClick={() => selectCatalogInput(input)}
                    className="flex w-full items-center justify-between gap-3 border-b px-3 py-2 text-left text-xs hover:bg-green-50 last:border-b-0"
                  >
                    <span>
                      <span className="font-semibold text-gray-900">{input.canonical_name}</span>
                      <span className="ml-2 font-mono text-gray-400">{input.code}</span>
                      <span className="ml-2 text-gray-400">{input.category_name || input.category_code || "Uncategorized"}</span>
                      <span className="mt-1 block text-gray-400">{[input.composition, input.unit, input.applicable_crops.join(", ")].filter(Boolean).join(" / ")}</span>
                    </span>
                    <span className="rounded border border-green-200 px-2 py-0.5 font-medium text-green-700">Use</span>
                  </button>
                ))}
              </div>
              {inputSource === "CATALOG" ? (
                <p className="mt-2 text-xs text-gray-500">Select an eligible catalog item. Crop and project assignment filters are applied automatically.</p>
              ) : (
                <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-700">Enter the local input name below. The backend will generate a stable CUSTOM_* code for Android and audit.</p>
              )}
              {selectedCatalogInput && inputSource === "CATALOG" ? (
                <div className="mt-2 rounded border border-green-200 bg-green-50 p-2 text-xs text-green-800">Selected: {selectedCatalogInput.canonical_name} / {selectedCatalogInput.composition || "No composition"} / Unit {selectedCatalogInput.unit}</div>
              ) : null}
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-[90px_120px_150px_1fr_160px_120px_auto]">
              <label className="text-xs font-medium text-gray-500">
                Day
                <input
                  type="number"
                  value={newRecDayOffset}
                  onChange={(event) => setNewRecDayOffset(event.target.value)}
                  className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                />
              </label>
              <label className="text-xs font-medium text-gray-500">
                Activity
                <input
                  value={newRecActivityType}
                  onChange={(event) => setNewRecActivityType(event.target.value)}
                  className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                />
              </label>
              <label className="text-xs font-medium text-gray-500">
                Input code
                <input
                  value={newRecInputCode}
                  readOnly
                  placeholder={inputSource === "CUSTOM" ? "Generated by backend" : "Select catalog item"}
                  className="mt-1 w-full rounded border bg-gray-50 px-2 py-1 text-sm text-gray-900"
                />
              </label>
              <label className="text-xs font-medium text-gray-500">
                Input name
                <input
                  value={newRecInputName}
                  onChange={(event) => setNewRecInputName(event.target.value)}
                  className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                />
              </label>
              <label className="text-xs font-medium text-gray-500">
                Quantity
                <input
                  value={newRecQuantity}
                  onChange={(event) => setNewRecQuantity(event.target.value)}
                  className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                />
              </label>
              <label className="text-xs font-medium text-gray-500">
                Cost/acre
                <input
                  type="number"
                  value={newRecCost}
                  onChange={(event) => setNewRecCost(event.target.value)}
                  className="mt-1 w-full rounded border px-2 py-1 text-sm text-gray-900"
                />
              </label>
              <div className="flex items-end gap-3">
                <label className="flex items-center gap-1 pb-1 text-xs font-medium text-gray-500">
                  <input
                    type="checkbox"
                    checked={newRecCritical}
                    onChange={(event) => setNewRecCritical(event.target.checked)}
                  />
                  Critical
                </label>
                <button
                  type="button"
                  disabled={(stageBusy || draftStageBusy) || newRecDayOffset === "" || !newRecActivityType.trim() || !newRecInputName.trim() || (inputSource === "CATALOG" && !selectedCatalogInput)}
                  onClick={addCustomRecommendation}
                  className="rounded border border-green-200 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                >
                  Add
                </button>
              </div>
            </div>
          </details>
        ) : null}

        {recs.length === 0 ? <p className="rounded bg-gray-50 p-3 text-sm text-gray-400">No recommendations.</p> : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Day</th>
                  <th className="px-3 py-2 text-left font-medium">Activity</th>
                  <th className="px-3 py-2 text-left font-medium">Input</th>
                  <th className="px-3 py-2 text-left font-medium">Quantity</th>
                  {projectScoped || draftEditable ? <th className="px-3 py-2 text-right font-medium">Editor</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y">
                {recs.map((rec, index) => (
                  <RecommendationPreview
                    key={`${rec.input_name}-${index}`}
                    stageCode={stage.code}
                    index={index}
                    rec={rec}
                    projectScoped={projectScoped}
                    draftEditable={draftEditable}
                    busyTarget={busyTarget}
                    onCreateOverride={onCreateOverride}
                    onUpdateDraftRecommendation={onUpdateDraftRecommendation}
                    onDeleteDraftRecommendation={onDeleteDraftRecommendation}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}

function RecommendationPreview({
  stageCode,
  index,
  rec,
  projectScoped,
  draftEditable,
  busyTarget,
  onCreateOverride,
  onUpdateDraftRecommendation,
  onDeleteDraftRecommendation,
}: {
  stageCode: string;
  index: number;
  rec: WorkflowRecommendation;
  projectScoped: boolean;
  draftEditable: boolean;
  busyTarget: string | null;
  onCreateOverride: (
    targetType: WorkflowTargetType,
    targetCode: string,
    operation: WorkflowOverrideOperation,
    overridePayload: Record<string, unknown>,
    reason: string,
  ) => void;
  onUpdateDraftRecommendation: (recommendationId: string, data: WorkflowDraftRecommendationRequest) => void;
  onDeleteDraftRecommendation: (recommendationId: string) => void;
}) {
  const targetCode = rec.input_code ? `${stageCode}|${rec.input_code}` : `${stageCode}|${rec.activity_type}|${rec.input_name}`;
  const [inputName, setInputName] = useState(rec.input_name || "");
  const [dayOffset, setDayOffset] = useState(String(rec.day_offset ?? 0));
  const [quantity, setQuantity] = useState(rec.typical_quantity || "");
  const recId = recommendationId(rec);

  useEffect(() => {
    setInputName(rec.input_name || "");
    setDayOffset(String(rec.day_offset ?? 0));
    setQuantity(rec.typical_quantity || "");
  }, [rec.input_name, rec.day_offset, rec.typical_quantity]);

  const recBusy = busyTarget === `RECOMMENDATION:${targetCode}`;
  const draftRecBusy = recId ? busyTarget === `DRAFT_REC:${recId}` : false;

  return (
    <tr id={`recommendation-${recommendationAnchorId(stageCode, rec, index)}`}>
      <td className="px-3 py-2 font-mono text-xs">+{rec.day_offset}</td>
      <td className="px-3 py-2"><span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">{rec.activity_type}</span></td>
      <td className="px-3 py-2">
        <p className="font-medium text-gray-900">{rec.input_name}</p>
        <p className="font-mono text-xs text-gray-400">{rec.input_code || "No input_code"}</p>
      </td>
      <td className="px-3 py-2 text-gray-600">{rec.typical_quantity || "?"}</td>
      {projectScoped || draftEditable ? (
        <td className="min-w-[360px] px-3 py-2 text-right">
          <div className="grid gap-2 text-left">
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <input
                value={inputName}
                onChange={(event) => setInputName(event.target.value)}
                className="rounded border px-2 py-1 text-xs text-gray-900"
                aria-label="Recommendation label"
              />
              {projectScoped ? (
                <button
                  type="button"
                  disabled={recBusy || !inputName.trim()}
                  onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "RENAME", { input_name: inputName.trim() }, `Rename recommendation ${targetCode}`)}
                  className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                >
                  Rename
                </button>
              ) : null}
            </div>
            <div className="grid grid-cols-[80px_1fr_auto_auto_auto] gap-2">
              <input
                type="number"
                value={dayOffset}
                onChange={(event) => setDayOffset(event.target.value)}
                className="rounded border px-2 py-1 text-xs text-gray-900"
                aria-label="Day offset"
              />
              <input
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                className="rounded border px-2 py-1 text-xs text-gray-900"
                aria-label="Typical quantity"
              />
              {projectScoped ? (
                <>
                  <button
                    type="button"
                    disabled={recBusy || dayOffset === ""}
                    onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "CHANGE_OFFSET", { day_offset: Number(dayOffset) }, `Change offset for ${targetCode}`)}
                    className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                  >
                    Offset
                  </button>
                  <button
                    type="button"
                    disabled={recBusy || !quantity.trim()}
                    onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "CHANGE_QUANTITY", { typical_quantity: quantity.trim() }, `Change quantity for ${targetCode}`)}
                    className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                  >
                    Quantity
                  </button>
                  <button
                    type="button"
                    disabled={recBusy}
                    onClick={() => onCreateOverride("RECOMMENDATION", targetCode, "HIDE", {}, `Hide recommendation ${targetCode}`)}
                    className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                  >
                    {recBusy ? "Saving..." : "Hide"}
                  </button>
                </>
              ) : null}
              {draftEditable ? (
                <>
                  <button
                    type="button"
                    disabled={!recId || draftRecBusy || !inputName.trim() || dayOffset === ""}
                    onClick={() => recId && onUpdateDraftRecommendation(recId, { input_name: inputName.trim(), day_offset: Number(dayOffset), typical_quantity: quantity.trim() || null })}
                    className="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                  >
                    {draftRecBusy ? "Saving..." : "Save draft"}
                  </button>
                  <button
                    type="button"
                    disabled={!recId || draftRecBusy}
                    onClick={() => recId && onDeleteDraftRecommendation(recId)}
                    className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                  >
                    {draftRecBusy ? "Saving..." : "Delete"}
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </td>
      ) : null}
    </tr>
  );
}
