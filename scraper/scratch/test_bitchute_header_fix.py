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
    print(f"Testing BitChute parsing with fixed headers for: {url}")
    
    profile = get_consistent_browser_profile()
    # Filter out Accept and Upgrade-Insecure-Requests from extra_http_headers
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
        
        # Listeners to verify network requests
        def handle_response(res):
            if "api.bitchute.com" in res.url:
                print(f"[API Response] Status: {res.status} | Content-Type: {res.headers.get('content-type')} | URL: {res.url}")
                
        page.on("response", handle_response)
        page.on("console", lambda msg: print(f"[Console {msg.type}] {msg.text}"))
        
        print("Navigating to URL...")
        await page.goto(url)
        
        print("Waiting for channel header name element...")
        try:
            # Wait for the channel name element to render
            await page.wait_for_selector("span.q-btn__content span.block, div.q-card__section.q-card__section--vert.q-pt-none > div.row.text-bold.text-h4", timeout=15000)
            print("Successfully found channel name element!")
        except Exception as e:
            print(f"Timeout waiting for elements: {e}")
            
        content = await page.content()
        soup = BeautifulSoup(content, "lxml")
        
        # Test Channel Name
        name_node = soup.select_one("span.q-btn__content span.block") or soup.select_one("div.q-card__section.q-card__section--vert.q-pt-none > div.row.text-bold.text-h4")
        print(f"Name: {name_node.get_text(strip=True) if name_node else None}")
        
        # Test Subscriber Count
        sub_node = soup.select_one("div.text-caption.text-grey-8 span[style*=\"cursor: pointer\"]")
        print(f"Subscribers: {sub_node.get_text(strip=True) if sub_node else None}")
        
        # Test Video cards
        cards = soup.select("a[href^=\"/video/\"]")
        print(f"Video cards count: {len(cards)}")
        for c in cards[:3]:
            print(f"  - Card: {c.get_text(strip=True)[:50]} | Href: {c.get('href')}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
