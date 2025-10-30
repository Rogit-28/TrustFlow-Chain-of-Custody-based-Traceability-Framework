from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Optional

class EncryptionMode(Enum):
    NONE = auto()
    RECOVERABLE = auto()
    IRRECOVERABLE = auto()

class EncryptionPolicy(ABC):
    @abstractmethod
    def get_policy_for_peer(self, peer_id: str) -> EncryptionMode:
        pass

    @abstractmethod
    def encrypt_for_transfer(self, content: str, peer_id: str, mode: EncryptionMode) -> bytes:
        pass

    @abstractmethod
    def can_decrypt(self, encrypted_content: bytes, peer_id: str) -> bool:
        pass

    @abstractmethod
    def decrypt_if_allowed(self, encrypted_content: bytes, peer_id: str) -> Optional[str]:
        pass

class NoEncryption(EncryptionPolicy):
    def get_policy_for_peer(self, peer_id: str) -> EncryptionMode:
        return EncryptionMode.NONE

    def encrypt_for_transfer(self, content: str, peer_id: str, mode: EncryptionMode) -> bytes:
        return content.encode('utf-8')

    def can_decrypt(self, encrypted_content: bytes, peer_id: str) -> bool:
        return True

    def decrypt_if_allowed(self, encrypted_content: bytes, peer_id: str) -> Optional[str]:
        return encrypted_content.decode('utf-8')
