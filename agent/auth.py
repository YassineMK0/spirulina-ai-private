"""User identity resolution.

Stub for now — returns the token string directly as the user_id.

When the platform is ready, replace resolve_user() with real JWT decoding:

    import jwt  # pip install PyJWT
    from jwt import PyJWTError

    SECRET  = os.getenv("JWT_SECRET")
    ALGO    = os.getenv("JWT_ALGORITHM", "HS256")

    def resolve_user(token: str | None) -> str:
        if not token:
            return "anonymous"
        try:
            payload = jwt.decode(token, SECRET, algorithms=[ALGO])
            return payload.get("sub") or payload.get("user_id") or "anonymous"
        except PyJWTError:
            return "anonymous"
"""

from __future__ import annotations


def resolve_user(token: str | None) -> str:
    """Return the user_id from *token*.

    Stub: treats the token as a plain user_id string.
    Replace body with JWT decode when the platform auth is available.
    """
    return (token or "").strip() or "anonymous"
