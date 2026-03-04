"""
Tests for coc_framework.core.secret_sharing module.
"""
import pytest
from coc_framework.core.secret_sharing import (
    split_secret,
    reconstruct_secret,
    verify_share,
    verify_share_mac,
    Share,
    SecretSharingEngine,
    ShareIntegrityError,
)


class TestSplitSecret:
    """Tests for the split_secret function."""

    def test_split_creates_correct_number_of_shares(self):
        """split_secret should create exactly num_shares shares."""
        secret = "Test secret message"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        assert len(shares) == 5
        assert isinstance(hmac_key, bytes)
        assert len(hmac_key) == 32  # HMAC key is 32 bytes

    def test_split_shares_have_correct_metadata(self):
        """Each share should have correct threshold and total_shares."""
        secret = "Test secret"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        for share in shares:
            assert share.threshold == 3
            assert share.total_shares == 5
            assert share.content_hash is not None
            assert len(share.content_hash) == 64  # SHA-256 hex
            assert share.mac != ""  # MAC should be populated

    def test_split_shares_have_unique_indices(self):
        """Each share should have a unique index."""
        secret = "Test secret"
        shares, _hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        indices = [s.index for s in shares]
        assert len(indices) == len(set(indices))

    def test_split_threshold_equals_num_shares(self):
        """Should work when threshold equals num_shares."""
        secret = "All shares needed"
        shares, _hmac_key = split_secret(secret, threshold=5, num_shares=5)
        
        assert len(shares) == 5
        for share in shares:
            assert share.threshold == 5

    def test_split_minimum_threshold(self):
        """Minimum threshold is 2."""
        secret = "Test"
        shares, _hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        assert len(shares) == 3
        assert shares[0].threshold == 2

    def test_split_rejects_threshold_one(self):
        """Threshold of 1 should raise ValueError."""
        with pytest.raises(ValueError, match="Threshold must be at least 2"):
            split_secret("secret", threshold=1, num_shares=3)

    def test_split_rejects_threshold_greater_than_shares(self):
        """Threshold > num_shares should raise ValueError."""
        with pytest.raises(ValueError, match="cannot exceed"):
            split_secret("secret", threshold=6, num_shares=5)

    def test_split_rejects_single_share(self):
        """num_shares < 2 should raise ValueError."""
        with pytest.raises(ValueError, match="Threshold must be at least 2"):
            split_secret("secret", threshold=1, num_shares=1)


class TestReconstructSecret:
    """Tests for the reconstruct_secret function."""

    def test_reconstruct_with_exact_threshold(self):
        """Should reconstruct with exactly threshold shares."""
        secret = "Confidential information"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        # Use exactly 3 shares
        subset = shares[:3]
        reconstructed = reconstruct_secret(subset, hmac_key=hmac_key)
        
        assert reconstructed == secret

    def test_reconstruct_with_more_than_threshold(self):
        """Should reconstruct with more than threshold shares."""
        secret = "More shares than needed"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        # Use all 5 shares
        reconstructed = reconstruct_secret(shares, hmac_key=hmac_key)
        
        assert reconstructed == secret

    def test_reconstruct_with_different_share_subsets(self):
        """Any subset of threshold shares should work."""
        secret = "Any subset works"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        # Try different combinations
        combinations = [
            [shares[0], shares[1], shares[2]],
            [shares[0], shares[2], shares[4]],
            [shares[1], shares[3], shares[4]],
            [shares[2], shares[3], shares[4]],
        ]
        
        for subset in combinations:
            reconstructed = reconstruct_secret(subset, hmac_key=hmac_key)
            assert reconstructed == secret

    def test_reconstruct_fails_with_insufficient_shares(self):
        """Should fail when fewer than threshold shares provided."""
        secret = "Need all shares"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        # Try with only 2 shares
        with pytest.raises(ValueError, match="Need at least 3 shares"):
            reconstruct_secret(shares[:2], hmac_key=hmac_key)

    def test_reconstruct_empty_shares_list(self):
        """Should raise error for empty shares list."""
        with pytest.raises(ValueError, match="No shares provided"):
            reconstruct_secret([])

    def test_reconstruct_mismatched_content_hash(self):
        """Should fail when shares are from different secrets."""
        secret1 = "First secret"
        secret2 = "Second secret"
        
        shares1, _hmac_key1 = split_secret(secret1, threshold=2, num_shares=3)
        shares2, _hmac_key2 = split_secret(secret2, threshold=2, num_shares=3)
        
        # Mix shares from different secrets
        mixed = [shares1[0], shares2[1]]
        
        with pytest.raises(ValueError, match="from different secrets"):
            reconstruct_secret(mixed)

    def test_reconstruct_long_content(self):
        """Should handle content longer than a single chunk."""
        secret = "A" * 1000  # Long content
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        reconstructed = reconstruct_secret(shares[:3], hmac_key=hmac_key)
        
        assert reconstructed == secret

    def test_reconstruct_unicode_content(self):
        """Should handle unicode content."""
        secret = "Unicode test: 你好世界 🔐 Ελληνικά العربية"
        shares, hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        reconstructed = reconstruct_secret(shares[:2], hmac_key=hmac_key)
        
        assert reconstructed == secret


class TestVerifyShare:
    """Tests for the verify_share function."""

    def test_verify_valid_share(self):
        """Should return True for valid share."""
        secret = "Test"
        shares, _hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        assert verify_share(shares[0], shares[0].content_hash) is True

    def test_verify_invalid_hash(self):
        """Should return False for wrong content hash."""
        secret = "Test"
        shares, _hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        assert verify_share(shares[0], "wrong_hash") is False


class TestShare:
    """Tests for the Share dataclass."""

    def test_share_to_dict(self):
        """Share.to_dict should return all fields."""
        share = Share(
            index=1,
            value="0xabc",
            share_id="test_1",
            content_hash="hash123",
            threshold=3,
            total_shares=5
        )
        
        d = share.to_dict()
        
        assert d["index"] == 1
        assert d["value"] == "0xabc"
        assert d["share_id"] == "test_1"
        assert d["content_hash"] == "hash123"
        assert d["threshold"] == 3
        assert d["total_shares"] == 5

    def test_share_from_dict(self):
        """Share.from_dict should recreate the share."""
        original = Share(
            index=2,
            value="0xdef",
            share_id="test_2",
            content_hash="hash456",
            threshold=4,
            total_shares=7
        )
        
        recreated = Share.from_dict(original.to_dict())
        
        assert recreated.index == original.index
        assert recreated.value == original.value
        assert recreated.share_id == original.share_id
        assert recreated.content_hash == original.content_hash
        assert recreated.threshold == original.threshold
        assert recreated.total_shares == original.total_shares


class TestSecretSharingEngine:
    """Tests for the SecretSharingEngine class."""

    def test_engine_split_content(self):
        """Engine should split content to recipients."""
        engine = SecretSharingEngine()
        content = "Sensitive data"
        recipients = ["peer_1", "peer_2", "peer_3", "peer_4", "peer_5"]
        
        share_map = engine.split_content(content, recipients, threshold=3)
        
        assert len(share_map) == 5
        for peer_id in recipients:
            assert peer_id in share_map
            assert isinstance(share_map[peer_id], Share)

    def test_engine_reconstruct_content(self):
        """Engine should reconstruct from shares."""
        engine = SecretSharingEngine()
        content = "Reconstruct this"
        recipients = ["p1", "p2", "p3", "p4"]
        
        share_map = engine.split_content(content, recipients, threshold=2)
        shares = list(share_map.values())[:2]
        
        reconstructed = engine.reconstruct_content(shares)
        
        assert reconstructed == content

    def test_engine_default_threshold(self):
        """Engine should use majority threshold by default."""
        engine = SecretSharingEngine()
        content = "Test"
        recipients = ["p1", "p2", "p3", "p4", "p5"]
        
        share_map = engine.split_content(content, recipients)
        
        # Default: majority = 5 // 2 + 1 = 3
        assert share_map["p1"].threshold == 3

    def test_engine_get_share_holders(self):
        """Should track who holds shares."""
        engine = SecretSharingEngine()
        recipients = ["alice", "bob", "charlie"]
        
        share_map = engine.split_content("secret", recipients, threshold=2)
        content_hash = share_map["alice"].content_hash
        
        holders = engine.get_share_holders(content_hash)
        
        assert set(holders) == set(recipients)

    def test_engine_rejects_single_recipient(self):
        """Should reject single recipient."""
        engine = SecretSharingEngine()
        
        with pytest.raises(ValueError, match="at least 2 recipients"):
            engine.split_content("secret", ["only_one"], threshold=2)


class TestSecretSharingIntegration:
    """Integration tests for the secret sharing system."""

    def test_full_split_reconstruct_cycle(self):
        """Full cycle: split -> serialize -> deserialize -> reconstruct."""
        engine = SecretSharingEngine()
        original = "Full integration test content"
        recipients = ["node_a", "node_b", "node_c", "node_d"]
        
        # Split
        share_map = engine.split_content(original, recipients, threshold=2)
        
        # Serialize
        serialized = {peer: share.to_dict() for peer, share in share_map.items()}
        
        # Deserialize
        deserialized = [Share.from_dict(serialized["node_a"]), Share.from_dict(serialized["node_c"])]
        
        # Reconstruct
        reconstructed = engine.reconstruct_content(deserialized)
        
        assert reconstructed == original

    def test_deletion_simulation(self):
        """Simulate deletion by destroying enough shares."""
        secret = "Delete me"
        shares, hmac_key = split_secret(secret, threshold=3, num_shares=5)
        
        # "Delete" 3 shares, leaving only 2
        remaining = shares[3:]  # Only shares 4 and 5
        
        # Reconstruction should fail
        with pytest.raises(ValueError, match="Need at least 3 shares"):
            reconstruct_secret(remaining, hmac_key=hmac_key)


class TestShareMACVerification:
    """Tests for HMAC authentication of shares."""

    def test_verify_share_mac_valid(self):
        """Should verify valid MAC."""
        secret = "Test MAC verification"
        shares, hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        for share in shares:
            assert verify_share_mac(share, hmac_key) is True

    def test_verify_share_mac_wrong_key(self):
        """Should fail with wrong HMAC key."""
        import os
        secret = "Test MAC verification"
        shares, hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        wrong_key = os.urandom(32)
        for share in shares:
            assert verify_share_mac(share, wrong_key) is False

    def test_verify_share_mac_tampered_value(self):
        """Should fail if share value is tampered."""
        secret = "Test tampering detection"
        shares, hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        # Tamper with share value
        tampered_share = Share(
            index=shares[0].index,
            value="0xtampered_value",
            share_id=shares[0].share_id,
            content_hash=shares[0].content_hash,
            threshold=shares[0].threshold,
            total_shares=shares[0].total_shares,
            mac=shares[0].mac,
        )
        
        assert verify_share_mac(tampered_share, hmac_key) is False

    def test_reconstruct_detects_tampered_share(self):
        """Reconstruction should fail with tampered share when MAC verification enabled."""
        secret = "Detect tampering on reconstruct"
        shares, hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        # Tamper with one share
        tampered_share = Share(
            index=shares[0].index,
            value="0xtampered",
            share_id=shares[0].share_id,
            content_hash=shares[0].content_hash,
            threshold=shares[0].threshold,
            total_shares=shares[0].total_shares,
            mac=shares[0].mac,
        )
        
        tampered_list = [tampered_share, shares[1]]
        
        with pytest.raises(ShareIntegrityError, match="failed integrity verification"):
            reconstruct_secret(tampered_list, hmac_key=hmac_key)

    def test_reconstruct_without_mac_key_skips_verification(self):
        """Reconstruction without hmac_key should skip MAC verification."""
        secret = "No MAC check"
        shares, _hmac_key = split_secret(secret, threshold=2, num_shares=3)
        
        # Should succeed without hmac_key (no verification)
        reconstructed = reconstruct_secret(shares[:2])
        assert reconstructed == secret


class TestSecretSharingEngineAuthorization:
    """Tests for the SecretSharingEngine authorization features."""

    def test_is_authorized_for_recipients(self):
        """Recipients should be authorized to access shares."""
        engine = SecretSharingEngine()
        content = "Authorized content"
        recipients = ["alice", "bob", "charlie"]
        
        share_map = engine.split_content(content, recipients, threshold=2)
        content_hash = share_map["alice"].content_hash
        
        for recipient in recipients:
            assert engine.is_authorized(content_hash, recipient) is True

    def test_is_not_authorized_for_non_recipients(self):
        """Non-recipients should not be authorized."""
        engine = SecretSharingEngine()
        content = "Private content"
        recipients = ["alice", "bob"]
        
        share_map = engine.split_content(content, recipients, threshold=2)
        content_hash = share_map["alice"].content_hash
        
        assert engine.is_authorized(content_hash, "eve") is False
        assert engine.is_authorized(content_hash, "mallory") is False

    def test_is_authorized_unknown_content_hash(self):
        """Unknown content_hash should return False."""
        engine = SecretSharingEngine()
        
        assert engine.is_authorized("unknown_hash", "anyone") is False

    def test_get_hmac_key_for_split_content(self):
        """Engine should store and return HMAC key for split content."""
        engine = SecretSharingEngine()
        content = "Content with HMAC"
        recipients = ["alice", "bob", "charlie"]
        
        share_map = engine.split_content(content, recipients, threshold=2)
        content_hash = share_map["alice"].content_hash
        
        hmac_key = engine.get_hmac_key(content_hash)
        assert hmac_key is not None
        assert isinstance(hmac_key, bytes)
        assert len(hmac_key) == 32

    def test_get_hmac_key_unknown_content_hash(self):
        """Unknown content_hash should return None for HMAC key."""
        engine = SecretSharingEngine()
        
        assert engine.get_hmac_key("unknown_hash") is None

    def test_engine_reconstruct_with_mac_verification(self):
        """Engine should verify MACs when reconstructing."""
        engine = SecretSharingEngine()
        content = "Verified content"
        recipients = ["alice", "bob", "charlie"]
        
        share_map = engine.split_content(content, recipients, threshold=2)
        shares = [share_map["alice"], share_map["bob"]]
        
        # Should succeed with valid shares
        reconstructed = engine.reconstruct_content(shares)
        assert reconstructed == content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
