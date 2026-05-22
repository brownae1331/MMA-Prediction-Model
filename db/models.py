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
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    fighter_1_id = Column(Integer, ForeignKey("fighters.id", ondelete="CASCADE"), nullable=False)
    fighter_2_id = Column(Integer, ForeignKey("fighters.id", ondelete="CASCADE"), nullable=False)
    match_number = Column(Integer, nullable=False)
    weight_class = Column(String)
    winner = Column(String)
    method = Column(String)
    finish_round = Column(Integer)
    finish_time = Column(String)
    last_updated_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("event_id", "match_number", name="uix_event_match_number"),
    )

    event = relationship("Event", back_populates="fights")
    fighter_1 = relationship("Fighter", foreign_keys=[fighter_1_id])
    fighter_2 = relationship("Fighter", foreign_keys=[fighter_2_id])
