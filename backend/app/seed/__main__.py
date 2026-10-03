import argparse

from app.config import settings
from app.database import SessionLocal
from app.seed.loader import load_fixtures, reset_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Load SuiteSpot seed data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing rows before loading fixtures.",
    )
    args = parser.parse_args()

    if settings.ENVIRONMENT == "production":
        raise SystemExit("Refusing to seed a production database.")

    db = SessionLocal()
    try:
        if args.reset:
            reset_tables(db)
            print("Cleared existing data.")
        created = load_fixtures(db)
        print(
            f"Seeded {created['users']} users, {created['hotels']} hotels, "
            f"{created['rooms']} rooms."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
