import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from camoufox.async_api import AsyncCamoufox
from core.proxy import get_random_proxy
from core.browser import _parse_proxy_settings

async def main():
    try:
        proxy_url = get_random_proxy()
        proxy_settings = _parse_proxy_settings(proxy_url)

        async with AsyncCamoufox(
            headless=True,
            proxy=proxy_settings,
            geoip=True,
        ) as browser:
            # Create a context explicitly
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                service_workers="block",
                permissions=["geolocation"],
            )
            
            page = await context.new_page()
            
            # Print page title of rumble
            await page.goto("https://rumble.com")
            print(f"Rumble Title: {await page.title()}")
            
            # Evaluate browser attributes to see if they are spoofed
            ua = await page.evaluate("navigator.userAgent")
            tz = await page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
            lang = await page.evaluate("navigator.language")
            webdriver = await page.evaluate("navigator.webdriver")
            
            print(f"User Agent: {ua}")
            print(f"Timezone: {tz}")
            print(f"Language: {lang}")
            print(f"Webdriver: {webdriver}")
            
            await context.close()
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
