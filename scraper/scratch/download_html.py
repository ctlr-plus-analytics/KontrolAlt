import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser

async def test_scrape():
    video_url = "https://rumble.com/v5a8x5f-jesus-reigns-on-our-southern-border-ft.-franklin-graham.html"
    print(f"Downloading HTML for: {video_url}")
    
    async with launch_browser(session_key="download_html_rumble") as context:
        page = await context.new_page()
        await page.goto(video_url)
        await asyncio.sleep(5)
        
        # Scroll down and wait a bit
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(2)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(3)
        
        html = await page.content()
        with open("scratch/video_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved to scratch/video_page.html")

if __name__ == "__main__":
    asyncio.run(test_scrape())
