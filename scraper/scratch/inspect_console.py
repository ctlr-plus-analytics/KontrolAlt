import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Inspecting console and requests for: {url}")
    
    async with launch_browser(session_key="inspect_console_bitchute") as context:
        page = await context.new_page()
        
        # Listen to console messages
        page.on("console", lambda msg: print(f"[Console] {msg.type}: {msg.text}"))
        # Listen to page errors
        page.on("pageerror", lambda err: print(f"[PageError] {err}"))
        # Listen to failed requests
        page.on("requestfailed", lambda req: print(f"[RequestFailed] {req.method} {req.url} - Error: {req.failure}"))
        # Listen to responses
        page.on("response", lambda res: print(f"[Response] {res.status} {res.url}") if res.status >= 400 else None)
        
        print("Navigating to URL...")
        await page.goto(url)
        print("Navigation done. Waiting 10 seconds for Vue app to load and execute...")
        await asyncio.sleep(10)
        print("Finished waiting.")

if __name__ == "__main__":
    asyncio.run(test_scrape())
