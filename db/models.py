"""Database models."""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    date = Column(DateTime(timezone=True))
    location = Column(String)
    organizer = Column(String)
    fightodds_event_pk = Column(Integer, unique=True, nullable=True)
    last_updated_at = Column(DateTime(timezone=True))

    fights = relationship("Fight", back_populates="event", cascade="all, delete-orphan")


class Fighter(Base):
    __tablename__ = "fighters"

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    nickname = Column(String)

    height = Column(String)
    weight = Column(String)
    reach = Column(String)
    stance = Column(String)
    dob = Column(Date)

    slpm = Column(Float)
    str_acc = Column(Float)
    sapm = Column(Float)
    str_def = Column(Float)
    td_avg = Column(Float)
    td_acc = Column(Float)
    td_def = Column(Float)
    sub_avg = Column(Float)

    last_updated_at = Column(DateTime(timezone=True))


class Fight(Base):
    __tablename__ = "fights"

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    fighter_1_id = Column(Integer, ForeignKey("fighters.id", ondelete="CASCADE"), nullable=False)
    fighter_2_id = Column(Integer, ForeignKey("fighters.id", ondelete="CASCADE"), nullable=False)
    match_number = Column(Integer, nullable=False)

    weight_class = Column(String)
    winner_id = Column(Integer, ForeignKey("fighters.id", ondelete="SET NULL"))
    method = Column(String)
    finish_round = Column(Integer)
    finish_time = Column(String)
    time_format = Column(String)
    referee = Column(String)
    scorecard = Column(JSONB)
    fightodds_slug = Column(String, unique=True, nullable=True)
    last_updated_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("event_id", "match_number", name="uix_event_match_number"),
    )

    event = relationship("Event", back_populates="fights")
    fighter_1 = relationship("Fighter", foreign_keys=[fighter_1_id])
    fighter_2 = relationship("Fighter", foreign_keys=[fighter_2_id])
    winner = relationship("Fighter", foreign_keys=[winner_id])
    round_stats = relationship(
        "FightRoundStats",
        back_populates="fight",
        cascade="all, delete-orphan",
    )
    odds = relationship(
        "FightOdds",
        back_populates="fight",
        cascade="all, delete-orphan",
    )


class FightRoundStats(Base):
    __tablename__ = "fight_round_stats"

    id = Column(Integer, primary_key=True)
    fight_id = Column(Integer, ForeignKey("fights.id", ondelete="CASCADE"), nullable=False)
    fighter_id = Column(Integer, ForeignKey("fighters.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)

    knockdowns = Column(Integer)
    sig_strikes_landed = Column(Integer)
    sig_strikes_attempted = Column(Integer)
    total_strikes_landed = Column(Integer)
    total_strikes_attempted = Column(Integer)
    takedowns_landed = Column(Integer)
    takedowns_attempted = Column(Integer)
    submission_attempts = Column(Integer)
    reversals = Column(Integer)
    control_time_seconds = Column(Integer)

    sig_head_landed = Column(Integer)
    sig_head_attempted = Column(Integer)
    sig_body_landed = Column(Integer)
    sig_body_attempted = Column(Integer)
    sig_leg_landed = Column(Integer)
    sig_leg_attempted = Column(Integer)

    sig_distance_landed = Column(Integer)
    sig_distance_attempted = Column(Integer)
    sig_clinch_landed = Column(Integer)
    sig_clinch_attempted = Column(Integer)
    sig_ground_landed = Column(Integer)
    sig_ground_attempted = Column(Integer)

    __table_args__ = (
        UniqueConstraint(
            "fight_id",
            "fighter_id",
            "round_number",
            name="uix_fight_fighter_round",
        ),
    )

    fight = relationship("Fight", back_populates="round_stats")
    fighter = relationship("Fighter")


class Bookmaker(Base):
    __tablename__ = "bookmakers"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)

    odds = relationship("FightOdds", back_populates="bookmaker")


class FightOdds(Base):
    __tablename__ = "fight_odds"

    id = Column(Integer, primary_key=True)
    fight_id = Column(Integer, ForeignKey("fights.id", ondelete="CASCADE"), nullable=False)
    bookmaker_id = Column(
        Integer, ForeignKey("bookmakers.id", ondelete="CASCADE"), nullable=False
    )
    fighter_id = Column(Integer, ForeignKey("fighters.id", ondelete="CASCADE"), nullable=False)
    american_odds = Column(Integer, nullable=True)
    american_odds_open = Column(Integer, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(String, nullable=False, default="fightodds")

    __table_args__ = (
        UniqueConstraint(
            "fight_id",
            "bookmaker_id",
            "fighter_id",
            name="uix_fight_bookmaker_fighter_odds",
        ),
    )

    fight = relationship("Fight", back_populates="odds")
    bookmaker = relationship("Bookmaker", back_populates="odds")
    fighter = relationship("Fighter")
