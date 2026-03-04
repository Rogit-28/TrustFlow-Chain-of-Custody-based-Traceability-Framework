from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Dict, Optional, Set, List, Any
import hashlib
import secrets
import time
from .crypto_core import CryptoCore
from .logging import deletion_logger, peer_logger
from coc_framework.interfaces.storage_backend import ContentTombstone, DEFAULT_TOMBSTONE_GRACE_SECONDS

if TYPE_CHECKING:
    from .network_sim import Peer
    from .coc_node import CoCNode


class ReplayAttackError(Exception):
    pass


class TokenExpiredError(Exception):
    pass


TOKEN_VALIDITY_SECONDS = 300


@dataclass
class DeletionToken:
    """Cryptographically signed deletion token with nonce, expiration, and signature."""
    node_hash: str
    originator_id: str
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""

    def sign(self, signing_key):
        self.signature = CryptoCore.sign_message(signing_key, self._get_signing_data()).hex()

    def _get_signing_data(self) -> str:
        return f"{self.node_hash}|{self.originator_id}|{self.nonce}|{self.timestamp}"

    def get_hash(self) -> str:
        token_data = f"{self.node_hash}|{self.originator_id}|{self.nonce}|{self.timestamp}|{self.signature}"
        return hashlib.sha256(token_data.encode("utf-8")).hexdigest()

    def is_expired(self, validity_seconds: int = TOKEN_VALIDITY_SECONDS) -> bool:
        try:
            token_time = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - token_time) > timedelta(seconds=validity_seconds)
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> DeletionToken:
        return DeletionToken(**data)


@dataclass
class DeletionReceipt:
    """Receipt acknowledging processing of a deletion token."""
    token_hash: str
    peer_id: str
    timestamp: str
    success: bool
    node_hash: str
    signature: str = ""
    error_message: Optional[str] = None

    def _get_data_to_sign(self) -> str:
        error_part = self.error_message if self.error_message else ""
        return f"{self.token_hash}|{self.peer_id}|{self.timestamp}|{self.success}|{self.node_hash}|{error_part}"

    def sign(self, signing_key) -> None:
        self.signature = CryptoCore.sign_message(signing_key, self._get_data_to_sign()).hex()

    def verify(self, verify_key) -> bool:
        if not self.signature:
            return False
        try:
            return CryptoCore.verify_signature(verify_key, self._get_data_to_sign(), bytes.fromhex(self.signature))
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> DeletionReceipt:
        return DeletionReceipt(**data)


class ProcessedTokenCache:
    """Cache of processed token hashes for replay attack prevention with time-based eviction."""
    
    def __init__(self, max_age_seconds: int = TOKEN_VALIDITY_SECONDS * 2):
        self._processed: Dict[str, float] = {}
        self._max_age = max_age_seconds
        self._last_cleanup = time.time()
        self._cleanup_interval = 60
    
    def is_processed(self, token_hash: str) -> bool:
        self._maybe_cleanup()
        return token_hash in self._processed
    
    def mark_processed(self, token_hash: str) -> None:
        self._processed[token_hash] = time.time()
        self._maybe_cleanup()
    
    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        cutoff = now - self._max_age
        self._processed = {h: ts for h, ts in self._processed.items() if ts > cutoff}
        self._last_cleanup = now
    
    def clear(self) -> None:
        self._processed.clear()


class DeletionTracker:
    """Tracks deletion requests and their acknowledgment receipts."""

    def __init__(self):
        self._pending: Dict[str, DeletionToken] = {}
        self._receipts: Dict[str, List[DeletionReceipt]] = {}
        self._expected_peers: Dict[str, Set[str]] = {}

    def track_deletion(self, token: DeletionToken, expected_peers: Set[str]) -> str:
        token_hash = token.get_hash()
        self._pending[token_hash] = token
        self._receipts[token_hash] = []
        self._expected_peers[token_hash] = expected_peers
        return token_hash

    def add_receipt(self, receipt: DeletionReceipt) -> None:
        token_hash = receipt.token_hash
        if token_hash not in self._receipts:
            return
        existing_peers = {r.peer_id for r in self._receipts[token_hash]}
        if receipt.peer_id in existing_peers:
            return
        self._receipts[token_hash].append(receipt)

    def get_receipts(self, token_hash: str) -> List[DeletionReceipt]:
        return self._receipts.get(token_hash, [])

    def get_token(self, token_hash: str) -> Optional[DeletionToken]:
        return self._pending.get(token_hash)

    def is_complete(self, token_hash: str) -> bool:
        if token_hash not in self._expected_peers:
            return False
        expected = self._expected_peers[token_hash]
        if not expected:
            return True
        received_peers = {r.peer_id for r in self._receipts.get(token_hash, [])}
        return expected.issubset(received_peers)

    def get_pending_peers(self, token_hash: str) -> Set[str]:
        if token_hash not in self._expected_peers:
            return set()
        expected = self._expected_peers[token_hash]
        received = {r.peer_id for r in self._receipts.get(token_hash, [])}
        return expected - received

    def get_deletion_status(self, token_hash: str) -> Dict[str, Any]:
        token = self._pending.get(token_hash)
        receipts = self._receipts.get(token_hash, [])
        expected = self._expected_peers.get(token_hash, set())
        pending = self.get_pending_peers(token_hash)
        success_count = sum(1 for r in receipts if r.success)
        failure_count = sum(1 for r in receipts if not r.success)
        return {
            "token_hash": token_hash,
            "token": token.to_dict() if token else None,
            "expected_peers": list(expected),
            "received_receipts": [r.to_dict() for r in receipts],
            "pending_peers": list(pending),
            "is_complete": self.is_complete(token_hash),
            "success_count": success_count,
            "failure_count": failure_count,
            "total_expected": len(expected),
            "total_received": len(receipts),
        }


class DeletionEngine:
    """Engine for processing deletion tokens with replay attack protection and cascade deletion."""
    
    def __init__(
        self, 
        network, 
        audit_log, 
        notification_handler, 
        peer_discovery, 
        tracker: Optional[DeletionTracker] = None,
        token_validity_seconds: int = TOKEN_VALIDITY_SECONDS,
        tombstone_grace_seconds: int = DEFAULT_TOMBSTONE_GRACE_SECONDS
    ):
        self.network = network
        self.audit_log = audit_log
        self.notification_handler = notification_handler
        self.peer_discovery = peer_discovery
        self.tracker = tracker
        self.token_validity_seconds = token_validity_seconds
        self.tombstone_grace_seconds = tombstone_grace_seconds
        self._processed_tokens: Dict[str, ProcessedTokenCache] = {}
        self._log = deletion_logger()
        self._log.info("Deletion Engine initialized")

    def _get_token_cache(self, peer_id: str) -> ProcessedTokenCache:
        if peer_id not in self._processed_tokens:
            self._processed_tokens[peer_id] = ProcessedTokenCache(
                max_age_seconds=self.token_validity_seconds * 2
            )
        return self._processed_tokens[peer_id]

    def issue_token(self, node: CoCNode, originator: Peer) -> DeletionToken:
        if node.owner_id != originator.peer_id:
            raise PermissionError("Only the owner of a node can issue a deletion token.")
        token = DeletionToken(node_hash=node.node_hash, originator_id=originator.peer_id)
        token.sign(originator.signing_key)
        peer_log = peer_logger(originator.peer_id)
        peer_log.info("Issued deletion token", node_hash=node.node_hash[:8])
        self.audit_log.log_event("DELETE_ISSUE", originator.peer_id, f"Node: {node.node_hash}")
        return token

    def process_token(self, token: DeletionToken, receiving_peer: Peer) -> bool:
        """Process a deletion token. Raises ReplayAttackError or TokenExpiredError on failure."""
        token_hash = token.get_hash()
        token_cache = self._get_token_cache(receiving_peer.peer_id)
        
        if token_cache.is_processed(token_hash):
            self._log.warning("Replay attack detected", token_hash=token_hash[:16])
            self.audit_log.log_event(
                "DELETE_FAIL", receiving_peer.peer_id, 
                f"Node: {token.node_hash}", "Replay attack detected"
            )
            raise ReplayAttackError(f"Token {token_hash[:16]} has already been processed")
        
        if token.is_expired(self.token_validity_seconds):
            self._log.warning("Token expired", token_hash=token_hash[:16])
            self.audit_log.log_event(
                "DELETE_FAIL", receiving_peer.peer_id,
                f"Node: {token.node_hash}", "Token expired"
            )
            raise TokenExpiredError(f"Token {token_hash[:16]} has expired")
        
        token_cache.mark_processed(token_hash)
        
        originator = self.peer_discovery.find_peer(token.originator_id)
        if not originator:
            self._log.warning("Originator not found, cannot verify token", originator_id=token.originator_id)
            return False

        token_data = token._get_signing_data()
        if not CryptoCore.verify_signature(originator.verify_key, token_data, bytes.fromhex(token.signature)):
            self._log.warning("Invalid signature for deletion token")
            self.audit_log.log_event("DELETE_FAIL", receiving_peer.peer_id, f"Node: {token.node_hash}", "Invalid signature")
            return False

        node_to_delete = receiving_peer.storage.get_node(token.node_hash)
        if not node_to_delete:
            return False

        peer_log = peer_logger(receiving_peer.peer_id)
        peer_log.info("Processing deletion token", node_hash=token.node_hash[:8])

        children_to_delete = [
            child_node for child_hash in node_to_delete.children_hashes
            if (child_node := receiving_peer.storage.get_node(child_hash)) and child_node.owner_id == receiving_peer.peer_id
        ]

        receiving_peer.storage.remove_node(node_to_delete.node_hash)
        if not receiving_peer.storage.is_content_referenced(node_to_delete.content_hash):
            receiving_peer.storage.remove_content(node_to_delete.content_hash)
            # Create tombstone to prevent race conditions with in-flight forwards
            now = datetime.now(timezone.utc)
            tombstone = ContentTombstone(
                content_hash=node_to_delete.content_hash,
                deleted_at=now.isoformat(),
                delete_after=(now + timedelta(seconds=self.tombstone_grace_seconds)).isoformat(),
                originator_id=token.originator_id,
                node_hash=node_to_delete.node_hash,
            )
            receiving_peer.storage.add_tombstone(tombstone)
            self._log.info("Tombstone created", content_hash=node_to_delete.content_hash[:16])

        self.audit_log.log_event("DELETE_SUCCESS", receiving_peer.peer_id, f"Node: {node_to_delete.node_hash}")
        peer_log.info("Deleted node", node_hash=node_to_delete.node_hash[:8])
        self.notification_handler.on_deletion_requested(receiving_peer.peer_id, token.node_hash, token.originator_id)

        for child in children_to_delete:
            receiving_peer.initiate_deletion(child)
        
        return True

    def clear_token_cache(self, peer_id: Optional[str] = None) -> None:
        if peer_id:
            if peer_id in self._processed_tokens:
                self._processed_tokens[peer_id].clear()
        else:
            self._processed_tokens.clear()
