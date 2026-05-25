import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Inspecting errors for: {url}")
    
    async with launch_browser(session_key="inspect_errors") as context:
        page = await context.new_page()
        
        # Capture console logs and details
        def handle_console(msg):
            print(f"[Console {msg.type}] {msg.text}")
            if msg.location:
                print(f"  Location: {msg.location}")
                
        page.on("console", handle_console)
        
        # Capture page errors
        def handle_pageerror(exc):
            print(f"[PageError Exception] {exc}")
            if hasattr(exc, "stack"):
                print(f"  Stack trace:\n{exc.stack}")
                
        page.on("pageerror", handle_pageerror)
        
        try:
            print("Navigating to URL...")
            await page.goto(url)
            print("Waiting 12 seconds...")
            await asyncio.sleep(12)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
