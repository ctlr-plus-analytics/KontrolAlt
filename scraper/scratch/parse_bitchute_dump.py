from bs4 import BeautifulSoup

with open("scratch/bitchute_channel.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

print("BitChute Channel HTML Analysis:")
print(f"Title: {soup.title.string if soup.title else 'No Title'}")
print(f"HTML Length: {len(html)} bytes")

# Print first 2000 chars of body text
body = soup.body
if body:
    text = body.get_text(" ", strip=True)
    print(f"\nFirst 1000 chars of body text:\n{text[:1000]}")
else:
    print("\nNo body element found!")

# Search for potential video card elements or anchors
print("\nSome sample video links / anchors:")
anchors = soup.find_all("a", href=True)
print(f"Found {len(anchors)} anchors in total.")
video_anchors = [a for a in anchors if "/video/" in a.get("href") or "/channel/" in a.get("href")]
print(f"Found {len(video_anchors)} video/channel anchors:")
for a in video_anchors[:10]:
    print(f"  <{a.name} href='{a.get('href')}'> text: '{a.get_text(strip=True)}'")
