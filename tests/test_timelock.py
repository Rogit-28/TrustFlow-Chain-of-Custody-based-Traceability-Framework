"""
Tests for coc_framework.core.timelock module.
"""
import pytest
import time
from datetime import datetime, timedelta, timezone
from coc_framework.core.timelock import (
    TimeLockEngine,
    TimeLockStatus,
    TimeLockMetadata,
    EncryptedContent,
    KeyStore,
    SimulatedTimeLockService,
    CryptoUnavailableError,
    CRYPTO_AVAILABLE,
)


class TestKeyStore:
    """Tests for the KeyStore class."""

    def test_store_and_retrieve_key(self):
        """Should store and retrieve a key."""
        store = KeyStore()
        lock_id = "test_lock"
        key = b"test_key_32_bytes_long__________"  # 32 bytes
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        
        store.store_key(lock_id, key, expiry)
        retrieved = store.get_key(lock_id)
        
        assert retrieved == key

    def test_get_nonexistent_key(self):
        """Should return None for nonexistent key."""
        store = KeyStore()
        
        assert store.get_key("nonexistent") is None

    def test_destroy_key(self):
        """Should destroy a key."""
        store = KeyStore()
        lock_id = "to_destroy"
        key = b"x" * 32
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        
        store.store_key(lock_id, key, expiry)
        assert store.has_key(lock_id) is True
        
        success = store.destroy_key(lock_id)
        
        assert success is True
        assert store.has_key(lock_id) is False

    def test_destroy_nonexistent_key(self):
        """Destroying nonexistent key returns False."""
        store = KeyStore()
        
        assert store.destroy_key("nonexistent") is False

    def test_get_expired_key(self):
        """Should return None for expired key."""
        store = KeyStore()
        lock_id = "expired"
        key = b"x" * 32
        expiry = datetime.now(timezone.utc) - timedelta(seconds=1)  # Already expired
        
        store.store_key(lock_id, key, expiry)
        
        assert store.get_key(lock_id) is None

    def test_get_expiry(self):
        """Should return expiry time."""
        store = KeyStore()
        lock_id = "test"
        key = b"x" * 32
        expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        
        store.store_key(lock_id, key, expiry)
        
        retrieved_expiry = store.get_expiry(lock_id)
        
        # Compare with tolerance for timing
        assert abs((retrieved_expiry - expiry).total_seconds()) < 1


class TestTimeLockMetadata:
    """Tests for TimeLockMetadata dataclass."""

    def test_to_dict(self):
        """Should serialize to dict."""
        meta = TimeLockMetadata(
            lock_id="lock123",
            content_hash="abc123",
            created_at="2024-01-01T00:00:00+00:00",
            expires_at="2024-01-01T01:00:00+00:00",
            ttl_seconds=3600,
            status="ACTIVE"
        )
        
        d = meta.to_dict()
        
        assert d["lock_id"] == "lock123"
        assert d["ttl_seconds"] == 3600
        assert d["status"] == "ACTIVE"

    def test_from_dict(self):
        """Should deserialize from dict."""
        data = {
            "lock_id": "lock456",
            "content_hash": "def456",
            "created_at": "2024-01-01T00:00:00+00:00",
            "expires_at": "2024-01-01T02:00:00+00:00",
            "ttl_seconds": 7200,
            "status": "EXPIRED"
        }
        
        meta = TimeLockMetadata.from_dict(data)
        
        assert meta.lock_id == "lock456"
        assert meta.ttl_seconds == 7200
        assert meta.status == "EXPIRED"

    def test_is_expired_false(self):
        """is_expired should return False for future expiry."""
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        meta = TimeLockMetadata(
            lock_id="test",
            content_hash="hash",
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=expires,
            ttl_seconds=3600
        )
        
        assert meta.is_expired() is False

    def test_is_expired_true(self):
        """is_expired should return True for past expiry."""
        expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        meta = TimeLockMetadata(
            lock_id="test",
            content_hash="hash",
            created_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            expires_at=expires,
            ttl_seconds=3600
        )
        
        assert meta.is_expired() is True


class TestTimeLockEngine:
    """Tests for the TimeLockEngine class."""

    @pytest.fixture
    def engine(self):
        """Create engine and ensure cleanup."""
        engine = TimeLockEngine(cleanup_interval=10.0)  # Long interval for tests
        yield engine
        engine.shutdown()

    def test_encrypt_returns_encrypted_content(self, engine):
        """encrypt should return EncryptedContent with metadata."""
        content = "Secret message"
        
        encrypted = engine.encrypt(content, ttl_seconds=60)
        
        assert isinstance(encrypted, EncryptedContent)
        assert encrypted.ciphertext is not None
        assert encrypted.nonce is not None
        assert encrypted.metadata.lock_id is not None
        assert encrypted.metadata.ttl_seconds == 60

    def test_decrypt_valid_content(self, engine):
        """Should decrypt content within TTL."""
        content = "Decrypt me"
        
        encrypted = engine.encrypt(content, ttl_seconds=60)
        decrypted = engine.decrypt(encrypted)
        
        assert decrypted == content

    def test_decrypt_preserves_unicode(self, engine):
        """Should preserve unicode in encryption/decryption."""
        content = "Unicode: 日本語 🔐 العربية"
        
        encrypted = engine.encrypt(content, ttl_seconds=60)
        decrypted = engine.decrypt(encrypted)
        
        assert decrypted == content

    def test_destroy_makes_content_unrecoverable(self, engine):
        """destroy should make content unrecoverable."""
        content = "Will be destroyed"
        
        encrypted = engine.encrypt(content, ttl_seconds=3600)
        lock_id = encrypted.metadata.lock_id
        
        # Should work before destroy
        assert engine.decrypt(encrypted) == content
        
        # Destroy
        success = engine.destroy(lock_id)
        assert success is True
        
        # Should fail after destroy
        assert engine.decrypt(encrypted) is None

    def test_get_status_active(self, engine):
        """Should return ACTIVE for valid lock."""
        encrypted = engine.encrypt("test", ttl_seconds=60)
        
        status = engine.get_status(encrypted.metadata.lock_id)
        
        assert status == TimeLockStatus.ACTIVE

    def test_get_status_destroyed(self, engine):
        """Should return DESTROYED after destroy."""
        encrypted = engine.encrypt("test", ttl_seconds=60)
        engine.destroy(encrypted.metadata.lock_id)
        
        status = engine.get_status(encrypted.metadata.lock_id)
        
        assert status == TimeLockStatus.DESTROYED

    def test_get_remaining_time(self, engine):
        """Should return remaining time."""
        encrypted = engine.encrypt("test", ttl_seconds=60)
        
        remaining = engine.get_remaining_time(encrypted.metadata.lock_id)
        
        assert remaining is not None
        assert 58 < remaining <= 60  # Allow some tolerance

    def test_extend_ttl(self, engine):
        """Should extend TTL."""
        encrypted = engine.encrypt("test", ttl_seconds=60)
        lock_id = encrypted.metadata.lock_id
        
        original_remaining = engine.get_remaining_time(lock_id)
        
        success = engine.extend_ttl(lock_id, additional_seconds=30)
        
        assert success is True
        new_remaining = engine.get_remaining_time(lock_id)
        assert new_remaining > original_remaining

    def test_extend_ttl_nonexistent_lock(self, engine):
        """extend_ttl should return False for nonexistent lock."""
        assert engine.extend_ttl("nonexistent", 30) is False


class TestSimulatedTimeLockService:
    """Tests for the SimulatedTimeLockService class."""

    def test_encrypt_and_decrypt(self):
        """Should encrypt and decrypt."""
        sim = SimulatedTimeLockService()
        content = "Simulated secret"
        
        lock_id, ciphertext = sim.encrypt(content, ttl_seconds=60)
        decrypted = sim.decrypt(lock_id)
        
        assert decrypted == content

    def test_advance_time_causes_expiry(self):
        """Advancing time past TTL should cause expiry."""
        sim = SimulatedTimeLockService()
        content = "Will expire"
        
        lock_id, _ = sim.encrypt(content, ttl_seconds=30)
        
        # Still valid
        assert sim.decrypt(lock_id) == content
        assert sim.is_expired(lock_id) is False
        
        # Advance past TTL
        sim.advance_time(35)
        
        # Now expired
        assert sim.is_expired(lock_id) is True
        assert sim.decrypt(lock_id) is None

    def test_set_time(self):
        """Should be able to set absolute time."""
        sim = SimulatedTimeLockService()
        future_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
        
        sim.set_time(future_time)
        
        assert sim.get_current_time() == future_time

    def test_multiple_locks_different_ttls(self):
        """Should handle multiple locks with different TTLs."""
        sim = SimulatedTimeLockService()
        
        lock1, _ = sim.encrypt("Short lived", ttl_seconds=30)
        lock2, _ = sim.encrypt("Long lived", ttl_seconds=120)
        
        # Both valid initially
        assert sim.decrypt(lock1) is not None
        assert sim.decrypt(lock2) is not None
        
        # After 40 seconds: lock1 expired, lock2 still valid
        sim.advance_time(40)
        assert sim.is_expired(lock1) is True
        assert sim.is_expired(lock2) is False
        
        # After another 100 seconds: both expired
        sim.advance_time(100)
        assert sim.is_expired(lock1) is True
        assert sim.is_expired(lock2) is True


class TestEncryptedContent:
    """Tests for EncryptedContent serialization."""

    def test_to_dict_and_from_dict(self):
        """Should serialize and deserialize correctly."""
        metadata = TimeLockMetadata(
            lock_id="test_lock",
            content_hash="abc123",
            created_at="2024-01-01T00:00:00+00:00",
            expires_at="2024-01-01T01:00:00+00:00",
            ttl_seconds=3600
        )
        original = EncryptedContent(
            ciphertext=b"encrypted_data",
            nonce=b"nonce_value_",  # 12 bytes
            metadata=metadata
        )
        
        serialized = original.to_dict()
        restored = EncryptedContent.from_dict(serialized)
        
        assert restored.ciphertext == original.ciphertext
        assert restored.nonce == original.nonce
        assert restored.metadata.lock_id == original.metadata.lock_id


class TestTimeLockIntegration:
    """Integration tests for time-lock system."""

    def test_full_lifecycle(self):
        """Full lifecycle: create -> use -> expire/destroy."""
        engine = TimeLockEngine(cleanup_interval=10.0)
        
        try:
            # Create
            content = "Integration test content"
            encrypted = engine.encrypt(content, ttl_seconds=3600)
            
            # Verify active
            assert engine.get_status(encrypted.metadata.lock_id) == TimeLockStatus.ACTIVE
            
            # Decrypt works
            assert engine.decrypt(encrypted) == content
            
            # Destroy
            engine.destroy(encrypted.metadata.lock_id)
            
            # Verify destroyed
            assert engine.get_status(encrypted.metadata.lock_id) == TimeLockStatus.DESTROYED
            
            # Decrypt fails
            assert engine.decrypt(encrypted) is None
        finally:
            engine.shutdown()

    def test_context_manager(self):
        """TimeLockEngine should work as context manager."""
        with TimeLockEngine(cleanup_interval=10.0) as engine:
            content = "Context manager test"
            encrypted = engine.encrypt(content, ttl_seconds=60)
            decrypted = engine.decrypt(encrypted)
            
            assert decrypted == content
        # Engine should be automatically shut down after context

    def test_context_manager_exception_handling(self):
        """Context manager should cleanup even on exception."""
        engine = None
        try:
            with TimeLockEngine(cleanup_interval=10.0) as e:
                engine = e
                encrypted = e.encrypt("test", ttl_seconds=60)
                raise ValueError("Test exception")
        except ValueError:
            pass
        # Engine should still be cleaned up


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
