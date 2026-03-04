"""Chat routes + WebSocket handler (PRD 5.7).

Per-document chat room, accessible to owner and active recipients.
Messages delivered via WebSocket and stored in PostgreSQL.
"""

import json
import logging
from typing import Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from trustdocs import database as db
from trustdocs.auth.dependencies import get_current_user
from trustdocs.auth.crypto import hash_session_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

# WebSocket rooms: doc_id -> set of connected WebSockets
_rooms: Dict[str, Set[WebSocket]] = {}


class MessageResponse(BaseModel):
    id: str
    document_id: str
    sender_username: str
    body: str
    created_at: str
    parent_message_id: str | None = None
    is_pinned: bool = False


@router.get("/documents/{doc_id}/messages", response_model=List[MessageResponse])
async def get_messages(doc_id: str, user: dict = Depends(get_current_user)):
    """Get last 100 chat messages for a document."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] == "deleted":
        raise HTTPException(404, "Document not found")

    # Access check
    if str(doc["owner_id"]) != str(user["id"]):
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            raise HTTPException(404, "Document not found")

    messages = await db.find_many("messages", document_id=doc_id, limit=100)
    results = []
    for m in messages:
        sender = await db.find_one("users", id=m["sender_id"])
        results.append(
            MessageResponse(
                id=str(m["id"]),
                document_id=doc_id,
                sender_username=sender["username"] if sender else "unknown",
                body=m["body"],
                created_at=str(m["created_at"]),
                parent_message_id=str(m["parent_message_id"])
                if m.get("parent_message_id")
                else None,
                is_pinned=bool(m.get("is_pinned", False)),
            )
        )

    return results


async def websocket_document(ws: WebSocket, doc_id: str):
    """WebSocket handler for per-document chat room.

    Protocol:
    - Client sends: {"token": "...", "type": "join"} first
    - Then: {"type": "message", "body": "...", "parent_message_id": "..."}
    - Server broadcasts: {"type": "message", "sender": "...", "body": "...", "id": "...", "parent_message_id": "..."}
    """
    await ws.accept()

    # Authenticate via initial message
    try:
        init = await ws.receive_json()
        token = init.get("token", "")
        token_hash = hash_session_token(token)
        session = await db.find_one("sessions", token_hash=token_hash)
        if not session:
            await ws.send_json({"type": "error", "message": "Authentication failed"})
            await ws.close(code=1008)
            return

        user = await db.find_one("users", id=session["user_id"])
        if not user:
            await ws.send_json({"type": "error", "message": "User not found"})
            await ws.close(code=1008)
            return
    except Exception:
        await ws.close(code=1008)
        return

    # Verify access to document
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] == "deleted":
        await ws.send_json({"type": "error", "message": "Document not found"})
        await ws.close(code=1008)
        return

    if str(doc["owner_id"]) != str(user["id"]):
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            await ws.send_json({"type": "error", "message": "Access denied"})
            await ws.close(code=1008)
            return

    # Join room
    if doc_id not in _rooms:
        _rooms[doc_id] = set()
    _rooms[doc_id].add(ws)

    await ws.send_json({"type": "joined", "username": user["username"]})

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "message" and data.get("body"):
                parent_message_id = data.get("parent_message_id")
                is_pinned = bool(data.get("is_pinned", False))

                # Store message
                msg = await db.insert(
                    "messages",
                    {
                        "document_id": doc_id,
                        "sender_id": user["id"],
                        "body": data["body"],
                        "parent_message_id": parent_message_id,
                        "is_pinned": is_pinned,
                    },
                )

                # Broadcast to room
                broadcast = {
                    "type": "message",
                    "id": str(msg["id"]),
                    "sender": user["username"],
                    "body": data["body"],
                    "created_at": str(msg["created_at"]),
                    "parent_message_id": str(msg["parent_message_id"])
                    if msg.get("parent_message_id")
                    else None,
                    "is_pinned": bool(msg.get("is_pinned", False)),
                }

                dead = []
                for client in _rooms.get(doc_id, set()):
                    try:
                        await client.send_json(broadcast)
                    except Exception:
                        dead.append(client)
                for d in dead:
                    _rooms[doc_id].discard(d)

    except WebSocketDisconnect:
        pass
    finally:
        if doc_id in _rooms:
            _rooms[doc_id].discard(ws)
            if not _rooms[doc_id]:
                del _rooms[doc_id]
