"""
Tests for coc_framework.core.crypto_core module.
"""
import pytest
from nacl.signing import SigningKey
from coc_framework.core.crypto_core import CryptoCore


class TestCryptoCore:
    """Test suite for CryptoCore class."""

    def test_generate_keypair_returns_tuple(self):
        """generate_keypair should return a signing key and verify key."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        assert signing_key is not None
        assert verify_key is not None
        # Verify they are the correct types
        assert hasattr(signing_key, 'sign')
        assert hasattr(verify_key, 'verify')

    def test_generate_keypair_unique_keys(self):
        """Each call to generate_keypair should create unique keys."""
        sk1, vk1 = CryptoCore.generate_keypair()
        sk2, vk2 = CryptoCore.generate_keypair()
        
        assert sk1 != sk2
        assert vk1 != vk2

    def test_sign_and_verify_valid_signature(self):
        """A valid signature should verify successfully."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        message = "Test message for signing"
        
        signature = CryptoCore.sign_message(signing_key, message)
        is_valid = CryptoCore.verify_signature(verify_key, message, signature)
        
        assert is_valid is True

    def test_verify_fails_with_wrong_message(self):
        """Verification should fail if the message is different."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        original_message = "Original message"
        tampered_message = "Tampered message"
        
        signature = CryptoCore.sign_message(signing_key, original_message)
        is_valid = CryptoCore.verify_signature(verify_key, tampered_message, signature)
        
        assert is_valid is False

    def test_verify_fails_with_wrong_key(self):
        """Verification should fail with a different key pair."""
        sk1, vk1 = CryptoCore.generate_keypair()
        sk2, vk2 = CryptoCore.generate_keypair()
        message = "Test message"
        
        # Sign with key 1, verify with key 2
        signature = CryptoCore.sign_message(sk1, message)
        is_valid = CryptoCore.verify_signature(vk2, message, signature)
        
        assert is_valid is False

    def test_verify_fails_with_tampered_signature(self):
        """Verification should fail if signature is tampered."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        message = "Test message"
        
        signature = CryptoCore.sign_message(signing_key, message)
        tampered_signature = signature[:-1] + b'\x00'
        is_valid = CryptoCore.verify_signature(verify_key, message, tampered_signature)
        
        assert is_valid is False

    def test_hash_content_deterministic(self):
        """Same content should produce same hash."""
        content = "Test content for hashing"
        
        hash1 = CryptoCore.hash_content(content)
        hash2 = CryptoCore.hash_content(content)
        
        assert hash1 == hash2

    def test_hash_content_different_inputs(self):
        """Different content should produce different hashes."""
        content1 = "Content 1"
        content2 = "Content 2"
        
        hash1 = CryptoCore.hash_content(content1)
        hash2 = CryptoCore.hash_content(content2)
        
        assert hash1 != hash2

    def test_hash_content_format(self):
        """Hash should be a valid SHA-256 hex string (64 characters)."""
        content = "Test content"
        
        content_hash = CryptoCore.hash_content(content)
        
        assert len(content_hash) == 64
        assert all(c in '0123456789abcdef' for c in content_hash)

    def test_sign_empty_message(self):
        """Should handle empty message."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        message = ""
        
        signature = CryptoCore.sign_message(signing_key, message)
        is_valid = CryptoCore.verify_signature(verify_key, message, signature)
        
        assert is_valid is True

    def test_sign_unicode_message(self):
        """Should handle unicode characters in message."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        message = "Unicode test: 你好世界 🔐 🌍"
        
        signature = CryptoCore.sign_message(signing_key, message)
        is_valid = CryptoCore.verify_signature(verify_key, message, signature)
        
        assert is_valid is True

    def test_hash_unicode_content(self):
        """Should handle unicode in hash content."""
        content = "Unicode: 日本語 العربية 한국어"
        
        content_hash = CryptoCore.hash_content(content)
        
        assert len(content_hash) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
