import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from coc_framework.core.coc_node import CoCNode
from coc_framework.core.network_sim import Peer
from coc_framework.core.deletion_engine import DeletionEngine
from coc_framework.interfaces.notification_handler import SilentNotificationHandler
from coc_framework.core.crypto_core import CryptoCore
from coc_framework.interfaces.peer_discovery import RegistryPeerDiscovery

from coc_framework.core.audit_log import AuditLog

class TestTreeStructure(unittest.TestCase):

    def setUp(self):
        self.notification_handler = SilentNotificationHandler()
        self.peer_discovery = RegistryPeerDiscovery()

        # The DeletionEngine requires an audit_log, let's use a dummy one for this test
        class DummyAuditLog(AuditLog):
            def log_event(self, event_type, peer_id, details, outcome=""):
                pass
        self.audit_log = DummyAuditLog()

        self.deletion_engine = DeletionEngine(None, self.audit_log, self.notification_handler, self.peer_discovery)

        self.peer1 = Peer(self.deletion_engine)
        self.peer2 = Peer(self.deletion_engine)
        self.peer3 = Peer(self.deletion_engine)

        self.peer_discovery.register_peer(self.peer1)
        self.peer_discovery.register_peer(self.peer2)
        self.peer_discovery.register_peer(self.peer3)

    def test_add_child(self):
        root_node = self.peer1.create_coc_root("root_content", [self.peer2.peer_id])
        # The forward_coc_message method returns the child node. The parent node is updated in the peer's storage.
        child_node = self.peer2.forward_coc_message(root_node, [self.peer3.peer_id])

        # We need to retrieve the updated root_node from storage to check its children
        updated_root_node = self.peer2.storage.get_node(root_node.node_hash)

        self.assertIn(child_node.node_hash, updated_root_node.children_hashes)
        self.assertEqual(child_node.parent_hash, root_node.node_hash)

    def test_depth_calculation(self):
        root_node = self.peer1.create_coc_root("root_content", [self.peer2.peer_id])
        child_node = self.peer2.forward_coc_message(root_node, [self.peer3.peer_id])
        grandchild_node = self.peer3.forward_coc_message(child_node, [self.peer1.peer_id])

        self.assertEqual(root_node.depth, 0)
        self.assertEqual(child_node.depth, 1)
        self.assertEqual(grandchild_node.depth, 2)

    def test_get_all_descendants(self):
        # This test is more complex now as we need to manage state across different peer storages
        # For simplicity, let's assume all nodes end up in a single peer's storage for the purpose of this test.
        storage = self.peer1.storage

        root_node = self.peer1.create_coc_root("root_content", [self.peer2.peer_id])
        storage.add_node(root_node)

        child1 = self.peer2.forward_coc_message(root_node, [self.peer3.peer_id])
        storage.add_node(child1)

        child2 = self.peer2.forward_coc_message(root_node, [self.peer3.peer_id])
        storage.add_node(child2)

        grandchild1 = self.peer3.forward_coc_message(child1, [self.peer1.peer_id])
        storage.add_node(grandchild1)

        # We also need to update the parent nodes in our central storage
        root_node.add_child(child1)
        root_node.add_child(child2)
        child1.add_child(grandchild1)
        storage.add_node(root_node)
        storage.add_node(child1)

        descendants = root_node.get_all_descendants(storage)
        descendant_hashes = [d.node_hash for d in descendants]

        self.assertIn(child1.node_hash, descendant_hashes)
        self.assertIn(child2.node_hash, descendant_hashes)
        self.assertIn(grandchild1.node_hash, descendant_hashes)
        self.assertEqual(len(descendants), 3)

if __name__ == '__main__':
    unittest.main()
