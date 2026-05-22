from fastapi import APIRouter

from app.modules.master_data.api.geography import router as geography_router
from app.modules.master_data.api.crops import router as crops_router
from app.modules.master_data.api.sync import router as sync_router

master_data_router = APIRouter(prefix="/api/v1/master-data")
master_data_router.include_router(geography_router)
master_data_router.include_router(crops_router)
master_data_router.include_router(sync_router)
