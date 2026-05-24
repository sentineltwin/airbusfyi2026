"""
SentinelTwin — Shared Auth Utilities
JWT helpers, user store, RBAC — used by all route modules
"""

import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt

SECRET_KEY = "sentineltwin-jwt-secret-key-production-grade-256bit"
ALGORITHM = "HS256"
ACCESS_EXPIRE_MIN = 30
REFRESH_EXPIRE_DAYS = 7

security = HTTPBearer()

# In-memory user store
_USERS: Dict[str, Dict] = {
    "admin": {
        "id": str(uuid.uuid4()), "username": "admin", "full_name": "System Administrator",
        "email": "admin@sentineltwin.airbus.internal",
        "hashed_password": bcrypt.hashpw(b"sentinel2026", bcrypt.gensalt()).decode(),
        "role": "administrator", "is_active": True, "is_locked": False,
        "failed_login_count": 0, "last_login": None,
    },
    "pilot": {
        "id": str(uuid.uuid4()), "username": "pilot", "full_name": "Capt. J. Renaud",
        "email": "j.renaud@airbus.com",
        "hashed_password": bcrypt.hashpw(b"pilot2026", bcrypt.gensalt()).decode(),
        "role": "pilot", "is_active": True, "is_locked": False,
        "failed_login_count": 0, "last_login": None,
    },
    "engineer": {
        "id": str(uuid.uuid4()), "username": "engineer", "full_name": "M. Bouchard — Avionics",
        "email": "m.bouchard@airbus.com",
        "hashed_password": bcrypt.hashpw(b"engineer2026", bcrypt.gensalt()).decode(),
        "role": "maintenance_engineer", "is_active": True, "is_locked": False,
        "failed_login_count": 0, "last_login": None,
    },
    "dispatcher": {
        "id": str(uuid.uuid4()), "username": "dispatcher", "full_name": "L. Martin — Dispatch",
        "email": "l.martin@airbus.com",
        "hashed_password": bcrypt.hashpw(b"dispatch2026", bcrypt.gensalt()).decode(),
        "role": "dispatcher", "is_active": True, "is_locked": False,
        "failed_login_count": 0, "last_login": None,
    },
}

_REFRESH_TOKENS: Dict[str, str] = {}
_FAILED_ATTEMPTS: Dict[str, List[float]] = {}


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_EXPIRE_MIN))
    payload.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc), "type": "refresh", "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _REFRESH_TOKENS[token_hash] = username
    return token


def decode_token(token: str) -> Dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="TOKEN_INVALID")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    payload = decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username or username not in _USERS:
        raise HTTPException(status_code=401, detail="USER_NOT_FOUND")
    user = _USERS[username]
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")
    if user["is_locked"]:
        raise HTTPException(status_code=403, detail="ACCOUNT_LOCKED")
    return user


def require_role(*roles: str):
    def checker(user: Dict = Depends(get_current_user)) -> Dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="INSUFFICIENT_PRIVILEGES")
        return user
    return checker


def check_brute_force(ip: str):
    now = time.time()
    attempts = _FAILED_ATTEMPTS.get(ip, [])
    attempts = [t for t in attempts if now - t < 300]
    _FAILED_ATTEMPTS[ip] = attempts
    if len(attempts) >= 10:
        raise HTTPException(status_code=429, detail="BRUTE_FORCE_LOCKOUT")
