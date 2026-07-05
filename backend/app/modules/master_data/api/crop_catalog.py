"""Crop catalog API: taxonomy, propagation, and Android-ready crop metadata."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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
