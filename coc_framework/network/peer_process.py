"""TrustFlow Network Peer - standalone process with ZeroMQ communication."""

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

import logging
_zmq_logger = logging.getLogger("trustflow.network.peer_process")
if not ZMQ_AVAILABLE:
    _zmq_logger.warning("pyzmq not installed. Network functionality disabled.")

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
    KeyExchangeMessage,
    KeyExchangeAckMessage,
    PeerStatus,
    SocketConfig,
    SignedEnvelope,
    SignatureVerificationError,
    MessageTimestampError,
    deserialize_message,
    unwrap_and_verify,
)

# Import core components
if TYPE_CHECKING:
    from ..core.coc_node import CoCNode
    from ..core.secret_sharing import Share

from ..core.crypto_core import CryptoCore
from ..interfaces.storage_backend import InMemoryStorage
from ..core.logging import peer_logger


@dataclass
class PeerConfig:
    peer_id: str
    peer_index: int
    host: str = "127.0.0.1"
    signing_key: Optional[SigningKey] = None
    enable_secret_sharing: bool = True
    enable_timelock: bool = True
    enable_steganography: bool = True


@dataclass
class PeerState:
    is_online: bool = True
    connected_peers: Set[str] = field(default_factory=set)
    pending_messages: List[NetworkMessage] = field(default_factory=list)
    last_heartbeat: Dict[str, float] = field(default_factory=dict)


class NetworkPeer:
    """Standalone TrustFlow peer with ZeroMQ networking and cryptographic identity."""
    
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
        
        self.storage = InMemoryStorage()
        self._shares: Dict[str, Any] = {}
        self._content: Dict[str, bytes] = {}
        self._peer_keys: Dict[str, VerifyKey] = {}
        
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._register_default_handlers()
        
        self._context: Optional[zmq.asyncio.Context] = None
        self._pub_socket: Optional[zmq.asyncio.Socket] = None
        self._rep_socket: Optional[zmq.asyncio.Socket] = None
        self._sub_sockets: Dict[str, zmq.asyncio.Socket] = {}
        self._offline_queue: Queue = Queue()
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._log = peer_logger(self.peer_id)
    
    def _register_default_handlers(self):
        self._message_handlers[MessageType.SHARE] = self._handle_share
        self._message_handlers[MessageType.DELETION_TOKEN] = self._handle_deletion
        self._message_handlers[MessageType.COC_NODE] = self._handle_coc_node
        self._message_handlers[MessageType.PEER_STATUS] = self._handle_peer_status
        self._message_handlers[MessageType.CONTENT] = self._handle_content
        self._message_handlers[MessageType.REQUEST_SHARE] = self._handle_request_share
        self._message_handlers[MessageType.REQUEST_CONTENT] = self._handle_request_content
        self._message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
        self._message_handlers[MessageType.KEY_EXCHANGE] = self._handle_key_exchange
        self._message_handlers[MessageType.KEY_EXCHANGE_ACK] = self._handle_key_exchange_ack
    
    def register_handler(self, msg_type: MessageType, handler: Callable):
        self._message_handlers[msg_type] = handler
    
    async def start(self):
        self._running = True
        self._context = zmq.asyncio.Context()
        
        self._pub_socket = self._context.socket(zmq.PUB)
        pub_addr = SocketConfig.get_pub_address(self.config.peer_index, self.config.host)
        self._pub_socket.bind(pub_addr)
        
        self._rep_socket = self._context.socket(zmq.REP)
        rep_addr = SocketConfig.get_rep_address(self.config.peer_index, self.config.host)
        self._rep_socket.bind(rep_addr)
        
        self._log.info("Started", pub_addr=pub_addr, rep_addr=rep_addr)
        await self._broadcast_status(PeerStatus.ONLINE)
        
        self._loop = asyncio.get_event_loop()
        asyncio.create_task(self._rep_loop())
        asyncio.create_task(self._sub_loop())
        asyncio.create_task(self._heartbeat_loop())
    
    async def stop(self):
        self._running = False
        await self._broadcast_status(PeerStatus.OFFLINE)
        
        if self._pub_socket:
            self._pub_socket.close()
        if self._rep_socket:
            self._rep_socket.close()
        for sock in self._sub_sockets.values():
            sock.close()
        
        if self._context:
            self._context.term()
        
        self._log.info("Stopped")
    
    async def connect_to_peer(self, peer_id: str, peer_index: int, host: str = "127.0.0.1"):
        """Subscribe to peer's broadcasts and perform key exchange."""
        if peer_id in self._sub_sockets:
            return  # Already connected
        
        sub_socket = self._context.socket(zmq.SUB)
        pub_addr = SocketConfig.get_pub_address(peer_index, host)
        sub_socket.connect(pub_addr)
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self._sub_sockets[peer_id] = sub_socket
        self.state.connected_peers.add(peer_id)
        
        self._log.info("Connected to peer", target_peer=peer_id[:8], address=pub_addr)
        await self._perform_key_exchange(peer_id, peer_index, host)
    
    async def _perform_key_exchange(self, peer_id: str, peer_index: int, host: str = "127.0.0.1"):
        """Send our public key and receive theirs for authenticated communication."""
        key_exchange_msg = KeyExchangeMessage(
            sender_id=self.peer_id,
            public_key=self.verify_key.encode().hex(),
            peer_address=SocketConfig.get_rep_address(self.config.peer_index, self.config.host),
        )
        
        req_socket = self._context.socket(zmq.REQ)
        req_socket.setsockopt(zmq.RCVTIMEO, 5000)
        req_socket.setsockopt(zmq.SNDTIMEO, 5000)
        req_socket.setsockopt(zmq.LINGER, 0)
        
        try:
            rep_addr = SocketConfig.get_rep_address(peer_index, host)
            req_socket.connect(rep_addr)
            
            await req_socket.send(key_exchange_msg.to_bytes())
            resp_bytes = await req_socket.recv()
            response = ResponseMessage.from_dict(json.loads(resp_bytes.decode("utf-8")))
            
            if response.success and response.data.get("public_key"):
                peer_key_bytes = bytes.fromhex(response.data["public_key"])
                peer_verify_key = VerifyKey(peer_key_bytes)
                self._peer_keys[peer_id] = peer_verify_key
                
                self._log.info("Key exchange complete", target_peer=peer_id[:8])
            else:
                self._log.warning("Key exchange failed", target_peer=peer_id[:8], 
                                error=response.error_message or "Unknown error")
        except zmq.Again:
            self._log.warning("Key exchange timeout", target_peer=peer_id[:8])
        except Exception as e:
            self._log.error("Key exchange error", target_peer=peer_id[:8], error=str(e))
        finally:
            req_socket.close()
    
    async def disconnect_from_peer(self, peer_id: str):
        if peer_id in self._sub_sockets:
            self._sub_sockets[peer_id].close()
            del self._sub_sockets[peer_id]
            self.state.connected_peers.discard(peer_id)
            self._log.info("Disconnected from peer", target_peer=peer_id[:8])
    
    async def _rep_loop(self):
        while self._running:
            try:
                if await self._rep_socket.poll(timeout=100):
                    msg_bytes = await self._rep_socket.recv()
                    
                    try:
                        message, sender_id = unwrap_and_verify(
                            msg_bytes,
                            lambda pid: self._peer_keys.get(pid),
                            validate_time=True
                        )
                    except SignatureVerificationError as e:
                        self._log.warning("Request rejected - signature verification failed", error=str(e))
                        error_resp = ResponseMessage(
                            sender_id=self.peer_id,
                            success=False,
                            error_message=f"Signature verification failed: {e}"
                        )
                        envelope = SignedEnvelope.wrap(error_resp, self.peer_id, self.signing_key)
                        await self._rep_socket.send(envelope.to_bytes())
                        continue
                    except MessageTimestampError as e:
                        self._log.warning("Request rejected - timestamp invalid", error=str(e))
                        error_resp = ResponseMessage(
                            sender_id=self.peer_id,
                            success=False,
                            error_message=f"Timestamp validation failed: {e}"
                        )
                        envelope = SignedEnvelope.wrap(error_resp, self.peer_id, self.signing_key)
                        await self._rep_socket.send(envelope.to_bytes())
                        continue
                    except Exception:
                        # Fallback: try plain message for key exchange
                        try:
                            message = deserialize_message(msg_bytes)
                            sender_id = message.sender_id
                            if message.msg_type not in (MessageType.KEY_EXCHANGE, MessageType.KEY_EXCHANGE_ACK):
                                self._log.warning("Unsigned non-key-exchange message rejected", sender=sender_id[:8])
                                error_resp = ResponseMessage(
                                    sender_id=self.peer_id,
                                    success=False,
                                    error_message="Unsigned messages not accepted"
                                )
                                await self._rep_socket.send(error_resp.to_bytes())
                                continue
                        except Exception as parse_err:
                            self._log.error("Failed to parse message", error=str(parse_err))
                            error_resp = ResponseMessage(
                                sender_id=self.peer_id,
                                success=False,
                                error_message="Invalid message format"
                            )
                            await self._rep_socket.send(error_resp.to_bytes())
                            continue
                    
                    response = await self._handle_request(message)
                    envelope = SignedEnvelope.wrap(response, self.peer_id, self.signing_key)
                    await self._rep_socket.send(envelope.to_bytes())
            except zmq.ZMQError as e:
                if self._running:
                    self._log.error("REP error", error=str(e))
            except Exception as e:
                if self._running:
                    self._log.error("REP handler error", error=str(e))
                    error_resp = ResponseMessage(
                        sender_id=self.peer_id,
                        success=False,
                        error_message=str(e)
                    )
                    try:
                        envelope = SignedEnvelope.wrap(error_resp, self.peer_id, self.signing_key)
                        await self._rep_socket.send(envelope.to_bytes())
                    except zmq.ZMQError:
                        pass
    
    async def _sub_loop(self):
        while self._running:
            for peer_id, sub_socket in list(self._sub_sockets.items()):
                try:
                    if await sub_socket.poll(timeout=10):
                        msg_bytes = await sub_socket.recv()
                        
                        try:
                            message, sender_id = unwrap_and_verify(
                                msg_bytes,
                                lambda pid: self._peer_keys.get(pid),
                                validate_time=True
                            )
                            await self._handle_broadcast(message)
                        except SignatureVerificationError as e:
                            self._log.warning(
                                "Broadcast dropped - signature verification failed",
                                source_peer=peer_id[:8],
                                error=str(e)
                            )
                        except MessageTimestampError as e:
                            self._log.warning(
                                "Broadcast dropped - timestamp invalid",
                                source_peer=peer_id[:8],
                                error=str(e)
                            )
                except zmq.ZMQError as e:
                    if self._running:
                        self._log.error("SUB error", source_peer=peer_id[:8], error=str(e))
                except Exception as e:
                    if self._running:
                        self._log.error("SUB handler error", error=str(e))
            
            await asyncio.sleep(0.01)
    
    async def _heartbeat_loop(self):
        sequence = 0
        while self._running:
            heartbeat = HeartbeatMessage(
                sender_id=self.peer_id,
                sequence=sequence,
                load=0
            )
            await self._broadcast(heartbeat)
            sequence += 1
            await asyncio.sleep(SocketConfig.HEARTBEAT_INTERVAL)
    
    async def _handle_request(self, message: NetworkMessage) -> ResponseMessage:
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
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                self._log.error("Broadcast handler error", error=str(e))
    
    async def _handle_share(self, message: ShareMessage) -> Dict:
        self._log.info("Received share", share_index=message.share_index, content_hash=message.content_hash[:8])
        self._shares[message.content_hash] = {
            "index": message.share_index,
            "data": message.share_data,
            "threshold": message.threshold,
            "total": message.total_shares,
            "from": message.sender_id,
        }
        
        return {"stored": True, "content_hash": message.content_hash}
    
    async def _handle_deletion(self, message: DeletionTokenMessage) -> Dict:
        self._log.info("Received deletion token", node_hash=message.node_hash[:8])
        originator_key = self._peer_keys.get(message.originator_id)
        if originator_key:
            token_data = f"{message.node_hash}{message.originator_id}{message.timestamp}"
            if not CryptoCore.verify_signature(originator_key, token_data, bytes.fromhex(message.token_signature)):
                self._log.warning("Invalid deletion token signature")
                return {"deleted": False, "reason": "invalid_signature"}
        
        node = self.storage.get_node(message.node_hash)
        if node:
            self.storage.remove_node(message.node_hash)
            if node.content_hash in self._shares:
                del self._shares[node.content_hash]
            if node.content_hash in self._content:
                del self._content[node.content_hash]
            
            self._log.info("Deleted node", node_hash=message.node_hash[:8])
            return {"deleted": True, "node_hash": message.node_hash}
        
        return {"deleted": False, "reason": "not_found"}
    
    async def _handle_coc_node(self, message: CoCNodeMessage) -> Dict:
        self._log.info("Received CoC node", content_hash=message.content_hash[:8])
        from ..core.coc_node import CoCNode
        node = CoCNode.from_dict(message.node_data)
        self.storage.store_node(node)
        
        return {"stored": True, "node_hash": node.node_hash}
    
    async def _handle_peer_status(self, message: PeerStatusMessage) -> Dict:
        if message.status == PeerStatus.ONLINE:
            self.state.connected_peers.add(message.peer_id)
            self._log.info("Peer online", target_peer=message.peer_id[:8])
        elif message.status == PeerStatus.OFFLINE:
            self.state.connected_peers.discard(message.peer_id)
            self._log.info("Peer offline", target_peer=message.peer_id[:8])
        
        return {"acknowledged": True}
    
    async def _handle_content(self, message: ContentMessage) -> Dict:
        self._log.info("Received content", content_hash=message.content_hash[:8])
        self._content[message.content_hash] = bytes.fromhex(message.encrypted_content)
        return {"stored": True, "content_hash": message.content_hash}
    
    async def _handle_request_share(self, message: RequestMessage) -> Dict:
        content_hash = message.content_hash
        
        if content_hash in self._shares:
            share_data = self._shares[content_hash]
            return {
                "found": True,
                "share": share_data
            }
        
        return {"found": False}
    
    async def _handle_request_content(self, message: RequestMessage) -> Dict:
        content_hash = message.content_hash
        
        if content_hash in self._content:
            return {
                "found": True,
                "content": self._content[content_hash].hex()
            }
        
        return {"found": False}
    
    async def _handle_heartbeat(self, message: HeartbeatMessage) -> Dict:
        self.state.last_heartbeat[message.sender_id] = time.time()
        return {"acknowledged": True}
    
    async def _handle_key_exchange(self, message: KeyExchangeMessage) -> Dict:
        """Store sender's public key and return ours."""
        self._log.info("Key exchange request", from_peer=message.sender_id[:8])
        
        try:
            sender_key_bytes = bytes.fromhex(message.public_key)
            sender_verify_key = VerifyKey(sender_key_bytes)
            self._peer_keys[message.sender_id] = sender_verify_key
            self._log.info("Stored peer key", peer=message.sender_id[:8])
        except Exception as e:
            self._log.error("Failed to store peer key", peer=message.sender_id[:8], error=str(e))
            return {"success": False, "error": str(e)}
        
        return {
            "success": True,
            "public_key": self.verify_key.encode().hex(),
            "peer_id": self.peer_id,
            "original_nonce": message.nonce,
        }
    
    async def _handle_key_exchange_ack(self, message: KeyExchangeAckMessage) -> Dict:
        self._log.info("Key exchange ack", from_peer=message.sender_id[:8])
        
        try:
            sender_key_bytes = bytes.fromhex(message.public_key)
            sender_verify_key = VerifyKey(sender_key_bytes)
            self._peer_keys[message.sender_id] = sender_verify_key
            self._log.info("Stored peer key from ack", peer=message.sender_id[:8])
        except Exception as e:
            self._log.error("Failed to store peer key from ack", error=str(e))
            return {"success": False, "error": str(e)}
        
        return {"success": True}
    
    async def _broadcast(self, message: NetworkMessage):
        if self._pub_socket:
            envelope = SignedEnvelope.wrap(message, self.peer_id, self.signing_key)
            await self._pub_socket.send(envelope.to_bytes())
    
    async def _broadcast_status(self, status: PeerStatus):
        msg = PeerStatusMessage(
            sender_id=self.peer_id,
            peer_id=self.peer_id,
            status=status,
            address=SocketConfig.get_pub_address(self.config.peer_index, self.config.host),
            capabilities=self._get_capabilities()
        )
        await self._broadcast(msg)
    
    def _get_capabilities(self) -> List[str]:
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
        req_socket = self._context.socket(zmq.REQ)
        req_socket.setsockopt(zmq.RCVTIMEO, timeout)
        req_socket.setsockopt(zmq.SNDTIMEO, timeout)
        req_socket.setsockopt(zmq.LINGER, 0)
        
        try:
            rep_addr = SocketConfig.get_rep_address(peer_index, host)
            req_socket.connect(rep_addr)
            
            envelope = SignedEnvelope.wrap(message, self.peer_id, self.signing_key)
            await req_socket.send(envelope.to_bytes())
            resp_bytes = await req_socket.recv()
            
            verify_key = self._peer_keys.get(peer_id)
            if verify_key:
                try:
                    response_msg, _ = unwrap_and_verify(
                        resp_bytes,
                        lambda pid: self._peer_keys.get(pid)
                    )
                    if isinstance(response_msg, ResponseMessage):
                        return response_msg
                    return ResponseMessage.from_dict(response_msg.to_dict())
                except (SignatureVerificationError, MessageTimestampError) as e:
                    self._log.warning("Response verification failed", target_peer=peer_id[:8], error=str(e))
                    return None
            else:
                return ResponseMessage.from_dict(json.loads(resp_bytes.decode("utf-8")))
        except zmq.Again:
            self._log.warning("Timeout sending", target_peer=peer_id[:8])
            return None
        except Exception as e:
            self._log.error("Error sending", target_peer=peer_id[:8], error=str(e))
            return None
        finally:
            req_socket.close()
    
    async def broadcast_deletion(self, node_hash: str, originator_id: str, signature: str):
        msg = DeletionTokenMessage(
            sender_id=self.peer_id,
            node_hash=node_hash,
            originator_id=originator_id,
            token_signature=signature,
            cascade=True
        )
        await self._broadcast(msg)
        self._log.info("Broadcast deletion", node_hash=node_hash[:8])
    
    async def send_share(self, peer_id: str, peer_index: int, share_data: Dict, 
                         content_hash: str, threshold: int, total_shares: int) -> bool:
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
        msg = CoCNodeMessage(
            sender_id=self.peer_id,
            node_data=node.to_dict(),
            parent_hash=node.parent_hash or "",
            content_hash=node.content_hash
        )
        
        response = await self.send_direct(peer_id, peer_index, msg)
        return response is not None and response.success
    
    def go_offline(self):
        self.state.is_online = False
        self._log.info("Now OFFLINE - messages will be queued")
    
    def go_online(self):
        self.state.is_online = True
        self._log.info("Now ONLINE - processing queued messages")
        while not self._offline_queue.empty():
            try:
                message = self._offline_queue.get_nowait()
                self.state.pending_messages.append(message)
            except Empty:
                break
    
    async def process_pending_messages(self):
        while self.state.pending_messages:
            message = self.state.pending_messages.pop(0)
            await self._handle_broadcast(message)
    
    def register_peer_key(self, peer_id: str, verify_key: VerifyKey):
        self._peer_keys[peer_id] = verify_key
    
    def get_share(self, content_hash: str) -> Optional[Dict]:
        return self._shares.get(content_hash)
    
    def get_content(self, content_hash: str) -> Optional[bytes]:
        return self._content.get(content_hash)


def run_peer_process(config_dict: Dict):
    """Entry point for running a peer as a standalone process."""
    config = PeerConfig(
        peer_id=config_dict["peer_id"],
        peer_index=config_dict["peer_index"],
        host=config_dict.get("host", "127.0.0.1")
    )
    
    peer = NetworkPeer(config)
    
    async def main():
        await peer.start()
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await peer.stop()
    
    def signal_handler(sig, frame):
        _zmq_logger.info(f"Peer {config.peer_id[:8]} shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    asyncio.run(main())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        _zmq_logger.error("Usage: python -m coc_framework.network.peer_process <peer_id> <peer_index>")
        sys.exit(1)
    
    config = {
        "peer_id": sys.argv[1],
        "peer_index": int(sys.argv[2]),
        "host": sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
    }
    
    run_peer_process(config)
