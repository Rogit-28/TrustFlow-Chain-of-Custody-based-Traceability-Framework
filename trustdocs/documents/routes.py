"""Document CRUD routes.

Implements:
- POST   /documents           — Upload
- GET    /documents           — List owned + shared
- GET    /documents/{id}      — Metadata
- DELETE /documents/{id}      — Move to recycle bin
- POST   /documents/{id}/restore — Restore from recycle bin
- DELETE /documents/{id}/purge — Permanent delete
- GET    /documents/recycled — List recycled docs
- POST   /documents/{id}/share — Share with recipient
- DELETE /documents/{id}/share/{user_id} — Revoke share
- GET    /documents/{id}/download — Download file
- GET    /documents/{id}/trace — Document topology view
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from trustdocs import database as db
from trustdocs.config import config
from trustdocs.auth.dependencies import get_current_user
from trustdocs.trustflow_service import trustflow
from coc_framework.core.coc_node import CoCNode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Models ───────────────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    coc_node_hash: str
    status: str
    created_at: str
    owner_username: Optional[str] = None
    is_owner: bool = False
    share_count: int = 0


class ShareRequest(BaseModel):
    recipient_username: str


class ShareResponse(BaseModel):
    id: str
    document_id: str
    recipient_username: str
    child_coc_node_hash: str
    status: str
    created_at: str


class DocumentListResponse(BaseModel):
    owned: List[DocumentResponse]
    shared_with_me: List[DocumentResponse]


class RestoreRequest(BaseModel):
    restore_access: bool


class TraceResponse(BaseModel):
    nodes: List[dict]
    edges: List[dict]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ensure_storage_dir():
    """Create file storage directory if it doesn't exist."""
    Path(config.storage_dir).mkdir(parents=True, exist_ok=True)


async def _doc_to_response(doc: dict, user: dict) -> DocumentResponse:
    """Convert a DB document dict to a response model."""
    owner = await db.find_one("users", id=doc["owner_id"])
    shares = await db.find_many("file_shares", document_id=doc["id"], status="active")
    return DocumentResponse(
        id=str(doc["id"]),
        filename=doc["filename"],
        mime_type=doc["mime_type"],
        size_bytes=doc["size_bytes"],
        content_hash=doc["content_hash"],
        coc_node_hash=doc["coc_node_hash"],
        status=doc["status"],
        created_at=str(doc["created_at"]),
        owner_username=owner["username"] if owner else "unknown",
        is_owner=str(doc["owner_id"]) == str(user["id"]),
        share_count=len(shares),
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Upload a document.

    System behaviour (PRD 5.2):
    1. Server receives the file
    2. SHA-256 hash computed
    3. TrustFlow Peer.create_coc_root() called
    4. File stored on disk, metadata in DB
    5. AuditLog event recorded
    """
    _ensure_storage_dir()

    # Validate file size
    content = await file.read()
    if len(content) > config.max_file_size_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {config.max_file_size_mb}MB limit")

    # Compute content hash
    content_text = content.decode("utf-8", errors="replace")
    content_hash = hashlib.sha256(content).hexdigest()

    # Store file on disk
    file_id = str(uuid.uuid4())
    ext = Path(file.filename or "file").suffix
    storage_path = str(Path(config.storage_dir) / f"{file_id}{ext}")

    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(content)

    # TrustFlow: create CoC root node
    node = await trustflow.create_document_node(user["peer_id"], content_text)

    # Store metadata in DB
    doc = await db.insert(
        "documents",
        {
            "id": file_id,
            "owner_id": user["id"],
            "filename": file.filename or "untitled",
            "mime_type": file.content_type or "application/octet-stream",
            "size_bytes": len(content),
            "storage_path": storage_path,
            "storage_node": config.node_id,
            "content_hash": node.content_hash,
            "coc_node_hash": node.node_hash,
            "status": "active",
        },
    )

    return await _doc_to_response(doc, user)


@router.get("", response_model=DocumentListResponse)
async def list_documents(user: dict = Depends(get_current_user)):
    """List all documents: owned and shared-with-me."""
    owned = await db.find_many("documents", owner_id=user["id"], status="active")
    owned_responses = [await _doc_to_response(d, user) for d in owned]

    # Find docs shared with me
    shares = await db.find_many("file_shares", recipient_id=user["id"], status="active")
    shared_docs = []
    for share in shares:
        doc = await db.find_one("documents", id=share["document_id"])
        if doc and doc["status"] == "active":
            shared_docs.append(await _doc_to_response(doc, user))

    return DocumentListResponse(owned=owned_responses, shared_with_me=shared_docs)


@router.get("/recycled", response_model=List[DocumentResponse])
async def list_recycled_documents(user: dict = Depends(get_current_user)):
    """List recycled documents owned by the current user."""
    recycled = await db.find_many("documents", owner_id=user["id"], status="recycled")
    return [await _doc_to_response(d, user) for d in recycled]
@router.get("/search")
async def search_documents(q: str, user: dict = Depends(get_current_user)):
    """Search for documents by filename (fuzzy matching). Returns owned, shared, and recycled."""
    q_lower = q.lower()
    owned = await db.find_many("documents", owner_id=user["id"], status="active")
    owned_matched = [d for d in owned if q_lower in d["filename"].lower()]
    owned_responses = [await _doc_to_response(d, user) for d in owned_matched]

    shares = await db.find_many("file_shares", recipient_id=user["id"], status="active")
    shared_docs = []
    for share in shares:
        doc = await db.find_one("documents", id=share["document_id"])
        if doc and doc["status"] == "active" and q_lower in doc["filename"].lower():
            shared_docs.append(await _doc_to_response(doc, user))

    recycled = await db.find_many("documents", owner_id=user["id"], status="recycled")
    recycled_matched = [d for d in recycled if q_lower in d["filename"].lower()]
    recycled_responses = [await _doc_to_response(d, user) for d in recycled_matched]

    return {"owned": owned_responses, "shared_with_me": shared_docs, "recycled": recycled_responses}


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Get document metadata."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    # Check access: owner or active share
    if str(doc["owner_id"]) != str(user["id"]):
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            raise HTTPException(
                403, "Access denied — you are not a recipient of this document"
            )

    return await _doc_to_response(doc, user)


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Download document file.

    Checks tombstone status before serving (PRD 5.5).
    """
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    tombstone = await trustflow.storage.get_tombstone(doc["content_hash"])
    if tombstone and not tombstone.is_expired():
        raise HTTPException(
            409,
            "This document has been deleted and is pending full propagation across all nodes.",
        )

    # Access check
    if str(doc["owner_id"]) != str(user["id"]):
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            raise HTTPException(403, "Access denied")

    # Audit trail
    trustflow.audit_log.log_event("ACCESS", user["peer_id"], doc["coc_node_hash"])

    return FileResponse(
        path=doc["storage_path"],
        filename=doc["filename"],
        media_type=doc["mime_type"],
    )


@router.post("/{doc_id}/share", response_model=ShareResponse)
async def share_document(
    doc_id: str, req: ShareRequest, user: dict = Depends(get_current_user)
):
    """Share a document with a recipient (PRD 5.3).

    System behaviour:
    1. Lookup recipient
    2. Embed unique steganographic watermark
    3. Create child CoCNode via forward_coc_message
    4. Store share record
    """
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    is_owner = str(doc["owner_id"]) == str(user["id"])
    active_share = None

    if not is_owner:
        active_share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not active_share:
            raise HTTPException(403, "Access denied — you cannot share this document")

    recipient = await db.find_one("users", username=req.recipient_username)
    if not recipient:
        raise HTTPException(404, f"User '{req.recipient_username}' not found")

    if str(recipient["id"]) == str(user["id"]):
        raise HTTPException(400, "Cannot share with yourself")

    existing = await db.find_one(
        "file_shares", document_id=doc_id, recipient_id=recipient["id"], status="active"
    )
    if existing:
        raise HTTPException(409, f"Already shared with {req.recipient_username}")

    parent_hash = doc["coc_node_hash"] if is_owner else active_share["child_coc_node_hash"]
    parent_node = await trustflow.storage.get_node(parent_hash)
    if not parent_node:
        # Self-healing: reconstruct missing node for pre-migration uploads
        logger.warning(f"CoC node {parent_hash} not in DB — reconstructing from document metadata")
        parent_node = CoCNode(
            content_hash=doc["content_hash"],
            owner_id=user["peer_id"],
            signing_key=trustflow.system_signing_key,
            recipient_ids=[]
        )
        # Override the auto-generated node_hash to match the one stored in the document record
        parent_node.node_hash = parent_hash
        await trustflow.storage.add_node(parent_node)

    # Read content from native file payload
    file_path = doc["storage_path"] if is_owner else str(
        Path(config.storage_dir) / f"{doc_id}_shared_{user['id']}{Path(doc['filename']).suffix}"
    )
    try:
        async with aiofiles.open(file_path, "r", errors="replace") as f:
            content = await f.read()
    except Exception:
        async with aiofiles.open(file_path, "rb") as f:
            raw = await f.read()
            content = raw.hex()

    child_node, watermarked = await trustflow.share_document(
        owner_peer_id=user["peer_id"],
        parent_node=parent_node,
        recipient_peer_ids=[recipient["peer_id"]],
        content=content,
    )

    wm_path = str(
        Path(config.storage_dir)
        / f"{doc_id}_shared_{recipient['id']}{Path(doc['filename']).suffix}"
    )
    async with aiofiles.open(wm_path, "w", encoding="utf-8") as f:
        await f.write(watermarked)

    share = await db.insert(
        "file_shares",
        {
            "document_id": doc_id,
            "owner_id": user["id"],
            "recipient_id": recipient["id"],
            "child_coc_node_hash": child_node.node_hash,
            "status": "active",
        },
    )

    return ShareResponse(
        id=str(share["id"]),
        document_id=doc_id,
        recipient_username=recipient["username"],
        child_coc_node_hash=child_node.node_hash,
        status="active",
        created_at=str(share["created_at"]),
    )


@router.get("/{doc_id}/trace", response_model=TraceResponse)
async def get_document_trace(doc_id: str, user: dict = Depends(get_current_user)):
    """Return document topology trace; non-owners see flat recipients list."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    is_owner = str(doc["owner_id"]) == str(user["id"])
    if not is_owner:
        share = await db.find_one(
            "file_shares", document_id=doc_id, recipient_id=user["id"], status="active"
        )
        if not share:
            raise HTTPException(403, "Access denied")

    nodes, edges = await trustflow.get_trace_for_document(doc["coc_node_hash"])
    if not nodes and is_owner:
        # Self-healing for trace: if root node is missing, try to reconstruct it for the owner
        logger.warning(f"CoC root node {doc['coc_node_hash']} missing during trace — reconstructing")
        root_node = CoCNode(
            content_hash=doc["content_hash"],
            owner_id=user["peer_id"],
            signing_key=trustflow.system_signing_key,
            recipient_ids=[]
        )
        root_node.node_hash = doc["coc_node_hash"]
        await trustflow.storage.add_node(root_node)
        nodes, edges = await trustflow.get_trace_for_document(doc["coc_node_hash"])

    if not is_owner:
        edges = []
    return TraceResponse(nodes=nodes, edges=edges)


@router.delete("/{doc_id}/share/{target_user_id}")
async def revoke_share(
    doc_id: str, target_user_id: str, user: dict = Depends(get_current_user)
):
    """Revoke a share. Owner only."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if str(doc["owner_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the owner can revoke shares")

    share = await db.find_one(
        "file_shares", document_id=doc_id, recipient_id=target_user_id, status="active"
    )
    if not share:
        raise HTTPException(404, "Share not found")

    await db.update_one(
        "file_shares",
        share["id"],
        status="revoked",
        revoked_at=datetime.now(timezone.utc),
    )

    trustflow.audit_log.log_event(
        "REVOKE_SHARE", user["peer_id"], share["child_coc_node_hash"]
    )

    return {"message": f"Share revoked for user {target_user_id}"}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Move a document to the recycle bin (soft delete)."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] in {"deleted", "recycled"}:
        raise HTTPException(404, "Document not found")

    if str(doc["owner_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the document owner can delete")

    await db.update_one(
        "documents",
        doc_id,
        status="recycled",
        recycled_at=datetime.now(timezone.utc),
    )

    # Suspend all active shares
    shares = await db.find_many("file_shares", document_id=doc_id, status="active")
    for share in shares:
        await db.update_one(
            "file_shares",
            share["id"],
            status="suspended",
            suspended_at=datetime.now(timezone.utc),
        )

    return {
        "message": "Document moved to recycle bin",
        "document_id": doc_id,
        "shares_suspended": len(shares),
    }


@router.post("/{doc_id}/restore")
async def restore_document(
    doc_id: str,
    req: RestoreRequest,
    user: dict = Depends(get_current_user),
):
    """Restore a recycled document, optionally reactivating shares."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] != "recycled":
        raise HTTPException(404, "Document not found")

    if str(doc["owner_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the document owner can restore")

    await db.update_one("documents", doc_id, status="active", recycled_at=None)

    shares = await db.find_many("file_shares", document_id=doc_id, status="suspended")
    reactivated = 0
    if req.restore_access:
        for share in shares:
            await db.update_one(
                "file_shares",
                share["id"],
                status="active",
                suspended_at=None,
            )
            reactivated += 1

    return {
        "message": "Document restored",
        "document_id": doc_id,
        "shares_reactivated": reactivated,
    }


@router.delete("/{doc_id}/purge")
async def purge_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Permanently delete a recycled document and revoke shares."""
    doc = await db.find_one("documents", id=doc_id)
    if not doc or doc["status"] != "recycled":
        raise HTTPException(404, "Document not found")

    if str(doc["owner_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the document owner can purge")

    # Remove legacy peer lookup
    # owner_peer = trustflow.get_peer(user["peer_id"])
    # if not owner_peer:
    #     raise HTTPException(500, "Owner peer not found")

    # node = owner_peer.storage.get_node(doc["coc_node_hash"])
    # if node:
    #     trustflow.delete_document(owner_peer, node)
    # The TrustFlowService.delete_document now takes peer_id and node_hash directly
    if doc["coc_node_hash"]:
        await trustflow.delete_document(user["peer_id"], doc["coc_node_hash"])

    await db.update_one(
        "documents",
        doc_id,
        status="deleted",
        deleted_at=datetime.now(timezone.utc),
    )

    shares = await db.find_many("file_shares", document_id=doc_id)
    for share in shares:
        await db.update_one(
            "file_shares",
            share["id"],
            status="revoked",
            revoked_at=datetime.now(timezone.utc),
        )

    try:
        if os.path.exists(doc["storage_path"]):
            os.remove(doc["storage_path"])
    except Exception:
        pass

    return {
        "message": "Document permanently deleted",
        "document_id": doc_id,
        "shares_revoked": len(shares),
    }
