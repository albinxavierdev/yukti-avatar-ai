"""Google OAuth and session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.requests import Request as StarletteRequest

from yukti.auth.deps import require_user
from yukti.auth.google_oauth import google, google_configured, redirect_uri
from yukti.auth.jwt_util import create_access_token
from yukti.config import AUTH_DISABLED, BASE_URL, JWT_COOKIE_NAME, JWT_EXPIRE_DAYS
from yukti.db.repository import ChatRepository, User

router = APIRouter(prefix="/auth", tags=["auth"])
_repo = ChatRepository()


@router.get("/status")
async def auth_status():
    return {
        "google_configured": google_configured(),
        "auth_disabled": AUTH_DISABLED,
        "login_url": f"{BASE_URL}/auth/google",
    }


@router.get("/me")
async def auth_me(user: User = Depends(require_user)):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    }


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


def _login_response(user: User) -> RedirectResponse:
    jwt_token = create_access_token(user.id, user.email)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        JWT_COOKIE_NAME,
        jwt_token,
        httponly=True,
        max_age=JWT_EXPIRE_DAYS * 86400,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/login")
async def auth_login_json(body: LoginRequest):
    if AUTH_DISABLED:
        return RedirectResponse(url="/", status_code=303)
    user = _repo.authenticate_local(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return _login_response(user)


@router.post("/login/form")
async def auth_login_form(
    username: str = Form(...),
    password: str = Form(...),
):
    if AUTH_DISABLED:
        return RedirectResponse(url="/", status_code=303)
    user = _repo.authenticate_local(username, password)
    if not user:
        return RedirectResponse(url="/login?error=invalid", status_code=303)
    return _login_response(user)


@router.post("/logout")
async def auth_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(JWT_COOKIE_NAME, path="/")
    return response


@router.get("/google")
async def auth_google(request: Request):
    if AUTH_DISABLED:
        return RedirectResponse(url="/")
    if not google_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
        )
    return await google.authorize_redirect(request, redirect_uri())


@router.get("/google/callback")
async def auth_google_callback(request: StarletteRequest):
    if AUTH_DISABLED:
        return RedirectResponse(url="/")
    if not google_configured():
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    token = await google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=400, detail="Google did not return user info")

    user = _repo.upsert_google_user(
        google_sub=userinfo["sub"],
        email=userinfo.get("email") or "",
        name=userinfo.get("name"),
        picture=userinfo.get("picture"),
    )
    jwt_token = create_access_token(user.id, user.email)
    response = RedirectResponse(url="/")
    response.set_cookie(
        JWT_COOKIE_NAME,
        jwt_token,
        httponly=True,
        max_age=JWT_EXPIRE_DAYS * 86400,
        samesite="lax",
        path="/",
    )
    return response
