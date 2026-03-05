"""Tests for scalable graph path-finding in TrustDocs admin routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from trustdocs.admin import router
from trustdocs.auth.dependencies import get_current_user
from trustdocs.trustflow_service import TrustFlowService


TEST_USER = {
    "id": "user-1",
    "peer_id": "peer-1",
    "username": "alice",
}


def _make_app(current_user: dict = TEST_USER) -> FastAPI:
    """Build a test app with admin routes and auth override."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


class TestServicePathAlgorithms:
    """Unit tests for edge-list path utilities."""

    def test_find_shortest_path(self):
        edges = [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "C"},
            {"from": "A", "to": "D"},
            {"from": "D", "to": "C"},
            {"from": "A", "to": "E"},
            {"from": "E", "to": "F"},
            {"from": "F", "to": "C"},
        ]

        result = TrustFlowService.find_paths_in_edges(
            edges=edges,
            source="A",
            target="C",
            mode="shortest",
            max_depth=8,
        )

        assert result["path_count"] == 1
        assert result["paths"][0]["nodes"] in (["A", "B", "C"], ["A", "D", "C"])

    def test_find_all_paths_with_limit(self):
        edges = [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "D"},
            {"from": "A", "to": "C"},
            {"from": "C", "to": "D"},
            {"from": "A", "to": "E"},
            {"from": "E", "to": "D"},
        ]

        result = TrustFlowService.find_paths_in_edges(
            edges=edges,
            source="A",
            target="D",
            mode="all",
            max_paths=2,
            max_depth=8,
        )

        assert result["path_count"] == 2
        assert result["truncated"] is True

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            TrustFlowService.find_paths_in_edges(
                edges=[],
                source="A",
                target="B",
                mode="invalid",
            )


class TestAdminGraphPathRoute:
    """API tests for GET /admin/graph/path."""

    @pytest.mark.asyncio
    async def test_my_scope_shortest_path(self):
        app = _make_app()

        with patch("trustdocs.admin.trustflow") as mock_tf:
            mock_tf.get_graph_paths_for_peer = AsyncMock(
                return_value={
                    "mode": "shortest",
                    "source": "A",
                    "target": "D",
                    "path_count": 1,
                    "truncated": False,
                    "paths": [
                        {
                            "nodes": ["A", "B", "D"],
                            "edges": [
                                {"from": "A", "to": "B"},
                                {"from": "B", "to": "D"},
                            ],
                        }
                    ],
                }
            )

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/admin/graph/path",
                    params={
                        "source": "A",
                        "target": "D",
                        "mode": "shortest",
                        "scope": "my",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["path_count"] == 1
        assert body["paths"][0]["nodes"] == ["A", "B", "D"]
        assert body["paths"][0]["edges"][0] == {
            "from_node": "A",
            "to_node": "B",
        }

    @pytest.mark.asyncio
    async def test_file_scope_requires_document_id(self):
        app = _make_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/graph/path",
                params={
                    "source": "A",
                    "target": "D",
                    "mode": "shortest",
                    "scope": "file",
                },
            )

        assert resp.status_code == 400
        assert "document_id" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_file_scope_checks_access(self):
        app = _make_app()

        with patch("trustdocs.admin.db") as mock_db:
            mock_db.find_one = AsyncMock(
                side_effect=[
                    {
                        "id": "doc-1",
                        "owner_id": "someone-else",
                        "status": "active",
                        "coc_node_hash": "root-1",
                    },
                    None,
                ]
            )

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/admin/graph/path",
                    params={
                        "source": "A",
                        "target": "D",
                        "mode": "shortest",
                        "scope": "file",
                        "document_id": "doc-1",
                    },
                )

        assert resp.status_code == 403
        assert "access denied" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_all_mode_returns_multiple_paths(self):
        app = _make_app()

        with patch("trustdocs.admin.trustflow") as mock_tf:
            mock_tf.get_graph_paths_for_peer = AsyncMock(
                return_value={
                    "mode": "all",
                    "source": "A",
                    "target": "D",
                    "path_count": 2,
                    "truncated": False,
                    "paths": [
                        {
                            "nodes": ["A", "B", "D"],
                            "edges": [
                                {"from": "A", "to": "B"},
                                {"from": "B", "to": "D"},
                            ],
                        },
                        {
                            "nodes": ["A", "C", "D"],
                            "edges": [
                                {"from": "A", "to": "C"},
                                {"from": "C", "to": "D"},
                            ],
                        },
                    ],
                }
            )

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/admin/graph/path",
                    params={
                        "source": "A",
                        "target": "D",
                        "mode": "all",
                        "scope": "my",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["path_count"] == 2
        assert len(body["paths"]) == 2
