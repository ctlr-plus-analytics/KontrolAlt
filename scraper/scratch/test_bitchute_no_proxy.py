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
    print(f"Testing BitChute parsing (NO PROXY) for: {url}")
    
    async with launch_browser(session_key="test_bitchute_no_proxy", use_proxy=False) as context:
        page = await context.new_page()
        await page.goto(url)
        
        # Wait for the Vue app / video grid to render
        print("Waiting for video cards or name element...")
        try:
            # wait for up to 10 seconds for the channel name or video card to render
            await page.wait_for_selector("span.q-btn__content span.block, a[href^='/video/']", timeout=12000)
            print("Successfully found element!")
        except Exception as e:
            print(f"Timeout waiting for elements: {e}")
            
        content = await page.content()
        soup = BeautifulSoup(content, "lxml")
        
        print(f"Page Title: {await page.title()}")
        print(f"HTML Size: {len(content)} bytes")
        
        # Test Channel Name
        name_node = soup.select_one("span.q-btn__content span.block")
        print(f"Name (span.q-btn__content span.block): {name_node.get_text(strip=True) if name_node else None}")
        
        # Test Subscriber Count
        sub_node = soup.select_one("div.text-caption.text-grey-8 span[style*=\"cursor: pointer\"]")
        print(f"Subscribers: {sub_node.get_text(strip=True) if sub_node else None}")
        
        # Test Video cards
        cards = soup.select("a[href^=\"/video/\"]")
        print(f"Video cards count: {len(cards)}")
        for c in cards[:5]:
            print(f"  - Card title: {c.get_text(strip=True)[:50]} | Href: {c.get('href')}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
