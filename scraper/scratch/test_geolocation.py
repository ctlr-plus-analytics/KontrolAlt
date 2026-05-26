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
        context = await browser.new_context(
            permissions=["geolocation"]
        )
        page = await context.new_page()
        # Enable permissions and retrieve geolocation via JS
        await page.goto("https://httpbin.org/ip") # warmup
        
        geo = await page.evaluate("""
            async () => {
                return new Promise((resolve) => {
                    navigator.geolocation.getCurrentPosition(
                        (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
                        (err) => resolve({ error: err.message })
                    );
                });
            }
        """)
        print("Browser reported geolocation:", geo)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
