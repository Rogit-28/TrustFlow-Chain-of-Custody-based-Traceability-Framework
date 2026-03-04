"""Storage Backend interfaces and implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Dict, Optional, List, Set
from datetime import datetime, timezone, timedelta
import json
import sqlite3

from coc_framework.core.coc_node import CoCNode


# Default tombstone grace period: content stays tombstoned for this long
# to prevent race conditions with in-flight forwards.
DEFAULT_TOMBSTONE_GRACE_SECONDS = 300  # 5 minutes


@dataclass
class ContentTombstone:
    """Tombstone record for deleted content.
    
    Prevents race conditions where content is deleted on one peer while
    still being forwarded by another. Content with an active tombstone
    cannot be re-added until the grace period expires.
    """
    content_hash: str
    deleted_at: str  # ISO8601
    delete_after: str  # ISO8601 — tombstone expires after this time
    originator_id: str
    node_hash: str  # the node whose deletion created this tombstone

    def is_expired(self) -> bool:
        try:
            expiry = datetime.fromisoformat(self.delete_after.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ContentTombstone":
        return ContentTombstone(**data)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def add_node(self, node: CoCNode) -> None:
        pass

    @abstractmethod
    def get_node(self, node_hash: str) -> Optional[CoCNode]:
        pass

    @abstractmethod
    def remove_node(self, node_hash: str) -> None:
        pass

    @abstractmethod
    def get_all_nodes(self) -> List[CoCNode]:
        pass

    @abstractmethod
    def add_content(self, content_hash: str, content: str) -> None:
        pass

    @abstractmethod
    def get_content(self, content_hash: str) -> Optional[str]:
        pass

    @abstractmethod
    def remove_content(self, content_hash: str) -> None:
        pass

    @abstractmethod
    def is_content_referenced(self, content_hash: str) -> bool:
        pass

    @abstractmethod
    def add_tombstone(self, tombstone: ContentTombstone) -> None:
        """Record a tombstone for deleted content."""
        pass

    @abstractmethod
    def get_tombstone(self, content_hash: str) -> Optional[ContentTombstone]:
        """Get active tombstone for content, or None."""
        pass

    @abstractmethod
    def is_tombstoned(self, content_hash: str) -> bool:
        """Check if content has an active (non-expired) tombstone."""
        pass

    @abstractmethod
    def cleanup_expired_tombstones(self) -> int:
        """Remove expired tombstones. Returns count removed."""
        pass

    def get_all_tombstones(self) -> List[ContentTombstone]:
        """Return all active tombstones. Default: empty list."""
        return []


class InMemoryStorage(StorageBackend):
    """In-memory storage with O(1) content reference lookups via reverse index."""

    def __init__(self):
        self._nodes: Dict[str, CoCNode] = {}
        self._content: Dict[str, str] = {}
        self._content_refs: Dict[str, Set[str]] = {}  # content_hash -> node_hashes
        self._tombstones: Dict[str, ContentTombstone] = {}  # content_hash -> tombstone

    def add_node(self, node: CoCNode) -> None:
        if node.node_hash in self._nodes:
            old_node = self._nodes[node.node_hash]
            if old_node.content_hash in self._content_refs:
                self._content_refs[old_node.content_hash].discard(node.node_hash)
                if not self._content_refs[old_node.content_hash]:
                    del self._content_refs[old_node.content_hash]
        
        self._nodes[node.node_hash] = node
        
        if node.content_hash not in self._content_refs:
            self._content_refs[node.content_hash] = set()
        self._content_refs[node.content_hash].add(node.node_hash)

    def store_node(self, node: CoCNode) -> None:
        self.add_node(node)

    def get_node(self, node_hash: str) -> Optional[CoCNode]:
        return self._nodes.get(node_hash)

    def remove_node(self, node_hash: str) -> None:
        if node_hash in self._nodes:
            node = self._nodes[node_hash]
            if node.content_hash in self._content_refs:
                self._content_refs[node.content_hash].discard(node_hash)
                if not self._content_refs[node.content_hash]:
                    del self._content_refs[node.content_hash]
            del self._nodes[node_hash]

    def get_all_nodes(self) -> List[CoCNode]:
        return list(self._nodes.values())

    def add_content(self, content_hash: str, content: str) -> None:
        self._content[content_hash] = content

    def store_content(self, content_hash: str, content: str) -> None:
        self.add_content(content_hash, content)

    def get_content(self, content_hash: str) -> Optional[str]:
        return self._content.get(content_hash)

    def remove_content(self, content_hash: str) -> None:
        if content_hash in self._content:
            del self._content[content_hash]

    def is_content_referenced(self, content_hash: str) -> bool:
        return content_hash in self._content_refs and len(self._content_refs[content_hash]) > 0

    def get_nodes_by_content(self, content_hash: str) -> List[CoCNode]:
        if content_hash not in self._content_refs:
            return []
        return [self._nodes[nh] for nh in self._content_refs[content_hash] if nh in self._nodes]

    def add_tombstone(self, tombstone: ContentTombstone) -> None:
        self._tombstones[tombstone.content_hash] = tombstone

    def get_tombstone(self, content_hash: str) -> Optional[ContentTombstone]:
        ts = self._tombstones.get(content_hash)
        if ts and ts.is_expired():
            del self._tombstones[content_hash]
            return None
        return ts

    def is_tombstoned(self, content_hash: str) -> bool:
        return self.get_tombstone(content_hash) is not None

    def cleanup_expired_tombstones(self) -> int:
        expired = [ch for ch, ts in self._tombstones.items() if ts.is_expired()]
        for ch in expired:
            del self._tombstones[ch]
        return len(expired)

    def get_all_tombstones(self) -> List[ContentTombstone]:
        self.cleanup_expired_tombstones()
        return list(self._tombstones.values())


SQLITE_SCHEMA_VERSION = 2


class SQLiteStorage(StorageBackend):
    """SQLite-based persistent storage with indexed content_hash for O(log N) lookups."""

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self._create_tables()
        self._migrate_schema()

    def _create_tables(self) -> None:
        cursor = self._conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_hash TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_content_hash 
            ON nodes(content_hash)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_owner_id 
            ON nodes(owner_id)
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content (
                content_hash TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tombstones (
                content_hash TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                delete_after TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tombstones_delete_after
            ON tombstones(delete_after)
        """)
        
        self._conn.commit()

    def _migrate_schema(self) -> None:
        cursor = self._conn.cursor()
        
        cursor.execute("SELECT value FROM schema_meta WHERE key = 'version'")
        row = cursor.fetchone()
        current_version = int(row[0]) if row else 1
        
        if current_version < SQLITE_SCHEMA_VERSION:
            cursor.execute("PRAGMA table_info(nodes)")
            columns = {col[1] for col in cursor.fetchall()}
            
            if "content_hash" not in columns:
                cursor.execute("ALTER TABLE nodes ADD COLUMN content_hash TEXT")
                cursor.execute("ALTER TABLE nodes ADD COLUMN owner_id TEXT")
                
                cursor.execute("SELECT node_hash, data FROM nodes")
                for node_hash, data in cursor.fetchall():
                    node_data = json.loads(data)
                    content_hash = node_data.get("content_hash", "")
                    owner_id = node_data.get("owner_id", "")
                    cursor.execute(
                        "UPDATE nodes SET content_hash = ?, owner_id = ? WHERE node_hash = ?",
                        (content_hash, owner_id, node_hash)
                    )
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_nodes_content_hash 
                    ON nodes(content_hash)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_nodes_owner_id 
                    ON nodes(owner_id)
                """)
            
            cursor.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(SQLITE_SCHEMA_VERSION),)
            )
            self._conn.commit()

    def add_node(self, node: CoCNode) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO nodes 
               (node_hash, content_hash, owner_id, data, created_at) 
               VALUES (?, ?, ?, ?, ?)""",
            (
                node.node_hash,
                node.content_hash,
                node.owner_id,
                json.dumps(node.to_dict()),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def store_node(self, node: CoCNode) -> None:
        self.add_node(node)

    def get_node(self, node_hash: str) -> Optional[CoCNode]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT data FROM nodes WHERE node_hash = ?", (node_hash,))
        row = cursor.fetchone()
        if row:
            return CoCNode.from_dict(json.loads(row[0]))
        return None

    def remove_node(self, node_hash: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM nodes WHERE node_hash = ?", (node_hash,))
        self._conn.commit()

    def get_all_nodes(self) -> List[CoCNode]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT data FROM nodes")
        rows = cursor.fetchall()
        return [CoCNode.from_dict(json.loads(row[0])) for row in rows]

    def add_content(self, content_hash: str, content: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO content (content_hash, content, created_at) VALUES (?, ?, ?)",
            (content_hash, content, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def store_content(self, content_hash: str, content: str) -> None:
        self.add_content(content_hash, content)

    def get_content(self, content_hash: str) -> Optional[str]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT content FROM content WHERE content_hash = ?", (content_hash,)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        return None

    def remove_content(self, content_hash: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM content WHERE content_hash = ?", (content_hash,))
        self._conn.commit()

    def is_content_referenced(self, content_hash: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT 1 FROM nodes WHERE content_hash = ? LIMIT 1",
            (content_hash,)
        )
        return cursor.fetchone() is not None

    def get_nodes_by_content(self, content_hash: str) -> List[CoCNode]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT data FROM nodes WHERE content_hash = ?",
            (content_hash,)
        )
        return [CoCNode.from_dict(json.loads(row[0])) for row in cursor.fetchall()]

    def get_nodes_by_owner(self, owner_id: str) -> List[CoCNode]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT data FROM nodes WHERE owner_id = ?",
            (owner_id,)
        )
        return [CoCNode.from_dict(json.loads(row[0])) for row in cursor.fetchall()]

    def add_tombstone(self, tombstone: ContentTombstone) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO tombstones (content_hash, data, delete_after) VALUES (?, ?, ?)",
            (tombstone.content_hash, json.dumps(tombstone.to_dict()), tombstone.delete_after),
        )
        self._conn.commit()

    def get_tombstone(self, content_hash: str) -> Optional[ContentTombstone]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT data FROM tombstones WHERE content_hash = ?", (content_hash,)
        )
        row = cursor.fetchone()
        if row:
            ts = ContentTombstone.from_dict(json.loads(row[0]))
            if ts.is_expired():
                cursor.execute("DELETE FROM tombstones WHERE content_hash = ?", (content_hash,))
                self._conn.commit()
                return None
            return ts
        return None

    def is_tombstoned(self, content_hash: str) -> bool:
        return self.get_tombstone(content_hash) is not None

    def cleanup_expired_tombstones(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tombstones WHERE delete_after < ?", (now,))
        count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM tombstones WHERE delete_after < ?", (now,))
        self._conn.commit()
        return count

    def get_all_tombstones(self) -> List[ContentTombstone]:
        self.cleanup_expired_tombstones()
        cursor = self._conn.cursor()
        cursor.execute("SELECT data FROM tombstones")
        return [ContentTombstone.from_dict(json.loads(row[0])) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SQLiteStorage":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
