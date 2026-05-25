import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser

async def test_scrape():
    url = "https://www.bitchute.com/channel/pierregirard"
    print(f"Saving HTML for: {url}")
    
    async with launch_browser(session_key="dump_bitchute") as context:
        page = await context.new_page()
        await page.goto(url)
        await asyncio.sleep(5)
        
        html = await page.content()
        with open("scratch/bitchute_channel.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved to scratch/bitchute_channel.html")

if __name__ == "__main__":
    asyncio.run(test_scrape())
