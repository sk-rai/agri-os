"""Shared farmer enrollment field normalization contracts."""

from __future__ import annotations

from typing import Optional


def normalize_assistance_mode(value: Optional[str]) -> str:
    """Map Android assistance modes to persisted enrollment methods."""
    normalized = (value or "ASSISTED").strip().upper()
    mapping = {
        "SELF_SERVICE": "SELF",
        "DEALER_ASSISTED": "ASSISTED",
        "FIELD_AGENT_ASSISTED": "ASSISTED",
        "AGRONOMIST_ASSISTED": "ASSISTED",
    }
    return mapping.get(normalized, normalized)
