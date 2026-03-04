"""Input validation utilities for TrustFlow framework."""

import re
from datetime import datetime
from functools import lru_cache
from typing import Dict, Any, List, FrozenSet, Tuple
from dataclasses import dataclass, field

_SHA256_HASH_PATTERN = re.compile(r'^[a-fA-F0-9]{64}$')
_ED25519_SIGNATURE_PATTERN = re.compile(r'^[a-fA-F0-9]{128}$')
_ED25519_PUBKEY_PATTERN = re.compile(r'^[a-fA-F0-9]{64}$')


class ValidationError(Exception):
    def __init__(self, message: str, field: str = None, errors: List[str] = None):
        self.message = message
        self.field = field
        self.errors = errors or []
        super().__init__(message)

    def __str__(self) -> str:
        if self.errors:
            return f"{self.message}: {'; '.join(self.errors)}"
        return self.message


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    
    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.is_valid = False
    
    def merge(self, other: "ValidationResult") -> None:
        if not other.is_valid:
            self.is_valid = False
            self.errors.extend(other.errors)


class EventValidator:
    """Validates scenario events."""
    
    REQUIRED_FIELDS: Dict[str, Tuple[str, ...]] = {
        "CREATE_MESSAGE": ("originator_id", "recipient_ids", "content"),
        "FORWARD_MESSAGE": ("sender_id", "recipient_ids"),
        "DELETE_MESSAGE": ("originator_id",),
        "PEER_ONLINE": ("peer_id",),
        "PEER_OFFLINE": ("peer_id",),
        "DISTRIBUTE_SHARES": ("originator_id", "content", "recipient_ids", "threshold"),
        "RECONSTRUCT_SECRET": ("requester_id", "content_hash"),
        "TIMELOCK_CONTENT": ("originator_id", "content", "ttl_seconds"),
        "DESTROY_TIMELOCK": ("peer_id", "lock_id"),
        "WATERMARK_FORWARD": ("sender_id", "recipient_ids"),
        "DETECT_LEAK": ("investigator_id", "leaked_content"),
    }
    
    ALTERNATIVE_FIELDS: Dict[str, Tuple[FrozenSet[str], ...]] = {
        "FORWARD_MESSAGE": (frozenset({"parent_message_id", "parent_node_hash"}),),
        "DELETE_MESSAGE": (frozenset({"message_id", "node_hash"}),),
        "WATERMARK_FORWARD": (frozenset({"parent_message_id", "parent_node_hash"}),),
    }
    
    FIELD_TYPES: Dict[str, type] = {
        "originator_id": str, "sender_id": str, "peer_id": str, "requester_id": str,
        "investigator_id": str, "recipient_ids": list, "content": str, "leaked_content": str,
        "node_hash": str, "parent_node_hash": str, "message_id": str, "parent_message_id": str,
        "content_hash": str, "lock_id": str, "threshold": int, "ttl_seconds": int,
        "time": int, "type": str, "suspect_ids": list, "contributor_ids": list,
    }
    
    VALID_EVENT_TYPES: FrozenSet[str] = frozenset(REQUIRED_FIELDS.keys())
    
    _STRING_FIELDS: FrozenSet[str] = frozenset({
        "originator_id", "sender_id", "peer_id", "requester_id", 
        "investigator_id", "content", "leaked_content", "node_hash",
        "parent_node_hash", "message_id", "parent_message_id",
        "content_hash", "lock_id"
    })
    
    _HASH_FIELDS: FrozenSet[str] = frozenset({"node_hash", "parent_node_hash", "content_hash"})
    
    @classmethod
    def validate_event(cls, event: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        
        if not isinstance(event, dict):
            result.add_error(f"Event must be a dictionary, got {type(event).__name__}")
            return result
        
        if "type" not in event:
            result.add_error("Event missing required field 'type'")
            return result
        
        event_type = event.get("type")
        
        if not isinstance(event_type, str):
            result.add_error(f"Event 'type' must be a string, got {type(event_type).__name__}")
            return result
        
        if event_type not in cls.VALID_EVENT_TYPES:
            result.add_error(f"Unknown event type '{event_type}'. Valid types: {', '.join(sorted(cls.VALID_EVENT_TYPES))}")
            return result
        
        required = cls.REQUIRED_FIELDS.get(event_type, ())
        for field_name in required:
            if field_name not in event:
                result.add_error(f"Event '{event_type}' missing required field '{field_name}'")
        
        alternatives = cls.ALTERNATIVE_FIELDS.get(event_type, ())
        for alt_group in alternatives:
            if not any(field in event for field in alt_group):
                result.add_error(f"Event '{event_type}' requires at least one of: {', '.join(sorted(alt_group))}")
        
        for field_name, field_value in event.items():
            if field_name in cls.FIELD_TYPES:
                expected_type = cls.FIELD_TYPES[field_name]
                if not isinstance(field_value, expected_type):
                    result.add_error(
                        f"Field '{field_name}' must be {expected_type.__name__}, "
                        f"got {type(field_value).__name__}"
                    )
        
        result.merge(cls._validate_field_values(event, event_type))
        return result
    
    @classmethod
    def _validate_field_values(cls, event: Dict[str, Any], event_type: str) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        
        for field_name in cls._STRING_FIELDS:
            if field_name in event:
                value = event[field_name]
                if isinstance(value, str) and not value.strip():
                    result.add_error(f"Field '{field_name}' cannot be empty")
        
        if "recipient_ids" in event:
            recipients = event["recipient_ids"]
            if isinstance(recipients, list):
                if len(recipients) == 0:
                    result.add_error("Field 'recipient_ids' cannot be empty")
                else:
                    for i, rid in enumerate(recipients):
                        if not isinstance(rid, str):
                            result.add_error(f"recipient_ids[{i}] must be a string, got {type(rid).__name__}")
                        elif not rid.strip():
                            result.add_error(f"recipient_ids[{i}] cannot be empty")
        
        if "threshold" in event:
            threshold = event["threshold"]
            if isinstance(threshold, int) and threshold < 2:
                result.add_error(f"Field 'threshold' must be at least 2, got {threshold}")
        
        if "ttl_seconds" in event:
            ttl = event["ttl_seconds"]
            if isinstance(ttl, int) and ttl <= 0:
                result.add_error(f"Field 'ttl_seconds' must be positive, got {ttl}")
        
        if "time" in event:
            time_val = event["time"]
            if isinstance(time_val, int) and time_val < 0:
                result.add_error(f"Field 'time' cannot be negative, got {time_val}")
        
        for field_name in cls._HASH_FIELDS:
            if field_name in event:
                value = event[field_name]
                if isinstance(value, str) and value.strip():
                    if not validate_content_hash(value):
                        result.add_error(f"Field '{field_name}' is not a valid SHA-256 hash (expected 64 hex chars)")
        
        return result
    
    @classmethod  
    def validate_scenario(cls, scenario: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        
        if not isinstance(scenario, dict):
            result.add_error(f"Scenario must be a dictionary, got {type(scenario).__name__}")
            return result
        
        if "events" not in scenario:
            result.add_error("Scenario missing required field 'events'")
        else:
            events = scenario["events"]
            if not isinstance(events, list):
                result.add_error(f"Scenario 'events' must be a list, got {type(events).__name__}")
            else:
                for i, event in enumerate(events):
                    event_result = cls.validate_event(event)
                    if not event_result.is_valid:
                        for error in event_result.errors:
                            result.add_error(f"Event {i}: {error}")
        
        if "peers" in scenario:
            peers = scenario["peers"]
            if not isinstance(peers, list):
                result.add_error(f"Scenario 'peers' must be a list, got {type(peers).__name__}")
            else:
                for i, peer_config in enumerate(peers):
                    if not isinstance(peer_config, dict):
                        result.add_error(f"Peer config {i} must be a dictionary")
                    elif "id" not in peer_config:
                        result.add_error(f"Peer config {i} missing required field 'id'")
                    elif not isinstance(peer_config["id"], str):
                        result.add_error(f"Peer config {i} 'id' must be a string")
                    elif not peer_config["id"].strip():
                        result.add_error(f"Peer config {i} 'id' cannot be empty")
        
        if "settings" in scenario:
            settings = scenario["settings"]
            if not isinstance(settings, dict):
                result.add_error(f"Scenario 'settings' must be a dictionary, got {type(settings).__name__}")
            else:
                if "total_peers" in settings:
                    total_peers = settings["total_peers"]
                    if not isinstance(total_peers, int):
                        result.add_error(f"Settings 'total_peers' must be an integer, got {type(total_peers).__name__}")
                    elif total_peers < 1:
                        result.add_error(f"Settings 'total_peers' must be at least 1, got {total_peers}")
                
                if "secret_sharing_threshold" in settings:
                    threshold = settings["secret_sharing_threshold"]
                    if not isinstance(threshold, int):
                        result.add_error(f"Settings 'secret_sharing_threshold' must be an integer")
                    elif threshold < 2:
                        result.add_error(f"Settings 'secret_sharing_threshold' must be at least 2, got {threshold}")
                
                if "timelock_cleanup_interval" in settings:
                    interval = settings["timelock_cleanup_interval"]
                    if not isinstance(interval, (int, float)):
                        result.add_error(f"Settings 'timelock_cleanup_interval' must be a number")
                    elif interval <= 0:
                        result.add_error(f"Settings 'timelock_cleanup_interval' must be positive")
        
        if "peers" in scenario and "settings" in scenario and "total_peers" in scenario.get("settings", {}):
            result.add_error("Scenario should not define both 'peers' list and 'settings.total_peers'")
        
        return result


def validate_peer_id(peer_id: str) -> bool:
    if not isinstance(peer_id, str):
        return False
    return bool(peer_id.strip())


def validate_content_hash(hash_str: str) -> bool:
    if not isinstance(hash_str, str):
        return False
    return _SHA256_HASH_PATTERN.match(hash_str) is not None


_TIMESTAMP_FORMATS: Tuple[str, ...] = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


@lru_cache(maxsize=256)
def validate_timestamp(timestamp: str) -> bool:
    if not isinstance(timestamp, str):
        return False
    for fmt in _TIMESTAMP_FORMATS:
        try:
            datetime.strptime(timestamp, fmt)
            return True
        except ValueError:
            continue
    try:
        ts = timestamp.replace('Z', '+00:00')
        datetime.fromisoformat(ts)
        return True
    except ValueError:
        return False


def validate_signature_hex(signature: str) -> bool:
    if not isinstance(signature, str):
        return False
    return _ED25519_SIGNATURE_PATTERN.match(signature) is not None


def validate_public_key_hex(public_key: str) -> bool:
    if not isinstance(public_key, str):
        return False
    return _ED25519_PUBKEY_PATTERN.match(public_key) is not None


__all__ = [
    "ValidationError",
    "ValidationResult",
    "EventValidator",
    "validate_peer_id",
    "validate_content_hash",
    "validate_timestamp",
    "validate_signature_hex",
    "validate_public_key_hex",
]
