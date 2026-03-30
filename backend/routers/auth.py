"""
routers/auth.py
──────────────────────────────────────────────────────────────────────────────
POST  /auth/token  — OAuth2 password flow → JWT
GET   /auth/me     — return current user profile
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from auth import (
    authenticate_user,
    create_access_token,
    oauth2_scheme,
    get_current_user,
)

router = APIRouter()


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 password flow.
    username = email address (e.g. mariem@vermeg.com)
    password = vermeg2025
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["email"]})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "email": user["email"],
            "name":  user["name"],
            "role":  user["role"],
        },
    }


@router.get("/me")
async def get_me(token: str = Depends(oauth2_scheme)):
    return get_current_user(token)
