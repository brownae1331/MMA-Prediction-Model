"""Pydantic schemas for fight scraping and import."""

from pydantic import BaseModel, Field


class FightStub(BaseModel):
    """Parsed from the event page — used to discover fights on a card."""

    url: str
    fighter_1_url: str
    fighter_2_url: str
    match_number: int = Field(ge=1)
    weight_class: str | None = None


class JudgeScore(BaseModel):
    """One judge's scorecard entry on a fight."""

    judge: str
    fighter_1: int
    fighter_2: int


class FightInfo(BaseModel):
    """Parsed from the fight detail page — outcome and metadata."""

    url: str
    weight_class: str | None = None
    winner_url: str | None = None
    method: str | None = None
    finish_round: int | None = Field(default=None, ge=1)
    finish_time: str | None = None
    time_format: str | None = None
    referee: str | None = None
    scorecard: list[JudgeScore] | None = None


class FightRoundStats(BaseModel):
    """One fighter's stats for a single round (fight detail page, per-round tables)."""

    fighter_url: str
    round_number: int = Field(ge=1)

    knockdowns: int | None = None
    sig_strikes_landed: int | None = None
    sig_strikes_attempted: int | None = None
    total_strikes_landed: int | None = None
    total_strikes_attempted: int | None = None
    takedowns_landed: int | None = None
    takedowns_attempted: int | None = None
    submission_attempts: int | None = None
    reversals: int | None = None
    control_time_seconds: int | None = None

    sig_head_landed: int | None = None
    sig_head_attempted: int | None = None
    sig_body_landed: int | None = None
    sig_body_attempted: int | None = None
    sig_leg_landed: int | None = None
    sig_leg_attempted: int | None = None

    sig_distance_landed: int | None = None
    sig_distance_attempted: int | None = None
    sig_clinch_landed: int | None = None
    sig_clinch_attempted: int | None = None
    sig_ground_landed: int | None = None
    sig_ground_attempted: int | None = None


class FightDetail(BaseModel):
    """Full scrape of a fight detail page — maps to fights + fight_round_stats tables."""

    fight: FightInfo
    round_stats: list[FightRoundStats] = Field(default_factory=list)
