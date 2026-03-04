"""
Tests for coc_framework.core.validation module.

Tests input validation for scenario events, peer IDs, content hashes,
timestamps, and other validation utilities.
"""

import pytest
from coc_framework.core.validation import (
    ValidationError,
    ValidationResult,
    EventValidator,
    validate_peer_id,
    validate_content_hash,
    validate_timestamp,
    validate_signature_hex,
    validate_public_key_hex,
)
from coc_framework import SimulationEngine


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_initial_valid_state(self):
        """ValidationResult should be valid by default."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
    
    def test_add_error_marks_invalid(self):
        """Adding an error should mark result as invalid."""
        result = ValidationResult(is_valid=True)
        result.add_error("Test error")
        assert result.is_valid is False
        assert "Test error" in result.errors
    
    def test_add_multiple_errors(self):
        """Multiple errors should be collected."""
        result = ValidationResult(is_valid=True)
        result.add_error("Error 1")
        result.add_error("Error 2")
        assert len(result.errors) == 2
        assert "Error 1" in result.errors
        assert "Error 2" in result.errors
    
    def test_merge_valid_results(self):
        """Merging two valid results should remain valid."""
        result1 = ValidationResult(is_valid=True)
        result2 = ValidationResult(is_valid=True)
        result1.merge(result2)
        assert result1.is_valid is True
        assert result1.errors == []
    
    def test_merge_invalid_result(self):
        """Merging an invalid result should make the target invalid."""
        result1 = ValidationResult(is_valid=True)
        result2 = ValidationResult(is_valid=False, errors=["Error from result2"])
        result1.merge(result2)
        assert result1.is_valid is False
        assert "Error from result2" in result1.errors


class TestValidationError:
    """Tests for ValidationError exception."""
    
    def test_basic_error(self):
        """ValidationError should store message."""
        error = ValidationError("Test message")
        assert error.message == "Test message"
        assert error.field is None
        assert error.errors == []
    
    def test_error_with_field(self):
        """ValidationError should store field name."""
        error = ValidationError("Test message", field="test_field")
        assert error.field == "test_field"
    
    def test_error_with_errors_list(self):
        """ValidationError should store errors list."""
        errors = ["Error 1", "Error 2"]
        error = ValidationError("Test message", errors=errors)
        assert error.errors == errors
    
    def test_str_representation(self):
        """ValidationError string should include errors."""
        error = ValidationError("Test message", errors=["Error 1", "Error 2"])
        error_str = str(error)
        assert "Test message" in error_str
        assert "Error 1" in error_str


class TestEventValidatorWithValidEvents:
    """Tests for EventValidator with valid events."""
    
    def test_valid_create_message_event(self):
        """CREATE_MESSAGE with all required fields should be valid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "recipient_ids": ["peer_2", "peer_3"],
            "content": "Test message"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
        assert result.errors == []
    
    def test_valid_forward_message_with_parent_message_id(self):
        """FORWARD_MESSAGE with parent_message_id should be valid."""
        event = {
            "type": "FORWARD_MESSAGE",
            "time": 1,
            "sender_id": "peer_2",
            "recipient_ids": ["peer_4"],
            "parent_message_id": "msg_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_forward_message_with_parent_node_hash(self):
        """FORWARD_MESSAGE with parent_node_hash should be valid."""
        event = {
            "type": "FORWARD_MESSAGE",
            "time": 1,
            "sender_id": "peer_2",
            "recipient_ids": ["peer_4"],
            "parent_node_hash": "a" * 64  # Valid SHA-256 hash
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_delete_message_with_message_id(self):
        """DELETE_MESSAGE with message_id should be valid."""
        event = {
            "type": "DELETE_MESSAGE",
            "time": 2,
            "originator_id": "peer_1",
            "message_id": "msg_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_delete_message_with_node_hash(self):
        """DELETE_MESSAGE with node_hash should be valid."""
        event = {
            "type": "DELETE_MESSAGE",
            "time": 2,
            "originator_id": "peer_1",
            "node_hash": "b" * 64
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_peer_online_event(self):
        """PEER_ONLINE with peer_id should be valid."""
        event = {
            "type": "PEER_ONLINE",
            "time": 0,
            "peer_id": "peer_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_peer_offline_event(self):
        """PEER_OFFLINE with peer_id should be valid."""
        event = {
            "type": "PEER_OFFLINE",
            "time": 5,
            "peer_id": "peer_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_distribute_shares_event(self):
        """DISTRIBUTE_SHARES with all required fields should be valid."""
        event = {
            "type": "DISTRIBUTE_SHARES",
            "time": 1,
            "originator_id": "peer_1",
            "content": "secret data",
            "recipient_ids": ["peer_2", "peer_3", "peer_4"],
            "threshold": 2
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_reconstruct_secret_event(self):
        """RECONSTRUCT_SECRET with all required fields should be valid."""
        event = {
            "type": "RECONSTRUCT_SECRET",
            "time": 2,
            "requester_id": "peer_2",
            "content_hash": "c" * 64
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_timelock_content_event(self):
        """TIMELOCK_CONTENT with all required fields should be valid."""
        event = {
            "type": "TIMELOCK_CONTENT",
            "time": 0,
            "originator_id": "peer_1",
            "content": "time-locked data",
            "ttl_seconds": 3600
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_destroy_timelock_event(self):
        """DESTROY_TIMELOCK with all required fields should be valid."""
        event = {
            "type": "DESTROY_TIMELOCK",
            "time": 5,
            "peer_id": "peer_1",
            "lock_id": "lock_123"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_watermark_forward_event(self):
        """WATERMARK_FORWARD with all required fields should be valid."""
        event = {
            "type": "WATERMARK_FORWARD",
            "time": 2,
            "sender_id": "peer_2",
            "recipient_ids": ["peer_3"],
            "parent_message_id": "msg_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True
    
    def test_valid_detect_leak_event(self):
        """DETECT_LEAK with all required fields should be valid."""
        event = {
            "type": "DETECT_LEAK",
            "time": 10,
            "investigator_id": "peer_admin",
            "leaked_content": "This is leaked content with watermark"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is True


class TestEventValidatorWithMissingRequiredFields:
    """Tests for EventValidator with missing required fields."""
    
    def test_missing_type_field(self):
        """Event without type should be invalid."""
        event = {
            "time": 0,
            "originator_id": "peer_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("type" in e.lower() for e in result.errors)
    
    def test_create_message_missing_originator(self):
        """CREATE_MESSAGE without originator_id should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "recipient_ids": ["peer_2"],
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("originator_id" in e for e in result.errors)
    
    def test_create_message_missing_recipient_ids(self):
        """CREATE_MESSAGE without recipient_ids should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("recipient_ids" in e for e in result.errors)
    
    def test_create_message_missing_content(self):
        """CREATE_MESSAGE without content should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "recipient_ids": ["peer_2"]
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("content" in e for e in result.errors)
    
    def test_forward_message_missing_parent(self):
        """FORWARD_MESSAGE without parent reference should be invalid."""
        event = {
            "type": "FORWARD_MESSAGE",
            "time": 1,
            "sender_id": "peer_2",
            "recipient_ids": ["peer_3"]
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("parent_message_id" in e or "parent_node_hash" in e for e in result.errors)
    
    def test_delete_message_missing_reference(self):
        """DELETE_MESSAGE without message/node reference should be invalid."""
        event = {
            "type": "DELETE_MESSAGE",
            "time": 2,
            "originator_id": "peer_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("message_id" in e or "node_hash" in e for e in result.errors)
    
    def test_peer_online_missing_peer_id(self):
        """PEER_ONLINE without peer_id should be invalid."""
        event = {
            "type": "PEER_ONLINE",
            "time": 0
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("peer_id" in e for e in result.errors)
    
    def test_multiple_missing_fields_collected(self):
        """All missing fields should be reported, not just the first."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0
            # Missing originator_id, recipient_ids, and content
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert len(result.errors) >= 3  # At least 3 missing fields


class TestEventValidatorWithInvalidFieldTypes:
    """Tests for EventValidator with invalid field types."""
    
    def test_invalid_type_field_type(self):
        """Event type as non-string should be invalid."""
        event = {
            "type": 123,  # Should be string
            "time": 0
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
    
    def test_invalid_originator_id_type(self):
        """originator_id as non-string should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": 123,  # Should be string
            "recipient_ids": ["peer_2"],
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("originator_id" in e and "str" in e.lower() for e in result.errors)
    
    def test_invalid_recipient_ids_type(self):
        """recipient_ids as non-list should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "recipient_ids": "peer_2",  # Should be list
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("recipient_ids" in e and "list" in e.lower() for e in result.errors)
    
    def test_invalid_content_type(self):
        """content as non-string should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "recipient_ids": ["peer_2"],
            "content": 12345  # Should be string
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("content" in e and "str" in e.lower() for e in result.errors)
    
    def test_invalid_threshold_type(self):
        """threshold as non-int should be invalid."""
        event = {
            "type": "DISTRIBUTE_SHARES",
            "time": 1,
            "originator_id": "peer_1",
            "content": "secret",
            "recipient_ids": ["peer_2", "peer_3"],
            "threshold": "2"  # Should be int
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("threshold" in e and "int" in e.lower() for e in result.errors)
    
    def test_invalid_ttl_seconds_type(self):
        """ttl_seconds as non-int should be invalid."""
        event = {
            "type": "TIMELOCK_CONTENT",
            "time": 0,
            "originator_id": "peer_1",
            "content": "locked",
            "ttl_seconds": 3600.5  # Should be int
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("ttl_seconds" in e and "int" in e.lower() for e in result.errors)
    
    def test_invalid_time_type(self):
        """time as non-int should be invalid."""
        event = {
            "type": "PEER_ONLINE",
            "time": "0",  # Should be int
            "peer_id": "peer_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("time" in e and "int" in e.lower() for e in result.errors)
    
    def test_recipient_ids_contains_non_string(self):
        """recipient_ids containing non-strings should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "recipient_ids": ["peer_2", 123, "peer_3"],  # Contains int
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("recipient_ids" in e for e in result.errors)


class TestEventValidatorWithInvalidFieldValues:
    """Tests for EventValidator with invalid field values."""
    
    def test_empty_originator_id(self):
        """Empty originator_id should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "",
            "recipient_ids": ["peer_2"],
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("originator_id" in e and "empty" in e.lower() for e in result.errors)
    
    def test_empty_recipient_ids_list(self):
        """Empty recipient_ids list should be invalid."""
        event = {
            "type": "CREATE_MESSAGE",
            "time": 0,
            "originator_id": "peer_1",
            "recipient_ids": [],
            "content": "Test"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("recipient_ids" in e and "empty" in e.lower() for e in result.errors)
    
    def test_whitespace_only_peer_id(self):
        """Whitespace-only peer_id should be invalid."""
        event = {
            "type": "PEER_ONLINE",
            "time": 0,
            "peer_id": "   "
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
    
    def test_threshold_below_minimum(self):
        """threshold < 2 should be invalid."""
        event = {
            "type": "DISTRIBUTE_SHARES",
            "time": 1,
            "originator_id": "peer_1",
            "content": "secret",
            "recipient_ids": ["peer_2", "peer_3"],
            "threshold": 1  # Must be at least 2
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("threshold" in e and "2" in e for e in result.errors)
    
    def test_ttl_seconds_zero_or_negative(self):
        """ttl_seconds <= 0 should be invalid."""
        event = {
            "type": "TIMELOCK_CONTENT",
            "time": 0,
            "originator_id": "peer_1",
            "content": "locked",
            "ttl_seconds": 0  # Must be positive
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("ttl_seconds" in e and "positive" in e.lower() for e in result.errors)
    
    def test_negative_time(self):
        """Negative time should be invalid."""
        event = {
            "type": "PEER_ONLINE",
            "time": -1,
            "peer_id": "peer_1"
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("time" in e and "negative" in e.lower() for e in result.errors)
    
    def test_invalid_hash_format(self):
        """Invalid hash format should be invalid."""
        event = {
            "type": "DELETE_MESSAGE",
            "time": 2,
            "originator_id": "peer_1",
            "node_hash": "invalid_hash"  # Not a valid SHA-256 hash
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("node_hash" in e and "SHA-256" in e for e in result.errors)
    
    def test_unknown_event_type(self):
        """Unknown event type should be invalid."""
        event = {
            "type": "UNKNOWN_EVENT",
            "time": 0
        }
        result = EventValidator.validate_event(event)
        assert result.is_valid is False
        assert any("unknown" in e.lower() or "UNKNOWN_EVENT" in e for e in result.errors)
    
    def test_event_not_dict(self):
        """Non-dictionary event should be invalid."""
        result = EventValidator.validate_event("not a dict")
        assert result.is_valid is False
        assert any("dictionary" in e.lower() for e in result.errors)


class TestScenarioValidation:
    """Tests for EventValidator.validate_scenario."""
    
    def test_valid_scenario_with_peers(self):
        """Valid scenario with peers list should pass validation."""
        scenario = {
            "peers": [
                {"id": "peer_1"},
                {"id": "peer_2"}
            ],
            "events": [
                {
                    "type": "CREATE_MESSAGE",
                    "time": 0,
                    "originator_id": "peer_1",
                    "recipient_ids": ["peer_2"],
                    "content": "Hello"
                }
            ]
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is True
    
    def test_valid_scenario_with_settings(self):
        """Valid scenario with settings should pass validation."""
        scenario = {
            "settings": {
                "total_peers": 3,
                "enable_secret_sharing": True,
                "secret_sharing_threshold": 2
            },
            "events": []
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is True
    
    def test_scenario_missing_events(self):
        """Scenario without events field should be invalid."""
        scenario = {
            "peers": [{"id": "peer_1"}]
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("events" in e for e in result.errors)
    
    def test_scenario_events_not_list(self):
        """Scenario with non-list events should be invalid."""
        scenario = {
            "events": "not a list"
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("events" in e and "list" in e.lower() for e in result.errors)
    
    def test_scenario_invalid_event_reported(self):
        """Invalid events in scenario should be reported with index."""
        scenario = {
            "peers": [{"id": "peer_1"}],
            "events": [
                {
                    "type": "CREATE_MESSAGE",
                    "time": 0,
                    "originator_id": "peer_1",
                    "recipient_ids": ["peer_2"],
                    "content": "Valid"
                },
                {
                    "type": "CREATE_MESSAGE",
                    "time": 1
                    # Missing required fields
                }
            ]
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("Event 1" in e for e in result.errors)  # Second event (index 1)
    
    def test_scenario_invalid_peer_config(self):
        """Invalid peer configuration should be invalid."""
        scenario = {
            "peers": [
                {"id": "peer_1"},
                {"name": "peer_2"}  # Missing 'id' field
            ],
            "events": []
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("Peer config" in e and "id" in e for e in result.errors)
    
    def test_scenario_empty_peer_id(self):
        """Empty peer id should be invalid."""
        scenario = {
            "peers": [{"id": ""}],
            "events": []
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
    
    def test_scenario_invalid_settings_total_peers(self):
        """total_peers < 1 should be invalid."""
        scenario = {
            "settings": {"total_peers": 0},
            "events": []
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("total_peers" in e for e in result.errors)
    
    def test_scenario_invalid_settings_threshold(self):
        """secret_sharing_threshold < 2 should be invalid."""
        scenario = {
            "settings": {"secret_sharing_threshold": 1},
            "events": []
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("secret_sharing_threshold" in e for e in result.errors)
    
    def test_scenario_both_peers_and_total_peers(self):
        """Defining both peers and total_peers should be invalid."""
        scenario = {
            "peers": [{"id": "peer_1"}],
            "settings": {"total_peers": 5},
            "events": []
        }
        result = EventValidator.validate_scenario(scenario)
        assert result.is_valid is False
        assert any("peers" in e and "total_peers" in e for e in result.errors)
    
    def test_scenario_not_dict(self):
        """Non-dictionary scenario should be invalid."""
        result = EventValidator.validate_scenario("not a dict")
        assert result.is_valid is False
        assert any("dictionary" in e.lower() for e in result.errors)


class TestValidatePeerId:
    """Tests for validate_peer_id function."""
    
    def test_valid_peer_id(self):
        """Normal peer ID should be valid."""
        assert validate_peer_id("peer_1") is True
        assert validate_peer_id("alice") is True
        assert validate_peer_id("node-123") is True
    
    def test_empty_peer_id(self):
        """Empty peer ID should be invalid."""
        assert validate_peer_id("") is False
    
    def test_whitespace_peer_id(self):
        """Whitespace-only peer ID should be invalid."""
        assert validate_peer_id("   ") is False
        assert validate_peer_id("\t\n") is False
    
    def test_non_string_peer_id(self):
        """Non-string peer ID should be invalid."""
        assert validate_peer_id(123) is False
        assert validate_peer_id(None) is False
        assert validate_peer_id(["peer_1"]) is False


class TestValidateContentHash:
    """Tests for validate_content_hash function."""
    
    def test_valid_sha256_hash(self):
        """Valid 64-character hex string should be valid."""
        valid_hash = "a" * 64
        assert validate_content_hash(valid_hash) is True
        
        # Real-looking hash
        real_hash = "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd"
        assert validate_content_hash(real_hash) is True
    
    def test_valid_mixed_case_hash(self):
        """Mixed case hex should be valid."""
        mixed_hash = "AbCdEf0123456789" + "a" * 48
        assert validate_content_hash(mixed_hash) is True
    
    def test_short_hash(self):
        """Hash shorter than 64 chars should be invalid."""
        assert validate_content_hash("a" * 63) is False
        assert validate_content_hash("a" * 32) is False
    
    def test_long_hash(self):
        """Hash longer than 64 chars should be invalid."""
        assert validate_content_hash("a" * 65) is False
    
    def test_non_hex_characters(self):
        """Non-hex characters should be invalid."""
        assert validate_content_hash("g" * 64) is False
        assert validate_content_hash("a" * 63 + "!") is False
    
    def test_empty_hash(self):
        """Empty string should be invalid."""
        assert validate_content_hash("") is False
    
    def test_non_string_hash(self):
        """Non-string should be invalid."""
        assert validate_content_hash(123) is False
        assert validate_content_hash(None) is False


class TestValidateTimestamp:
    """Tests for validate_timestamp function."""
    
    def test_valid_iso_timestamps(self):
        """Valid ISO timestamps should pass."""
        assert validate_timestamp("2024-01-15T12:30:00") is True
        assert validate_timestamp("2024-01-15T12:30:00.123456") is True
        assert validate_timestamp("2024-01-15") is True
        assert validate_timestamp("2024-01-15 12:30:00") is True
    
    def test_valid_timestamp_with_timezone(self):
        """Timestamps with timezone should pass."""
        assert validate_timestamp("2024-01-15T12:30:00+00:00") is True
        assert validate_timestamp("2024-01-15T12:30:00Z") is True
        assert validate_timestamp("2024-01-15T12:30:00-05:00") is True
    
    def test_invalid_timestamp_format(self):
        """Invalid timestamp formats should fail."""
        assert validate_timestamp("not a timestamp") is False
        assert validate_timestamp("01/15/2024") is False
        assert validate_timestamp("2024-13-01") is False  # Invalid month
    
    def test_empty_timestamp(self):
        """Empty string should be invalid."""
        assert validate_timestamp("") is False
    
    def test_non_string_timestamp(self):
        """Non-string should be invalid."""
        assert validate_timestamp(1234567890) is False
        assert validate_timestamp(None) is False


class TestValidateSignatureHex:
    """Tests for validate_signature_hex function."""
    
    def test_valid_signature(self):
        """Valid 128-character hex string should be valid."""
        valid_sig = "a" * 128
        assert validate_signature_hex(valid_sig) is True
    
    def test_short_signature(self):
        """Signature shorter than 128 chars should be invalid."""
        assert validate_signature_hex("a" * 127) is False
    
    def test_long_signature(self):
        """Signature longer than 128 chars should be invalid."""
        assert validate_signature_hex("a" * 129) is False
    
    def test_non_hex_signature(self):
        """Non-hex characters should be invalid."""
        assert validate_signature_hex("g" * 128) is False


class TestValidatePublicKeyHex:
    """Tests for validate_public_key_hex function."""
    
    def test_valid_public_key(self):
        """Valid 64-character hex string should be valid."""
        valid_key = "a" * 64
        assert validate_public_key_hex(valid_key) is True
    
    def test_short_public_key(self):
        """Key shorter than 64 chars should be invalid."""
        assert validate_public_key_hex("a" * 63) is False
    
    def test_long_public_key(self):
        """Key longer than 64 chars should be invalid."""
        assert validate_public_key_hex("a" * 65) is False
    
    def test_non_hex_public_key(self):
        """Non-hex characters should be invalid."""
        assert validate_public_key_hex("g" * 64) is False


class TestSimulationEngineValidation:
    """Tests for SimulationEngine scenario validation integration."""
    
    def test_engine_validates_scenario_by_default(self):
        """SimulationEngine should validate scenario by default."""
        invalid_scenario = {
            "peers": [{"id": "peer_1"}],
            "events": [
                {"type": "CREATE_MESSAGE", "time": 0}  # Missing required fields
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            SimulationEngine(invalid_scenario)
        assert "originator_id" in str(exc_info.value)
    
    def test_engine_validation_can_be_disabled(self):
        """SimulationEngine validation can be disabled."""
        invalid_scenario = {
            "peers": [{"id": "peer_1"}],
            "events": [
                {"type": "CREATE_MESSAGE", "time": 0}  # Missing required fields
            ]
        }
        # Should not raise with validation disabled
        engine = SimulationEngine(invalid_scenario, validate_scenario=False, validate_events=False)
        assert engine is not None
        engine.shutdown()
    
    def test_engine_accepts_valid_scenario(self):
        """SimulationEngine should accept valid scenarios."""
        valid_scenario = {
            "peers": [{"id": "peer_1"}, {"id": "peer_2"}],
            "events": [
                {
                    "type": "CREATE_MESSAGE",
                    "time": 0,
                    "originator_id": "peer_1",
                    "recipient_ids": ["peer_2"],
                    "content": "Hello"
                }
            ]
        }
        engine = SimulationEngine(valid_scenario)
        assert engine is not None
        assert len(engine.peers) == 2
        engine.shutdown()
    
    def test_engine_collects_all_errors(self):
        """SimulationEngine should collect all validation errors."""
        invalid_scenario = {
            "peers": [{"id": ""}],  # Invalid peer
            "settings": {"total_peers": 3},  # Conflicting with peers
            "events": [
                {"type": "UNKNOWN", "time": 0},  # Unknown type
                {"type": "CREATE_MESSAGE", "time": 0}  # Missing fields
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            SimulationEngine(invalid_scenario)
        # Should have multiple errors collected
        assert len(exc_info.value.errors) >= 2
