"""Season and cropping pattern reference data.

Standard Indian agricultural calendar: Kharif, Rabi, Zaid.
"""

from sqlalchemy import Column, String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.shared.models import AuditMixin, UUIDPrimaryKey


class Season(Base, UUIDPrimaryKey, AuditMixin):
    """Agricultural season (Kharif, Rabi, Zaid)."""

    __tablename__ = "seasons"

    code = Column(String(20), unique=True, nullable=False, index=True)
    canonical_name = Column(String(50), nullable=False)
    description = Column(Text)
    start_month = Column(Integer, nullable=False)  # 1-12
    end_month = Column(Integer, nullable=False)  # 1-12
    sowing_window_start = Column(Integer)  # day of year (1-365)
    sowing_window_end = Column(Integer)
    harvest_window_start = Column(Integer)
    harvest_window_end = Column(Integer)
    aliases = Column(JSONB, default=list)
