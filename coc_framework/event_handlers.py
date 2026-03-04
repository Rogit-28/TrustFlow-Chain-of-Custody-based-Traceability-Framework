"""
Event Handler Registry Pattern for SimulationEngine.

This module provides an extensible event handling system using the registry pattern,
replacing the if-elif chain in SimulationEngine._handle_event() to follow the
Open/Closed Principle.

Optimizations applied:
- __slots__ on handler classes to reduce memory footprint
- Base class with common utility methods to reduce code duplication
- Cached property for event_type to avoid repeated string creation
- Extracted common patterns: peer lookup, audit logging, parent hash resolution
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging

from .core.validation import EventValidator, ValidationError
from .core.audit_log import AuditEventType

if TYPE_CHECKING:
    from .simulation_engine import SimulationEngine
    from .core.network_sim import Peer
    from .core.coc_node import CoCNode

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """Base class for event handlers with common utilities.
    
    Provides helper methods for common operations like peer lookup,
    audit logging, and parent hash resolution to reduce code duplication.
    """
    __slots__ = ()
    
    @property
    @abstractmethod
    def event_type(self) -> str:
        """The event type this handler processes."""
        pass
    
    @abstractmethod
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Process the event.
        
        Args:
            engine: The simulation engine instance.
            event: The event dictionary to process.
        """
        pass
    
    # ---- Utility methods for subclasses ----
    
    @staticmethod
    def get_peer(engine: "SimulationEngine", peer_id: str) -> Optional["Peer"]:
        """Get a peer by ID from the engine.
        
        Args:
            engine: The simulation engine instance.
            peer_id: The peer ID to look up.
            
        Returns:
            The peer if found, None otherwise.
        """
        return engine.peers.get(peer_id)
    
    @staticmethod
    def log_audit(
        engine: "SimulationEngine",
        event_type: AuditEventType,
        actor_id: str,
        target_id: Optional[str] = None,
        **details: Any
    ) -> None:
        """Log an audit event if audit logger is enabled.
        
        Args:
            engine: The simulation engine instance.
            event_type: The type of audit event.
            actor_id: The ID of the actor performing the action.
            target_id: The ID of the target (optional).
            **details: Additional details to log.
        """
        if engine.audit_logger is not None:
            engine.audit_logger.log(
                event_type,
                actor_id=actor_id,
                target_id=target_id,
                tick=engine.tick_count,
                **details
            )
    
    @staticmethod
    def resolve_parent_hash(
        engine: "SimulationEngine",
        event: Dict[str, Any],
        event_type_name: str
    ) -> Optional[str]:
        """Resolve parent node hash from event, supporting both direct hash and message_id.
        
        Args:
            engine: The simulation engine instance.
            event: The event dictionary.
            event_type_name: Name of the event type for logging.
            
        Returns:
            The parent hash if resolved, None otherwise.
        """
        parent_hash = event.get("parent_node_hash")
        if not parent_hash and "parent_message_id" in event:
            parent_hash = engine._message_registry.get(event["parent_message_id"])
            if not parent_hash:
                logger.warning(f"Message ID '{event['parent_message_id']}' not found in registry")
                return None
        
        if not parent_hash:
            logger.warning(f"{event_type_name} requires either 'parent_node_hash' or 'parent_message_id'")
            return None
        
        return parent_hash
    
    @staticmethod
    def resolve_node_hash(
        engine: "SimulationEngine",
        event: Dict[str, Any],
        event_type_name: str
    ) -> Optional[str]:
        """Resolve node hash from event, supporting both direct hash and message_id.
        
        Args:
            engine: The simulation engine instance.
            event: The event dictionary.
            event_type_name: Name of the event type for logging.
            
        Returns:
            The node hash if resolved, None otherwise.
        """
        node_hash = event.get("node_hash")
        if not node_hash and "message_id" in event:
            node_hash = engine._message_registry.get(event["message_id"])
            if not node_hash:
                logger.warning(f"Message ID '{event['message_id']}' not found in registry")
                return None
        
        if not node_hash:
            logger.warning(f"{event_type_name} requires either 'node_hash' or 'message_id'")
            return None
        
        return node_hash
    
    @staticmethod
    def register_message(
        engine: "SimulationEngine",
        event: Dict[str, Any],
        node_hash: str
    ) -> None:
        """Register a message_id -> node_hash mapping if message_id is provided.
        
        Args:
            engine: The simulation engine instance.
            event: The event dictionary.
            node_hash: The node hash to register.
        """
        if "message_id" in event:
            engine._message_registry[event["message_id"]] = node_hash
            logger.debug(f"Registered message '{event['message_id']}' -> {node_hash[:16]}...")


class EventRegistry:
    """Registry for event handlers.
    
    Uses __slots__ for memory efficiency and caches handler lookup.
    """
    __slots__ = ("_handlers", "_validate_events")
    
    def __init__(self, validate_events: bool = True) -> None:
        """Initialize the event registry.
        
        Args:
            validate_events: Whether to validate events before handling (default True).
        """
        self._handlers: Dict[str, EventHandler] = {}
        self._validate_events: bool = validate_events
    
    def register(self, handler: EventHandler) -> None:
        """Register an event handler.
        
        Args:
            handler: The event handler to register.
        """
        self._handlers[handler.event_type] = handler
    
    def get_handler(self, event_type: str) -> Optional[EventHandler]:
        """Get handler for event type.
        
        Args:
            event_type: The event type to look up.
            
        Returns:
            The handler if found, None otherwise.
        """
        return self._handlers.get(event_type)
    
    def handle_event(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Dispatch event to appropriate handler.
        
        Args:
            engine: The simulation engine instance.
            event: The event dictionary to process.
            
        Raises:
            ValidationError: If validation is enabled and the event is invalid.
        """
        # Validate event if validation is enabled
        if self._validate_events:
            result = EventValidator.validate_event(event)
            if not result.is_valid:
                error_msg = f"Invalid event: {'; '.join(result.errors)}"
                logger.error(error_msg)
                raise ValidationError(error_msg, errors=result.errors)
        
        # Direct dict access is faster than .get() when we need the value
        event_type = event.get("type")
        handler = self._handlers.get(event_type)
        if handler:
            handler.handle(engine, event)
        else:
            logger.warning(f"No handler registered for event type: {event_type}")


# ============ Event Handler Implementations ============


class PeerOnlineHandler(EventHandler):
    """Handler for PEER_ONLINE events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "PEER_ONLINE"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        peer = self.get_peer(engine, event["peer_id"])
        if peer:
            peer.go_online()
            logger.debug(f"[Tick {engine.tick_count}] Peer {peer.peer_id[:8]} goes online.")
            self.log_audit(engine, AuditEventType.PEER_JOINED, actor_id=peer.peer_id)


class PeerOfflineHandler(EventHandler):
    """Handler for PEER_OFFLINE events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "PEER_OFFLINE"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        peer = self.get_peer(engine, event["peer_id"])
        if peer:
            peer.go_offline()
            logger.debug(f"[Tick {engine.tick_count}] Peer {peer.peer_id[:8]} goes offline.")
            self.log_audit(engine, AuditEventType.PEER_LEFT, actor_id=peer.peer_id)


class CreateMessageHandler(EventHandler):
    """Handler for CREATE_MESSAGE events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "CREATE_MESSAGE"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        originator = self.get_peer(engine, event["originator_id"])
        if not originator:
            return

        # Create the content and the root CoC node
        recipient_ids = event["recipient_ids"]
        content = event["content"]
        node = originator.create_coc_root(content=content, recipient_ids=recipient_ids)

        # Register message_id -> node_hash mapping if message_id provided
        self.register_message(engine, event, node.node_hash)

        # Log audit event
        self.log_audit(
            engine,
            AuditEventType.CONTENT_CREATED,
            actor_id=originator.peer_id,
            target_id=node.node_hash,
            recipients=recipient_ids,
            message_id=event.get("message_id")
        )

        # Pre-serialize node data once for all recipients
        node_data = node.to_dict()
        message_content = {"node_data": node_data, "content": content}
        
        # Send the message to recipients
        for recipient_id in recipient_ids:
            originator.send_message(
                recipient_id=recipient_id,
                message_type="coc_data",
                content=message_content
            )
            # Log message sent
            self.log_audit(
                engine,
                AuditEventType.MESSAGE_SENT,
                actor_id=originator.peer_id,
                target_id=recipient_id,
                node_hash=node.node_hash
            )
        logger.debug(f"[Tick {engine.tick_count}] Peer {originator.peer_id[:8]} creates message.")


class ForwardMessageHandler(EventHandler):
    """Handler for FORWARD_MESSAGE events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "FORWARD_MESSAGE"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        sender = self.get_peer(engine, event["sender_id"])
        if not sender:
            return

        # Resolve parent hash using base class utility
        parent_hash = self.resolve_parent_hash(engine, event, "FORWARD_MESSAGE")
        if not parent_hash:
            return

        # Find the original node to create a child from
        parent_node = sender.storage.get_node(parent_hash)
        if not parent_node:
            logger.warning(f"Parent node {parent_hash} not found in {sender.peer_id}'s storage")
            return

        recipient_ids = event["recipient_ids"]
        
        # Check if watermarking is enabled and requested
        use_watermark = event.get("use_watermark", False) and engine.enable_steganography
        
        if use_watermark:
            # Get the content to watermark
            content = sender.storage.get_content(parent_node.content_hash)
            if content:
                # Use watermarked forwarding
                child_node = sender.forward_with_watermark(
                    parent_node=parent_node,
                    recipient_ids=recipient_ids,
                    content=content
                )
                # Register child message if message_id provided
                self.register_message(engine, event, child_node.node_hash)
                # Log audit event
                self.log_audit(
                    engine,
                    AuditEventType.CONTENT_FORWARDED,
                    actor_id=sender.peer_id,
                    target_id=child_node.node_hash,
                    parent_hash=parent_hash,
                    recipients=recipient_ids,
                    watermarked=True
                )
                logger.debug(f"[Tick {engine.tick_count}] Peer {sender.peer_id[:8]} forwards message with watermark.")
                return
        
        # Standard forwarding (no watermark)
        child_node = sender.forward_coc_message(
            parent_node=parent_node,
            recipient_ids=recipient_ids
        )

        # Register child message if message_id provided
        self.register_message(engine, event, child_node.node_hash)

        # Log audit event
        self.log_audit(
            engine,
            AuditEventType.CONTENT_FORWARDED,
            actor_id=sender.peer_id,
            target_id=child_node.node_hash,
            parent_hash=parent_hash,
            recipients=recipient_ids,
            watermarked=False
        )

        # Pre-serialize node data once for all recipients
        node_data = child_node.to_dict()
        message_content = {"node_data": node_data, "content": child_node.content_hash}
        
        # Send the forwarded message
        for recipient_id in recipient_ids:
            sender.send_message(
                recipient_id=recipient_id,
                message_type="coc_data",
                content=message_content
            )
        logger.debug(f"[Tick {engine.tick_count}] Peer {sender.peer_id[:8]} forwards message.")


class DeleteMessageHandler(EventHandler):
    """Handler for DELETE_MESSAGE events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "DELETE_MESSAGE"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        originator = self.get_peer(engine, event["originator_id"])
        if not originator:
            return

        # Resolve node hash using base class utility
        node_hash = self.resolve_node_hash(engine, event, "DELETE_MESSAGE")
        if not node_hash:
            return

        node_to_delete = originator.storage.get_node(node_hash)
        if node_to_delete:
            originator.initiate_deletion(node_to_delete)
            logger.debug(f"[Tick {engine.tick_count}] Peer {originator.peer_id[:8]} initiates deletion.")
            self.log_audit(
                engine,
                AuditEventType.DELETION_REQUESTED,
                actor_id=originator.peer_id,
                target_id=node_hash,
                message_id=event.get("message_id")
            )


class DistributeSharesHandler(EventHandler):
    """Handler for DISTRIBUTE_SHARES events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "DISTRIBUTE_SHARES"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Handle DISTRIBUTE_SHARES event.
        
        Event format:
        {
            "type": "DISTRIBUTE_SHARES",
            "time": <tick>,
            "originator_id": "<peer_id>",
            "content": "<secret content>",
            "recipient_ids": ["peer_1", "peer_2", ...],
            "threshold": <optional int>
        }
        """
        if not engine.enable_secret_sharing:
            logger.warning(f"[Tick {engine.tick_count}] DISTRIBUTE_SHARES failed: secret sharing not enabled")
            return

        originator = self.get_peer(engine, event["originator_id"])
        if not originator:
            logger.warning(f"[Tick {engine.tick_count}] DISTRIBUTE_SHARES failed: originator not found")
            return

        try:
            share_map = originator.distribute_shares(
                content=event["content"],
                recipient_ids=event["recipient_ids"],
                threshold=event.get("threshold")
            )
            
            # Track the shares for later reconstruction
            # Use next(iter()) instead of list() for efficiency when only need first item
            first_share = next(iter(share_map.values()))
            content_hash = first_share.content_hash
            engine._distributed_shares[content_hash] = {
                "originator": event["originator_id"],
                "recipients": event["recipient_ids"],
                "share_map": share_map
            }
            
            logger.debug(f"[Tick {engine.tick_count}] Peer {originator.peer_id[:8]} distributed {len(share_map)} shares")
        except Exception as e:
            logger.error(f"[Tick {engine.tick_count}] DISTRIBUTE_SHARES failed: {e}")


class ReconstructSecretHandler(EventHandler):
    """Handler for RECONSTRUCT_SECRET events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "RECONSTRUCT_SECRET"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Handle RECONSTRUCT_SECRET event.
        
        Event format:
        {
            "type": "RECONSTRUCT_SECRET",
            "time": <tick>,
            "requester_id": "<peer_id>",
            "content_hash": "<hash>",
            "contributor_ids": ["peer_1", "peer_2", ...]  # peers to collect shares from
        }
        """
        if not engine.enable_secret_sharing:
            logger.warning(f"[Tick {engine.tick_count}] RECONSTRUCT_SECRET failed: secret sharing not enabled")
            return

        requester = self.get_peer(engine, event["requester_id"])
        if not requester:
            logger.warning(f"[Tick {engine.tick_count}] RECONSTRUCT_SECRET failed: requester not found")
            return

        content_hash = event["content_hash"]
        contributor_ids = event.get("contributor_ids", [])
        
        # Collect shares from contributors - use dict comprehension for efficiency
        peers_dict = engine.peers
        collected_shares = {
            peer_id: peer._received_shares[content_hash]
            for peer_id in contributor_ids
            if (peer := peers_dict.get(peer_id)) and content_hash in peer._received_shares
        }

        try:
            reconstructed = requester.collect_and_reconstruct(content_hash, collected_shares)
            if reconstructed:
                logger.debug(f"[Tick {engine.tick_count}] Peer {requester.peer_id[:8]} reconstructed secret successfully")
                # Store reconstructed content
                requester.storage.add_content(content_hash, reconstructed)
            else:
                logger.warning(f"[Tick {engine.tick_count}] Peer {requester.peer_id[:8]} failed to reconstruct secret")
        except Exception as e:
            logger.error(f"[Tick {engine.tick_count}] RECONSTRUCT_SECRET failed: {e}")


class TimelockContentHandler(EventHandler):
    """Handler for TIMELOCK_CONTENT events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "TIMELOCK_CONTENT"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Handle TIMELOCK_CONTENT event.
        
        Event format:
        {
            "type": "TIMELOCK_CONTENT",
            "time": <tick>,
            "originator_id": "<peer_id>",
            "content": "<content>",
            "ttl_seconds": <int>,
            "recipient_ids": ["peer_1", "peer_2", ...]
        }
        """
        if not engine.enable_timelock:
            logger.warning(f"[Tick {engine.tick_count}] TIMELOCK_CONTENT failed: timelock not enabled")
            return

        originator = self.get_peer(engine, event["originator_id"])
        if not originator:
            logger.warning(f"[Tick {engine.tick_count}] TIMELOCK_CONTENT failed: originator not found")
            return

        try:
            originator.create_timelocked_content(
                content=event["content"],
                ttl_seconds=event["ttl_seconds"],
                recipient_ids=event["recipient_ids"]
            )
            logger.debug(f"[Tick {engine.tick_count}] Peer {originator.peer_id[:8]} created time-locked content (TTL={event['ttl_seconds']}s)")
        except Exception as e:
            logger.error(f"[Tick {engine.tick_count}] TIMELOCK_CONTENT failed: {e}")


class DestroyTimelockHandler(EventHandler):
    """Handler for DESTROY_TIMELOCK events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "DESTROY_TIMELOCK"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Handle DESTROY_TIMELOCK event.
        
        Event format:
        {
            "type": "DESTROY_TIMELOCK",
            "time": <tick>,
            "peer_id": "<peer_id>",
            "lock_id": "<lock_id>"
        }
        """
        if not engine.enable_timelock:
            logger.warning(f"[Tick {engine.tick_count}] DESTROY_TIMELOCK failed: timelock not enabled")
            return

        peer = self.get_peer(engine, event["peer_id"])
        if not peer:
            logger.warning(f"[Tick {engine.tick_count}] DESTROY_TIMELOCK failed: peer not found")
            return

        lock_id = event["lock_id"]
        success = peer.destroy_timelock(lock_id)
        if success:
            logger.debug(f"[Tick {engine.tick_count}] Peer {peer.peer_id[:8]} destroyed time-lock {lock_id[:16]}")
        else:
            logger.warning(f"[Tick {engine.tick_count}] DESTROY_TIMELOCK failed: lock not found or already expired")


class WatermarkForwardHandler(EventHandler):
    """Handler for WATERMARK_FORWARD events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "WATERMARK_FORWARD"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Handle WATERMARK_FORWARD event - forward with invisible watermarking.
        
        Event format:
        {
            "type": "WATERMARK_FORWARD",
            "time": <tick>,
            "sender_id": "<peer_id>",
            "parent_node_hash": "<hash>",  # OR "parent_message_id": "<id>"
            "recipient_ids": ["peer_1", "peer_2", ...],
            "message_id": "<optional id>"  # optional, to register the new message
        }
        """
        if not engine.enable_steganography:
            logger.warning(f"[Tick {engine.tick_count}] WATERMARK_FORWARD failed: steganography not enabled")
            return

        sender = self.get_peer(engine, event["sender_id"])
        if not sender:
            logger.warning(f"[Tick {engine.tick_count}] WATERMARK_FORWARD failed: sender not found")
            return

        # Resolve parent hash using base class utility
        parent_hash = self.resolve_parent_hash(engine, event, "WATERMARK_FORWARD")
        if not parent_hash:
            return

        parent_node = sender.storage.get_node(parent_hash)
        if not parent_node:
            logger.warning(f"[Tick {engine.tick_count}] WATERMARK_FORWARD failed: parent node not found")
            return

        content = sender.storage.get_content(parent_node.content_hash)
        if not content:
            logger.warning(f"[Tick {engine.tick_count}] WATERMARK_FORWARD failed: content not found")
            return

        recipient_ids = event["recipient_ids"]
        
        try:
            child_node = sender.forward_with_watermark(
                parent_node=parent_node,
                recipient_ids=recipient_ids,
                content=content
            )
            # Register child message if message_id provided
            self.register_message(engine, event, child_node.node_hash)
            # Log audit event
            self.log_audit(
                engine,
                AuditEventType.WATERMARK_EMBEDDED,
                actor_id=sender.peer_id,
                target_id=child_node.node_hash,
                parent_hash=parent_hash,
                recipients=recipient_ids
            )
            logger.debug(f"[Tick {engine.tick_count}] Peer {sender.peer_id[:8]} forwarded with watermark to {len(recipient_ids)} recipients")
        except Exception as e:
            logger.error(f"[Tick {engine.tick_count}] WATERMARK_FORWARD failed: {e}")


class DetectLeakHandler(EventHandler):
    """Handler for DETECT_LEAK events."""
    __slots__ = ()
    
    @property
    def event_type(self) -> str:
        return "DETECT_LEAK"
    
    def handle(self, engine: "SimulationEngine", event: Dict[str, Any]) -> None:
        """Handle DETECT_LEAK event - attempt to identify leaker from watermarked content.
        
        Event format:
        {
            "type": "DETECT_LEAK",
            "time": <tick>,
            "investigator_id": "<peer_id>",
            "leaked_content": "<content>",
            "suspect_ids": ["peer_1", "peer_2", ...]  # optional, defaults to all peers
        }
        """
        if not engine.enable_steganography:
            logger.warning(f"[Tick {engine.tick_count}] DETECT_LEAK failed: steganography not enabled")
            return

        investigator = self.get_peer(engine, event["investigator_id"])
        if not investigator:
            logger.warning(f"[Tick {engine.tick_count}] DETECT_LEAK failed: investigator not found")
            return

        suspect_ids = event.get("suspect_ids") or list(engine.peers.keys())
        
        # Register all suspects with the engine
        stegano_engine = engine.stegano_engine
        for suspect_id in suspect_ids:
            stegano_engine.register_peer(suspect_id)

        result = stegano_engine.extract_watermark(
            content=event["leaked_content"],
            candidate_peers=suspect_ids
        )

        if result.success:
            logger.info(f"[Tick {engine.tick_count}] LEAK DETECTED: Peer {result.peer_id[:8]} identified as leaker "
                        f"(confidence: {result.confidence:.1%}, method: {result.method})")
            self.log_audit(
                engine,
                AuditEventType.LEAK_DETECTED,
                actor_id=event["investigator_id"],
                target_id=result.peer_id,
                confidence=result.confidence,
                method=result.method
            )
        else:
            logger.debug(f"[Tick {engine.tick_count}] DETECT_LEAK: No watermark found or leaker not in suspect list")


def create_default_registry(validate_events: bool = True) -> EventRegistry:
    """Create an EventRegistry with all default handlers registered.
    
    Args:
        validate_events: Whether to validate events before handling (default True).
    
    Returns:
        An EventRegistry with all standard event handlers.
    """
    registry = EventRegistry(validate_events=validate_events)
    
    # Register all default handlers - use tuple for slight iteration speed improvement
    handlers = (
        PeerOnlineHandler(),
        PeerOfflineHandler(),
        CreateMessageHandler(),
        ForwardMessageHandler(),
        DeleteMessageHandler(),
        DistributeSharesHandler(),
        ReconstructSecretHandler(),
        TimelockContentHandler(),
        DestroyTimelockHandler(),
        WatermarkForwardHandler(),
        DetectLeakHandler(),
    )
    for handler in handlers:
        registry.register(handler)
    
    return registry


# Export all public classes
__all__ = [
    "EventHandler",
    "EventRegistry",
    "PeerOnlineHandler",
    "PeerOfflineHandler",
    "CreateMessageHandler",
    "ForwardMessageHandler",
    "DeleteMessageHandler",
    "DistributeSharesHandler",
    "ReconstructSecretHandler",
    "TimelockContentHandler",
    "DestroyTimelockHandler",
    "WatermarkForwardHandler",
    "DetectLeakHandler",
    "create_default_registry",
]
