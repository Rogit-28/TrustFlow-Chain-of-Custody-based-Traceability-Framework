import hashlib
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder

class CryptoCore:
    @staticmethod
    def generate_keypair():
        """Generates an Ed25519 keypair for signing."""
        signing_key = SigningKey.generate()
        return signing_key, signing_key.verify_key

    @staticmethod
    def sign_message(signing_key: SigningKey, message: str) -> bytes:
        """Signs a message with the given signing key."""
        return signing_key.sign(message.encode('utf-8')).signature

    @staticmethod
    def verify_signature(verify_key: VerifyKey, message: str, signature: bytes) -> bool:
        """Verifies a signature with the given verification key."""
        try:
            verify_key.verify(message.encode('utf-8'), signature)
            return True
        except Exception:
            return False

    @staticmethod
    def hash_content(content: str) -> str:
        """Creates a SHA-256 hash of the given content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

if __name__ == '__main__':
    # --- DEMONSTRATION ---
    crypto = CryptoCore()

    # 1. Key Generation
    sk, vk = crypto.generate_keypair()
    print(f"Generated Signing Key (private): {sk.encode(encoder=HexEncoder).decode('utf-8')[:12]}...")
    print(f"Generated Verify Key (public):  {vk.encode(encoder=HexEncoder).decode('utf-8')[:12]}...")

    # 2. Hashing
    message_content = "This is a secret message for the CoC simulation."
    message_hash = crypto.hash_content(message_content)
    print(f"\nMessage Content: '{message_content}'")
    print(f"Message Hash: {message_hash}")

    # 3. Signing and Verification
    signed = crypto.sign_message(sk, message_hash)
    is_valid = crypto.verify_signature(vk, signed)
    print(f"\nSignature: {signed.hex()[:24]}...")
    print(f"Signature is valid: {is_valid}")

    # 4. Tampering Demo
    tampered_signed_message = signed[:-1] + b'X' # Alter the signature
    is_tampered_valid = crypto.verify_signature(vk, tampered_signed_message)
    print(f"\nTampered signature is valid: {is_tampered_valid}")
