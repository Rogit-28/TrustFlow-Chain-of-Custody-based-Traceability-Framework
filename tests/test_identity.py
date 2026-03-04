"""
Tests for coc_framework.core.identity module.
"""
import pytest
from datetime import datetime, timezone, timedelta
from nacl.signing import SigningKey

from coc_framework.core.identity import (
    Identity,
    Certificate,
    CertificateAuthority,
    IdentityStore,
)
from coc_framework.core.crypto_core import CryptoCore


class TestIdentity:
    """Test suite for Identity class."""

    def test_identity_creation(self):
        """Identity can be created with required fields."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        identity = Identity.create("peer-001", verify_key)
        
        assert identity.peer_id == "peer-001"
        assert identity.public_key == bytes(verify_key)
        assert identity.created_at is not None
        assert identity.metadata == {}

    def test_identity_creation_with_metadata(self):
        """Identity can be created with metadata."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        metadata = {"name": "Test Peer", "role": "validator"}
        
        identity = Identity.create("peer-002", verify_key, metadata)
        
        assert identity.metadata == metadata

    def test_identity_to_dict(self):
        """Identity can be serialized to dictionary."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        identity = Identity.create("peer-003", verify_key, {"key": "value"})
        
        data = identity.to_dict()
        
        assert data["peer_id"] == "peer-003"
        assert data["public_key"] == identity.public_key.hex()
        assert data["created_at"] == identity.created_at
        assert data["metadata"] == {"key": "value"}

    def test_identity_from_dict(self):
        """Identity can be deserialized from dictionary."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        original = Identity.create("peer-004", verify_key, {"test": "data"})
        
        data = original.to_dict()
        restored = Identity.from_dict(data)
        
        assert restored.peer_id == original.peer_id
        assert restored.public_key == original.public_key
        assert restored.created_at == original.created_at
        assert restored.metadata == original.metadata

    def test_identity_get_verify_key(self):
        """get_verify_key returns a usable VerifyKey."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        identity = Identity.create("peer-005", verify_key)
        
        recovered_key = identity.get_verify_key()
        
        # Verify the recovered key works for signature verification
        message = "test message"
        signature = CryptoCore.sign_message(signing_key, message)
        assert CryptoCore.verify_signature(recovered_key, message, signature)

    def test_identity_roundtrip_serialization(self):
        """Identity survives JSON serialization roundtrip."""
        import json
        signing_key, verify_key = CryptoCore.generate_keypair()
        original = Identity.create("peer-006", verify_key, {"extra": "info"})
        
        json_str = json.dumps(original.to_dict())
        restored = Identity.from_dict(json.loads(json_str))
        
        assert restored.peer_id == original.peer_id
        assert restored.public_key == original.public_key


class TestCertificate:
    """Test suite for Certificate class."""

    def test_certificate_to_dict(self):
        """Certificate can be serialized to dictionary."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-cert-001", signing_key)
        
        data = cert.to_dict()
        
        assert "identity" in data
        assert data["issuer_id"] == "self"
        assert "valid_from" in data
        assert "valid_until" in data
        assert "signature" in data
        assert "serial_number" in data

    def test_certificate_from_dict(self):
        """Certificate can be deserialized from dictionary."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        original = CertificateAuthority.create_self_signed("peer-cert-002", signing_key)
        
        data = original.to_dict()
        restored = Certificate.from_dict(data)
        
        assert restored.identity.peer_id == original.identity.peer_id
        assert restored.issuer_id == original.issuer_id
        assert restored.signature == original.signature
        assert restored.serial_number == original.serial_number

    def test_certificate_is_self_signed(self):
        """is_self_signed correctly identifies self-signed certificates."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-cert-003", signing_key)
        
        assert cert.is_self_signed() is True
        assert cert.issuer_id == "self"

    def test_certificate_is_not_expired(self):
        """Fresh certificate should not be expired."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-cert-004", signing_key, validity_days=365)
        
        assert cert.is_expired() is False
        assert cert.is_valid_time() is True

    def test_certificate_get_signed_data_deterministic(self):
        """get_signed_data produces deterministic output."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-cert-005", signing_key)
        
        data1 = cert.get_signed_data()
        data2 = cert.get_signed_data()
        
        assert data1 == data2

    def test_certificate_serial_number_is_uuid(self):
        """Certificate serial number should be a valid UUID."""
        import uuid
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-cert-006", signing_key)
        
        # This should not raise
        parsed = uuid.UUID(cert.serial_number)
        assert str(parsed) == cert.serial_number


class TestSelfSignedCertificate:
    """Test suite for self-signed certificate creation."""

    def test_create_self_signed_certificate(self):
        """Self-signed certificate is created correctly."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        cert = CertificateAuthority.create_self_signed("peer-self-001", signing_key)
        
        assert cert.identity.peer_id == "peer-self-001"
        assert cert.is_self_signed() is True
        assert cert.signature != ""
        assert cert.serial_number != ""

    def test_self_signed_certificate_verifies(self):
        """Self-signed certificate signature is valid."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-self-002", signing_key)
        
        is_valid = CertificateAuthority.verify_self_signed(cert)
        
        assert is_valid is True

    def test_self_signed_certificate_with_metadata(self):
        """Self-signed certificate can include metadata."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        metadata = {"organization": "TrustFlow", "unit": "Testing"}
        
        cert = CertificateAuthority.create_self_signed(
            "peer-self-003", signing_key, metadata=metadata
        )
        
        assert cert.identity.metadata == metadata

    def test_self_signed_certificate_custom_validity(self):
        """Self-signed certificate respects custom validity period."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        cert = CertificateAuthority.create_self_signed(
            "peer-self-004", signing_key, validity_days=30
        )
        
        valid_from = datetime.fromisoformat(cert.valid_from)
        valid_until = datetime.fromisoformat(cert.valid_until)
        
        # Should be approximately 30 days
        delta = valid_until - valid_from
        assert 29 <= delta.days <= 31

    def test_tampered_self_signed_fails_verification(self):
        """Self-signed certificate fails verification if tampered."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-self-005", signing_key)
        
        # Tamper with the certificate
        cert.identity.peer_id = "tampered-peer"
        
        is_valid = CertificateAuthority.verify_self_signed(cert)
        
        assert is_valid is False


class TestCertificateAuthority:
    """Test suite for CertificateAuthority class."""

    def test_ca_creation(self):
        """CertificateAuthority can be created."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-001", ca_verify_key)
        
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        assert ca.peer_id == "ca-001"
        assert ca.identity == ca_identity

    def test_ca_issues_certificate(self):
        """CA can issue certificates for other peers."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-002", ca_verify_key)
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        peer_identity = Identity.create("peer-from-ca-002", peer_verify_key)
        
        cert = ca.issue_certificate(peer_identity)
        
        assert cert.identity.peer_id == "peer-from-ca-002"
        assert cert.issuer_id == "ca-002"
        assert cert.is_self_signed() is False
        assert cert.signature != ""

    def test_ca_verifies_issued_certificate(self):
        """CA can verify certificates it issued."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-003", ca_verify_key)
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        peer_identity = Identity.create("peer-from-ca-003", peer_verify_key)
        
        cert = ca.issue_certificate(peer_identity)
        is_valid = ca.verify_certificate(cert)
        
        assert is_valid is True

    def test_ca_rejects_certificate_from_other_ca(self):
        """CA rejects certificates issued by different CA."""
        ca1_signing_key, ca1_verify_key = CryptoCore.generate_keypair()
        ca1_identity = Identity.create("ca-004-a", ca1_verify_key)
        ca1 = CertificateAuthority(ca1_identity, ca1_signing_key)
        
        ca2_signing_key, ca2_verify_key = CryptoCore.generate_keypair()
        ca2_identity = Identity.create("ca-004-b", ca2_verify_key)
        ca2 = CertificateAuthority(ca2_identity, ca2_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        peer_identity = Identity.create("peer-from-ca-004", peer_verify_key)
        
        # CA1 issues the certificate
        cert = ca1.issue_certificate(peer_identity)
        
        # CA2 tries to verify it - should fail
        is_valid = ca2.verify_certificate(cert)
        
        assert is_valid is False

    def test_ca_verifies_self_signed(self):
        """CA can verify self-signed certificates."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-005", ca_verify_key)
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("self-signed-peer", peer_signing_key)
        
        is_valid = ca.verify_certificate(cert)
        
        assert is_valid is True

    def test_ca_custom_validity_period(self):
        """CA respects custom validity period when issuing certificates."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-006", ca_verify_key)
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        peer_identity = Identity.create("peer-from-ca-006", peer_verify_key)
        
        cert = ca.issue_certificate(peer_identity, validity_days=7)
        
        valid_from = datetime.fromisoformat(cert.valid_from)
        valid_until = datetime.fromisoformat(cert.valid_until)
        
        delta = valid_until - valid_from
        assert 6 <= delta.days <= 8

    def test_tampered_ca_certificate_fails_verification(self):
        """CA-issued certificate fails verification if tampered."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-007", ca_verify_key)
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        peer_identity = Identity.create("peer-from-ca-007", peer_verify_key)
        
        cert = ca.issue_certificate(peer_identity)
        
        # Tamper with the certificate
        cert.identity.metadata["tampered"] = "yes"
        
        is_valid = ca.verify_certificate(cert)
        
        assert is_valid is False


class TestCertificateExpiration:
    """Test suite for certificate expiration handling."""

    def test_expired_certificate_detected(self):
        """Expired certificates are correctly identified."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-exp-001", signing_key)
        
        # Manually set to expired
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cert.valid_until = past_time
        
        assert cert.is_expired() is True
        assert cert.is_valid_time() is False

    def test_expired_self_signed_fails_verification(self):
        """Expired self-signed certificate fails verification."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-exp-002", signing_key)
        
        # Manually set to expired
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cert.valid_until = past_time
        
        is_valid = CertificateAuthority.verify_self_signed(cert)
        
        assert is_valid is False

    def test_expired_ca_certificate_fails_verification(self):
        """Expired CA-issued certificate fails verification."""
        ca_signing_key, ca_verify_key = CryptoCore.generate_keypair()
        ca_identity = Identity.create("ca-exp-001", ca_verify_key)
        ca = CertificateAuthority(ca_identity, ca_signing_key)
        
        peer_signing_key, peer_verify_key = CryptoCore.generate_keypair()
        peer_identity = Identity.create("peer-exp-003", peer_verify_key)
        
        cert = ca.issue_certificate(peer_identity)
        
        # Manually expire it
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cert.valid_until = past_time
        
        is_valid = ca.verify_certificate(cert)
        
        assert is_valid is False

    def test_not_yet_valid_certificate(self):
        """Certificate not yet valid is detected."""
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("peer-exp-004", signing_key)
        
        # Set valid_from to future
        future_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        cert.valid_from = future_time
        
        assert cert.is_not_yet_valid() is True
        assert cert.is_valid_time() is False


class TestIdentityStore:
    """Test suite for IdentityStore class."""

    def test_store_creation(self):
        """IdentityStore can be created empty."""
        store = IdentityStore()
        
        assert store.list_all_certificates() == []
        assert store.list_all_identities() == []

    def test_add_identity(self):
        """Identities can be added and retrieved."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        identity = Identity.create("store-peer-001", verify_key)
        
        store.add_identity(identity)
        retrieved = store.get_identity("store-peer-001")
        
        assert retrieved is not None
        assert retrieved.peer_id == "store-peer-001"

    def test_get_nonexistent_identity(self):
        """Getting nonexistent identity returns None."""
        store = IdentityStore()
        
        retrieved = store.get_identity("nonexistent")
        
        assert retrieved is None

    def test_add_certificate(self):
        """Certificates can be added and retrieved."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("store-peer-002", signing_key)
        
        store.add_certificate(cert)
        retrieved = store.get_certificate(cert.serial_number)
        
        assert retrieved is not None
        assert retrieved.serial_number == cert.serial_number

    def test_get_certificates_for_peer(self):
        """Can retrieve all certificates for a peer."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        # Add multiple certificates for same peer
        cert1 = CertificateAuthority.create_self_signed("store-peer-003", signing_key)
        cert2 = CertificateAuthority.create_self_signed("store-peer-003", signing_key)
        
        store.add_certificate(cert1)
        store.add_certificate(cert2)
        
        certs = store.get_certificates_for_peer("store-peer-003")
        
        assert len(certs) == 2

    def test_get_certificates_for_peer_empty(self):
        """Returns empty list for peer with no certificates."""
        store = IdentityStore()
        
        certs = store.get_certificates_for_peer("nonexistent")
        
        assert certs == []

    def test_get_valid_certificate(self):
        """Can retrieve a valid certificate for a peer."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("store-peer-004", signing_key)
        
        store.add_certificate(cert)
        valid_cert = store.get_valid_certificate("store-peer-004")
        
        assert valid_cert is not None
        assert valid_cert.serial_number == cert.serial_number

    def test_get_valid_certificate_skips_expired(self):
        """get_valid_certificate skips expired certificates."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        # Create and expire one certificate
        expired_cert = CertificateAuthority.create_self_signed("store-peer-005", signing_key)
        expired_cert.valid_until = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        # Create a valid certificate
        valid_cert = CertificateAuthority.create_self_signed("store-peer-005", signing_key)
        
        store.add_certificate(expired_cert)
        store.add_certificate(valid_cert)
        
        retrieved = store.get_valid_certificate("store-peer-005")
        
        assert retrieved is not None
        assert retrieved.serial_number == valid_cert.serial_number

    def test_revoke_certificate(self):
        """Certificates can be revoked."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("store-peer-006", signing_key)
        
        store.add_certificate(cert)
        result = store.revoke_certificate(cert.serial_number)
        
        assert result is True
        assert store.is_revoked(cert.serial_number) is True

    def test_revoke_nonexistent_certificate(self):
        """Revoking nonexistent certificate returns False."""
        store = IdentityStore()
        
        result = store.revoke_certificate("nonexistent-serial")
        
        assert result is False

    def test_get_valid_certificate_skips_revoked(self):
        """get_valid_certificate skips revoked certificates."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        
        cert1 = CertificateAuthority.create_self_signed("store-peer-007", signing_key)
        cert2 = CertificateAuthority.create_self_signed("store-peer-007", signing_key)
        
        store.add_certificate(cert1)
        store.add_certificate(cert2)
        
        # Revoke the first certificate
        store.revoke_certificate(cert1.serial_number)
        
        valid_cert = store.get_valid_certificate("store-peer-007")
        
        assert valid_cert is not None
        assert valid_cert.serial_number == cert2.serial_number

    def test_get_valid_certificate_returns_none_if_all_revoked(self):
        """get_valid_certificate returns None if all certificates are revoked."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("store-peer-008", signing_key)
        
        store.add_certificate(cert)
        store.revoke_certificate(cert.serial_number)
        
        valid_cert = store.get_valid_certificate("store-peer-008")
        
        assert valid_cert is None

    def test_list_all_certificates(self):
        """Can list all certificates in the store."""
        store = IdentityStore()
        
        sk1, vk1 = CryptoCore.generate_keypair()
        sk2, vk2 = CryptoCore.generate_keypair()
        
        cert1 = CertificateAuthority.create_self_signed("peer-a", sk1)
        cert2 = CertificateAuthority.create_self_signed("peer-b", sk2)
        
        store.add_certificate(cert1)
        store.add_certificate(cert2)
        
        all_certs = store.list_all_certificates()
        
        assert len(all_certs) == 2

    def test_list_all_identities(self):
        """Can list all identities in the store."""
        store = IdentityStore()
        
        sk1, vk1 = CryptoCore.generate_keypair()
        sk2, vk2 = CryptoCore.generate_keypair()
        
        cert1 = CertificateAuthority.create_self_signed("peer-c", sk1)
        cert2 = CertificateAuthority.create_self_signed("peer-d", sk2)
        
        store.add_certificate(cert1)
        store.add_certificate(cert2)
        
        all_identities = store.list_all_identities()
        
        assert len(all_identities) == 2

    def test_adding_certificate_also_stores_identity(self):
        """Adding a certificate also stores the associated identity."""
        store = IdentityStore()
        signing_key, verify_key = CryptoCore.generate_keypair()
        cert = CertificateAuthority.create_self_signed("store-peer-009", signing_key)
        
        store.add_certificate(cert)
        identity = store.get_identity("store-peer-009")
        
        assert identity is not None
        assert identity.peer_id == "store-peer-009"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
