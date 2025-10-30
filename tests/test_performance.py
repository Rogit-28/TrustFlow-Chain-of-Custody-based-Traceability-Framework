import unittest
import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from coc_framework.simulation_engine import SimulationEngine
from coc_framework.core.crypto_core import CryptoCore

class TestPerformance(unittest.TestCase):

    def test_deletion_propagation_performance(self):
        async def run_test():
            num_peers = 1000
            events = [
                {
                    "time": 0,
                    "type": "CREATE_MESSAGE",
                    "originator_idx": 0,
                    "recipient_indices": [1],
                    "content": "test_content",
                    "message_id": "msg1"
                }
            ]
            for i in range(1, num_peers - 1):
                events.append({
                    "time": i,
                    "type": "FORWARD_MESSAGE",
                    "sender_idx": i,
                    "recipient_indices": [i+1],
                    "parent_message_id": f"msg{i}",
                    "forwarded_message_id": f"msg{i+1}"
                })
            events.append({
                "time": num_peers,
                "type": "DELETE_MESSAGE",
                "originator_idx": 0,
                "message_id": "msg1"
            })

            scenario = {
                "settings": {"total_peers": num_peers},
                "events": events
            }

            sim_engine = SimulationEngine(scenario)

            start_time = time.time()
            for _ in range(num_peers + 1):
                await sim_engine.tick()
            end_time = time.time()

            self.assertLess(end_time - start_time, 1.0)

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
