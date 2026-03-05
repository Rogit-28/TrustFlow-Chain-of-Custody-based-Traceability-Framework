import asyncio
import logging
import random
from uuid import uuid4
from typing import Optional, Dict, List, TYPE_CHECKING
from .crypto_core import CryptoCore
from coc_framework.interfaces.storage_backend import StorageBackend, InMemoryStorage
from coc_framework.interfaces.transfer_monitor import (
    TransferMonitor,
    NullTransferMonitor,
)
from coc_framework.interfaces.notification_handler import (
    NotificationHandler,
    SilentNotificationHandler,
)
from .coc_node import CoCNode
from .deletion_engine import DeletionEngine, DeletionToken

from datetime import datetime, timedelta, timezone

if TYPE_CHECKING:
    from coc_framework.core.secret_sharing import SecretSharingEngine, Share
    from coc_framework.core.timelock import TimeLockEngine, EncryptedContent
    from coc_framework.core.steganography import SteganoEngine

logger = logging.getLogger(__name__)


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

        # MVP feature engines (optional, shared across peers)
        self.secret_sharing_engine = secret_sharing_engine
        self.timelock_engine = timelock_engine
        self.stegano_engine = stegano_engine

        # Storage for received secret shares
        self._received_shares: Dict[str, "Share"] = {}  # content_hash -> Share

        self.network = None  # Set by the Network class upon registration

        print(f"[PEER] Created Anonymous Peer (ID: {self.peer_id[:8]})")

    def create_coc_root(self, content, recipient_ids):
        """Creates a new CoC root node and stores it."""
        content_hash = CryptoCore.hash_content(content)
        node = CoCNode(content_hash, self.peer_id, self.signing_key, recipient_ids)
        self.storage.add_node(node)
        self.storage.add_content(content_hash, content)
        return node

    def forward_coc_message(self, parent_node, recipient_ids):
        """Creates a new CoC child node for forwarding."""
        forward_content_hash = parent_node.content_hash
        child_node = CoCNode(
            forward_content_hash,
            self.peer_id,
            self.signing_key,
            recipient_ids,
            parent_hash=parent_node.node_hash,
        )
        parent_node.add_child(child_node)
        self.storage.add_node(child_node)
        self.storage.add_node(parent_node)  # Update the parent node in storage
        # Content is already stored, no need to add it again
        return child_node

    def initiate_deletion(self, node):
        """Starts the deletion process for a given node."""
        token = self.deletion_engine.issue_token(node, self)

        # Propagate to direct recipients of this node
        for recipient_id in node.recipient_ids:
            self.send_message(recipient_id, "deletion_token", token.to_dict())

    def go_offline(self):
        """Marks the peer as offline."""
        self.online = False
        self.last_online_timestamp = datetime.now(timezone.utc)
        self.notification_handler.on_peer_status_changed(self.peer_id, self.online)
        print(f"[PEER {self.peer_id[:8]}] Went offline.")

    def go_online(self):
        """Marks the peer as online and processes any queued messages."""
        self.online = True
        self.notification_handler.on_peer_status_changed(self.peer_id, self.online)
        print(f"[PEER {self.peer_id[:8]}] Came online. Processing offline queue...")

        processed_count = 0

        for queued_message in list(self.offline_queue):
            timestamp, message = queued_message
            if datetime.now(timezone.utc) - timestamp <= timedelta(
                hours=self.message_ttl_hours
            ):
                self.receive_message(message)
                processed_count += 1

        self.offline_queue.clear()
        self.notification_handler.on_queue_processed(self.peer_id, processed_count)

    def send_message(self, recipient_id, message_type, content):
        """Sends a message to another peer via the network."""
        if not self.network:
            print(
                f"[PEER {self.peer_id[:8]}] Cannot send message: not connected to a network."
            )
            return

        message = {
            "sender_id": self.peer_id,
            "recipient_id": recipient_id,
            "message_type": message_type,
            "content": content,
        }
        self.network.route_message(message)

    def receive_message(self, message):
        """Handles an incoming message from the network."""
        msg_type = message["message_type"]
        content = message["content"]

        if msg_type == "coc_data":
            node = CoCNode.from_dict(content["node_data"])
            self.storage.add_node(node)
            self.storage.add_content(node.content_hash, content["content"])

            # If the node has a parent, update the parent node in storage
            if node.parent_hash:
                parent_node = self.storage.get_node(node.parent_hash)
                if parent_node:
                    parent_node.add_child(node)
                    self.storage.add_node(parent_node)

            print(
                f"[PEER {self.peer_id[:8]}] Received and stored CoC node {node.node_hash[:8]}"
            )

        elif msg_type == "deletion_token":
            token = DeletionToken.from_dict(content)
            self.deletion_engine.process_token(token, self)

    # ============ MVP Feature Methods ============

    def distribute_shares(
        self,
        content: str,
        recipient_ids: List[str],
        threshold: Optional[int] = None,
    ) -> Dict[str, "Share"]:
        """Split content into secret shares and distribute to recipients."""
        if not self.secret_sharing_engine:
            raise RuntimeError("Secret sharing engine not available on this peer")

        share_map = self.secret_sharing_engine.split_content(
            content=content,
            recipient_ids=recipient_ids,
            threshold=threshold,
        )

        # Send each share to the corresponding recipient via the network
        for peer_id, share in share_map.items():
            self.send_message(peer_id, "secret_share", share.to_dict())

        logger.debug(
            f"[PEER {self.peer_id[:8]}] Distributed {len(share_map)} shares "
            f"(threshold={share_map[recipient_ids[0]].threshold})"
        )
        return share_map

    def collect_and_reconstruct(
        self,
        content_hash: str,
        collected_shares: Optional[Dict[str, "Share"]] = None,
    ) -> Optional[str]:
        """Reconstruct a secret from collected shares."""
        if not self.secret_sharing_engine:
            raise RuntimeError("Secret sharing engine not available on this peer")

        shares_list = list((collected_shares or {}).values())

        # Also include our own share if we have one
        if content_hash in self._received_shares:
            own_share = self._received_shares[content_hash]
            if own_share not in shares_list:
                shares_list.append(own_share)

        if not shares_list:
            logger.warning(
                f"[PEER {self.peer_id[:8]}] No shares available for reconstruction"
            )
            return None

        return self.secret_sharing_engine.reconstruct_content(shares_list)

    def create_timelocked_content(
        self,
        content: str,
        ttl_seconds: int,
        recipient_ids: Optional[List[str]] = None,
    ) -> "EncryptedContent":
        """Create time-lock encrypted content."""
        if not self.timelock_engine:
            raise RuntimeError("Timelock engine not available on this peer")

        encrypted = self.timelock_engine.encrypt(content, ttl_seconds)

        # Optionally send to recipients
        if recipient_ids:
            for peer_id in recipient_ids:
                self.send_message(peer_id, "timelocked_content", encrypted.to_dict())

        logger.debug(
            f"[PEER {self.peer_id[:8]}] Created time-locked content (TTL={ttl_seconds}s)"
        )
        return encrypted

    def destroy_timelock(self, lock_id: str) -> bool:
        """Destroy a time-lock, making the content permanently inaccessible."""
        if not self.timelock_engine:
            raise RuntimeError("Timelock engine not available on this peer")
        return self.timelock_engine.destroy(lock_id)

    def forward_with_watermark(
        self,
        parent_node: "CoCNode",
        recipient_ids: List[str],
        content: str,
    ) -> "CoCNode":
        """Forward a CoC message with steganographic watermarking per recipient."""
        if not self.stegano_engine:
            raise RuntimeError("Steganography engine not available on this peer")

        child_node = self.forward_coc_message(parent_node, recipient_ids)

        for recipient_id in recipient_ids:
            watermarked_content = self.stegano_engine.embed_watermark(
                content=content,
                peer_id=recipient_id,
            )
            self.send_message(
                recipient_id=recipient_id,
                message_type="coc_data",
                content={
                    "node_data": child_node.to_dict(),
                    "content": watermarked_content,
                },
            )

        logger.debug(
            f"[PEER {self.peer_id[:8]}] Forwarded with watermark to "
            f"{len(recipient_ids)} recipients"
        )
        return child_node


class Network:
    def __init__(self, peer_discovery=None):
        from coc_framework.interfaces.peer_discovery import RegistryPeerDiscovery

        self.peer_discovery = peer_discovery or RegistryPeerDiscovery()
        print("[NETWORK] Network Simulator Initialized.")

    def add_peer(self, peer: Peer):
        self.peer_discovery.register_peer(peer)
        peer.network = self
        print(f"[NETWORK] Peer {peer.peer_id[:8]} joined the network.")

    def route_message(self, message):
        recipient = self.peer_discovery.find_peer(message["recipient_id"])
        if not recipient:
            print(
                f"[NETWORK] Peer {message['recipient_id'][:8]} does not exist. Message dropped."
            )
            return

        if recipient.online:
            asyncio.create_task(self.deliver_message(recipient, message))
        else:
            recipient.offline_queue.append((datetime.now(timezone.utc), message))
            print(
                f"[NETWORK] Peer {message['recipient_id'][:8]} is offline. Message queued."
            )

    async def deliver_message(self, recipient, message):
        """Simulates a network delay before delivering a message."""
        await asyncio.sleep(random.uniform(0.01, 0.05))
        recipient.receive_message(message)

    def tick(self):
        """Processes network events."""
        # This is now primarily for orchestrating async tasks if needed
        pass
