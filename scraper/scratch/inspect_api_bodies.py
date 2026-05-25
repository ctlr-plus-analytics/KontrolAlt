import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camoufox.async_api import AsyncCamoufox
from core.cf_bypass import get_consistent_browser_profile

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Inspecting API bodies for: {url}")
    
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
        
        async def handle_response(res):
            if "api.bitchute.com" in res.url:
                try:
                    text = await res.text()
                    print(f"\n[API Response] {res.status} | Content-Type: {res.headers.get('content-type')} | URL: {res.url}")
                    print(f"  Body (first 500 chars): {text[:500]}")
                except Exception as e:
                    print(f"  Error reading body for {res.url}: {e}")
                    
        page.on("response", handle_response)
        
        try:
            await page.goto(url)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
