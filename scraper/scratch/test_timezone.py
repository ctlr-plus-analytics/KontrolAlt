import asyncio
import os
from camoufox.async_api import AsyncCamoufox
from core.browser import _parse_proxy_settings
from core.proxy import get_random_proxy

async def main():
    # Load dotenv if not already loaded by core.proxy/config
    proxy = get_random_proxy()
    proxy_settings = _parse_proxy_settings(proxy)
    print("Using proxy:", proxy_settings.get("server"))
    
    async with AsyncCamoufox(
        headless=True,
        proxy=proxy_settings,
        geoip=True,
        os="windows",
    ) as browser:
        # Case 1: new_context without passing locale & timezone_id
        context1 = await browser.new_context()
        page1 = await context1.new_page()
        await page1.goto("https://httpbin.org/ip") # warmup
        
        js_loc_tz_1 = await page1.evaluate(
            "() => ({ lang: navigator.language, tz: Intl.DateTimeFormat().resolvedOptions().timeZone })"
        )
        print("Case 1 (no override):", js_loc_tz_1)
        await context1.close()
        
        # Case 2: new_context with en-US & America/New_York forced
        context2 = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York"
        )
        page2 = await context2.new_page()
        js_loc_tz_2 = await page2.evaluate(
            "() => ({ lang: navigator.language, tz: Intl.DateTimeFormat().resolvedOptions().timeZone })"
        )
        print("Case 2 (forced NY):", js_loc_tz_2)
        await context2.close()

if __name__ == "__main__":
    asyncio.run(main())
