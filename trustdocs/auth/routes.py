"""Authentication routes: register, login, logout."""

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Response, Depends
from pydantic import BaseModel, EmailStr

from trustdocs import database as db
from trustdocs.config import config
from trustdocs.auth.crypto import (
    hash_password,
    verify_password,
    generate_keypair,
    encrypt_signing_key,
    generate_session_token,
    hash_session_token,
)
from trustdocs.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Request/Response Models ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    peer_id: str
    node_id: str


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest):
    """Register a new user with Ed25519 keypair generation."""
    # Check uniqueness
    existing = await db.find_one("users", username=req.username)
    if existing:
        raise HTTPException(409, "Username already taken")
    existing = await db.find_one("users", email=req.email)
    if existing:
        raise HTTPException(409, "Email already registered")

    # Generate Ed25519 keypair
    signing_key, verify_key = generate_keypair()

    # Encrypt signing key with password-derived wrapping key
    encrypted_sk = encrypt_signing_key(bytes(signing_key), req.password)

    peer_id = str(uuid.uuid4())

    user = await db.insert("users", {
        "username": req.username,
        "email": req.email,
        "password_hash": hash_password(req.password),
        "encrypted_signing_key": encrypted_sk,
        "verify_key_hex": verify_key.encode().hex(),
        "peer_id": peer_id,
        "node_id": config.node_id,
    })

    return UserResponse(
        id=str(user["id"]),
        username=user["username"],
        email=user["email"],
        peer_id=user["peer_id"],
        node_id=user["node_id"],
    )


@router.post("/login")
async def login(req: LoginRequest, response: Response):
    """Login with username/password. Returns session cookie."""
    user = await db.find_one("users", username=req.username)
    if not user:
        raise HTTPException(401, "Invalid credentials")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")

    # Generate session token
    token = generate_session_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=config.session_ttl_hours)

    await db.insert("sessions", {
        "user_id": user["id"],
        "token_hash": hash_session_token(token),
        "expires_at": expires,
    })

    # Set HTTP-only session cookie
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=config.session_ttl_hours * 3600,
    )

    return {
        "message": "Login successful",
        "user": UserResponse(
            id=str(user["id"]),
            username=user["username"],
            email=user["email"],
            peer_id=user["peer_id"],
            node_id=user["node_id"],
        ).model_dump(),
    }


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    """Invalidate session. Signing key discarded from memory."""
    # Delete all sessions for this user (clean slate)
    await db.delete_where("sessions", user_id=user["id"])

    response.delete_cookie("session_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    """Return current user info."""
    return UserResponse(
        id=str(user["id"]),
        username=user["username"],
        email=user["email"],
        peer_id=user["peer_id"],
        node_id=user["node_id"],
    )

@router.post("/heartbeat")
async def heartbeat(user: dict = Depends(get_current_user)):
    """Update user's last_seen_at timestamp for presence tracking."""
    # We update the last_seen_at directly in the DB
    await db.update_one(
        "users", 
        user["id"], 
        last_seen_at=datetime.now(timezone.utc)
    )
    return {"status": "ok"}
