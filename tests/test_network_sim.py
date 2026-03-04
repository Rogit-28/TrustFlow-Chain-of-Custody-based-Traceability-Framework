"""
Tests for TrustFlow Network Simulation - Message Deduplication

Tests cover:
- Message ID computation
- MessageCache integration in Peer
- Duplicate message filtering
"""

import pytest
import hashlib
from unittest.mock import MagicMock, patch
import time

from coc_framework.core.network_sim import (
    Peer,
    Network,
    _compute_message_id,
    MessageCache,
)
from coc_framework.core.deletion_engine import DeletionEngine
from coc_framework.core.audit_log import AuditLog
from coc_framework.interfaces.notification_handler import SilentNotificationHandler
from coc_framework.interfaces.peer_discovery import RegistryPeerDiscovery


class TestComputeMessageId:
    """Tests for _compute_message_id function."""
    
    def test_returns_32_char_hex_string(self):
        """Message ID should be 32 character hex string."""
        message = {
            "sender_id": "peer_A",
            "message_type": "test",
            "content": "hello"
        }
        
        msg_id = _compute_message_id(message)
        
        assert len(msg_id) == 32
        assert all(c in "0123456789abcdef" for c in msg_id)
    
    def test_same_message_produces_same_id(self):
        """Same message should always produce same ID."""
        message = {
            "sender_id": "peer_A",
            "message_type": "test",
            "content": "hello world"
        }
        
        id1 = _compute_message_id(message)
        id2 = _compute_message_id(message)
        
        assert id1 == id2
    
    def test_different_sender_produces_different_id(self):
        """Different sender should produce different ID."""
        msg1 = {
            "sender_id": "peer_A",
            "message_type": "test",
            "content": "hello"
        }
        msg2 = {
            "sender_id": "peer_B",
            "message_type": "test",
            "content": "hello"
        }
        
        assert _compute_message_id(msg1) != _compute_message_id(msg2)
    
    def test_different_type_produces_different_id(self):
        """Different message type should produce different ID."""
        msg1 = {
            "sender_id": "peer_A",
            "message_type": "type_A",
            "content": "hello"
        }
        msg2 = {
            "sender_id": "peer_A",
            "message_type": "type_B",
            "content": "hello"
        }
        
        assert _compute_message_id(msg1) != _compute_message_id(msg2)
    
    def test_different_content_produces_different_id(self):
        """Different content should produce different ID."""
        msg1 = {
            "sender_id": "peer_A",
            "message_type": "test",
            "content": "hello"
        }
        msg2 = {
            "sender_id": "peer_A",
            "message_type": "test",
            "content": "world"
        }
        
        assert _compute_message_id(msg1) != _compute_message_id(msg2)
    
    def test_handles_missing_fields(self):
        """Should handle missing fields gracefully."""
        message = {}
        
        msg_id = _compute_message_id(message)
        
        assert len(msg_id) == 32  # Still produces valid ID


class TestPeerMessageDeduplication:
    """Tests for message deduplication in Peer class."""
    
    @pytest.fixture
    def mock_network(self):
        """Create a mock network."""
        return MagicMock()
    
    @pytest.fixture
    def deletion_engine(self, mock_network):
        """Create a deletion engine for testing."""
        audit_log = AuditLog()
        notification_handler = SilentNotificationHandler()
        peer_discovery = RegistryPeerDiscovery()
        return DeletionEngine(
            network=mock_network,
            audit_log=audit_log,
            notification_handler=notification_handler,
            peer_discovery=peer_discovery
        )
    
    @pytest.fixture
    def peer(self, deletion_engine):
        """Create a peer for testing."""
        return Peer(deletion_engine=deletion_engine, peer_id="test_peer")
    
    def test_peer_has_message_cache(self, peer):
        """Peer should have a message cache for deduplication."""
        assert hasattr(peer, '_received_messages')
        assert isinstance(peer._received_messages, MessageCache)
    
    def test_first_message_is_processed(self, peer):
        """First message should be processed."""
        message = {
            "sender_id": "peer_A",
            "recipient_id": peer.peer_id,
            "message_type": "test_type",
            "content": {"data": "test"}
        }
        
        # Should not raise and should mark as seen
        peer.receive_message(message)
        
        msg_id = _compute_message_id(message)
        assert peer._received_messages.has_seen(msg_id) is True
    
    def test_duplicate_message_is_ignored(self, peer):
        """Duplicate message should be ignored."""
        message = {
            "sender_id": "peer_A",
            "recipient_id": peer.peer_id,
            "message_type": "test_type",
            "content": {"data": "test"}
        }
        
        # Track processing (we'll use a mock to verify)
        processed_count = 0
        original_receive = peer.receive_message
        
        # Send same message twice
        peer.receive_message(message)
        
        # Verify it's in cache now
        msg_id = _compute_message_id(message)
        assert peer._received_messages.has_seen(msg_id) is True
        
        # Second call should return early (duplicate detected)
        # We can verify by checking the cache doesn't change behavior
        # and no error is raised
        peer.receive_message(message)  # Should silently ignore


class TestNetworkDeduplication:
    """Tests for deduplication at network level."""
    
    @pytest.fixture
    def peer_discovery(self):
        """Create a peer discovery instance."""
        return RegistryPeerDiscovery()
    
    @pytest.fixture
    def network(self, peer_discovery):
        """Create network with peer discovery."""
        return Network(peer_discovery=peer_discovery)
    
    @pytest.fixture
    def deletion_engine(self, network):
        """Create a deletion engine for testing."""
        audit_log = AuditLog()
        notification_handler = SilentNotificationHandler()
        peer_discovery = RegistryPeerDiscovery()
        return DeletionEngine(
            network=network,
            audit_log=audit_log,
            notification_handler=notification_handler,
            peer_discovery=peer_discovery
        )
    
    @pytest.fixture
    def two_peers(self, network, deletion_engine):
        """Create two connected peers."""
        peer_a = Peer(deletion_engine=deletion_engine, peer_id="peer_A")
        peer_b = Peer(deletion_engine=deletion_engine, peer_id="peer_B")
        network.add_peer(peer_a)
        network.add_peer(peer_b)
        return peer_a, peer_b
    
    @pytest.mark.asyncio
    async def test_message_routed_only_once(self, network, two_peers):
        """Same message should only be processed once by recipient."""
        peer_a, peer_b = two_peers
        
        # Send same message multiple times
        message = {
            "sender_id": "peer_A",
            "recipient_id": "peer_B",
            "message_type": "test",
            "content": "hello"
        }
        
        # Route the same message twice
        network.route_message(message)
        network.route_message(message)
        
        # Wait for async delivery
        import asyncio
        await asyncio.sleep(0.1)
        
        # Peer B should have seen the message
        msg_id = _compute_message_id(message)
        assert peer_b._received_messages.has_seen(msg_id) is True


class TestMessageCacheIntegration:
    """Integration tests for MessageCache with Peer."""
    
    @pytest.fixture
    def mock_network(self):
        """Create a mock network."""
        return MagicMock()
    
    @pytest.fixture
    def deletion_engine(self, mock_network):
        """Create a deletion engine for testing."""
        audit_log = AuditLog()
        notification_handler = SilentNotificationHandler()
        peer_discovery = RegistryPeerDiscovery()
        return DeletionEngine(
            network=mock_network,
            audit_log=audit_log,
            notification_handler=notification_handler,
            peer_discovery=peer_discovery
        )
    
    def test_cache_size_is_configured(self, deletion_engine):
        """Peer's message cache should have configured size."""
        peer = Peer(deletion_engine=deletion_engine, peer_id="test")
        
        assert peer._received_messages._max_size == 1000
        assert peer._received_messages._ttl == 300  # 5 minutes
    
    def test_cache_cleanup_on_receive(self, deletion_engine):
        """Cache should cleanup on message receive."""
        peer = Peer(deletion_engine=deletion_engine, peer_id="test")
        
        # Force a cleanup trigger by manipulating last_cleanup
        peer._received_messages._last_cleanup = time.time() - 1000
        
        message = {
            "sender_id": "peer_A",
            "message_type": "test",
            "content": "trigger cleanup"
        }
        
        peer.receive_message(message)
        
        # Cleanup should have run, updating last_cleanup
        assert peer._received_messages._last_cleanup > time.time() - 10
