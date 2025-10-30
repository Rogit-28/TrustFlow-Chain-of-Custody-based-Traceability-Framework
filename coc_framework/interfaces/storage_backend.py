from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Set

from coc_framework.core.coc_node import CoCNode

class StorageBackend(ABC):
    # --- Node Management ---
    @abstractmethod
    def add_node(self, node: CoCNode):
        pass

    @abstractmethod
    def get_node(self, node_hash: str) -> Optional[CoCNode]:
        pass

    @abstractmethod
    def remove_node(self, node_hash: str):
        pass

    @abstractmethod
    def get_all_nodes(self) -> List[CoCNode]:
        pass

    # --- Content Management ---
    @abstractmethod
    def add_content(self, content_hash: str, content: str):
        pass

    @abstractmethod
    def get_content(self, content_hash: str) -> Optional[str]:
        pass

    @abstractmethod
    def remove_content(self, content_hash: str):
        pass

    @abstractmethod
    def is_content_referenced(self, content_hash: str) -> bool:
        pass


class InMemoryStorage(StorageBackend):
    def __init__(self):
        self._nodes: Dict[str, CoCNode] = {}
        self._content: Dict[str, str] = {}

    # --- Node Management ---
    def add_node(self, node: CoCNode):
        self._nodes[node.node_hash] = node

    def get_node(self, node_hash: str) -> Optional[CoCNode]:
        return self._nodes.get(node_hash)

    def remove_node(self, node_hash: str):
        if node_hash in self._nodes:
            del self._nodes[node_hash]

    def get_all_nodes(self) -> List[CoCNode]:
        return list(self._nodes.values())

    # --- Content Management ---
    def add_content(self, content_hash: str, content: str):
        self._content[content_hash] = content

    def get_content(self, content_hash: str) -> Optional[str]:
        return self._content.get(content_hash)

    def remove_content(self, content_hash: str):
        if content_hash in self._content:
            del self._content[content_hash]

    def is_content_referenced(self, content_hash: str) -> bool:
        """Checks if any node in storage references the given content hash."""
        for node in self._nodes.values():
            if node.content_hash == content_hash:
                return True
        return False
