"""SentinelTwin — Auth Routes"""
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
import bcrypt
from api.routes._auth_utils import (
    _USERS, _REFRESH_TOKENS, _FAILED_ATTEMPTS,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, check_brute_force, ACCESS_EXPIRE_MIN,
)

log = logging.getLogger("sentineltwin.api.auth")
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None
    @field_validator("username")
    @classmethod
    def username_clean(cls, v):
        return v.strip().lower()

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_EXPIRE_MIN * 60
    user: Dict

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    check_brute_force(ip)
    user = _USERS.get(body.username)
    if not user:
        _FAILED_ATTEMPTS.setdefault(ip, []).append(time.time())
        raise HTTPException(status_code=401, detail="AUTHENTICATION_FAILED")
    if user["is_locked"]:
        raise HTTPException(status_code=403, detail="ACCOUNT_LOCKED")
    if not bcrypt.checkpw(body.password.encode(), user["hashed_password"].encode()):
        user["failed_login_count"] += 1
        if user["failed_login_count"] >= 5:
            user["is_locked"] = True
        _FAILED_ATTEMPTS.setdefault(ip, []).append(time.time())
        raise HTTPException(status_code=401, detail="AUTHENTICATION_FAILED")
    user["failed_login_count"] = 0
    user["last_login"] = datetime.now(timezone.utc).isoformat()
    access_token = create_access_token({"sub": user["username"], "role": user["role"]})
    refresh_token = create_refresh_token(user["username"])
    log.info(f"AUTH: User '{user['username']}' ({user['role']}) logged in from {ip}")
    return LoginResponse(
        access_token=access_token, refresh_token=refresh_token,
        user={"id": user["id"], "username": user["username"],
              "full_name": user["full_name"], "role": user["role"], "email": user["email"]})


@router.post("/refresh")
async def refresh_token_endpoint(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="INVALID_TOKEN_TYPE")
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    username = _REFRESH_TOKENS.get(token_hash)
    if not username:
        raise HTTPException(status_code=401, detail="REFRESH_TOKEN_REVOKED")
    user = _USERS.get(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="USER_INVALID")
    del _REFRESH_TOKENS[token_hash]
    new_access = create_access_token({"sub": username, "role": user["role"]})
    new_refresh = create_refresh_token(username)
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.post("/logout")
async def logout(body: RefreshRequest, user: Dict = Depends(get_current_user)):
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    _REFRESH_TOKENS.pop(token_hash, None)
    return {"status": "LOGGED_OUT"}


@router.get("/me")
async def get_me(user: Dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "full_name": user["full_name"],
            "role": user["role"], "email": user["email"], "last_login": user["last_login"]}
