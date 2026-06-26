"""Tenant isolation middleware.

All API requests must include X-Tenant-ID header.
Master data endpoints are exempt (shared across tenants for MVP).

Per ADR-002: tenant_id enforced at middleware level, not per-query.
Per Security Framework: cross-tenant query returns 403.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths exempt from tenant requirement (public/shared data)
TENANT_EXEMPT_PATHS = [
    "/health",
    "/docs",
    "/openapi.json",
    "/api/v1/master-data/",  # Master data is shared (MVP)
    "/api/v1/auth/",  # Auth endpoints don't require tenant yet
    "/api/v1/tenants",  # Tenant creation doesn't require existing tenant
    "/api/v1/soil-profiles/infer",  # Soil inference is geography-based, no tenant
    "/api/v1/forms",  # Form schemas are cacheable, no tenant context needed
    "/api/v1/crop-cycles/templates",  # Crop templates are reference data
]


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract and validate X-Tenant-ID header."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip CORS preflight requests
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip tenant check for exempt paths
        if any(path.startswith(exempt) for exempt in TENANT_EXEMPT_PATHS):
            request.state.tenant_id = None
            return await call_next(request)

        # Extract tenant ID
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={"detail": "X-Tenant-ID header required"},
            )

        # Store in request state for downstream use
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response
