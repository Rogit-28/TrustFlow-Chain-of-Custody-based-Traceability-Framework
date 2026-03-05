"""
TrustFlow Network Peer Process

Standalone peer implementation that runs as a separate process.
Uses ZeroMQ for inter-peer communication:
- PUB socket: Broadcasts (deletion tokens, status updates)
- REP socket: Direct request/response (shares, CoC nodes)
- SUB socket: Subscribes to broadcasts from other peers

Each peer maintains its own storage, crypto keys, and audit log.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Set, Callable, Any, TYPE_CHECKING
from queue import Queue, Empty

try:
    import zmq
    import zmq.asyncio
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False
    print("[WARNING] pyzmq not installed. Network functionality disabled.")

from nacl.signing import SigningKey, VerifyKey

from .protocol import (
    MessageType,
    NetworkMessage,
    ShareMessage,
    DeletionTokenMessage,
    CoCNodeMessage,
    PeerStatusMessage,
    ContentMessage,
    RequestMessage,
    ResponseMessage,
    HeartbeatMessage,
    PeerStatus,
    SocketConfig,
    deserialize_message,
)

# Import core components
if TYPE_CHECKING:
    from ..core.coc_node import CoCNode
    from ..core.secret_sharing import Share

from ..core.crypto_core import CryptoCore
from ..interfaces.storage_backend import InMemoryStorage


@dataclass
class PeerConfig:
    """Configuration for a network peer."""
    peer_id: str
    peer_index: int                     # Index for port assignment
    host: str = "127.0.0.1"
    signing_key: Optional[SigningKey] = None
    enable_secret_sharing: bool = True
    enable_timelock: bool = True
    enable_steganography: bool = True


@dataclass
class PeerState:
    """Runtime state for a network peer."""
    is_online: bool = True
    connected_peers: Set[str] = field(default_factory=set)
    pending_messages: List[NetworkMessage] = field(default_factory=list)
    last_heartbeat: Dict[str, float] = field(default_factory=dict)


class NetworkPeer:
    """
    A peer in the TrustFlow network running as a standalone process.
    
    Communication:
    - PUB socket on port 5550+index: Broadcasts to all subscribers
    - REP socket on port 5600+index: Handles direct requests
    - SUB sockets: Subscribes to other peers' PUB sockets
    
    Features:
    - Cryptographic identity (Ed25519)
    - Local storage for CoC nodes, shares, and content
    - Offline message queuing
    - Automatic reconnection
    """
    
    def __init__(self, config: PeerConfig):
        if not ZMQ_AVAILABLE:
            raise RuntimeError("pyzmq is required for NetworkPeer")
        
        self.config = config
        self.peer_id = config.peer_id
        self.state = PeerState()
        
        # Cryptographic identity
        if config.signing_key:
            self.signing_key = config.signing_key
        else:
            self.signing_key = SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        
        # Storage
        self.storage = InMemoryStorage()
        self._shares: Dict[str, Any] = {}           # content_hash -> Share
        self._content: Dict[str, bytes] = {}        # content_hash -> encrypted content
        self._peer_keys: Dict[str, VerifyKey] = {}  # peer_id -> verify_key
        
        # Message handlers
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._register_default_handlers()
        
        # ZeroMQ context and sockets
        self._context: Optional[zmq.asyncio.Context] = None
        self._pub_socket: Optional[zmq.asyncio.Socket] = None
        self._rep_socket: Optional[zmq.asyncio.Socket] = None
        self._sub_sockets: Dict[str, zmq.asyncio.Socket] = {}
        
        # Offline queue
        self._offline_queue: Queue = Queue()
        
        # Control
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _register_default_handlers(self):
        """Register default message handlers."""
        self._message_handlers[MessageType.SHARE] = self._handle_share
        self._message_handlers[MessageType.DELETION_TOKEN] = self._handle_deletion
        self._message_handlers[MessageType.COC_NODE] = self._handle_coc_node
        self._message_handlers[MessageType.PEER_STATUS] = self._handle_peer_status
        self._message_handlers[MessageType.CONTENT] = self._handle_content
        self._message_handlers[MessageType.REQUEST_SHARE] = self._handle_request_share
        self._message_handlers[MessageType.REQUEST_CONTENT] = self._handle_request_content
        self._message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
    
    def register_handler(self, msg_type: MessageType, handler: Callable):
        """Register a custom message handler."""
        self._message_handlers[msg_type] = handler
    
    # ==================== Socket Management ====================
    
    async def start(self):
        """Start the peer and begin listening for messages."""
        self._running = True
        self._context = zmq.asyncio.Context()
        
        # Create PUB socket for broadcasts
        self._pub_socket = self._context.socket(zmq.PUB)
        pub_addr = SocketConfig.get_pub_address(self.config.peer_index, self.config.host)
        self._pub_socket.bind(pub_addr)
        
        # Create REP socket for direct requests
        self._rep_socket = self._context.socket(zmq.REP)
        rep_addr = SocketConfig.get_rep_address(self.config.peer_index, self.config.host)
        self._rep_socket.bind(rep_addr)
        
        print(f"[PEER {self.peer_id[:8]}] Started - PUB: {pub_addr}, REP: {rep_addr}")
        
        # Broadcast online status
        await self._broadcast_status(PeerStatus.ONLINE)
        
        # Start message processing loops
        self._loop = asyncio.get_event_loop()
        asyncio.create_task(self._rep_loop())
        asyncio.create_task(self._sub_loop())
        asyncio.create_task(self._heartbeat_loop())
    
    async def stop(self):
        """Stop the peer gracefully."""
        self._running = False
        
        # Broadcast offline status
        await self._broadcast_status(PeerStatus.OFFLINE)
        
        # Close sockets
        if self._pub_socket:
            self._pub_socket.close()
        if self._rep_socket:
            self._rep_socket.close()
        for sock in self._sub_sockets.values():
            sock.close()
        
        if self._context:
            self._context.term()
        
        print(f"[PEER {self.peer_id[:8]}] Stopped")
    
    async def connect_to_peer(self, peer_id: str, peer_index: int, host: str = "127.0.0.1"):
        """Subscribe to another peer's broadcasts."""
        if peer_id in self._sub_sockets:
            return  # Already connected
        
        sub_socket = self._context.socket(zmq.SUB)
        pub_addr = SocketConfig.get_pub_address(peer_index, host)
        sub_socket.connect(pub_addr)
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages
        
        self._sub_sockets[peer_id] = sub_socket
        self.state.connected_peers.add(peer_id)
        
        print(f"[PEER {self.peer_id[:8]}] Connected to peer {peer_id[:8]} at {pub_addr}")
    
    async def disconnect_from_peer(self, peer_id: str):
        """Unsubscribe from a peer's broadcasts."""
        if peer_id in self._sub_sockets:
            self._sub_sockets[peer_id].close()
            del self._sub_sockets[peer_id]
            self.state.connected_peers.discard(peer_id)
            print(f"[PEER {self.peer_id[:8]}] Disconnected from peer {peer_id[:8]}")
    
    # ==================== Message Loops ====================
    
    async def _rep_loop(self):
        """Handle direct request/response messages."""
        while self._running:
            try:
                # Non-blocking receive with timeout
                if await self._rep_socket.poll(timeout=100):
                    msg_bytes = await self._rep_socket.recv()
                    message = deserialize_message(msg_bytes)
                    
                    # Process and send response
                    response = await self._handle_request(message)
                    await self._rep_socket.send(response.to_bytes())
            except zmq.ZMQError as e:
                if self._running:
                    print(f"[PEER {self.peer_id[:8]}] REP error: {e}")
            except Exception as e:
                if self._running:
                    print(f"[PEER {self.peer_id[:8]}] REP handler error: {e}")
                    # Send error response
                    error_resp = ResponseMessage(
                        sender_id=self.peer_id,
                        success=False,
                        error_message=str(e)
                    )
                    try:
                        await self._rep_socket.send(error_resp.to_bytes())
                    except zmq.ZMQError:
                        pass  # Socket may already be closed
    
    async def _sub_loop(self):
        """Handle broadcast messages from subscribed peers."""
        while self._running:
            for peer_id, sub_socket in list(self._sub_sockets.items()):
                try:
                    if await sub_socket.poll(timeout=10):
                        msg_bytes = await sub_socket.recv()
                        message = deserialize_message(msg_bytes)
                        await self._handle_broadcast(message)
                except zmq.ZMQError as e:
                    if self._running:
                        print(f"[PEER {self.peer_id[:8]}] SUB error from {peer_id[:8]}: {e}")
                except Exception as e:
                    if self._running:
                        print(f"[PEER {self.peer_id[:8]}] SUB handler error: {e}")
            
            await asyncio.sleep(0.01)  # Small delay to prevent busy loop
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        sequence = 0
        while self._running:
            heartbeat = HeartbeatMessage(
                sender_id=self.peer_id,
                sequence=sequence,
                load=0  # TODO: Implement actual load calculation
            )
            await self._broadcast(heartbeat)
            sequence += 1
            await asyncio.sleep(SocketConfig.HEARTBEAT_INTERVAL)
    
    # ==================== Message Handling ====================
    
    async def _handle_request(self, message: NetworkMessage) -> ResponseMessage:
        """Handle a direct request and return response."""
        handler = self._message_handlers.get(message.msg_type)
        
        if handler:
            try:
                result = await handler(message)
                return ResponseMessage(
                    sender_id=self.peer_id,
                    request_id=message.msg_id,
                    success=True,
                    data=result if isinstance(result, dict) else {"result": result}
                )
            except Exception as e:
                return ResponseMessage(
                    sender_id=self.peer_id,
                    request_id=message.msg_id,
                    success=False,
                    error_message=str(e)
                )
        else:
            return ResponseMessage(
                sender_id=self.peer_id,
                request_id=message.msg_id,
                success=False,
                error_message=f"Unknown message type: {message.msg_type}"
            )
    
    async def _handle_broadcast(self, message: NetworkMessage):
        """Handle a broadcast message."""
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                print(f"[PEER {self.peer_id[:8]}] Broadcast handler error: {e}")
    
    # ==================== Default Handlers ====================
    
    async def _handle_share(self, message: ShareMessage) -> Dict:
        """Handle incoming secret share."""
        print(f"[PEER {self.peer_id[:8]}] Received share {message.share_index} for content {message.content_hash[:8]}")
        
        # Store the share
        self._shares[message.content_hash] = {
            "index": message.share_index,
            "data": message.share_data,
            "threshold": message.threshold,
            "total": message.total_shares,
            "from": message.sender_id,
        }
        
        return {"stored": True, "content_hash": message.content_hash}
    
    async def _handle_deletion(self, message: DeletionTokenMessage) -> Dict:
        """Handle deletion token."""
        print(f"[PEER {self.peer_id[:8]}] Received deletion token for node {message.node_hash[:8]}")
        
        # Verify signature if we have originator's key
        originator_key = self._peer_keys.get(message.originator_id)
        if originator_key:
            token_data = f"{message.node_hash}{message.originator_id}{message.timestamp}"
            if not CryptoCore.verify_signature(originator_key, token_data, bytes.fromhex(message.token_signature)):
                print(f"[PEER {self.peer_id[:8]}] Invalid deletion token signature")
                return {"deleted": False, "reason": "invalid_signature"}
        
        # Delete the node from storage
        node = self.storage.get_node(message.node_hash)
        if node:
            self.storage.remove_node(message.node_hash)
            
            # Also delete associated share if exists
            if node.content_hash in self._shares:
                del self._shares[node.content_hash]
            
            # Also delete content if no other references
            if node.content_hash in self._content:
                del self._content[node.content_hash]
            
            print(f"[PEER {self.peer_id[:8]}] Deleted node {message.node_hash[:8]}")
            return {"deleted": True, "node_hash": message.node_hash}
        
        return {"deleted": False, "reason": "not_found"}
    
    async def _handle_coc_node(self, message: CoCNodeMessage) -> Dict:
        """Handle incoming CoC node."""
        print(f"[PEER {self.peer_id[:8]}] Received CoC node {message.content_hash[:8]}")
        
        # Import here to avoid circular imports
        from ..core.coc_node import CoCNode
        
        # Reconstruct the node
        node = CoCNode.from_dict(message.node_data)
        
        # Store the node
        self.storage.store_node(node)
        
        return {"stored": True, "node_hash": node.node_hash}
    
    async def _handle_peer_status(self, message: PeerStatusMessage) -> Dict:
        """Handle peer status update."""
        if message.status == PeerStatus.ONLINE:
            self.state.connected_peers.add(message.peer_id)
            print(f"[PEER {self.peer_id[:8]}] Peer {message.peer_id[:8]} is now ONLINE")
        elif message.status == PeerStatus.OFFLINE:
            self.state.connected_peers.discard(message.peer_id)
            print(f"[PEER {self.peer_id[:8]}] Peer {message.peer_id[:8]} is now OFFLINE")
        
        return {"acknowledged": True}
    
    async def _handle_content(self, message: ContentMessage) -> Dict:
        """Handle incoming encrypted content."""
        print(f"[PEER {self.peer_id[:8]}] Received content {message.content_hash[:8]}")
        
        # Store encrypted content
        self._content[message.content_hash] = bytes.fromhex(message.encrypted_content)
        
        return {"stored": True, "content_hash": message.content_hash}
    
    async def _handle_request_share(self, message: RequestMessage) -> Dict:
        """Handle request for a share."""
        content_hash = message.content_hash
        
        if content_hash in self._shares:
            share_data = self._shares[content_hash]
            return {
                "found": True,
                "share": share_data
            }
        
        return {"found": False}
    
    async def _handle_request_content(self, message: RequestMessage) -> Dict:
        """Handle request for content."""
        content_hash = message.content_hash
        
        if content_hash in self._content:
            return {
                "found": True,
                "content": self._content[content_hash].hex()
            }
        
        return {"found": False}
    
    async def _handle_heartbeat(self, message: HeartbeatMessage) -> Dict:
        """Handle heartbeat from peer."""
        self.state.last_heartbeat[message.sender_id] = time.time()
        return {"acknowledged": True}
    
    # ==================== Sending Messages ====================
    
    async def _broadcast(self, message: NetworkMessage):
        """Broadcast a message to all subscribers."""
        if self._pub_socket:
            await self._pub_socket.send(message.to_bytes())
    
    async def _broadcast_status(self, status: PeerStatus):
        """Broadcast peer status update."""
        msg = PeerStatusMessage(
            sender_id=self.peer_id,
            peer_id=self.peer_id,
            status=status,
            address=SocketConfig.get_pub_address(self.config.peer_index, self.config.host),
            capabilities=self._get_capabilities()
        )
        await self._broadcast(msg)
    
    def _get_capabilities(self) -> List[str]:
        """Get list of supported capabilities."""
        caps = ["coc", "deletion"]
        if self.config.enable_secret_sharing:
            caps.append("secret_sharing")
        if self.config.enable_timelock:
            caps.append("timelock")
        if self.config.enable_steganography:
            caps.append("steganography")
        return caps
    
    async def send_direct(self, peer_id: str, peer_index: int, message: NetworkMessage, 
                          host: str = "127.0.0.1", timeout: int = 5000) -> Optional[ResponseMessage]:
        """Send a direct request to a peer and wait for response."""
        req_socket = self._context.socket(zmq.REQ)
        req_socket.setsockopt(zmq.RCVTIMEO, timeout)
        req_socket.setsockopt(zmq.SNDTIMEO, timeout)
        req_socket.setsockopt(zmq.LINGER, 0)
        
        try:
            rep_addr = SocketConfig.get_rep_address(peer_index, host)
            req_socket.connect(rep_addr)
            
            await req_socket.send(message.to_bytes())
            resp_bytes = await req_socket.recv()
            
            return ResponseMessage.from_dict(json.loads(resp_bytes.decode("utf-8")))
        except zmq.Again:
            print(f"[PEER {self.peer_id[:8]}] Timeout sending to {peer_id[:8]}")
            return None
        except Exception as e:
            print(f"[PEER {self.peer_id[:8]}] Error sending to {peer_id[:8]}: {e}")
            return None
        finally:
            req_socket.close()
    
    async def broadcast_deletion(self, node_hash: str, originator_id: str, signature: str):
        """Broadcast a deletion token to all peers."""
        msg = DeletionTokenMessage(
            sender_id=self.peer_id,
            node_hash=node_hash,
            originator_id=originator_id,
            token_signature=signature,
            cascade=True
        )
        await self._broadcast(msg)
        print(f"[PEER {self.peer_id[:8]}] Broadcast deletion for node {node_hash[:8]}")
    
    async def send_share(self, peer_id: str, peer_index: int, share_data: Dict, 
                         content_hash: str, threshold: int, total_shares: int) -> bool:
        """Send a secret share to a specific peer."""
        msg = ShareMessage(
            sender_id=self.peer_id,
            share_index=share_data["index"],
            share_data=share_data["value"],
            content_hash=content_hash,
            threshold=threshold,
            total_shares=total_shares
        )
        
        response = await self.send_direct(peer_id, peer_index, msg)
        return response is not None and response.success
    
    async def send_coc_node(self, peer_id: str, peer_index: int, node: CoCNode) -> bool:
        """Send a CoC node to a specific peer."""
        msg = CoCNodeMessage(
            sender_id=self.peer_id,
            node_data=node.to_dict(),
            parent_hash=node.parent_hash or "",
            content_hash=node.content_hash
        )
        
        response = await self.send_direct(peer_id, peer_index, msg)
        return response is not None and response.success
    
    # ==================== Offline Handling ====================
    
    def go_offline(self):
        """Simulate going offline."""
        self.state.is_online = False
        print(f"[PEER {self.peer_id[:8]}] Now OFFLINE - messages will be queued")
    
    def go_online(self):
        """Simulate coming online and process queued messages."""
        self.state.is_online = True
        print(f"[PEER {self.peer_id[:8]}] Now ONLINE - processing queued messages")
        
        # Process queued messages
        while not self._offline_queue.empty():
            try:
                message = self._offline_queue.get_nowait()
                self.state.pending_messages.append(message)
            except Empty:
                break
    
    async def process_pending_messages(self):
        """Process all pending messages after coming online."""
        while self.state.pending_messages:
            message = self.state.pending_messages.pop(0)
            await self._handle_broadcast(message)
    
    # ==================== Utility ====================
    
    def register_peer_key(self, peer_id: str, verify_key: VerifyKey):
        """Register a peer's verification key for signature verification."""
        self._peer_keys[peer_id] = verify_key
    
    def get_share(self, content_hash: str) -> Optional[Dict]:
        """Get stored share for content."""
        return self._shares.get(content_hash)
    
    def get_content(self, content_hash: str) -> Optional[bytes]:
        """Get stored encrypted content."""
        return self._content.get(content_hash)


def run_peer_process(config_dict: Dict):
    """
    Entry point for running a peer as a standalone process.
    
    Args:
        config_dict: Dictionary with peer configuration
    """
    config = PeerConfig(
        peer_id=config_dict["peer_id"],
        peer_index=config_dict["peer_index"],
        host=config_dict.get("host", "127.0.0.1")
    )
    
    peer = NetworkPeer(config)
    
    async def main():
        await peer.start()
        
        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await peer.stop()
    
    # Handle signals
    def signal_handler(sig, frame):
        print(f"\n[PEER {config.peer_id[:8]}] Shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    asyncio.run(main())


if __name__ == "__main__":
    # Run as standalone process with arguments
    if len(sys.argv) < 3:
        print("Usage: python -m coc_framework.network.peer_process <peer_id> <peer_index>")
        sys.exit(1)
    
    config = {
        "peer_id": sys.argv[1],
        "peer_index": int(sys.argv[2]),
        "host": sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
    }
    
    run_peer_process(config)
