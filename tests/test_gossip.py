"""
Tests for TrustFlow Gossip Protocol

Tests cover:
- GossipEnvelope sign/verify functionality
- Timestamp validation for replay attack prevention
- MessageCache deduplication
- Peer key management
"""

import pytest
import time
import json
import hashlib
from nacl.signing import SigningKey

from coc_framework.network.gossip import (
    GossipEnvelope,
    MessageCache,
    PeerInfo,
    GossipSignatureError,
    GossipTimestampError,
    DEFAULT_TTL,
    DEFAULT_CACHE_SIZE,
    DEFAULT_CACHE_TTL,
)
from coc_framework.network.protocol import (
    HeartbeatMessage,
    PeerStatus,
    MESSAGE_MAX_AGE_SECONDS,
    MESSAGE_MAX_FUTURE_SECONDS,
)


class TestGossipEnvelope:
    """Tests for GossipEnvelope cryptographic wrapper."""
    
    @pytest.fixture
    def keypair(self):
        """Generate a signing keypair."""
        signing_key = SigningKey.generate()
        return signing_key, signing_key.verify_key
    
    @pytest.fixture
    def sample_payload(self):
        """Create a sample payload."""
        return {"sender_id": "peer_A", "msg_type": "heartbeat", "data": "test"}
    
    def test_sign_creates_signature(self, keypair, sample_payload):
        """sign() should create a non-empty signature."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A",
            ttl=DEFAULT_TTL
        )
        
        assert envelope.signature == ""
        envelope.sign(signing_key)
        assert envelope.signature != ""
        assert len(envelope.signature) > 0
    
    def test_verify_valid_signature(self, keypair, sample_payload):
        """verify() should return True for valid signature."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A"
        )
        envelope.sign(signing_key)
        
        assert envelope.verify(verify_key) is True
    
    def test_verify_invalid_signature_wrong_key(self, keypair, sample_payload):
        """verify() should return False for wrong verification key."""
        signing_key, verify_key = keypair
        wrong_signing_key = SigningKey.generate()
        wrong_verify_key = wrong_signing_key.verify_key
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A"
        )
        envelope.sign(signing_key)
        
        assert envelope.verify(wrong_verify_key) is False
    
    def test_verify_tampered_payload(self, keypair, sample_payload):
        """verify() should return False if payload is tampered."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A"
        )
        envelope.sign(signing_key)
        
        # Tamper with payload
        envelope.payload = {"tampered": True}
        
        assert envelope.verify(verify_key) is False
    
    def test_verify_tampered_origin_id(self, keypair, sample_payload):
        """verify() should return False if origin_id is tampered."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A"
        )
        envelope.sign(signing_key)
        
        # Tamper with origin_id
        envelope.origin_id = "peer_EVIL"
        
        assert envelope.verify(verify_key) is False
    
    def test_verify_tampered_msg_id(self, keypair, sample_payload):
        """verify() should return False if msg_id is tampered."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A"
        )
        envelope.sign(signing_key)
        
        # Tamper with msg_id
        envelope.msg_id = "tampered_id"
        
        assert envelope.verify(verify_key) is False
    
    def test_verify_empty_signature(self, keypair, sample_payload):
        """verify() should return False for empty signature."""
        _, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A",
            signature=""  # No signature
        )
        
        assert envelope.verify(verify_key) is False
    
    def test_serialization_roundtrip(self, keypair, sample_payload):
        """Envelope should serialize and deserialize correctly."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A",
            ttl=8,
            path=["peer_A", "peer_B"]
        )
        envelope.sign(signing_key)
        
        # Serialize and deserialize
        data = envelope.to_bytes()
        restored = GossipEnvelope.from_bytes(data)
        
        assert restored.msg_id == envelope.msg_id
        assert restored.origin_id == envelope.origin_id
        assert restored.ttl == envelope.ttl
        assert restored.path == envelope.path
        assert restored.signature == envelope.signature
        assert restored.verify(verify_key) is True
    
    def test_preserved_signature_after_forwarding(self, keypair, sample_payload):
        """Signature should remain valid after relaying peer modifies TTL/path."""
        signing_key, verify_key = keypair
        
        envelope = GossipEnvelope(
            msg_id="test_msg_001",
            payload=sample_payload,
            origin_id="peer_A",
            ttl=10
        )
        envelope.sign(signing_key)
        original_signature = envelope.signature
        
        # Simulate forwarding: decrement TTL and add to path
        envelope.decrement_ttl()
        envelope.add_to_path("peer_B")
        
        # Signature should still be valid (doesn't cover TTL/path)
        assert envelope.signature == original_signature
        assert envelope.verify(verify_key) is True


class TestGossipTimestampValidation:
    """Tests for GossipEnvelope timestamp validation."""
    
    @pytest.fixture
    def sample_payload(self):
        return {"test": "data"}
    
    def test_valid_current_timestamp(self, sample_payload):
        """Current timestamp should be valid."""
        envelope = GossipEnvelope(
            msg_id="test",
            payload=sample_payload,
            origin_id="peer_A",
            timestamp=time.time()
        )
        
        valid, error = envelope.validate_timestamp()
        
        assert valid is True
        assert error == ""
    
    def test_valid_recent_timestamp(self, sample_payload):
        """Recent timestamp should be valid."""
        recent = time.time() - (MESSAGE_MAX_AGE_SECONDS / 2)
        envelope = GossipEnvelope(
            msg_id="test",
            payload=sample_payload,
            origin_id="peer_A",
            timestamp=recent
        )
        
        valid, error = envelope.validate_timestamp()
        
        assert valid is True
    
    def test_invalid_old_timestamp(self, sample_payload):
        """Old timestamp should be invalid."""
        old = time.time() - (MESSAGE_MAX_AGE_SECONDS + 100)
        envelope = GossipEnvelope(
            msg_id="test",
            payload=sample_payload,
            origin_id="peer_A",
            timestamp=old
        )
        
        valid, error = envelope.validate_timestamp()
        
        assert valid is False
        assert "too old" in error.lower()
    
    def test_valid_slight_future_timestamp(self, sample_payload):
        """Slight future timestamp should be valid (clock skew tolerance)."""
        future = time.time() + (MESSAGE_MAX_FUTURE_SECONDS / 2)
        envelope = GossipEnvelope(
            msg_id="test",
            payload=sample_payload,
            origin_id="peer_A",
            timestamp=future
        )
        
        valid, error = envelope.validate_timestamp()
        
        assert valid is True
    
    def test_invalid_far_future_timestamp(self, sample_payload):
        """Far future timestamp should be invalid."""
        far_future = time.time() + (MESSAGE_MAX_FUTURE_SECONDS + 100)
        envelope = GossipEnvelope(
            msg_id="test",
            payload=sample_payload,
            origin_id="peer_A",
            timestamp=far_future
        )
        
        valid, error = envelope.validate_timestamp()
        
        assert valid is False
        assert "future" in error.lower()


class TestGossipTTL:
    """Tests for TTL management."""
    
    def test_decrement_ttl_returns_true_when_positive(self):
        """decrement_ttl should return True when TTL remains positive."""
        envelope = GossipEnvelope(
            msg_id="test",
            payload={},
            origin_id="peer_A",
            ttl=5
        )
        
        result = envelope.decrement_ttl()
        
        assert result is True
        assert envelope.ttl == 4
    
    def test_decrement_ttl_returns_false_when_zero(self):
        """decrement_ttl should return False when TTL reaches zero."""
        envelope = GossipEnvelope(
            msg_id="test",
            payload={},
            origin_id="peer_A",
            ttl=1
        )
        
        result = envelope.decrement_ttl()
        
        assert result is False
        assert envelope.ttl == 0
    
    def test_add_to_path(self):
        """add_to_path should append peer to path list."""
        envelope = GossipEnvelope(
            msg_id="test",
            payload={},
            origin_id="peer_A",
            path=["peer_A"]
        )
        
        envelope.add_to_path("peer_B")
        envelope.add_to_path("peer_C")
        
        assert envelope.path == ["peer_A", "peer_B", "peer_C"]


class TestMessageCache:
    """Tests for MessageCache deduplication."""
    
    def test_has_seen_returns_false_for_new_message(self):
        """has_seen should return False for unseen message."""
        cache = MessageCache()
        
        assert cache.has_seen("msg_001") is False
    
    def test_has_seen_returns_true_after_mark_seen(self):
        """has_seen should return True after marking message as seen."""
        cache = MessageCache()
        
        cache.mark_seen("msg_001")
        
        assert cache.has_seen("msg_001") is True
    
    def test_multiple_messages(self):
        """Cache should track multiple messages correctly."""
        cache = MessageCache()
        
        cache.mark_seen("msg_001")
        cache.mark_seen("msg_002")
        cache.mark_seen("msg_003")
        
        assert cache.has_seen("msg_001") is True
        assert cache.has_seen("msg_002") is True
        assert cache.has_seen("msg_003") is True
        assert cache.has_seen("msg_004") is False
    
    def test_expired_message_not_seen(self):
        """Expired message should not be considered seen."""
        cache = MessageCache(ttl_seconds=0.1)  # 100ms TTL
        
        cache.mark_seen("msg_001")
        time.sleep(0.2)  # Wait for expiry
        
        assert cache.has_seen("msg_001") is False
    
    def test_get_recent_ids(self):
        """get_recent_ids should return most recent message IDs."""
        cache = MessageCache()
        
        for i in range(5):
            cache.mark_seen(f"msg_{i:03d}")
            time.sleep(0.01)  # Small delay to ensure different timestamps
        
        recent = cache.get_recent_ids(3)
        
        assert len(recent) == 3
        # Most recent should be first
        assert "msg_004" in recent
    
    def test_max_size_eviction(self):
        """Cache should evict oldest entries when max size exceeded."""
        cache = MessageCache(max_size=5, ttl_seconds=300)
        
        # Add more than max size
        for i in range(10):
            cache.mark_seen(f"msg_{i:03d}")
        
        # Force cleanup
        cache._last_cleanup = 0
        cache._maybe_cleanup()
        
        # Should have at most max_size entries
        assert len(cache._cache) <= 5


class TestPeerInfo:
    """Tests for PeerInfo dataclass."""
    
    def test_update_last_seen(self):
        """update_last_seen should update the timestamp."""
        info = PeerInfo(
            peer_id="peer_A",
            address="tcp://127.0.0.1:5000",
            last_seen=time.time() - 100
        )
        
        old_time = info.last_seen
        info.update_last_seen()
        
        assert info.last_seen > old_time
    
    def test_is_stale_returns_true_for_old_peer(self):
        """is_stale should return True for peer not seen within timeout."""
        info = PeerInfo(
            peer_id="peer_A",
            address="tcp://127.0.0.1:5000",
            last_seen=time.time() - 1000
        )
        
        assert info.is_stale(timeout=10) is True
    
    def test_is_stale_returns_false_for_recent_peer(self):
        """is_stale should return False for recently seen peer."""
        info = PeerInfo(
            peer_id="peer_A",
            address="tcp://127.0.0.1:5000",
            last_seen=time.time()
        )
        
        assert info.is_stale(timeout=10) is False
    
    def test_default_status_is_unknown(self):
        """Default status should be UNKNOWN."""
        info = PeerInfo(
            peer_id="peer_A",
            address="tcp://127.0.0.1:5000"
        )
        
        assert info.status == PeerStatus.UNKNOWN
