"""Controlled HTTP boundary for provider integrations.

This module centralizes future external provider calls so weather/soil
adapters do not scatter raw HTTP clients, timeout rules, retry policy,
or live-execution gates across the codebase.

Current behavior is intentionally no-network unless live execution is
explicitly enabled in provider config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.media.provider_runtime_policy import (
    ProviderRuntimePolicy,
    provider_live_execution_status,
    provider_runtime_policy_from_config,
)


@dataclass(frozen=True)
class ProviderHttpRequest:
    provider: str
    method: str
    url: str
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ProviderHttpResponse:
    provider: str
    status_code: int
    payload: dict[str, Any]
    metadata: dict[str, Any]


class ProviderLiveExecutionBlocked(Exception):
    def __init__(self, *, provider: str, request: ProviderHttpRequest, policy: ProviderRuntimePolicy, live_execution: dict):
        super().__init__("Live provider execution is blocked until explicitly approved.")
        self.provider = provider
        self.request = request
        self.policy = policy
        self.live_execution = live_execution

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "error_code": "PROVIDER_LIVE_EXECUTION_BLOCKED",
            "message": str(self),
            "retryable": False,
            "runtime_policy": self.policy.to_dict(),
            "live_execution": self.live_execution,
            "request": {
                "method": self.request.method,
                "url": self.request.url,
                "params": self.request.params or {},
            },
        }


def execute_provider_http_request(request: ProviderHttpRequest, *, config: dict[str, Any] | None = None) -> ProviderHttpResponse:
    policy = provider_runtime_policy_from_config(config)
    live_execution = provider_live_execution_status(config)
    if not live_execution["live_execution_enabled"]:
        raise ProviderLiveExecutionBlocked(provider=request.provider, request=request, policy=policy, live_execution=live_execution)

    raise NotImplementedError("Live provider HTTP execution is not wired yet. Add the approved HTTP client here.")
