"""Shared provider worker runtime policy helpers.

These helpers keep weather and soil provider worker configuration explicit,
serializable, and testable without making external network calls.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderRuntimePolicy:
    timeout_seconds: int = 20
    max_retries: int = 2
    backoff_seconds: int = 30
    rate_limit_window_seconds: int = 60
    max_requests_per_window: int = 60
    demo_mode: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def provider_runtime_policy_from_config(config: dict[str, Any] | None) -> ProviderRuntimePolicy:
    source = config or {}

    def int_value(key: str, default: int, *, minimum: int, maximum: int) -> int:
        raw = source.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    return ProviderRuntimePolicy(
        timeout_seconds=int_value("timeout_seconds", 20, minimum=1, maximum=120),
        max_retries=int_value("max_retries", 2, minimum=0, maximum=10),
        backoff_seconds=int_value("backoff_seconds", 30, minimum=0, maximum=3600),
        rate_limit_window_seconds=int_value("rate_limit_window_seconds", 60, minimum=1, maximum=86400),
        max_requests_per_window=int_value("max_requests_per_window", 60, minimum=1, maximum=100000),
        demo_mode=bool(source.get("demo_mode") or source.get("demo_payload")),
    )


def provider_failure_metadata(*, error: Any, policy: ProviderRuntimePolicy) -> dict:
    to_dict = getattr(error, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
    else:
        payload = {
            "error_code": "PROVIDER_UNEXPECTED_ERROR",
            "message": str(error),
            "retryable": True,
        }
    payload["runtime_policy"] = policy.to_dict()
    return payload
