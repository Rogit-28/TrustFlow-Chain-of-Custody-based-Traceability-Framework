"""
Tests for StorageBackend implementations (InMemoryStorage and SQLiteStorage).
"""

import os
import tempfile
import pytest
from nacl.signing import SigningKey

from coc_framework.core.coc_node import CoCNode
from coc_framework.core.crypto_core import CryptoCore
from coc_framework.interfaces.storage_backend import (
    StorageBackend,
    InMemoryStorage,
    SQLiteStorage,
)


# --- Fixtures ---

@pytest.fixture
def signing_key():
    """Generate a signing key for creating test nodes."""
    return SigningKey.generate()


@pytest.fixture
def sample_node(signing_key):
    """Create a sample CoCNode for testing."""
    content = "Test content for storage"
    content_hash = CryptoCore.hash_content(content)
    return CoCNode(
        content_hash=content_hash,
        owner_id="test-owner-123",
        signing_key=signing_key,
        recipient_ids=["recipient-1", "recipient-2"],
    )


@pytest.fixture
def another_node(signing_key):
    """Create another sample CoCNode with different content."""
    content = "Another test content"
    content_hash = CryptoCore.hash_content(content)
    return CoCNode(
        content_hash=content_hash,
        owner_id="test-owner-456",
        signing_key=signing_key,
        recipient_ids=["recipient-3"],
    )


@pytest.fixture
def in_memory_storage():
    """Create an InMemoryStorage instance."""
    return InMemoryStorage()


@pytest.fixture
def sqlite_storage():
    """Create an SQLiteStorage instance (in-memory)."""
    storage = SQLiteStorage()
    yield storage
    storage.close()


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


# --- Test Classes ---

class TestInMemoryStorage:
    """Tests for InMemoryStorage implementation."""

    def test_add_and_get_node(self, in_memory_storage, sample_node):
        """Test adding and retrieving a node."""
        in_memory_storage.add_node(sample_node)
        retrieved = in_memory_storage.get_node(sample_node.node_hash)
        
        assert retrieved is not None
        assert retrieved.node_hash == sample_node.node_hash
        assert retrieved.owner_id == sample_node.owner_id
        assert retrieved.content_hash == sample_node.content_hash

    def test_store_node_alias(self, in_memory_storage, sample_node):
        """Test store_node alias for add_node."""
        in_memory_storage.store_node(sample_node)
        retrieved = in_memory_storage.get_node(sample_node.node_hash)
        assert retrieved is not None

    def test_get_nonexistent_node(self, in_memory_storage):
        """Test getting a node that doesn't exist."""
        result = in_memory_storage.get_node("nonexistent-hash")
        assert result is None

    def test_remove_node(self, in_memory_storage, sample_node):
        """Test removing a node."""
        in_memory_storage.add_node(sample_node)
        in_memory_storage.remove_node(sample_node.node_hash)
        retrieved = in_memory_storage.get_node(sample_node.node_hash)
        assert retrieved is None

    def test_remove_nonexistent_node(self, in_memory_storage):
        """Test removing a node that doesn't exist (should not raise)."""
        in_memory_storage.remove_node("nonexistent-hash")  # Should not raise

    def test_get_all_nodes(self, in_memory_storage, sample_node, another_node):
        """Test getting all nodes."""
        in_memory_storage.add_node(sample_node)
        in_memory_storage.add_node(another_node)
        
        all_nodes = in_memory_storage.get_all_nodes()
        assert len(all_nodes) == 2
        node_hashes = {n.node_hash for n in all_nodes}
        assert sample_node.node_hash in node_hashes
        assert another_node.node_hash in node_hashes

    def test_get_all_nodes_empty(self, in_memory_storage):
        """Test getting all nodes when storage is empty."""
        all_nodes = in_memory_storage.get_all_nodes()
        assert all_nodes == []

    def test_add_and_get_content(self, in_memory_storage):
        """Test adding and retrieving content."""
        content = "Test content string"
        content_hash = CryptoCore.hash_content(content)
        
        in_memory_storage.add_content(content_hash, content)
        retrieved = in_memory_storage.get_content(content_hash)
        assert retrieved == content

    def test_store_content_alias(self, in_memory_storage):
        """Test store_content alias for add_content."""
        content = "Test content"
        content_hash = CryptoCore.hash_content(content)
        
        in_memory_storage.store_content(content_hash, content)
        retrieved = in_memory_storage.get_content(content_hash)
        assert retrieved == content

    def test_get_nonexistent_content(self, in_memory_storage):
        """Test getting content that doesn't exist."""
        result = in_memory_storage.get_content("nonexistent-hash")
        assert result is None

    def test_remove_content(self, in_memory_storage):
        """Test removing content."""
        content = "Test content"
        content_hash = CryptoCore.hash_content(content)
        
        in_memory_storage.add_content(content_hash, content)
        in_memory_storage.remove_content(content_hash)
        retrieved = in_memory_storage.get_content(content_hash)
        assert retrieved is None

    def test_remove_nonexistent_content(self, in_memory_storage):
        """Test removing content that doesn't exist (should not raise)."""
        in_memory_storage.remove_content("nonexistent-hash")  # Should not raise

    def test_is_content_referenced(self, in_memory_storage, sample_node):
        """Test checking if content is referenced by a node."""
        in_memory_storage.add_node(sample_node)
        
        assert in_memory_storage.is_content_referenced(sample_node.content_hash) is True
        assert in_memory_storage.is_content_referenced("nonexistent-hash") is False

    def test_is_content_referenced_after_removal(self, in_memory_storage, sample_node):
        """Test is_content_referenced after node removal."""
        in_memory_storage.add_node(sample_node)
        in_memory_storage.remove_node(sample_node.node_hash)
        
        assert in_memory_storage.is_content_referenced(sample_node.content_hash) is False


class TestSQLiteStorage:
    """Tests for SQLiteStorage implementation."""

    def test_add_and_get_node(self, sqlite_storage, sample_node):
        """Test adding and retrieving a node."""
        sqlite_storage.add_node(sample_node)
        retrieved = sqlite_storage.get_node(sample_node.node_hash)
        
        assert retrieved is not None
        assert retrieved.node_hash == sample_node.node_hash
        assert retrieved.owner_id == sample_node.owner_id
        assert retrieved.content_hash == sample_node.content_hash
        assert retrieved.recipient_ids == sample_node.recipient_ids

    def test_store_node_alias(self, sqlite_storage, sample_node):
        """Test store_node alias for add_node."""
        sqlite_storage.store_node(sample_node)
        retrieved = sqlite_storage.get_node(sample_node.node_hash)
        assert retrieved is not None

    def test_get_nonexistent_node(self, sqlite_storage):
        """Test getting a node that doesn't exist."""
        result = sqlite_storage.get_node("nonexistent-hash")
        assert result is None

    def test_remove_node(self, sqlite_storage, sample_node):
        """Test removing a node."""
        sqlite_storage.add_node(sample_node)
        sqlite_storage.remove_node(sample_node.node_hash)
        retrieved = sqlite_storage.get_node(sample_node.node_hash)
        assert retrieved is None

    def test_remove_nonexistent_node(self, sqlite_storage):
        """Test removing a node that doesn't exist (should not raise)."""
        sqlite_storage.remove_node("nonexistent-hash")  # Should not raise

    def test_get_all_nodes(self, sqlite_storage, sample_node, another_node):
        """Test getting all nodes."""
        sqlite_storage.add_node(sample_node)
        sqlite_storage.add_node(another_node)
        
        all_nodes = sqlite_storage.get_all_nodes()
        assert len(all_nodes) == 2
        node_hashes = {n.node_hash for n in all_nodes}
        assert sample_node.node_hash in node_hashes
        assert another_node.node_hash in node_hashes

    def test_get_all_nodes_empty(self, sqlite_storage):
        """Test getting all nodes when storage is empty."""
        all_nodes = sqlite_storage.get_all_nodes()
        assert all_nodes == []

    def test_add_and_get_content(self, sqlite_storage):
        """Test adding and retrieving content."""
        content = "Test content string"
        content_hash = CryptoCore.hash_content(content)
        
        sqlite_storage.add_content(content_hash, content)
        retrieved = sqlite_storage.get_content(content_hash)
        assert retrieved == content

    def test_store_content_alias(self, sqlite_storage):
        """Test store_content alias for add_content."""
        content = "Test content"
        content_hash = CryptoCore.hash_content(content)
        
        sqlite_storage.store_content(content_hash, content)
        retrieved = sqlite_storage.get_content(content_hash)
        assert retrieved == content

    def test_get_nonexistent_content(self, sqlite_storage):
        """Test getting content that doesn't exist."""
        result = sqlite_storage.get_content("nonexistent-hash")
        assert result is None

    def test_remove_content(self, sqlite_storage):
        """Test removing content."""
        content = "Test content"
        content_hash = CryptoCore.hash_content(content)
        
        sqlite_storage.add_content(content_hash, content)
        sqlite_storage.remove_content(content_hash)
        retrieved = sqlite_storage.get_content(content_hash)
        assert retrieved is None

    def test_remove_nonexistent_content(self, sqlite_storage):
        """Test removing content that doesn't exist (should not raise)."""
        sqlite_storage.remove_content("nonexistent-hash")  # Should not raise

    def test_is_content_referenced(self, sqlite_storage, sample_node):
        """Test checking if content is referenced by a node."""
        sqlite_storage.add_node(sample_node)
        
        assert sqlite_storage.is_content_referenced(sample_node.content_hash) is True
        assert sqlite_storage.is_content_referenced("nonexistent-hash") is False

    def test_is_content_referenced_after_removal(self, sqlite_storage, sample_node):
        """Test is_content_referenced after node removal."""
        sqlite_storage.add_node(sample_node)
        sqlite_storage.remove_node(sample_node.node_hash)
        
        assert sqlite_storage.is_content_referenced(sample_node.content_hash) is False

    def test_node_upsert(self, sqlite_storage, signing_key):
        """Test that adding a node with same hash updates it."""
        content_hash = CryptoCore.hash_content("Test")
        node1 = CoCNode(
            content_hash=content_hash,
            owner_id="owner-1",
            signing_key=signing_key,
            recipient_ids=["r1"],
        )
        
        sqlite_storage.add_node(node1)
        
        # Create a modified version with same structure to test upsert
        # In real usage, same node_hash means same node, but we test INSERT OR REPLACE
        sqlite_storage.add_node(node1)  # Should not raise
        
        all_nodes = sqlite_storage.get_all_nodes()
        assert len(all_nodes) == 1


class TestSQLiteStoragePersistence:
    """Tests for SQLiteStorage persistence with file-based database."""

    def test_persistence_across_connections(self, temp_db_path, sample_node):
        """Test that data persists after closing and reopening."""
        content = "Persistent content"
        content_hash = CryptoCore.hash_content(content)
        
        # First connection - write data
        storage1 = SQLiteStorage(temp_db_path)
        storage1.add_node(sample_node)
        storage1.add_content(content_hash, content)
        storage1.close()
        
        # Second connection - verify data persisted
        storage2 = SQLiteStorage(temp_db_path)
        retrieved_node = storage2.get_node(sample_node.node_hash)
        retrieved_content = storage2.get_content(content_hash)
        storage2.close()
        
        assert retrieved_node is not None
        assert retrieved_node.node_hash == sample_node.node_hash
        assert retrieved_node.owner_id == sample_node.owner_id
        assert retrieved_content == content

    def test_persistence_with_multiple_nodes(self, temp_db_path, sample_node, another_node):
        """Test persistence with multiple nodes."""
        # Write
        storage1 = SQLiteStorage(temp_db_path)
        storage1.add_node(sample_node)
        storage1.add_node(another_node)
        storage1.close()
        
        # Read
        storage2 = SQLiteStorage(temp_db_path)
        all_nodes = storage2.get_all_nodes()
        storage2.close()
        
        assert len(all_nodes) == 2


class TestSQLiteStorageContextManager:
    """Tests for SQLiteStorage context manager support."""

    def test_context_manager_basic(self, sample_node):
        """Test basic context manager usage."""
        with SQLiteStorage() as storage:
            storage.add_node(sample_node)
            retrieved = storage.get_node(sample_node.node_hash)
            assert retrieved is not None

    def test_context_manager_with_file(self, temp_db_path, sample_node):
        """Test context manager with file-based database."""
        content = "Context manager test"
        content_hash = CryptoCore.hash_content(content)
        
        # Write using context manager
        with SQLiteStorage(temp_db_path) as storage:
            storage.add_node(sample_node)
            storage.add_content(content_hash, content)
        
        # Verify persistence after context exit
        with SQLiteStorage(temp_db_path) as storage:
            retrieved_node = storage.get_node(sample_node.node_hash)
            retrieved_content = storage.get_content(content_hash)
            
            assert retrieved_node is not None
            assert retrieved_content == content

    def test_context_manager_closes_connection(self, temp_db_path, sample_node):
        """Test that context manager properly closes connection."""
        storage = SQLiteStorage(temp_db_path)
        storage.add_node(sample_node)
        
        # Manually enter and exit context
        storage.__enter__()
        storage.__exit__(None, None, None)
        
        # Connection should be closed
        assert storage._conn is None

    def test_context_manager_exception_handling(self, sample_node):
        """Test context manager handles exceptions properly."""
        try:
            with SQLiteStorage() as storage:
                storage.add_node(sample_node)
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Storage should be closed even after exception
        assert storage._conn is None


class TestSQLiteStorageNodeSerialization:
    """Tests for proper CoCNode serialization/deserialization."""

    def test_node_children_hashes_preserved(self, sqlite_storage, signing_key):
        """Test that children_hashes are preserved through serialization."""
        content_hash = CryptoCore.hash_content("Parent content")
        parent = CoCNode(
            content_hash=content_hash,
            owner_id="parent-owner",
            signing_key=signing_key,
            recipient_ids=["child-owner"],
        )
        
        child_content_hash = CryptoCore.hash_content("Child content")
        child = CoCNode(
            content_hash=child_content_hash,
            owner_id="child-owner",
            signing_key=signing_key,
            recipient_ids=["recipient"],
            parent_hash=parent.node_hash,
            depth=1,
        )
        
        # add_child modifies child.depth in-memory to parent.depth + 1
        parent.add_child(child)
        
        # Store nodes after add_child so updated depth is saved
        sqlite_storage.add_node(parent)
        sqlite_storage.add_node(child)
        
        retrieved_parent = sqlite_storage.get_node(parent.node_hash)
        retrieved_child = sqlite_storage.get_node(child.node_hash)
        
        assert child.node_hash in retrieved_parent.children_hashes
        assert retrieved_child.parent_hash == parent.node_hash
        # child depth was updated to parent.depth + 1 = 0 + 1 = 1 by add_child
        assert retrieved_child.depth == 1

    def test_node_signature_preserved(self, sqlite_storage, sample_node):
        """Test that signature is preserved through serialization."""
        sqlite_storage.add_node(sample_node)
        retrieved = sqlite_storage.get_node(sample_node.node_hash)
        
        assert retrieved.signature is not None
        assert retrieved.signature == sample_node.signature

    def test_node_timestamp_preserved(self, sqlite_storage, sample_node):
        """Test that timestamp is preserved through serialization."""
        sqlite_storage.add_node(sample_node)
        retrieved = sqlite_storage.get_node(sample_node.node_hash)
        
        assert retrieved.timestamp == sample_node.timestamp
