"""Pydantic schemas for Fight Odds scrape results."""

from datetime import date, datetime

from pydantic import BaseModel, Field


def american_to_decimal(odds: int) -> float:
    """Convert American moneyline odds to decimal odds."""
    if odds > 0:
        return odds / 100 + 1
    return 100 / abs(odds) + 1


class FighterRef(BaseModel):
    first_name: str
    last_name: str
    slug: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class SportsbookOdds(BaseModel):
    slug: str
    short_name: str
    fighter_1_odds: int | None = None
    fighter_2_odds: int | None = None
    fighter_1_odds_open: int | None = None
    fighter_2_odds_open: int | None = None


class FightOddsCard(BaseModel):
    fight_pk: int
    fight_slug: str
    fight_order: int | None = None
    fighter_1: FighterRef
    fighter_2: FighterRef
    offers: list[SportsbookOdds] = Field(default_factory=list)
    scraped_at: datetime


class EventOddsCard(BaseModel):
    event_pk: int
    event_slug: str
    name: str
    date: date
    promotion_slug: str
    fights: list[FightOddsCard] = Field(default_factory=list)
    scraped_at: datetime


class EventStub(BaseModel):
    """Lightweight event row from paginated event listing."""

    pk: int
    slug: str
    name: str
    date: date
    promotion_slug: str


class FightOddsScrapeResult(BaseModel):
    scraped_at: datetime
    recent_events: list[EventOddsCard] = Field(default_factory=list)
    upcoming_events: list[EventOddsCard] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)

    @property
    def event_count(self) -> int:
        return len(self.recent_events) + len(self.upcoming_events)

    @property
    def fight_count(self) -> int:
        return sum(len(e.fights) for e in self.recent_events + self.upcoming_events)

    @property
    def offer_count(self) -> int:
        return sum(
            len(f.offers)
            for e in self.recent_events + self.upcoming_events
            for f in e.fights
        )
