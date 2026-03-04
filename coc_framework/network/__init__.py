"""
TrustFlow Network Layer

Real multi-process network implementation using ZeroMQ for inter-peer communication.
This replaces the in-memory simulation with actual process isolation.

Components:
- protocol: Message format definitions and serialization
- peer_process: Standalone peer running as separate process
- coordinator: Spawns and manages peer processes, runs scenarios
"""

from .protocol import (
    MessageType,
    NetworkMessage,
    ShareMessage,
    DeletionTokenMessage,
    CoCNodeMessage,
    PeerStatusMessage,
)
from .peer_process import NetworkPeer
from .coordinator import NetworkCoordinator

__all__ = [
    "MessageType",
    "NetworkMessage",
    "ShareMessage",
    "DeletionTokenMessage",
    "CoCNodeMessage",
    "PeerStatusMessage",
    "NetworkPeer",
    "NetworkCoordinator",
]
