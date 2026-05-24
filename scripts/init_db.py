"""Create all tables defined in db.models."""

from db.database import Base, engine
from db.models import (  # noqa: F401
    Bookmaker,
    Event,
    Fight,
    FightOdds,
    FightRoundStats,
    Fighter,
)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Tables created:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
