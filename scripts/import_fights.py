"""Scrape UFC fights for each event in the DB and upsert them with per-round stats."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import (
    Event as EventModel,
    Fight as FightModel,
    FightRoundStats as FightRoundStatsModel,
    Fighter as FighterModel,
)
from schemas.fight import FightDetail, FightStub
from scrapers.browser_session import BrowserSession
from scrapers.ufcstats.fight_scraper import UFCStatsFightScraper


def resolve_fighter_id(
    session: Session, url: str | None, cache: dict[str, int]
) -> int | None:
    if not url:
        return None
    if url in cache:
        return cache[url]
    fighter_id = (
        session.query(FighterModel.id).filter(FighterModel.url == url).scalar()
    )
    if fighter_id is not None:
        cache[url] = fighter_id
    return fighter_id


def upsert_fight(
    session: Session,
    event_id: int,
    stub: FightStub,
    detail: FightDetail,
    fighter_cache: dict[str, int],
) -> tuple[FightModel | None, bool]:
    """Insert or update a Fight row keyed by url.

    Returns (fight, is_new). Returns (None, False) if a required fighter row
    cannot be resolved — caller treats this as a failure.
    """
    fighter_1_id = resolve_fighter_id(session, stub.fighter_1_url, fighter_cache)
    fighter_2_id = resolve_fighter_id(session, stub.fighter_2_url, fighter_cache)
    if fighter_1_id is None or fighter_2_id is None:
        missing = [
            url
            for url, fid in (
                (stub.fighter_1_url, fighter_1_id),
                (stub.fighter_2_url, fighter_2_id),
            )
            if fid is None
        ]
        print(
            f"  Missing fighter row(s) for {stub.url}: {missing}. "
            "Run import_fighters.py first.",
            flush=True,
        )
        return None, False

    winner_id = resolve_fighter_id(session, detail.fight.winner_url, fighter_cache)

    scorecard = (
        [s.model_dump() for s in detail.fight.scorecard]
        if detail.fight.scorecard
        else None
    )

    values = {
        "url": detail.fight.url,
        "event_id": event_id,
        "fighter_1_id": fighter_1_id,
        "fighter_2_id": fighter_2_id,
        "match_number": stub.match_number,
        "weight_class": detail.fight.weight_class or stub.weight_class,
        "winner_id": winner_id,
        "method": detail.fight.method,
        "finish_round": detail.fight.finish_round,
        "finish_time": detail.fight.finish_time,
        "time_format": detail.fight.time_format,
        "referee": detail.fight.referee,
        "scorecard": scorecard,
        "last_updated_at": datetime.now(timezone.utc),
    }

    existing = (
        session.query(FightModel).filter(FightModel.url == detail.fight.url).one_or_none()
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing, False

    fight = FightModel(**values)
    session.add(fight)
    return fight, True


def upsert_round_stats(
    session: Session,
    fight: FightModel,
    detail: FightDetail,
    fighter_cache: dict[str, int],
) -> None:
    """Upsert FightRoundStats by (fight_id, fighter_id, round_number)."""
    session.flush()  # ensure fight.id is populated for new rows

    existing: dict[tuple[int, int], FightRoundStatsModel] = {
        (rs.fighter_id, rs.round_number): rs for rs in fight.round_stats
    }

    for round_stats in detail.round_stats:
        fighter_id = resolve_fighter_id(
            session, round_stats.fighter_url, fighter_cache
        )
        if fighter_id is None:
            print(
                f"  Missing fighter row for round stats {round_stats.fighter_url}; "
                "skipping round.",
                flush=True,
            )
            continue

        stats_values = round_stats.model_dump(exclude={"fighter_url", "round_number"})

        key = (fighter_id, round_stats.round_number)
        if key in existing:
            row = existing[key]
            for field, value in stats_values.items():
                setattr(row, field, value)
        else:
            session.add(
                FightRoundStatsModel(
                    fight_id=fight.id,
                    fighter_id=fighter_id,
                    round_number=round_stats.round_number,
                    **stats_values,
                )
            )


def event_already_complete(
    session: Session, event_id: int, expected_fight_count: int
) -> bool:
    """An event is "complete" only when every expected fight has a result.

    A finished UFC bout always populates `method` on the detail page (e.g.
    "Decision - Unanimous", "KO/TKO", "Draw - Unanimous", "Could Not Continue").
    Upcoming/unfought fights leave `method` NULL, so they still get re-scraped
    on the next run.
    """
    if expected_fight_count <= 0:
        return False
    finished = (
        session.query(FightModel)
        .filter(
            FightModel.event_id == event_id,
            FightModel.method.isnot(None),
        )
        .count()
    )
    return finished >= expected_fight_count


def main() -> None:
    inserted = 0
    updated = 0
    skipped = 0
    failed = 0

    with BrowserSession() as browser, UFCStatsFightScraper(
        browser=browser
    ) as scraper, SessionLocal() as session:
        events = (
            session.query(EventModel).order_by(EventModel.date.desc()).all()
        )
        print(f"Importing fights for {len(events)} events", flush=True)

        for ev_idx, event in enumerate(events, start=1):
            print(
                f"\n=== [{ev_idx}/{len(events)}] {event.title} ({event.url}) ===",
                flush=True,
            )
            stubs = scraper.get_fight_stubs_for_event(event.url)
            if not stubs:
                print("  No fights found on event page.", flush=True)
                continue

            if event_already_complete(session, event.id, len(stubs)):
                print(
                    f"  Skipping (all {len(stubs)} fights already have results).",
                    flush=True,
                )
                skipped += len(stubs)
                continue

            fighter_cache: dict[str, int] = {}
            total = len(stubs)
            for i, stub in enumerate(stubs, start=1):
                progress = f"  [{i}/{total}] Fight #{stub.match_number}"
                try:
                    detail = scraper.get_fight_detail(stub.url, progress=progress)
                    if detail is None:
                        failed += 1
                        continue

                    fight, is_new = upsert_fight(
                        session, event.id, stub, detail, fighter_cache
                    )
                    if fight is None:
                        failed += 1
                        continue

                    upsert_round_stats(session, fight, detail, fighter_cache)
                    session.commit()

                    if is_new:
                        inserted += 1
                    else:
                        updated += 1
                except Exception as exc:
                    session.rollback()
                    failed += 1
                    print(f"  Failed to import {stub.url}: {exc}", flush=True)

    print(
        f"\nDone  |  inserted: {inserted}  updated: {updated}  "
        f"skipped: {skipped}  failed: {failed}"
    )


if __name__ == "__main__":
    main()
