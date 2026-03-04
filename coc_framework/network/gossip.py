"""
TrustFlow Gossip Protocol - Epidemic-style message dissemination.

Replaces O(N²) mesh with O(N log N) gossip. Signed envelopes for origin verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

try:
    import zmq
    import zmq.asyncio
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False

from nacl.signing import SigningKey, VerifyKey

from .protocol import (
    MessageType,
    NetworkMessage,
    PeerStatus,
    HeartbeatMessage,
    deserialize_message,
    SocketConfig,
    MESSAGE_MAX_AGE_SECONDS,
    MESSAGE_MAX_FUTURE_SECONDS,
)
from ..core.crypto_core import CryptoCore
from ..core.logging import gossip_logger


DEFAULT_FANOUT = 3
DEFAULT_TTL = 10
DEFAULT_CACHE_SIZE = 10000
DEFAULT_CACHE_TTL = 300
ANTI_ENTROPY_INTERVAL = 30


class GossipMessageType(Enum):
    """Types of gossip protocol messages."""
    GOSSIP = "gossip"
    PULL_REQUEST = "pull_request"
    PULL_RESPONSE = "pull_response"
    PEER_LIST_REQUEST = "peer_list"
    PEER_LIST_RESPONSE = "peer_list_response"


class GossipSignatureError(Exception):
    """Raised when gossip envelope signature verification fails."""
    pass


class GossipTimestampError(Exception):
    """Raised when gossip envelope timestamp is invalid."""
    pass


@dataclass
class GossipEnvelope:
    """
    Envelope for gossip dissemination with signature by origin peer.
    Signature covers: origin_id | timestamp | msg_id | payload_hash
    """
    msg_id: str
    payload: Dict[str, Any]
    origin_id: str
    ttl: int = DEFAULT_TTL
    timestamp: float = field(default_factory=time.time)
    path: List[str] = field(default_factory=list)
    signature: str = ""
    
    _DELIMITER = "|"
    
    def decrement_ttl(self) -> bool:
        self.ttl -= 1
        return self.ttl > 0
    
    def add_to_path(self, peer_id: str) -> None:
        self.path.append(peer_id)
    
    def _get_signing_data(self) -> str:
        payload_hash = hashlib.sha256(json.dumps(self.payload, sort_keys=True).encode()).hexdigest()
        return f"{self.origin_id}{self._DELIMITER}{self.timestamp}{self._DELIMITER}{self.msg_id}{self._DELIMITER}{payload_hash}"
    
    def sign(self, signing_key: SigningKey) -> None:
        data = self._get_signing_data()
        self.signature = CryptoCore.sign_message(signing_key, data).hex()
    
    def verify(self, verify_key: VerifyKey) -> bool:
        if not self.signature:
            return False
        data = self._get_signing_data()
        try:
            return CryptoCore.verify_signature(verify_key, data, bytes.fromhex(self.signature))
        except Exception:
            return False
    
    def validate_timestamp(
        self,
        max_age: int = MESSAGE_MAX_AGE_SECONDS,
        max_future: int = MESSAGE_MAX_FUTURE_SECONDS
    ) -> Tuple[bool, str]:
        now = time.time()
        age = now - self.timestamp
        if age > max_age:
            return False, f"Gossip too old ({age:.0f}s > {max_age}s)"
        if age < -max_future:
            return False, f"Gossip from future ({-age:.0f}s ahead)"
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "payload": self.payload,
            "origin_id": self.origin_id,
            "ttl": self.ttl,
            "timestamp": self.timestamp,
            "path": self.path,
            "signature": self.signature,
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> GossipEnvelope:
        return GossipEnvelope(**data)
    
    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict()).encode("utf-8")
    
    @staticmethod
    def from_bytes(data: bytes) -> GossipEnvelope:
        return GossipEnvelope.from_dict(json.loads(data.decode("utf-8")))


@dataclass
class PeerInfo:
    """Information about a known peer."""
    peer_id: str
    address: str
    last_seen: float = field(default_factory=time.time)
    status: PeerStatus = PeerStatus.UNKNOWN
    capabilities: FrozenSet[str] = field(default_factory=frozenset)
    
    def update_last_seen(self) -> None:
        self.last_seen = time.time()
    
    def is_stale(self, timeout: float = SocketConfig.HEARTBEAT_TIMEOUT) -> bool:
        return time.time() - self.last_seen > timeout


class MessageCache:
    """LRU-style cache for seen messages with TTL-based expiration."""
    
    def __init__(self, max_size: int = DEFAULT_CACHE_SIZE, ttl_seconds: float = DEFAULT_CACHE_TTL):
        self._cache: Dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._last_cleanup = time.time()
        self._cleanup_interval = 60
    
    def has_seen(self, msg_id: str) -> bool:
        self._maybe_cleanup()
        if msg_id not in self._cache:
            return False
        if time.time() - self._cache[msg_id] > self._ttl:
            del self._cache[msg_id]
            return False
        return True
    
    def mark_seen(self, msg_id: str) -> None:
        self._cache[msg_id] = time.time()
        self._maybe_cleanup()
    
    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        cutoff = now - self._ttl
        expired = [k for k, v in self._cache.items() if v < cutoff]
        for k in expired:
            del self._cache[k]
        if len(self._cache) > self._max_size:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1])
            for k, _ in sorted_items[:len(self._cache) - self._max_size]:
                del self._cache[k]
        self._last_cleanup = now
    
    def get_recent_ids(self, count: int = 100) -> List[str]:
        sorted_items = sorted(self._cache.items(), key=lambda x: x[1], reverse=True)
        return [k for k, _ in sorted_items[:count]]


class GossipPeer:
    """Peer using gossip protocol for O(fanout) message dissemination."""
    
    def __init__(
        self,
        peer_id: str,
        host: str = "127.0.0.1",
        port: int = 0,
        fanout: int = DEFAULT_FANOUT,
        max_peers: int = 50,
        signing_key: Optional[SigningKey] = None,
    ):
        if not ZMQ_AVAILABLE:
            raise RuntimeError("pyzmq is required for GossipPeer")
        
        self.peer_id = peer_id
        self.host = host
        self.port = port
        self.fanout = fanout
        self.max_peers = max_peers
        self.signing_key = signing_key or SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        
        self._peers: Dict[str, PeerInfo] = {}
        self._peer_keys: Dict[str, VerifyKey] = {}
        self._seen_messages = MessageCache()
        self._handlers: Dict[MessageType, Callable] = {}
        
        self._context: Optional[zmq.asyncio.Context] = None
        self._router: Optional[zmq.asyncio.Socket] = None
        self._dealers: Dict[str, zmq.asyncio.Socket] = {}
        
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._log = gossip_logger(peer_id)
    
    @property
    def address(self) -> str:
        return f"tcp://{self.host}:{self.port}"
    
    def get_peer_count(self) -> int:
        return len(self._peers)
    
    def get_active_peers(self) -> List[str]:
        return [p.peer_id for p in self._peers.values() if not p.is_stale()]
    
    async def start(self) -> None:
        self._running = True
        self._context = zmq.asyncio.Context()
        
        self._router = self._context.socket(zmq.ROUTER)
        self._router.setsockopt(zmq.ROUTER_MANDATORY, 1)
        
        if self.port == 0:
            self.port = self._router.bind_to_random_port(f"tcp://{self.host}")
        else:
            self._router.bind(f"tcp://{self.host}:{self.port}")
        
        self._log.info("Started", address=self.address)
        
        self._tasks.append(asyncio.create_task(self._receive_loop()))
        self._tasks.append(asyncio.create_task(self._anti_entropy_loop()))
        self._tasks.append(asyncio.create_task(self._peer_maintenance_loop()))
    
    async def stop(self) -> None:
        self._running = False
        
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        
        if self._router:
            self._router.close()
        for dealer in self._dealers.values():
            dealer.close()
        self._dealers.clear()
        
        if self._context:
            self._context.term()
        
        self._log.info("Stopped")
    
    def add_peer(
        self, 
        peer_id: str, 
        address: str, 
        capabilities: Optional[Set[str]] = None,
        verify_key: Optional[VerifyKey] = None
    ) -> None:
        if peer_id == self.peer_id:
            return
        
        if len(self._peers) >= self.max_peers and peer_id not in self._peers:
            self._evict_oldest_peer()
        
        caps = frozenset(capabilities) if capabilities else frozenset()
        self._peers[peer_id] = PeerInfo(
            peer_id=peer_id,
            address=address,
            status=PeerStatus.ONLINE,
            capabilities=caps,
        )
        
        if verify_key:
            self._peer_keys[peer_id] = verify_key
    
    def register_peer_key(self, peer_id: str, verify_key: VerifyKey) -> None:
        self._peer_keys[peer_id] = verify_key
    
    def get_peer_key(self, peer_id: str) -> Optional[VerifyKey]:
        return self._peer_keys.get(peer_id)
    
    def remove_peer(self, peer_id: str) -> None:
        self._peers.pop(peer_id, None)
        if peer_id in self._dealers:
            self._dealers[peer_id].close()
            del self._dealers[peer_id]
        self._peer_keys.pop(peer_id, None)
    
    def _evict_oldest_peer(self) -> None:
        if not self._peers:
            return
        oldest = min(self._peers.values(), key=lambda p: p.last_seen)
        self.remove_peer(oldest.peer_id)
    
    def _select_gossip_targets(self, exclude: Optional[Set[str]] = None) -> List[str]:
        exclude = exclude or set()
        available = [p for p in self._peers.keys() if p not in exclude]
        if len(available) <= self.fanout:
            return available
        return random.sample(available, self.fanout)
    
    async def _get_dealer(self, peer_id: str) -> Optional[zmq.asyncio.Socket]:
        if peer_id not in self._dealers:
            if peer_id not in self._peers:
                return None
            peer_info = self._peers[peer_id]
            dealer = self._context.socket(zmq.DEALER)
            dealer.setsockopt_string(zmq.IDENTITY, self.peer_id)
            dealer.setsockopt(zmq.LINGER, 0)
            dealer.setsockopt(zmq.SNDTIMEO, 1000)
            dealer.connect(peer_info.address)
            self._dealers[peer_id] = dealer
        return self._dealers[peer_id]
    
    def register_handler(self, msg_type: MessageType, handler: Callable) -> None:
        self._handlers[msg_type] = handler
    
    async def _receive_loop(self) -> None:
        while self._running:
            try:
                if await self._router.poll(timeout=100):
                    frames = await self._router.recv_multipart()
                    if len(frames) >= 2:
                        sender_id = frames[0].decode("utf-8")
                        data = frames[-1]
                        await self._handle_received(sender_id, data)
            except zmq.ZMQError as e:
                if self._running:
                    self._log.error("Receive error", error=str(e))
            except Exception as e:
                if self._running:
                    self._log.error("Handler error", error=str(e))
    
    async def _handle_received(self, sender_id: str, data: bytes) -> None:
        try:
            envelope = GossipEnvelope.from_bytes(data)
        except Exception:
            try:
                message = deserialize_message(data)
                await self._dispatch_message(message)
            except Exception as e:
                self._log.error("Failed to parse message", error=str(e))
            return
        
        if sender_id in self._peers:
            self._peers[sender_id].update_last_seen()
        
        if self._seen_messages.has_seen(envelope.msg_id):
            return
        
        origin_key = self._peer_keys.get(envelope.origin_id)
        if origin_key:
            if not envelope.verify(origin_key):
                self._log.warning("Gossip dropped - invalid signature", origin=envelope.origin_id[:8], msg_id=envelope.msg_id[:8])
                return
        else:
            self._log.warning("Gossip dropped - unknown origin", origin=envelope.origin_id[:8], msg_id=envelope.msg_id[:8])
            return
        
        valid, error = envelope.validate_timestamp()
        if not valid:
            self._log.warning("Gossip dropped - timestamp invalid", origin=envelope.origin_id[:8], error=error)
            return
        
        self._seen_messages.mark_seen(envelope.msg_id)
        
        try:
            message = deserialize_message(envelope.payload)
            await self._dispatch_message(message)
        except Exception as e:
            self._log.error("Handler error", error=str(e))
        
        if envelope.decrement_ttl():
            envelope.add_to_path(self.peer_id)
            exclude = set(envelope.path) | {sender_id, envelope.origin_id}
            await self._forward_gossip(envelope, exclude)
    
    async def _dispatch_message(self, message: NetworkMessage) -> None:
        handler = self._handlers.get(message.msg_type)
        if handler:
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)
    
    async def gossip(self, message: NetworkMessage) -> None:
        """Disseminate a message using gossip protocol."""
        msg_id = hashlib.sha256(f"{self.peer_id}:{time.time()}:{message.msg_id}".encode()).hexdigest()[:32]
        
        envelope = GossipEnvelope(
            msg_id=msg_id,
            payload=message.to_dict(),
            origin_id=self.peer_id,
            ttl=DEFAULT_TTL,
        )
        envelope.add_to_path(self.peer_id)
        envelope.sign(self.signing_key)
        
        self._seen_messages.mark_seen(msg_id)
        targets = self._select_gossip_targets()
        await self._send_to_peers(envelope, targets)
    
    async def _forward_gossip(self, envelope: GossipEnvelope, exclude: Set[str]) -> None:
        targets = self._select_gossip_targets(exclude)
        await self._send_to_peers(envelope, targets)
    
    async def _send_to_peers(self, envelope: GossipEnvelope, peer_ids: List[str]) -> None:
        data = envelope.to_bytes()
        for peer_id in peer_ids:
            dealer = await self._get_dealer(peer_id)
            if dealer:
                try:
                    await dealer.send_multipart([b"", data])
                except zmq.ZMQError as e:
                    self._log.error("Send failed", target_peer=peer_id[:8], error=str(e))
    
    async def send_direct(self, peer_id: str, message: NetworkMessage) -> bool:
        dealer = await self._get_dealer(peer_id)
        if not dealer:
            return False
        try:
            await dealer.send_multipart([b"", message.to_bytes()])
            return True
        except zmq.ZMQError:
            return False
    
    async def _anti_entropy_loop(self) -> None:
        while self._running:
            await asyncio.sleep(ANTI_ENTROPY_INTERVAL)
            
            if not self._peers:
                continue
            
            peer_id = random.choice(list(self._peers.keys()))
            our_ids = self._seen_messages.get_recent_ids(100)
            pull_request = {
                "type": GossipMessageType.PULL_REQUEST.value,
                "sender_id": self.peer_id,
                "message_ids": our_ids,
            }
            
            dealer = await self._get_dealer(peer_id)
            if dealer:
                try:
                    await dealer.send_multipart([b"", json.dumps(pull_request).encode()])
                except zmq.ZMQError:
                    pass
    
    async def _peer_maintenance_loop(self) -> None:
        while self._running:
            await asyncio.sleep(SocketConfig.HEARTBEAT_INTERVAL)
            
            stale = [p for p in self._peers.values() if p.is_stale()]
            for peer_info in stale:
                self._log.info("Peer stale, removing", stale_peer=peer_info.peer_id[:8])
                self.remove_peer(peer_info.peer_id)
            
            heartbeat = HeartbeatMessage(sender_id=self.peer_id)
            await self.gossip(heartbeat)
    
    async def discover_peers(self, bootstrap_addresses: List[str]) -> None:
        for address in bootstrap_addresses:
            try:
                sock = self._context.socket(zmq.DEALER)
                sock.setsockopt_string(zmq.IDENTITY, self.peer_id)
                sock.setsockopt(zmq.LINGER, 0)
                sock.setsockopt(zmq.RCVTIMEO, 5000)
                sock.connect(address)
                
                request = {
                    "type": GossipMessageType.PEER_LIST_REQUEST.value,
                    "sender_id": self.peer_id,
                    "address": self.address,
                }
                await sock.send_multipart([b"", json.dumps(request).encode()])
                
                try:
                    frames = await sock.recv_multipart()
                    response = json.loads(frames[-1].decode())
                    
                    if response.get("type") == GossipMessageType.PEER_LIST_RESPONSE.value:
                        for peer_data in response.get("peers", []):
                            self.add_peer(
                                peer_data["peer_id"],
                                peer_data["address"],
                                set(peer_data.get("capabilities", [])),
                            )
                except zmq.Again:
                    pass
                
                sock.close()
            except Exception as e:
                self._log.error("Discovery failed", address=address, error=str(e))


class GossipNetwork:
    """Network manager for gossip-based peer coordination."""
    
    def __init__(self, host: str = "127.0.0.1", base_port: int = 6000):
        self.host = host
        self.base_port = base_port
        self._peers: Dict[str, GossipPeer] = {}
        self._next_port = base_port
    
    def create_peer(self, peer_id: str, fanout: int = DEFAULT_FANOUT) -> GossipPeer:
        peer = GossipPeer(
            peer_id=peer_id,
            host=self.host,
            port=self._next_port,
            fanout=fanout,
        )
        self._peers[peer_id] = peer
        self._next_port += 1
        return peer
    
    def get_peer(self, peer_id: str) -> Optional[GossipPeer]:
        return self._peers.get(peer_id)
    
    async def start_all(self) -> None:
        for peer in self._peers.values():
            await peer.start()
        
        peer_list = list(self._peers.values())
        for peer in peer_list:
            for other in peer_list:
                if other.peer_id != peer.peer_id:
                    peer.add_peer(other.peer_id, other.address)
    
    async def stop_all(self) -> None:
        for peer in self._peers.values():
            await peer.stop()
    
    async def broadcast(self, message: NetworkMessage) -> None:
        if self._peers:
            peer = random.choice(list(self._peers.values()))
            await peer.gossip(message)
