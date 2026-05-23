"""Playwright-backed GraphQL client for fightodds.io."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from playwright.sync_api import APIResponse, Browser, BrowserContext, Page, sync_playwright

from scrapers.browser_session import BrowserSession

GQL_URL = "https://api.fightodds.io/gql"
SITE_URL = "https://fightodds.io/"


class FightOddsGraphQLError(Exception):
    """Raised when the Fight Odds API returns GraphQL or HTTP errors."""


class FightOddsClient:
    """Bootstrap Chromium, pass Cloudflare, then POST to the GraphQL API."""

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        delay: float | None = None,
        user_agent: str | None = None,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.delay = delay
        if self.delay is None:
            env_delay = os.environ.get("FIGHTODDS_DELAY")
            self.delay = float(env_delay) if env_delay else 0.4
        self.user_agent = user_agent or BrowserSession.DEFAULT_UA

        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> "FightOddsClient":
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
        self._page.goto(SITE_URL, timeout=self.timeout_ms, wait_until="domcontentloaded")
        self._page.wait_for_timeout(1500)

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

    def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query and return the `data` payload."""
        if self._context is None:
            self.start()
        assert self._context is not None

        payload = {"query": query, "variables": variables or {}}
        last_exc: Exception | None = None

        max_attempts = 4
        for attempt in range(max_attempts):
            time.sleep(self.delay)
            try:
                response = self._context.request.post(
                    GQL_URL,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout_ms,
                )
                if response.status == 429:
                    wait = 2.0 * (attempt + 1)
                    if attempt < max_attempts - 1:
                        time.sleep(wait)
                        continue
                    raise FightOddsGraphQLError(
                        f"HTTP 429 after {max_attempts} attempts: rate limited"
                    )
                body = self._parse_response(response)
                if "errors" in body and body["errors"]:
                    messages = "; ".join(
                        err.get("message", str(err)) for err in body["errors"]
                    )
                    raise FightOddsGraphQLError(messages)
                if "data" not in body:
                    raise FightOddsGraphQLError(f"Missing data in response: {body}")
                return body["data"]
            except FightOddsGraphQLError as exc:
                if "429" in str(exc) and attempt < max_attempts - 1:
                    time.sleep(2.0 * (attempt + 1))
                    last_exc = exc
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise FightOddsGraphQLError(str(exc)) from exc

        raise FightOddsGraphQLError(str(last_exc) if last_exc else "Unknown GQL error")

    @staticmethod
    def _parse_response(response: APIResponse) -> dict[str, Any]:
        if not response.ok:
            raise FightOddsGraphQLError(
                f"HTTP {response.status}: {response.text()[:500]}"
            )
        return response.json()
