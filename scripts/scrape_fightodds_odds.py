"""Scrape UFC per-sportsbook moneyline odds from fightodds.io and write JSON."""
from datetime import datetime, timezone
from pathlib import Path

from scrapers.fightodds_client import FightOddsClient
from scrapers.fightodds_scraper import FightOddsScraper

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "fightodds"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Starting Fight Odds UFC odds scrape...", flush=True)
    with FightOddsClient() as client:
        print("Connected to fightodds.io — scraping events...", flush=True)
        result = FightOddsScraper(client).scrape_all()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"scrape-{timestamp}.json"
    out_path.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(
        f"\nDone  |  events: {result.event_count}  "
        f"fights: {result.fight_count}  "
        f"offers: {result.offer_count}  "
        f"failures: {len(result.failures)}",
        flush=True,
    )
    print(f"Wrote {out_path}", flush=True)

    if result.failures:
        print("\nFailures:", flush=True)
        for msg in result.failures[:20]:
            print(f"  - {msg}", flush=True)
        if len(result.failures) > 20:
            print(f"  ... and {len(result.failures) - 20} more", flush=True)


if __name__ == "__main__":
    main()
