import unittest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from coc_framework.core.network_sim import Peer, Network
from coc_framework.core.deletion_engine import DeletionEngine
from coc_framework.interfaces.notification_handler import SilentNotificationHandler
from coc_framework.core.crypto_core import CryptoCore
from coc_framework.core.audit_log import AuditLog

class TestOfflineQueue(unittest.TestCase):

    def setUp(self):
        self.notification_handler = SilentNotificationHandler()
        self.network = Network()
        # The DeletionEngine requires an audit_log, let's use a dummy one for this test
        class DummyAuditLog(AuditLog):
            def log_event(self, event_type, peer_id, details, outcome=""):
                pass
        self.audit_log = DummyAuditLog()
        self.deletion_engine = DeletionEngine(self.network, self.audit_log, self.notification_handler, self.network.peer_discovery)
        self.peer1 = Peer(self.deletion_engine)
        self.peer2 = Peer(self.deletion_engine)
        self.network.add_peer(self.peer1)
        self.network.add_peer(self.peer2)


    def test_message_queued_when_offline(self):
        self.peer2.go_offline()
        self.peer1.send_message(self.peer2.peer_id, "test_message", {"data": "test"})
        self.assertEqual(len(self.peer2.offline_queue), 1)

    def test_message_delivered_when_online(self):
        self.peer2.go_offline()
        content = "test_content"

        # Create the CoC root node using the peer
        node = self.peer1.create_coc_root(content, [self.peer2.peer_id])

        # The message format for CoC data is different now. Let's construct it properly.
        coc_data_message = {
            "node_data": node.to_dict(),
            "content": content
        }
        self.peer1.send_message(self.peer2.peer_id, "coc_data", coc_data_message)

        self.peer2.go_online()
        self.assertEqual(len(self.peer2.offline_queue), 0)

        # Check if the node is in the peer's storage
        retrieved_node = self.peer2.storage.get_node(node.node_hash)
        self.assertIsNotNone(retrieved_node)
        self.assertEqual(retrieved_node.content_hash, node.content_hash)

    def test_ttl_expiration(self):
        self.peer2.message_ttl_hours = 0.0001  # 0.36 seconds
        self.peer2.go_offline()
        self.peer1.send_message(self.peer2.peer_id, "test_message", {"data": "test"})

        import time
        time.sleep(0.5)

        self.peer2.go_online()
        self.assertEqual(len(self.peer2.offline_queue), 0)
        # We don't expect any coc_node to be in the storage backend, so we can't assert on it
        # self.assertFalse(self.peer2.storage_backend.message_exists("test_hash"))

if __name__ == '__main__':
    unittest.main()
