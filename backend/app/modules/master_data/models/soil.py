"""Soil type reference data.

Source: ICAR-NBSS&LUP soil classification.
Static reference data — rarely changes.
"""

from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class SoilType(Base, UUIDPrimaryKey, AuditMixin):
    """Soil classification reference table."""

    __tablename__ = "soil_types"

    code = Column(String(30), unique=True, nullable=False, index=True)
    canonical_name = Column(String(100), nullable=False)
    description = Column(Text)
    characteristics = Column(JSONB, default=dict)
    suitable_crops = Column(JSONB, default=list)
    ph_range_min = Column(String(10))
    ph_range_max = Column(String(10))
    aliases = Column(JSONB, default=list)
