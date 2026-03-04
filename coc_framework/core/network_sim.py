import asyncio
import hashlib
import random
from typing import Optional, TYPE_CHECKING
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from .crypto_core import CryptoCore
from .coc_node import CoCNode
from .deletion_engine import DeletionEngine, DeletionToken
from .logging import peer_logger, network_logger
from coc_framework.interfaces.storage_backend import StorageBackend, InMemoryStorage
from coc_framework.interfaces.transfer_monitor import TransferMonitor, NullTransferMonitor
from coc_framework.interfaces.notification_handler import NotificationHandler, SilentNotificationHandler
from coc_framework.network.gossip import MessageCache

if TYPE_CHECKING:
    from .secret_sharing import SecretSharingEngine
    from .timelock import TimeLockEngine
    from .steganography import SteganoEngine


def _compute_message_id(message: dict) -> str:
    """Compute unique ID for deduplication using sender, type, and content hash."""
    content_str = str(message.get("content", ""))
    data = f"{message.get('sender_id', '')}:{message.get('message_type', '')}:{content_str}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


class Peer:
    def __init__(
        self,
        deletion_engine,
        peer_id: str = None,
        message_ttl_hours: int = 24,
        storage_backend: StorageBackend = None,
        transfer_monitor: TransferMonitor = None,
        notification_handler: NotificationHandler = None,
        secret_sharing_engine: Optional["SecretSharingEngine"] = None,
        timelock_engine: Optional["TimeLockEngine"] = None,
        stegano_engine: Optional["SteganoEngine"] = None,
    ):
        self.peer_id = peer_id or str(uuid4())
        self.signing_key, self.verify_key = CryptoCore.generate_keypair()
        self.online = True
        self.storage = storage_backend or InMemoryStorage()
        self.transfer_monitor = transfer_monitor or NullTransferMonitor()
        self.notification_handler = notification_handler or SilentNotificationHandler()
        self.deletion_engine = deletion_engine
        self.offline_queue = []
        self.last_online_timestamp = datetime.now(timezone.utc)
        self.message_ttl_hours = message_ttl_hours

        self.secret_sharing_engine = secret_sharing_engine
        self.timelock_engine = timelock_engine
        self.stegano_engine = stegano_engine
        self.network = None
        self._received_messages = MessageCache(max_size=1000, ttl_seconds=300)

        self._log = peer_logger(self.peer_id)
        self._log.info("Peer created", peer_id=self.peer_id[:8])

    def create_coc_root(self, content, recipient_ids):
        content_hash = CryptoCore.hash_content(content)
        node = CoCNode(content_hash, self.peer_id, self.signing_key, recipient_ids)
        self.storage.add_node(node)
        self.storage.add_content(content_hash, content)
        return node

    def forward_coc_message(self, parent_node, recipient_ids):
        forward_content_hash = parent_node.content_hash
        child_node = CoCNode(forward_content_hash, self.peer_id, self.signing_key, recipient_ids, parent_hash=parent_node.node_hash)
        parent_node.add_child(child_node)
        self.storage.add_node(child_node)
        self.storage.add_node(parent_node)
        return child_node

    def initiate_deletion(self, node):
        token = self.deletion_engine.issue_token(node, self)
        for recipient_id in node.recipient_ids:
            self.send_message(recipient_id, "deletion_token", token.to_dict())

    def go_offline(self):
        self.online = False
        self.last_online_timestamp = datetime.now(timezone.utc)
        self.notification_handler.on_peer_status_changed(self.peer_id, self.online)
        self._log.info("Went offline")

    def go_online(self):
        self.online = True
        self.notification_handler.on_peer_status_changed(self.peer_id, self.online)
        self._log.info("Came online, processing offline queue")

        processed_count = 0

        for queued_message in list(self.offline_queue):
            timestamp, message = queued_message
            if datetime.now(timezone.utc) - timestamp <= timedelta(hours=self.message_ttl_hours):
                self.receive_message(message)
                processed_count += 1

        self.offline_queue.clear()
        self.notification_handler.on_queue_processed(self.peer_id, processed_count)

    def send_message(self, recipient_id, message_type, content):
        if not self.network:
            self._log.warning("Cannot send message: not connected to network")
            return

        message = {
            "sender_id": self.peer_id,
            "recipient_id": recipient_id,
            "message_type": message_type,
            "content": content
        }
        self.network.route_message(message)

    def receive_message(self, message):
        """Handles incoming messages with deduplication."""
        msg_id = _compute_message_id(message)
        if self._received_messages.has_seen(msg_id):
            self._log.debug("Duplicate message ignored", msg_id=msg_id[:8])
            return
        self._received_messages.mark_seen(msg_id)
        msg_type = message["message_type"]
        content = message["content"]

        if msg_type == "coc_data":
            node = CoCNode.from_dict(content["node_data"])
            self.storage.add_node(node)
            self.storage.add_content(node.content_hash, content["content"])
            if node.parent_hash:
                parent_node = self.storage.get_node(node.parent_hash)
                if parent_node:
                    parent_node.add_child(node)
                    self.storage.add_node(parent_node)

            self._log.info("Received and stored CoC node", node_hash=node.node_hash[:8])

        elif msg_type == "deletion_token":
            token = DeletionToken.from_dict(content)
            self.deletion_engine.process_token(token, self)


class Network:
    def __init__(self, peer_discovery=None):
        from coc_framework.interfaces.peer_discovery import RegistryPeerDiscovery
        self.peer_discovery = peer_discovery or RegistryPeerDiscovery()
        self._log = network_logger()
        self._log.info("Network Simulator initialized")

    def add_peer(self, peer: Peer):
        self.peer_discovery.register_peer(peer)
        peer.network = self
        self._log.info("Peer joined network", peer_id=peer.peer_id[:8])

    def route_message(self, message):
        recipient = self.peer_discovery.find_peer(message["recipient_id"])
        if not recipient:
            self._log.warning("Peer not found, message dropped", peer_id=message['recipient_id'][:8])
            return

        if recipient.online:
            asyncio.create_task(self.deliver_message(recipient, message))
        else:
            recipient.offline_queue.append((datetime.now(timezone.utc), message))
            self._log.info("Peer offline, message queued", peer_id=message['recipient_id'][:8])

    async def deliver_message(self, recipient, message):
        await asyncio.sleep(random.uniform(0.01, 0.05))
        recipient.receive_message(message)

    def tick(self):
        pass
