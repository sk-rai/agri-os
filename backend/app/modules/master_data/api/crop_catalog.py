"""Crop catalog API: taxonomy, propagation, and Android-ready crop metadata."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.master_data.models import (
    Crop,
    CropPropagationOption,
    CropPropagationType,
    CropTaxonomyAssignment,
    CropTaxonomyEdge,
    CropTaxonomyNode,
)

router = APIRouter(prefix="/api/v1/crop-catalog", tags=["crop-catalog"])


class TaxonomyNodeResponse(BaseModel):
    id: UUID
    code: str
    canonical_name: str
    description: Optional[str] = None
    node_type: str
    level: int
    display_order: int
    aliases: Optional[list | dict] = None
    metadata: Optional[dict] = None
    parent_codes: list[str] = []
    child_codes: list[str] = []


class PropagationTypeResponse(BaseModel):
    id: UUID
    code: str
    canonical_name: str
    description: Optional[str] = None
    establishment_type: str
    aliases: Optional[list | dict] = None
    metadata: Optional[dict] = None


class CropCatalogItem(BaseModel):
    id: UUID
    code: str
    canonical_name: str
    scientific_name: Optional[str] = None
    typical_duration_days: Optional[int] = None
    suitable_seasons: Optional[list[str]] = None
    taxonomy: list[dict]
    propagation_options: list[dict]


def _node_payload(node: CropTaxonomyNode, parent_codes: list[str], child_codes: list[str]) -> dict:
    return {
        "id": node.id,
        "code": node.code,
        "canonical_name": node.canonical_name,
        "description": node.description,
        "node_type": node.node_type,
        "level": node.level,
        "display_order": node.display_order,
        "aliases": node.aliases or [],
        "metadata": node.metadata_ or {},
        "parent_codes": parent_codes,
        "child_codes": child_codes,
    }


def _crop_catalog_item(db: Session, crop: Crop) -> dict:
    assignments = (
        db.query(CropTaxonomyAssignment, CropTaxonomyNode)
        .join(CropTaxonomyNode, CropTaxonomyAssignment.taxonomy_node_id == CropTaxonomyNode.id)
        .filter(
            CropTaxonomyAssignment.crop_id == crop.id,
            CropTaxonomyAssignment.is_active == True,
            CropTaxonomyNode.is_active == True,
        )
        .order_by(CropTaxonomyNode.level, CropTaxonomyNode.display_order, CropTaxonomyNode.code)
        .all()
    )
    propagation_options = (
        db.query(CropPropagationOption, CropPropagationType)
        .join(CropPropagationType, CropPropagationOption.propagation_type_id == CropPropagationType.id)
        .filter(
            CropPropagationOption.crop_id == crop.id,
            CropPropagationOption.is_active == True,
            CropPropagationType.is_active == True,
        )
        .order_by(CropPropagationOption.is_default.desc(), CropPropagationType.code)
        .all()
    )

    return {
        "id": crop.id,
        "code": crop.code,
        "canonical_name": crop.canonical_name,
        "scientific_name": crop.scientific_name,
        "typical_duration_days": crop.typical_duration_days,
        "suitable_seasons": crop.suitable_seasons or [],
        "taxonomy": [
            {
                "code": node.code,
                "canonical_name": node.canonical_name,
                "node_type": node.node_type,
                "level": node.level,
                "assignment_type": assignment.assignment_type,
                "is_primary": assignment.is_primary,
            }
            for assignment, node in assignments
        ],
        "propagation_options": [
            {
                "code": propagation_type.code,
                "canonical_name": propagation_type.canonical_name,
                "establishment_type": propagation_type.establishment_type,
                "season_code": option.season_code,
                "is_default": option.is_default,
                "notes": option.notes,
            }
            for option, propagation_type in propagation_options
        ],
    }


@router.get("/taxonomy", response_model=dict)
def list_taxonomy_nodes(db: Session = Depends(get_db)):
    nodes = (
        db.query(CropTaxonomyNode)
        .filter(CropTaxonomyNode.is_active == True)
        .order_by(CropTaxonomyNode.level, CropTaxonomyNode.display_order, CropTaxonomyNode.code)
        .all()
    )
    edges = db.query(CropTaxonomyEdge).filter(CropTaxonomyEdge.is_active == True).all()
    node_by_id = {node.id: node for node in nodes}
    parents: dict[UUID, list[str]] = {node.id: [] for node in nodes}
    children: dict[UUID, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        parent = node_by_id.get(edge.parent_node_id)
        child = node_by_id.get(edge.child_node_id)
        if parent and child:
            parents[child.id].append(parent.code)
            children[parent.id].append(child.code)

    return {
        "schema_version": "crop_taxonomy.v1",
        "nodes": [_node_payload(node, parents.get(node.id, []), children.get(node.id, [])) for node in nodes],
        "edges": [
            {
                "parent_code": node_by_id[edge.parent_node_id].code,
                "child_code": node_by_id[edge.child_node_id].code,
                "relationship_type": edge.relationship_type,
            }
            for edge in edges
            if edge.parent_node_id in node_by_id and edge.child_node_id in node_by_id
        ],
    }


@router.get("/propagation-types", response_model=list[PropagationTypeResponse])
def list_propagation_types(db: Session = Depends(get_db)):
    propagation_types = (
        db.query(CropPropagationType)
        .filter(CropPropagationType.is_active == True)
        .order_by(CropPropagationType.code)
        .all()
    )
    return [
        {
            "id": propagation_type.id,
            "code": propagation_type.code,
            "canonical_name": propagation_type.canonical_name,
            "description": propagation_type.description,
            "establishment_type": propagation_type.establishment_type,
            "aliases": propagation_type.aliases or [],
            "metadata": propagation_type.metadata_ or {},
        }
        for propagation_type in propagation_types
    ]


@router.get("/crops", response_model=dict)
def list_crop_catalog(
    taxonomy_code: Optional[str] = Query(None),
    propagation_type: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Crop).filter(Crop.is_active == True)
    if season:
        query = query.filter(Crop.suitable_seasons.contains([season.upper()]))

    crops = query.order_by(Crop.canonical_name).all()
    items = [_crop_catalog_item(db, crop) for crop in crops]

    if taxonomy_code:
        taxonomy_code = taxonomy_code.upper()
        items = [item for item in items if any(node["code"] == taxonomy_code for node in item["taxonomy"])]
    if propagation_type:
        propagation_type = propagation_type.upper()
        items = [item for item in items if any(option["code"] == propagation_type for option in item["propagation_options"])]

    return {
        "schema_version": "crop_catalog.v1",
        "crops": items,
        "count": len(items),
    }


@router.get("/crops/{crop_code}", response_model=CropCatalogItem)
def get_crop_catalog_item(crop_code: str, db: Session = Depends(get_db)):
    crop = (
        db.query(Crop)
        .filter(Crop.code == crop_code.upper(), Crop.is_active == True)
        .first()
    )
    if not crop:
        from fastapi import HTTPException
        raise HTTPException(404, f"Crop '{crop_code}' not found")
    return _crop_catalog_item(db, crop)

def _suitability_public_rule(rule):
    return {
        "rule_id": str(rule.id),
        "crop_code": rule.crop_code,
        "season_code": rule.season_code,
        "region_code": rule.region_code,
        "geography_scope": rule.geography_scope,
        "suitability_status": rule.suitability_status,
        "confidence": rule.confidence,
        "irrigation_required": rule.irrigation_required,
        "warning_rules": rule.warning_rules or [],
        "source_references": rule.source_references or [],
        "review_status": rule.review_status,
    }


def _suitability_public_override(override):
    return {
        "override_id": str(override.id),
        "tenant_id": override.tenant_id,
        "project_id": str(override.project_id) if override.project_id else None,
        "crop_code": override.crop_code,
        "season_code": override.season_code,
        "region_code": override.region_code,
        "geography_scope": override.geography_scope,
        "suitability_status": override.suitability_status,
        "confidence": override.confidence,
        "irrigation_required": override.irrigation_required,
        "warning_rules": override.warning_rules or [],
        "source_references": override.source_references or [],
        "review_status": override.review_status,
        "review_notes": override.review_notes,
        "reason": override.reason,
    }


def _first_effective_override(db, *, tenant_id, project_id, crop_code, season_code, region_code):
    from app.modules.master_data.models import CropClimateSuitabilityOverride

    filters = [
        CropClimateSuitabilityOverride.tenant_id == tenant_id,
        CropClimateSuitabilityOverride.crop_code == crop_code,
        CropClimateSuitabilityOverride.season_code == season_code,
        CropClimateSuitabilityOverride.region_code == region_code,
        CropClimateSuitabilityOverride.review_status == "PUBLISHED",
        CropClimateSuitabilityOverride.is_active == True,
    ]
    if project_id:
        project_override = (
            db.query(CropClimateSuitabilityOverride)
            .filter(*filters, CropClimateSuitabilityOverride.project_id == project_id)
            .order_by(CropClimateSuitabilityOverride.updated_at.desc())
            .first()
        )
        if project_override:
            return project_override
    return (
        db.query(CropClimateSuitabilityOverride)
        .filter(*filters, CropClimateSuitabilityOverride.project_id.is_(None))
        .order_by(CropClimateSuitabilityOverride.updated_at.desc())
        .first()
    )


@router.get("/suitability", response_model=dict)
def get_crop_geography_suitability(
    crop_code: str = Query(...),
    season_code: str = Query(...),
    state_lgd_code: str | None = Query(None),
    district_lgd_code: str | None = Query(None),
    pin_code: str | None = Query(None),
    project_id: str | None = Query(None),
    tenant_id: str = Header("default", alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    from uuid import UUID
    from app.modules.master_data.models import (
        Crop,
        CropClimateSuitabilityRule,
        GeographyClimateRegion,
        GeographyClimateRegionMapping,
    )

    crop_code = crop_code.upper()
    season_code = season_code.upper()

    crop = db.query(Crop).filter(Crop.code == crop_code, Crop.is_active == True).first()
    if not crop:
        raise HTTPException(404, "Crop not found")

    project_uuid = UUID(project_id) if project_id else None

    mapping_query = db.query(GeographyClimateRegionMapping).filter(
        GeographyClimateRegionMapping.is_active == True
    )
    if pin_code:
        mapping_query = mapping_query.filter(GeographyClimateRegionMapping.pin_code == pin_code)
    elif district_lgd_code:
        mapping_query = mapping_query.filter(GeographyClimateRegionMapping.district_lgd_code == district_lgd_code)
    elif state_lgd_code:
        mapping_query = mapping_query.filter(GeographyClimateRegionMapping.state_lgd_code == state_lgd_code)
    else:
        raise HTTPException(400, "Provide state_lgd_code, district_lgd_code, or pin_code")

    mappings = mapping_query.all()
    region_codes = sorted({m.region_code for m in mappings})

    rules = []
    effective = []
    for region_code in region_codes:
        rule = (
            db.query(CropClimateSuitabilityRule)
            .filter(
                CropClimateSuitabilityRule.crop_code == crop_code,
                CropClimateSuitabilityRule.season_code == season_code,
                CropClimateSuitabilityRule.region_code == region_code,
                CropClimateSuitabilityRule.is_active == True,
            )
            .first()
        )
        if not rule:
            continue
        override = _first_effective_override(
            db,
            tenant_id=tenant_id,
            project_id=project_uuid,
            crop_code=crop_code,
            season_code=season_code,
            region_code=region_code,
        )
        default_payload = _suitability_public_rule(rule)
        effective_payload = _suitability_public_override(override) if override else default_payload
        effective_payload["source"] = "PROJECT_OVERRIDE" if override and override.project_id else ("TENANT_OVERRIDE" if override else "DEFAULT_RULE")
        rules.append(default_payload)
        effective.append(effective_payload)

    status_rank = {
        "UNSUITABLE": 0,
        "NOT_TYPICAL": 1,
        "UNKNOWN": 2,
        "CONDITIONAL": 3,
        "SUITABLE": 4,
        "HIGHLY_SUITABLE": 5,
    }
    best = max(effective, key=lambda r: status_rank.get(r.get("suitability_status"), 2), default=None)
    warnings = []
    for row in effective:
        warnings.extend(row.get("warning_rules") or [])

    regions = (
        db.query(GeographyClimateRegion)
        .filter(GeographyClimateRegion.region_code.in_(region_codes), GeographyClimateRegion.is_active == True)
        .all()
        if region_codes else []
    )

    return {
        "schema_version": "crop_geography_suitability.v1",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "crop_code": crop_code,
        "season_code": season_code,
        "geography": {
            "state_lgd_code": state_lgd_code,
            "district_lgd_code": district_lgd_code,
            "pin_code": pin_code,
        },
        "region_matches": [
            {
                "region_code": region.region_code,
                "region_name": region.region_name,
                "region_system": region.region_system,
                "confidence": region.confidence,
                "review_status": region.review_status,
            }
            for region in regions
        ],
        "default_rules": rules,
        "effective_rules": effective,
        "suitability": {
            "status": best.get("suitability_status") if best else "UNKNOWN",
            "source": best.get("source") if best else "NO_RULE_MATCH",
            "confidence": best.get("confidence") if best else "UNKNOWN",
            "warnings": warnings,
            "requires_confirmation": any(row.get("suitability_status") in {"CONDITIONAL", "NOT_TYPICAL", "UNSUITABLE"} for row in effective),
        },
        "android_contract": {
            "android_hardcodes_suitability": False,
            "android_displays_backend_warning": True,
            "climate_layer_is_advisory_intelligence": True,
        },
    }


@router.get("/suitability-overrides", response_model=dict)
def list_crop_climate_suitability_overrides(
    crop_code: str | None = Query(None),
    season_code: str | None = Query(None),
    project_id: str | None = Query(None),
    tenant_id: str = Header("default", alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    from uuid import UUID
    from app.modules.master_data.models import CropClimateSuitabilityOverride

    query = db.query(CropClimateSuitabilityOverride).filter(
        CropClimateSuitabilityOverride.tenant_id == tenant_id,
        CropClimateSuitabilityOverride.is_active == True,
    )
    if crop_code:
        query = query.filter(CropClimateSuitabilityOverride.crop_code == crop_code.upper())
    if season_code:
        query = query.filter(CropClimateSuitabilityOverride.season_code == season_code.upper())
    if project_id:
        query = query.filter(CropClimateSuitabilityOverride.project_id == UUID(project_id))

    overrides = query.order_by(CropClimateSuitabilityOverride.updated_at.desc()).limit(200).all()
    return {
        "schema_version": "crop_climate_suitability_overrides.v1",
        "tenant_id": tenant_id,
        "count": len(overrides),
        "overrides": [_suitability_public_override(row) for row in overrides],
    }


@router.post("/suitability-overrides", response_model=dict)
def publish_crop_climate_suitability_override(
    payload: dict = Body(...),
    tenant_id: str = Header("default", alias="X-Tenant-ID"),
    actor_id: str | None = Header(None, alias="X-Actor-ID"),
    db: Session = Depends(get_db),
):
    from uuid import UUID
    from app.modules.master_data.models import Crop, CropClimateSuitabilityOverride, GeographyClimateRegion

    crop_code = str(payload.get("crop_code") or "").upper()
    season_code = str(payload.get("season_code") or "").upper()
    region_code = str(payload.get("region_code") or "")
    project_id = payload.get("project_id")
    project_uuid = UUID(project_id) if project_id else None
    status = str(payload.get("suitability_status") or "UNKNOWN").upper()

    allowed = {"HIGHLY_SUITABLE", "SUITABLE", "CONDITIONAL", "NOT_TYPICAL", "UNSUITABLE", "UNKNOWN"}
    if status not in allowed:
        raise HTTPException(400, {"error": "INVALID_SUITABILITY_STATUS", "allowed": sorted(allowed)})

    if not db.query(Crop).filter(Crop.code == crop_code, Crop.is_active == True).first():
        raise HTTPException(404, "Crop not found")
    if not db.query(GeographyClimateRegion).filter(GeographyClimateRegion.region_code == region_code, GeographyClimateRegion.is_active == True).first():
        raise HTTPException(404, "Climate region not found")

    override = CropClimateSuitabilityOverride(
        tenant_id=tenant_id,
        project_id=project_uuid,
        crop_code=crop_code,
        season_code=season_code,
        region_code=region_code,
        geography_scope=str(payload.get("geography_scope") or "REGION"),
        suitability_status=status,
        confidence=str(payload.get("confidence") or "CLIENT_OVERRIDE"),
        irrigation_required=bool(payload.get("irrigation_required") or False),
        warning_rules=payload.get("warning_rules") or [],
        source_references=payload.get("source_references") or [],
        review_status="PUBLISHED",
        review_notes=payload.get("review_notes"),
        published_by=actor_id,
        reason=payload.get("reason"),
        metadata_=payload.get("metadata") or {},
    )
    db.add(override)
    db.commit()
    db.refresh(override)

    return {
        "schema_version": "crop_climate_suitability_override_publish_result.v1",
        "override": _suitability_public_override(override),
        "message": "Crop climate suitability override published.",
    }

@router.get("/suitability-regions", response_model=dict)
def list_crop_climate_regions(
    review_status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.modules.master_data.models import GeographyClimateRegion, GeographyClimateRegionMapping

    query = db.query(GeographyClimateRegion).filter(GeographyClimateRegion.is_active == True)
    if review_status:
        query = query.filter(GeographyClimateRegion.review_status == review_status)

    regions = query.order_by(GeographyClimateRegion.region_system, GeographyClimateRegion.region_code).all()
    mappings = (
        db.query(GeographyClimateRegionMapping)
        .filter(GeographyClimateRegionMapping.is_active == True)
        .all()
    )
    mappings_by_region = {}
    for mapping in mappings:
        mappings_by_region.setdefault(mapping.region_code, []).append({
            "mapping_id": str(mapping.id),
            "scope_level": mapping.scope_level,
            "state_lgd_code": mapping.state_lgd_code,
            "district_lgd_code": mapping.district_lgd_code,
            "block_lgd_code": mapping.block_lgd_code,
            "village_lgd_code": mapping.village_lgd_code,
            "pin_code": mapping.pin_code,
            "confidence": mapping.confidence,
            "review_status": mapping.review_status,
            "metadata": mapping.metadata_ or {},
        })

    return {
        "schema_version": "crop_climate_regions.v1",
        "count": len(regions),
        "regions": [
            {
                "region_id": str(region.id),
                "region_code": region.region_code,
                "region_name": region.region_name,
                "region_system": region.region_system,
                "parent_region_code": region.parent_region_code,
                "country_code": region.country_code,
                "rainfall_band_mm": region.rainfall_band_mm or {},
                "temperature_band_c": region.temperature_band_c or {},
                "length_of_growing_period_days": region.length_of_growing_period_days or {},
                "dominant_soil_groups": region.dominant_soil_groups or [],
                "irrigation_context": region.irrigation_context or {},
                "source_references": region.source_references or [],
                "confidence": region.confidence,
                "review_status": region.review_status,
                "metadata": region.metadata_ or {},
                "mappings": mappings_by_region.get(region.region_code, []),
            }
            for region in regions
        ],
    }


@router.get("/suitability-rules", response_model=dict)
def list_crop_climate_suitability_rules(
    crop_code: str | None = Query(None),
    season_code: str | None = Query(None),
    region_code: str | None = Query(None),
    review_status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    from app.modules.master_data.models import CropClimateSuitabilityRule

    query = db.query(CropClimateSuitabilityRule).filter(CropClimateSuitabilityRule.is_active == True)
    if crop_code:
        query = query.filter(CropClimateSuitabilityRule.crop_code == crop_code.upper())
    if season_code:
        query = query.filter(CropClimateSuitabilityRule.season_code == season_code.upper())
    if region_code:
        query = query.filter(CropClimateSuitabilityRule.region_code == region_code)
    if review_status:
        query = query.filter(CropClimateSuitabilityRule.review_status == review_status)

    rules = (
        query.order_by(
            CropClimateSuitabilityRule.region_code,
            CropClimateSuitabilityRule.season_code,
            CropClimateSuitabilityRule.crop_code,
        )
        .limit(limit)
        .all()
    )

    return {
        "schema_version": "crop_climate_suitability_rules.v1",
        "count": len(rules),
        "rules": [_suitability_public_rule(rule) for rule in rules],
    }
