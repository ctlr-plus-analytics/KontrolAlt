from bs4 import BeautifulSoup
import re

with open("scratch/video_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

print("Checking elements related to comments:")

# 1. Look for any tags with id or class containing 'comment'
print("\nTags with class or id containing 'comment':")
for tag in soup.find_all(True):
    tag_id = tag.get("id") or ""
    tag_classes = tag.get("class") or []
    classes_str = " ".join(tag_classes)
    
    if "comment" in tag_id.lower() or "comment" in classes_str.lower():
        print(f"  <{tag.name} id='{tag_id}' class='{classes_str}'> (text: '{tag.get_text(strip=True)[:100]}')")

# 2. Look for any script tags containing 'comments' or comment counts
print("\nScript tags containing 'comment' or comment variables:")
for idx, script in enumerate(soup.find_all("script")):
    text = script.get_text()
    if "comment" in text.lower():
        print(f"  Script {idx}: contains 'comment' (length: {len(text)})")
        # Print a few lines around 'comment'
        for line in text.split("\n"):
            if "comment" in line.lower():
                print(f"    Line: {line.strip()[:120]}")

# 3. Look for 'disabled' or comments closed messaging
print("\nSearching for comments disabled/closed messaging in body text:")
body_text = soup.get_text(" ", strip=True)
for match in re.finditer(r'([^.!?\n]*comment[^.!?\n]*)', body_text, re.I):
    print(f"  Match: '{match.group(1).strip()[:120]}'")
