import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Inspecting network for: {url}")
    
    async with launch_browser(session_key="inspect_network") as context:
        page = await context.new_page()
        
        # Log all requests and responses
        def handle_response(response):
            print(f"[Network Response] Status: {response.status} | Content-Type: {response.headers.get('content-type', 'unknown')} | URL: {response.url}")
            
        page.on("response", handle_response)
        
        try:
            print("Navigating to URL...")
            await page.goto(url)
            print("Waiting 10 seconds...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
