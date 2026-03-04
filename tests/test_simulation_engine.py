"""
Integration tests for the SimulationEngine and scenario execution.
"""
import pytest
import asyncio
from coc_framework.simulation_engine import SimulationEngine


class TestSimulationEngineSetup:
    """Tests for SimulationEngine initialization."""

    def test_engine_creates_peers_from_settings(self):
        """Engine should create peers from total_peers setting."""
        scenario = {
            "settings": {"total_peers": 3},
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        assert len(engine.peers) == 3
        assert "peer_0" in engine.peers
        assert "peer_1" in engine.peers
        assert "peer_2" in engine.peers

    def test_engine_creates_peers_from_peer_list(self):
        """Engine should create peers from explicit peer definitions."""
        scenario = {
            "peers": [
                {"id": "alice"},
                {"id": "bob"},
                {"id": "charlie"}
            ],
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        assert len(engine.peers) == 3
        assert "alice" in engine.peers
        assert "bob" in engine.peers
        assert "charlie" in engine.peers

    def test_engine_initializes_features_disabled_by_default(self):
        """Features should be disabled by default."""
        scenario = {"settings": {"total_peers": 2}, "events": []}
        
        engine = SimulationEngine(scenario)
        
        assert engine.enable_secret_sharing is False
        assert engine.enable_timelock is False
        assert engine.enable_steganography is False
        assert engine.secret_sharing_engine is None
        assert engine.timelock_engine is None
        assert engine.stegano_engine is None

    def test_engine_initializes_secret_sharing_when_enabled(self):
        """Secret sharing engine should be created when enabled."""
        scenario = {
            "settings": {
                "total_peers": 2,
                "enable_secret_sharing": True,
                "secret_sharing_threshold": 2
            },
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        assert engine.enable_secret_sharing is True
        assert engine.secret_sharing_engine is not None

    def test_engine_initializes_timelock_when_enabled(self):
        """Timelock engine should be created when enabled."""
        scenario = {
            "settings": {
                "total_peers": 2,
                "enable_timelock": True
            },
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        try:
            assert engine.enable_timelock is True
            assert engine.timelock_engine is not None
        finally:
            engine.shutdown()

    def test_engine_initializes_steganography_when_enabled(self):
        """Steganography engine should be created when enabled."""
        scenario = {
            "settings": {
                "total_peers": 2,
                "enable_steganography": True
            },
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        assert engine.enable_steganography is True
        assert engine.stegano_engine is not None


class TestMessageRegistry:
    """Tests for the message_id to node_hash registry."""

    @pytest.mark.asyncio
    async def test_create_message_registers_id(self):
        """CREATE_MESSAGE with message_id should register mapping."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "message_id": "test_msg",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1"],
                    "content": "Test content"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        await engine.tick(tick_delay=0.01)
        
        assert "test_msg" in engine._message_registry
        node_hash = engine._message_registry["test_msg"]
        assert len(node_hash) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_get_node_hash_returns_hash(self):
        """get_node_hash should return registered hash."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "message_id": "lookup_msg",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1"],
                    "content": "Content"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        await engine.tick(tick_delay=0.01)
        
        result = engine.get_node_hash("lookup_msg")
        
        assert result is not None
        assert result == engine._message_registry["lookup_msg"]

    @pytest.mark.asyncio
    async def test_get_node_hash_returns_none_for_unknown(self):
        """get_node_hash should return None for unregistered id."""
        scenario = {"settings": {"total_peers": 1}, "events": []}
        
        engine = SimulationEngine(scenario)
        
        result = engine.get_node_hash("nonexistent")
        
        assert result is None


class TestCreateMessageEvent:
    """Tests for CREATE_MESSAGE event handling."""

    @pytest.mark.asyncio
    async def test_create_message_stores_in_originator(self):
        """Originator should store the created node."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1"],
                    "content": "Test message"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        await engine.tick(tick_delay=0.01)
        
        originator = engine.peers["peer_0"]
        assert len(originator.storage._nodes) == 1

    @pytest.mark.asyncio
    async def test_create_message_sends_to_recipients(self):
        """Message should be sent to all recipients."""
        scenario = {
            "settings": {"total_peers": 4},
            "events": [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1", "peer_2", "peer_3"],
                    "content": "Broadcast message"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        # tick_delay must exceed MAX_NETWORK_DELAY_SECONDS (0.05) from network_sim.py
        # to ensure async message delivery completes before assertion
        await engine.tick(tick_delay=0.1)
        
        # Recipients should have received the message
        for peer_id in ["peer_1", "peer_2", "peer_3"]:
            peer = engine.peers[peer_id]
            assert len(peer.storage._nodes) >= 1


class TestForwardMessageEvent:
    """Tests for FORWARD_MESSAGE event handling."""

    @pytest.mark.asyncio
    async def test_forward_with_message_id(self):
        """FORWARD_MESSAGE should work with parent_message_id."""
        scenario = {
            "settings": {"total_peers": 4},
            "events": [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "message_id": "original",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1"],
                    "content": "Original content"
                },
                {
                    "time": 5,
                    "type": "FORWARD_MESSAGE",
                    "message_id": "forwarded",
                    "sender_id": "peer_1",
                    "parent_message_id": "original",
                    "recipient_ids": ["peer_2", "peer_3"]
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        
        # Run enough ticks
        for _ in range(10):
            await engine.tick(tick_delay=0.01)
        
        # Both messages should be registered
        assert "original" in engine._message_registry
        assert "forwarded" in engine._message_registry

    @pytest.mark.asyncio
    async def test_forward_fails_without_parent(self):
        """FORWARD_MESSAGE should fail gracefully with invalid parent."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {
                    "time": 0,
                    "type": "FORWARD_MESSAGE",
                    "sender_id": "peer_0",
                    "parent_message_id": "nonexistent",
                    "recipient_ids": ["peer_1"]
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        
        # Should not raise, just log warning
        await engine.tick(tick_delay=0.01)
        
        # No messages should be registered
        assert len(engine._message_registry) == 0


class TestDeleteMessageEvent:
    """Tests for DELETE_MESSAGE event handling."""

    @pytest.mark.asyncio
    async def test_delete_with_message_id(self):
        """DELETE_MESSAGE should work with message_id."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "message_id": "to_delete",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1"],
                    "content": "Will be deleted"
                },
                {
                    "time": 5,
                    "type": "DELETE_MESSAGE",
                    "originator_id": "peer_0",
                    "message_id": "to_delete"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        
        # Run simulation
        for _ in range(10):
            await engine.tick(tick_delay=0.01)
        
        # The delete should have been initiated (check audit log or peer state)
        # Note: actual deletion propagation is async and may take time


class TestPeerOnlineOfflineEvents:
    """Tests for PEER_ONLINE and PEER_OFFLINE events."""

    @pytest.mark.asyncio
    async def test_peer_offline_event(self):
        """PEER_OFFLINE should mark peer as offline."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {
                    "time": 0,
                    "type": "PEER_OFFLINE",
                    "peer_id": "peer_1"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        await engine.tick(tick_delay=0.01)
        
        assert engine.peers["peer_1"].online is False

    @pytest.mark.asyncio
    async def test_peer_online_event(self):
        """PEER_ONLINE should mark peer as online."""
        scenario = {
            "settings": {"total_peers": 2},
            "events": [
                {"time": 0, "type": "PEER_OFFLINE", "peer_id": "peer_1"},
                {"time": 2, "type": "PEER_ONLINE", "peer_id": "peer_1"}
            ]
        }
        
        engine = SimulationEngine(scenario)
        
        # First tick: peer goes offline
        await engine.tick(tick_delay=0.01)
        assert engine.peers["peer_1"].online is False
        
        # Second tick: nothing
        await engine.tick(tick_delay=0.01)
        
        # Third tick: peer comes online
        await engine.tick(tick_delay=0.01)
        assert engine.peers["peer_1"].online is True


class TestSimulationState:
    """Tests for get_simulation_state."""

    def test_get_simulation_state_includes_tick(self):
        """State should include current tick count."""
        scenario = {"settings": {"total_peers": 2}, "events": []}
        
        engine = SimulationEngine(scenario)
        
        state = engine.get_simulation_state()
        
        assert "tick" in state
        assert state["tick"] == 0

    def test_get_simulation_state_includes_peers(self):
        """State should include peers dict."""
        scenario = {"settings": {"total_peers": 3}, "events": []}
        
        engine = SimulationEngine(scenario)
        
        state = engine.get_simulation_state()
        
        assert "peers" in state
        assert len(state["peers"]) == 3

    def test_get_simulation_state_includes_features(self):
        """State should include feature flags."""
        scenario = {
            "settings": {
                "total_peers": 2,
                "enable_secret_sharing": True
            },
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        state = engine.get_simulation_state()
        
        assert "features" in state
        assert state["features"]["secret_sharing"] is True
        assert state["features"]["timelock"] is False

    def test_get_simulation_state_includes_message_registry(self):
        """State should include message registry."""
        scenario = {"settings": {"total_peers": 2}, "events": []}
        
        engine = SimulationEngine(scenario)
        
        state = engine.get_simulation_state()
        
        assert "message_registry" in state


class TestSimulationEngineIntegration:
    """Full integration tests for simulation scenarios."""

    @pytest.mark.asyncio
    async def test_full_scenario_execution(self):
        """Execute a complete scenario with multiple event types."""
        scenario = {
            "settings": {
                "total_peers": 4,
                "simulation_duration": 8
            },
            "events": [
                {
                    "time": 1,
                    "type": "CREATE_MESSAGE",
                    "message_id": "msg1",
                    "originator_id": "peer_0",
                    "recipient_ids": ["peer_1", "peer_2"],
                    "content": "Initial message"
                },
                {
                    "time": 2,
                    "type": "PEER_OFFLINE",
                    "peer_id": "peer_3"
                },
                {
                    "time": 5,
                    "type": "PEER_ONLINE",
                    "peer_id": "peer_3"
                }
            ]
        }
        
        engine = SimulationEngine(scenario)
        
        # Run all ticks
        for _ in range(8):
            await engine.tick(tick_delay=0.01)
        
        # Verify final state
        assert engine.tick_count == 8
        assert "msg1" in engine._message_registry
        assert engine.peers["peer_3"].online is True

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up_timelock(self):
        """shutdown should clean up timelock engine."""
        scenario = {
            "settings": {
                "total_peers": 2,
                "enable_timelock": True
            },
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        assert engine.timelock_engine is not None
        
        # Should not raise
        engine.shutdown()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """SimulationEngine should work as context manager."""
        scenario = {
            "settings": {"total_peers": 2, "enable_timelock": True},
            "events": []
        }
        
        with SimulationEngine(scenario) as engine:
            assert engine.timelock_engine is not None
            await engine.tick(tick_delay=0.01)
        # Engine should be automatically shut down after context

    @pytest.mark.asyncio
    async def test_context_manager_exception_handling(self):
        """Context manager should cleanup even on exception."""
        scenario = {
            "settings": {"total_peers": 2, "enable_timelock": True},
            "events": []
        }
        
        try:
            with SimulationEngine(scenario) as engine:
                await engine.tick(tick_delay=0.01)
                raise ValueError("Test exception")
        except ValueError:
            pass
        # Engine should still be cleaned up


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
