# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A data pipeline that scrapes UFC data (fighter stats, events, fight results with per-round stats, and betting odds) and stores it in PostgreSQL. The eventual goal is a fight-outcome prediction model; currently only the ingestion layer exists.

## Setup & commands

```bash
docker compose up -d                 # start PostgreSQL (user/pass/db = mma/mma/mma_prediction on :5432)
pip install -r requirements.txt
playwright install chromium          # scrapers drive a real Chromium, not plain HTTP
cp .env.example .env                 # provides DATABASE_URL; db/database.py raises if unset
python -m scripts.init_db            # create all tables from db/models.py
```

**Run scripts as modules from the repo root** (`python -m scripts.import_fights`), never `python scripts/import_fights.py`. Scripts use absolute imports (`from db.database import ...`), so the repo root must be on `sys.path`; the `-m` form does this, the direct path form does not.

### Ingestion order matters

Foreign keys force this sequence on a fresh DB:

```bash
python -m scripts.import_fighters              # fighters first
python -m scripts.import_events                # then events
python -m scripts.import_fights                # fights link to existing fighters + events
python -m scripts.import_fightodds_odds        # odds link to existing fights
```

`import_fights` looks up fighters by URL and **skips** any fight whose fighters aren't already in the DB. `import_fightodds_odds` matches against existing `fights` rows and silently drops unmatched ones. Running them out of order produces missing data, not errors.

There are no tests, linter, or formatter configured. Each `scrapers/*/*_scraper.py` has a `__main__` smoke test (e.g. `python -m scrapers.fightodds.scraper`) that hits the live site with minimal requests.

## Architecture

Three layers, each a top-level package:

- **`scrapers/`** — fetch + parse raw HTML/GraphQL into Pydantic schemas. Knows nothing about the DB.
- **`schemas/`** — Pydantic models = the scraper output contract (e.g. `FightDetail`, `FightOddsEvent`). Distinct from DB models.
- **`db/`** — SQLAlchemy ORM models (`db/models.py`) + engine/session (`db/database.py`).
- **`scripts/`** — orchestration: drive a scraper, then **upsert** Pydantic schemas into SQLAlchemy models. This is the only layer that bridges schemas → DB.

Data flows one way: `scrapers → schemas → scripts → db`. Keep DB concerns out of scrapers and scraping concerns out of `db/`.

### Two data sources

- **ufcstats.com** — HTML scraped with BeautifulSoup (`scrapers/ufcstats/`). Source of fighters, events, fight results, and per-round stats.
- **fightodds.io** — queried via its GraphQL API (`scrapers/fightodds/`, queries in `queries.py`). Source of per-sportsbook betting odds.

### Cloudflare / BrowserSession

Both sites sit behind Cloudflare and block plain HTTP clients, so all fetching goes through `scrapers/browser_session.py` (`BrowserSession`), a Playwright Chromium wrapper. `.get()` returns a `requests`-like `PageResponse` so BeautifulSoup parsers are unchanged. For fightodds, `post_json()` first calls `warm_fightodds()` (visits the site so Cloudflare allows the API POST) and retries 429s with backoff.

Scrapers take an optional `browser=` argument: pass a shared `BrowserSession` to reuse one Chromium across scrapers (what the import scripts do), or pass nothing and the scraper owns/closes its own. Always use these as context managers.

### Joining the two sources

fightodds has no UFCStats IDs, so `scrapers/fightodds/matching.py` links them:
1. By `fightodds_slug` if the fight was already matched.
2. Otherwise by event date + a normalized, accent-stripped fighter-name pair (`normalize_name`, order-independent via `frozenset`).

On a successful name match it **backfills** `fights.fightodds_slug` and `events.fightodds_event_pk` so subsequent runs hit the fast slug path.

### Upsert & idempotency conventions

Every importer is re-runnable. Rows are keyed by a natural unique column (`url`, or composite `UniqueConstraint`s in `db/models.py`): existing rows are updated in place, new ones inserted. `import_fights` and `import_fightodds_odds` commit per-fight and `rollback()` on exception so one bad fight doesn't lose the batch. `import_fights` also skips an event entirely once every fight on it has a non-null `method` (i.e. all results are in), so re-runs only re-scrape unfinished cards.
