"""
Tests for the typed configuration module.
"""
import pytest
import json
import tempfile
import os
from coc_framework.config import SimulationSettings, ScenarioConfig, SCENARIO_SCHEMA


class TestSimulationSettings:
    """Tests for SimulationSettings dataclass."""

    def test_default_values(self):
        """Settings should have sensible defaults."""
        settings = SimulationSettings()
        
        assert settings.total_peers == 5
        assert settings.simulation_duration == 10
        assert settings.enable_secret_sharing is False
        assert settings.enable_timelock is False
        assert settings.enable_steganography is False
        assert settings.default_secret_threshold == 3
        assert settings.default_timelock_ttl == 300
        assert settings.network_delay_min == 0.01
        assert settings.network_delay_max == 0.05

    def test_custom_values(self):
        """Settings should accept custom values."""
        settings = SimulationSettings(
            total_peers=10,
            simulation_duration=100,
            enable_secret_sharing=True,
            enable_timelock=True,
            enable_steganography=True,
            default_secret_threshold=5,
            default_timelock_ttl=600
        )
        
        assert settings.total_peers == 10
        assert settings.simulation_duration == 100
        assert settings.enable_secret_sharing is True
        assert settings.enable_timelock is True
        assert settings.enable_steganography is True
        assert settings.default_secret_threshold == 5
        assert settings.default_timelock_ttl == 600

    def test_validation_total_peers_minimum(self):
        """total_peers must be >= 1."""
        with pytest.raises(ValueError, match="total_peers must be >= 1"):
            SimulationSettings(total_peers=0)
        
        with pytest.raises(ValueError, match="total_peers must be >= 1"):
            SimulationSettings(total_peers=-1)

    def test_validation_simulation_duration_minimum(self):
        """simulation_duration must be >= 1."""
        with pytest.raises(ValueError, match="simulation_duration must be >= 1"):
            SimulationSettings(simulation_duration=0)

    def test_validation_secret_threshold_minimum(self):
        """default_secret_threshold must be >= 2."""
        with pytest.raises(ValueError, match="default_secret_threshold must be >= 2"):
            SimulationSettings(default_secret_threshold=1)

    def test_validation_timelock_ttl_minimum(self):
        """default_timelock_ttl must be >= 1."""
        with pytest.raises(ValueError, match="default_timelock_ttl must be >= 1"):
            SimulationSettings(default_timelock_ttl=0)

    def test_validation_network_delay_non_negative(self):
        """Network delays must be non-negative."""
        with pytest.raises(ValueError, match="network_delay_min must be >= 0"):
            SimulationSettings(network_delay_min=-0.1)
        
        with pytest.raises(ValueError, match="network_delay_max must be >= 0"):
            SimulationSettings(network_delay_max=-0.1)

    def test_validation_network_delay_order(self):
        """network_delay_min must be <= network_delay_max."""
        with pytest.raises(ValueError, match="network_delay_min must be <= network_delay_max"):
            SimulationSettings(network_delay_min=0.1, network_delay_max=0.05)

    def test_validation_timelock_cleanup_interval(self):
        """timelock_cleanup_interval must be > 0."""
        with pytest.raises(ValueError, match="timelock_cleanup_interval must be > 0"):
            SimulationSettings(timelock_cleanup_interval=0)
        
        with pytest.raises(ValueError, match="timelock_cleanup_interval must be > 0"):
            SimulationSettings(timelock_cleanup_interval=-1)

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        settings = SimulationSettings(total_peers=3, enable_timelock=True)
        
        result = settings.to_dict()
        
        assert isinstance(result, dict)
        assert result["total_peers"] == 3
        assert result["enable_timelock"] is True
        assert "simulation_duration" in result

    def test_from_dict(self):
        """from_dict should create settings from dictionary."""
        data = {
            "total_peers": 8,
            "simulation_duration": 50,
            "enable_secret_sharing": True
        }
        
        settings = SimulationSettings.from_dict(data)
        
        assert settings.total_peers == 8
        assert settings.simulation_duration == 50
        assert settings.enable_secret_sharing is True
        # Defaults should still apply
        assert settings.enable_timelock is False

    def test_from_dict_ignores_unknown_fields(self):
        """from_dict should ignore unknown fields for forward compatibility."""
        data = {
            "total_peers": 5,
            "unknown_future_field": "some_value",
            "another_unknown": 123
        }
        
        # Should not raise
        settings = SimulationSettings.from_dict(data)
        
        assert settings.total_peers == 5

    def test_roundtrip_serialization(self):
        """to_dict -> from_dict should preserve all values."""
        original = SimulationSettings(
            total_peers=7,
            simulation_duration=20,
            enable_secret_sharing=True,
            enable_timelock=True,
            network_delay_min=0.02,
            network_delay_max=0.1
        )
        
        serialized = original.to_dict()
        restored = SimulationSettings.from_dict(serialized)
        
        assert restored.total_peers == original.total_peers
        assert restored.simulation_duration == original.simulation_duration
        assert restored.enable_secret_sharing == original.enable_secret_sharing
        assert restored.enable_timelock == original.enable_timelock
        assert restored.network_delay_min == original.network_delay_min
        assert restored.network_delay_max == original.network_delay_max


class TestScenarioConfig:
    """Tests for ScenarioConfig dataclass."""

    def test_minimal_config(self):
        """Config should work with minimal required fields."""
        config = ScenarioConfig(
            settings=SimulationSettings(),
            events=[]
        )
        
        assert config.settings.total_peers == 5
        assert config.events == []
        assert config.metadata == {}
        assert config.peers == []

    def test_full_config(self):
        """Config should accept all fields."""
        settings = SimulationSettings(total_peers=3)
        events = [{"time": 0, "type": "CREATE_MESSAGE", "content": "test"}]
        metadata = {"author": "test", "version": "1.0"}
        peers = [{"id": "alice"}, {"id": "bob"}]
        
        config = ScenarioConfig(
            settings=settings,
            events=events,
            metadata=metadata,
            peers=peers
        )
        
        assert config.settings.total_peers == 3
        assert len(config.events) == 1
        assert config.metadata["author"] == "test"
        assert len(config.peers) == 2

    def test_to_dict(self):
        """to_dict should serialize the config."""
        config = ScenarioConfig(
            settings=SimulationSettings(total_peers=2),
            events=[{"time": 0, "type": "TEST"}],
            metadata={"key": "value"}
        )
        
        result = config.to_dict()
        
        assert isinstance(result, dict)
        assert result["settings"]["total_peers"] == 2
        assert len(result["events"]) == 1
        assert result["metadata"]["key"] == "value"

    def test_to_dict_excludes_empty_optional_fields(self):
        """to_dict should not include empty optional fields."""
        config = ScenarioConfig(
            settings=SimulationSettings(),
            events=[]
        )
        
        result = config.to_dict()
        
        assert "metadata" not in result
        assert "peers" not in result

    def test_from_dict(self):
        """from_dict should create config from dictionary."""
        data = {
            "settings": {"total_peers": 4, "enable_timelock": True},
            "events": [{"time": 1, "type": "CREATE_MESSAGE"}],
            "metadata": {"description": "Test scenario"}
        }
        
        config = ScenarioConfig.from_dict(data)
        
        assert config.settings.total_peers == 4
        assert config.settings.enable_timelock is True
        assert len(config.events) == 1
        assert config.metadata["description"] == "Test scenario"

    def test_from_dict_with_empty_settings(self):
        """from_dict should use defaults when settings is empty."""
        data = {
            "events": [{"time": 0, "type": "TEST"}]
        }
        
        config = ScenarioConfig.from_dict(data)
        
        assert config.settings.total_peers == 5  # default
        assert config.settings.enable_secret_sharing is False  # default

    def test_from_dict_with_peers(self):
        """from_dict should handle peers list."""
        data = {
            "peers": [{"id": "peer_a"}, {"id": "peer_b"}],
            "events": []
        }
        
        config = ScenarioConfig.from_dict(data)
        
        assert len(config.peers) == 2
        assert config.peers[0]["id"] == "peer_a"

    def test_roundtrip_serialization(self):
        """to_dict -> from_dict should preserve all values."""
        original = ScenarioConfig(
            settings=SimulationSettings(total_peers=6, enable_steganography=True),
            events=[
                {"time": 0, "type": "CREATE_MESSAGE", "content": "hello"},
                {"time": 5, "type": "DELETE_MESSAGE"}
            ],
            metadata={"name": "test_scenario", "version": 2},
            peers=[{"id": "alice"}, {"id": "bob"}]
        )
        
        serialized = original.to_dict()
        restored = ScenarioConfig.from_dict(serialized)
        
        assert restored.settings.total_peers == original.settings.total_peers
        assert restored.settings.enable_steganography == original.settings.enable_steganography
        assert len(restored.events) == len(original.events)
        assert restored.metadata == original.metadata
        assert restored.peers == original.peers


class TestScenarioConfigFileIO:
    """Tests for ScenarioConfig file I/O."""

    def test_from_json_file(self):
        """from_json_file should load config from JSON file."""
        data = {
            "settings": {"total_peers": 3},
            "events": [{"time": 0, "type": "TEST"}]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name
        
        try:
            config = ScenarioConfig.from_json_file(temp_path)
            
            assert config.settings.total_peers == 3
            assert len(config.events) == 1
        finally:
            os.unlink(temp_path)

    def test_to_json_file(self):
        """to_json_file should save config to JSON file."""
        config = ScenarioConfig(
            settings=SimulationSettings(total_peers=4),
            events=[{"time": 1, "type": "CREATE_MESSAGE"}]
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            config.to_json_file(temp_path)
            
            with open(temp_path, 'r') as f:
                loaded = json.load(f)
            
            assert loaded["settings"]["total_peers"] == 4
            assert len(loaded["events"]) == 1
        finally:
            os.unlink(temp_path)

    def test_json_file_roundtrip(self):
        """Save and load should preserve all data."""
        original = ScenarioConfig(
            settings=SimulationSettings(
                total_peers=5,
                enable_secret_sharing=True,
                default_secret_threshold=3
            ),
            events=[
                {"time": 0, "type": "CREATE_MESSAGE", "content": "test"},
                {"time": 10, "type": "DELETE_MESSAGE"}
            ],
            metadata={"author": "test_suite"}
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            original.to_json_file(temp_path)
            loaded = ScenarioConfig.from_json_file(temp_path)
            
            assert loaded.settings.total_peers == original.settings.total_peers
            assert loaded.settings.enable_secret_sharing == original.settings.enable_secret_sharing
            assert len(loaded.events) == len(original.events)
            assert loaded.metadata == original.metadata
        finally:
            os.unlink(temp_path)

    def test_from_json_file_not_found(self):
        """from_json_file should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            ScenarioConfig.from_json_file("/nonexistent/path/scenario.json")

    def test_from_json_file_invalid_json(self):
        """from_json_file should raise JSONDecodeError for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name
        
        try:
            with pytest.raises(json.JSONDecodeError):
                ScenarioConfig.from_json_file(temp_path)
        finally:
            os.unlink(temp_path)

    def test_from_json_file_validation_error(self):
        """from_json_file should raise ValueError for invalid settings."""
        data = {
            "settings": {"total_peers": 0},  # Invalid: must be >= 1
            "events": []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="total_peers must be >= 1"):
                ScenarioConfig.from_json_file(temp_path)
        finally:
            os.unlink(temp_path)


class TestScenarioSchema:
    """Tests for the JSON schema definition."""

    def test_schema_exists(self):
        """SCENARIO_SCHEMA should be defined."""
        assert SCENARIO_SCHEMA is not None
        assert isinstance(SCENARIO_SCHEMA, dict)

    def test_schema_has_required_properties(self):
        """Schema should define required properties."""
        assert "$schema" in SCENARIO_SCHEMA
        assert "type" in SCENARIO_SCHEMA
        assert "properties" in SCENARIO_SCHEMA
        assert "required" in SCENARIO_SCHEMA

    def test_schema_requires_events(self):
        """Schema should require events field."""
        assert "events" in SCENARIO_SCHEMA["required"]

    def test_schema_defines_settings(self):
        """Schema should define settings properties."""
        settings_schema = SCENARIO_SCHEMA["properties"]["settings"]
        
        assert "total_peers" in settings_schema["properties"]
        assert "simulation_duration" in settings_schema["properties"]
        assert "enable_secret_sharing" in settings_schema["properties"]


class TestConfigIntegrationWithSimulationEngine:
    """Integration tests for config with SimulationEngine."""

    def test_engine_accepts_scenario_config(self):
        """SimulationEngine should accept ScenarioConfig."""
        from coc_framework.simulation_engine import SimulationEngine
        
        config = ScenarioConfig(
            settings=SimulationSettings(total_peers=3),
            events=[]
        )
        
        engine = SimulationEngine(config)
        
        assert len(engine.peers) == 3
        assert engine.config is config

    def test_engine_accepts_raw_dict(self):
        """SimulationEngine should still accept raw dict (backward compat)."""
        from coc_framework.simulation_engine import SimulationEngine
        
        scenario = {
            "settings": {"total_peers": 2},
            "events": []
        }
        
        engine = SimulationEngine(scenario)
        
        assert len(engine.peers) == 2
        assert engine.config is not None
        assert engine.config.settings.total_peers == 2

    def test_engine_uses_typed_settings(self):
        """SimulationEngine should use typed settings for feature flags."""
        from coc_framework.simulation_engine import SimulationEngine
        
        config = ScenarioConfig(
            settings=SimulationSettings(
                total_peers=2,
                enable_secret_sharing=True,
                enable_steganography=True
            ),
            events=[]
        )
        
        engine = SimulationEngine(config)
        
        assert engine.enable_secret_sharing is True
        assert engine.enable_steganography is True
        assert engine.enable_timelock is False
        assert engine.secret_sharing_engine is not None
        assert engine.stegano_engine is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
