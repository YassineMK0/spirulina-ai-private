"""Authentication — signup, login, token helpers.

Supports two token types transparently:
  - Custom HS256 JWT  (issued by /auth/login or /auth/signup)
  - Cognito RS256 JWT (issued by AWS Cognito — verified via JWKS)

require_auth() accepts both.  Cognito users are auto-provisioned in the
local DB on first request so tier management works the same for all users.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

log = logging.getLogger("spirulina.auth")

JWT_SECRET    = os.getenv("JWT_SECRET", "spirulina-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

router = APIRouter(prefix="/auth", tags=["auth"])

# ── crypto helpers ───────────────────────────────────────────────────────────
# Use bcrypt directly — passlib has a known compat bug with bcrypt 4.x

import bcrypt as _bcrypt


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user: dict) -> str:
    from jose import jwt
    payload = {
        "sub":   user["id"],
        "email": user["email"],
        "tier":  user["tier"],
        "exp":   datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    from api.cognito import is_cognito_token, verify_cognito_token

    # Cognito token (RS256) — verify against JWKS and auto-provision user
    if is_cognito_token(token):
        payload = verify_cognito_token(token)
        _provision_cognito_user(payload)
        return payload

    # Custom HS256 JWT issued by this backend
    from jose import jwt, JWTError
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


def _provision_cognito_user(payload: dict) -> None:
    """Insert Cognito user into local DB on first login (idempotent)."""
    try:
        from data.users import user_store
        if not user_store.get_by_id(payload["sub"]):
            user_store.create_user_with_id(
                uid=payload["sub"],
                email=payload["email"],
                tier=payload.get("tier", "free"),
            )
            log.info("provisioned Cognito user  sub=%s  email=%s", payload["sub"][:8], payload["email"])
    except Exception as exc:
        log.warning("could not provision Cognito user: %s", exc)


# ── FastAPI dependencies ─────────────────────────────────────────────────────

def require_auth(authorization: str = Header(None)) -> dict:
    """Dependency: verify Bearer token, return decoded payload {sub, email, tier}."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")
    return decode_token(authorization.split(" ", 1)[1])


def require_admin(authorization: str = Header(None)) -> dict:
    """Dependency: require token with tier=admin."""
    payload = require_auth(authorization)
    if payload.get("tier") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


# ── Schemas ──────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email:    str
    password: str


class LoginRequest(BaseModel):
    email:    str
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup")
def signup(req: SignupRequest):
    from data.users import user_store

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if user_store.get_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    # First user ever automatically becomes admin
    tier = "admin" if not user_store.has_any_user() else "free"

    uid   = user_store.create_user(req.email, hash_password(req.password), tier)
    user  = {"id": uid, "email": req.email.lower().strip(), "tier": tier}
    token = create_token(user)

    return {"token": token, "user": user}


@router.post("/login")
def login(req: LoginRequest):
    from data.users import user_store

    user = user_store.get_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user)
    return {
        "token": token,
        "user":  {"id": user["id"], "email": user["email"], "tier": user["tier"]},
    }


@router.get("/me")
def me(authorization: str = Header(None)):
    """Verify token and return fresh user profile from DB."""
    payload = require_auth(authorization)
    from data.users import user_store
    user = user_store.get_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "email": user["email"], "tier": user["tier"]}
