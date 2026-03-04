"""PostgreSQL database layer using asyncpg.

Manages connection pool, schema creation, and provides query helpers.
Falls back to in-memory SQLite-like dicts when PostgreSQL is unavailable
(for development without a running database).
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── In-memory fallback store ─────────────────────────────────────────────────
# When PostgreSQL isn't available, we use simple dicts. This allows the app
# to run in demo mode without any external dependencies.

_mem: Dict[str, Dict[str, dict]] = {
    "users": {},
    "documents": {},
    "file_shares": {},
    "messages": {},
    "sessions": {},
}


_MESSAGE_DEFAULTS = {
    "parent_message_id": None,
    "is_pinned": False,
}


_MESSAGE_ORDER = "created_at"


_pool = None
_use_pg = False


async def init_db(dsn: str) -> bool:
    """Try to connect to PostgreSQL. Falls back to in-memory on failure."""
    global _pool, _use_pg
    try:
        import asyncpg

        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, timeout=5)
        await _create_tables()
        _use_pg = True
        logger.info("Connected to PostgreSQL")
        return True
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable ({e}), using in-memory storage")
        _use_pg = False
        return False


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def _create_tables():
    """Create schema if not exists."""
    sql = """
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        encrypted_signing_key BYTEA NOT NULL,
        verify_key_hex TEXT NOT NULL,
        peer_id TEXT UNIQUE NOT NULL,
        node_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_id UUID REFERENCES users(id) NOT NULL,
        filename TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size_bytes BIGINT NOT NULL,
        storage_path TEXT NOT NULL,
        storage_node TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        coc_node_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at TIMESTAMPTZ,
        recycled_at TIMESTAMPTZ
    );

    CREATE TABLE IF NOT EXISTS file_shares (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id UUID REFERENCES documents(id) NOT NULL,
        owner_id UUID REFERENCES users(id) NOT NULL,
        recipient_id UUID REFERENCES users(id) NOT NULL,
        child_coc_node_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at TIMESTAMPTZ,
        suspended_at TIMESTAMPTZ
    );

    CREATE TABLE IF NOT EXISTS messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id UUID REFERENCES documents(id) NOT NULL,
        sender_id UUID REFERENCES users(id) NOT NULL,
        body TEXT NOT NULL,
        parent_message_id UUID REFERENCES messages(id),
        is_pinned BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);
    CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
    CREATE INDEX IF NOT EXISTS idx_file_shares_doc ON file_shares(document_id);
    CREATE INDEX IF NOT EXISTS idx_file_shares_recipient ON file_shares(recipient_id);
    CREATE INDEX IF NOT EXISTS idx_messages_doc ON messages(document_id);
    CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_message_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);

    CREATE TABLE IF NOT EXISTS coc_nodes (
        node_hash TEXT PRIMARY KEY,
        content_hash TEXT NOT NULL,
        parent_hash TEXT,
        owner_peer_id TEXT NOT NULL,
        signature TEXT,
        depth INTEGER NOT NULL DEFAULT 0,
        schema_version INTEGER NOT NULL DEFAULT 2,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS coc_recipients (
        node_hash TEXT REFERENCES coc_nodes(node_hash) ON DELETE CASCADE,
        recipient_peer_id TEXT NOT NULL,
        PRIMARY KEY (node_hash, recipient_peer_id)
    );

    CREATE TABLE IF NOT EXISTS tombstones (
        content_hash TEXT PRIMARY KEY,
        deleted_at TIMESTAMPTZ NOT NULL,
        delete_after TIMESTAMPTZ NOT NULL,
        originator_id TEXT NOT NULL,
        node_hash TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_coc_parent_hash ON coc_nodes(parent_hash);
    CREATE INDEX IF NOT EXISTS idx_coc_content_hash ON coc_nodes(content_hash);
    CREATE INDEX IF NOT EXISTS idx_tombstones_expiry ON tombstones(delete_after);
    """
    async with _pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Database schema created")


# ── Generic query helpers (work for both PG and in-memory) ───────────────────


async def insert(table: str, data: dict) -> dict:
    """Insert a row. Returns the row with generated defaults."""
    if "id" not in data:
        data["id"] = str(uuid.uuid4())
    if "created_at" not in data:
        data["created_at"] = datetime.now(timezone.utc)

    if _use_pg and _pool:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))
        values = list(data.values())
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(sql, *values)
            return dict(row)
    else:
        if table == "messages":
            defaults = dict(_MESSAGE_DEFAULTS)
            defaults.update(data)
            data = defaults
        _mem[table][data["id"]] = data
        return data


async def find_one(table: str, **kwargs) -> Optional[dict]:
    """Find one row by column=value filters."""
    if _use_pg and _pool:
        conditions = " AND ".join(
            f"{k} = ${i + 1}" for i, k in enumerate(kwargs.keys())
        )
        sql = f"SELECT * FROM {table} WHERE {conditions} LIMIT 1"
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(sql, *kwargs.values())
            return dict(row) if row else None
    else:
        for row in _mem[table].values():
            if all(row.get(k) == v for k, v in kwargs.items()):
                return row
        return None


async def find_many(
    table: str, order_by: str = "created_at", limit: int = 100, **kwargs
) -> List[dict]:
    """Find multiple rows by column=value filters."""
    if _use_pg and _pool:
        if kwargs:
            conditions = " AND ".join(
                f"{k} = ${i + 1}" for i, k in enumerate(kwargs.keys())
            )
            sql = f"SELECT * FROM {table} WHERE {conditions} ORDER BY {order_by} LIMIT {limit}"
            async with _pool.acquire() as conn:
                rows = await conn.fetch(sql, *kwargs.values())
        else:
            sql = f"SELECT * FROM {table} ORDER BY {order_by} LIMIT {limit}"
            async with _pool.acquire() as conn:
                rows = await conn.fetch(sql)
        return [dict(r) for r in rows]
    else:
        results = [
            row
            for row in _mem[table].values()
            if all(row.get(k) == v for k, v in kwargs.items())
        ]
        return sorted(results, key=lambda r: r.get(order_by, ""))[:limit]


async def update_one(table: str, row_id: str, **updates) -> Optional[dict]:
    """Update a row by ID."""
    if _use_pg and _pool:
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates.keys()))
        sql = f"UPDATE {table} SET {sets} WHERE id = $1 RETURNING *"
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(sql, row_id, *updates.values())
            return dict(row) if row else None
    else:
        row = _mem[table].get(row_id)
        if row:
            row.update(updates)
        return row


async def delete_one(table: str, row_id: str) -> bool:
    """Delete a row by ID."""
    if _use_pg and _pool:
        sql = f"DELETE FROM {table} WHERE id = $1"
        async with _pool.acquire() as conn:
            result = await conn.execute(sql, row_id)
            return "DELETE 1" in result
    else:
        return _mem[table].pop(row_id, None) is not None


async def delete_where(table: str, **kwargs) -> int:
    """Delete rows matching conditions. Returns count."""
    if _use_pg and _pool:
        conditions = " AND ".join(
            f"{k} = ${i + 1}" for i, k in enumerate(kwargs.keys())
        )
        sql = f"DELETE FROM {table} WHERE {conditions}"
        async with _pool.acquire() as conn:
            result = await conn.execute(sql, *kwargs.values())
            return int(result.split()[-1]) if result else 0
    else:
        to_remove = [
            rid
            for rid, row in _mem[table].items()
            if all(row.get(k) == v for k, v in kwargs.items())
        ]
        for rid in to_remove:
            del _mem[table][rid]
        return len(to_remove)
