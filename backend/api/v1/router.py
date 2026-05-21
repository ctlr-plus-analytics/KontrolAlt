"""API v1 router — mounts all sub-routers."""

from fastapi import APIRouter

from api.v1.channels import router as channels_router
from api.v1.velocity import router as velocity_router
from api.v1.gate0 import router as gate0_router
from api.v1.lookalike import router as lookalike_router
from api.v1.scraper import router as scraper_router
from api.v1.admin import router as admin_router

api_v1_router = APIRouter()

api_v1_router.include_router(channels_router, prefix="/channels", tags=["channels"])
api_v1_router.include_router(velocity_router, prefix="/velocity", tags=["velocity"])
api_v1_router.include_router(gate0_router, prefix="/gate0", tags=["gate0"])
api_v1_router.include_router(lookalike_router, prefix="/lookalike", tags=["lookalike"])
api_v1_router.include_router(scraper_router, prefix="/scraper", tags=["scraper"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["admin"])
