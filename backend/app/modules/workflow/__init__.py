"""Workflow module exports without eager API imports.

Keeping the package initializer model-safe prevents Alembic model discovery
from importing FastAPI routes and their authorization dependencies.
"""

from __future__ import annotations


__all__ = ["workflow_router"]


def __getattr__(name: str):
    if name == "workflow_router":
        from app.modules.workflow.api import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
