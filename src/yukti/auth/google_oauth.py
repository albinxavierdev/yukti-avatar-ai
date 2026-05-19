"""Google OAuth2 login (Authlib + Starlette)."""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

from yukti.config import BASE_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

oauth = OAuth(
    Config(
        environ={
            "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
            "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
        }
    )
)

google = oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def redirect_uri() -> str:
    return f"{BASE_URL}/auth/google/callback"
