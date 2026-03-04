"""Time-lock encryption with AES-256-GCM and automatic key expiration."""

import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Callable, Dict, Optional, Tuple

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class CryptoUnavailableError(RuntimeError):
    pass


def _require_crypto() -> None:
    if not CRYPTO_AVAILABLE:
        raise CryptoUnavailableError(
            "cryptography library required. Install with: pip install cryptography"
        )


class TimeLockStatus(Enum):
    ACTIVE = auto()
    EXPIRED = auto()
    DESTROYED = auto()


@dataclass
class TimeLockMetadata:
    lock_id: str
    content_hash: str
    created_at: str
    expires_at: str
    ttl_seconds: int
    status: str = "ACTIVE"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict) -> "TimeLockMetadata":
        return TimeLockMetadata(**data)
    
    def is_expired(self) -> bool:
        expires = datetime.fromisoformat(self.expires_at)
        return datetime.now(timezone.utc) > expires


@dataclass 
class EncryptedContent:
    ciphertext: bytes
    nonce: bytes
    metadata: TimeLockMetadata
    
    def to_dict(self) -> Dict:
        return {
            "ciphertext": self.ciphertext.hex(),
            "nonce": self.nonce.hex(),
            "metadata": self.metadata.to_dict()
        }
    
    @staticmethod
    def from_dict(data: Dict) -> "EncryptedContent":
        return EncryptedContent(
            ciphertext=bytes.fromhex(data["ciphertext"]),
            nonce=bytes.fromhex(data["nonce"]),
            metadata=TimeLockMetadata.from_dict(data["metadata"])
        )


class KeyStore:
    """Secure key storage with automatic expiration."""
    
    def __init__(self):
        self._keys: Dict[str, Tuple[bytes, datetime]] = {}
        self._lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False
    
    def start_cleanup_daemon(self, interval: float = 1.0):
        self._running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            args=(interval,),
            daemon=True
        )
        self._cleanup_thread.start()
    
    def stop_cleanup_daemon(self):
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=2.0)
    
    def _cleanup_loop(self, interval: float):
        while self._running:
            self._cleanup_expired()
            time.sleep(interval)
    
    def _cleanup_expired(self):
        now = datetime.now(timezone.utc)
        with self._lock:
            expired = [
                lock_id for lock_id, (_, expiry) in self._keys.items()
                if now > expiry
            ]
            for lock_id in expired:
                self._secure_wipe(lock_id)
                del self._keys[lock_id]
    
    def _secure_wipe(self, lock_id: str):
        """Best-effort secure key deletion (overwrite before delete)."""
        if lock_id in self._keys:
            key, expiry = self._keys[lock_id]
            self._keys[lock_id] = (os.urandom(32), expiry)
    
    def store_key(self, lock_id: str, key: bytes, expiry: datetime):
        with self._lock:
            self._keys[lock_id] = (key, expiry)
    
    def get_key(self, lock_id: str) -> Optional[bytes]:
        with self._lock:
            if lock_id not in self._keys:
                return None
            key, expiry = self._keys[lock_id]
            if datetime.now(timezone.utc) > expiry:
                self._secure_wipe(lock_id)
                del self._keys[lock_id]
                return None
            return key
    
    def destroy_key(self, lock_id: str) -> bool:
        with self._lock:
            if lock_id in self._keys:
                self._secure_wipe(lock_id)
                del self._keys[lock_id]
                return True
            return False
    
    def has_key(self, lock_id: str) -> bool:
        return self.get_key(lock_id) is not None
    
    def get_expiry(self, lock_id: str) -> Optional[datetime]:
        with self._lock:
            if lock_id in self._keys:
                _, expiry = self._keys[lock_id]
                return expiry
            return None


class TimeLockEngine:
    """High-level interface for time-locked encryption with automatic key destruction."""
    
    def __init__(self, cleanup_interval: float = 1.0):
        self.key_store = KeyStore()
        self._metadata_store: Dict[str, TimeLockMetadata] = {}
        self._callbacks: Dict[str, Callable[[str], None]] = {}
        self.key_store.start_cleanup_daemon(cleanup_interval)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False
    
    def shutdown(self):
        self.key_store.stop_cleanup_daemon()
    
    def encrypt(
        self,
        content: str,
        ttl_seconds: int,
        on_expire: Optional[Callable[[str], None]] = None
    ) -> EncryptedContent:
        lock_id = secrets.token_hex(16)
        key = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        
        plaintext = content.encode('utf-8')
        content_hash = hashlib.sha256(plaintext).hexdigest()
        
        _require_crypto()
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        self.key_store.store_key(lock_id, key, expires_at)
        
        metadata = TimeLockMetadata(
            lock_id=lock_id,
            content_hash=content_hash,
            created_at=created_at.isoformat(),
            expires_at=expires_at.isoformat(),
            ttl_seconds=ttl_seconds,
            status="ACTIVE"
        )
        self._metadata_store[lock_id] = metadata
        
        if on_expire:
            self._callbacks[lock_id] = on_expire
        
        return EncryptedContent(ciphertext=ciphertext, nonce=nonce, metadata=metadata)
    
    def decrypt(self, encrypted: EncryptedContent) -> Optional[str]:
        lock_id = encrypted.metadata.lock_id
        key = self.key_store.get_key(lock_id)
        if key is None:
            if lock_id in self._metadata_store:
                if self._metadata_store[lock_id].status != "DESTROYED":
                    self._metadata_store[lock_id].status = "EXPIRED"
            return None
        
        try:
            _require_crypto()
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(encrypted.nonce, encrypted.ciphertext, None)
            content = plaintext.decode('utf-8')
            if hashlib.sha256(plaintext).hexdigest() != encrypted.metadata.content_hash:
                return None
            return content
        except Exception:
            return None
    
    def destroy(self, lock_id: str) -> bool:
        success = self.key_store.destroy_key(lock_id)
        if success and lock_id in self._metadata_store:
            self._metadata_store[lock_id].status = "DESTROYED"
        return success
    
    def get_status(self, lock_id: str) -> TimeLockStatus:
        if lock_id not in self._metadata_store:
            return TimeLockStatus.DESTROYED
        metadata = self._metadata_store[lock_id]
        if metadata.status == "DESTROYED":
            return TimeLockStatus.DESTROYED
        if self.key_store.has_key(lock_id):
            return TimeLockStatus.ACTIVE
        return TimeLockStatus.EXPIRED
    
    def get_remaining_time(self, lock_id: str) -> Optional[float]:
        expiry = self.key_store.get_expiry(lock_id)
        if expiry is None:
            return None
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        return max(0, remaining)
    
    def extend_ttl(self, lock_id: str, additional_seconds: int) -> bool:
        key = self.key_store.get_key(lock_id)
        if key is None:
            return False
        current_expiry = self.key_store.get_expiry(lock_id)
        if current_expiry is None:
            return False
        new_expiry = current_expiry + timedelta(seconds=additional_seconds)
        self.key_store.store_key(lock_id, key, new_expiry)
        if lock_id in self._metadata_store:
            self._metadata_store[lock_id].expires_at = new_expiry.isoformat()
            self._metadata_store[lock_id].ttl_seconds += additional_seconds
        return True


class SimulatedTimeLockService:
    """Simulated time-lock service for testing with manual time advancement."""
    
    def __init__(self):
        self._current_time = datetime.now(timezone.utc)
        self._locks: Dict[str, Tuple[bytes, bytes, bytes, int]] = {}
        self._creation_times: Dict[str, datetime] = {}
    
    def set_time(self, new_time: datetime):
        self._current_time = new_time
    
    def advance_time(self, seconds: float):
        self._current_time += timedelta(seconds=seconds)
    
    def get_current_time(self) -> datetime:
        return self._current_time
    
    def encrypt(self, content: str, ttl_seconds: int) -> Tuple[str, bytes]:
        lock_id = secrets.token_hex(16)
        key = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        plaintext = content.encode('utf-8')
        
        _require_crypto()
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        self._locks[lock_id] = (key, nonce, ciphertext, ttl_seconds)
        self._creation_times[lock_id] = self._current_time
        return lock_id, ciphertext
    
    def decrypt(self, lock_id: str) -> Optional[str]:
        if lock_id not in self._locks:
            return None
        
        key, nonce, ciphertext, ttl = self._locks[lock_id]
        created = self._creation_times[lock_id]
        
        if (self._current_time - created).total_seconds() > ttl:
            del self._locks[lock_id]
            del self._creation_times[lock_id]
            return None
        
        try:
            _require_crypto()
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except Exception:
            return None
    
    def is_expired(self, lock_id: str) -> bool:
        if lock_id not in self._locks:
            return True
        _, _, _, ttl = self._locks[lock_id]
        created = self._creation_times[lock_id]
        return (self._current_time - created).total_seconds() > ttl

