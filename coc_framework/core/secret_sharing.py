"""Shamir's Secret Sharing with HMAC authentication per share."""

import secrets
import hashlib
import hmac
import os
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass, asdict, field
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 256-bit prime for finite field arithmetic
PRIME = 2**256 - 189


@dataclass
class Share:
    """Single share with HMAC for integrity verification."""
    index: int
    value: str
    share_id: str
    content_hash: str
    threshold: int
    total_shares: int
    mac: str = ""
    is_hybrid: bool = False  # True when AES+Shamir hybrid encryption was used
    ciphertext: str = ""  # hex-encoded AES-GCM ciphertext (only set on hybrid shares)
    nonce: str = ""  # hex-encoded AES-GCM nonce (only set on hybrid shares)

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "Share":
        return Share(**data)


def _mod_inverse(a: int, p: int) -> int:
    def extended_gcd(a: int, b: int) -> Tuple[int, int, int]:
        if a == 0:
            return b, 0, 1
        gcd, x1, y1 = extended_gcd(b % a, a)
        x = y1 - (b // a) * x1
        y = x1
        return gcd, x, y

    _, x, _ = extended_gcd(a % p, p)
    return (x % p + p) % p


def _evaluate_polynomial(coefficients: List[int], x: int, prime: int) -> int:
    result = 0
    for i, coeff in enumerate(coefficients):
        result = (result + coeff * pow(x, i, prime)) % prime
    return result


def _lagrange_interpolation(shares: List[Tuple[int, int]], prime: int) -> int:
    secret = 0
    k = len(shares)

    for i in range(k):
        xi, yi = shares[i]
        numerator = 1
        denominator = 1

        for j in range(k):
            if i != j:
                xj = shares[j][0]
                numerator = (numerator * (-xj)) % prime
                denominator = (denominator * (xi - xj)) % prime

        lagrange_coeff = (numerator * _mod_inverse(denominator, prime)) % prime
        secret = (secret + yi * lagrange_coeff) % prime

    return secret


def _bytes_to_int(data: bytes) -> int:
    return int.from_bytes(data, byteorder='big')


def _int_to_bytes(num: int, length: int) -> bytes:
    return num.to_bytes(length, byteorder='big')


def _compute_share_mac(share_value: str, index: int, content_hash: str, hmac_key: bytes) -> str:
    data = f"{index}|{share_value}|{content_hash}".encode('utf-8')
    return hmac.new(hmac_key, data, hashlib.sha256).hexdigest()


def verify_share_mac(share: Share, hmac_key: bytes) -> bool:
    """Returns True if MAC is valid, False if tampered."""
    if not share.mac:
        return False
    expected_mac = _compute_share_mac(share.value, share.index, share.content_hash, hmac_key)
    return hmac.compare_digest(share.mac, expected_mac)


class ShareIntegrityError(Exception):
    pass


# ── Hybrid Encryption Helpers ────────────────────────────────────────────────
# For payloads > HYBRID_THRESHOLD_BYTES, we encrypt the content with AES-256-GCM
# and only split the 32-byte key via Shamir. This reduces polynomial count from
# O(content_size/31) to exactly 2 (32 bytes = 1 chunk + length header).

HYBRID_THRESHOLD_BYTES = 256


def _aes_encrypt(content_bytes: bytes) -> Tuple[bytes, bytes, bytes]:
    """Encrypt content with AES-256-GCM. Returns (key, nonce, ciphertext)."""
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, content_bytes, None)
    return key, nonce, ciphertext


def _aes_decrypt(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """Decrypt AES-256-GCM ciphertext."""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def split_secret(content: str, threshold: int, num_shares: int) -> Tuple[List[Share], bytes]:
    """Split content into shares. Returns (shares, hmac_key).
    
    For content > HYBRID_THRESHOLD_BYTES, uses hybrid encryption:
    AES-256-GCM encrypts the content, then only the 32-byte AES key
    is split via Shamir. This drastically reduces overhead for large payloads.
    """
    if threshold > num_shares:
        raise ValueError(f"Threshold ({threshold}) cannot exceed number of shares ({num_shares})")
    if threshold < 2:
        raise ValueError("Threshold must be at least 2")
    if num_shares < 2:
        raise ValueError("Must create at least 2 shares")

    hmac_key = secrets.token_bytes(32)
    content_bytes = content.encode('utf-8')
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    use_hybrid = len(content_bytes) > HYBRID_THRESHOLD_BYTES

    if use_hybrid:
        # Hybrid path: AES encrypt content, Shamir split only the key
        aes_key, aes_nonce, ciphertext = _aes_encrypt(content_bytes)
        secret_bytes = aes_key  # 32 bytes — fits in ~2 Shamir chunks
    else:
        # Direct path: Shamir split the content itself
        secret_bytes = content_bytes
        aes_nonce = b''
        ciphertext = b''

    chunks = _split_into_chunks(secret_bytes)
    
    all_shares_data: List[List[Tuple[int, int]]] = []

    for chunk in chunks:
        secret = _bytes_to_int(chunk)
        coefficients = [secret]  # a_0 = secret, rest are random
        for _ in range(threshold - 1):
            coefficients.append(secrets.randbelow(PRIME))

        chunk_shares = []
        for x in range(1, num_shares + 1):
            y = _evaluate_polynomial(coefficients, x, PRIME)
            chunk_shares.append((x, y))

        all_shares_data.append(chunk_shares)

    share_id_base = secrets.token_hex(8)
    shares = []

    for i in range(num_shares):
        combined_value = "|".join(hex(all_shares_data[chunk_idx][i][1]) 
                                   for chunk_idx in range(len(chunks)))
        mac = _compute_share_mac(combined_value, i + 1, content_hash, hmac_key)
        
        share = Share(
            index=i + 1,
            value=combined_value,
            share_id=f"{share_id_base}_{i+1}",
            content_hash=content_hash,
            threshold=threshold,
            total_shares=num_shares,
            mac=mac,
            is_hybrid=use_hybrid,
            ciphertext=ciphertext.hex() if use_hybrid else "",
            nonce=aes_nonce.hex() if use_hybrid else "",
        )
        shares.append(share)

    return shares, hmac_key


def _split_into_chunks(data: bytes, chunk_size: int = 31) -> List[bytes]:
    """Split data into 31-byte chunks (fits within 256-bit prime field)."""
    chunks = []
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk + b'\x00' * (chunk_size - len(chunk))
        chunks.append(chunk)
    
    # Prepend length header
    length_header = len(data).to_bytes(4, byteorder='big')
    chunks.insert(0, length_header + b'\x00' * (chunk_size - 4))
    return chunks


def reconstruct_secret(shares: List[Share], hmac_key: Optional[bytes] = None) -> Optional[str]:
    """Reconstruct content from shares. Raises ShareIntegrityError if HMAC fails.
    
    Handles both direct and hybrid (AES+Shamir) shares transparently.
    """
    if not shares:
        raise ValueError("No shares provided")

    threshold = shares[0].threshold
    content_hash = shares[0].content_hash
    is_hybrid = shares[0].is_hybrid

    if len(shares) < threshold:
        raise ValueError(f"Need at least {threshold} shares, got {len(shares)}")

    for share in shares:
        if share.content_hash != content_hash:
            raise ValueError("Shares are from different secrets")
        if share.threshold != threshold:
            raise ValueError("Shares have inconsistent threshold values")
        if share.is_hybrid != is_hybrid:
            raise ValueError("Shares have inconsistent hybrid flags")
        if hmac_key is not None and not verify_share_mac(share, hmac_key):
            raise ShareIntegrityError(
                f"Share {share.share_id} failed integrity verification (possible tampering)"
            )

    num_chunks = len(shares[0].value.split("|"))
    reconstructed_chunks = []
    
    for chunk_idx in range(num_chunks):
        chunk_shares = []
        for share in shares[:threshold]:
            chunk_values = share.value.split("|")
            y = int(chunk_values[chunk_idx], 16)
            chunk_shares.append((share.index, y))
        secret_int = _lagrange_interpolation(chunk_shares, PRIME)
        chunk_bytes = _int_to_bytes(secret_int, 31)
        reconstructed_chunks.append(chunk_bytes)

    length_chunk = reconstructed_chunks[0]
    original_length = int.from_bytes(length_chunk[:4], byteorder='big')
    combined = b''.join(reconstructed_chunks[1:])
    secret_bytes = combined[:original_length]

    if is_hybrid:
        # Hybrid path: secret_bytes is the AES key, decrypt the ciphertext
        aes_key = secret_bytes
        ciphertext = bytes.fromhex(shares[0].ciphertext)
        nonce = bytes.fromhex(shares[0].nonce)
        try:
            content_bytes = _aes_decrypt(aes_key, nonce, ciphertext)
        except Exception:
            return None
    else:
        # Direct path: secret_bytes is the content itself
        content_bytes = secret_bytes

    try:
        content = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return None

    if hashlib.sha256(content_bytes).hexdigest() != content_hash:
        return None

    return content


def verify_share(share: Share, content_hash: str) -> bool:
    return share.content_hash == content_hash


class SecretSharingEngine:
    """High-level interface with HMAC key storage and authorization tracking."""

    def __init__(self, default_threshold: int = 3, default_shares: int = 5):
        self.default_threshold = default_threshold
        self.default_shares = default_shares
        self._share_registry: Dict[str, List[str]] = {}  # content_hash -> [peer_ids]
        self._hmac_keys: Dict[str, bytes] = {}  # content_hash -> hmac_key
        self._authorized_recipients: Dict[str, Set[str]] = {}  # content_hash -> {peer_ids}
        self._thresholds: Dict[str, int] = {}  # content_hash -> threshold

    def split_content(
        self,
        content: str,
        recipient_ids: List[str],
        threshold: Optional[int] = None
    ) -> Dict[str, Share]:
        """Split content and assign shares to recipients. Returns {peer_id: Share}."""
        num_shares = len(recipient_ids)
        if threshold is None:
            threshold = max(2, num_shares // 2 + 1)

        if num_shares < 2:
            raise ValueError("Need at least 2 recipients for secret sharing")

        shares, hmac_key = split_secret(content, threshold, num_shares)
        share_map = {peer_id: shares[i] for i, peer_id in enumerate(recipient_ids)}

        content_hash = shares[0].content_hash
        self._share_registry[content_hash] = recipient_ids.copy()
        self._hmac_keys[content_hash] = hmac_key
        self._authorized_recipients[content_hash] = set(recipient_ids)
        self._thresholds[content_hash] = threshold
        return share_map

    def reconstruct_content(self, shares: List[Share], verify_integrity: bool = True) -> Optional[str]:
        """Reconstruct content. Raises ShareIntegrityError if integrity check fails."""
        if not shares:
            return None
        
        content_hash = shares[0].content_hash
        hmac_key = self._hmac_keys.get(content_hash) if verify_integrity else None
        
        return reconstruct_secret(shares, hmac_key)

    def get_share_holders(self, content_hash: str) -> List[str]:
        return self._share_registry.get(content_hash, [])

    def get_hmac_key(self, content_hash: str) -> Optional[bytes]:
        return self._hmac_keys.get(content_hash)

    def is_authorized(self, content_hash: str, peer_id: str) -> bool:
        return peer_id in self._authorized_recipients.get(content_hash, set())

    def add_authorized_recipient(self, content_hash: str, peer_id: str) -> None:
        if content_hash not in self._authorized_recipients:
            self._authorized_recipients[content_hash] = set()
        self._authorized_recipients[content_hash].add(peer_id)

    def remove_authorized_recipient(self, content_hash: str, peer_id: str) -> None:
        if content_hash in self._authorized_recipients:
            self._authorized_recipients[content_hash].discard(peer_id)

    def can_reconstruct(self, content_hash: str, available_peers: Optional[List[str]] = None) -> bool:
        """Check if enough holders are available to meet the threshold."""
        holders = self._share_registry.get(content_hash, [])
        threshold = self._thresholds.get(content_hash, self.default_threshold)
        if available_peers is not None:
            available_holders = [p for p in holders if p in available_peers]
        else:
            available_holders = holders
        return len(available_holders) >= threshold

    def get_threshold(self, content_hash: str) -> int:
        return self._thresholds.get(content_hash, self.default_threshold)

