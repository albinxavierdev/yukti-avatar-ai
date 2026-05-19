"""SQLite persistence for users, sessions, and messages."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from yukti.db.passwords import hash_password, verify_password
from yukti.config import CHAT_HISTORY_LIMIT, DATABASE_PATH


@dataclass
class User:
    id: int
    google_sub: str
    email: str
    name: str | None
    picture: str | None


@dataclass
class ChatSession:
    id: str
    user_id: int
    title: str | None
    updated_at: str


class ChatRepository:
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_google_user(
        self,
        *,
        google_sub: str,
        email: str,
        name: str | None,
        picture: str | None,
    ) -> User:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE users SET email = ?, name = ?, picture = ?
                    WHERE google_sub = ?
                    """,
                    (email, name, picture, google_sub),
                )
                conn.commit()
                return self._row_user(
                    conn.execute(
                        "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
                    ).fetchone()
                )

            conn.execute(
                """
                INSERT INTO users (google_sub, email, name, picture)
                VALUES (?, ?, ?, ?)
                """,
                (google_sub, email, name, picture),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
            ).fetchone()
            return self._row_user(row)

    def get_user_by_id(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._row_user(row) if row else None

    def get_user_by_username(self, username: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return self._row_user(row) if row else None

    def upsert_local_user(
        self,
        *,
        username: str,
        password: str,
        name: str | None = None,
        email: str | None = None,
    ) -> User:
        username = username.strip().lower()
        google_sub = f"local:{username}"
        email = email or f"{username}@yukti.local"
        name = name or username
        pwd_hash = hash_password(password)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? OR google_sub = ?",
                (username, google_sub),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, email = ?, name = ?, google_sub = ?
                    WHERE id = ?
                    """,
                    (pwd_hash, email, name, google_sub, row["id"]),
                )
                conn.commit()
                return self._row_user(
                    conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
                )

            conn.execute(
                """
                INSERT INTO users (google_sub, email, name, picture, username, password_hash)
                VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (google_sub, email, name, username, pwd_hash),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return self._row_user(row)

    def authenticate_local(self, username: str, password: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
            ).fetchone()
            if not row or not row["password_hash"]:
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            return self._row_user(row)

    def ensure_session(self, session_id: str | None, user_id: int) -> str:
        sid = session_id or str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id FROM chat_sessions WHERE id = ?", (sid,)
            ).fetchone()
            if row:
                if row["user_id"] != user_id:
                    raise PermissionError("Session does not belong to this user")
                conn.execute(
                    "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                    (now, sid),
                )
                conn.commit()
                return sid

            conn.execute(
                """
                INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sid, user_id, "New chat", now, now),
            )
            conn.commit()
            return sid

    def list_sessions(self, user_id: int, limit: int = 30) -> list[ChatSession]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, title, updated_at
                FROM chat_sessions
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [
                ChatSession(
                    id=r["id"],
                    user_id=r["user_id"],
                    title=r["title"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def get_messages(self, session_id: str, *, limit: int = CHAT_HISTORY_LIMIT) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ? AND role IN ('user', 'assistant')
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            chron = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
            return chron

    def append_message(self, session_id: str, role: str, content: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now),
            )
            preview = content.strip().replace("\n", " ")[:80]
            conn.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?, title = COALESCE(NULLIF(title, 'New chat'), ?)
                WHERE id = ?
                """,
                (now, preview or "New chat", session_id),
            )
            conn.commit()

    def append_turn(
        self, session_id: str, user_message: str, assistant_message: str
    ) -> list[dict]:
        self.append_message(session_id, "user", user_message)
        self.append_message(session_id, "assistant", assistant_message)
        return self.get_messages(session_id)

    def clear_session(self, session_id: str, user_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row or row["user_id"] != user_id:
                raise PermissionError("Session not found")
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute(
                """
                UPDATE chat_sessions
                SET title = 'New chat', updated_at = ?
                WHERE id = ?
                """,
                (_utc_now(), session_id),
            )
            conn.commit()

    @staticmethod
    def _row_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            google_sub=row["google_sub"],
            email=row["email"],
            name=row["name"],
            picture=row["picture"],
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
