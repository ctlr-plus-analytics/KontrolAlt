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
        humanize=True,
    ) as browser:
        # Create context without any manual fingerprint parameters
        context = await browser.new_context(
            permissions=["geolocation"]
        )
        page = await context.new_page()
        await page.goto("https://httpbin.org/ip") # warmup
        
        info = await page.evaluate("""
            () => ({
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                languages: navigator.languages,
                screen: { w: screen.width, h: screen.height },
                window: { w: window.outerWidth, h: window.outerHeight },
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            })
        """)
        print("Native Camoufox Info:")
        for k, v in info.items():
            print(f"  {k}: {v}")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
