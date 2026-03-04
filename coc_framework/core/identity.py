"""
PKI/Identity module for TrustFlow Chain of Custody framework.

Provides identity certificates that bind peer_id to public key,
certificate chains for trust hierarchy, and certificate validation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from nacl.signing import SigningKey, VerifyKey

from .crypto_core import CryptoCore


@dataclass(slots=True)
class Identity:
    """Represents a peer's identity with crypto keys."""
    
    peer_id: str
    public_key: bytes  # VerifyKey.encode()
    created_at: str
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Serialize identity to dictionary."""
        return {
            "peer_id": self.peer_id,
            "public_key": self.public_key.hex(),
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> Identity:
        """Deserialize identity from dictionary."""
        return Identity(
            peer_id=data["peer_id"],
            public_key=bytes.fromhex(data["public_key"]),
            created_at=data["created_at"],
            metadata=data.get("metadata", {}),
        )
    
    def get_verify_key(self) -> VerifyKey:
        """Get the VerifyKey object from stored public key bytes."""
        return VerifyKey(self.public_key)
    
    @staticmethod
    def create(peer_id: str, verify_key: VerifyKey, metadata: Optional[Dict[str, str]] = None) -> Identity:
        """Create a new Identity from a peer_id and verify key."""
        return Identity(
            peer_id=peer_id,
            public_key=bytes(verify_key),
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(slots=True)
class Certificate:
    """Self-signed or CA-signed certificate binding identity to public key."""
    
    identity: Identity
    issuer_id: str  # "self" for self-signed, or CA's peer_id
    valid_from: str  # ISO timestamp
    valid_until: str  # ISO timestamp
    signature: str  # Hex-encoded signature
    serial_number: str  # UUID
    
    def to_dict(self) -> Dict:
        """Serialize certificate to dictionary."""
        return {
            "identity": self.identity.to_dict(),
            "issuer_id": self.issuer_id,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "signature": self.signature,
            "serial_number": self.serial_number,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> Certificate:
        """Deserialize certificate from dictionary."""
        return Certificate(
            identity=Identity.from_dict(data["identity"]),
            issuer_id=data["issuer_id"],
            valid_from=data["valid_from"],
            valid_until=data["valid_until"],
            signature=data["signature"],
            serial_number=data["serial_number"],
        )
    
    def is_expired(self) -> bool:
        """Check if the certificate has expired."""
        now = datetime.now(timezone.utc)
        valid_until = datetime.fromisoformat(self.valid_until)
        return now > valid_until
    
    def is_not_yet_valid(self) -> bool:
        """Check if the certificate is not yet valid."""
        now = datetime.now(timezone.utc)
        valid_from = datetime.fromisoformat(self.valid_from)
        return now < valid_from
    
    def is_valid_time(self) -> bool:
        """Check if current time is within validity period.
        
        Optimized to parse timestamps only once.
        """
        now = datetime.now(timezone.utc)
        valid_from = datetime.fromisoformat(self.valid_from)
        valid_until = datetime.fromisoformat(self.valid_until)
        return valid_from <= now <= valid_until
    
    def is_self_signed(self) -> bool:
        """Check if the certificate is self-signed."""
        return self.issuer_id == "self"
    
    def get_signed_data(self) -> str:
        """Get canonical string representation of data to sign.
        
        Returns a deterministic JSON string containing all certificate
        fields except the signature itself.
        """
        data = {
            "identity": self.identity.to_dict(),
            "issuer_id": self.issuer_id,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "serial_number": self.serial_number,
        }
        # Use sort_keys=True for deterministic output
        return json.dumps(data, sort_keys=True, separators=(",", ":"))


class CertificateAuthority:
    """Issues and validates certificates."""
    
    def __init__(self, ca_identity: Identity, signing_key: SigningKey):
        """Initialize the Certificate Authority.
        
        Args:
            ca_identity: The identity of the CA itself
            signing_key: The CA's private signing key
        """
        self._identity = ca_identity
        self._signing_key = signing_key
        # Cache for certificate validation results: serial_number -> (is_valid, validation_time)
        self._validation_cache: Dict[str, tuple] = {}
        # Cache TTL in seconds (re-validate after this time)
        self._cache_ttl_seconds = 60.0
    
    @property
    def identity(self) -> Identity:
        """Get the CA's identity."""
        return self._identity
    
    @property
    def peer_id(self) -> str:
        """Get the CA's peer_id."""
        return self._identity.peer_id
    
    def _get_cached_validation(self, serial_number: str) -> Optional[bool]:
        """Get cached validation result if still valid.
        
        Args:
            serial_number: The certificate serial number to look up.
            
        Returns:
            Cached validation result or None if not cached/expired.
        """
        if serial_number in self._validation_cache:
            is_valid, validation_time = self._validation_cache[serial_number]
            now = datetime.now(timezone.utc)
            if (now - validation_time).total_seconds() < self._cache_ttl_seconds:
                return is_valid
            # Cache entry expired, remove it
            del self._validation_cache[serial_number]
        return None
    
    def _cache_validation_result(self, serial_number: str, is_valid: bool) -> None:
        """Cache a validation result.
        
        Args:
            serial_number: The certificate serial number.
            is_valid: The validation result.
        """
        self._validation_cache[serial_number] = (is_valid, datetime.now(timezone.utc))
    
    def invalidate_cache(self, serial_number: Optional[str] = None) -> None:
        """Invalidate validation cache.
        
        Args:
            serial_number: If provided, only invalidate this certificate.
                          If None, clear entire cache.
        """
        if serial_number is None:
            self._validation_cache.clear()
        elif serial_number in self._validation_cache:
            del self._validation_cache[serial_number]
    
    def issue_certificate(self, identity: Identity, validity_days: int = 365) -> Certificate:
        """Issue a certificate for the given identity.
        
        Args:
            identity: The identity to certify
            validity_days: Number of days the certificate is valid
            
        Returns:
            A signed Certificate
        """
        now = datetime.now(timezone.utc)
        valid_from = now.isoformat()
        valid_until = (now + timedelta(days=validity_days)).isoformat()
        serial_number = str(uuid.uuid4())
        
        # Create certificate without signature first
        cert = Certificate(
            identity=identity,
            issuer_id=self._identity.peer_id,
            valid_from=valid_from,
            valid_until=valid_until,
            signature="",
            serial_number=serial_number,
        )
        
        # Sign the canonical data
        signed_data = cert.get_signed_data()
        signature_bytes = CryptoCore.sign_message(self._signing_key, signed_data)
        cert.signature = signature_bytes.hex()
        
        return cert
    
    def verify_certificate(self, cert: Certificate) -> bool:
        """Verify certificate signature and expiration.
        
        For CA-issued certificates (where issuer_id matches this CA),
        verifies the signature using the CA's public key.
        
        For self-signed certificates, verifies the signature using
        the certificate's own public key.
        
        Uses caching to avoid repeated signature verification for
        the same certificate within a short time window.
        
        Args:
            cert: The certificate to verify
            
        Returns:
            True if signature is valid and certificate is not expired
        """
        # Check cache first
        cached_result = self._get_cached_validation(cert.serial_number)
        if cached_result is not None:
            # Still need to verify time validity (can change)
            if not cert.is_valid_time():
                return False
            return cached_result
        
        # Check time validity
        if not cert.is_valid_time():
            self._cache_validation_result(cert.serial_number, False)
            return False
        
        # Get the verify key based on issuer
        if cert.is_self_signed():
            verify_key = cert.identity.get_verify_key()
        elif cert.issuer_id == self._identity.peer_id:
            verify_key = self._identity.get_verify_key()
        else:
            # Certificate was issued by a different CA
            self._cache_validation_result(cert.serial_number, False)
            return False
        
        # Verify signature
        try:
            signature_bytes = bytes.fromhex(cert.signature)
            signed_data = cert.get_signed_data()
            result = CryptoCore.verify_signature(verify_key, signed_data, signature_bytes)
            self._cache_validation_result(cert.serial_number, result)
            return result
        except Exception:
            self._cache_validation_result(cert.serial_number, False)
            return False
    
    @staticmethod
    def create_self_signed(
        peer_id: str,
        signing_key: SigningKey,
        validity_days: int = 365,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Certificate:
        """Create a self-signed certificate.
        
        Args:
            peer_id: The peer's identifier
            signing_key: The peer's private signing key
            validity_days: Number of days the certificate is valid
            metadata: Optional metadata for the identity
            
        Returns:
            A self-signed Certificate
        """
        # Create identity from signing key
        verify_key = signing_key.verify_key
        identity = Identity.create(peer_id, verify_key, metadata)
        
        now = datetime.now(timezone.utc)
        valid_from = now.isoformat()
        valid_until = (now + timedelta(days=validity_days)).isoformat()
        serial_number = str(uuid.uuid4())
        
        # Create certificate without signature first
        cert = Certificate(
            identity=identity,
            issuer_id="self",
            valid_from=valid_from,
            valid_until=valid_until,
            signature="",
            serial_number=serial_number,
        )
        
        # Sign with the peer's own key
        signed_data = cert.get_signed_data()
        signature_bytes = CryptoCore.sign_message(signing_key, signed_data)
        cert.signature = signature_bytes.hex()
        
        return cert
    
    @staticmethod
    def verify_self_signed(cert: Certificate) -> bool:
        """Verify a self-signed certificate.
        
        Args:
            cert: The self-signed certificate to verify
            
        Returns:
            True if certificate is self-signed, signature is valid, and not expired
        """
        if not cert.is_self_signed():
            return False
        
        if not cert.is_valid_time():
            return False
        
        try:
            verify_key = cert.identity.get_verify_key()
            signature_bytes = bytes.fromhex(cert.signature)
            signed_data = cert.get_signed_data()
            return CryptoCore.verify_signature(verify_key, signed_data, signature_bytes)
        except Exception:
            return False


class IdentityStore:
    """Storage for identities and certificates."""
    
    def __init__(self):
        """Initialize the identity store."""
        self._identities: Dict[str, Identity] = {}
        self._certificates: Dict[str, Certificate] = {}  # serial_number -> cert
        self._peer_certs: Dict[str, Set[str]] = {}  # peer_id -> set of serial_numbers (O(1) lookup)
        self._revoked: Set[str] = set()  # Set of revoked serial numbers
    
    def add_identity(self, identity: Identity) -> None:
        """Add an identity to the store.
        
        Args:
            identity: The identity to store
        """
        self._identities[identity.peer_id] = identity
    
    def get_identity(self, peer_id: str) -> Optional[Identity]:
        """Get an identity by peer_id.
        
        Args:
            peer_id: The peer's identifier
            
        Returns:
            The Identity if found, None otherwise
        """
        return self._identities.get(peer_id)
    
    def add_certificate(self, cert: Certificate) -> None:
        """Add a certificate to the store.
        
        Args:
            cert: The certificate to store
        """
        serial = cert.serial_number
        peer_id = cert.identity.peer_id
        
        self._certificates[serial] = cert
        
        if peer_id not in self._peer_certs:
            self._peer_certs[peer_id] = set()
        
        self._peer_certs[peer_id].add(serial)
        
        # Also store the identity
        self.add_identity(cert.identity)
    
    def get_certificate(self, serial_number: str) -> Optional[Certificate]:
        """Get a certificate by serial number.
        
        Args:
            serial_number: The certificate's serial number
            
        Returns:
            The Certificate if found, None otherwise
        """
        return self._certificates.get(serial_number)
    
    def get_certificates_for_peer(self, peer_id: str) -> List[Certificate]:
        """Get all certificates for a peer.
        
        Args:
            peer_id: The peer's identifier
            
        Returns:
            List of all certificates for the peer
        """
        serial_numbers = self._peer_certs.get(peer_id, set())
        return [self._certificates[sn] for sn in serial_numbers if sn in self._certificates]
    
    def get_valid_certificate(self, peer_id: str) -> Optional[Certificate]:
        """Get a valid (non-expired, non-revoked) certificate for a peer.
        
        Args:
            peer_id: The peer's identifier
            
        Returns:
            A valid Certificate if found, None otherwise
        """
        serial_numbers = self._peer_certs.get(peer_id, set())
        
        for sn in serial_numbers:
            if sn not in self._revoked:
                cert = self._certificates.get(sn)
                if cert is not None and cert.is_valid_time():
                    return cert
        
        return None
    
    def revoke_certificate(self, serial_number: str) -> bool:
        """Revoke a certificate by serial number.
        
        Args:
            serial_number: The serial number of the certificate to revoke
            
        Returns:
            True if certificate was found and revoked, False otherwise
        """
        if serial_number in self._certificates:
            self._revoked.add(serial_number)
            return True
        return False
    
    def is_revoked(self, serial_number: str) -> bool:
        """Check if a certificate is revoked.
        
        Args:
            serial_number: The serial number to check
            
        Returns:
            True if revoked, False otherwise
        """
        return serial_number in self._revoked
    
    def list_all_certificates(self) -> List[Certificate]:
        """Get all certificates in the store.
        
        Returns:
            List of all certificates
        """
        return list(self._certificates.values())
    
    def list_all_identities(self) -> List[Identity]:
        """Get all identities in the store.
        
        Returns:
            List of all identities
        """
        return list(self._identities.values())
