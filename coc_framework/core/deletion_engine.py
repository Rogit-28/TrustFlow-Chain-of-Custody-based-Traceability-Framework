from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import TYPE_CHECKING, Dict
from .crypto_core import CryptoCore

if TYPE_CHECKING:
    from .network_sim import Peer
    from .coc_node import CoCNode

@dataclass
class DeletionToken:
    node_hash: str  # Hash of the CoCNode to be deleted
    originator_id: str
    timestamp: str = datetime.utcnow().isoformat()
    signature: str = ""

    def sign(self, signing_key):
        """Signs the token."""
        token_data = f"{self.node_hash}{self.originator_id}{self.timestamp}"
        self.signature = CryptoCore.sign_message(signing_key, token_data).hex()

    def to_dict(self) -> Dict:
        """Serializes the token to a dictionary."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> DeletionToken:
        """Deserializes a dictionary to a DeletionToken instance."""
        return DeletionToken(**data)

class DeletionEngine:
    def __init__(self, network, audit_log, notification_handler, peer_discovery):
        self.network = network
        self.audit_log = audit_log
        self.notification_handler = notification_handler
        self.peer_discovery = peer_discovery
        print("[DELETE] Deletion Engine Initialized.")

    def issue_token(self, node: CoCNode, originator: Peer) -> DeletionToken:
        """Originator creates and signs a deletion token for a specific node."""
        if node.owner_id != originator.peer_id:
            raise PermissionError("Only the owner of a node can issue a deletion token.")

        token = DeletionToken(node_hash=node.node_hash, originator_id=originator.peer_id)
        token.sign(originator.signing_key)

        print(f"[PEER {originator.peer_id[:8]}] Issued deletion token for node {node.node_hash[:8]}")
        self.audit_log.log_event("DELETE_ISSUE", originator.peer_id, f"Node: {node.node_hash}")
        return token

    def process_token(self, token: DeletionToken, receiving_peer: Peer):
        """A peer processes a deletion token."""
        originator = self.peer_discovery.find_peer(token.originator_id)
        if not originator:
            print(f"[DELETE] Originator {token.originator_id} not found. Cannot verify token.")
            return

        # Verify the token's signature
        token_data = f"{token.node_hash}{token.originator_id}{token.timestamp}"
        if not CryptoCore.verify_signature(originator.verify_key, token_data, bytes.fromhex(token.signature)):
            print(f"[DELETE] Invalid signature for deletion token. Discarding.")
            self.audit_log.log_event("DELETE_FAIL", receiving_peer.peer_id, f"Node: {token.node_hash}", "Invalid signature")
            return

        node_to_delete = receiving_peer.storage.get_node(token.node_hash)
        if not node_to_delete:
            return # Peer doesn't have this node, so nothing to do

        print(f"[PEER {receiving_peer.peer_id[:8]}] Processing deletion token for node {token.node_hash[:8]}")

        # Find all children of the deleted node that this peer owns
        children_to_delete = [
            child_node for child_hash in node_to_delete.children_hashes
            if (child_node := receiving_peer.storage.get_node(child_hash)) and child_node.owner_id == receiving_peer.peer_id
        ]

        # Delete the node and its content
        receiving_peer.storage.remove_node(node_to_delete.node_hash)
        if not receiving_peer.storage.is_content_referenced(node_to_delete.content_hash):
            receiving_peer.storage.remove_content(node_to_delete.content_hash)

        self.audit_log.log_event("DELETE_SUCCESS", receiving_peer.peer_id, f"Node: {node_to_delete.node_hash}")
        print(f"[PEER {receiving_peer.peer_id[:8]}] Deleted node {node_to_delete.node_hash[:8]}.")
        self.notification_handler.on_deletion_requested(receiving_peer.peer_id, token.node_hash, token.originator_id)

        # Propagate deletion to children
        for child in children_to_delete:
            receiving_peer.initiate_deletion(child)
