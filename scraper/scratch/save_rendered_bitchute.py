import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Saving rendered HTML for: {url}")
    
    async with launch_browser(session_key="save_rendered_bitchute", use_proxy=False) as context:
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
