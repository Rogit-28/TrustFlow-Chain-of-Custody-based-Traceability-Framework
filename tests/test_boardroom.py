"""Tests for the boardroom (Inner Circle) routes.

Exercises all endpoints: create boardroom, list boardrooms, create proposal
(with and without timelock), list proposals, approve, and unlock.
All database calls are mocked so no PostgreSQL or in-memory state is required.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from trustdocs.boardroom.routes import router
from trustdocs.auth.dependencies import get_current_user
from coc_framework.core.secret_sharing import Share

# ── Test fixtures ─────────────────────────────────────────────────────────────

ALICE_ID = str(uuid.uuid4())
BOB_ID = str(uuid.uuid4())
CAROL_ID = str(uuid.uuid4())

ALICE = {
    "id": ALICE_ID,
    "username": "alice",
    "peer_id": "peer-alice",
    "email": "alice@test.com",
}
BOB = {
    "id": BOB_ID,
    "username": "bob",
    "peer_id": "peer-bob",
    "email": "bob@test.com",
}
CAROL = {
    "id": CAROL_ID,
    "username": "carol",
    "peer_id": "peer-carol",
    "email": "carol@test.com",
}

BOARDROOM_ID = str(uuid.uuid4())
PROPOSAL_ID = str(uuid.uuid4())


def _make_app(current_user: dict = ALICE) -> FastAPI:
    """Build a minimal FastAPI app with boardroom router and auth overridden."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


def _make_shares(content: str, threshold: int, n: int):
    """Helper that calls the real Shamir split for test data."""
    from coc_framework.core.secret_sharing import split_secret

    shares, _ = split_secret(content, threshold, n)
    return shares


# ── Create boardroom ─────────────────────────────────────────────────────────


class TestCreateBoardroom:
    """POST /boardrooms"""

    @pytest.mark.asyncio
    async def test_create_boardroom_success(self):
        app = _make_app()

        mock_boardroom = {"id": BOARDROOM_ID, "name": "Alpha", "threshold_m": 2}

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[ALICE, BOB])
            mock_db.insert = AsyncMock(side_effect=[mock_boardroom, {}, {}])
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/boardrooms",
                    json={
                        "name": "Alpha",
                        "threshold_m": 2,
                        "member_usernames": ["alice", "bob"],
                    },
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["boardroom_id"] == BOARDROOM_ID
            assert "created" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_create_boardroom_member_not_found(self):
        app = _make_app()

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            # alice exists, bob does not
            mock_db.find_one = AsyncMock(side_effect=[ALICE, None])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/boardrooms",
                    json={
                        "name": "Alpha",
                        "threshold_m": 2,
                        "member_usernames": ["alice", "bob"],
                    },
                )
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_boardroom_invalid_threshold_too_high(self):
        app = _make_app()

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow"),
        ):
            mock_db.find_one = AsyncMock(side_effect=[ALICE, BOB])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/boardrooms",
                    json={
                        "name": "Alpha",
                        "threshold_m": 5,
                        "member_usernames": ["alice", "bob"],
                    },
                )
            assert resp.status_code == 400
            assert "threshold" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_boardroom_invalid_threshold_too_low(self):
        app = _make_app()

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow"),
        ):
            mock_db.find_one = AsyncMock(side_effect=[ALICE, BOB])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/boardrooms",
                    json={
                        "name": "Alpha",
                        "threshold_m": 1,
                        "member_usernames": ["alice", "bob"],
                    },
                )
            assert resp.status_code == 400
            assert "threshold" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_boardroom_creator_auto_added(self):
        """The creator's username is automatically added to the member list."""
        app = _make_app()
        mock_boardroom = {"id": BOARDROOM_ID, "name": "Solo", "threshold_m": 2}

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            # alice is looked up (auto-added), bob is looked up
            mock_db.find_one = AsyncMock(side_effect=[BOB, ALICE])
            mock_db.insert = AsyncMock(side_effect=[mock_boardroom, {}, {}])
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/boardrooms",
                    json={
                        "name": "Solo",
                        "threshold_m": 2,
                        "member_usernames": ["bob"],
                    },
                )
            assert resp.status_code == 200


# ── List boardrooms ──────────────────────────────────────────────────────────


class TestListBoardrooms:
    """GET /boardrooms"""

    @pytest.mark.asyncio
    async def test_list_boardrooms_success(self):
        app = _make_app()

        boardroom = {
            "id": uuid.UUID(BOARDROOM_ID),
            "name": "Alpha",
            "threshold_m": 2,
            "created_at": datetime.now(timezone.utc),
        }

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_many = AsyncMock(
                side_effect=[
                    [
                        {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
                    ],  # memberships
                    [
                        {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID},
                        {"boardroom_id": BOARDROOM_ID, "user_id": BOB_ID},
                    ],  # members
                ]
            )
            mock_db.find_one = AsyncMock(return_value=boardroom)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/boardrooms")

            assert resp.status_code == 200
            body = resp.json()
            assert len(body["boardrooms"]) == 1
            assert body["boardrooms"][0]["total_members"] == 2

    @pytest.mark.asyncio
    async def test_list_boardrooms_empty(self):
        app = _make_app()

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_many = AsyncMock(return_value=[])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/boardrooms")

            assert resp.status_code == 200
            assert resp.json()["boardrooms"] == []


# ── Create proposal ──────────────────────────────────────────────────────────


class TestCreateProposal:
    """POST /boardrooms/{boardroom_id}/proposals"""

    @pytest.mark.asyncio
    async def test_create_proposal_success(self):
        app = _make_app()

        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        members = [
            {"user_id": ALICE_ID},
            {"user_id": BOB_ID},
            {"user_id": CAROL_ID},
        ]
        proposal = {"id": PROPOSAL_ID, "title": "Budget Q1", "status": "pending"}

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=members)
            mock_db.insert = AsyncMock(
                side_effect=[proposal, {}, {}, {}]  # proposal + 3 shares
            )
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/boardrooms/{BOARDROOM_ID}/proposals",
                    json={"title": "Budget Q1", "content": "Confidential data"},
                )

            assert resp.status_code == 200
            body = resp.json()
            assert body["proposal_id"] == PROPOSAL_ID
            assert "split" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_create_proposal_not_a_member(self):
        app = _make_app()

        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(side_effect=[boardroom, None])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/boardrooms/{BOARDROOM_ID}/proposals",
                    json={"title": "Secret", "content": "data"},
                )

            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_proposal_boardroom_not_found(self):
        app = _make_app()

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/boardrooms/{BOARDROOM_ID}/proposals",
                    json={"title": "Secret", "content": "data"},
                )

            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_proposal_with_timelock(self):
        """When ttl_seconds is provided, content is time-lock encrypted before splitting."""
        app = _make_app()

        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        members = [{"user_id": ALICE_ID}, {"user_id": BOB_ID}]
        proposal = {"id": PROPOSAL_ID, "title": "TimeLocked", "status": "pending"}

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)
        mock_encrypted = MagicMock()
        mock_encrypted.metadata.lock_id = "lock-123"
        mock_encrypted.metadata.expires_at = expires_at.isoformat()
        mock_encrypted.to_dict.return_value = {
            "ciphertext": "abc",
            "metadata": {"lock_id": "lock-123"},
        }

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=members)
            mock_db.insert = AsyncMock(
                side_effect=[proposal, {}, {}]  # proposal + 2 shares
            )
            mock_tf.timelock_engine.encrypt.return_value = mock_encrypted
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/boardrooms/{BOARDROOM_ID}/proposals",
                    json={
                        "title": "TimeLocked",
                        "content": "Secret",
                        "ttl_seconds": 300,
                    },
                )

            assert resp.status_code == 200
            body = resp.json()
            assert "expires_at" in body
            mock_tf.timelock_engine.encrypt.assert_called_once_with("Secret", 300)


# ── Approve proposal ─────────────────────────────────────────────────────────


class TestApproveProposal:
    """POST /boardrooms/proposals/{proposal_id}/approve"""

    @pytest.mark.asyncio
    async def test_approve_success_below_threshold(self):
        app = _make_app()

        share_record = {
            "id": str(uuid.uuid4()),
            "proposal_id": PROPOSAL_ID,
            "user_id": ALICE_ID,
            "submitted": False,
        }
        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "status": "pending",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(
                side_effect=[share_record, proposal, boardroom]
            )
            mock_db.update_one = AsyncMock(return_value=share_record)
            mock_db.find_many = AsyncMock(
                return_value=[{**share_record, "submitted": True}]
            )
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/boardrooms/proposals/{PROPOSAL_ID}/approve")

            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "pending"
            assert "yielded" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_approve_reaches_threshold(self):
        app = _make_app()

        share_record = {
            "id": str(uuid.uuid4()),
            "proposal_id": PROPOSAL_ID,
            "user_id": ALICE_ID,
            "submitted": False,
        }
        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "status": "pending",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}

        # Two shares now submitted — meets threshold of 2
        submitted_shares = [
            {**share_record, "submitted": True},
            {
                "id": str(uuid.uuid4()),
                "proposal_id": PROPOSAL_ID,
                "user_id": BOB_ID,
                "submitted": True,
            },
        ]

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(
                side_effect=[share_record, proposal, boardroom]
            )
            mock_db.update_one = AsyncMock(return_value=share_record)
            mock_db.find_many = AsyncMock(return_value=submitted_shares)
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/boardrooms/proposals/{PROPOSAL_ID}/approve")

            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "executed"
            assert "threshold met" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_approve_share_not_found(self):
        app = _make_app()

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/boardrooms/proposals/{PROPOSAL_ID}/approve")

            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_already_submitted(self):
        app = _make_app()

        share_record = {
            "id": str(uuid.uuid4()),
            "proposal_id": PROPOSAL_ID,
            "user_id": ALICE_ID,
            "submitted": True,
        }

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(return_value=share_record)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/boardrooms/proposals/{PROPOSAL_ID}/approve")

            assert resp.status_code == 400
            assert "already" in resp.json()["detail"].lower()


# ── Unlock proposal ──────────────────────────────────────────────────────────


class TestUnlockProposal:
    """GET /boardrooms/proposals/{proposal_id}/unlock"""

    def _make_shares_and_records(self, content: str, threshold: int, n: int):
        """Build share records with real Shamir shares for reconstruction testing."""
        shares = _make_shares(content, threshold, n)
        user_ids = [ALICE_ID, BOB_ID, CAROL_ID][:n]
        records = []
        for i, share in enumerate(shares):
            records.append(
                {
                    "id": str(uuid.uuid4()),
                    "proposal_id": PROPOSAL_ID,
                    "user_id": user_ids[i],
                    "share_data": share.to_dict(),
                    "submitted": True,
                }
            )
        return records

    @pytest.mark.asyncio
    async def test_unlock_success_with_watermark(self):
        app = _make_app()

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Budget Q1",
            "status": "executed",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        share_records = self._make_shares_and_records("Confidential data", 2, 3)

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[proposal, boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=share_records)
            mock_tf.stegano_engine.embed_watermark.return_value = (
                "Confidential data [watermarked]"
            )
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 200
            body = resp.json()
            assert body["title"] == "Budget Q1"
            assert body["watermarked"] is True
            assert "watermarked" in body["content"].lower()
            mock_tf.stegano_engine.embed_watermark.assert_called_once_with(
                content="Confidential data", peer_id="peer-alice", depth=0
            )

    @pytest.mark.asyncio
    async def test_unlock_insufficient_approvals(self):
        app = _make_app()

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Budget Q1",
            "status": "pending",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}

        # Only 1 share submitted, threshold is 2
        share_records = [
            {
                "id": str(uuid.uuid4()),
                "proposal_id": PROPOSAL_ID,
                "user_id": ALICE_ID,
                "share_data": {},
                "submitted": True,
            },
            {
                "id": str(uuid.uuid4()),
                "proposal_id": PROPOSAL_ID,
                "user_id": BOB_ID,
                "share_data": {},
                "submitted": False,
            },
        ]

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(side_effect=[proposal, boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=share_records)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 403
            assert "threshold" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_unlock_not_a_member(self):
        app = _make_app()

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Budget Q1",
            "status": "executed",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(
                side_effect=[proposal, boardroom, None]  # no membership
            )

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unlock_proposal_not_found(self):
        app = _make_app()

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unlock_with_expired_timelock(self):
        """Unlock should be denied when the time-lock has expired."""
        app = _make_app()

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Expired Doc",
            "status": "executed",
            "lock_id": "lock-expired",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        share_records = self._make_shares_and_records("Secret", 2, 3)

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[proposal, boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=share_records)

            from coc_framework.core.timelock import TimeLockStatus

            mock_tf.timelock_engine.get_status.return_value = TimeLockStatus.EXPIRED

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 403
            assert "expired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_unlock_with_destroyed_timelock(self):
        """Unlock should be denied when the time-lock was manually destroyed."""
        app = _make_app()

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Destroyed Doc",
            "status": "executed",
            "lock_id": "lock-destroyed",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        share_records = self._make_shares_and_records("Secret", 2, 3)

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[proposal, boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=share_records)

            from coc_framework.core.timelock import TimeLockStatus

            mock_tf.timelock_engine.get_status.return_value = TimeLockStatus.DESTROYED

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 403
            assert "destroyed" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_unlock_watermark_failure_returns_unwatermarked(self):
        """If watermarking fails, the route still returns content (unwatermarked)."""
        app = _make_app()

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Doc",
            "status": "executed",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        share_records = self._make_shares_and_records("Plain text", 2, 3)

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[proposal, boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=share_records)
            mock_tf.stegano_engine.embed_watermark.side_effect = RuntimeError(
                "Engine error"
            )
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 200
            body = resp.json()
            assert body["content"] == "Plain text"
            assert body["watermarked"] is True  # flag is still set in route


# ── List proposals ───────────────────────────────────────────────────────────


class TestListProposals:
    """GET /boardrooms/{boardroom_id}/proposals"""

    @pytest.mark.asyncio
    async def test_list_proposals_success(self):
        app = _make_app()

        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}
        proposal = {
            "id": uuid.UUID(PROPOSAL_ID),
            "boardroom_id": uuid.UUID(BOARDROOM_ID),
            "initiator_id": uuid.UUID(ALICE_ID),
            "title": "Budget Q1",
            "status": "pending",
        }
        shares = [
            {
                "id": str(uuid.uuid4()),
                "proposal_id": PROPOSAL_ID,
                "user_id": ALICE_ID,
                "submitted": True,
            },
            {
                "id": str(uuid.uuid4()),
                "proposal_id": PROPOSAL_ID,
                "user_id": BOB_ID,
                "submitted": False,
            },
        ]
        initiator = {"username": "alice"}

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(side_effect=[membership, initiator])
            mock_db.find_many = AsyncMock(side_effect=[[proposal], shares])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/{BOARDROOM_ID}/proposals")

            assert resp.status_code == 200
            body = resp.json()
            assert len(body["proposals"]) == 1
            p = body["proposals"][0]
            assert p["approvals"] == 1
            assert p["user_has_approved"] is True
            assert p["has_timelock"] is False

    @pytest.mark.asyncio
    async def test_list_proposals_access_denied(self):
        app = _make_app()

        with patch("trustdocs.boardroom.routes.db") as mock_db:
            mock_db.find_one = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/{BOARDROOM_ID}/proposals")

            assert resp.status_code == 403


# ── End-to-end Shamir reconstruction ─────────────────────────────────────────


class TestShamirReconstruction:
    """Verify that the unlock route actually reconstructs content correctly
    when given real Shamir shares (not mocked)."""

    @pytest.mark.asyncio
    async def test_reconstruction_with_real_shares(self):
        """Full round-trip: split -> store as records -> unlock reconstructs."""
        app = _make_app()
        original = "This is highly classified content"

        shares = _make_shares(original, 2, 3)
        share_records = []
        user_ids = [ALICE_ID, BOB_ID, CAROL_ID]
        for i, share in enumerate(shares):
            share_records.append(
                {
                    "id": str(uuid.uuid4()),
                    "proposal_id": PROPOSAL_ID,
                    "user_id": user_ids[i],
                    "share_data": share.to_dict(),
                    "submitted": True,
                }
            )

        proposal = {
            "id": PROPOSAL_ID,
            "boardroom_id": BOARDROOM_ID,
            "title": "Classified",
            "status": "executed",
        }
        boardroom = {"id": BOARDROOM_ID, "threshold_m": 2}
        membership = {"boardroom_id": BOARDROOM_ID, "user_id": ALICE_ID}

        with (
            patch("trustdocs.boardroom.routes.db") as mock_db,
            patch("trustdocs.boardroom.routes.trustflow") as mock_tf,
        ):
            mock_db.find_one = AsyncMock(side_effect=[proposal, boardroom, membership])
            mock_db.find_many = AsyncMock(return_value=share_records)
            # Pass-through watermarking (return same content)
            mock_tf.stegano_engine.embed_watermark.side_effect = lambda content, **kw: (
                content
            )
            mock_tf.audit_log = MagicMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/boardrooms/proposals/{PROPOSAL_ID}/unlock")

            assert resp.status_code == 200
            body = resp.json()
            assert body["content"] == original


# ── Pydantic validation tests ────────────────────────────────────────────────


class TestRequestValidation:
    """Verify that Pydantic models reject invalid payloads."""

    @pytest.mark.asyncio
    async def test_proposal_ttl_below_minimum(self):
        """ttl_seconds must be >= 60."""
        app = _make_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/boardrooms/{BOARDROOM_ID}/proposals",
                json={"title": "Bad", "content": "data", "ttl_seconds": 10},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_boardroom_create_missing_fields(self):
        """Missing required fields should return 422."""
        app = _make_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/boardrooms",
                json={"name": "NoThreshold"},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_proposal_missing_content(self):
        """Missing content field should return 422."""
        app = _make_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/boardrooms/{BOARDROOM_ID}/proposals",
                json={"title": "NoContent"},
            )

        assert resp.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
