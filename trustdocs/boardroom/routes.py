"""Boardroom (Inner Circle) routes — threshold-based document execution.

Provides endpoints for creating boardrooms, initiating proposals that are
cryptographically split via Shamir's Secret Sharing, approving (yielding shares),
and unlocking (reconstructing) proposals once the threshold is met.

Features:
  - Optional time-lock encryption on proposals (auto-destruct timer)
  - Steganographic watermarking on unlock (per-reader leak attribution)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from trustdocs import database as db
from trustdocs.auth.dependencies import get_current_user
from coc_framework.core.secret_sharing import split_secret, reconstruct_secret, Share
from coc_framework.core.timelock import EncryptedContent, TimeLockStatus
from trustdocs.trustflow_service import trustflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/boardrooms", tags=["Boardrooms"])

# ── Models ───────────────────────────────────────────────────────────────────


class BoardroomCreateRequest(BaseModel):
    name: str
    threshold_m: int
    member_usernames: List[str]


class ProposalRequest(BaseModel):
    title: str
    content: str
    ttl_seconds: Optional[int] = Field(
        default=None,
        description="Optional auto-destruct timer in seconds. If set, the proposal "
        "content is time-lock encrypted and cannot be read after expiry.",
        ge=60,  # Minimum 1 minute
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("")
async def create_boardroom(
    req: BoardroomCreateRequest, user: dict = Depends(get_current_user)
):
    """Create a new Inner Circle Boardroom."""
    try:
        members = []
        member_usernames = set(req.member_usernames)
        member_usernames.add(user["username"])

        for username in member_usernames:
            member_user = await db.find_one("users", username=username)
            if not member_user:
                raise HTTPException(
                    status_code=404, detail=f"User {username} not found"
                )
            members.append(member_user)

        if len(members) < 2:
            raise HTTPException(
                status_code=400, detail="Boardroom must have at least 2 members"
            )

        if req.threshold_m > len(members) or req.threshold_m < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid threshold. Must be between 2 and {len(members)}",
            )

        boardroom = await db.insert(
            "boardrooms",
            {
                "name": req.name,
                "threshold_m": req.threshold_m,
            },
        )

        for member in members:
            await db.insert(
                "boardroom_members",
                {
                    "boardroom_id": boardroom["id"],
                    "user_id": member["id"],
                },
            )

        trustflow.audit_log.log_event(
            "BOARDROOM_CREATED",
            user["peer_id"],
            f"Boardroom ID: {boardroom['id']} Threshold: {req.threshold_m}",
        )

        return {
            "message": "Boardroom created successfully",
            "boardroom_id": str(boardroom["id"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create boardroom: {e}")
        raise HTTPException(status_code=500, detail="Internal error creating boardroom")


@router.get("")
async def list_boardrooms(user: dict = Depends(get_current_user)):
    """List boardrooms the user is a member of."""
    try:
        memberships = await db.find_many("boardroom_members", user_id=user["id"])
        results = []
        for m in memberships:
            br = await db.find_one("boardrooms", id=m["boardroom_id"])
            if br:
                br_members = await db.find_many(
                    "boardroom_members", boardroom_id=br["id"]
                )
                br["total_members"] = len(br_members)
                # Serialize UUID fields for JSON response
                br["id"] = str(br["id"])
                results.append(br)

        return {"boardrooms": results}

    except Exception as e:
        logger.exception(f"Failed to list boardrooms: {e}")
        raise HTTPException(status_code=500, detail="Internal error listing boardrooms")


@router.post("/{boardroom_id}/proposals")
async def create_proposal(
    boardroom_id: str, req: ProposalRequest, user: dict = Depends(get_current_user)
):
    """Initiate a confidential execution document.

    Splits content using Shamir's Secret Sharing. If ttl_seconds is provided,
    the content is first wrapped in time-lock encryption before splitting.
    """
    try:
        boardroom = await db.find_one("boardrooms", id=boardroom_id)
        if not boardroom:
            raise HTTPException(404, "Boardroom not found")

        membership = await db.find_one(
            "boardroom_members", boardroom_id=boardroom_id, user_id=user["id"]
        )
        if not membership:
            raise HTTPException(403, "You are not a member of this boardroom")

        all_members = await db.find_many("boardroom_members", boardroom_id=boardroom_id)
        num_shares = len(all_members)
        threshold = boardroom["threshold_m"]

        # ── Optional time-lock encryption ────────────────────────────────
        lock_id = None
        expires_at = None
        content_to_split = req.content

        if req.ttl_seconds is not None:
            try:
                encrypted = trustflow.timelock_engine.encrypt(
                    req.content, req.ttl_seconds
                )
                lock_id = encrypted.metadata.lock_id
                expires_at = datetime.fromisoformat(encrypted.metadata.expires_at)
                # Split the serialized encrypted payload instead of raw content
                import json

                content_to_split = json.dumps(encrypted.to_dict())
                logger.info(
                    f"Time-lock applied: lock_id={lock_id}, ttl={req.ttl_seconds}s"
                )
            except Exception as e:
                logger.exception(f"Time-lock encryption failed: {e}")
                raise HTTPException(500, "Failed to apply time-lock encryption")

        # ── Shamir split ─────────────────────────────────────────────────
        shares, _ = split_secret(content_to_split, threshold, num_shares)

        proposal_data = {
            "boardroom_id": boardroom_id,
            "initiator_id": user["id"],
            "title": req.title,
            "status": "pending",
        }
        if lock_id:
            proposal_data["lock_id"] = lock_id
        if expires_at:
            proposal_data["expires_at"] = expires_at

        proposal = await db.insert("boardroom_proposals", proposal_data)

        for idx, member in enumerate(all_members):
            share = shares[idx]
            await db.insert(
                "shamir_shares",
                {
                    "proposal_id": proposal["id"],
                    "user_id": member["user_id"],
                    "share_data": share.to_dict(),
                    "submitted": False,
                },
            )

        trustflow.audit_log.log_event(
            "PROPOSAL_INITIATED",
            user["peer_id"],
            f"Proposal ID: {proposal['id']}"
            + (f" | TimeLock TTL: {req.ttl_seconds}s" if req.ttl_seconds else ""),
        )

        result = {
            "message": "Proposal created and cryptographically split",
            "proposal_id": str(proposal["id"]),
        }
        if expires_at:
            result["expires_at"] = expires_at.isoformat()

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create proposal: {e}")
        raise HTTPException(status_code=500, detail="Internal error creating proposal")


@router.get("/{boardroom_id}/proposals")
async def list_proposals(boardroom_id: str, user: dict = Depends(get_current_user)):
    """List all proposals in a boardroom with approval status."""
    try:
        membership = await db.find_one(
            "boardroom_members", boardroom_id=boardroom_id, user_id=user["id"]
        )
        if not membership:
            raise HTTPException(403, "Access denied")

        proposals = await db.find_many("boardroom_proposals", boardroom_id=boardroom_id)
        results = []
        for p in proposals:
            shares = await db.find_many("shamir_shares", proposal_id=p["id"])
            submitted_count = sum(1 for s in shares if s["submitted"])

            user_share = next(
                (s for s in shares if str(s["user_id"]) == str(user["id"])), None
            )
            user_submitted = user_share["submitted"] if user_share else False

            initiator = await db.find_one("users", id=p["initiator_id"])
            p["initiator_username"] = initiator["username"] if initiator else "unknown"
            p["approvals"] = submitted_count
            p["user_has_approved"] = user_submitted
            # Serialize UUIDs for JSON
            p["id"] = str(p["id"])
            p["boardroom_id"] = str(p["boardroom_id"])
            p["initiator_id"] = str(p["initiator_id"])

            # Timelock info
            if p.get("lock_id"):
                p["has_timelock"] = True
                if p.get("expires_at"):
                    exp = p["expires_at"]
                    if isinstance(exp, datetime):
                        p["expires_at"] = exp.isoformat()
                    remaining = trustflow.timelock_engine.get_remaining_time(
                        p["lock_id"]
                    )
                    p["timelock_expired"] = remaining is None or remaining <= 0
                else:
                    p["timelock_expired"] = True
            else:
                p["has_timelock"] = False
                p["timelock_expired"] = False

            results.append(p)

        return {"proposals": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list proposals: {e}")
        raise HTTPException(status_code=500, detail="Internal error listing proposals")


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    """Yield cryptographic share to the reconstruction pool."""
    try:
        share_record = await db.find_one(
            "shamir_shares", proposal_id=proposal_id, user_id=user["id"]
        )
        if not share_record:
            raise HTTPException(404, "Share not found")

        if share_record["submitted"]:
            raise HTTPException(400, "Share already submitted")

        await db.update_one("shamir_shares", share_record["id"], submitted=True)

        trustflow.audit_log.log_event(
            "SHARE_SUBMITTED", user["peer_id"], f"Proposal ID: {proposal_id}"
        )

        proposal = await db.find_one("boardroom_proposals", id=proposal_id)
        if not proposal:
            raise HTTPException(404, "Proposal not found")

        boardroom = await db.find_one("boardrooms", id=proposal["boardroom_id"])
        if not boardroom:
            raise HTTPException(404, "Boardroom not found")

        threshold = boardroom["threshold_m"]
        all_shares = await db.find_many("shamir_shares", proposal_id=proposal_id)
        submitted_shares = [s for s in all_shares if s["submitted"]]

        response_msg = "Cryptographic share yielded to pool."
        if len(submitted_shares) >= threshold and proposal["status"] != "executed":
            await db.update_one("boardroom_proposals", proposal_id, status="executed")
            trustflow.audit_log.log_event(
                "PROPOSAL_EXECUTED",
                user["peer_id"],
                f"Threshold {threshold} met for Proposal {proposal_id}",
            )
            response_msg += " Threshold met. Document unlocked."

        return {
            "message": response_msg,
            "status": "executed" if len(submitted_shares) >= threshold else "pending",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to approve proposal: {e}")
        raise HTTPException(status_code=500, detail="Internal error approving proposal")


@router.get("/proposals/{proposal_id}/unlock")
async def unlock_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    """Reconstruct and read the execution document.

    If the proposal has a time-lock, the lock must still be active.
    The returned content is steganographically watermarked with the
    requesting user's peer_id for leak attribution.
    """
    try:
        proposal = await db.find_one("boardroom_proposals", id=proposal_id)
        if not proposal:
            raise HTTPException(404, "Proposal not found")

        boardroom = await db.find_one("boardrooms", id=proposal["boardroom_id"])
        if not boardroom:
            raise HTTPException(404, "Boardroom not found")

        membership = await db.find_one(
            "boardroom_members", boardroom_id=boardroom["id"], user_id=user["id"]
        )
        if not membership:
            raise HTTPException(403, "Access denied")

        all_shares = await db.find_many("shamir_shares", proposal_id=proposal_id)
        submitted_shares = [s for s in all_shares if s["submitted"]]

        if len(submitted_shares) < boardroom["threshold_m"]:
            raise HTTPException(
                403,
                f"Threshold not met. {len(submitted_shares)}/{boardroom['threshold_m']} approvals.",
            )

        # ── Reconstruct from shares ──────────────────────────────────────
        share_objects = []
        for record in submitted_shares[: boardroom["threshold_m"]]:
            share_objects.append(Share.from_dict(record["share_data"]))

        try:
            plaintext = reconstruct_secret(share_objects, hmac_key=None)
            if not plaintext:
                raise HTTPException(
                    500, "Cryptographic reconstruction failed. Invalid shares."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Shamir reconstruction error: {e}")
            raise HTTPException(500, "Cryptographic reconstruction failed.")

        # ── Time-lock decryption (if applicable) ─────────────────────────
        if proposal.get("lock_id"):
            lock_id = proposal["lock_id"]
            status = trustflow.timelock_engine.get_status(lock_id)

            if status == TimeLockStatus.EXPIRED:
                raise HTTPException(
                    403, "Content expired. The auto-destruct timer has elapsed."
                )
            if status == TimeLockStatus.DESTROYED:
                raise HTTPException(
                    403, "Content destroyed. The time-lock was manually revoked."
                )

            try:
                import json

                encrypted = EncryptedContent.from_dict(json.loads(plaintext))
                decrypted = trustflow.timelock_engine.decrypt(encrypted)
                if decrypted is None:
                    raise HTTPException(
                        403, "Content expired. The auto-destruct timer has elapsed."
                    )
                plaintext = decrypted
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Time-lock decryption error: {e}")
                raise HTTPException(500, "Failed to decrypt time-locked content.")

        # ── Steganographic watermarking ───────────────────────────────────
        # Embed an invisible watermark unique to this reader's peer_id.
        # If the content is later leaked, we can attribute it to this user.
        try:
            watermarked = trustflow.stegano_engine.embed_watermark(
                content=plaintext,
                peer_id=user["peer_id"],
                depth=0,
            )
            trustflow.audit_log.log_event(
                "PROPOSAL_UNLOCKED",
                user["peer_id"],
                f"Proposal {proposal_id} | Watermarked copy issued",
            )
        except Exception as e:
            logger.warning(f"Watermarking failed (returning unwatermarked): {e}")
            watermarked = plaintext
            trustflow.audit_log.log_event(
                "PROPOSAL_UNLOCKED",
                user["peer_id"],
                f"Proposal {proposal_id} | Watermarking failed",
            )

        result = {
            "title": proposal["title"],
            "content": watermarked,
            "status": proposal["status"],
            "watermarked": True,
        }

        if proposal.get("lock_id"):
            remaining = trustflow.timelock_engine.get_remaining_time(
                proposal["lock_id"]
            )
            result["timelock_remaining_seconds"] = remaining

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to unlock proposal: {e}")
        raise HTTPException(status_code=500, detail="Internal error unlocking proposal")
