from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, Optional, List
import hashlib
import json
import os

from .logging import audit_logger as get_audit_logger


class AuditEventType(Enum):
    # Content lifecycle
    CONTENT_CREATED = "content_created"
    CONTENT_ACCESSED = "content_accessed"
    CONTENT_FORWARDED = "content_forwarded"
    CONTENT_DELETED = "content_deleted"

    # Identity events
    IDENTITY_CREATED = "identity_created"
    CERTIFICATE_ISSUED = "certificate_issued"
    CERTIFICATE_REVOKED = "certificate_revoked"

    # Network events
    PEER_JOINED = "peer_joined"
    PEER_LEFT = "peer_left"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"

    # Security events
    SIGNATURE_VERIFIED = "signature_verified"
    SIGNATURE_FAILED = "signature_failed"
    DELETION_REQUESTED = "deletion_requested"
    DELETION_CONFIRMED = "deletion_confirmed"
    WATERMARK_EMBEDDED = "watermark_embedded"
    LEAK_DETECTED = "leak_detected"

    # Access control
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"


@dataclass
class AuditEvent:
    event_type: AuditEventType
    timestamp: str
    actor_id: str
    target_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "details": self.details,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AuditEvent":
        return AuditEvent(
            event_type=AuditEventType(data["event_type"]),
            timestamp=data["timestamp"],
            actor_id=data["actor_id"],
            target_id=data.get("target_id"),
            details=data.get("details", {}),
        )


@dataclass
class LogEntry:
    """Single entry in the tamper-evident log."""
    data: Dict[str, Any]
    timestamp: str
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "LogEntry":
        return LogEntry(
            data=data["data"],
            timestamp=data["timestamp"],
            prev_hash=data["prev_hash"],
            entry_hash=data["entry_hash"],
        )


class TamperEvidentLog:
    """In-memory hash-chained log for tamper detection."""

    def __init__(self):
        self._entries: List[LogEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, data: Dict[str, Any]) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        prev_hash = self._entries[-1].entry_hash if self._entries else ""
        content_to_hash = json.dumps({
            "data": data,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
        }, sort_keys=True)
        entry_hash = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()
        entry = LogEntry(
            data=data,
            timestamp=timestamp,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        self._entries.append(entry)
        return entry_hash

    def verify(self) -> bool:
        if not self._entries:
            return True
        prev_hash = ""
        for entry in self._entries:
            if entry.prev_hash != prev_hash:
                return False
            content_to_hash = json.dumps({
                "data": entry.data,
                "timestamp": entry.timestamp,
                "prev_hash": entry.prev_hash,
            }, sort_keys=True)
            recalculated_hash = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()
            if recalculated_hash != entry.entry_hash:
                return False
            prev_hash = entry.entry_hash
        return True

    def get_entries(self) -> List[LogEntry]:
        return list(self._entries)

    def get_entry(self, entry_hash: str) -> Optional[LogEntry]:
        for entry in self._entries:
            if entry.entry_hash == entry_hash:
                return entry
        return None


class AuditLogger:
    """High-level audit logger with filtering and export capabilities."""

    def __init__(self):
        self._log = TamperEvidentLog()

    def __len__(self) -> int:
        return len(self._log)

    def log_event(self, event: AuditEvent) -> str:
        return self._log.append(event.to_dict())

    def log(
        self,
        event_type: AuditEventType,
        actor_id: str,
        target_id: Optional[str] = None,
        **details: Any,
    ) -> str:
        event = AuditEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor_id=actor_id,
            target_id=target_id,
            details=details,
        )
        return self.log_event(event)

    def get_all_events(self) -> List[AuditEvent]:
        return [AuditEvent.from_dict(entry.data) for entry in self._log.get_entries()]

    def get_events_by_type(self, event_type: AuditEventType) -> List[AuditEvent]:
        return [e for e in self.get_all_events() if e.event_type == event_type]

    def get_events_by_actor(self, actor_id: str) -> List[AuditEvent]:
        return [e for e in self.get_all_events() if e.actor_id == actor_id]

    def get_events_for_target(self, target_id: str) -> List[AuditEvent]:
        return [e for e in self.get_all_events() if e.target_id == target_id]

    def get_events_in_range(self, start: str, end: str) -> List[AuditEvent]:
        return [e for e in self.get_all_events() if start <= e.timestamp <= end]

    def export_audit_trail(self, format: str = "json") -> str:
        entries = self._log.get_entries()
        if format == "json":
            trail = []
            for entry in entries:
                trail.append({
                    "event": entry.data,
                    "entry_hash": entry.entry_hash,
                    "prev_hash": entry.prev_hash,
                })
            return json.dumps({
                "audit_trail": trail,
                "total_events": len(trail),
            }, indent=2)
        elif format == "csv":
            lines = ["event_type,timestamp,actor_id,target_id,entry_hash"]
            for entry in entries:
                event = AuditEvent.from_dict(entry.data)
                target = event.target_id if event.target_id else ""
                lines.append(
                    f"{event.event_type.value},{event.timestamp},{event.actor_id},{target},{entry.entry_hash}"
                )
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def verify_integrity(self) -> bool:
        return self._log.verify()

class AuditLog:
    """File-based hash-chained audit log."""
    
    def __init__(self, log_directory=None):
        if log_directory is None:
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            log_directory = os.path.join(script_dir, "data", "logs")
        os.makedirs(log_directory, exist_ok=True)
        self.log_file = os.path.join(log_directory, "audit.log")
        self.last_hash = self._get_last_hash()
        self._log = get_audit_logger()
        if not self.last_hash:
            self._initialize_log()
        self._log.info("Audit Log initialized", log_file=self.log_file)

    def _get_last_hash(self) -> str:
        try:
            with open(self.log_file, 'rb') as f:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
                last_line = f.readline().decode().strip()
                return last_line.split(" | ")[-1]
        except (IOError, IndexError):
            return ""

    def _initialize_log(self):
        with open(self.log_file, 'w') as f:
            f.write("# Audit Log - Chain of Custody Simulator\n")
            f.write("# Each entry is chained by hashing the previous entry's hash.\n")
        self.log_event("GENESIS", "SYSTEM", "Log Initialized", "Initial state.")

    def log_event(self, event_type: str, actor: str, target: str, details: str = ""):
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry_content = f"{event_type} | {actor} | {target} | {timestamp} | {details} | {self.last_hash}"
        new_hash = hashlib.sha256(log_entry_content.encode('utf-8')).hexdigest()
        full_log_entry = f"{log_entry_content} | {new_hash}\n"
        with open(self.log_file, 'a') as f:
            f.write(full_log_entry)
        self._log.info("Event logged", event_type=event_type, actor=actor, target=target)
        self.last_hash = new_hash

    def verify_log_integrity(self) -> bool:
        self._log.info("Verifying log integrity")
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
            log_entries = [line.strip() for line in lines if not line.startswith("#")]
            current_hash_from_prev_line = ""
            for i, entry in enumerate(log_entries):
                parts = entry.split(" | ")
                if len(parts) != 7:
                    continue
                prev_hash_in_entry = parts[5]
                if prev_hash_in_entry != current_hash_from_prev_line:
                    self._log.error("Chain broken", line=i+1, expected_hash=current_hash_from_prev_line, found_hash=prev_hash_in_entry)
                    return False
                content_to_hash = " | ".join(parts[:-1])
                recalculated_hash = hashlib.sha256(content_to_hash.encode('utf-8')).hexdigest()
                stored_hash = parts[6]
                if recalculated_hash != stored_hash:
                    self._log.error("Hash mismatch", line=i+1, recalculated_hash=recalculated_hash, stored_hash=stored_hash)
                    return False
                current_hash_from_prev_line = stored_hash
            self._log.info("Log integrity verified successfully")
            return True
        except FileNotFoundError:
            self._log.error("Log file not found")
            return False
