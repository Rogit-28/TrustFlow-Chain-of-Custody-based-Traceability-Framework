"""Typed configuration objects with validation for TrustFlow scenarios."""

from dataclasses import dataclass, field, fields, asdict
from typing import Dict, Any, List, FrozenSet
import json

# Module-level cache for known field names
_KNOWN_FIELDS_CACHE: Dict[type, FrozenSet[str]] = {}


def _get_known_fields(cls: type) -> FrozenSet[str]:
    if cls not in _KNOWN_FIELDS_CACHE:
        _KNOWN_FIELDS_CACHE[cls] = frozenset(f.name for f in fields(cls) if f.init)
    return _KNOWN_FIELDS_CACHE[cls]


@dataclass(slots=True)
class SimulationSettings:
    """Simulation configuration settings with validation."""
    total_peers: int = 5
    simulation_duration: int = 10
    enable_secret_sharing: bool = False
    enable_timelock: bool = False
    enable_steganography: bool = False
    default_secret_threshold: int = 3
    default_timelock_ttl: int = 300
    network_delay_min: float = 0.01
    network_delay_max: float = 0.05
    secret_sharing_threshold: int = 3
    timelock_cleanup_interval: float = 1.0

    def __post_init__(self):
        if self.total_peers < 1:
            raise ValueError("total_peers must be >= 1")
        if self.simulation_duration < 1:
            raise ValueError("simulation_duration must be >= 1")
        if self.default_secret_threshold < 2:
            raise ValueError("default_secret_threshold must be >= 2")
        if self.secret_sharing_threshold < 2:
            raise ValueError("secret_sharing_threshold must be >= 2")
        if self.default_timelock_ttl < 1:
            raise ValueError("default_timelock_ttl must be >= 1")
        if self.network_delay_min < 0:
            raise ValueError("network_delay_min must be >= 0")
        if self.network_delay_max < 0:
            raise ValueError("network_delay_max must be >= 0")
        if self.network_delay_min > self.network_delay_max:
            raise ValueError("network_delay_min must be <= network_delay_max")
        if self.timelock_cleanup_interval <= 0:
            raise ValueError("timelock_cleanup_interval must be > 0")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimulationSettings":
        known = _get_known_fields(cls)
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass(slots=True)
class ScenarioConfig:
    """Full scenario configuration with settings and events."""
    settings: SimulationSettings
    events: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    peers: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "settings": self.settings.to_dict(),
            "events": self.events,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        if self.peers:
            result["peers"] = self.peers
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioConfig":
        settings = SimulationSettings.from_dict(data.get("settings", {}))
        events = data.get("events", [])
        metadata = data.get("metadata", {})
        peers = data.get("peers", [])
        return cls(settings=settings, events=events, metadata=metadata, peers=peers)

    @classmethod
    def from_json_file(cls, path: str) -> "ScenarioConfig":
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))

    def to_json_file(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)


# JSON Schema for external validation
SCENARIO_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "settings": {
            "type": "object",
            "properties": {
                "total_peers": {"type": "integer", "minimum": 1},
                "simulation_duration": {"type": "integer", "minimum": 1},
                "enable_secret_sharing": {"type": "boolean"},
                "enable_timelock": {"type": "boolean"},
                "enable_steganography": {"type": "boolean"},
                "default_secret_threshold": {"type": "integer", "minimum": 2},
                "default_timelock_ttl": {"type": "integer", "minimum": 1},
                "network_delay_min": {"type": "number", "minimum": 0},
                "network_delay_max": {"type": "number", "minimum": 0},
                "secret_sharing_threshold": {"type": "integer", "minimum": 2},
                "timelock_cleanup_interval": {"type": "number", "exclusiveMinimum": 0}
            },
            "additionalProperties": True
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "time": {"type": "integer", "minimum": 0},
                    "type": {"type": "string"}
                },
                "required": ["time", "type"]
            }
        },
        "peers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}
                },
                "required": ["id"]
            }
        },
        "metadata": {
            "type": "object",
            "additionalProperties": True
        }
    },
    "required": ["events"]
}
