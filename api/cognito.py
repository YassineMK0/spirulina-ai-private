"""AWS Cognito JWT verification — RS256 tokens issued by a Cognito User Pool.

The JWKS (public keys) are fetched once from Cognito's well-known endpoint
and cached for the process lifetime.  python-jose handles RS256 signature
verification; no boto3 dependency needed.

Required env vars
-----------------
COGNITO_REGION         e.g. eu-west-1
COGNITO_USER_POOL_ID   e.g. eu-west-1_AbCdEfGhI
COGNITO_APP_CLIENT_ID  e.g. 6xxxxxxxxxxxxxxxxxxxxxxxx

Setup guide (AWS Console)
-------------------------
1. Cognito -> User Pools -> Create user pool
2. Sign-in options: Email
3. Password policy: keep defaults or relax minimums
4. MFA: optional (Off is fine for dev)
5. Self-registration: enabled
6. App client -> Create -> Public client (no secret), enable
   "ALLOW_USER_PASSWORD_AUTH" + "ALLOW_REFRESH_TOKEN_AUTH"
7. Note: User Pool ID, App Client ID, Region -> add to .env
8. Optional: add custom attribute "custom:tier" (String, mutable)
   so tier is embedded in the token without a DB lookup.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

log = logging.getLogger("spirulina.cognito")

COGNITO_REGION        = os.getenv("COGNITO_REGION", "")
COGNITO_USER_POOL_ID  = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")


def _issuer() -> str:
    return f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Fetch Cognito public keys. Cached for the process lifetime."""
    url = f"{_issuer()}/.well-known/jwks.json"
    log.info("fetching Cognito JWKS from %s", url)
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def is_cognito_token(token: str) -> bool:
    """Return True if this token's iss claim matches our User Pool (unverified, fast)."""
    if not COGNITO_USER_POOL_ID:
        return False
    try:
        claims = jwt.get_unverified_claims(token)
        return claims.get("iss", "") == _issuer()
    except Exception:
        return False


def verify_cognito_token(token: str) -> dict:
    """Verify a Cognito ID/access token and return normalised {sub, email, tier}.

    Raises HTTP 401 if the token is invalid or expired.
    Raises HTTP 503 if Cognito is not configured.
    """
    if not COGNITO_REGION or not COGNITO_USER_POOL_ID:
        raise HTTPException(status_code=503, detail="Cognito not configured on this server")

    try:
        jwks = _get_jwks()
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=COGNITO_APP_CLIENT_ID or None,
            issuer=_issuer(),
        )
    except JWTError as exc:
        log.warning("Cognito token rejected: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid Cognito token: {exc}")

    return {
        "sub":   claims["sub"],
        "email": claims.get("email", claims.get("cognito:username", "")),
        "tier":  claims.get("custom:tier", "free"),
    }
