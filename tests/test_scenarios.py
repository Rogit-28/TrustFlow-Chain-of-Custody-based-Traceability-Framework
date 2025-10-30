import unittest
import asyncio
from coc_framework.simulation_engine import SimulationEngine
from coc_framework.core.coc_node import CoCNode
from coc_framework.core.crypto_core import CryptoCore

class TestScenarios(unittest.TestCase):

    def setUp(self):
        self.peer_ids = [f"peer_{i}" for i in range(5)]

    def test_graph_merging(self):
        """
        Tests a scenario where two separate CoC graphs eventually merge
        through a common recipient.
        """
        async def run_test():
            scenario = {
                "peers": [
                    {"id": self.peer_ids[0]},
                    {"id": self.peer_ids[1]},
                    {"id": self.peer_ids[2]},
                    {"id": self.peer_ids[3]}
                ],
                "events": [
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[0]},
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[1]},
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[2]},
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[3]},
                    {
                        "time": 1, "type": "CREATE_MESSAGE",
                        "originator_id": self.peer_ids[0], "recipient_ids": [self.peer_ids[1]],
                        "content": "Doc A", "message_id": "msgA"
                    },
                    {
                        "time": 1, "type": "CREATE_MESSAGE",
                        "originator_id": self.peer_ids[2], "recipient_ids": [self.peer_ids[3]],
                        "content": "Doc B", "message_id": "msgB"
                    },
                    {
                        "time": 2, "type": "FORWARD_MESSAGE",
                        "sender_id": self.peer_ids[1], "recipient_ids": [self.peer_ids[3]],
                        "parent_message_id": "msgA", "forwarded_message_id": "msgC"
                    }
                ]
            }

            sim_engine = SimulationEngine(scenario)

            await sim_engine.tick() # Tick 0

            await sim_engine.tick() # Tick 1
            peer0 = sim_engine.peers[self.peer_ids[0]]
            msgA_node_hash = list(peer0.storage.get_all_nodes())[0].node_hash

            for event in sim_engine.events:
                if event.get("forwarded_message_id") == "msgC":
                    event["parent_node_hash"] = msgA_node_hash

            await sim_engine.tick() # Tick 2
            await sim_engine.tick() # Process network queue

            peer3 = sim_engine.peers[self.peer_ids[3]]

            node_hashes = {node.content_hash for node in peer3.storage.get_all_nodes()}

            self.assertIn(CryptoCore.hash_content("Doc B"), node_hashes)
            self.assertEqual(len(peer3.storage.get_all_nodes()), 2)

            node_c = next(n for n in peer3.storage.get_all_nodes() if n.parent_hash is not None)
            self.assertIsNotNone(node_c)

        asyncio.run(run_test())

    def test_concurrent_forwards(self):
        """
        Tests a scenario with multiple peers forwarding the same message
        concurrently to a single recipient.
        """
        async def run_test():
            scenario = {
                "peers": [
                    {"id": self.peer_ids[0]},
                    {"id": self.peer_ids[1]},
                    {"id": self.peer_ids[2]},
                    {"id": self.peer_ids[3]}
                ],
                "events": [
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[0]},
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[1]},
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[2]},
                    {"time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[3]},
                    {
                        "time": 1, "type": "CREATE_MESSAGE",
                        "originator_id": self.peer_ids[0], "recipient_ids": [self.peer_ids[1], self.peer_ids[2]],
                        "content": "Project Plan", "message_id": "proj_plan"
                    },
                    {
                        "time": 2, "type": "FORWARD_MESSAGE",
                        "sender_id": self.peer_ids[1], "recipient_ids": [self.peer_ids[3]],
                        "parent_message_id": "proj_plan", "forwarded_message_id": "fwd1"
                    },
                    {
                        "time": 2, "type": "FORWARD_MESSAGE",
                        "sender_id": self.peer_ids[2], "recipient_ids": [self.peer_ids[3]],
                        "parent_message_id": "proj_plan", "forwarded_message_id": "fwd2"
                    }
                ]
            }

            sim_engine = SimulationEngine(scenario)

            await sim_engine.tick() # Tick 0

            await sim_engine.tick() # Tick 1

            peer0 = sim_engine.peers[self.peer_ids[0]]
            parent_hash = list(peer0.storage.get_all_nodes())[0].node_hash
            for event in sim_engine.events:
                if event.get("type") == "FORWARD_MESSAGE":
                    event["parent_node_hash"] = parent_hash

            await sim_engine.tick() # Tick 2
            await sim_engine.tick() # Process network

            peer3 = sim_engine.peers[self.peer_ids[3]]
            self.assertEqual(len(peer3.storage.get_all_nodes()), 2)

            nodes = list(peer3.storage.get_all_nodes())
            self.assertEqual(nodes[0].parent_hash, nodes[1].parent_hash)

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
