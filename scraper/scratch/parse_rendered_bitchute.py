from bs4 import BeautifulSoup
import re

with open("scratch/rendered_bitchute.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

print("Rendered BitChute DOM Analysis:")

# 1. Search for 'pierre@raqiya' in text nodes to see where the channel name is
print("\nSearching for channel name 'pierre@raqiya' or 'pierre' in elements:")
for tag in soup.find_all(True):
    # check text content of the tag directly (not children)
    text = "".join([t for t in tag.contents if isinstance(t, str)]).strip()
    if "pierre@raqiya" in text or "pierre" in text:
        print(f"  <{tag.name} class='{tag.get('class')}'> {text}")

# 2. Search for 'subscribers' in text nodes
print("\nSearching for 'subscribers' in elements:")
for tag in soup.find_all(True):
    text = "".join([t for t in tag.contents if isinstance(t, str)]).strip()
    if "subscriber" in text.lower():
        print(f"  <{tag.name} class='{tag.get('class')}'> {text}")

# 3. Look at any video cards / anchors containing '/video/'
print("\nChecking for video links in rendered DOM:")
anchors = soup.find_all("a", href=True)
video_anchors = [a for a in anchors if "/video/" in a.get("href")]
print(f"Found {len(video_anchors)} video anchors:")
for a in video_anchors[:5]:
    parent_classes = a.parent.get("class") if a.parent else []
    print(f"  <{a.name} class='{a.get('class')}' href='{a.get('href')}'> (Parent: <{a.parent.name} class='{parent_classes}'>) text: '{a.get_text(strip=True)[:50]}'")

# 4. Search for social links (external links)
print("\nChecking external/social links:")
for a in anchors:
    href = a.get("href")
    if href and not href.startswith(("/", "mailto:", "tel:", "#", "javascript:")) and "bitchute.com" not in href:
        print(f"  Social Link: {href} | Text: '{a.get_text(strip=True)}'")
