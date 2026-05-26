import asyncio
from camoufox.async_api import AsyncCamoufox
from core.browser import _parse_proxy_settings
from core.proxy import get_random_proxy

async def main():
    proxy = get_random_proxy()
    proxy_settings = _parse_proxy_settings(proxy)
    
    async with AsyncCamoufox(
        headless=True,
        proxy=proxy_settings,
        geoip=True,
        os="windows",
    ) as browser:
        # Test 1: viewport=None
        context1 = await browser.new_context(viewport=None)
        page1 = await context1.new_page()
        await page1.goto("https://httpbin.org/ip")
        v1 = await page1.evaluate("() => [window.innerWidth, window.innerHeight]")
        print("viewport=None inner size:", v1)
        await context1.close()
        
        # Test 2: no viewport parameter
        context2 = await browser.new_context()
        page2 = await context2.new_page()
        await page2.goto("https://httpbin.org/ip")
        v2 = await page2.evaluate("() => [window.innerWidth, window.innerHeight]")
        print("default viewport inner size:", v2)
        await context2.close()

if __name__ == "__main__":
    asyncio.run(main())
