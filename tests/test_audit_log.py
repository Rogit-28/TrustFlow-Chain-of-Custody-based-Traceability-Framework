"""
Tests for the expanded audit logging system.
"""
import json
import pytest
from datetime import datetime, timezone, timedelta

from coc_framework.core.audit_log import (
    AuditEventType,
    AuditEvent,
    AuditLogger,
    TamperEvidentLog,
    LogEntry,
)


class TestAuditEventType:
    """Tests for AuditEventType enum."""

    def test_all_event_types_exist(self):
        """All expected event types should be defined."""
        # Content lifecycle
        assert AuditEventType.CONTENT_CREATED.value == "content_created"
        assert AuditEventType.CONTENT_ACCESSED.value == "content_accessed"
        assert AuditEventType.CONTENT_FORWARDED.value == "content_forwarded"
        assert AuditEventType.CONTENT_DELETED.value == "content_deleted"

        # Identity events
        assert AuditEventType.IDENTITY_CREATED.value == "identity_created"
        assert AuditEventType.CERTIFICATE_ISSUED.value == "certificate_issued"
        assert AuditEventType.CERTIFICATE_REVOKED.value == "certificate_revoked"

        # Network events
        assert AuditEventType.PEER_JOINED.value == "peer_joined"
        assert AuditEventType.PEER_LEFT.value == "peer_left"
        assert AuditEventType.MESSAGE_SENT.value == "message_sent"
        assert AuditEventType.MESSAGE_RECEIVED.value == "message_received"

        # Security events
        assert AuditEventType.SIGNATURE_VERIFIED.value == "signature_verified"
        assert AuditEventType.SIGNATURE_FAILED.value == "signature_failed"
        assert AuditEventType.DELETION_REQUESTED.value == "deletion_requested"
        assert AuditEventType.DELETION_CONFIRMED.value == "deletion_confirmed"
        assert AuditEventType.WATERMARK_EMBEDDED.value == "watermark_embedded"
        assert AuditEventType.LEAK_DETECTED.value == "leak_detected"

        # Access control
        assert AuditEventType.ACCESS_GRANTED.value == "access_granted"
        assert AuditEventType.ACCESS_DENIED.value == "access_denied"

    def test_total_event_types_count(self):
        """Should have exactly 19 event types."""
        assert len(AuditEventType) == 19

    def test_event_type_from_string(self):
        """Should be able to create event type from string value."""
        event_type = AuditEventType("content_created")
        assert event_type == AuditEventType.CONTENT_CREATED

    def test_invalid_event_type_raises(self):
        """Invalid event type string should raise ValueError."""
        with pytest.raises(ValueError):
            AuditEventType("invalid_type")


class TestAuditEvent:
    """Tests for AuditEvent dataclass."""

    def test_create_event(self):
        """Should create an audit event with all fields."""
        event = AuditEvent(
            event_type=AuditEventType.CONTENT_CREATED,
            timestamp="2024-01-01T00:00:00+00:00",
            actor_id="alice",
            target_id="msg_001",
            details={"content_hash": "abc123"}
        )

        assert event.event_type == AuditEventType.CONTENT_CREATED
        assert event.timestamp == "2024-01-01T00:00:00+00:00"
        assert event.actor_id == "alice"
        assert event.target_id == "msg_001"
        assert event.details == {"content_hash": "abc123"}

    def test_event_default_values(self):
        """Should have correct default values."""
        event = AuditEvent(
            event_type=AuditEventType.PEER_JOINED,
            timestamp="2024-01-01T00:00:00+00:00",
            actor_id="bob"
        )

        assert event.target_id is None
        assert event.details == {}

    def test_event_to_dict(self):
        """Should serialize event to dictionary."""
        event = AuditEvent(
            event_type=AuditEventType.MESSAGE_SENT,
            timestamp="2024-01-01T12:00:00+00:00",
            actor_id="alice",
            target_id="bob",
            details={"size": 1024}
        )

        result = event.to_dict()

        assert result == {
            "event_type": "message_sent",
            "timestamp": "2024-01-01T12:00:00+00:00",
            "actor_id": "alice",
            "target_id": "bob",
            "details": {"size": 1024}
        }

    def test_event_from_dict(self):
        """Should deserialize event from dictionary."""
        data = {
            "event_type": "deletion_requested",
            "timestamp": "2024-01-01T15:30:00+00:00",
            "actor_id": "charlie",
            "target_id": "msg_002",
            "details": {"reason": "expired"}
        }

        event = AuditEvent.from_dict(data)

        assert event.event_type == AuditEventType.DELETION_REQUESTED
        assert event.timestamp == "2024-01-01T15:30:00+00:00"
        assert event.actor_id == "charlie"
        assert event.target_id == "msg_002"
        assert event.details == {"reason": "expired"}

    def test_event_roundtrip(self):
        """Serialization and deserialization should be reversible."""
        original = AuditEvent(
            event_type=AuditEventType.LEAK_DETECTED,
            timestamp="2024-06-15T08:45:00+00:00",
            actor_id="investigator",
            target_id="leaker_peer",
            details={"confidence": 0.95, "method": "zero_width"}
        )

        restored = AuditEvent.from_dict(original.to_dict())

        assert restored.event_type == original.event_type
        assert restored.timestamp == original.timestamp
        assert restored.actor_id == original.actor_id
        assert restored.target_id == original.target_id
        assert restored.details == original.details


class TestTamperEvidentLog:
    """Tests for TamperEvidentLog class."""

    def test_empty_log(self):
        """New log should be empty."""
        log = TamperEvidentLog()
        assert len(log) == 0
        assert log.verify()

    def test_append_entry(self):
        """Should append entries and return hash."""
        log = TamperEvidentLog()

        entry_hash = log.append({"event": "test"})

        assert len(log) == 1
        assert len(entry_hash) == 64  # SHA-256 hex

    def test_multiple_entries(self):
        """Should append multiple entries."""
        log = TamperEvidentLog()

        hash1 = log.append({"event": "first"})
        hash2 = log.append({"event": "second"})
        hash3 = log.append({"event": "third"})

        assert len(log) == 3
        assert hash1 != hash2 != hash3

    def test_verify_intact_log(self):
        """Verify should pass for unmodified log."""
        log = TamperEvidentLog()
        log.append({"event": "first"})
        log.append({"event": "second"})
        log.append({"event": "third"})

        assert log.verify() is True

    def test_verify_detects_tampering(self):
        """Verify should detect tampered entries."""
        log = TamperEvidentLog()
        log.append({"event": "first"})
        log.append({"event": "second"})

        # Tamper with the log
        log._entries[0].data["event"] = "tampered"

        assert log.verify() is False

    def test_verify_detects_chain_break(self):
        """Verify should detect broken hash chain."""
        log = TamperEvidentLog()
        log.append({"event": "first"})
        log.append({"event": "second"})

        # Break the chain
        log._entries[1].prev_hash = "wrong_hash"

        assert log.verify() is False

    def test_get_entries(self):
        """Should return all entries."""
        log = TamperEvidentLog()
        log.append({"n": 1})
        log.append({"n": 2})

        entries = log.get_entries()

        assert len(entries) == 2
        assert entries[0].data == {"n": 1}
        assert entries[1].data == {"n": 2}

    def test_get_entry_by_hash(self):
        """Should find entry by hash."""
        log = TamperEvidentLog()
        hash1 = log.append({"n": 1})
        log.append({"n": 2})

        entry = log.get_entry(hash1)

        assert entry is not None
        assert entry.data == {"n": 1}

    def test_get_entry_not_found(self):
        """Should return None for unknown hash."""
        log = TamperEvidentLog()
        log.append({"n": 1})

        entry = log.get_entry("nonexistent_hash")

        assert entry is None


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_create_entry(self):
        """Should create a log entry."""
        entry = LogEntry(
            data={"test": "data"},
            timestamp="2024-01-01T00:00:00+00:00",
            prev_hash="abc123",
            entry_hash="def456"
        )

        assert entry.data == {"test": "data"}
        assert entry.timestamp == "2024-01-01T00:00:00+00:00"
        assert entry.prev_hash == "abc123"
        assert entry.entry_hash == "def456"

    def test_entry_to_dict(self):
        """Should serialize entry to dictionary."""
        entry = LogEntry(
            data={"test": "data"},
            timestamp="2024-01-01T00:00:00+00:00",
            prev_hash="abc",
            entry_hash="def"
        )

        result = entry.to_dict()

        assert result == {
            "data": {"test": "data"},
            "timestamp": "2024-01-01T00:00:00+00:00",
            "prev_hash": "abc",
            "entry_hash": "def"
        }

    def test_entry_from_dict(self):
        """Should deserialize entry from dictionary."""
        data = {
            "data": {"test": "value"},
            "timestamp": "2024-06-01T12:00:00+00:00",
            "prev_hash": "prev",
            "entry_hash": "curr"
        }

        entry = LogEntry.from_dict(data)

        assert entry.data == {"test": "value"}
        assert entry.timestamp == "2024-06-01T12:00:00+00:00"
        assert entry.prev_hash == "prev"
        assert entry.entry_hash == "curr"


class TestAuditLogger:
    """Tests for AuditLogger class."""

    def test_empty_logger(self):
        """New logger should be empty."""
        logger = AuditLogger()
        assert len(logger) == 0
        assert logger.verify_integrity()

    def test_log_event(self):
        """Should log an audit event."""
        logger = AuditLogger()
        event = AuditEvent(
            event_type=AuditEventType.CONTENT_CREATED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor_id="alice",
            target_id="msg_001"
        )

        entry_hash = logger.log_event(event)

        assert len(logger) == 1
        assert len(entry_hash) == 64

    def test_log_convenience_method(self):
        """Should log using convenience method."""
        logger = AuditLogger()

        entry_hash = logger.log(
            AuditEventType.MESSAGE_SENT,
            actor_id="alice",
            target_id="bob",
            content="Hello"
        )

        assert len(logger) == 1
        assert len(entry_hash) == 64

        events = logger.get_all_events()
        assert events[0].actor_id == "alice"
        assert events[0].target_id == "bob"
        assert events[0].details == {"content": "Hello"}

    def test_get_events_by_type(self):
        """Should filter events by type."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.MESSAGE_SENT, actor_id="alice", target_id="bob")
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="bob", target_id="msg2")
        logger.log(AuditEventType.PEER_JOINED, actor_id="charlie")

        created_events = logger.get_events_by_type(AuditEventType.CONTENT_CREATED)

        assert len(created_events) == 2
        assert all(e.event_type == AuditEventType.CONTENT_CREATED for e in created_events)

    def test_get_events_by_actor(self):
        """Should filter events by actor."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.MESSAGE_SENT, actor_id="alice", target_id="bob")
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="bob", target_id="msg2")

        alice_events = logger.get_events_by_actor("alice")

        assert len(alice_events) == 2
        assert all(e.actor_id == "alice" for e in alice_events)

    def test_get_events_for_target(self):
        """Should filter events by target."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.CONTENT_ACCESSED, actor_id="bob", target_id="msg1")
        logger.log(AuditEventType.CONTENT_DELETED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="charlie", target_id="msg2")

        msg1_events = logger.get_events_for_target("msg1")

        assert len(msg1_events) == 3
        assert all(e.target_id == "msg1" for e in msg1_events)

    def test_get_events_in_range(self):
        """Should filter events by timestamp range."""
        logger = AuditLogger()

        # Create events with specific timestamps
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        
        event1 = AuditEvent(
            event_type=AuditEventType.CONTENT_CREATED,
            timestamp=(base_time + timedelta(hours=1)).isoformat(),
            actor_id="alice"
        )
        event2 = AuditEvent(
            event_type=AuditEventType.MESSAGE_SENT,
            timestamp=(base_time + timedelta(hours=2)).isoformat(),
            actor_id="bob"
        )
        event3 = AuditEvent(
            event_type=AuditEventType.CONTENT_DELETED,
            timestamp=(base_time + timedelta(hours=3)).isoformat(),
            actor_id="charlie"
        )

        logger.log_event(event1)
        logger.log_event(event2)
        logger.log_event(event3)

        # Query for middle time range
        start = (base_time + timedelta(minutes=90)).isoformat()
        end = (base_time + timedelta(hours=2, minutes=30)).isoformat()

        range_events = logger.get_events_in_range(start, end)

        assert len(range_events) == 1
        assert range_events[0].actor_id == "bob"

    def test_export_audit_trail_json(self):
        """Should export audit trail as JSON."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.MESSAGE_SENT, actor_id="alice", target_id="bob")

        export = logger.export_audit_trail("json")
        data = json.loads(export)

        assert "audit_trail" in data
        assert "total_events" in data
        assert data["total_events"] == 2
        assert len(data["audit_trail"]) == 2
        assert "event" in data["audit_trail"][0]
        assert "entry_hash" in data["audit_trail"][0]
        assert "prev_hash" in data["audit_trail"][0]

    def test_export_audit_trail_csv(self):
        """Should export audit trail as CSV."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.MESSAGE_SENT, actor_id="bob", target_id="charlie")

        export = logger.export_audit_trail("csv")
        lines = export.strip().split("\n")

        assert len(lines) == 3  # header + 2 events
        assert lines[0] == "event_type,timestamp,actor_id,target_id,entry_hash"
        assert "content_created" in lines[1]
        assert "alice" in lines[1]
        assert "message_sent" in lines[2]
        assert "bob" in lines[2]

    def test_export_invalid_format_raises(self):
        """Should raise for invalid export format."""
        logger = AuditLogger()

        with pytest.raises(ValueError, match="Unsupported format"):
            logger.export_audit_trail("xml")

    def test_verify_integrity(self):
        """Should verify audit log integrity."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.MESSAGE_SENT, actor_id="bob", target_id="charlie")
        logger.log(AuditEventType.DELETION_CONFIRMED, actor_id="alice", target_id="msg1")

        assert logger.verify_integrity() is True

    def test_verify_integrity_detects_tampering(self):
        """Should detect tampered audit events."""
        logger = AuditLogger()
        logger.log(AuditEventType.CONTENT_CREATED, actor_id="alice", target_id="msg1")
        logger.log(AuditEventType.MESSAGE_SENT, actor_id="bob", target_id="charlie")

        # Tamper with the underlying log
        logger._log._entries[0].data["actor_id"] = "mallory"

        assert logger.verify_integrity() is False

    def test_get_all_events(self):
        """Should return all events."""
        logger = AuditLogger()
        logger.log(AuditEventType.PEER_JOINED, actor_id="alice")
        logger.log(AuditEventType.PEER_JOINED, actor_id="bob")
        logger.log(AuditEventType.PEER_LEFT, actor_id="alice")

        all_events = logger.get_all_events()

        assert len(all_events) == 3


class TestAuditLoggerIntegration:
    """Integration tests for AuditLogger with various event types."""

    def test_content_lifecycle_tracking(self):
        """Should track complete content lifecycle."""
        logger = AuditLogger()

        # Create
        logger.log(AuditEventType.CONTENT_CREATED, "alice", "doc_001",
                   content_type="document", size=1024)
        
        # Access
        logger.log(AuditEventType.CONTENT_ACCESSED, "bob", "doc_001",
                   access_type="read")
        
        # Forward
        logger.log(AuditEventType.CONTENT_FORWARDED, "bob", "doc_001",
                   recipient="charlie")
        
        # Delete
        logger.log(AuditEventType.DELETION_REQUESTED, "alice", "doc_001")
        logger.log(AuditEventType.DELETION_CONFIRMED, "bob", "doc_001")
        logger.log(AuditEventType.CONTENT_DELETED, "charlie", "doc_001")

        doc_events = logger.get_events_for_target("doc_001")
        assert len(doc_events) == 6

        # Verify chain integrity
        assert logger.verify_integrity()

    def test_security_event_tracking(self):
        """Should track security-related events."""
        logger = AuditLogger()

        logger.log(AuditEventType.SIGNATURE_VERIFIED, "alice", "msg_001")
        logger.log(AuditEventType.WATERMARK_EMBEDDED, "alice", "msg_001",
                   method="zero_width")
        logger.log(AuditEventType.SIGNATURE_FAILED, "mallory", "msg_001",
                   reason="invalid_key")
        logger.log(AuditEventType.ACCESS_DENIED, "mallory", "msg_001",
                   reason="unauthorized")
        logger.log(AuditEventType.LEAK_DETECTED, "admin", "mallory",
                   confidence=0.95)

        security_events = [
            e for e in logger.get_all_events()
            if e.event_type in [
                AuditEventType.SIGNATURE_VERIFIED,
                AuditEventType.SIGNATURE_FAILED,
                AuditEventType.WATERMARK_EMBEDDED,
                AuditEventType.LEAK_DETECTED,
                AuditEventType.ACCESS_DENIED
            ]
        ]

        assert len(security_events) == 5

    def test_network_event_tracking(self):
        """Should track network events."""
        logger = AuditLogger()

        logger.log(AuditEventType.PEER_JOINED, "alice")
        logger.log(AuditEventType.PEER_JOINED, "bob")
        logger.log(AuditEventType.MESSAGE_SENT, "alice", "bob", content="hello")
        logger.log(AuditEventType.MESSAGE_RECEIVED, "bob", "msg_001")
        logger.log(AuditEventType.PEER_LEFT, "alice")

        alice_events = logger.get_events_by_actor("alice")
        assert len(alice_events) == 3  # joined, sent, left


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
