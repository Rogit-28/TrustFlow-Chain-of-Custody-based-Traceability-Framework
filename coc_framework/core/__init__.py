"""
TrustFlow Core Module

Core components for the Chain of Custody privacy framework.
"""

from .coc_node import CoCNode, SignatureVerificationError
from .crypto_core import CryptoCore
from .audit_log import AuditLog
from .deletion_engine import DeletionEngine
from .network_sim import Peer, Network

# Additional modules (if they exist and export these)
try:
    from .audit_log import (
        AuditLogger,
        AuditEvent,
        AuditEventType,
        TamperEvidentLog,
        LogEntry,
    )
except ImportError:
    AuditLogger = None
    AuditEvent = None
    AuditEventType = None
    TamperEvidentLog = None
    LogEntry = None

try:
    from .deletion_engine import DeletionToken, DeletionReceipt, DeletionTracker
except ImportError:
    DeletionToken = None
    DeletionReceipt = None
    DeletionTracker = None

try:
    from .secret_sharing import SecretSharingEngine, Share
except ImportError:
    SecretSharingEngine = None
    Share = None

try:
    from .timelock import TimeLockEngine, EncryptedContent, TimeLockStatus
except ImportError:
    TimeLockEngine = None
    EncryptedContent = None
    TimeLockStatus = None

try:
    from .steganography import SteganoEngine, WatermarkData, ExtractionResult
except ImportError:
    SteganoEngine = None
    WatermarkData = None
    ExtractionResult = None

try:
    from .identity import Identity, Certificate, CertificateAuthority, IdentityStore
except ImportError:
    Identity = None
    Certificate = None
    CertificateAuthority = None
    IdentityStore = None

try:
    from .validation import (
        ValidationError,
        ValidationResult,
        EventValidator,
        validate_peer_id,
        validate_content_hash,
        validate_timestamp,
        validate_signature_hex,
        validate_public_key_hex,
    )
except ImportError:
    ValidationError = None
    ValidationResult = None
    EventValidator = None
    validate_peer_id = None
    validate_content_hash = None
    validate_timestamp = None
    validate_signature_hex = None
    validate_public_key_hex = None

# Structured logging
from .logging import (
    StructuredLogger,
    JSONFormatter,
    LogLevel,
    Component,
    get_logger,
    peer_logger,
    network_logger,
    coordinator_logger,
    gossip_logger,
    deletion_logger,
    audit_logger,
    crypto_logger,
    storage_logger,
    configure_logging,
    silence_logging,
    restore_logging,
)

__all__ = [
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
    # Structured logging
    "StructuredLogger",
    "JSONFormatter",
    "LogLevel",
    "Component",
    "get_logger",
    "peer_logger",
    "network_logger",
    "coordinator_logger",
    "gossip_logger",
    "deletion_logger",
    "audit_logger",
    "crypto_logger",
    "storage_logger",
    "configure_logging",
    "silence_logging",
    "restore_logging",
]
