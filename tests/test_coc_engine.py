import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from coc_framework.core.coc_engine import CoCEngine
from coc_framework.core.network_sim import Peer

class TestCoCEngine(unittest.TestCase):
    def test_graph_creation_and_verification(self):
        # Setup
        coc_engine = CoCEngine()
        sender = Peer(coc_engine, None)
        receiver1 = Peer(coc_engine, None)
        receiver2 = Peer(coc_engine, None)

        # Create a root node with multiple recipients
        root_node = coc_engine.create_root_node("Test message", sender, [receiver1, receiver2])
        self.assertIn(root_node.node_hash, coc_engine.nodes)
        self.assertEqual(len(root_node.receiver_ids), 2)
        self.assertIn(receiver1.peer_id, root_node.receiver_ids)

        # Create a forward node (receiver1 forwards to sender in a loop)
        forward_node = coc_engine.add_forward_node(root_node, "Forwarded message", receiver1, [sender])
        self.assertIn(forward_node.node_hash, coc_engine.nodes)
        self.assertEqual(forward_node.parent_hash, root_node.node_hash)
        self.assertEqual(forward_node.receiver_ids[0], sender.peer_id)

        # Verification
        peer_keys = {
            sender.peer_id: sender,
            receiver1.peer_id: receiver1,
            receiver2.peer_id: receiver2
        }
        self.assertTrue(coc_engine.verify_chain_from_node(forward_node, peer_keys))

if __name__ == '__main__':
    unittest.main()
