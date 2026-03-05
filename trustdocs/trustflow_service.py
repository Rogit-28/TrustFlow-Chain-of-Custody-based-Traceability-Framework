"""TrustFlow in-process service wrapper.

Provides a stateless TrustFlowService that wraps the core TrustFlow
components (AuditLog, SteganoEngine, PostgresStorageBackend)
for direct async method calls from FastAPI route handlers.
"""

import logging
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple

from coc_framework.core.coc_node import CoCNode
from coc_framework.core.crypto_core import CryptoCore
from coc_framework.core.audit_log import AuditLog
from coc_framework.core.steganography import SteganoEngine
from coc_framework.core.timelock import TimeLockEngine
from coc_framework.interfaces.postgres_backend import PostgresStorageBackend
from trustdocs import database as db

logger = logging.getLogger(__name__)


class TrustFlowService:
    """In-process TrustFlow service (Stateless).

    Wraps all TrustFlow operations that TrustDocs needs:
    - CoC operations (create root, forward, delete)
    - Steganographic watermarking
    - Audit log access
    """

    def __init__(self):
        self.audit_log = AuditLog()
        self.stegano_engine = SteganoEngine()
        self.timelock_engine = TimeLockEngine(cleanup_interval=5.0)
        self.storage = PostgresStorageBackend()

        # System key used to sign CoC nodes since user keys are password-encrypted
        self.system_signing_key, self.system_verify_key = CryptoCore.generate_keypair()

        logger.info("TrustFlowService initialized (Stateless Postgres Mode)")

    # ── Peer Management (Legacy shims) ───────────────────────────────────

    async def get_peer_status(self, peer_id: str) -> bool:
        """Returns online status. All users are considered online in stateless mode."""
        row = await db.find_one("users", peer_id=peer_id)
        return row is not None

    async def register_peer_for_stegano(self, peer_id: str):
        self.stegano_engine.register_peer(peer_id)

    # ── Chain of Custody ─────────────────────────────────────────────────

    async def create_document_node(
        self,
        owner_peer_id: str,
        content: str,
        recipient_ids: Optional[List[str]] = None,
    ) -> CoCNode:
        """Create a root CoC node for a new document upload."""
        content_hash = CryptoCore.hash_content(content)

        node = CoCNode(
            content_hash=content_hash,
            owner_id=owner_peer_id,
            signing_key=self.system_signing_key,
            recipient_ids=recipient_ids or [],
        )

        await self.storage.add_node(node)
        self.audit_log.log_event("UPLOAD", owner_peer_id, node.node_hash)
        return node

    async def share_document(
        self,
        owner_peer_id: str,
        parent_node: CoCNode,
        recipient_peer_ids: List[str],
        content: str,
    ) -> tuple:
        """Forward a document with watermarking. Returns (child_node, watermarked_content)."""
        watermarked = self.stegano_engine.embed_watermark(
            content=content,
            peer_id=recipient_peer_ids[0],  # Primary recipient for watermark
            depth=parent_node.depth + 1,
        )

        wm_hash = CryptoCore.hash_content(watermarked)

        child_node = CoCNode(
            content_hash=wm_hash,
            owner_id=owner_peer_id,
            signing_key=self.system_signing_key,
            recipient_ids=recipient_peer_ids,
            parent_hash=parent_node.node_hash,
            depth=parent_node.depth + 1,
        )

        # Write to PostgreSQL
        await self.storage.add_node(child_node)

        # Update parent recipients in DB if necessary
        for pid in recipient_peer_ids:
            try:
                await db.insert(
                    "coc_recipients",
                    {"node_hash": parent_node.node_hash, "recipient_peer_id": pid},
                )
            except Exception:
                pass

        self.audit_log.log_event(
            "SHARE",
            owner_peer_id,
            child_node.node_hash,
            f"To: {','.join(p[:8] for p in recipient_peer_ids)}",
        )
        return child_node, watermarked

    def detect_leak(self, content: str, candidate_peer_ids: Optional[List[str]] = None):
        """Run watermark extraction on suspected leaked content."""
        if candidate_peer_ids:
            for pid in candidate_peer_ids:
                self.stegano_engine.register_peer(pid)
        return self.stegano_engine.extract_watermark(
            content=content, candidate_peers=candidate_peer_ids or []
        )

    # ── Graph queries and augmentation ───────────────────────────────────

    async def _augment_nodes(self, nodes: List[CoCNode]) -> List[dict]:
        """Augment nodes with user presence and username for UI rendering."""
        if not nodes:
            return []

        users = await db.find_many("users")
        user_map = {}
        now = datetime.now(timezone.utc)

        for u in users:
            is_online = False
            last_seen = u.get("last_seen_at")
            if last_seen:
                if isinstance(last_seen, str):
                    last_seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if not last_seen.tzinfo:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                if now - last_seen < timedelta(minutes=2):
                    is_online = True

            user_map[u["peer_id"]] = {"username": u["username"], "is_online": is_online}

        docs = await db.find_many("documents")
        doc_map = {d["coc_node_hash"]: d["filename"] for d in docs}

        augmented_nodes = []
        for n in nodes:
            n_dict = n.to_dict()
            owner_info = user_map.get(
                n.owner_id, {"username": "Unknown", "is_online": False}
            )
            n_dict["owner_username"] = owner_info["username"]
            n_dict["is_online"] = owner_info["is_online"]
            n_dict["filename"] = doc_map.get(n.node_hash, "")
            augmented_nodes.append(n_dict)

        return augmented_nodes

    async def get_all_nodes(self) -> tuple:
        """Return all nodes and edges globally from DB."""
        nodes = await self.storage.get_all_nodes()
        augmented = await self._augment_nodes(nodes)
        nodes_map = {n["node_hash"]: n for n in augmented}
        edges = [
            {"from": n.parent_hash, "to": n.node_hash} for n in nodes if n.parent_hash
        ]
        return list(nodes_map.values()), edges

    @staticmethod
    def find_paths_in_edges(
        edges: List[dict],
        source: str,
        target: str,
        mode: str = "shortest",
        max_paths: int = 25,
        max_depth: int = 16,
    ) -> dict:
        """Find directed path(s) in an edge list with bounded complexity.

        Args:
            edges: Directed edges in shape {"from": str, "to": str}.
            source: Source node hash.
            target: Target node hash.
            mode: "shortest" or "all".
            max_paths: Maximum number of paths to return when mode="all".
            max_depth: Maximum traversal depth to prevent combinatorial blowups.
        """
        if mode not in {"shortest", "all"}:
            raise ValueError("mode must be 'shortest' or 'all'")

        max_paths = max(1, min(int(max_paths), 200))
        max_depth = max(1, min(int(max_depth), 64))

        adjacency: Dict[str, Set[str]] = {}
        for edge in edges:
            frm = edge.get("from")
            to = edge.get("to")
            if not frm or not to:
                continue
            adjacency.setdefault(frm, set()).add(to)

        if source == target:
            return {
                "mode": mode,
                "source": source,
                "target": target,
                "paths": [{"nodes": [source], "edges": []}],
                "path_count": 1,
                "truncated": False,
            }

        if mode == "shortest":
            queue = deque([source])
            parents: Dict[str, str] = {}
            visited = {source}
            depth: Dict[str, int] = {source: 0}

            while queue:
                current = queue.popleft()
                current_depth = depth.get(current, 0)
                if current_depth >= max_depth:
                    continue

                for nxt in adjacency.get(current, set()):
                    if nxt in visited:
                        continue
                    visited.add(nxt)
                    parents[nxt] = current
                    depth[nxt] = current_depth + 1
                    if nxt == target:
                        queue.clear()
                        break
                    queue.append(nxt)

            if target not in parents:
                return {
                    "mode": mode,
                    "source": source,
                    "target": target,
                    "paths": [],
                    "path_count": 0,
                    "truncated": False,
                }

            node_path = [target]
            cursor = target
            while cursor in parents:
                cursor = parents[cursor]
                node_path.append(cursor)
            node_path.reverse()

            edge_path = [
                {"from": node_path[i], "to": node_path[i + 1]}
                for i in range(len(node_path) - 1)
            ]

            return {
                "mode": mode,
                "source": source,
                "target": target,
                "paths": [{"nodes": node_path, "edges": edge_path}],
                "path_count": 1,
                "truncated": False,
            }

        collected_paths: List[List[str]] = []
        truncated = False

        def dfs(current: str, trail: List[str], seen: Set[str]) -> None:
            nonlocal truncated
            if truncated:
                return
            if len(trail) - 1 > max_depth:
                return
            if current == target:
                collected_paths.append(list(trail))
                if len(collected_paths) >= max_paths:
                    truncated = True
                return

            for nxt in adjacency.get(current, set()):
                if nxt in seen:
                    continue
                seen.add(nxt)
                trail.append(nxt)
                dfs(nxt, trail, seen)
                trail.pop()
                seen.remove(nxt)
                if truncated:
                    return

        dfs(source, [source], {source})

        paths = []
        for node_path in collected_paths:
            edge_path = [
                {"from": node_path[i], "to": node_path[i + 1]}
                for i in range(len(node_path) - 1)
            ]
            paths.append({"nodes": node_path, "edges": edge_path})

        return {
            "mode": mode,
            "source": source,
            "target": target,
            "paths": paths,
            "path_count": len(paths),
            "truncated": truncated,
        }

    async def get_graph_for_peer(self, peer_id: str) -> tuple:
        """Return nodes/edges visible to a specific peer."""
        nodes = await self.storage.get_all_nodes()

        # 1. Identify all nodes the user directly interacts with
        visible_raw_nodes = []
        for n in nodes:
            if n.owner_id == peer_id or peer_id in n.recipient_ids:
                visible_raw_nodes.append(n)

        # 2. For each visible node, crawl UP to find its ultimate Root hash
        root_hashes = set()
        nodes_by_hash = {n.node_hash: n for n in nodes}

        for n in visible_raw_nodes:
            current = n
            while current.parent_hash and current.parent_hash in nodes_by_hash:
                current = nodes_by_hash[current.parent_hash]
            root_hashes.add(current.node_hash)

        # 3. For every Root hash identified, capture its entire lineage
        provenance_nodes_map = {}
        edges = []

        for root_hash in root_hashes:
            root_node = nodes_by_hash[root_hash]
            stack = [root_node]

            while stack:
                current = stack.pop()
                if current.node_hash not in provenance_nodes_map:
                    provenance_nodes_map[current.node_hash] = current

                    # Add child links to edges and stack
                    for child_hash in current.children_hashes:
                        edges.append({"from": current.node_hash, "to": child_hash})
                        if child_hash in nodes_by_hash:
                            stack.append(nodes_by_hash[child_hash])

        # 4. Augment and return the full provenance subgraph
        augmented = await self._augment_nodes(list(provenance_nodes_map.values()))
        final_nodes_map = {n["node_hash"]: n for n in augmented}

        # Filter duplicates in edges just in case multiple lineages overlapped
        unique_edges = [dict(t) for t in {tuple(d.items()) for d in edges}]

        return list(final_nodes_map.values()), unique_edges

    async def get_graph_paths_for_peer(
        self,
        peer_id: str,
        source: str,
        target: str,
        mode: str = "shortest",
        max_paths: int = 25,
        max_depth: int = 16,
    ) -> dict:
        """Find path(s) between two nodes for a peer-scoped graph."""
        nodes, edges = await self.get_graph_for_peer(peer_id)
        visible_nodes = {n["node_hash"] for n in nodes}

        if source not in visible_nodes or target not in visible_nodes:
            return {
                "mode": mode,
                "source": source,
                "target": target,
                "paths": [],
                "path_count": 0,
                "truncated": False,
                "error": "source_or_target_not_visible",
            }

        return self.find_paths_in_edges(
            edges=edges,
            source=source,
            target=target,
            mode=mode,
            max_paths=max_paths,
            max_depth=max_depth,
        )

    async def get_graph_paths_for_document(
        self,
        root_hash: str,
        source: str,
        target: str,
        mode: str = "shortest",
        max_paths: int = 25,
        max_depth: int = 16,
    ) -> dict:
        """Find path(s) between two nodes in a single document trace tree."""
        nodes, edges = await self.get_trace_for_document(root_hash)
        visible_nodes = {n["node_hash"] for n in nodes}

        if source not in visible_nodes or target not in visible_nodes:
            return {
                "mode": mode,
                "source": source,
                "target": target,
                "paths": [],
                "path_count": 0,
                "truncated": False,
                "error": "source_or_target_not_visible",
            }

        return self.find_paths_in_edges(
            edges=edges,
            source=source,
            target=target,
            mode=mode,
            max_paths=max_paths,
            max_depth=max_depth,
        )

    async def get_node(self, node_hash: str) -> Optional[CoCNode]:
        return await self.storage.get_node(node_hash)

    async def get_trace_for_document(self, root_hash: str) -> tuple:
        """Return a full tree trace for a document root hash, recursively fetching from DB."""
        nodes = []
        edges = []
        nodes_seen = set()

        root = await self.storage.get_node(root_hash)
        if not root:
            return [], []

        stack = [root]
        while stack:
            node = stack.pop()
            if node.node_hash in nodes_seen:
                continue
            nodes_seen.add(node.node_hash)
            nodes.append(node)
            for child_hash in node.children_hashes:
                edges.append({"from": node.node_hash, "to": child_hash})
                child = await self.storage.get_node(child_hash)
                if child:
                    stack.append(child)

        augmented = await self._augment_nodes(nodes)
        return augmented, edges

    async def delete_document(self, owner_peer_id: str, node_hash: str):
        """Log the deletion event. Network propagation is handled natively by DB views."""
        self.audit_log.log_event("DELETE", owner_peer_id, node_hash)


# Singleton instance — shared across the app.
trustflow = TrustFlowService()
