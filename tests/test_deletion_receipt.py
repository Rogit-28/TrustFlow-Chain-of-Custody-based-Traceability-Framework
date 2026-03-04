"""
Tests for deletion acknowledgment/receipt system.

Tests DeletionReceipt, DeletionTracker, and integration with DeletionEngine.
"""
import pytest
from datetime import datetime, timezone

from coc_framework.core.crypto_core import CryptoCore
from coc_framework.core.deletion_engine import (
    DeletionToken,
    DeletionReceipt,
    DeletionTracker,
    DeletionEngine,
)
from coc_framework.core.audit_log import AuditLog
from coc_framework.interfaces.notification_handler import SilentNotificationHandler
from coc_framework.interfaces.peer_discovery import RegistryPeerDiscovery
from coc_framework.interfaces.storage_backend import InMemoryStorage
from coc_framework.core.coc_node import CoCNode


class TestDeletionReceipt:
    """Tests for DeletionReceipt dataclass."""

    def test_receipt_creation(self):
        """Should create a DeletionReceipt with all fields."""
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-hash-123",
        )
        
        assert receipt.token_hash == "abc123"
        assert receipt.peer_id == "peer-001"
        assert receipt.success is True
        assert receipt.node_hash == "node-hash-123"
        assert receipt.error_message is None
        assert receipt.signature == ""

    def test_receipt_creation_with_error(self):
        """Should create a DeletionReceipt with error message."""
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=False,
            node_hash="node-hash-123",
            error_message="Invalid signature"
        )
        
        assert receipt.success is False
        assert receipt.error_message == "Invalid signature"

    def test_receipt_sign_and_verify(self):
        """Should sign and verify receipt correctly."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-hash-123",
        )
        
        receipt.sign(signing_key)
        
        assert receipt.signature != ""
        assert receipt.verify(verify_key) is True

    def test_receipt_verify_fails_with_wrong_key(self):
        """Verification should fail with different key pair."""
        sk1, vk1 = CryptoCore.generate_keypair()
        sk2, vk2 = CryptoCore.generate_keypair()
        
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-hash-123",
        )
        
        receipt.sign(sk1)
        
        assert receipt.verify(vk2) is False

    def test_receipt_verify_fails_with_tampered_data(self):
        """Verification should fail if receipt data is tampered."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-hash-123",
        )
        
        receipt.sign(signing_key)
        
        # Tamper with the receipt
        receipt.success = False
        
        assert receipt.verify(verify_key) is False

    def test_receipt_to_dict(self):
        """Should serialize receipt to dictionary."""
        timestamp = datetime.now(timezone.utc).isoformat()
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=timestamp,
            success=True,
            node_hash="node-hash-123",
            signature="sig-hex",
            error_message=None
        )
        
        data = receipt.to_dict()
        
        assert data["token_hash"] == "abc123"
        assert data["peer_id"] == "peer-001"
        assert data["timestamp"] == timestamp
        assert data["success"] is True
        assert data["node_hash"] == "node-hash-123"
        assert data["signature"] == "sig-hex"
        assert data["error_message"] is None

    def test_receipt_from_dict(self):
        """Should deserialize dictionary to DeletionReceipt."""
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {
            "token_hash": "abc123",
            "peer_id": "peer-001",
            "timestamp": timestamp,
            "success": False,
            "node_hash": "node-hash-123",
            "signature": "sig-hex",
            "error_message": "Test error"
        }
        
        receipt = DeletionReceipt.from_dict(data)
        
        assert receipt.token_hash == "abc123"
        assert receipt.peer_id == "peer-001"
        assert receipt.timestamp == timestamp
        assert receipt.success is False
        assert receipt.node_hash == "node-hash-123"
        assert receipt.signature == "sig-hex"
        assert receipt.error_message == "Test error"

    def test_receipt_roundtrip_serialization(self):
        """Should roundtrip serialize and deserialize receipt."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        original = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-hash-123",
        )
        original.sign(signing_key)
        
        data = original.to_dict()
        restored = DeletionReceipt.from_dict(data)
        
        assert restored.token_hash == original.token_hash
        assert restored.peer_id == original.peer_id
        assert restored.timestamp == original.timestamp
        assert restored.success == original.success
        assert restored.node_hash == original.node_hash
        assert restored.signature == original.signature
        assert restored.verify(verify_key) is True


class TestDeletionTracker:
    """Tests for DeletionTracker class."""

    def test_tracker_initialization(self):
        """Should initialize with empty state."""
        tracker = DeletionTracker()
        
        assert len(tracker._pending) == 0
        assert len(tracker._receipts) == 0
        assert len(tracker._expected_peers) == 0

    def test_track_deletion(self):
        """Should start tracking a deletion request."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(
            node_hash="node-123",
            originator_id="originator-001"
        )
        token.sign(signing_key)
        
        expected_peers = {"peer-001", "peer-002", "peer-003"}
        token_hash = tracker.track_deletion(token, expected_peers)
        
        assert token_hash is not None
        assert token_hash in tracker._pending
        assert tracker._pending[token_hash] == token
        assert tracker._expected_peers[token_hash] == expected_peers
        assert tracker._receipts[token_hash] == []

    def test_add_receipt(self):
        """Should add receipts for tracked deletion."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001", "peer-002"})
        
        receipt = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-123"
        )
        
        tracker.add_receipt(receipt)
        
        receipts = tracker.get_receipts(token_hash)
        assert len(receipts) == 1
        assert receipts[0].peer_id == "peer-001"

    def test_add_receipt_prevents_duplicates(self):
        """Should not add duplicate receipts from same peer."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001"})
        
        receipt1 = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-123"
        )
        receipt2 = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-123"
        )
        
        tracker.add_receipt(receipt1)
        tracker.add_receipt(receipt2)  # Duplicate
        
        receipts = tracker.get_receipts(token_hash)
        assert len(receipts) == 1

    def test_is_complete_false_when_pending(self):
        """Should return False when some peers haven't acknowledged."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001", "peer-002", "peer-003"})
        
        # Only one peer acknowledges
        receipt = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-123"
        )
        tracker.add_receipt(receipt)
        
        assert tracker.is_complete(token_hash) is False

    def test_is_complete_true_when_all_acknowledged(self):
        """Should return True when all expected peers have acknowledged."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001", "peer-002"})
        
        # All peers acknowledge
        for peer_id in ["peer-001", "peer-002"]:
            receipt = DeletionReceipt(
                token_hash=token_hash,
                peer_id=peer_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                success=True,
                node_hash="node-123"
            )
            tracker.add_receipt(receipt)
        
        assert tracker.is_complete(token_hash) is True

    def test_is_complete_with_empty_expected_peers(self):
        """Should return True when no peers are expected."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, set())
        
        assert tracker.is_complete(token_hash) is True

    def test_get_pending_peers(self):
        """Should return set of peers that haven't acknowledged."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001", "peer-002", "peer-003"})
        
        # Only one peer acknowledges
        receipt = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-002",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-123"
        )
        tracker.add_receipt(receipt)
        
        pending = tracker.get_pending_peers(token_hash)
        
        assert pending == {"peer-001", "peer-003"}

    def test_get_deletion_status(self):
        """Should return comprehensive status of deletion request."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001", "peer-002", "peer-003"})
        
        # Two peers acknowledge - one success, one failure
        success_receipt = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
            node_hash="node-123"
        )
        failure_receipt = DeletionReceipt(
            token_hash=token_hash,
            peer_id="peer-002",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=False,
            node_hash="node-123",
            error_message="Storage error"
        )
        tracker.add_receipt(success_receipt)
        tracker.add_receipt(failure_receipt)
        
        status = tracker.get_deletion_status(token_hash)
        
        assert status["token_hash"] == token_hash
        assert status["token"]["node_hash"] == "node-123"
        assert set(status["expected_peers"]) == {"peer-001", "peer-002", "peer-003"}
        assert len(status["received_receipts"]) == 2
        assert status["pending_peers"] == ["peer-003"]
        assert status["is_complete"] is False
        assert status["success_count"] == 1
        assert status["failure_count"] == 1
        assert status["total_expected"] == 3
        assert status["total_received"] == 2

    def test_get_token(self):
        """Should retrieve the original tracked token."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001"})
        
        retrieved = tracker.get_token(token_hash)
        
        assert retrieved is not None
        assert retrieved.node_hash == token.node_hash
        assert retrieved.originator_id == token.originator_id

    def test_get_token_returns_none_for_unknown(self):
        """Should return None for unknown token hash."""
        tracker = DeletionTracker()
        
        assert tracker.get_token("unknown-hash") is None


class TestDeletionTokenGetHash:
    """Tests for DeletionToken.get_hash() method."""

    def test_get_hash_returns_string(self):
        """get_hash should return a hash string."""
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        
        token_hash = token.get_hash()
        
        assert isinstance(token_hash, str)
        assert len(token_hash) == 64  # SHA-256 hex

    def test_get_hash_deterministic(self):
        """Same token should produce same hash."""
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        
        hash1 = token.get_hash()
        hash2 = token.get_hash()
        
        assert hash1 == hash2

    def test_different_tokens_different_hashes(self):
        """Different tokens should produce different hashes."""
        signing_key, _ = CryptoCore.generate_keypair()
        
        token1 = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token1.sign(signing_key)
        
        token2 = DeletionToken(node_hash="node-456", originator_id="originator-001")
        token2.sign(signing_key)
        
        assert token1.get_hash() != token2.get_hash()


class TestDeletionEngineWithTracker:
    """Integration tests for DeletionEngine with DeletionTracker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.peer_discovery = RegistryPeerDiscovery()
        self.audit_log = AuditLog()
        self.notification_handler = SilentNotificationHandler()
        self.tracker = DeletionTracker()

    def test_engine_init_with_tracker(self):
        """Should initialize DeletionEngine with optional tracker."""
        engine = DeletionEngine(
            network=None,
            audit_log=self.audit_log,
            notification_handler=self.notification_handler,
            peer_discovery=self.peer_discovery,
            tracker=self.tracker
        )
        
        assert engine.tracker is self.tracker

    def test_engine_init_without_tracker(self):
        """Should initialize DeletionEngine without tracker."""
        engine = DeletionEngine(
            network=None,
            audit_log=self.audit_log,
            notification_handler=self.notification_handler,
            peer_discovery=self.peer_discovery
        )
        
        assert engine.tracker is None


class TestErrorReceiptHandling:
    """Tests for error receipt scenarios."""

    def test_receipt_with_error_message_signature(self):
        """Error message should be included in signature verification."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        receipt = DeletionReceipt(
            token_hash="abc123",
            peer_id="peer-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=False,
            node_hash="node-hash-123",
            error_message="Invalid signature"
        )
        
        receipt.sign(signing_key)
        
        # Should verify with error message
        assert receipt.verify(verify_key) is True
        
        # Tampering with error message should fail verification
        receipt.error_message = "Different error"
        assert receipt.verify(verify_key) is False

    def test_tracker_counts_failures(self):
        """Tracker should correctly count failed deletions."""
        tracker = DeletionTracker()
        signing_key, _ = CryptoCore.generate_keypair()
        
        token = DeletionToken(node_hash="node-123", originator_id="originator-001")
        token.sign(signing_key)
        token_hash = tracker.track_deletion(token, {"peer-001", "peer-002", "peer-003"})
        
        # Add various receipts
        receipts_data = [
            ("peer-001", True, None),
            ("peer-002", False, "Invalid signature"),
            ("peer-003", False, "Node not found"),
        ]
        
        for peer_id, success, error in receipts_data:
            receipt = DeletionReceipt(
                token_hash=token_hash,
                peer_id=peer_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                success=success,
                node_hash="node-123",
                error_message=error
            )
            tracker.add_receipt(receipt)
        
        status = tracker.get_deletion_status(token_hash)
        
        assert status["success_count"] == 1
        assert status["failure_count"] == 2
        assert status["is_complete"] is True  # All peers responded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
