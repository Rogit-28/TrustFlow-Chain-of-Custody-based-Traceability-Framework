import asyncio
from typing import List, Optional
from datetime import datetime, timezone

from coc_framework.interfaces.storage_backend import StorageBackend, ContentTombstone
from coc_framework.core.coc_node import CoCNode
from trustdocs import database as db
import logging

logger = logging.getLogger(__name__)


def _parse_ts(ts_value) -> datetime:
    """Convert ISO string or datetime to a timezone-aware datetime for asyncpg."""
    if isinstance(ts_value, datetime):
        return ts_value if ts_value.tzinfo else ts_value.replace(tzinfo=timezone.utc)
    if isinstance(ts_value, str):
        return datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


class PostgresStorageBackend:
    """PostgreSQL implementation of the CoC graph backend.
    
    Replaces InMemoryStorage. Storage operations are inherently asynchronous.
    """

    async def add_node(self, node: CoCNode) -> None:
        try:
            ts = _parse_ts(node.timestamp)
            async with db._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO coc_nodes
                        (node_hash, content_hash, parent_hash, owner_peer_id, signature, depth, schema_version, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT (node_hash) DO NOTHING
                """,
                    node.node_hash,
                    node.content_hash,
                    node.parent_hash,
                    node.owner_id,
                    node.signature.hex() if node.signature else None,
                    node.depth,
                    node.schema_version,
                    ts,
                )
                for pid in node.recipient_ids:
                    await conn.execute("""
                        INSERT INTO coc_recipients (node_hash, recipient_peer_id)
                        VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                    """, node.node_hash, pid)
        except Exception as e:
            logger.error(f"add_node failed for {getattr(node, 'node_hash', '?')}: {e}", exc_info=True)

    async def get_node(self, node_hash: str) -> Optional[CoCNode]:
        row = await db.find_one("coc_nodes", node_hash=node_hash)
        if not row:
            return None
        
        # Get recipients — no created_at column, use node_hash ordering
        try:
            async with db._pool.acquire() as conn:
                r_rows = await conn.fetch(
                    "SELECT recipient_peer_id FROM coc_recipients WHERE node_hash = $1",
                    node_hash
                )
                recipients_list = [r["recipient_peer_id"] for r in r_rows]
        except Exception:
            recipients_list = []

        # Get children
        try:
            async with db._pool.acquire() as conn:
                c_rows = await conn.fetch(
                    "SELECT node_hash FROM coc_nodes WHERE parent_hash = $1",
                    node_hash
                )
                children_hashes = [c["node_hash"] for c in c_rows]
        except Exception:
            children_hashes = []

        created_at = row["created_at"]
        node_dict = {
            "schema_version": row["schema_version"],
            "node_hash": row["node_hash"],
            "content_hash": row["content_hash"],
            "parent_hash": row["parent_hash"],
            "owner_id": row["owner_peer_id"],
            "recipient_ids": recipients_list,
            "timestamp": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
            "children_hashes": children_hashes,
            "depth": row["depth"],
            "signature": row["signature"]
        }
        return CoCNode.from_dict(node_dict)

    async def get_all_nodes(self) -> List[CoCNode]:
        try:
            async with db._pool.acquire() as conn:
                rows = await conn.fetch("SELECT node_hash FROM coc_nodes ORDER BY created_at")
        except Exception as e:
            logger.error(f"get_all_nodes failed: {e}")
            return []
        nodes = []
        for row in rows:
            node = await self.get_node(row["node_hash"])
            if node:
                nodes.append(node)
        return nodes

    async def add_content(self, content_hash: str, content: str) -> None:
        # File payload storage is fully offloaded to the filesystem by TrustDocs API.
        pass

    async def get_content(self, content_hash: str) -> Optional[str]:
        # Handled natively by the API via filesystem reads.
        return None

    async def add_tombstone(self, tombstone: ContentTombstone) -> None:
        try:
            d = tombstone.to_dict()
            async with db._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO tombstones (content_hash, deleted_at, delete_after, originator_id, node_hash)
                    VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (content_hash) DO NOTHING
                """,
                    d["content_hash"],
                    _parse_ts(d["deleted_at"]),
                    _parse_ts(d["delete_after"]),
                    d["originator_id"],
                    d["node_hash"])
        except Exception as e:
            logger.error(f"add_tombstone failed: {e}", exc_info=True)

    async def get_tombstone(self, content_hash: str) -> Optional[ContentTombstone]:
        row = await db.find_one("tombstones", content_hash=content_hash)
        if row:
            row["deleted_at"] = row["deleted_at"].isoformat() if isinstance(row["deleted_at"], datetime) else row["deleted_at"]
            row["delete_after"] = row["delete_after"].isoformat() if isinstance(row["delete_after"], datetime) else row["delete_after"]
            return ContentTombstone.from_dict(row)
        return None
