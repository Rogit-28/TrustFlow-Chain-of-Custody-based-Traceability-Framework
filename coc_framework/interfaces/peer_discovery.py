from abc import ABC, abstractmethod
from typing import List, Optional

# Forward declaration to avoid circular import
class Peer:
    pass

class PeerDiscovery(ABC):
    @abstractmethod
    def find_peer(self, peer_id: str) -> Optional[Peer]:
        pass

    @abstractmethod
    def register_peer(self, peer: Peer) -> bool:
        pass

    @abstractmethod
    def unregister_peer(self, peer_id: str) -> bool:
        pass

    @abstractmethod
    def list_online_peers(self) -> List[str]:
        pass

    @abstractmethod
    def get_peer_status(self, peer_id: str) -> bool:
        pass

class RegistryPeerDiscovery(PeerDiscovery):
    def __init__(self):
        self._peers = {}

    def find_peer(self, peer_id: str) -> Optional[Peer]:
        return self._peers.get(peer_id)

    def register_peer(self, peer: Peer) -> bool:
        self._peers[peer.peer_id] = peer
        return True

    def unregister_peer(self, peer_id: str) -> bool:
        if peer_id in self._peers:
            del self._peers[peer_id]
            return True
        return False

    def list_online_peers(self) -> List[str]:
        return [peer.peer_id for peer in self._peers.values() if peer.online]

    def get_peer_status(self, peer_id: str) -> bool:
        peer = self.find_peer(peer_id)
        return peer.online if peer else False
