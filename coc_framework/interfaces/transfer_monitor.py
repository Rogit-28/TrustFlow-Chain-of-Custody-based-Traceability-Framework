from abc import ABC, abstractmethod
from enum import Enum, auto

class TransferAccessType(Enum):
    READ = auto()
    COPY = auto()
    SAVE = auto()
    FORWARD = auto()

class EncryptionPolicyEnum(Enum):
    ALLOW = auto()
    KNOWN_KEY = auto()
    UNKNOWN_KEY = auto()

class TransferMonitor(ABC):
    @abstractmethod
    def on_message_accessed(self, msg_hash: str, peer_id: str, access_type: TransferAccessType) -> None:
        pass

    @abstractmethod
    def on_transfer_attempt(self, msg_hash: str, peer_id: str, destination: str) -> None:
        pass

    @abstractmethod
    def should_allow_transfer(self, msg_hash: str, peer_id: str) -> bool:
        pass

    @abstractmethod
    def get_encryption_policy(self, msg_hash: str, peer_id: str) -> EncryptionPolicyEnum:
        pass

class NullTransferMonitor(TransferMonitor):
    def on_message_accessed(self, msg_hash: str, peer_id: str, access_type: TransferAccessType) -> None:
        pass

    def on_transfer_attempt(self, msg_hash: str, peer_id: str, destination: str) -> None:
        pass

    def should_allow_transfer(self, msg_hash: str, peer_id: str) -> bool:
        return True

    def get_encryption_policy(self, msg_hash: str, peer_id: str) -> EncryptionPolicyEnum:
        return EncryptionPolicyEnum.ALLOW
