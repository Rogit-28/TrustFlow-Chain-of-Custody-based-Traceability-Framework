import json
import hmac
import hashlib
from datetime import datetime
from typing import Optional

class WatermarkEngine:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode('utf-8')
        print("[WATERMARK] Watermarking Engine Initialized.")

    def embed_watermark(self, content: str, peer_id: str, depth: int, message_hash: str) -> str:
        """
        Embeds a signed metadata watermark into the text content.
        For this text-based simulation, we'll append it in a structured, visible way.
        """
        metadata = {
            "watermark_id": hashlib.sha256((peer_id + str(datetime.utcnow())).encode()).hexdigest(),
            "peer_id": peer_id,
            "timestamp": datetime.utcnow().isoformat(),
            "depth": depth,
            "message_hash": message_hash
        }

        metadata_str = json.dumps(metadata, sort_keys=True)
        signature = hmac.new(self.secret_key, metadata_str.encode('utf-8'), hashlib.sha256).hexdigest()

        # Append the watermark to the content in a readable format
        watermarked_content = (
            f"{content}\n"
            f"--- WATERMARK ---\n"
            f"DATA:{metadata_str}\n"
            f"SIG:{signature}\n"
            f"--- END WATERMARK ---"
        )
        print(f"[WATERMARK] Embedded watermark for Peer {peer_id[:8]}... in message {message_hash[:8]}...")
        return watermarked_content

    def extract_and_verify_watermark(self, watermarked_content: str) -> (Optional[str], Optional[dict]):
        """
        Extracts the watermark from the text and verifies its integrity.
        Returns the original content and the metadata if valid, otherwise None.
        """
        original_content = watermarked_content
        try:
            parts = watermarked_content.split("\n--- WATERMARK ---\n")
            if len(parts) != 2:
                # No watermark found, return original content
                return original_content, None

            original_content = parts[0]
            watermark_section = parts[1].split("\n--- END WATERMARK ---")[0]

            lines = watermark_section.strip().split('\n')
            if len(lines) != 2 or not lines[0].startswith("DATA:") or not lines[1].startswith("SIG:"):
                raise ValueError("Invalid watermark format")

            metadata_str = lines[0].replace("DATA:", "")
            received_sig = lines[1].replace("SIG:", "")

            # Verify the signature
            expected_sig = hmac.new(self.secret_key, metadata_str.encode('utf-8'), hashlib.sha256).hexdigest()

            if hmac.compare_digest(received_sig, expected_sig):
                metadata = json.loads(metadata_str)
                print(f"[WATERMARK] Extracted watermark is VALID. (Peer: {metadata['peer_id'][:8]}...)")
                return original_content, metadata
            else:
                print("[WATERMARK] Verification FAILED: Watermark signature is invalid.")
                return original_content, None
        except (ValueError, IndexError, json.JSONDecodeError):
            print("[WATERMARK] Verification FAILED: Malformed watermark.")
            return original_content, None

if __name__ == '__main__':
    # --- DEMONSTRATION ---
    engine = WatermarkEngine("a_very_secret_and_secure_key")

    # 1. Embed a watermark
    original_text = "This is a highly sensitive document."
    watermarked_doc = engine.embed_watermark(
        original_text,
        peer_id="peer-12345",
        chain_position=1,
        message_hash="abcde12345"
    )
    print("\n--- Watermarked Document ---\n" + watermarked_doc)

    # 2. Extract and verify the valid watermark
    print("\n--- Verifying a valid watermark ---")
    content, data = engine.extract_and_verify_watermark(watermarked_doc)
    if data:
        print("Original content:", content)
        print("Extracted data:", data)

    # 3. Tamper with the watermark and try to verify
    print("\n--- Verifying a tampered watermark ---")
    tampered_doc = watermarked_doc.replace("peer-12345", "peer-evil")
    content, data = engine.extract_and_verify_watermark(tampered_doc)
    if not data:
        print("Tampering correctly detected.")
