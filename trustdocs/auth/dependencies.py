"""FastAPI dependencies for authentication.

Provides `get_current_user` — a dependency that extracts the session
cookie, validates it, and returns the authenticated user dict.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import Cookie, HTTPException, Request

from trustdocs import database as db
from trustdocs.auth.crypto import hash_session_token


async def get_current_user(request: Request) -> dict:
    """Extract and validate session from cookie. Returns user dict.

    Raises 401 if session is missing, expired, or invalid.
    """
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(401, "Not authenticated")

    token_hash = hash_session_token(token)
    session = await db.find_one("sessions", token_hash=token_hash)

    if not session:
        raise HTTPException(401, "Invalid session")

    # Check expiry
    expires = session.get("expires_at")
    if expires:
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        if expires < datetime.now(timezone.utc):
            await db.delete_one("sessions", session["id"])
            raise HTTPException(401, "Session expired")

    user = await db.find_one("users", id=session["user_id"])
    if not user:
        raise HTTPException(401, "User not found")

    return user


async def get_optional_user(request: Request) -> Optional[dict]:
    """Like get_current_user but returns None instead of raising."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
