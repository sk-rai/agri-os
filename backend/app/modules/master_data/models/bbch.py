"""BBCH Scale reference data.

The BBCH (Biologische Bundesanstalt, Bundessortenamt und CHemische Industrie)
scale is the industry-standard framework for crop phenological stages.

Two-digit decimal code (00-99):
- First digit: principal growth stage (0-9)
- Second digit: secondary growth stage within principal

This table provides the universal reference. Crop lifecycle templates
can optionally map their stages to BBCH ranges for:
- Scientific interoperability
- Satellite/NDVI correlation
- Cross-crop benchmarking
- Precision input timing

The BBCH mapping is OPTIONAL — tenants can use simple stage names
without BBCH codes and the system still works.
"""

from sqlalchemy import Column, String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class BBCHPrincipalStage(Base, UUIDPrimaryKey, AuditMixin):
    """The 10 principal BBCH growth stages (0-9)."""

    __tablename__ = "bbch_principal_stages"

    code = Column(Integer, unique=True, nullable=False)  # 0-9
    code_range_start = Column(Integer, nullable=False)  # 0, 10, 20, ...
    code_range_end = Column(Integer, nullable=False)  # 9, 19, 29, ...
    canonical_name = Column(String(100), nullable=False)
    description = Column(Text)
    aliases = Column(JSONB, default=list)
    # e.g., [{"lang": "hi", "name": "अंकुरण"}]
    applicable_crop_types = Column(JSONB, default=list)
    # e.g., ["CEREALS", "PULSES", "VEGETABLES", "FRUITS"]
