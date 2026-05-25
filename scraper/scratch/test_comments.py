import asyncio
import logging
import sys
import re
from pathlib import Path

# Add scraper path to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser import launch_browser
from bs4 import BeautifulSoup
from scrapers.rumble import parse_count_text

logging.basicConfig(level=logging.INFO)

async def test_scrape():
    url = "https://rumble.com/c/ElaineBeck/videos"
    print(f"Testing multiple videos for: {url}")
    
    async with launch_browser(session_key="test_comments_rumble_elaine") as context:
        page = await context.new_page()
        await page.goto(url)
        await asyncio.sleep(5)
        
        content = await page.content()
        soup = BeautifulSoup(content, "lxml")
        
        video_links = []
        for card in soup.select("div.videostream.thumbnail__grid--item"):
            link_node = card.select_one("a.title__link.link")
            if link_node:
                href = link_node.get("href")
                if href:
                    video_links.append(href)
                    
        print(f"Found {len(video_links)} videos. Checking first 5:")
        
        for idx, link in enumerate(video_links[:5]):
            video_url = "https://rumble.com" + link
            print(f"\n--- Video {idx+1}: {video_url} ---")
            await page.goto(video_url)
            await asyncio.sleep(3)
            
            # Scroll down to load comments
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(1.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            video_content = await page.content()
            video_soup = BeautifulSoup(video_content, "lxml")
            
            # Extract comment headers and values
            comment_header = video_soup.select_one("div.comments-header > h3.comment-count")
            comment_text = comment_header.get_text(" ", strip=True) if comment_header else None
            parsed = parse_count_text(comment_text) if comment_text else None
            
            print(f"  Primary selector (div.comments-header > h3.comment-count): {comment_header}")
            print(f"  Text: '{comment_text}'")
            print(f"  Parsed as integer: {parsed}")
            
            # Check for alternative elements
            alt_comments = video_soup.select(".comment-count, span.comments-count, span.comment-count")
            print(f"  Alt selectors: {[ (elem.name, elem.get('class'), elem.get_text(strip=True)) for elem in alt_comments ]}")
            
            # Let's inspect the entire #video-comments section structure
            video_comments_sec = video_soup.select_one("#video-comments")
            if video_comments_sec:
                text_sec = video_comments_sec.get_text(" ", strip=True)
                print(f"  #video-comments text: '{text_sec[:150]}...'")
                # print first 500 chars of HTML
                html_snippet = str(video_comments_sec)[:500]
                print(f"  #video-comments HTML: {html_snippet}")
            else:
                print("  #video-comments section NOT found.")

if __name__ == "__main__":
    asyncio.run(test_scrape())
