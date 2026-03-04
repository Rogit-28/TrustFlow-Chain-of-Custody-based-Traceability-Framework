"""
TrustFlow - Chain of Custody Privacy Framework

A Python-based framework for decentralized privacy and trust in P2P networks
with message provenance tracking, secure deletion propagation, cryptographic 
signatures, and steganographic watermarking for leak attribution.
"""

from .__version__ import VERSION

# Simulation engine
from .simulation_engine import SimulationEngine

# Configuration
from .config import (
    SimulationSettings,
    ScenarioConfig,
)

# Core module exports
from .core import (
    # CoC Node
    CoCNode,
    SignatureVerificationError,
    # Cryptography
    CryptoCore,
    # Audit logging
    AuditLog,
    AuditLogger,
    AuditEvent,
    AuditEventType,
    TamperEvidentLog,
    LogEntry,
    # Deletion
    DeletionEngine,
    DeletionToken,
    DeletionReceipt,
    DeletionTracker,
    # Network simulation
    Peer,
    Network,
    # Secret sharing
    SecretSharingEngine,
    Share,
    # Timelock
    TimeLockEngine,
    EncryptedContent,
    TimeLockStatus,
    # Steganography
    SteganoEngine,
    WatermarkData,
    ExtractionResult,
    # Identity/PKI
    Identity,
    Certificate,
    CertificateAuthority,
    IdentityStore,
    # Validation
    ValidationError,
    ValidationResult,
    EventValidator,
    validate_peer_id,
    validate_content_hash,
    validate_timestamp,
    validate_signature_hex,
    validate_public_key_hex,
)

# Interface exports
from .interfaces import (
    # Storage
    StorageBackend,
    InMemoryStorage,
    SQLiteStorage,
    # Notifications
    NotificationHandler,
    SilentNotificationHandler,
    LoggingNotificationHandler,
    # Peer Discovery
    PeerDiscovery,
    RegistryPeerDiscovery,
    # Transfer Monitor
    TransferMonitor,
    NullTransferMonitor,
    # Encryption Policy
    EncryptionPolicy,
    NoEncryption,
)

__all__ = [
    # Version
    "VERSION",
    # Simulation
    "SimulationEngine",
    # Configuration
    "SimulationSettings",
    "ScenarioConfig",
    # Core classes
    "CoCNode",
    "SignatureVerificationError",
    "CryptoCore",
    # Audit logging
    "AuditLog",
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "TamperEvidentLog",
    "LogEntry",
    # Deletion
    "DeletionEngine",
    "DeletionToken",
    "DeletionReceipt",
    "DeletionTracker",
    # Network simulation
    "Peer",
    "Network",
    # Secret sharing
    "SecretSharingEngine",
    "Share",
    # Timelock
    "TimeLockEngine",
    "EncryptedContent",
    "TimeLockStatus",
    # Steganography
    "SteganoEngine",
    "WatermarkData",
    "ExtractionResult",
    # Identity/PKI
    "Identity",
    "Certificate",
    "CertificateAuthority",
    "IdentityStore",
    # Validation
    "ValidationError",
    "ValidationResult",
    "EventValidator",
    "validate_peer_id",
    "validate_content_hash",
    "validate_timestamp",
    "validate_signature_hex",
    "validate_public_key_hex",
    # Storage
    "StorageBackend",
    "InMemoryStorage",
    "SQLiteStorage",
    # Notifications
    "NotificationHandler",
    "SilentNotificationHandler",
    "LoggingNotificationHandler",
    # Peer Discovery
    "PeerDiscovery",
    "RegistryPeerDiscovery",
    # Transfer Monitor
    "TransferMonitor",
    "NullTransferMonitor",
    # Encryption Policy
    "EncryptionPolicy",
    "NoEncryption",
]
