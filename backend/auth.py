"""
auth.py
──────────────────────────────────────────────────────────────────────────────
JWT authentication with role-based access.

Roles:
  banking    → can upload: ISDA, Loan Agreement, Credit Agreement
  insurance  → can upload: Insurance Policy, Invoice, Settlement
  compliance → can upload: Compliance Report, Risk Assessment, Audit Report
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY  = "docai-vermeg-secret-2025-xK9#mP2@nL5"
ALGORITHM   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8   # 8 hours

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# ── Users DB (extend to DB later) ────────────────────────────────────────────
# role: "banking" | "insurance" | "compliance" | "admin"
USERS_DB = {
    "mariem@vermeg.com": {
        "email":           "mariem@vermeg.com",
        "name":            "Mariem Nasri",
        "role":            "banking",          # banking user
        "hashed_password": pwd_context.hash("vermeg2025"),
    },
    "admin@vermeg.com": {
        "email":           "admin@vermeg.com",
        "name":            "Admin VERMEG",
        "role":            "admin",            # admin can access all doc types
        "hashed_password": pwd_context.hash("admin2025"),
    },
    "insurance@vermeg.com": {
        "email":           "insurance@vermeg.com",
        "name":            "Insurance Analyst",
        "role":            "insurance",
        "hashed_password": pwd_context.hash("insurance2025"),
    },
    "compliance@vermeg.com": {
        "email":           "compliance@vermeg.com",
        "name":            "Compliance Officer",
        "role":            "compliance",
        "hashed_password": pwd_context.hash("compliance2025"),
    },
}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = USERS_DB.get(email)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(token: str) -> dict:
    payload = decode_token(token)
    email: str = payload.get("sub")
    if not email or email not in USERS_DB:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    user = USERS_DB[email].copy()
    user.pop("hashed_password", None)
    return user
