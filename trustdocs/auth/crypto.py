"""Cryptographic utilities for authentication.

Implements:
- Argon2id key derivation for password → wrapping key
- AES-256-GCM encryption/decryption of Ed25519 signing keys
- Ed25519 keypair generation via TrustFlow's CryptoCore
- Password hashing via bcrypt
"""

import os
import secrets
import bcrypt
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from coc_framework.core.crypto_core import CryptoCore
from trustdocs.config import config


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def derive_wrapping_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit wrapping key from password using Argon2id.

    Parameters match PRD Section 5.1:
    - time_cost=2, memory_cost=65536 (64MB), parallelism=2
    """
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=config.argon2_time_cost,
        memory_cost=config.argon2_memory_cost,
        parallelism=config.argon2_parallelism,
        hash_len=32,
        type=Type.ID,
    )


def encrypt_signing_key(signing_key_bytes: bytes, password: str) -> bytes:
    """Encrypt an Ed25519 signing key with AES-256-GCM using an Argon2id-derived key.

    Returns: salt (16) + nonce (12) + ciphertext (variable)
    The server stores this blob — it never holds the plaintext signing key
    beyond the duration of the registration request.
    """
    salt = os.urandom(16)
    nonce = os.urandom(12)
    wrapping_key = derive_wrapping_key(password, salt)
    aesgcm = AESGCM(wrapping_key)
    ciphertext = aesgcm.encrypt(nonce, signing_key_bytes, None)
    return salt + nonce + ciphertext


def decrypt_signing_key(encrypted_blob: bytes, password: str) -> bytes:
    """Decrypt an Ed25519 signing key from the stored blob.

    Raises cryptography.exceptions.InvalidTag if password is wrong.
    """
    salt = encrypted_blob[:16]
    nonce = encrypted_blob[16:28]
    ciphertext = encrypted_blob[28:]
    wrapping_key = derive_wrapping_key(password, salt)
    aesgcm = AESGCM(wrapping_key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def generate_keypair():
    """Generate an Ed25519 keypair via TrustFlow's CryptoCore.

    Returns: (signing_key, verify_key)
    - signing_key: nacl.signing.SigningKey
    - verify_key: nacl.signing.VerifyKey
    """
    return CryptoCore.generate_keypair()


def generate_session_token() -> str:
    """Generate a 32-byte cryptographically random session token."""
    return secrets.token_hex(32)


def hash_session_token(token: str) -> str:
    """SHA-256 hash of the session token for server-side storage."""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
