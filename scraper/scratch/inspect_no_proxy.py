import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camoufox.async_api import AsyncCamoufox
from core.cf_bypass import get_consistent_browser_profile
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Inspecting network and errors (NO PROXY) for: {url}")
    
    profile = get_consistent_browser_profile()
    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        context = await browser.new_context(
            viewport=profile["viewport"],
            locale=str(profile["locale"]),
            timezone_id=str(profile["timezone_id"]),
            user_agent=str(profile["user_agent"]),
            extra_http_headers=profile["extra_http_headers"],
        )
        page = await context.new_page()
        
        # Listeners
        page.on("console", lambda msg: print(f"[Console {msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: print(f"[PageError] {exc}"))
        page.on("response", lambda res: print(f"[Network Response] Status: {res.status} | Content-Type: {res.headers.get('content-type', 'unknown')} | URL: {res.url}"))
        
        try:
            print("Navigating to URL...")
            await page.goto(url)
            print("Waiting 12 seconds...")
            await asyncio.sleep(12)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
