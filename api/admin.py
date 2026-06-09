"""Admin endpoints — full user management."""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from api.auth import require_admin, hash_password

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_TIERS = {"free", "pro", "admin"}


class TierUpdate(BaseModel):
    tier: str


class CreateUser(BaseModel):
    email:    str
    password: str
    tier:     str = "free"


class PasswordReset(BaseModel):
    password: str


@router.get("/users")
def list_users(authorization: str = Header(None)):
    require_admin(authorization)
    from data.users import user_store
    return user_store.list_users()


@router.post("/users", status_code=201)
def create_user(body: CreateUser, authorization: str = Header(None)):
    require_admin(authorization)
    from data.users import user_store

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if body.tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"tier must be one of: {', '.join(VALID_TIERS)}")
    if user_store.get_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    uid = user_store.create_user(body.email, hash_password(body.password), body.tier)
    return {"id": uid, "email": body.email, "tier": body.tier}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, authorization: str = Header(None)):
    current = require_admin(authorization)
    if current["sub"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    from data.users import user_store
    user_store.delete_user(user_id)
    return {"status": "deleted"}


@router.patch("/users/{user_id}/tier")
def update_tier(user_id: str, body: TierUpdate, authorization: str = Header(None)):
    require_admin(authorization)
    if body.tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"tier must be one of: {', '.join(VALID_TIERS)}")
    from data.users import user_store
    user_store.update_tier(user_id, body.tier)
    return {"status": "updated", "tier": body.tier}


@router.patch("/users/{user_id}/password")
def reset_password(user_id: str, body: PasswordReset, authorization: str = Header(None)):
    require_admin(authorization)
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    from data.users import user_store
    user_store.update_password(user_id, hash_password(body.password))
    return {"status": "updated"}
