"""Dependency-light validated request shape shared by direct and sync ingress."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


ActivityDecimal10_2 = Annotated[
    Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)
]
ActivityDecimal12_2 = Annotated[
    Decimal, Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
]
ActivityDecimal12_3 = Annotated[
    Decimal, Field(ge=Decimal("0"), max_digits=12, decimal_places=3)
]
ActivityLatitude = Annotated[
    Decimal,
    Field(ge=Decimal("-90"), le=Decimal("90"), max_digits=10, decimal_places=8),
]
ActivityLongitude = Annotated[
    Decimal,
    Field(
        ge=Decimal("-180"),
        le=Decimal("180"),
        max_digits=11,
        decimal_places=8,
    ),
]


class ActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional stable direct-command identity for exact replay",
    )
    activity_type: str = Field(
        ...,
        pattern=r"^(FERTILIZER|PESTICIDE|IRRIGATION|LABOR|MACHINERY|HARVEST|SEED|OTHER)$",
    )
    input_code: Optional[str] = Field(default=None, max_length=50)
    input_name: Optional[str] = Field(default=None, max_length=200)
    requested_stage_id: Optional[uuid.UUID] = None
    requested_stage_code: Optional[str] = Field(default=None, max_length=50)
    quantity: Optional[ActivityDecimal10_2] = None
    quantity_unit: Optional[str] = Field(default=None, max_length=20)
    area_applied: Optional[ActivityDecimal10_2] = None
    area_unit: Optional[str] = Field(default=None, max_length=20)
    input_rule_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = None
    product_code: Optional[str] = Field(default=None, max_length=80)
    package_id: Optional[uuid.UUID] = None
    package_sku: Optional[str] = Field(default=None, max_length=100)
    recommended_quantity: Optional[ActivityDecimal12_3] = None
    recommended_quantity_unit: Optional[str] = Field(default=None, max_length=20)
    actual_quantity: Optional[ActivityDecimal12_3] = None
    actual_quantity_unit: Optional[str] = Field(default=None, max_length=20)
    dosage_variance_reason: Optional[str] = None
    cost_amount: Optional[ActivityDecimal12_2] = None
    cost_currency: Optional[str] = Field(default="INR", max_length=5)
    activity_date: date
    gps_lat: Optional[ActivityLatitude] = None
    gps_lng: Optional[ActivityLongitude] = None
    notes: Optional[str] = None
    irrigation_source: Optional[str] = Field(default=None, max_length=100)
    duration_hours: Optional[ActivityDecimal10_2] = None
