"""Scrape UFC betting odds from fightodds.io via GraphQL."""

from __future__ import annotations

from datetime import date

from schemas.fightodds import (
    FightOddsDetail,
    FightOddsEvent,
    FightOddsFightStub,
    FightOddsFighter,
    SportsbookOffer,
)
from scrapers.browser_session import BrowserSession
from scrapers.fightodds.queries import (
    EVENT_FIGHTS_QUERY,
    EVENTS_PAGE_QUERY,
    FIGHT_ODDS_QUERY,
    FIGHTODDS_GQL_URL,
)

UFC_PROMOTION_SLUG = "ufc"
EVENTS_PAGE_SIZE = 10


class FightOddsScraper:
    def __init__(self, browser: BrowserSession | None = None, *, delay: float = 0.5):
        self._owns_browser = browser is None
        self.browser = browser or BrowserSession(delay=delay)
        if self._owns_browser:
            self.browser.start()

    def close(self) -> None:
        if self._owns_browser:
            self.browser.close()

    def __enter__(self) -> "FightOddsScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def gql(self, query: str, variables: dict) -> dict | None:
        payload = {"query": query, "variables": variables}
        result = self.browser.post_json(FIGHTODDS_GQL_URL, payload)
        if result is None:
            return None
        if "errors" in result:
            print(f"GraphQL errors: {result['errors']}")
            return None
        return result.get("data")

    def _paginate_events(
        self,
        *,
        date_gte: str | None,
        date_lt: str | None,
        order_by: str,
    ) -> list[FightOddsEvent]:
        events: list[FightOddsEvent] = []
        cursor: str | None = None

        while True:
            variables: dict = {
                "count": EVENTS_PAGE_SIZE,
                "cursor": cursor,
                "dateGte": date_gte,
                "dateLt": date_lt,
                "orderBy": order_by,
            }
            data = self.gql(EVENTS_PAGE_QUERY, variables)
            if data is None:
                break

            connection = data.get("allEvents") or {}
            for edge in connection.get("edges") or []:
                node = edge.get("node") or {}
                promotion = node.get("promotion") or {}
                if promotion.get("slug") != UFC_PROMOTION_SLUG:
                    continue
                date_str = node.get("date")
                if not date_str:
                    continue
                events.append(
                    FightOddsEvent(
                        pk=node["pk"],
                        slug=node["slug"],
                        name=node["name"],
                        event_date=date.fromisoformat(date_str),
                        promotion_slug=promotion["slug"],
                        promotion_name=promotion.get("shortName"),
                        venue=node.get("venue") or None,
                        city=node.get("city") or None,
                    )
                )

            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break

        return events

    def get_recent_ufc_events(self) -> list[FightOddsEvent]:
        today = date.today().isoformat()
        return self._paginate_events(date_gte=None, date_lt=today, order_by="-date")

    def get_upcoming_ufc_events(self) -> list[FightOddsEvent]:
        today = date.today().isoformat()
        return self._paginate_events(date_gte=today, date_lt=None, order_by="date")

    @staticmethod
    def _parse_fighter(node: dict | None) -> FightOddsFighter:
        node = node or {}
        return FightOddsFighter(
            first_name=node.get("firstName") or "",
            last_name=node.get("lastName") or "",
            slug=node.get("slug"),
        )

    def get_event(self, event_pk: int) -> FightOddsEvent | None:
        data = self.gql(EVENT_FIGHTS_QUERY, {"eventPk": event_pk})
        if data is None:
            return None
        event = data.get("event")
        if not event:
            return None
        promotion = event.get("promotion") or {}
        date_str = event.get("date")
        if not date_str:
            return None
        return FightOddsEvent(
            pk=event["pk"],
            slug=event["slug"],
            name=event["name"],
            event_date=date.fromisoformat(date_str),
            promotion_slug=promotion.get("slug") or "",
            promotion_name=promotion.get("shortName"),
        )

    def get_fight_stubs_for_event(self, event_pk: int) -> list[FightOddsFightStub]:
        data = self.gql(EVENT_FIGHTS_QUERY, {"eventPk": event_pk})
        if data is None:
            return []

        event = data.get("event")
        if not event:
            return []

        stubs: list[FightOddsFightStub] = []
        fights = (event.get("fights") or {}).get("edges") or []
        for edge in fights:
            node = edge.get("node") or {}
            stubs.append(
                FightOddsFightStub(
                    pk=node["pk"],
                    slug=node["slug"],
                    order=node.get("order") or 0,
                    fighter_1=self._parse_fighter(node.get("fighter1")),
                    fighter_2=self._parse_fighter(node.get("fighter2")),
                    is_cancelled=bool(node.get("isCancelled")),
                    event_pk=event_pk,
                )
            )
        active = sum(1 for s in stubs if not s.is_cancelled)
        print(
            f"Scraping Fight Odds card pk={event_pk}: "
            f"{len(stubs)} fights ({active} active)",
            flush=True,
        )
        return stubs

    def get_fight_odds(self, fight_slug: str, *, progress: str | None = None) -> FightOddsDetail | None:
        if progress:
            print(f"{progress}: {fight_slug}", flush=True)

        data = self.gql(FIGHT_ODDS_QUERY, {"fightSlug": fight_slug})
        if data is None:
            return None

        table = data.get("fightOfferTable")
        if not table:
            return None

        offers: list[SportsbookOffer] = []
        for edge in (table.get("straightOffers") or {}).get("edges") or []:
            node = edge.get("node") or {}
            book = node.get("sportsbook") or {}
            o1 = node.get("outcome1") or {}
            o2 = node.get("outcome2") or {}
            offers.append(
                SportsbookOffer(
                    book_slug=book.get("slug") or "",
                    book_name=book.get("shortName") or book.get("slug") or "",
                    fighter_1_odds=o1.get("odds"),
                    fighter_2_odds=o2.get("odds"),
                    fighter_1_odds_open=o1.get("oddsOpen"),
                    fighter_2_odds_open=o2.get("oddsOpen"),
                )
            )

        return FightOddsDetail(
            fight_slug=fight_slug,
            fighter_1=self._parse_fighter(table.get("fighter1")),
            fighter_2=self._parse_fighter(table.get("fighter2")),
            best_odds_1=table.get("bestOdds1"),
            best_odds_2=table.get("bestOdds2"),
            offers=offers,
        )

    def get_odds_for_event(self, event_pk: int) -> list[FightOddsDetail]:
        details: list[FightOddsDetail] = []
        stubs = self.get_fight_stubs_for_event(event_pk)
        total = len(stubs)
        for i, stub in enumerate(stubs, start=1):
            if stub.is_cancelled:
                continue
            progress = f"  [{i}/{total}] Fight #{stub.order}"
            detail = self.get_fight_odds(stub.slug, progress=progress)
            if detail:
                details.append(detail)
        return details


def main() -> None:
    # Light smoke test: one known UFC card (minimizes API calls).
    test_event_pk = 8995
    with FightOddsScraper(delay=1.0) as scraper:
        event = scraper.get_event(test_event_pk)
        if event is None:
            print("Failed to load test event.")
            return
        print(f"Event: {event.name} ({event.url})")

        stubs = scraper.get_fight_stubs_for_event(event.pk)
        active = [s for s in stubs if not s.is_cancelled]
        print(f"Fights on card: {len(stubs)} ({len(active)} active)")

        if not active:
            return

        detail = scraper.get_fight_odds(active[0].slug)
        if detail is None:
            print("No odds returned.")
            return

        print(
            f"Sample: {detail.fighter_1.full_name} vs {detail.fighter_2.full_name} "
            f"— {len(detail.offers)} sportsbook offers"
        )
        for offer in detail.offers[:3]:
            print(
                f"  {offer.book_name}: "
                f"{offer.fighter_1_odds}/{offer.fighter_2_odds} "
                f"(open {offer.fighter_1_odds_open}/{offer.fighter_2_odds_open})"
            )


if __name__ == "__main__":
    main()
