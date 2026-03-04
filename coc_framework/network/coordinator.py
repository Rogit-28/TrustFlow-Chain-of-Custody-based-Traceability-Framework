"""Multi-process network coordinator for TrustFlow peers."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Callable
from multiprocessing import Process

try:
    import zmq
    import zmq.asyncio
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False

from nacl.signing import SigningKey

from .protocol import (
    MessageType,
    NetworkMessage,
    ShareMessage,
    DeletionTokenMessage,
    CoCNodeMessage,
    PeerStatusMessage,
    ResponseMessage,
    PeerStatus,
    SocketConfig,
    deserialize_message,
)
from .peer_process import NetworkPeer, PeerConfig, run_peer_process
from ..core.logging import coordinator_logger


@dataclass
class PeerInfo:
    peer_id: str
    peer_index: int
    process: Optional[Process] = None
    host: str = "127.0.0.1"
    signing_key: Optional[SigningKey] = None
    is_online: bool = False
    
    @property
    def pub_address(self) -> str:
        return SocketConfig.get_pub_address(self.peer_index, self.host)
    
    @property
    def rep_address(self) -> str:
        return SocketConfig.get_rep_address(self.peer_index, self.host)


@dataclass
class ScenarioEvent:
    event_type: str
    timestamp: float
    params: Dict[str, Any]
    executed: bool = False


class NetworkCoordinator:
    """Coordinates a network of TrustFlow peers running as separate processes."""
    
    def __init__(self, host: str = "127.0.0.1"):
        if not ZMQ_AVAILABLE:
            raise RuntimeError("pyzmq is required for NetworkCoordinator")
        
        self.host = host
        self.peers: Dict[str, PeerInfo] = {}
        self._peer_index_counter = 0
        self._context: Optional[zmq.asyncio.Context] = None
        self._control_socket: Optional[zmq.asyncio.Socket] = None
        self._events: List[ScenarioEvent] = []
        self._start_time: Optional[float] = None
        self._running = False
        self._results: List[Dict[str, Any]] = []
        self._audit_log: List[Dict[str, Any]] = []
        self._on_event_complete: Optional[Callable[[str, Dict], None]] = None
        self._log = coordinator_logger()
    
    def create_peer(self, peer_id: Optional[str] = None) -> PeerInfo:
        if peer_id is None:
            import secrets
            peer_id = secrets.token_hex(8)
        
        signing_key = SigningKey.generate()
        peer_index = self._peer_index_counter
        self._peer_index_counter += 1
        
        peer_info = PeerInfo(
            peer_id=peer_id,
            peer_index=peer_index,
            host=self.host,
            signing_key=signing_key
        )
        self.peers[peer_id] = peer_info
        return peer_info
    
    def start_peer(self, peer_id: str) -> bool:
        if peer_id not in self.peers:
            self._log.warning("Unknown peer", peer_id=peer_id)
            return False
        
        peer_info = self.peers[peer_id]
        if peer_info.process is not None and peer_info.process.is_alive():
            self._log.info("Peer already running", peer_id=peer_id[:8])
            return True
        
        config = {
            "peer_id": peer_info.peer_id,
            "peer_index": peer_info.peer_index,
            "host": peer_info.host,
        }
        
        process = Process(target=run_peer_process, args=(config,), daemon=True)
        process.start()
        
        peer_info.process = process
        peer_info.is_online = True
        self._log.info("Started peer", peer_id=peer_id[:8], pid=process.pid)
        time.sleep(0.5)
        return True
    
    def stop_peer(self, peer_id: str) -> bool:
        if peer_id not in self.peers:
            return False
        
        peer_info = self.peers[peer_id]
        if peer_info.process is None:
            return False
        
        if peer_info.process.is_alive():
            peer_info.process.terminate()
            peer_info.process.join(timeout=2.0)
            if peer_info.process.is_alive():
                peer_info.process.kill()
        
        peer_info.is_online = False
        self._log.info("Stopped peer", peer_id=peer_id[:8])
        return True
    
    def start_all_peers(self):
        for peer_id in self.peers:
            self.start_peer(peer_id)
    
    def stop_all_peers(self):
        for peer_id in list(self.peers.keys()):
            self.stop_peer(peer_id)
    
    async def run_in_process(self, num_peers: int = 3) -> List[NetworkPeer]:
        """Run peers in-process (single process, multiple async peers)."""
        peers = []
        
        for i in range(num_peers):
            import secrets
            peer_id = secrets.token_hex(8)
            config = PeerConfig(peer_id=peer_id, peer_index=i, host=self.host)
            peer = NetworkPeer(config)
            await peer.start()
            
            peer_info = PeerInfo(
                peer_id=peer_id,
                peer_index=i,
                host=self.host,
                signing_key=peer.signing_key,
                is_online=True
            )
            self.peers[peer_id] = peer_info
            peers.append(peer)
        
        for peer in peers:
            for other_peer in peers:
                if peer.peer_id != other_peer.peer_id:
                    other_info = self.peers[other_peer.peer_id]
                    await peer.connect_to_peer(other_peer.peer_id, other_info.peer_index, self.host)
                    peer.register_peer_key(other_peer.peer_id, other_peer.verify_key)
        
        self._running = True
        return peers
    
    async def stop_in_process_peers(self, peers: List[NetworkPeer]):
        for peer in peers:
            await peer.stop()
        self._running = False
    
    def load_scenario(self, scenario_path: str):
        with open(scenario_path, 'r') as f:
            data = json.load(f)
        
        self._events = []
        for event_data in data.get("events", []):
            event = ScenarioEvent(
                event_type=event_data["type"],
                timestamp=event_data.get("timestamp", 0),
                params=event_data.get("params", {})
            )
            self._events.append(event)
        
        self._events.sort(key=lambda e: e.timestamp)
        self._log.info("Loaded events", count=len(self._events), path=scenario_path)
    
    def add_event(self, event_type: str, params: Dict[str, Any], timestamp: float = 0):
        event = ScenarioEvent(event_type=event_type, timestamp=timestamp, params=params)
        self._events.append(event)
        self._events.sort(key=lambda e: e.timestamp)
    
    async def execute_scenario(self, peers: List[NetworkPeer]):
        if not self._events:
            self._log.info("No events to execute")
            return
        
        self._start_time = time.time()
        peer_map = {p.peer_id: p for p in peers}
        self._log.info("Starting scenario execution", event_count=len(self._events))
        
        for event in self._events:
            elapsed = time.time() - self._start_time
            wait_time = event.timestamp - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            try:
                await self._execute_event(event, peer_map)
                event.executed = True
                if self._on_event_complete:
                    self._on_event_complete(event.event_type, event.params)
            except Exception as e:
                self._log.error("Error executing event", event_type=event.event_type, error=str(e))
                self._results.append({
                    "event": event.event_type,
                    "error": str(e),
                    "timestamp": time.time()
                })
        
        self._log.info("Scenario execution complete")
    
    async def _execute_event(self, event: ScenarioEvent, peer_map: Dict[str, NetworkPeer]):
        event_type = event.event_type
        params = event.params
        self._log.info("Executing event", event_type=event_type, params=params)
        
        if event_type == "CREATE_MESSAGE":
            await self._event_create_message(params, peer_map)
        elif event_type == "FORWARD_MESSAGE":
            await self._event_forward_message(params, peer_map)
        elif event_type == "DELETE_MESSAGE":
            await self._event_delete_message(params, peer_map)
        elif event_type == "PEER_ONLINE":
            await self._event_peer_online(params, peer_map)
        elif event_type == "PEER_OFFLINE":
            await self._event_peer_offline(params, peer_map)
        elif event_type == "DISTRIBUTE_SHARES":
            await self._event_distribute_shares(params, peer_map)
        else:
            self._log.warning("Unknown event type", event_type=event_type)
    
    async def _event_create_message(self, params: Dict, peer_map: Dict[str, NetworkPeer]):
        sender_id = params.get("sender")
        content = params.get("content", "")
        recipients = params.get("recipients", [])
        
        sender = self._find_peer(sender_id, peer_map)
        if not sender:
            self._log.warning("Sender not found", sender_id=sender_id)
            return
        
        from ..core.coc_node import CoCNode
        from ..core.crypto_core import CryptoCore
        
        content_hash = CryptoCore.hash_content(content)
        node = CoCNode.create_root(content=content, owner_id=sender.peer_id, signing_key=sender.signing_key)
        
        sender.storage.store_node(node)
        sender.storage.store_content(content_hash, content)
        
        for recipient_id in recipients:
            recipient = self._find_peer(recipient_id, peer_map)
            if recipient:
                recipient_info = self.peers.get(recipient.peer_id)
                if recipient_info:
                    success = await sender.send_coc_node(recipient.peer_id, recipient_info.peer_index, node)
                    self._log.info("Sent node", recipient=recipient_id, success=success)
        
        self._results.append({
            "event": "CREATE_MESSAGE",
            "node_hash": node.node_hash,
            "content_hash": content_hash,
            "sender": sender.peer_id,
            "recipients": recipients
        })
    
    async def _event_forward_message(self, params: Dict, peer_map: Dict[str, NetworkPeer]):
        sender_id = params.get("sender")
        node_hash = params.get("node_hash")
        recipients = params.get("recipients", [])
        
        sender = self._find_peer(sender_id, peer_map)
        if not sender:
            return
        
        node = sender.storage.get_node(node_hash)
        if not node:
            self._log.warning("Node not found", node_hash=node_hash)
            return
        
        from ..core.coc_node import CoCNode
        
        for recipient_id in recipients:
            recipient = self._find_peer(recipient_id, peer_map)
            if recipient:
                child_node = CoCNode.create_child(parent=node, new_owner_id=recipient.peer_id, signing_key=sender.signing_key)
                sender.storage.store_node(child_node)
                recipient_info = self.peers.get(recipient.peer_id)
                if recipient_info:
                    await sender.send_coc_node(recipient.peer_id, recipient_info.peer_index, child_node)
    
    async def _event_delete_message(self, params: Dict, peer_map: Dict[str, NetworkPeer]):
        originator_id = params.get("originator")
        node_hash = params.get("node_hash")
        
        originator = self._find_peer(originator_id, peer_map)
        if not originator:
            return
        
        node = originator.storage.get_node(node_hash)
        if not node:
            self._log.warning("Node not found for deletion", node_hash=node_hash)
            return
        
        if node.owner_id != originator.peer_id:
            self._log.warning("Not owner, cannot delete")
            return
        
        from ..core.crypto_core import CryptoCore
        timestamp = datetime.now(timezone.utc).isoformat()
        token_data = f"{node_hash}{originator.peer_id}{timestamp}"
        signature = CryptoCore.sign_message(originator.signing_key, token_data).hex()
        
        await originator.broadcast_deletion(node_hash, originator.peer_id, signature)
        originator.storage.remove_node(node_hash)
    
    async def _event_peer_online(self, params: Dict, peer_map: Dict[str, NetworkPeer]):
        peer_id = params.get("peer")
        peer = self._find_peer(peer_id, peer_map)
        if peer:
            peer.go_online()
            await peer.process_pending_messages()
    
    async def _event_peer_offline(self, params: Dict, peer_map: Dict[str, NetworkPeer]):
        peer_id = params.get("peer")
        peer = self._find_peer(peer_id, peer_map)
        if peer:
            peer.go_offline()
    
    async def _event_distribute_shares(self, params: Dict, peer_map: Dict[str, NetworkPeer]):
        sender_id = params.get("sender")
        content = params.get("content", "")
        recipients = params.get("recipients", [])
        threshold = params.get("threshold", len(recipients) // 2 + 1)
        
        sender = self._find_peer(sender_id, peer_map)
        if not sender:
            return
        
        from ..core.secret_sharing import SecretSharingEngine
        
        engine = SecretSharingEngine()
        recipient_peers = [self._find_peer(r, peer_map) for r in recipients]
        recipient_peers = [p for p in recipient_peers if p]
        recipient_ids = [p.peer_id for p in recipient_peers]
        
        share_map = engine.split_content(content, recipient_ids, threshold)
        
        for peer_id, share in share_map.items():
            recipient = peer_map.get(peer_id)
            if recipient:
                recipient_info = self.peers.get(peer_id)
                if recipient_info:
                    await sender.send_share(
                        peer_id,
                        recipient_info.peer_index,
                        {"index": share.index, "value": share.value},
                        share.content_hash,
                        share.threshold,
                        share.total_shares
                    )
        
        self._results.append({
            "event": "DISTRIBUTE_SHARES",
            "content_hash": share_map[recipient_ids[0]].content_hash if recipient_ids else "",
            "threshold": threshold,
            "total_shares": len(recipients)
        })
    
    def _find_peer(self, identifier: str, peer_map: Dict[str, NetworkPeer]) -> Optional[NetworkPeer]:
        if identifier in peer_map:
            return peer_map[identifier]
        for peer_id, peer in peer_map.items():
            if peer_id.startswith(identifier) or identifier in peer_id:
                return peer
        return None
    
    def get_results(self) -> List[Dict[str, Any]]:
        return self._results
    
    def get_audit_log(self) -> List[Dict[str, Any]]:
        return self._audit_log
    
    def set_event_callback(self, callback: Callable[[str, Dict], None]):
        self._on_event_complete = callback


async def demo():
    print("=== TrustFlow Network Coordinator Demo ===\n")
    
    coordinator = NetworkCoordinator()
    peers = await coordinator.run_in_process(num_peers=4)
    
    print(f"\nCreated {len(peers)} peers:")
    for peer in peers:
        print(f"  - {peer.peer_id}")
    
    coordinator.add_event("CREATE_MESSAGE", {
        "sender": peers[0].peer_id,
        "content": "Hello from TrustFlow!",
        "recipients": [peers[1].peer_id, peers[2].peer_id]
    }, timestamp=0)
    
    coordinator.add_event("DISTRIBUTE_SHARES", {
        "sender": peers[0].peer_id,
        "content": "Secret data that needs protection",
        "recipients": [p.peer_id for p in peers],
        "threshold": 3
    }, timestamp=1)
    
    print("\n--- Executing Scenario ---")
    await coordinator.execute_scenario(peers)
    
    print("\n--- Results ---")
    for result in coordinator.get_results():
        print(f"  {result}")
    
    print("\n--- Share Distribution ---")
    for peer in peers:
        shares = list(peer._shares.keys())
        print(f"  Peer {peer.peer_id[:8]}: {len(shares)} shares")
    
    await coordinator.stop_in_process_peers(peers)
    print("\n[COORD] Demo complete")


if __name__ == "__main__":
    asyncio.run(demo())
