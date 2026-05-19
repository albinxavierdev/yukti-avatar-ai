#!/usr/bin/env python3
"""Create or update the dummy local user test / test123."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from yukti.db.schema import init_db
from yukti.db.repository import ChatRepository


def main() -> int:
    init_db()
    repo = ChatRepository()
    user = repo.upsert_local_user(
        username="test",
        password="test123",
        name="Test User",
        email="test@yukti.local",
    )
    print(f"Dummy user ready: username=test  password=test123  id={user.id}")
    print("Set AUTH_DISABLED=0 in .env and sign in at /login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
