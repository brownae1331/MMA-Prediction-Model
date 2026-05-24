"""Pydantic schemas for Fight Odds scraping and import."""

from datetime import date

from pydantic import BaseModel, Field, computed_field


class FightOddsFighter(BaseModel):
    first_name: str
    last_name: str
    slug: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class FightOddsEvent(BaseModel):
    pk: int
    slug: str
    name: str
    event_date: date
    promotion_slug: str
    promotion_name: str | None = None
    venue: str | None = None
    city: str | None = None

    @computed_field
    @property
    def url(self) -> str:
        return f"https://fightodds.io/mma-events/{self.pk}/{self.slug}"


class FightOddsFightStub(BaseModel):
    pk: int
    slug: str
    order: int = Field(ge=0)
    fighter_1: FightOddsFighter
    fighter_2: FightOddsFighter
    is_cancelled: bool = False
    event_pk: int | None = None

    @computed_field
    @property
    def url(self) -> str:
        return f"https://fightodds.io/fights/{self.slug}/odds"


class SportsbookOffer(BaseModel):
    book_slug: str
    book_name: str
    fighter_1_odds: int | None = None
    fighter_2_odds: int | None = None
    fighter_1_odds_open: int | None = None
    fighter_2_odds_open: int | None = None


class FightOddsDetail(BaseModel):
    fight_slug: str
    fighter_1: FightOddsFighter
    fighter_2: FightOddsFighter
    best_odds_1: int | None = None
    best_odds_2: int | None = None
    offers: list[SportsbookOffer] = Field(default_factory=list)
