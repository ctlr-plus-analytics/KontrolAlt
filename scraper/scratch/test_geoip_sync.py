import asyncio
import os
import httpx
from camoufox.async_api import AsyncCamoufox
from core.browser import _parse_proxy_settings
from core.proxy import get_random_proxy

async def main():
    proxy = get_random_proxy()
    proxy_settings = _parse_proxy_settings(proxy)
    
    # 1. Fetch geoip from httpbin or ip-api using httpx with proxy
    async with httpx.AsyncClient(proxies=proxy) as client:
        try:
            resp = await client.get("http://ip-api.com/json", timeout=10)
            ip_data = resp.json()
            print("Proxy IP Data:", {
                "ip": ip_data.get("query"),
                "timezone": ip_data.get("timezone"),
                "country": ip_data.get("countryCode"),
                "city": ip_data.get("city")
            })
        except Exception as e:
            print("Failed to fetch proxy IP metadata:", e)
            return

    async with AsyncCamoufox(
        headless=True,
        proxy=proxy_settings,
        geoip=True,
        os="windows",
    ) as browser:
        # Case A: Default Playwright context (no manual locale/timezone override)
        context_a = await browser.new_context()
        page_a = await context_a.new_page()
        await page_a.goto("https://httpbin.org/ip") # Warmup
        js_data_a = await page_a.evaluate(
            "() => ({ lang: navigator.language, tz: Intl.DateTimeFormat().resolvedOptions().timeZone })"
        )
        print("Case A (No Playwright overrides):", js_data_a)
        await context_a.close()

        # Case B: Standard KontrolAlt Browser Context Overrides (Manual NY profile)
        from core.cf_bypass import get_consistent_browser_profile
        profile = get_consistent_browser_profile()
        context_b = await browser.new_context(
            viewport=profile["viewport"],
            locale=str(profile["locale"]),
            timezone_id=str(profile["timezone_id"]),
        )
        page_b = await context_b.new_page()
        await page_b.goto("https://httpbin.org/ip") # Warmup
        js_data_b = await page_b.evaluate(
            "() => ({ lang: navigator.language, tz: Intl.DateTimeFormat().resolvedOptions().timeZone })"
        )
        print("Case B (KontrolAlt profile override):", js_data_b)
        await context_b.close()

if __name__ == "__main__":
    asyncio.run(main())
