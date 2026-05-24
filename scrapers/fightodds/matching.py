"""Match Fight Odds scraped data to UFCstats rows in the database."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session, joinedload

from db.models import Event as EventModel
from db.models import Fight as FightModel
from db.models import Fighter as FighterModel
from schemas.fightodds import FightOddsEvent, FightOddsFightStub


def normalize_name(name: str) -> str:
    """Lowercase name with punctuation stripped for comparison."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return " ".join(text.split())


def fighter_pair_key(name_a: str, name_b: str) -> frozenset[str]:
    return frozenset({normalize_name(name_a), normalize_name(name_b)})


def db_fighter_name(fighter: FighterModel) -> str:
    return fighter.name.strip()


def resolve_event(
    session: Session,
    fo_event: FightOddsEvent,
) -> EventModel | None:
    by_pk = (
        session.query(EventModel)
        .filter(EventModel.fightodds_event_pk == fo_event.pk)
        .one_or_none()
    )
    if by_pk is not None:
        return by_pk

    candidates = (
        session.query(EventModel)
        .filter(EventModel.organizer == "UFC")
        .all()
    )
    fo_date = fo_event.event_date
    for event in candidates:
        if event.date is None:
            continue
        if event.date.date() != fo_date:
            continue
        return event
    return None


def fighters_match_fight(
    fight: FightModel,
    stub: FightOddsFightStub,
) -> bool:
    db_pair = fighter_pair_key(
        db_fighter_name(fight.fighter_1),
        db_fighter_name(fight.fighter_2),
    )
    stub_pair = fighter_pair_key(
        stub.fighter_1.full_name,
        stub.fighter_2.full_name,
    )
    return db_pair == stub_pair


def resolve_fight(
    session: Session,
    fo_event: FightOddsEvent,
    stub: FightOddsFightStub,
) -> FightModel | None:
    by_slug = (
        session.query(FightModel)
        .options(
            joinedload(FightModel.fighter_1),
            joinedload(FightModel.fighter_2),
        )
        .filter(FightModel.fightodds_slug == stub.slug)
        .one_or_none()
    )
    if by_slug is not None:
        return by_slug

    event = resolve_event(session, fo_event)
    if event is None:
        return None

    fights = (
        session.query(FightModel)
        .options(
            joinedload(FightModel.fighter_1),
            joinedload(FightModel.fighter_2),
        )
        .filter(FightModel.event_id == event.id)
        .all()
    )
    for fight in fights:
        if fighters_match_fight(fight, stub):
            if fight.fightodds_slug is None:
                fight.fightodds_slug = stub.slug
            if event.fightodds_event_pk is None:
                event.fightodds_event_pk = fo_event.pk
            return fight

    return None
