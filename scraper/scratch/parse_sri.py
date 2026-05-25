import hashlib
import httpx
from bs4 import BeautifulSoup

with open("scratch/bitchute_channel.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

print("Script SRI Integrity Check:")
scripts = soup.find_all("script", src=True)

with httpx.Client(timeout=10.0) as client:
    for s in scripts:
        src = s.get("src")
        integrity = s.get("integrity")
        if not integrity:
            print(f"Script: {src} - No Integrity Attribute")
            continue
            
        print(f"\nScript: {src}")
        print(f"  Expected Integrity: {integrity}")
        
        try:
            r = client.get(src)
            if r.status_code != 200:
                print(f"  Failed to fetch: HTTP {r.status_code}")
                continue
                
            content = r.content
            print(f"  Fetched Content Length: {len(content)} bytes")
            
            # Compute sha512 hash
            sha512_hash = hashlib.sha512(content).digest()
            import base64
            computed_integrity = "sha512-" + base64.b64encode(sha512_hash).decode("utf-8")
            print(f"  Computed Integrity: {computed_integrity}")
            
            if computed_integrity == integrity:
                print("  Status: MATCH!")
            else:
                print("  Status: MISMATCH!")
                print(f"  First 200 chars: {content[:200]}")
        except Exception as e:
            print(f"  Error fetching/hashing: {e}")
