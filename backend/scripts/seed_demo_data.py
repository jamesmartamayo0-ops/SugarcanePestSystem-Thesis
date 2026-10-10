"""Deterministic synthetic demo-data utility (test database only).

Usage from the repository root::

    backend\\.venv\\Scripts\\flask --app backend/run.py seed-demo-data

The utility REFUSES to run unless DB_NAME is sugarcane_pest_test and the
live connection is sugarcane_pest_test. It never touches sugarcane_pest_db.
Repeated execution is safe: existing demo marker data causes a refusal
instead of duplicate seeding. No passwords or .env contents are printed.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.demo_data import seed_demo_data  # noqa: E402
from app.extensions import db  # noqa: E402


def main() -> int:
    if os.environ.get("DB_NAME") != "sugarcane_pest_test":
        print("Refusing to seed: DB_NAME must be sugarcane_pest_test.")
        return 2
    app = create_app()
    with app.app_context():
        try:
            result = seed_demo_data()
        except RuntimeError as exc:
            print(str(exc))
            return 2
        except Exception:
            db.session.rollback()
            print("Unable to seed demo data.")
            return 1
    if not result.get("seeded"):
        print(str(result.get("reason")))
        return 0
    print(f"Demo data seeded: {result['farmers']} farmers, {result['farms']} farms.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
