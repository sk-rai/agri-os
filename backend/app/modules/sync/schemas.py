"""Dependency-light Pydantic schemas for sync ingress."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SyncEventPayload(BaseModel):
    """A single sync event from the mobile client."""

    event_id: UUID
    entity_type: str = Field(
        ...,
        description="Canonical entity type (farmer, parcel, crop_cycle, crop_stage)",
    )
    entity_id: Optional[UUID] = None
    operation: str = Field(..., pattern="^(CREATE|UPDATE|DELETE)$")
    payload: dict
    version: int = Field(default=1, description="Client-side version counter")
    dependency_ids: list[UUID] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict, description="GPS, device_id, timestamp")

    model_config = ConfigDict(extra="forbid")


class SyncBatchRequest(BaseModel):
    """Batch of validated sync events."""

    events: list[SyncEventPayload] = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")
