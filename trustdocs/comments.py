"""Deprecated comment routes retained for backward compatibility.

Threads are now unified into chat messages via parent_message_id.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trustdocs import database as db
from trustdocs.auth.dependencies import get_current_user

router = APIRouter(tags=["Comments"])


class CommentRequest(BaseModel):
    body: str
    parent_message_id: str | None = None


class CommentResponse(BaseModel):
    id: str
    document_id: str
    author_username: str
    body: str
    created_at: str
    parent_message_id: str | None = None


@router.get("/documents/{doc_id}/comments", response_model=List[CommentResponse])
async def list_comments(doc_id: str, user: dict = Depends(get_current_user)):
    """List threaded comments, mapped from unified messages."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    if str(doc["owner_id"]) != str(user["id"]):
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            raise HTTPException(404, "Document not found")

    messages = await db.find_many("messages", document_id=doc_id, limit=100)
    results = []
    for m in messages:
        if not m.get("parent_message_id"):
            continue
        author = await db.find_one("users", id=m["sender_id"])
        results.append(
            CommentResponse(
                id=str(m["id"]),
                document_id=doc_id,
                author_username=author["username"] if author else "unknown",
                body=m["body"],
                created_at=str(m["created_at"]),
                parent_message_id=str(m["parent_message_id"]),
            )
        )
    return results


@router.post("/documents/{doc_id}/comments", response_model=CommentResponse)
async def create_comment(
    doc_id: str, req: CommentRequest, user: dict = Depends(get_current_user)
):
    """Create a threaded comment by inserting a reply message."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    if str(doc["owner_id"]) != str(user["id"]):
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            raise HTTPException(403, "Access denied")

    comment = await db.insert(
        "messages",
        {
            "document_id": doc_id,
            "sender_id": user["id"],
            "body": req.body,
            "parent_message_id": req.parent_message_id,
            "is_pinned": False,
        },
    )

    return CommentResponse(
        id=str(comment["id"]),
        document_id=doc_id,
        author_username=user["username"],
        body=comment["body"],
        created_at=str(comment["created_at"]),
        parent_message_id=str(comment["parent_message_id"])
        if comment.get("parent_message_id")
        else None,
    )
