"""
Tests for TrustFlow Network Protocol

Tests cover:
- SignedEnvelope sign/verify functionality
- Timestamp validation for replay attack prevention
- KeyExchangeMessage and KeyExchangeAckMessage
- Message serialization/deserialization
"""

import pytest
import time
from nacl.signing import SigningKey

from coc_framework.network.protocol import (
    SignedEnvelope,
    NetworkMessage,
    HeartbeatMessage,
    ShareMessage,
    DeletionTokenMessage,
    KeyExchangeMessage,
    KeyExchangeAckMessage,
    MessageType,
    MESSAGE_TYPE_MAP,
    validate_message_timestamp,
    unwrap_and_verify,
    deserialize_message,
    SignatureVerificationError,
    MessageTimestampError,
    MESSAGE_MAX_AGE_SECONDS,
    MESSAGE_MAX_FUTURE_SECONDS,
)


class TestSignedEnvelope:
    """Tests for SignedEnvelope cryptographic wrapper."""
    
    @pytest.fixture
    def keypair(self):
        """Generate a signing keypair."""
        signing_key = SigningKey.generate()
        return signing_key, signing_key.verify_key
    
    @pytest.fixture
    def message(self):
        """Create a sample message."""
        return HeartbeatMessage(sender_id="peer_A", sequence=1, load=50)
    
    def test_wrap_creates_signed_envelope(self, keypair, message):
        """wrap() should create a properly signed envelope."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        
        assert envelope.sender_id == "peer_A"
        assert envelope.signature != ""
        assert len(envelope.payload) > 0
        assert envelope.timestamp > 0
    
    def test_verify_valid_signature(self, keypair, message):
        """verify() should return True for valid signature."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        
        assert envelope.verify(verify_key) is True
    
    def test_verify_invalid_signature_wrong_key(self, keypair, message):
        """verify() should return False for wrong verification key."""
        signing_key, verify_key = keypair
        wrong_signing_key = SigningKey.generate()
        wrong_verify_key = wrong_signing_key.verify_key
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        
        assert envelope.verify(wrong_verify_key) is False
    
    def test_verify_tampered_payload(self, keypair, message):
        """verify() should return False if payload is tampered."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        # Tamper with payload
        envelope.payload = b"tampered content"
        
        assert envelope.verify(verify_key) is False
    
    def test_verify_tampered_timestamp(self, keypair, message):
        """verify() should return False if timestamp is tampered."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        # Tamper with timestamp
        envelope.timestamp = time.time() - 1000
        
        assert envelope.verify(verify_key) is False
    
    def test_verify_empty_signature(self, keypair, message):
        """verify() should return False for empty signature."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope(
            sender_id="peer_A",
            timestamp=time.time(),
            payload=message.to_bytes(),
            signature=""
        )
        
        assert envelope.verify(verify_key) is False
    
    def test_unwrap_returns_original_message(self, keypair, message):
        """unwrap() should return the original message."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        unwrapped = envelope.unwrap()
        
        assert unwrapped.sender_id == message.sender_id
        assert unwrapped.msg_type == MessageType.HEARTBEAT
    
    def test_serialization_roundtrip(self, keypair, message):
        """Envelope should serialize and deserialize correctly."""
        signing_key, verify_key = keypair
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        serialized = envelope.to_bytes()
        restored = SignedEnvelope.from_bytes(serialized)
        
        assert restored.sender_id == envelope.sender_id
        assert restored.timestamp == envelope.timestamp
        assert restored.signature == envelope.signature
        assert restored.verify(verify_key) is True


class TestTimestampValidation:
    """Tests for timestamp validation functionality."""
    
    def test_valid_current_timestamp(self):
        """Current timestamp should be valid."""
        valid, error = validate_message_timestamp(time.time())
        
        assert valid is True
        assert error == ""
    
    def test_valid_recent_timestamp(self):
        """Recent timestamp (within max age) should be valid."""
        recent = time.time() - (MESSAGE_MAX_AGE_SECONDS / 2)
        valid, error = validate_message_timestamp(recent)
        
        assert valid is True
        assert error == ""
    
    def test_invalid_too_old_timestamp(self):
        """Old timestamp (beyond max age) should be invalid."""
        old = time.time() - (MESSAGE_MAX_AGE_SECONDS + 10)
        valid, error = validate_message_timestamp(old)
        
        assert valid is False
        assert "too old" in error.lower()
    
    def test_valid_slight_future_timestamp(self):
        """Slight future timestamp (within tolerance) should be valid."""
        future = time.time() + (MESSAGE_MAX_FUTURE_SECONDS / 2)
        valid, error = validate_message_timestamp(future)
        
        assert valid is True
        assert error == ""
    
    def test_invalid_far_future_timestamp(self):
        """Far future timestamp (beyond tolerance) should be invalid."""
        far_future = time.time() + (MESSAGE_MAX_FUTURE_SECONDS + 10)
        valid, error = validate_message_timestamp(far_future)
        
        assert valid is False
        assert "future" in error.lower()
    
    def test_envelope_validate_timestamp(self):
        """SignedEnvelope.validate_timestamp() should work correctly."""
        signing_key = SigningKey.generate()
        message = HeartbeatMessage(sender_id="peer_A")
        
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key)
        valid, error = envelope.validate_timestamp()
        
        assert valid is True
        assert error == ""


class TestUnwrapAndVerify:
    """Tests for the unwrap_and_verify helper function."""
    
    @pytest.fixture
    def setup_peers(self):
        """Set up peer keys for testing."""
        signing_key_a = SigningKey.generate()
        signing_key_b = SigningKey.generate()
        
        peer_keys = {
            "peer_A": signing_key_a.verify_key,
            "peer_B": signing_key_b.verify_key,
        }
        
        def get_verify_key(sender_id):
            return peer_keys.get(sender_id)
        
        return signing_key_a, signing_key_b, get_verify_key
    
    def test_unwrap_valid_message(self, setup_peers):
        """unwrap_and_verify should succeed with valid message."""
        signing_key_a, _, get_verify_key = setup_peers
        
        message = HeartbeatMessage(sender_id="peer_A")
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key_a)
        data = envelope.to_bytes()
        
        result, sender_id = unwrap_and_verify(data, get_verify_key)
        
        assert sender_id == "peer_A"
        assert result.msg_type == MessageType.HEARTBEAT
    
    def test_unwrap_unknown_sender(self, setup_peers):
        """unwrap_and_verify should raise for unknown sender."""
        signing_key_unknown = SigningKey.generate()
        _, _, get_verify_key = setup_peers
        
        message = HeartbeatMessage(sender_id="unknown_peer")
        envelope = SignedEnvelope.wrap(message, "unknown_peer", signing_key_unknown)
        data = envelope.to_bytes()
        
        with pytest.raises(SignatureVerificationError) as exc_info:
            unwrap_and_verify(data, get_verify_key)
        
        assert "Unknown sender" in str(exc_info.value)
    
    def test_unwrap_invalid_signature(self, setup_peers):
        """unwrap_and_verify should raise for invalid signature."""
        signing_key_a, signing_key_b, get_verify_key = setup_peers
        
        # Sign with wrong key
        message = HeartbeatMessage(sender_id="peer_A")
        envelope = SignedEnvelope.wrap(message, "peer_A", signing_key_b)  # Wrong key!
        data = envelope.to_bytes()
        
        with pytest.raises(SignatureVerificationError) as exc_info:
            unwrap_and_verify(data, get_verify_key)
        
        assert "Invalid signature" in str(exc_info.value)
    
    def test_unwrap_expired_timestamp(self, setup_peers):
        """unwrap_and_verify should raise for expired timestamp."""
        signing_key_a, _, get_verify_key = setup_peers
        
        message = HeartbeatMessage(sender_id="peer_A")
        envelope = SignedEnvelope(
            sender_id="peer_A",
            timestamp=time.time() - (MESSAGE_MAX_AGE_SECONDS + 100),
            payload=message.to_bytes(),
            signature=""
        )
        envelope.sign(signing_key_a)
        data = envelope.to_bytes()
        
        with pytest.raises(MessageTimestampError):
            unwrap_and_verify(data, get_verify_key)
    
    def test_unwrap_skip_timestamp_validation(self, setup_peers):
        """unwrap_and_verify should skip timestamp check if disabled."""
        signing_key_a, _, get_verify_key = setup_peers
        
        message = HeartbeatMessage(sender_id="peer_A")
        envelope = SignedEnvelope(
            sender_id="peer_A",
            timestamp=time.time() - (MESSAGE_MAX_AGE_SECONDS + 100),
            payload=message.to_bytes(),
            signature=""
        )
        envelope.sign(signing_key_a)
        data = envelope.to_bytes()
        
        # Should not raise when timestamp validation is disabled
        result, sender_id = unwrap_and_verify(data, get_verify_key, validate_time=False)
        
        assert sender_id == "peer_A"


class TestKeyExchangeMessages:
    """Tests for KeyExchangeMessage and KeyExchangeAckMessage."""
    
    def test_key_exchange_message_auto_nonce(self):
        """KeyExchangeMessage should auto-generate nonce."""
        msg = KeyExchangeMessage(
            sender_id="peer_A",
            public_key="abc123",
            peer_address="tcp://127.0.0.1:5000"
        )
        
        assert msg.nonce != ""
        assert len(msg.nonce) == 32  # 16 bytes = 32 hex chars
        assert msg.msg_type == MessageType.KEY_EXCHANGE
    
    def test_key_exchange_ack_message_fields(self):
        """KeyExchangeAckMessage should have all required fields."""
        msg = KeyExchangeAckMessage(
            sender_id="peer_B",
            public_key="def456",
            peer_address="tcp://127.0.0.1:5001",
            original_nonce="abc123"
        )
        
        assert msg.public_key == "def456"
        assert msg.original_nonce == "abc123"
        assert msg.response_nonce != ""
        assert msg.msg_type == MessageType.KEY_EXCHANGE_ACK
    
    def test_key_exchange_serialization_roundtrip(self):
        """KeyExchange messages should serialize/deserialize correctly."""
        original = KeyExchangeMessage(
            sender_id="peer_A",
            public_key="abc123",
            peer_address="tcp://127.0.0.1:5000"
        )
        
        data = original.to_dict()
        restored = KeyExchangeMessage.from_dict(data)
        
        assert restored.sender_id == original.sender_id
        assert restored.public_key == original.public_key
        assert restored.nonce == original.nonce
    
    def test_key_exchange_ack_serialization_roundtrip(self):
        """KeyExchangeAck messages should serialize/deserialize correctly."""
        original = KeyExchangeAckMessage(
            sender_id="peer_B",
            public_key="def456",
            peer_address="tcp://127.0.0.1:5001",
            original_nonce="abc123"
        )
        
        data = original.to_dict()
        restored = KeyExchangeAckMessage.from_dict(data)
        
        assert restored.sender_id == original.sender_id
        assert restored.original_nonce == original.original_nonce
        assert restored.response_nonce == original.response_nonce


class TestMessageDeserialization:
    """Tests for message deserialization."""
    
    def test_deserialize_heartbeat(self):
        """Should deserialize HeartbeatMessage correctly."""
        msg = HeartbeatMessage(sender_id="peer_A", sequence=5, load=75)
        data = msg.to_bytes()
        
        result = deserialize_message(data)
        
        assert isinstance(result, HeartbeatMessage)
        assert result.sequence == 5
        assert result.load == 75
    
    def test_deserialize_share_message(self):
        """Should deserialize ShareMessage correctly."""
        msg = ShareMessage(
            sender_id="peer_A",
            share_index=3,
            share_data="abc123",
            content_hash="hash123",
            threshold=3,
            total_shares=5
        )
        data = msg.to_bytes()
        
        result = deserialize_message(data)
        
        assert isinstance(result, ShareMessage)
        assert result.share_index == 3
        assert result.threshold == 3
    
    def test_deserialize_deletion_token(self):
        """Should deserialize DeletionTokenMessage correctly."""
        msg = DeletionTokenMessage(
            sender_id="peer_A",
            node_hash="nodehash123",
            originator_id="orig_peer",
            cascade=True,
            reason="User requested"
        )
        data = msg.to_bytes()
        
        result = deserialize_message(data)
        
        assert isinstance(result, DeletionTokenMessage)
        assert result.node_hash == "nodehash123"
        assert result.cascade is True
    
    def test_deserialize_from_dict(self):
        """Should deserialize from dictionary."""
        data = {
            "sender_id": "peer_A",
            "msg_type": "heartbeat",
            "timestamp": time.time(),
            "msg_id": "test123",
            "signature": "",
            "sequence": 1,
            "load": 0
        }
        
        result = deserialize_message(data)
        
        assert result.sender_id == "peer_A"
        assert result.msg_type == MessageType.HEARTBEAT


class TestMessageTypeMap:
    """Tests for MESSAGE_TYPE_MAP lookup."""
    
    def test_all_message_types_in_map(self):
        """All MessageType enum values should be in the lookup map."""
        for msg_type in MessageType:
            assert msg_type.value in MESSAGE_TYPE_MAP
            assert MESSAGE_TYPE_MAP[msg_type.value] == msg_type
    
    def test_lookup_returns_correct_type(self):
        """Lookup should return correct MessageType."""
        assert MESSAGE_TYPE_MAP["heartbeat"] == MessageType.HEARTBEAT
        assert MESSAGE_TYPE_MAP["share"] == MessageType.SHARE
        assert MESSAGE_TYPE_MAP["key_exchange"] == MessageType.KEY_EXCHANGE
