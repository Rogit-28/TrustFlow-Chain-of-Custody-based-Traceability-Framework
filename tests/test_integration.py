import unittest
import asyncio
from coc_framework.simulation_engine import SimulationEngine
from coc_framework.core.coc_node import CoCNode
from coc_framework.core.deletion_engine import DeletionEngine

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.peer_ids = [f"peer_{i}" for i in range(3)]

    def test_full_lifecycle(self):
        """
        Tests a full message lifecycle: create, forward, and delete.
        """
        async def run_test():
            scenario = {
                "peers": [
                    {"id": self.peer_ids[0]},
                    {"id": self.peer_ids[1]},
                    {"id": self.peer_ids[2]}
                ],
                "events": [
                    {
                        "time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[0]
                    },
                    {
                        "time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[1]
                    },
                    {
                        "time": 0, "type": "PEER_ONLINE", "peer_id": self.peer_ids[2]
                    },
                    {
                        "time": 1,
                        "type": "CREATE_MESSAGE",
                        "originator_id": self.peer_ids[0],
                        "recipient_ids": [self.peer_ids[1]],
                        "content": "Secret Meeting @ Noon",
                        "message_id": "msg1"
                    },
                    {
                        "time": 2,
                        "type": "FORWARD_MESSAGE",
                        "sender_id": self.peer_ids[1],
                        "recipient_ids": [self.peer_ids[2]],
                        "parent_message_id": "msg1",
                        "forwarded_message_id": "msg2"
                    },
                    {
                        "time": 3,
                        "type": "DELETE_MESSAGE",
                        "originator_id": self.peer_ids[0],
                        "message_id": "msg1"
                    }
                ]
            }

            sim_engine = SimulationEngine(scenario)

            await sim_engine.tick() # Tick 0

            # Tick 1: Create
            await sim_engine.tick()
            peer0 = sim_engine.peers[self.peer_ids[0]]
            self.assertEqual(len(peer0.storage.get_all_nodes()), 1)
            root_node_hash = list(peer0.storage.get_all_nodes())[0].node_hash

            # Update forward and deletion events with the correct hash
            for event in sim_engine.events:
                if event.get("parent_message_id") == "msg1":
                    event['parent_node_hash'] = root_node_hash
                if event.get("type") == "DELETE_MESSAGE" and event.get("message_id") == "msg1":
                    event['node_hash'] = root_node_hash

            # Tick 2: Forward
            await sim_engine.tick()
            peer1 = sim_engine.peers[self.peer_ids[1]]
            self.assertEqual(len(peer1.storage.get_all_nodes()), 2)

            # Tick 3: Process network queue from forward
            await sim_engine.tick()
            peer2 = sim_engine.peers[self.peer_ids[2]]
            self.assertEqual(len(peer2.storage.get_all_nodes()), 1)

            # Tick 4: Delete
            await sim_engine.tick()

            # After deletion propagation, the content should be gone from all peers
            await sim_engine.tick()
            await sim_engine.tick()
            await sim_engine.tick()

            self.assertEqual(len(peer0.storage.get_all_nodes()), 1)
            self.assertEqual(len(peer1.storage.get_all_nodes()), 0)
            self.assertEqual(len(peer2.storage.get_all_nodes()), 0)

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
