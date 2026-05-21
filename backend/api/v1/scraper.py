"""Scraper admin endpoints."""

from fastapi import APIRouter, Depends

from core.security import require_admin_user
from models.scrape import ScrapeTaskResponse
from services import scraper_service

router = APIRouter()


@router.post("/trigger", response_model=ScrapeTaskResponse)
async def trigger_scrape(
    user: dict = Depends(require_admin_user),
) -> ScrapeTaskResponse:
    """Trigger a full scrape run across all platforms."""
    return await scraper_service.trigger_full_scrape()


@router.post("/discovery/trigger", response_model=ScrapeTaskResponse)
async def trigger_discovery_only(
    user: dict = Depends(require_admin_user),
) -> ScrapeTaskResponse:
    """Trigger discovery expansion tasks only (without scraping channels)."""
    return await scraper_service.trigger_discovery_only()
