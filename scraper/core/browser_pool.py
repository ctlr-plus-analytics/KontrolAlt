"""Per-worker-process Chromium browser pool with persistent event loop."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class WorkerBrowserPool:
    """Keeps one Chromium process alive per Celery worker process.

    Celery prefork workers are long-lived — starting a fresh Chromium
    binary for every scrape task wastes 2–5 s per channel.  This pool
    launches Chromium once at worker startup, then creates lightweight
    BrowserContexts (one per task) from the shared browser process.

    Proxy is set at context creation time so different tasks can use
    different proxy endpoints from the same browser process.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright = None  # playwright.async_api.Playwright
        self._browser = None    # playwright.async_api.Browser

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Return the persistent event loop, creating it if needed."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def run(self, coro):
        """Run *coro* in the persistent event loop (blocking)."""
        return self.get_loop().run_until_complete(coro)

    async def ensure_browser(self):
        """Return the shared Chromium browser, (re-)launching if needed.

        Returns None when called from a loop that is not the pool's
        persistent loop (e.g. tests using asyncio.run), signalling
        launch_browser() to fall back to a fresh browser launch.
        """
        # If we're running in a different loop than the pool's, don't
        # hand out the pool browser — it was created in (or for) a
        # different loop and would be unsafe to use here.
        try:
            current_loop = asyncio.get_running_loop()
            if self._loop is not None and current_loop is not self._loop:
                return None
        except RuntimeError:
            pass

        try:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
        except Exception:
            self._browser = None
            self._playwright = None

        await self._launch()
        return self._browser

    def reset(self) -> None:
        """Discard all state inherited across a fork boundary.

        Must be called at the top of worker_process_init before any async
        work.  After fork the child process inherits the parent's event loop
        and browser handles, both of which are unusable in the child.
        """
        self._loop = None
        self._browser = None
        self._playwright = None

    def warm_up(self) -> None:
        """Pre-launch Chromium synchronously. Call from worker_process_init."""
        try:
            self.run(self.ensure_browser())
            logger.info("BrowserPool: Chromium pre-warmed")
        except Exception as exc:
            logger.warning(
                "BrowserPool: pre-warm failed (will retry on first task): %s", exc
            )

    def shutdown(self) -> None:
        """Close browser and Playwright transport. Call from worker shutdown."""
        try:
            self.get_loop().run_until_complete(self._close())
            logger.info("BrowserPool: shut down")
        except Exception as exc:
            logger.debug("BrowserPool: shutdown error: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _launch(self) -> None:
        from playwright.async_api import async_playwright
        from core.browser import _resolve_headless_mode

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
            self._browser = None

        headless = _resolve_headless_mode()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            # Proxy intentionally omitted at browser level — set per-context
            # so each task can use a different proxy endpoint.
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                # Residential exit nodes sometimes run SSL inspection software.
                # Without this flag, their MITM certificate causes ERR_SSL_PROTOCOL_ERROR
                # and the scrape fails entirely. Acceptable for a read-only scraping context.
                "--ignore-certificate-errors",
                # Containers (Docker/Render) have a small /dev/shm (64 MB default).
                # Without this flag Chromium uses shared memory for rendering and crashes.
                "--disable-dev-shm-usage",
                # Render (and most container runtimes) drop the Linux SYS_ADMIN capability
                # that Chromium's process sandbox requires. Without this flag Chromium
                # silently fails to launch in those environments.
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        logger.info("BrowserPool: Chromium launched (headless=%s)", headless)

    async def _close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


worker_pool = WorkerBrowserPool()
