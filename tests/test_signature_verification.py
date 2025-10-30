import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from coc_framework.core.crypto_core import CryptoCore
from coc_framework.core.deletion_engine import DeletionEngine, DeletionToken
from coc_framework.core.network_sim import Peer
from coc_framework.interfaces.notification_handler import SilentNotificationHandler
from coc_framework.core.audit_log import AuditLog
from coc_framework.interfaces.peer_discovery import RegistryPeerDiscovery

class TestSignatureVerification(unittest.TestCase):

    def setUp(self):
        self.crypto_core = CryptoCore()
        self.notification_handler = SilentNotificationHandler()

        # The DeletionEngine requires an audit_log, let's use a dummy one for this test
        class DummyAuditLog(AuditLog):
            def log_event(self, event_type, peer_id, details, outcome=""):
                pass
        self.audit_log = DummyAuditLog()

        self.peer_discovery = RegistryPeerDiscovery()
        self.deletion_engine = DeletionEngine(None, self.audit_log, self.notification_handler, self.peer_discovery) # Network can be None for these tests

        self.peer1 = Peer(self.deletion_engine)
        self.peer2 = Peer(self.deletion_engine)
        self.peer_discovery.register_peer(self.peer1)
        self.peer_discovery.register_peer(self.peer2)

    def test_valid_deletion_token(self):
        node = self.peer1.create_coc_root("test_content", [self.peer2.peer_id])
        token = self.deletion_engine.issue_token(node, self.peer1)
        token_data = f"{token.node_hash}{token.originator_id}{token.timestamp}"
        self.assertTrue(CryptoCore.verify_signature(self.peer1.verify_key, token_data, bytes.fromhex(token.signature)))

    def test_invalid_deletion_token(self):
        node = self.peer1.create_coc_root("test_content", [self.peer2.peer_id])
        token = self.deletion_engine.issue_token(node, self.peer1)
        # Tamper with the signature
        token.signature = token.signature[:-4] + "aaaa"
        token_data = f"{token.node_hash}{token.originator_id}{token.timestamp}"
        self.assertFalse(CryptoCore.verify_signature(self.peer1.verify_key, token_data, bytes.fromhex(token.signature)))

    def test_coc_node_signature(self):
        node = self.peer1.create_coc_root("test_content", [self.peer2.peer_id])
        self.assertTrue(node.verify_signature(self.peer1.verify_key))

    def test_process_invalid_token(self):
        node = self.peer1.create_coc_root("test_content", [self.peer2.peer_id])
        token = self.deletion_engine.issue_token(node, self.peer1)
        # Tamper with the signature
        token.signature = token.signature[:-4] + "aaaa"

        # This method doesn't return anything now, it logs errors.
        # We can't easily assert on the log output here, but we can ensure it doesn't raise an exception.
        try:
            self.deletion_engine.process_token(token, self.peer2)
        except Exception as e:
            self.fail(f"process_token raised an exception with an invalid token: {e}")

if __name__ == '__main__':
    unittest.main()
