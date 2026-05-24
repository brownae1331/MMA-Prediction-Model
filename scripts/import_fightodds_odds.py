"""Scrape Fight Odds per-book lines and upsert into the database."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import Bookmaker as BookmakerModel
from db.models import Fight as FightModel
from db.models import FightOdds as FightOddsModel
from schemas.fightodds import FightOddsDetail, FightOddsEvent
from scrapers.browser_session import BrowserSession
from scrapers.fightodds.matching import normalize_name, resolve_fight
from scrapers.fightodds.scraper import FightOddsScraper


def upsert_bookmaker(session: Session, slug: str, name: str, cache: dict[str, int]) -> int:
    if slug in cache:
        return cache[slug]
    existing = (
        session.query(BookmakerModel).filter(BookmakerModel.slug == slug).one_or_none()
    )
    if existing is not None:
        if existing.name != name:
            existing.name = name
        cache[slug] = existing.id
        return existing.id

    bookmaker = BookmakerModel(slug=slug, name=name)
    session.add(bookmaker)
    session.flush()
    cache[slug] = bookmaker.id
    return bookmaker.id


def _fighter_ids_for_offer(
    fight: FightModel,
    detail: FightOddsDetail,
) -> tuple[int, int]:
    """Map Fight Odds outcome1/2 to DB fighter corners by name."""

    def corner_id(fo_name: str) -> int | None:
        key = normalize_name(fo_name)
        if key == normalize_name(fight.fighter_1.name):
            return fight.fighter_1_id
        if key == normalize_name(fight.fighter_2.name):
            return fight.fighter_2_id
        return None

    f1_id = corner_id(detail.fighter_1.full_name)
    f2_id = corner_id(detail.fighter_2.full_name)
    if f1_id is not None and f2_id is not None:
        return f1_id, f2_id
    return fight.fighter_1_id, fight.fighter_2_id


def upsert_fight_odds_for_offer(
    session: Session,
    fight: FightModel,
    fighter_id: int,
    bookmaker_id: int,
    american_odds: int | None,
    american_odds_open: int | None,
    captured_at: datetime,
) -> bool:
    """Returns True if a new row was inserted."""
    existing = (
        session.query(FightOddsModel)
        .filter(
            FightOddsModel.fight_id == fight.id,
            FightOddsModel.bookmaker_id == bookmaker_id,
            FightOddsModel.fighter_id == fighter_id,
        )
        .one_or_none()
    )
    if existing:
        existing.american_odds = american_odds
        existing.american_odds_open = american_odds_open
        existing.captured_at = captured_at
        existing.source = "fightodds"
        return False

    session.add(
        FightOddsModel(
            fight_id=fight.id,
            bookmaker_id=bookmaker_id,
            fighter_id=fighter_id,
            american_odds=american_odds,
            american_odds_open=american_odds_open,
            captured_at=captured_at,
            source="fightodds",
        )
    )
    return True


def upsert_offers(
    session: Session,
    fight: FightModel,
    detail: FightOddsDetail,
    bookmaker_cache: dict[str, int],
    captured_at: datetime,
) -> tuple[int, int]:
    """Upsert all sportsbook offers for a fight. Returns (inserted, updated)."""
    fighter_1_id, fighter_2_id = _fighter_ids_for_offer(fight, detail)
    inserted = 0
    updated = 0

    for offer in detail.offers:
        if not offer.book_slug:
            continue
        bookmaker_id = upsert_bookmaker(
            session, offer.book_slug, offer.book_name, bookmaker_cache
        )
        for fighter_id, odds, odds_open in (
            (fighter_1_id, offer.fighter_1_odds, offer.fighter_1_odds_open),
            (fighter_2_id, offer.fighter_2_odds, offer.fighter_2_odds_open),
        ):
            if odds is None and odds_open is None:
                continue
            is_new = upsert_fight_odds_for_offer(
                session,
                fight,
                fighter_id,
                bookmaker_id,
                odds,
                odds_open,
                captured_at,
            )
            if is_new:
                inserted += 1
            else:
                updated += 1

    return inserted, updated


def collect_events(
    scraper: FightOddsScraper,
    *,
    upcoming_only: bool,
    recent_only: bool,
    event_pk: int | None,
) -> list[FightOddsEvent]:
    if event_pk is not None:
        fo_event = scraper.get_event(event_pk)
        if fo_event is None:
            return []
        return [fo_event]

    events: list[FightOddsEvent] = []
    if not recent_only:
        events.extend(scraper.get_upcoming_ufc_events())
    if not upcoming_only:
        events.extend(scraper.get_recent_ufc_events())

    seen: dict[int, FightOddsEvent] = {}
    for event in events:
        seen[event.pk] = event
    return list(seen.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Fight Odds into the database")
    parser.add_argument("--upcoming-only", action="store_true")
    parser.add_argument("--recent-only", action="store_true")
    parser.add_argument("--limit-events", type=int, default=None)
    parser.add_argument("--event-pk", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inserted = 0
    updated = 0
    unmatched = 0
    skipped_cancelled = 0
    failed = 0

    with BrowserSession(delay=1.0) as browser, FightOddsScraper(
        browser=browser
    ) as scraper, SessionLocal() as session:
        events = collect_events(
            scraper,
            upcoming_only=args.upcoming_only,
            recent_only=args.recent_only,
            event_pk=args.event_pk,
        )
        if args.limit_events is not None:
            events = events[: args.limit_events]

        print(f"Importing odds for {len(events)} Fight Odds UFC events", flush=True)
        captured_at = datetime.now(timezone.utc)
        bookmaker_cache: dict[str, int] = {}

        for ev_idx, fo_event in enumerate(events, start=1):
            label = fo_event.name if fo_event.name else f"pk={fo_event.pk}"
            print(f"\n=== [{ev_idx}/{len(events)}] {label} ===", flush=True)

            stubs = scraper.get_fight_stubs_for_event(fo_event.pk)
            if not stubs:
                print("  No fights found.", flush=True)
                continue

            total = len(stubs)
            for i, stub in enumerate(stubs, start=1):
                if stub.is_cancelled:
                    skipped_cancelled += 1
                    continue

                progress = f"  [{i}/{total}] Fight #{stub.order}"
                try:
                    detail = scraper.get_fight_odds(stub.slug, progress=progress)
                    if detail is None:
                        failed += 1
                        continue

                    fight = resolve_fight(session, fo_event, stub)
                    if fight is None:
                        unmatched += 1
                        print(
                            f"  No DB match for {stub.fighter_1.full_name} vs "
                            f"{stub.fighter_2.full_name} ({stub.slug})",
                            flush=True,
                        )
                        continue

                    ins, upd = upsert_offers(
                        session, fight, detail, bookmaker_cache, captured_at
                    )
                    session.commit()
                    inserted += ins
                    updated += upd
                    print(
                        f"  Imported {detail.fighter_1.full_name} vs "
                        f"{detail.fighter_2.full_name}: "
                        f"{ins} new, {upd} updated ({len(detail.offers)} books)",
                        flush=True,
                    )
                except Exception as exc:
                    session.rollback()
                    failed += 1
                    print(f"  Failed {stub.slug}: {exc}", flush=True)

    print(
        f"\nDone  |  odds inserted: {inserted}  updated: {updated}  "
        f"unmatched fights: {unmatched}  cancelled skipped: {skipped_cancelled}  "
        f"failed: {failed}"
    )


if __name__ == "__main__":
    main()
