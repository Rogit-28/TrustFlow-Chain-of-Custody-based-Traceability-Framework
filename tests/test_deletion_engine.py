import unittest
from unittest.mock import MagicMock
import sys
import os
import asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from coc_framework.core.network_sim import Peer
from coc_framework.simulation_engine import SimulationEngine
from coc_framework.core.crypto_core import CryptoCore

class TestDeletionLogic(unittest.TestCase):
    def test_loop_safe_deletion_propagation(self):
        async def run_test():
            # Setup: Create a scenario with a communication loop (A->B->C->A)
            scenario = {
                "settings": {"total_peers": 3},
                "events": [
                    {
                        "time": 1, "type": "CREATE_MESSAGE", "originator_idx": 0, "recipient_indices": [1],
                        "content": "Loop message", "message_id": "msg_loop_1"
                    },
                    {
                        "time": 2, "type": "FORWARD_MESSAGE", "sender_idx": 1, "recipient_indices": [2],
                        "parent_message_id": "msg_loop_1", "forwarded_message_id": "msg_loop_2"
                    },
                    {
                        "time": 3, "type": "FORWARD_MESSAGE", "sender_idx": 2, "recipient_indices": [0],
                        "parent_message_id": "msg_loop_2", "forwarded_message_id": "msg_loop_3"
                    },
                    {
                    "time": 4, "type": "DELETE_MESSAGE", "originator_id": "peer_0", "node_hash": "msg_loop_1"
                    }
                ]
            }

            # --- Act ---
            # Initialize and run the simulation
            engine = SimulationEngine(scenario)

            # Run the simulation until the deletion event
            for _ in range(5):
                await engine.tick()

            # --- Assert ---
            # Now, mock the send_message function to capture who gets notified
            originator_id = list(engine.peers.keys())[0]
            originator = engine.peers[originator_id]
            originator.send_message = MagicMock()

            # Re-run the deletion event
            engine._handle_event(scenario["events"][-1])

            # Check that send_message was called for all three unique peers, but no more
            self.assertEqual(originator.send_message.call_count, 3)

            # Extract the peer IDs that were notified from the mock calls
            notified_peer_ids = {call.args[1] for call in originator.send_message.call_args_list}

            # Verify that all three peers (0, 1, 2) are in the notification set
            expected_peer_ids = {p.peer_id for p in engine.peers}
            self.assertEqual(notified_peer_ids, expected_peer_ids)
            print("\n[TEST] Loop-safe deletion test successful: All unique peers were notified exactly once.")

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
