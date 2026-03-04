"""Pydantic schemas for TrustFlow API request/response validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────────────

class CreatePeerRequest(BaseModel):
    peer_id: Optional[str] = Field(None, description="Optional custom peer ID. Auto-generated if omitted.")
    name: Optional[str] = Field(None, description="Human-readable peer name (e.g. 'Alice')")


class CreateMessageRequest(BaseModel):
    originator_id: str = Field(..., description="Peer ID of the message creator")
    content: str = Field(..., description="Message content text")
    recipient_ids: List[str] = Field(..., description="List of recipient peer IDs")
    message_id: Optional[str] = Field(None, description="Optional human-readable message ID")


class ForwardMessageRequest(BaseModel):
    sender_id: str = Field(..., description="Peer ID forwarding the message")
    recipient_ids: List[str] = Field(..., description="List of new recipient peer IDs")
    use_watermark: bool = Field(False, description="Whether to embed steganographic watermark")
    message_id: Optional[str] = Field(None, description="Optional ID for the new forwarded message")


class DeleteMessageRequest(BaseModel):
    originator_id: str = Field(..., description="Peer ID initiating deletion (must be node owner)")


class DetectLeakRequest(BaseModel):
    leaked_content: str = Field(..., description="The suspected leaked text")
    candidate_peer_ids: Optional[List[str]] = Field(None, description="Narrow down suspects")


class TimelockRequest(BaseModel):
    originator_id: str = Field(..., description="Peer ID creating the time-lock")
    content: str = Field(..., description="Content to time-lock")
    ttl_seconds: float = Field(..., description="Time-to-live in seconds")


class DistributeSharesRequest(BaseModel):
    originator_id: str = Field(..., description="Peer ID distributing shares")
    content: str = Field(..., description="Content to split into shares")
    holder_ids: List[str] = Field(..., description="Peer IDs to hold shares")
    threshold: Optional[int] = Field(None, description="Minimum shares to reconstruct")


class ReconstructSecretRequest(BaseModel):
    requester_id: str = Field(..., description="Peer ID requesting reconstruction")
    content_hash: str = Field(..., description="Hash of the content to reconstruct")


# ── Response Schemas ─────────────────────────────────────────────────────────

class PeerResponse(BaseModel):
    peer_id: str
    name: Optional[str] = None
    is_online: bool = True
    node_count: int = 0


class CoCNodeResponse(BaseModel):
    schema_version: int
    node_hash: str
    content_hash: str
    parent_hash: Optional[str] = None
    owner_id: str
    recipient_ids: List[str]
    timestamp: str
    children_hashes: List[str]
    depth: int
    signature: Optional[str] = None


class MessageCreatedResponse(BaseModel):
    success: bool = True
    node: CoCNodeResponse
    message_id: Optional[str] = None


class ProvenanceChainResponse(BaseModel):
    root: CoCNodeResponse
    nodes: List[CoCNodeResponse]
    edges: List[Dict[str, str]]  # [{"from": hash, "to": hash}]


class DeletionResponse(BaseModel):
    success: bool = True
    deleted_node_hash: str
    cascade_count: int = 0


class AuditEntry(BaseModel):
    event_type: str
    actor: str
    target: str
    timestamp: str
    details: str
    prev_hash: str
    entry_hash: str


class AuditLogResponse(BaseModel):
    entries: List[AuditEntry]
    integrity_valid: bool
    total_entries: int


class LeakDetectionResponse(BaseModel):
    leak_detected: bool
    suspected_peer_id: Optional[str] = None
    confidence: float = 0.0
    method: str = "none"
    original_content: Optional[str] = None


class TimelockResponse(BaseModel):
    success: bool = True
    lock_id: str
    expires_at: str


class SharesDistributedResponse(BaseModel):
    success: bool = True
    content_hash: str
    total_shares: int
    threshold: int
    holder_ids: List[str]


class ReconstructResponse(BaseModel):
    success: bool
    content: Optional[str] = None
    content_hash: str
    shares_used: int = 0


class SimulationStateResponse(BaseModel):
    tick: int
    peer_count: int
    features: Dict[str, bool]
    message_count: int
    distributed_shares: List[str]


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    tests_passing: int = 464
    features: Dict[str, bool] = {}


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
