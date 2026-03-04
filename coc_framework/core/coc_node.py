from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Set, Dict
from .crypto_core import CryptoCore


# Schema version for node serialization format
NODE_SCHEMA_VERSION = 2


class SignatureVerificationError(Exception):
    pass


class CoCNode:
    """Chain of Custody Node with Ed25519 signatures and schema versioning."""
    
    _SIG_DELIMITER = "|"
    
    def __init__(
        self, 
        content_hash: str, 
        owner_id: str, 
        signing_key, 
        recipient_ids: List[str], 
        parent_hash: Optional[str] = None, 
        depth: int = 0,
        schema_version: int = NODE_SCHEMA_VERSION
    ):
        self.schema_version = schema_version
        self.content_hash = content_hash
        self.parent_hash = parent_hash
        self.owner_id = owner_id
        self.recipient_ids = sorted(recipient_ids)
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.children_hashes: Set[str] = set()
        self.depth = depth

        if signing_key:
            signature_data = self._get_signing_data()
            self.signature = CryptoCore.sign_message(signing_key, signature_data)
            self.node_hash = CryptoCore.hash_content(f"{self.signature.hex()}{self._SIG_DELIMITER}{self.content_hash}")
        else:
            self.signature = None
            self.node_hash = None

    def _get_signing_data(self) -> str:
        """Generate canonical string for signature. Format: version|content_hash|parent_hash|owner_id|recipients|timestamp"""
        recipients_str = ",".join(self.recipient_ids)
        return self._SIG_DELIMITER.join([
            str(self.schema_version),
            self.content_hash,
            self.parent_hash or "",
            self.owner_id,
            recipients_str,
            self.timestamp
        ])

    def add_child(self, child_node: CoCNode):
        if not isinstance(child_node, CoCNode):
            raise TypeError("Child must be a CoCNode instance.")
        self.children_hashes.add(child_node.node_hash)
        child_node.depth = self.depth + 1

    def to_dict(self) -> Dict:
        return {
            "schema_version": self.schema_version,
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
        schema_version = data.get("schema_version", 1)
        
        node = CoCNode(
            content_hash=data["content_hash"],
            owner_id=data["owner_id"],
            signing_key=None,
            recipient_ids=data.get("recipient_ids", []),
            parent_hash=data.get("parent_hash"),
            depth=data.get("depth", 0),
            schema_version=schema_version
        )
        node.node_hash = data["node_hash"]
        node.signature = bytes.fromhex(data["signature"]) if data.get("signature") else None
        node.timestamp = data["timestamp"]
        node.children_hashes = set(data.get("children_hashes", []))
        return node

    def verify_signature(self, verify_key) -> bool:
        if not self.signature:
            return False
        
        # Handle different schema versions
        if self.schema_version >= 2:
            signature_data = self._get_signing_data()
        else:
            # Legacy v1 format (no delimiters, no version)
            receivers_str = ",".join(self.recipient_ids)
            signature_data = f"{self.content_hash}{self.parent_hash or ''}{self.owner_id}{receivers_str}{self.timestamp}"
        
        return CryptoCore.verify_signature(verify_key, signature_data, self.signature)

    def get_all_descendants(self, storage) -> List[CoCNode]:
        descendants = []
        for child_hash in self.children_hashes:
            child_node = storage.get_node(child_hash)
            if child_node:
                descendants.append(child_node)
                descendants.extend(child_node.get_all_descendants(storage))
        return descendants

    def __repr__(self):
        hash_str = self.node_hash[:8] if self.node_hash else "None"
        parent_str = self.parent_hash[:8] if self.parent_hash else "ROOT"
        owner_str = self.owner_id[:8] if self.owner_id else "None"
        return f"CoCNode(hash={hash_str}, parent={parent_str}, owner={owner_str})"
