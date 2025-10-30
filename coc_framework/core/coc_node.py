from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Set, Dict
from .crypto_core import CryptoCore

class CoCNode:
    def __init__(self, content_hash: str, owner_id: str, signing_key, recipient_ids: List[str], parent_hash: Optional[str] = None, depth: int = 0):
        self.content_hash = content_hash
        self.parent_hash = parent_hash
        self.owner_id = owner_id
        self.recipient_ids = sorted(recipient_ids)
        self.timestamp = datetime.utcnow().isoformat()
        self.children_hashes: Set[str] = set()
        self.depth = depth

        receivers_str = ",".join(self.recipient_ids)
        signature_data = f"{self.content_hash}{self.parent_hash or ''}{self.owner_id}{receivers_str}{self.timestamp}"

        if signing_key:
            self.signature = CryptoCore.sign_message(signing_key, signature_data)
            self.node_hash = CryptoCore.hash_content(f"{self.signature.hex()}{self.content_hash}")
        else:
            self.signature = None
            self.node_hash = None

    def add_child(self, child_node: CoCNode):
        """Adds a hash of a child node."""
        if not isinstance(child_node, CoCNode):
            raise TypeError("Child must be a CoCNode instance.")
        self.children_hashes.add(child_node.node_hash)
        child_node.depth = self.depth + 1

    def to_dict(self) -> Dict:
        """Serializes the node to a dictionary."""
        return {
            "node_hash": self.node_hash,
            "content_hash": self.content_hash,
            "parent_hash": self.parent_hash,
            "owner_id": self.owner_id,
            "recipient_ids": self.recipient_ids,
            "timestamp": self.timestamp,
            "children_hashes": list(self.children_hashes),
            "depth": self.depth,
            "signature": self.signature.hex() if self.signature else None,
        }

    @staticmethod
    def from_dict(data: Dict) -> CoCNode:
        """Deserializes a dictionary back into a CoCNode instance."""
        node = CoCNode(
            content_hash=data["content_hash"],
            owner_id=data["owner_id"],
            signing_key=None,
            recipient_ids=data.get("recipient_ids", []),
            parent_hash=data.get("parent_hash"),
            depth=data.get("depth", 0)
        )
        # Manually set the original hash and signature, as they can't be regenerated
        node.node_hash = data["node_hash"]
        node.signature = bytes.fromhex(data["signature"]) if data["signature"] else None
        node.timestamp = data["timestamp"]
        node.children_hashes = set(data.get("children_hashes", []))
        return node

    def verify_signature(self, verify_key) -> bool:
        """Verifies the node's signature."""
        if not self.signature:
            return False
        receivers_str = ",".join(self.recipient_ids)
        signature_data = f"{self.content_hash}{self.parent_hash or ''}{self.owner_id}{receivers_str}{self.timestamp}"
        return CryptoCore.verify_signature(verify_key, signature_data, self.signature)

    def get_all_descendants(self, storage) -> List[CoCNode]:
        """Recursively gets all descendants of this node."""
        descendants = []
        for child_hash in self.children_hashes:
            child_node = storage.get_node(child_hash)
            if child_node:
                descendants.append(child_node)
                descendants.extend(child_node.get_all_descendants(storage))
        return descendants

    def __repr__(self):
        return (f"CoCNode(hash={self.node_hash[:8]}, parent={self.parent_hash[:8] if self.parent_hash else 'ROOT'}, "
                f"owner={self.owner_id[:8]})")
