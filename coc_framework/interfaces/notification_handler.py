from abc import ABC, abstractmethod
from typing import List
from coc_framework.core.logging import get_logger, Component


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
        pass

    def on_message_forwarded(self, peer_id: str, msg_hash: str, recipients: List[str]) -> None:
        pass

    def on_deletion_requested(self, peer_id: str, msg_hash: str, originator_id: str) -> None:
        pass

    def on_peer_status_changed(self, peer_id: str, online_status: bool) -> None:
        pass

    def on_queue_processed(self, peer_id: str, message_count: int) -> None:
        pass


class LoggingNotificationHandler(NotificationHandler):
    def __init__(self):
        self._log = get_logger(Component.NOTIFICATION)

    def on_message_received(self, peer_id: str, msg_hash: str, sender_id: str) -> None:
        self._log.info("Message received", peer_id=peer_id, msg_hash=msg_hash, sender_id=sender_id)

    def on_message_forwarded(self, peer_id: str, msg_hash: str, recipients: List[str]) -> None:
        self._log.info("Message forwarded", peer_id=peer_id, msg_hash=msg_hash, recipients=recipients)

    def on_deletion_requested(self, peer_id: str, msg_hash: str, originator_id: str) -> None:
        self._log.info("Deletion requested", peer_id=peer_id, msg_hash=msg_hash, originator_id=originator_id)

    def on_peer_status_changed(self, peer_id: str, online_status: bool) -> None:
        status_str = "online" if online_status else "offline"
        self._log.info("Peer status changed", peer_id=peer_id, status=status_str)

    def on_queue_processed(self, peer_id: str, message_count: int) -> None:
        self._log.info("Queue processed", peer_id=peer_id, message_count=message_count)
