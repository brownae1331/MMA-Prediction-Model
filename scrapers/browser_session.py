"""Shared Playwright session for UFCStats scrapers.

UFCStats sits behind Cloudflare which blocks plain HTTP clients. This wrapper
launches a real Chromium browser so the JS challenge is solved automatically.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

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
        self._fightodds_warmed = False

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
            self._fightodds_warmed = False

    def warm_fightodds(self) -> bool:
        """Visit fightodds.io so Cloudflare allows api.fightodds.io/gql requests."""
        if self._fightodds_warmed:
            return True
        response = self.get("https://fightodds.io/")
        if response is None:
            return False
        self._fightodds_warmed = True
        return True

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST JSON via the browser context (bypasses Cloudflare on fightodds.io)."""
        if self._context is None:
            self.start()
        assert self._context is not None

        if "fightodds.io" in url and not self._fightodds_warmed:
            if not self.warm_fightodds():
                return None

        max_attempts = 4
        for attempt in range(max_attempts):
            time.sleep(self.delay * (attempt + 1))
            try:
                response = self._context.request.post(
                    url,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout_ms,
                )
            except Exception as exc:
                print(f"Browser POST failed for {url}: {exc}")
                return None

            if response.status == 429 and attempt < max_attempts - 1:
                wait_s = 2 ** (attempt + 1)
                print(f"Rate limited (429), retrying in {wait_s}s...", flush=True)
                time.sleep(wait_s)
                continue

            if response.status >= 400:
                print(f"Browser POST {url} returned status {response.status}")
                return None

            break
        else:
            return None

        try:
            return response.json()
        except Exception as exc:
            print(f"Failed to parse JSON from {url}: {exc}")
            return None

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
