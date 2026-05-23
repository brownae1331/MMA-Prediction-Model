"""Scrape per-sportsbook UFC moneyline odds from fightodds.io via GraphQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Literal

from schemas.fightodds import (
    EventOddsCard,
    EventStub,
    FightOddsCard,
    FightOddsScrapeResult,
    FighterRef,
    SportsbookOdds,
)
from scrapers.fightodds_client import FightOddsClient, FightOddsGraphQLError
from scrapers.fightodds_queries import (
    EVENT_CARD_LIST_QUERY,
    EVENT_FIGHTS_QUERY,
    FIGHT_ODDS_QUERY,
)

UFC_PROMOTION_SLUG = "ufc"
EVENTS_PER_PAGE = 10

# Set to an int (e.g. 2) to cap pagination during development; None = all pages.
MAX_EVENT_PAGES: int | None = 2


class FightOddsScraper:
    def __init__(self, client: FightOddsClient):
        self.client = client

    def iter_ufc_events(
        self, *, mode: Literal["recent", "upcoming"]
    ) -> Iterator[EventStub]:
        today = date.today().isoformat()
        if mode == "recent":
            date_gte = None
            date_lt = today
            order_by = "-date"
        else:
            date_gte = today
            date_lt = None
            order_by = "date"

        cursor: str | None = None
        page_num = 0

        while True:
            page_num += 1
            if MAX_EVENT_PAGES is not None and page_num > MAX_EVENT_PAGES:
                break

            variables = {
                "count": EVENTS_PER_PAGE,
                "cursor": cursor,
                "dateGte": date_gte,
                "dateLt": date_lt,
                "orderBy": order_by,
            }
            data = self.client.gql(EVENT_CARD_LIST_QUERY, variables)
            connection = data.get("allEvents") or {}
            edges = connection.get("edges") or []

            for edge in edges:
                node = edge.get("node") or {}
                promotion = node.get("promotion") or {}
                if promotion.get("slug") != UFC_PROMOTION_SLUG:
                    continue
                yield EventStub(
                    pk=node["pk"],
                    slug=node["slug"],
                    name=node["name"],
                    date=date.fromisoformat(node["date"]),
                    promotion_slug=promotion["slug"],
                )

            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break

    def scrape_fight_odds(self, fight_slug: str) -> list[SportsbookOdds]:
        data = self.client.gql(FIGHT_ODDS_QUERY, {"fightSlug": fight_slug})
        table = data.get("fightOfferTable") or {}
        offers: list[SportsbookOdds] = []

        for edge in (table.get("straightOffers") or {}).get("edges") or []:
            node = edge.get("node") or {}
            sportsbook = node.get("sportsbook") or {}
            outcome1 = node.get("outcome1") or {}
            outcome2 = node.get("outcome2") or {}
            offers.append(
                SportsbookOdds(
                    slug=sportsbook.get("slug", ""),
                    short_name=sportsbook.get("shortName", ""),
                    fighter_1_odds=outcome1.get("odds"),
                    fighter_2_odds=outcome2.get("odds"),
                    fighter_1_odds_open=outcome1.get("oddsOpen"),
                    fighter_2_odds_open=outcome2.get("oddsOpen"),
                )
            )
        return offers

    def scrape_event(self, stub: EventStub) -> EventOddsCard:
        scraped_at = datetime.now(timezone.utc)
        data = self.client.gql(EVENT_FIGHTS_QUERY, {"eventPk": stub.pk})
        event = data.get("event")
        if not event:
            raise FightOddsGraphQLError(f"eventByPk returned no event for pk={stub.pk}")

        fights: list[FightOddsCard] = []
        edges = (event.get("fights") or {}).get("edges") or []

        for fight_edge in edges:
            node = fight_edge.get("node") or {}
            if node.get("isCancelled"):
                continue

            fight_slug = node.get("slug")
            if not fight_slug:
                continue

            f1 = node.get("fighter1") or {}
            f2 = node.get("fighter2") or {}
            fighter_1 = FighterRef(
                first_name=f1.get("firstName", ""),
                last_name=f1.get("lastName", ""),
                slug=f1.get("slug", ""),
            )
            fighter_2 = FighterRef(
                first_name=f2.get("firstName", ""),
                last_name=f2.get("lastName", ""),
                slug=f2.get("slug", ""),
            )

            offers = self.scrape_fight_odds(fight_slug)
            fights.append(
                FightOddsCard(
                    fight_pk=node["pk"],
                    fight_slug=fight_slug,
                    fight_order=node.get("order"),
                    fighter_1=fighter_1,
                    fighter_2=fighter_2,
                    offers=offers,
                    scraped_at=scraped_at,
                )
            )

        promotion = event.get("promotion") or {}
        return EventOddsCard(
            event_pk=event["pk"],
            event_slug=event.get("slug", stub.slug),
            name=event.get("name", stub.name),
            date=date.fromisoformat(event["date"]),
            promotion_slug=promotion.get("slug", stub.promotion_slug),
            fights=fights,
            scraped_at=scraped_at,
        )

    def scrape_events_for_mode(
        self,
        mode: Literal["recent", "upcoming"],
        failures: list[str],
    ) -> list[EventOddsCard]:
        results: list[EventOddsCard] = []
        stubs = list(self.iter_ufc_events(mode=mode))
        total = len(stubs)
        label = "recent" if mode == "recent" else "upcoming"

        print(f"\n=== {label.upper()} UFC events: {total} ===", flush=True)

        for idx, stub in enumerate(stubs, start=1):
            print(
                f"  [{idx}/{total}] {stub.name} ({stub.date}) pk={stub.pk}",
                flush=True,
            )
            try:
                card = self.scrape_event(stub)
                fight_count = len(card.fights)
                offer_count = sum(len(f.offers) for f in card.fights)
                print(
                    f"    {fight_count} fights, {offer_count} sportsbook offers",
                    flush=True,
                )
                results.append(card)
            except FightOddsGraphQLError as exc:
                msg = f"{label} event pk={stub.pk} ({stub.name}): {exc}"
                print(f"    FAILED: {exc}", flush=True)
                failures.append(msg)
            except Exception as exc:
                msg = f"{label} event pk={stub.pk} ({stub.name}): {exc}"
                print(f"    FAILED: {exc}", flush=True)
                failures.append(msg)

        return results

    def scrape_all(self) -> FightOddsScrapeResult:
        scraped_at = datetime.now(timezone.utc)
        failures: list[str] = []

        recent = self.scrape_events_for_mode("recent", failures)
        upcoming = self.scrape_events_for_mode("upcoming", failures)

        return FightOddsScrapeResult(
            scraped_at=scraped_at,
            recent_events=recent,
            upcoming_events=upcoming,
            failures=failures,
        )

    def scrape_single_event(self, event_pk: int) -> EventOddsCard:
        """Scrape one event by primary key (for smoke tests)."""
        data = self.client.gql(
            EVENT_FIGHTS_QUERY,
            {"eventPk": event_pk},
        )
        event = data.get("event")
        if not event:
            raise FightOddsGraphQLError(f"No event for pk={event_pk}")
        promotion = event.get("promotion") or {}
        stub = EventStub(
            pk=event["pk"],
            slug=event.get("slug", ""),
            name=event.get("name", ""),
            date=date.fromisoformat(event["date"]),
            promotion_slug=promotion.get("slug", ""),
        )
        return self.scrape_event(stub)
