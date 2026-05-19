"""FastAPI dependencies for authenticated users."""

from __future__ import annotations

from fastapi import Cookie, HTTPException, Request

from yukti.auth.jwt_util import decode_access_token
from yukti.config import AUTH_DISABLED, JWT_COOKIE_NAME
from yukti.db.repository import ChatRepository, User

_repo = ChatRepository()
_dev_user: User | None = None


def _dev_user_record() -> User:
    global _dev_user
    if _dev_user is None:
        _dev_user = _repo.upsert_google_user(
            google_sub="dev-local",
            email="dev@yukti.local",
            name="Dev User",
            picture=None,
        )
    return _dev_user


async def get_optional_user(
    request: Request,
    yukti_token: str | None = Cookie(default=None, alias=JWT_COOKIE_NAME),
) -> User | None:
    if AUTH_DISABLED:
        return _dev_user_record()

    token = yukti_token or request.cookies.get(JWT_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user = _repo.get_user_by_id(int(payload["sub"]))
        return user
    except Exception:
        return None


async def get_current_user(
    user: User | None = None,
) -> User:
    if user is not None:
        return user
    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_user(
    request: Request,
    yukti_token: str | None = Cookie(default=None, alias=JWT_COOKIE_NAME),
) -> User:
    user = await get_optional_user(request, yukti_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
