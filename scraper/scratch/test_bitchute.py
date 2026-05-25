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
    print(f"Testing BitChute parsing for: {url}")
    
    async with launch_browser(session_key="test_bitchute") as context:
        page = await context.new_page()
        await page.goto(url)
        await asyncio.sleep(5)
        
        content = await page.content()
        soup = BeautifulSoup(content, "lxml")
        
        # Print page size and title
        print(f"Page Title: {await page.title()}")
        print(f"HTML Size: {len(content)} bytes")
        
        # Test Channel Name
        name_node = soup.select_one("span.q-btn__content span.block")
        print(f"Name (span.q-btn__content span.block): {name_node.get_text(strip=True) if name_node else None}")
        
        # Test Subscriber Count
        sub_node = soup.select_one("div.text-caption.text-grey-8 span[style*=\"cursor: pointer\"]")
        print(f"Subscribers: {sub_node.get_text(strip=True) if sub_node else None}")
        
        # Test Description selectors
        desc_primary = soup.select_one("div[style*=\"white-space: pre-line\"]")
        desc_fallback = soup.select_one("div.text-grey-8.bc-text-break.bc-description")
        print(f"Description primary: {desc_primary.get_text(strip=True)[:100] if desc_primary else None}")
        print(f"Description fallback: {desc_fallback.get_text(strip=True)[:100] if desc_fallback else None}")
        
        # Test External Links selectors
        links = soup.select("div.row.q-mt-sm a[target=\"_blank\"]")
        print(f"Links count (row.q-mt-sm): {len(links)}")
        for l in links:
            print(f"  - {l.get('href')}")
            
        links_fallback = soup.select("div.text-grey-8.bc-text-break.bc-description a[target=\"_blank\"]")
        print(f"Links count (bc-description): {len(links_fallback)}")
        for l in links_fallback:
            print(f"  - {l.get('href')}")

        # Test video cards
        cards = soup.select("a[href^=\"/video/\"]")
        print(f"Video cards count (a[href^=\"/video/\"]): {len(cards)}")
        for c in cards[:5]:
            print(f"  - Card title: {c.get_text(strip=True)[:50]} | Href: {c.get('href')}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
