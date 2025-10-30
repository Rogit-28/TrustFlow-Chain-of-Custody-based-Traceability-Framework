import unittest
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from coc_framework.core.watermark_engine import WatermarkEngine
from coc_framework.simulation_engine import SimulationEngine
from coc_framework.core.network_sim import Peer
from coc_framework.core.crypto_core import CryptoCore

class TestWatermarkIntegration(unittest.TestCase):

    def setUp(self):
        self.watermark_engine = WatermarkEngine("test_secret")

    def test_watermark_embedding(self):
        content = "test_content"
        watermarked_content = self.watermark_engine.embed_watermark(content, "peer1", 0, "hash1")
        self.assertNotEqual(content, watermarked_content)
        self.assertIn("WATERMARK", watermarked_content)

    def test_watermark_extraction_and_verification(self):
        content = "test_content"
        watermarked_content = self.watermark_engine.embed_watermark(content, "peer1", 0, "hash1")
        extracted_content, metadata = self.watermark_engine.extract_and_verify_watermark(watermarked_content)
        self.assertEqual(content, extracted_content)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["peer_id"], "peer1")

    def test_watermark_tampering(self):
        content = "test_content"
        watermarked_content = self.watermark_engine.embed_watermark(content, "peer1", 0, "hash1")
        tampered_content = watermarked_content.replace("peer1", "peer2")
        extracted_content, metadata = self.watermark_engine.extract_and_verify_watermark(tampered_content)
        # The extracted content should be the original content, but the metadata will be None
        self.assertEqual(content, extracted_content)
        self.assertIsNone(metadata)

    def test_watermark_disabled(self):
        async def run_test():
            scenario = {
                "settings": {"total_peers": 2},
                "events": [
                    {
                        "time": 0,
                        "type": "SET_PEER_SETTINGS",
                        "peer_idx": 0,
                        "settings": {"watermark_enabled": False}
                    },
                    {
                        "time": 1,
                        "type": "CREATE_MESSAGE",
                        "originator_idx": 0,
                        "recipient_indices": [1],
                        "content": "test_content",
                        "message_id": "msg1"
                    }
                ]
            }

            sim_engine = SimulationEngine(scenario)
            await sim_engine.tick() # Process SET_PEER_SETTINGS
            await sim_engine.tick() # Process CREATE_MESSAGE

            # We need to find the node in the recipient's storage.
            # Since we don't have a direct way to get the node by message_id,
            # we'll just check all the content in the recipient's storage.
            recipient_id = list(sim_engine.peers.keys())[1]
            recipient = sim_engine.peers[recipient_id]
            all_content = [
                recipient.storage.get_content(node.content_hash)
                for node in recipient.storage.get_all_nodes()
            ]

            # Check that none of the stored content contains a watermark
            for content in all_content:
                self.assertNotIn("WATERMARK", content)

        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
