"""Shared Playwright session for UFCStats scrapers.

UFCStats sits behind Cloudflare which blocks plain HTTP clients. This wrapper
launches a real Chromium browser so the JS challenge is solved automatically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


@dataclass
class PageResponse:
    """Minimal Response-like object so parsers can keep reading `.text`."""

    text: str
    status_code: int = 200


class BrowserSession:
    """Reusable headless Chromium session.

    Use as a context manager so the browser shuts down cleanly:

        with BrowserSession() as session:
            html = session.get(url).text
    """

    DEFAULT_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        delay: float = 0.25,
        user_agent: str | None = None,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.delay = delay
        self.user_agent = user_agent or self.DEFAULT_UA

        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._pw is not None:
            return
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(user_agent=self.user_agent)
        self._page = self._context.new_page()

    def close(self) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        finally:
            self._pw = None
            self._browser = None
            self._context = None
            self._page = None

    def get(self, url: str) -> PageResponse | None:
        if self._page is None:
            self.start()
        assert self._page is not None

        time.sleep(self.delay)
        try:
            response = self._page.goto(
                url, timeout=self.timeout_ms, wait_until="domcontentloaded"
            )
        except Exception as exc:
            print(f"Browser navigation failed for {url}: {exc}")
            return None

        html = self._page.content()
        if "Checking your browser" in html or "Just a moment" in html:
            try:
                self._page.wait_for_timeout(3000)
                html = self._page.content()
            except Exception:
                pass

        status = response.status if response else 200
        return PageResponse(text=html, status_code=status)
