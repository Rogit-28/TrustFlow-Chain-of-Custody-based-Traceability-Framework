import asyncio
import json
import logging
from typing import Optional, Dict, List, Any, Union
from coc_framework.core.network_sim import Network, Peer
from coc_framework.core.deletion_engine import DeletionEngine
from coc_framework.core.audit_log import AuditLog
from coc_framework.core.secret_sharing import SecretSharingEngine
from coc_framework.core.timelock import TimeLockEngine
from coc_framework.core.steganography import SteganoEngine
from coc_framework.core.validation import EventValidator, ValidationError
from coc_framework.config import ScenarioConfig, SimulationSettings
from coc_framework.interfaces.notification_handler import SilentNotificationHandler

logger = logging.getLogger(__name__)

# Configurable simulation constants
DEFAULT_TICK_DELAY_SECONDS = 2.0


class SimulationEngine:
    """In-memory orchestrator for CoC simulation scenarios.

    Accepts either a raw ``dict`` scenario or a :class:`ScenarioConfig` instance.
    Supports optional scenario/event validation, a message-id registry, and
    context-manager usage for automatic resource cleanup.
    """

    def __init__(
        self,
        scenario: Union[Dict[str, Any], "ScenarioConfig"],
        validate_scenario: bool = True,
        validate_events: bool = True,
    ):
        # Normalise input -------------------------------------------------
        if isinstance(scenario, ScenarioConfig):
            self.config: ScenarioConfig = scenario
            self.scenario: Dict[str, Any] = scenario.to_dict()
        else:
            self.config = ScenarioConfig.from_dict(scenario)
            self.scenario = scenario

        # Optional validation ---------------------------------------------
        if validate_scenario or validate_events:
            result = EventValidator.validate_scenario(self.scenario)
            if not result.is_valid:
                raise ValidationError(
                    "Scenario validation failed",
                    errors=result.errors,
                )

        # Core components --------------------------------------------------
        self.network = Network()
        self.audit_log = AuditLog()

        self.notification_handler = SilentNotificationHandler()
        self.deletion_engine = DeletionEngine(
            self.network,
            self.audit_log,
            self.notification_handler,
            self.network.peer_discovery,
        )

        # MVP Feature Engines (shared across all peers) --------------------
        settings = self.scenario.get("settings", {})
        self.enable_secret_sharing = settings.get("enable_secret_sharing", False)
        self.enable_timelock = settings.get("enable_timelock", False)
        self.enable_steganography = settings.get("enable_steganography", False)

        self.secret_sharing_engine: Optional[SecretSharingEngine] = None
        self.timelock_engine: Optional[TimeLockEngine] = None
        self.stegano_engine: Optional[SteganoEngine] = None

        if self.enable_secret_sharing:
            default_threshold = settings.get("secret_sharing_threshold", 3)
            self.secret_sharing_engine = SecretSharingEngine(
                default_threshold=default_threshold
            )
            logger.info("Secret Sharing enabled")

        if self.enable_timelock:
            cleanup_interval = settings.get("timelock_cleanup_interval", 1.0)
            self.timelock_engine = TimeLockEngine(cleanup_interval=cleanup_interval)
            logger.info("Time-Lock Encryption enabled")

        if self.enable_steganography:
            self.stegano_engine = SteganoEngine()
            logger.info("Steganographic Watermarking enabled")

        self.peers: Dict[str, Peer] = {}
        self.tick_count = 0

        # Track distributed shares for DISTRIBUTE_SHARES events
        self._distributed_shares: Dict[str, Dict[str, Any]] = {}

        # Message-id <-> node-hash registry --------------------------------
        self._message_registry: Dict[str, str] = {}

        # Load events and sort by time
        self.events = sorted(self.scenario.get("events", []), key=lambda x: x["time"])

        # Initialize the simulation
        self._setup_simulation()

    # -- Context manager ---------------------------------------------------

    def __enter__(self) -> "SimulationEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.shutdown()
        return False

    # -- Message registry helpers ------------------------------------------

    def _register_message(self, message_id: Optional[str], node_hash: str) -> None:
        """Register a human-readable message_id to a node_hash."""
        if message_id:
            self._message_registry[message_id] = node_hash

    def get_node_hash(self, message_id: str) -> Optional[str]:
        """Look up a node_hash by its human-readable message_id."""
        return self._message_registry.get(message_id)

    # -- Setup -------------------------------------------------------------

    def _setup_simulation(self):
        """Sets up the simulation based on the scenario file."""
        if "peers" in self.scenario:
            peer_setups = self.scenario.get("peers", [])
            for peer_config in peer_setups:
                peer_id = peer_config["id"]
                peer = Peer(
                    peer_id=peer_id,
                    deletion_engine=self.deletion_engine,
                    secret_sharing_engine=self.secret_sharing_engine,
                    timelock_engine=self.timelock_engine,
                    stegano_engine=self.stegano_engine,
                )
                self.peers[peer_id] = peer
                self.network.add_peer(peer)
        elif "settings" in self.scenario and "total_peers" in self.scenario.get(
            "settings", {}
        ):
            total_peers = self.scenario["settings"]["total_peers"]
            for i in range(total_peers):
                peer_id = f"peer_{i}"
                peer = Peer(
                    peer_id=peer_id,
                    deletion_engine=self.deletion_engine,
                    secret_sharing_engine=self.secret_sharing_engine,
                    timelock_engine=self.timelock_engine,
                    stegano_engine=self.stegano_engine,
                )
                self.peers[peer_id] = peer
                self.network.add_peer(peer)

        logger.info(f"Setup complete with {len(self.peers)} peers.")

    # -- Tick loop ---------------------------------------------------------

    async def tick(self, tick_delay: float = DEFAULT_TICK_DELAY_SECONDS):
        """Advances the simulation by one time step.

        Args:
            tick_delay: Seconds to wait for async operations to complete.
        """
        logger.debug(f"--- Tick {self.tick_count} ---")
        events_for_this_tick = [e for e in self.events if e["time"] == self.tick_count]
        for event in events_for_this_tick:
            try:
                self._handle_event(event)
            except Exception as e:
                logger.error(f"Error handling event {event}: {e}")

        await asyncio.sleep(tick_delay)
        self.tick_count += 1

    # -- Event dispatch ----------------------------------------------------

    def _handle_event(self, event):
        """Handles a single event from the scenario."""
        event_type = event.get("type")

        if event_type == "PEER_ONLINE":
            peer = self.peers.get(event["peer_id"])
            if peer:
                peer.go_online()
                logger.debug(
                    f"[Tick {self.tick_count}] Peer {peer.peer_id[:8]} goes online."
                )

        elif event_type == "PEER_OFFLINE":
            peer = self.peers.get(event["peer_id"])
            if peer:
                peer.go_offline()
                logger.debug(
                    f"[Tick {self.tick_count}] Peer {peer.peer_id[:8]} goes offline."
                )

        elif event_type == "CREATE_MESSAGE":
            self._handle_create_message(event)

        elif event_type == "FORWARD_MESSAGE":
            self._handle_forward_message(event)

        elif event_type == "DELETE_MESSAGE":
            self._handle_delete_message(event)

        # ============ NEW MVP EVENT TYPES ============

        elif event_type == "DISTRIBUTE_SHARES":
            self._handle_distribute_shares(event)

        elif event_type == "RECONSTRUCT_SECRET":
            self._handle_reconstruct_secret(event)

        elif event_type == "TIMELOCK_CONTENT":
            self._handle_timelock_content(event)

        elif event_type == "DESTROY_TIMELOCK":
            self._handle_destroy_timelock(event)

        elif event_type == "WATERMARK_FORWARD":
            self._handle_watermark_forward(event)

        elif event_type == "DETECT_LEAK":
            self._handle_detect_leak(event)

    # -- Core event handlers -----------------------------------------------

    def _handle_create_message(self, event):
        originator = self.peers.get(event["originator_id"])
        if not originator:
            return

        node = originator.create_coc_root(
            content=event["content"],
            recipient_ids=event["recipient_ids"],
        )

        # Register message_id -> node_hash if provided
        self._register_message(event.get("message_id"), node.node_hash)

        for recipient_id in event["recipient_ids"]:
            originator.send_message(
                recipient_id=recipient_id,
                message_type="coc_data",
                content={
                    "node_data": node.to_dict(),
                    "content": event["content"],
                },
            )
        logger.debug(
            f"[Tick {self.tick_count}] Peer {originator.peer_id[:8]} creates message."
        )

    def _handle_forward_message(self, event):
        sender = self.peers.get(event["sender_id"])
        if not sender:
            return

        # Resolve parent node — prefer parent_node_hash, fall back to
        # parent_message_id via registry
        parent_node_hash = event.get("parent_node_hash")
        if not parent_node_hash:
            parent_message_id = event.get("parent_message_id")
            if parent_message_id:
                parent_node_hash = self.get_node_hash(parent_message_id)

        if not parent_node_hash:
            logger.warning(
                f"[Tick {self.tick_count}] FORWARD_MESSAGE: no parent reference resolved"
            )
            return

        parent_node = sender.storage.get_node(parent_node_hash)
        if not parent_node:
            logger.warning(
                f"Parent node {parent_node_hash} not found in "
                f"{sender.peer_id}'s storage"
            )
            return

        # Check if watermarking is enabled and requested
        use_watermark = event.get("use_watermark", False) and self.enable_steganography

        if use_watermark:
            content = sender.storage.get_content(parent_node.content_hash)
            if content:
                child_node = sender.forward_with_watermark(
                    parent_node=parent_node,
                    recipient_ids=event["recipient_ids"],
                    content=content,
                )
                self._register_message(event.get("message_id"), child_node.node_hash)
                logger.debug(
                    f"[Tick {self.tick_count}] Peer {sender.peer_id[:8]} "
                    f"forwards message with watermark."
                )
                return

        child_node = sender.forward_coc_message(
            parent_node=parent_node,
            recipient_ids=event["recipient_ids"],
        )

        self._register_message(event.get("message_id"), child_node.node_hash)

        for recipient_id in event["recipient_ids"]:
            sender.send_message(
                recipient_id=recipient_id,
                message_type="coc_data",
                content={
                    "node_data": child_node.to_dict(),
                    "content": child_node.content_hash,
                },
            )
        logger.debug(
            f"[Tick {self.tick_count}] Peer {sender.peer_id[:8]} forwards message."
        )

    def _handle_delete_message(self, event):
        originator = self.peers.get(event["originator_id"])
        if not originator:
            return

        # Resolve node_hash — prefer direct hash, fall back to message_id
        node_hash = event.get("node_hash")
        if not node_hash:
            message_id = event.get("message_id")
            if message_id:
                node_hash = self.get_node_hash(message_id)

        if not node_hash:
            logger.warning(
                f"[Tick {self.tick_count}] DELETE_MESSAGE: no node reference resolved"
            )
            return

        node_to_delete = originator.storage.get_node(node_hash)

        if node_to_delete:
            originator.initiate_deletion(node_to_delete)
            logger.debug(
                f"[Tick {self.tick_count}] Peer {originator.peer_id[:8]} "
                f"initiates deletion."
            )

    # -- MVP event handlers ------------------------------------------------

    def _handle_distribute_shares(self, event):
        """Handle DISTRIBUTE_SHARES event."""
        if not self.enable_secret_sharing:
            logger.warning(
                f"[Tick {self.tick_count}] DISTRIBUTE_SHARES failed: "
                f"secret sharing not enabled"
            )
            return

        originator = self.peers.get(event["originator_id"])
        if not originator:
            logger.warning(
                f"[Tick {self.tick_count}] DISTRIBUTE_SHARES failed: "
                f"originator not found"
            )
            return

        try:
            share_map = originator.distribute_shares(
                content=event["content"],
                recipient_ids=event["recipient_ids"],
                threshold=event.get("threshold"),
            )

            content_hash = list(share_map.values())[0].content_hash
            self._distributed_shares[content_hash] = {
                "originator": event["originator_id"],
                "recipients": event["recipient_ids"],
                "share_map": share_map,
            }

            logger.debug(
                f"[Tick {self.tick_count}] Peer {originator.peer_id[:8]} "
                f"distributed {len(share_map)} shares"
            )
        except Exception as e:
            logger.error(f"[Tick {self.tick_count}] DISTRIBUTE_SHARES failed: {e}")

    def _handle_reconstruct_secret(self, event):
        """Handle RECONSTRUCT_SECRET event."""
        if not self.enable_secret_sharing:
            logger.warning(
                f"[Tick {self.tick_count}] RECONSTRUCT_SECRET failed: "
                f"secret sharing not enabled"
            )
            return

        requester = self.peers.get(event["requester_id"])
        if not requester:
            logger.warning(
                f"[Tick {self.tick_count}] RECONSTRUCT_SECRET failed: "
                f"requester not found"
            )
            return

        content_hash = event["content_hash"]
        contributor_ids = event.get("contributor_ids", [])

        collected_shares = {}
        for peer_id in contributor_ids:
            peer = self.peers.get(peer_id)
            if peer and content_hash in peer._received_shares:
                collected_shares[peer_id] = peer._received_shares[content_hash]

        try:
            reconstructed = requester.collect_and_reconstruct(
                content_hash, collected_shares
            )
            if reconstructed:
                logger.debug(
                    f"[Tick {self.tick_count}] Peer {requester.peer_id[:8]} "
                    f"reconstructed secret successfully"
                )
                requester.storage.add_content(content_hash, reconstructed)
            else:
                logger.warning(
                    f"[Tick {self.tick_count}] Peer {requester.peer_id[:8]} "
                    f"failed to reconstruct secret"
                )
        except Exception as e:
            logger.error(f"[Tick {self.tick_count}] RECONSTRUCT_SECRET failed: {e}")

    def _handle_timelock_content(self, event):
        """Handle TIMELOCK_CONTENT event."""
        if not self.enable_timelock:
            logger.warning(
                f"[Tick {self.tick_count}] TIMELOCK_CONTENT failed: "
                f"timelock not enabled"
            )
            return

        originator = self.peers.get(event["originator_id"])
        if not originator:
            logger.warning(
                f"[Tick {self.tick_count}] TIMELOCK_CONTENT failed: "
                f"originator not found"
            )
            return

        try:
            encrypted = originator.create_timelocked_content(
                content=event["content"],
                ttl_seconds=event["ttl_seconds"],
                recipient_ids=event.get("recipient_ids"),
            )
            logger.debug(
                f"[Tick {self.tick_count}] Peer {originator.peer_id[:8]} "
                f"created time-locked content (TTL={event['ttl_seconds']}s)"
            )
        except Exception as e:
            logger.error(f"[Tick {self.tick_count}] TIMELOCK_CONTENT failed: {e}")

    def _handle_destroy_timelock(self, event):
        """Handle DESTROY_TIMELOCK event."""
        if not self.enable_timelock:
            logger.warning(
                f"[Tick {self.tick_count}] DESTROY_TIMELOCK failed: "
                f"timelock not enabled"
            )
            return

        peer = self.peers.get(event["peer_id"])
        if not peer:
            logger.warning(
                f"[Tick {self.tick_count}] DESTROY_TIMELOCK failed: peer not found"
            )
            return

        success = peer.destroy_timelock(event["lock_id"])
        if success:
            logger.debug(
                f"[Tick {self.tick_count}] Peer {peer.peer_id[:8]} "
                f"destroyed time-lock {event['lock_id'][:16]}"
            )
        else:
            logger.warning(
                f"[Tick {self.tick_count}] DESTROY_TIMELOCK failed: "
                f"lock not found or already expired"
            )

    def _handle_watermark_forward(self, event):
        """Handle WATERMARK_FORWARD event — forward with invisible watermarking."""
        if not self.enable_steganography:
            logger.warning(
                f"[Tick {self.tick_count}] WATERMARK_FORWARD failed: "
                f"steganography not enabled"
            )
            return

        sender = self.peers.get(event["sender_id"])
        if not sender:
            logger.warning(
                f"[Tick {self.tick_count}] WATERMARK_FORWARD failed: sender not found"
            )
            return

        parent_node = sender.storage.get_node(event["parent_node_hash"])
        if not parent_node:
            logger.warning(
                f"[Tick {self.tick_count}] WATERMARK_FORWARD failed: "
                f"parent node not found"
            )
            return

        content = sender.storage.get_content(parent_node.content_hash)
        if not content:
            logger.warning(
                f"[Tick {self.tick_count}] WATERMARK_FORWARD failed: content not found"
            )
            return

        try:
            child_node = sender.forward_with_watermark(
                parent_node=parent_node,
                recipient_ids=event["recipient_ids"],
                content=content,
            )
            logger.debug(
                f"[Tick {self.tick_count}] Peer {sender.peer_id[:8]} forwarded "
                f"with watermark to {len(event['recipient_ids'])} recipients"
            )
        except Exception as e:
            logger.error(f"[Tick {self.tick_count}] WATERMARK_FORWARD failed: {e}")

    def _handle_detect_leak(self, event):
        """Handle DETECT_LEAK event — attempt to identify leaker from watermarked content."""
        if not self.enable_steganography:
            logger.warning(
                f"[Tick {self.tick_count}] DETECT_LEAK failed: "
                f"steganography not enabled"
            )
            return

        investigator = self.peers.get(event["investigator_id"])
        if not investigator:
            logger.warning(
                f"[Tick {self.tick_count}] DETECT_LEAK failed: investigator not found"
            )
            return

        suspect_ids = event.get("suspect_ids", list(self.peers.keys()))

        for suspect_id in suspect_ids:
            self.stegano_engine.register_peer(suspect_id)

        result = self.stegano_engine.extract_watermark(
            content=event["leaked_content"],
            candidate_peers=suspect_ids,
        )

        if result.success:
            logger.info(
                f"[Tick {self.tick_count}] LEAK DETECTED: "
                f"Peer {result.peer_id[:8]} identified as leaker "
                f"(confidence: {result.confidence:.1%}, method: {result.method})"
            )
        else:
            logger.debug(
                f"[Tick {self.tick_count}] DETECT_LEAK: "
                f"No watermark found or leaker not in suspect list"
            )

    # -- State / lifecycle -------------------------------------------------

    def get_simulation_state(self):
        """Returns the current state of the simulation for serialization."""
        return {
            "tick": self.tick_count,
            "peers": self.peers,
            "features": {
                "secret_sharing": self.enable_secret_sharing,
                "timelock": self.enable_timelock,
                "steganography": self.enable_steganography,
            },
            "distributed_shares": list(self._distributed_shares.keys()),
            "message_registry": dict(self._message_registry),
        }

    def shutdown(self):
        """Clean up resources when simulation ends."""
        if self.timelock_engine:
            self.timelock_engine.shutdown()
            logger.info("TimeLockEngine shutdown complete")
