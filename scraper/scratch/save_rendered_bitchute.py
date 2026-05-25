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
    print(f"Saving rendered HTML for: {url}")
    
    profile = get_consistent_browser_profile()
    fixed_headers = {
        k: v for k, v in profile["extra_http_headers"].items()
        if k.lower() not in {"accept", "upgrade-insecure-requests"}
    }
    
    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        context = await browser.new_context(
            viewport=profile["viewport"],
            locale=str(profile["locale"]),
            timezone_id=str(profile["timezone_id"]),
            user_agent=str(profile["user_agent"]),
            extra_http_headers=fixed_headers,
        )
        page = await context.new_page()
        await page.goto(url)
        
        # Wait for the channel name element to render
        await page.wait_for_selector("span.q-btn__content span.block, div.q-card__section.q-card__section--vert.q-pt-none > div.row.text-bold.text-h4", timeout=15000)
        
        # Let's wait another 3 seconds for videos and other elements to finish loading
        await asyncio.sleep(3)
        
        html = await page.content()
        with open("scratch/rendered_bitchute.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved to scratch/rendered_bitchute.html")

if __name__ == "__main__":
    asyncio.run(test_scrape())
