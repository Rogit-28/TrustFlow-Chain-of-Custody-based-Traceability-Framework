from abc import ABC, abstractmethod
from typing import List

class NotificationHandler(ABC):
    @abstractmethod
    def on_message_received(self, peer_id: str, msg_hash: str, sender_id: str) -> None:
        pass

    @abstractmethod
    def on_message_forwarded(self, peer_id: str, msg_hash: str, recipients: List[str]) -> None:
        pass

    @abstractmethod
    def on_deletion_requested(self, peer_id: str, msg_hash: str, originator_id: str) -> None:
        pass

    @abstractmethod
    def on_peer_status_changed(self, peer_id: str, online_status: bool) -> None:
        pass

    @abstractmethod
    def on_queue_processed(self, peer_id: str, message_count: int) -> None:
        pass

class SilentNotificationHandler(NotificationHandler):
    def on_message_received(self, peer_id: str, msg_hash: str, sender_id: str) -> None:
        print(f"[Notification] Peer {peer_id} received message {msg_hash} from {sender_id}")

    def on_message_forwarded(self, peer_id: str, msg_hash: str, recipients: List[str]) -> None:
        print(f"[Notification] Peer {peer_id} forwarded message {msg_hash} to {recipients}")

    def on_deletion_requested(self, peer_id: str, msg_hash: str, originator_id: str) -> None:
        print(f"[Notification] Peer {peer_id} received deletion request for {msg_hash} from {originator_id}")

    def on_peer_status_changed(self, peer_id: str, online_status: bool) -> None:
        print(f"[Notification] Peer {peer_id} status changed to {'online' if online_status else 'offline'}")

    def on_queue_processed(self, peer_id: str, message_count: int) -> None:
        print(f"[Notification] Peer {peer_id} processed {message_count} queued messages")
