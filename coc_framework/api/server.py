"""
TrustFlow REST API Server

FastAPI application that wraps the SimulationEngine, exposing all
chain-of-custody operations over HTTP with WebSocket event streaming.
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from coc_framework.api.schemas import (
    AuditEntry,
    AuditLogResponse,
    CoCNodeResponse,
    CreateMessageRequest,
    CreatePeerRequest,
    DeleteMessageRequest,
    DeletionResponse,
    DetectLeakRequest,
    DistributeSharesRequest,
    ErrorResponse,
    ForwardMessageRequest,
    HealthResponse,
    LeakDetectionResponse,
    MessageCreatedResponse,
    PeerResponse,
    ProvenanceChainResponse,
    ReconstructResponse,
    ReconstructSecretRequest,
    SharesDistributedResponse,
    SimulationStateResponse,
    TimelockRequest,
    TimelockResponse,
)

logger = logging.getLogger(__name__)

# ── Global State ─────────────────────────────────────────────────────────────

# We hold a SimulationEngine instance and supplementary state here.
# The engine is created on startup via the /api/init endpoint or lazily.

_engine = None
_peer_names: Dict[str, str] = {}  # peer_id -> human name
_ws_clients: Set[WebSocket] = set()
_event_log: List[dict] = []  # in-memory API event log for the frontend


def _get_engine():
    global _engine
    if _engine is None:
        _init_default_engine()
    return _engine


def _init_default_engine():
    """Create a default engine with all features enabled."""
    global _engine
    from coc_framework.simulation_engine import SimulationEngine

    scenario = {
        "settings": {
            "num_peers": 0,
            "simulation_duration": 1000,
            "enable_secret_sharing": True,
            "enable_timelock": True,
            "enable_steganography": True,
            "secret_sharing_threshold": 2,
        },
        "events": [],
    }
    _engine = SimulationEngine(scenario, validate_scenario=False, validate_events=False)


async def _broadcast_event(event: dict):
    """Send a real-time event to all connected WebSocket clients."""
    _event_log.append(event)
    dead: List[WebSocket] = []
    message = json.dumps(event, default=str)
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


def _node_to_response(node) -> CoCNodeResponse:
    """Convert a CoCNode to its API response model."""
    d = node.to_dict()
    return CoCNodeResponse(
        schema_version=d["schema_version"],
        node_hash=d["node_hash"],
        content_hash=d["content_hash"],
        parent_hash=d.get("parent_hash"),
        owner_id=d["owner_id"],
        recipient_ids=d.get("recipient_ids", []),
        timestamp=d["timestamp"],
        children_hashes=d.get("children_hashes", []),
        depth=d.get("depth", 0),
        signature=d.get("signature"),
    )


# ── App Lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize the engine. Shutdown: cleanup."""
    _init_default_engine()
    logger.info("TrustFlow API started with all features enabled")
    yield
    global _engine
    if _engine:
        _engine.shutdown()
    logger.info("TrustFlow API shut down")


app = FastAPI(
    title="TrustFlow API",
    description="Chain of Custody Privacy Framework — REST API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Static Files (Frontend) ─────────────────────────────────────────────────

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(_frontend_dir / "index.html"))


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        # Send existing event history
        for event in _event_log:
            await ws.send_text(json.dumps(event, default=str))
        # Keep connection alive
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


# ── Health & Status ──────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health():
    engine = _get_engine()
    return HealthResponse(
        features={
            "secret_sharing": engine.enable_secret_sharing,
            "timelock": engine.enable_timelock,
            "steganography": engine.enable_steganography,
        }
    )


@app.get("/api/state", response_model=SimulationStateResponse, tags=["System"])
async def get_state():
    engine = _get_engine()
    state = engine.get_simulation_state()
    return SimulationStateResponse(
        tick=state["tick"],
        peer_count=len(state["peers"]),
        features=state["features"],
        message_count=len(state["message_registry"]),
        distributed_shares=state["distributed_shares"],
    )


@app.get("/api/events", tags=["System"])
async def get_events():
    """Return all API events for the frontend to replay."""
    return _event_log


# ── Peer Management ─────────────────────────────────────────────────────────

@app.post("/api/peers", response_model=PeerResponse, tags=["Peers"])
async def create_peer(req: CreatePeerRequest):
    engine = _get_engine()
    peer_id = req.peer_id or str(uuid.uuid4())
    name = req.name or peer_id[:8]

    if peer_id in engine.peers:
        raise HTTPException(400, f"Peer '{peer_id}' already exists")

    from coc_framework.core.network_sim import Peer

    peer = Peer(engine.deletion_engine, peer_id=peer_id)
    engine.peers[peer_id] = peer
    engine.network.add_peer(peer)
    _peer_names[peer_id] = name

    event = {
        "type": "PEER_CREATED",
        "peer_id": peer_id,
        "name": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return PeerResponse(
        peer_id=peer_id,
        name=name,
        is_online=peer.online,
        node_count=len(peer.storage.get_all_nodes()),
    )


@app.get("/api/peers", response_model=List[PeerResponse], tags=["Peers"])
async def list_peers():
    engine = _get_engine()
    results = []
    for pid, peer in engine.peers.items():
        results.append(
            PeerResponse(
                peer_id=pid,
                name=_peer_names.get(pid, pid[:8]),
                is_online=peer.online,
                node_count=len(peer.storage.get_all_nodes()),
            )
        )
    return results


@app.get("/api/peers/{peer_id}", response_model=PeerResponse, tags=["Peers"])
async def get_peer(peer_id: str):
    engine = _get_engine()
    peer = engine.peers.get(peer_id)
    if not peer:
        raise HTTPException(404, f"Peer '{peer_id}' not found")
    return PeerResponse(
        peer_id=peer_id,
        name=_peer_names.get(peer_id, peer_id[:8]),
        is_online=peer.online,
        node_count=len(peer.storage.get_all_nodes()),
    )


# ── Messages (Create / Forward / Delete) ─────────────────────────────────────

@app.post("/api/messages", response_model=MessageCreatedResponse, tags=["Messages"])
async def create_message(req: CreateMessageRequest):
    engine = _get_engine()
    originator = engine.peers.get(req.originator_id)
    if not originator:
        raise HTTPException(404, f"Peer '{req.originator_id}' not found")

    for rid in req.recipient_ids:
        if rid not in engine.peers:
            raise HTTPException(404, f"Recipient peer '{rid}' not found")

    message_id = req.message_id or str(uuid.uuid4())

    node = originator.create_coc_root(
        content=req.content, recipient_ids=req.recipient_ids
    )

    engine._message_registry[message_id] = node.node_hash

    # Deliver to recipients by directly storing in their storage
    for recipient_id in req.recipient_ids:
        recipient = engine.peers[recipient_id]
        recipient.storage.add_node(node)
        recipient.storage.add_content(node.content_hash, req.content)

    engine.audit_log.log_event(
        "CREATE_MESSAGE",
        req.originator_id,
        node.node_hash,
        f"Content delivered to {len(req.recipient_ids)} recipients",
    )

    event = {
        "type": "MESSAGE_CREATED",
        "node": node.to_dict(),
        "message_id": message_id,
        "originator_name": _peer_names.get(req.originator_id, req.originator_id[:8]),
        "recipient_names": [
            _peer_names.get(r, r[:8]) for r in req.recipient_ids
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return MessageCreatedResponse(
        node=_node_to_response(node), message_id=message_id
    )


@app.post(
    "/api/messages/{node_hash}/forward",
    response_model=MessageCreatedResponse,
    tags=["Messages"],
)
async def forward_message(node_hash: str, req: ForwardMessageRequest):
    engine = _get_engine()
    sender = engine.peers.get(req.sender_id)
    if not sender:
        raise HTTPException(404, f"Peer '{req.sender_id}' not found")

    parent_node = sender.storage.get_node(node_hash)
    if not parent_node:
        raise HTTPException(404, f"Node '{node_hash}' not found in sender's storage")

    for rid in req.recipient_ids:
        if rid not in engine.peers:
            raise HTTPException(404, f"Recipient peer '{rid}' not found")

    message_id = req.message_id or str(uuid.uuid4())

    # Watermark path
    if req.use_watermark and engine.enable_steganography and engine.stegano_engine:
        content = sender.storage.get_content(parent_node.content_hash)
        if content:
            watermarked = engine.stegano_engine.embed_watermark(
                content=content,
                peer_id=req.sender_id,
                depth=parent_node.depth + 1,
            )
            from coc_framework.core.crypto_core import CryptoCore

            wm_hash = CryptoCore.hash_content(watermarked)
            from coc_framework.core.coc_node import CoCNode

            child_node = CoCNode(
                wm_hash,
                req.sender_id,
                sender.signing_key,
                req.recipient_ids,
                parent_hash=parent_node.node_hash,
                depth=parent_node.depth + 1,
            )
            parent_node.add_child(child_node)
            sender.storage.add_node(child_node)
            sender.storage.add_node(parent_node)
            sender.storage.add_content(wm_hash, watermarked)

            engine._message_registry[message_id] = child_node.node_hash

            for rid in req.recipient_ids:
                recipient = engine.peers[rid]
                recipient.storage.add_node(child_node)
                recipient.storage.add_content(wm_hash, watermarked)

            engine.audit_log.log_event(
                "FORWARD_WATERMARKED",
                req.sender_id,
                child_node.node_hash,
                f"Watermarked forward to {len(req.recipient_ids)} recipients",
            )

            event = {
                "type": "MESSAGE_FORWARDED",
                "node": child_node.to_dict(),
                "parent_hash": node_hash,
                "message_id": message_id,
                "watermarked": True,
                "sender_name": _peer_names.get(req.sender_id, req.sender_id[:8]),
                "recipient_names": [
                    _peer_names.get(r, r[:8]) for r in req.recipient_ids
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await _broadcast_event(event)

            return MessageCreatedResponse(
                node=_node_to_response(child_node), message_id=message_id
            )

    # Regular forward
    child_node = sender.forward_coc_message(
        parent_node=parent_node, recipient_ids=req.recipient_ids
    )

    engine._message_registry[message_id] = child_node.node_hash

    for rid in req.recipient_ids:
        recipient = engine.peers[rid]
        recipient.storage.add_node(child_node)
        content = sender.storage.get_content(child_node.content_hash)
        if content:
            recipient.storage.add_content(child_node.content_hash, content)

    engine.audit_log.log_event(
        "FORWARD_MESSAGE",
        req.sender_id,
        child_node.node_hash,
        f"Forwarded to {len(req.recipient_ids)} recipients",
    )

    event = {
        "type": "MESSAGE_FORWARDED",
        "node": child_node.to_dict(),
        "parent_hash": node_hash,
        "message_id": message_id,
        "watermarked": False,
        "sender_name": _peer_names.get(req.sender_id, req.sender_id[:8]),
        "recipient_names": [_peer_names.get(r, r[:8]) for r in req.recipient_ids],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return MessageCreatedResponse(
        node=_node_to_response(child_node), message_id=message_id
    )


@app.delete(
    "/api/messages/{node_hash}",
    response_model=DeletionResponse,
    tags=["Messages"],
)
async def delete_message(node_hash: str, req: DeleteMessageRequest):
    engine = _get_engine()
    originator = engine.peers.get(req.originator_id)
    if not originator:
        raise HTTPException(404, f"Peer '{req.originator_id}' not found")

    node = originator.storage.get_node(node_hash)
    if not node:
        raise HTTPException(404, f"Node '{node_hash}' not found")

    if node.owner_id != req.originator_id:
        raise HTTPException(403, "Only the node owner can delete it")

    children_count = len(node.children_hashes)
    originator.initiate_deletion(node)

    engine.audit_log.log_event(
        "DELETE_MESSAGE",
        req.originator_id,
        node_hash,
        f"Cascade: {children_count} children",
    )

    event = {
        "type": "MESSAGE_DELETED",
        "node_hash": node_hash,
        "originator_name": _peer_names.get(req.originator_id, req.originator_id[:8]),
        "cascade_count": children_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return DeletionResponse(
        deleted_node_hash=node_hash, cascade_count=children_count
    )


# ── Provenance Chain ─────────────────────────────────────────────────────────

@app.get(
    "/api/messages/{node_hash}/chain",
    response_model=ProvenanceChainResponse,
    tags=["Provenance"],
)
async def get_provenance_chain(node_hash: str):
    """Walk the provenance graph from a given node to the root, collecting all connected nodes."""
    engine = _get_engine()

    # Find the node in any peer's storage
    target_node = None
    target_peer = None
    for peer in engine.peers.values():
        target_node = peer.storage.get_node(node_hash)
        if target_node:
            target_peer = peer
            break

    if not target_node:
        raise HTTPException(404, f"Node '{node_hash}' not found")

    # Walk up to root
    nodes_map: Dict[str, object] = {}
    edges: List[Dict[str, str]] = []

    def _collect(nh: str):
        if nh in nodes_map:
            return
        for p in engine.peers.values():
            n = p.storage.get_node(nh)
            if n:
                nodes_map[nh] = n
                if n.parent_hash:
                    edges.append({"from": n.parent_hash, "to": nh})
                    _collect(n.parent_hash)
                for ch in n.children_hashes:
                    edges.append({"from": nh, "to": ch})
                    _collect(ch)
                break

    _collect(node_hash)

    # Find root
    root_hash = node_hash
    for nh, n in nodes_map.items():
        if not n.parent_hash:
            root_hash = nh
            break

    root_node = nodes_map.get(root_hash, target_node)

    return ProvenanceChainResponse(
        root=_node_to_response(root_node),
        nodes=[_node_to_response(n) for n in nodes_map.values()],
        edges=edges,
    )


# ── All Nodes (for graph rendering) ──────────────────────────────────────────

@app.get("/api/nodes", tags=["Provenance"])
async def get_all_nodes():
    """Return all known nodes and edges across all peers for the graph view."""
    engine = _get_engine()
    nodes_map: Dict[str, dict] = {}
    edges: List[Dict[str, str]] = []

    for peer in engine.peers.values():
        for node in peer.storage.get_all_nodes():
            if node.node_hash not in nodes_map:
                d = node.to_dict()
                d["owner_name"] = _peer_names.get(node.owner_id, node.owner_id[:8])
                nodes_map[node.node_hash] = d
                if node.parent_hash:
                    edges.append({"from": node.parent_hash, "to": node.node_hash})

    return {"nodes": list(nodes_map.values()), "edges": edges}


# ── Audit Log ────────────────────────────────────────────────────────────────

@app.get("/api/audit", response_model=AuditLogResponse, tags=["Audit"])
async def get_audit_log():
    engine = _get_engine()
    entries: List[AuditEntry] = []

    try:
        with open(engine.audit_log.log_file, "r") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            parts = line.split(" | ")
            if len(parts) >= 7:
                entries.append(
                    AuditEntry(
                        event_type=parts[0],
                        actor=parts[1],
                        target=parts[2],
                        timestamp=parts[3],
                        details=parts[4],
                        prev_hash=parts[5],
                        entry_hash=parts[6],
                    )
                )
    except FileNotFoundError:
        pass

    integrity = engine.audit_log.verify_log_integrity()

    return AuditLogResponse(
        entries=entries, integrity_valid=integrity, total_entries=len(entries)
    )


# ── Leak Detection ───────────────────────────────────────────────────────────

@app.post(
    "/api/leak-detect",
    response_model=LeakDetectionResponse,
    tags=["Steganography"],
)
async def detect_leak(req: DetectLeakRequest):
    engine = _get_engine()
    if not engine.enable_steganography or not engine.stegano_engine:
        raise HTTPException(400, "Steganography is not enabled")

    candidate_peers = req.candidate_peer_ids or list(engine.peers.keys())

    # Register known peers with the stegano engine
    for pid in candidate_peers:
        engine.stegano_engine.register_peer(pid)

    result = engine.stegano_engine.extract_watermark(
        content=req.leaked_content, candidate_peers=candidate_peers
    )

    detected_name = None
    if result.success and result.peer_id:
        detected_name = _peer_names.get(result.peer_id, result.peer_id[:8])

    event = {
        "type": "LEAK_DETECTED" if result.success else "LEAK_SCAN_CLEAN",
        "suspected_peer_id": result.peer_id,
        "suspected_peer_name": detected_name,
        "confidence": result.confidence,
        "method": result.method,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return LeakDetectionResponse(
        leak_detected=result.success,
        suspected_peer_id=result.peer_id,
        confidence=result.confidence,
        method=result.method,
        original_content=result.original_content,
    )


# ── Secret Sharing ───────────────────────────────────────────────────────────

@app.post(
    "/api/shares/distribute",
    response_model=SharesDistributedResponse,
    tags=["Secret Sharing"],
)
async def distribute_shares(req: DistributeSharesRequest):
    engine = _get_engine()
    if not engine.enable_secret_sharing or not engine.secret_sharing_engine:
        raise HTTPException(400, "Secret sharing is not enabled")

    originator = engine.peers.get(req.originator_id)
    if not originator:
        raise HTTPException(404, f"Peer '{req.originator_id}' not found")

    for hid in req.holder_ids:
        if hid not in engine.peers:
            raise HTTPException(404, f"Holder peer '{hid}' not found")

    threshold = req.threshold or engine.secret_sharing_engine.default_threshold
    from coc_framework.core.crypto_core import CryptoCore

    content_hash = CryptoCore.hash_content(req.content)

    shares, hmac_key = engine.secret_sharing_engine.split_secret(
        req.content, threshold, len(req.holder_ids)
    )

    for i, hid in enumerate(req.holder_ids):
        engine.secret_sharing_engine.store_share(
            peer_id=hid,
            content_hash=content_hash,
            share=shares[i],
            threshold=threshold,
        )

    engine._distributed_shares[content_hash] = {
        "holder_ids": req.holder_ids,
        "threshold": threshold,
        "hmac_key": hmac_key.hex() if hmac_key else None,
    }

    engine.audit_log.log_event(
        "DISTRIBUTE_SHARES",
        req.originator_id,
        content_hash,
        f"{len(req.holder_ids)} shares, threshold={threshold}",
    )

    event = {
        "type": "SHARES_DISTRIBUTED",
        "content_hash": content_hash,
        "holder_names": [_peer_names.get(h, h[:8]) for h in req.holder_ids],
        "threshold": threshold,
        "total_shares": len(req.holder_ids),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return SharesDistributedResponse(
        content_hash=content_hash,
        total_shares=len(req.holder_ids),
        threshold=threshold,
        holder_ids=req.holder_ids,
    )


@app.post(
    "/api/shares/reconstruct",
    response_model=ReconstructResponse,
    tags=["Secret Sharing"],
)
async def reconstruct_secret(req: ReconstructSecretRequest):
    engine = _get_engine()
    if not engine.enable_secret_sharing or not engine.secret_sharing_engine:
        raise HTTPException(400, "Secret sharing is not enabled")

    if req.requester_id not in engine.peers:
        raise HTTPException(404, f"Peer '{req.requester_id}' not found")

    can = engine.secret_sharing_engine.can_reconstruct(req.content_hash)
    if not can:
        return ReconstructResponse(
            success=False, content_hash=req.content_hash, content=None
        )

    try:
        content = engine.secret_sharing_engine.reconstruct_secret(req.content_hash)
        engine.audit_log.log_event(
            "RECONSTRUCT_SECRET", req.requester_id, req.content_hash, "Success"
        )

        event = {
            "type": "SECRET_RECONSTRUCTED",
            "content_hash": req.content_hash,
            "requester_name": _peer_names.get(req.requester_id, req.requester_id[:8]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await _broadcast_event(event)

        return ReconstructResponse(
            success=True, content=content, content_hash=req.content_hash
        )
    except Exception as e:
        return ReconstructResponse(
            success=False, content_hash=req.content_hash, content=None
        )


# ── Time-Lock ────────────────────────────────────────────────────────────────

@app.post(
    "/api/timelock", response_model=TimelockResponse, tags=["Time-Lock"]
)
async def create_timelock(req: TimelockRequest):
    engine = _get_engine()
    if not engine.enable_timelock or not engine.timelock_engine:
        raise HTTPException(400, "Time-lock encryption is not enabled")

    if req.originator_id not in engine.peers:
        raise HTTPException(404, f"Peer '{req.originator_id}' not found")

    lock_id, ciphertext = engine.timelock_engine.encrypt(
        req.content, req.ttl_seconds
    )

    expires_at = datetime.now(timezone.utc).isoformat()

    engine.audit_log.log_event(
        "TIMELOCK_CREATED",
        req.originator_id,
        lock_id,
        f"TTL={req.ttl_seconds}s",
    )

    event = {
        "type": "TIMELOCK_CREATED",
        "lock_id": lock_id,
        "originator_name": _peer_names.get(req.originator_id, req.originator_id[:8]),
        "ttl_seconds": req.ttl_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast_event(event)

    return TimelockResponse(lock_id=lock_id, expires_at=expires_at)


# ── Entry Point ──────────────────────────────────────────────────────────────

def main():
    import uvicorn

    uvicorn.run(
        "coc_framework.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
