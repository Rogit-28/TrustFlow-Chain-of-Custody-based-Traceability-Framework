"""Admin dashboard routes (PRD 5.8).

- GET  /admin/graph       — CoC graph snapshot
- GET  /admin/peers       — Peer status
- POST /admin/verify-log  — Audit log integrity check
- POST /admin/detect-leak — Watermark attribution
- WS   /ws/admin          — Real-time event feed
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from trustdocs.auth.dependencies import get_current_user
from trustdocs.trustflow_service import trustflow
from trustdocs import database as db


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

_admin_ws_clients: Set[WebSocket] = set()


# ── Models ───────────────────────────────────────────────────────────────────


class PeerStatusResponse(BaseModel):
    peer_id: str
    is_online: bool


class GraphResponse(BaseModel):
    nodes: List[dict]
    edges: List[dict]


class IntegrityResponse(BaseModel):
    valid: bool
    chain_length: int


class PathEdge(BaseModel):
    from_node: str
    to_node: str


class GraphPath(BaseModel):
    nodes: List[str]
    edges: List[PathEdge]


class GraphPathResponse(BaseModel):
    mode: str
    source: str
    target: str
    path_count: int
    truncated: bool = False
    paths: List[GraphPath]


class LeakDetectRequest(BaseModel):
    content: str
    candidate_peer_ids: Optional[List[str]] = None


class LeakDetectResponse(BaseModel):
    leak_detected: bool
    suspected_peer_id: Optional[str] = None
    confidence: float = 0.0
    method: Optional[str] = None


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/peers", response_model=List[PeerStatusResponse])
async def list_peers():
    """Peer status panel: online/offline for all registered peers."""
    peers = []
    users = await db.find_many("users")
    now = datetime.now(timezone.utc)
    for u in users:
        is_online = False
        last_seen = u.get("last_seen_at")
        if last_seen:
            # Handle string fallback if SQLite/in-memory, datetime if asyncpg
            if isinstance(last_seen, str):
                last_seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            
            # Ensure timezone awareness for comparison
            if not last_seen.tzinfo:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
                
            if now - last_seen < timedelta(minutes=2):
                is_online = True
                
        peers.append(
            PeerStatusResponse(
                peer_id=u["peer_id"],
                is_online=is_online,
            )
        )
    return peers


@router.get("/graph", response_model=GraphResponse)
async def get_graph(user: dict = Depends(get_current_user)):
    """CoC graph snapshot for vis.js rendering (admin-only)."""
    nodes, edges = await trustflow.get_all_nodes()
    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/graph/me", response_model=GraphResponse)
async def get_my_graph(user: dict = Depends(get_current_user)):
    """User-scoped CoC graph for current user's peer."""
    nodes, edges = await trustflow.get_graph_for_peer(user["peer_id"])
    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/graph/path", response_model=GraphPathResponse)
async def get_graph_path(
    source: str,
    target: str,
    mode: str = "shortest",
    scope: str = "my",
    document_id: Optional[str] = None,
    max_paths: int = 25,
    max_depth: int = 16,
    user: dict = Depends(get_current_user),
):
    """Find directed path(s) in peer graph or document trace graph.

    Scope options:
    - my: current user's visible graph
    - file: single document trace graph, requires document_id
    """
    if mode not in {"shortest", "all"}:
        raise HTTPException(400, "mode must be 'shortest' or 'all'")
    if scope not in {"my", "file"}:
        raise HTTPException(400, "scope must be 'my' or 'file'")

    if scope == "my":
        result = await trustflow.get_graph_paths_for_peer(
            peer_id=user["peer_id"],
            source=source,
            target=target,
            mode=mode,
            max_paths=max_paths,
            max_depth=max_depth,
        )
    else:
        if not document_id:
            raise HTTPException(400, "document_id is required for scope='file'")

        doc = await db.find_one("documents", id=document_id)
        if not doc or doc["status"] in {"deleted", "recycled"}:
            raise HTTPException(404, "Document not found")

        is_owner = str(doc["owner_id"]) == str(user["id"])
        if not is_owner:
            share = await db.find_one(
                "file_shares",
                document_id=document_id,
                recipient_id=user["id"],
                status="active",
            )
            if not share:
                raise HTTPException(403, "Access denied")

        result = await trustflow.get_graph_paths_for_document(
            root_hash=doc["coc_node_hash"],
            source=source,
            target=target,
            mode=mode,
            max_paths=max_paths,
            max_depth=max_depth,
        )

    if result.get("error") == "source_or_target_not_visible":
        raise HTTPException(404, "Source or target node is not visible in this graph")

    response_paths = []
    for path in result.get("paths", []):
        response_paths.append(
            GraphPath(
                nodes=path["nodes"],
                edges=[
                    PathEdge(from_node=edge["from"], to_node=edge["to"])
                    for edge in path["edges"]
                ],
            )
        )

    return GraphPathResponse(
        mode=result["mode"],
        source=result["source"],
        target=result["target"],
        path_count=result["path_count"],
        truncated=result.get("truncated", False),
        paths=response_paths,
    )


@router.post("/verify-log", response_model=IntegrityResponse)
async def verify_log(user: dict = Depends(get_current_user)):
    """Verify audit log integrity — hash chain check."""
    valid = trustflow.audit_log.verify_log_integrity()
    # Count entries
    try:
        with open(trustflow.audit_log.log_file, "r") as f:
            lines = [l for l in f.readlines() if l.strip() and not l.startswith("#")]
        chain_length = len(lines)
    except FileNotFoundError:
        chain_length = 0

    return IntegrityResponse(valid=valid, chain_length=chain_length)


@router.post("/detect-leak", response_model=LeakDetectResponse)
async def detect_leak(req: LeakDetectRequest, user: dict = Depends(get_current_user)):
    """Watermark attribution tool. Admin pastes suspected leaked content."""
    candidate_peer_ids = req.candidate_peer_ids
    if not candidate_peer_ids:
        users = await db.find_many("users")
        candidate_peer_ids = [u["peer_id"] for u in users]
    result = trustflow.detect_leak(req.content, candidate_peer_ids)

    return LeakDetectResponse(
        leak_detected=result.success,
        suspected_peer_id=result.peer_id if result.success else None,
        confidence=result.confidence,
        method=result.method,
    )


# ── Admin WebSocket ──────────────────────────────────────────────────────────


async def admin_websocket(ws: WebSocket):
    """Real-time event feed for admin dashboard."""
    await ws.accept()
    _admin_ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # Keep alive
    except WebSocketDisconnect:
        pass
    finally:
        _admin_ws_clients.discard(ws)


async def broadcast_admin_event(event: dict):
    """Send event to all connected admin WebSocket clients."""
    dead = []
    message = json.dumps(event, default=str)
    for ws in _admin_ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _admin_ws_clients.discard(ws)
