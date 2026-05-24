"""Scrape UFC events and upsert them into the database."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Event as EventModel
from schemas.event import Event as EventSchema
from scrapers.ufcstats.event_scraper import UFCStatsEventScraper


def upsert_event(session: Session, scraped_event: EventSchema) -> EventModel:
    existing_event = (
        session.query(EventModel)
        .filter(EventModel.url == scraped_event.url)
        .one_or_none()
    )

    now = datetime.now(timezone.utc)

    if existing_event:
        existing_event.title = scraped_event.title
        existing_event.date = scraped_event.date
        existing_event.location = scraped_event.location
        existing_event.organizer = scraped_event.organizer
        existing_event.last_updated_at = now
        return existing_event

    event = EventModel(
        url=scraped_event.url,
        title=scraped_event.title,
        date=scraped_event.date,
        location=scraped_event.location,
        organizer=scraped_event.organizer,
        last_updated_at=now,
    )
    session.add(event)
    return event


def main() -> None:
    scraper = UFCStatsEventScraper()
    scraped_events = scraper.get_all_events()

    inserted = 0
    updated = 0

    with SessionLocal() as session:
        for scraped_event in scraped_events:
            existing = (
                session.query(EventModel.id)
                .filter(EventModel.url == scraped_event.url)
                .one_or_none()
            )
            upsert_event(session, scraped_event)
            if existing:
                updated += 1
            else:
                inserted += 1

        session.commit()

    print(f"Scraped {len(scraped_events)} events  |  inserted: {inserted}  updated: {updated}")


if __name__ == "__main__":
    main()
