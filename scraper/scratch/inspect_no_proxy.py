import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Inspecting network and errors (NO PROXY) for: {url}")
    
    async with launch_browser(session_key="inspect_no_proxy", use_proxy=False) as context:
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
