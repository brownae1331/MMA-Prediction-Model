"""Create all tables defined in db.models."""

from db.database import Base, engine
from db.models import Event, Fight, FightRoundStats, Fighter  # noqa: F401


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Tables created:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
