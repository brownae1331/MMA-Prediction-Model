"""Scrape UFC fighters and upsert them into the database."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import Fighter as FighterModel
from schemas.fighter import Fighter as FighterSchema
from scrapers.fighter_scraper import UFCStatsFighterScraper


def upsert_fighter(session: Session, scraped: FighterSchema) -> tuple[FighterModel, bool]:
    """Insert or update a fighter row keyed by url.

    Returns the model and a bool that is True when a new row was inserted.
    """
    existing = (
        session.query(FighterModel)
        .filter(FighterModel.url == scraped.url)
        .one_or_none()
    )

    values = {
        "url": scraped.url,
        "name": scraped.name,
        "nickname": scraped.nickname,
        "height": scraped.height,
        "weight": scraped.weight,
        "reach": scraped.reach,
        "stance": scraped.stance,
        "dob": scraped.dob,
        "slpm": scraped.SLpM,
        "str_acc": scraped.StrAcc,
        "sapm": scraped.SApM,
        "str_def": scraped.StrDef,
        "td_avg": scraped.TDAvg,
        "td_acc": scraped.TDAcc,
        "td_def": scraped.TDDef,
        "sub_avg": scraped.SubAvg,
        "last_updated_at": datetime.now(timezone.utc),
    }

    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing, False

    fighter = FighterModel(**values)
    session.add(fighter)
    return fighter, True


def main() -> None:
    scraper = UFCStatsFighterScraper()
    scraped_fighters = scraper.get_all_fighters()

    inserted = 0
    updated = 0
    failed = 0

    with SessionLocal() as session:
        for scraped in scraped_fighters:
            try:
                _, is_new = upsert_fighter(session, scraped)
                session.commit()
            except Exception as exc:
                session.rollback()
                failed += 1
                print(f"Failed to upsert {scraped.url}: {exc}")
                continue

            if is_new:
                inserted += 1
            else:
                updated += 1

    print(
        f"Scraped {len(scraped_fighters)} fighters  |  "
        f"inserted: {inserted}  updated: {updated}  failed: {failed}"
    )


if __name__ == "__main__":
    main()
