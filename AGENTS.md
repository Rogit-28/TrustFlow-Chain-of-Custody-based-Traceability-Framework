# AGENTS.md - Coding Agent Instructions

## Project Overview

TrustFlow is a Python-based Chain of Custody (CoC) Privacy Framework Simulator. It models
decentralized privacy and trust in a P2P network with message provenance tracking, secure
deletion propagation, cryptographic signatures, and steganographic watermarking for leak attribution.

## Repository Location

```
C:\Users\rogit\dev\Trustflow-local-dev\TrustFlow-Chain-of-Custody-based-Traceability-Framework
```

## Project Structure

```
TrustFlow-Chain-of-Custody-based-Traceability-Framework/
├── coc_framework/
│   ├── __init__.py # Package exports
│   ├── __version__.py # Version string
│   ├── config.py # SimulationSettings, ScenarioConfig
│   ├── event_handlers.py # Event processing handlers (793 lines)
│   ├── simulation_engine.py # In-memory orchestrator
│   ├── core/
│   │   ├── __init__.py # Core module exports
│   │   ├── audit_log.py # Hash-chained tamper-evident logging
│   │   ├── coc_node.py # CoC graph node with crypto signatures
│   │   ├── crypto_core.py # Ed25519 signing, SHA-256 hashing
│   │   ├── deletion_engine.py # Deletion token issuance/propagation
│   │   ├── identity.py # Identity, Certificate, CA, IdentityStore (PKI)
│   │   ├── logging.py # Structured logging (JSONFormatter, loggers)
│   │   ├── network_sim.py # In-memory Peer/Network simulation
│   │   ├── secret_sharing.py # Shamir's Secret Sharing
│   │   ├── steganography.py # Invisible watermarking for leak attribution
│   │   ├── timelock.py # Time-lock encryption (AES-256-GCM)
│   │   └── validation.py # Validation utilities (EventValidator, etc.)
│   ├── interfaces/
│   │   ├── __init__.py # Interface exports
│   │   ├── encryption_policy.py # EncryptionPolicy ABC + NoEncryption
│   │   ├── notification_handler.py # NotificationHandler ABC + implementations
│   │   ├── peer_discovery.py # PeerDiscovery ABC + RegistryPeerDiscovery
│   │   ├── storage_backend.py # StorageBackend ABC + InMemoryStorage + SQLiteStorage
│   │   └── transfer_monitor.py # TransferMonitor ABC + NullTransferMonitor
│   └── network/
│       ├── __init__.py # Network layer exports
│       ├── coordinator.py # Multi-process orchestrator (ZeroMQ)
│       ├── gossip.py # Gossip protocol for message propagation
│       ├── peer_process.py # Standalone peer process
│       └── protocol.py # Message types and serialization
├── tests/ # Test suite (16 test files)
│   ├── test_audit_log.py
│   ├── test_config.py
│   ├── test_crypto_core.py
│   ├── test_deletion_receipt.py
│   ├── test_gossip.py
│   ├── test_identity.py
│   ├── test_network_sim.py
│   ├── test_protocol.py
│   ├── test_secret_sharing.py
│   ├── test_simulation_engine.py
│   ├── test_steganography.py
│   ├── test_storage_backend.py
│   ├── test_timelock.py
│   └── test_validation.py
├── scenario_runner.py # CLI entry point
├── scenario.json # Sample scenario file
├── requirements.txt # Dependencies
├── README.md
├── AGENTS.md # This file
├── LICENSE
└── .gitignore
```

## Build/Lint/Test Commands

### Environment Setup
```bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### Running the Simulation
```bash
# CLI simulation runner (default scenario.json)
python scenario_runner.py

# With custom scenario file
python scenario_runner.py path/to/scenario.json

# With verbose logging
python scenario_runner.py -v

# With custom tick delay
python scenario_runner.py --tick-delay 0.5
```

### Running Tests
```bash
# Tests will be added as needed
python -m pytest tests/ -v
```

### No Formal Linting
This project does not have a configured linter. Follow PEP 8 conventions manually.

## Code Style Guidelines

### Imports
- Standard library imports first, then third-party, then local modules
- Use absolute imports from `coc_framework` package
- Group imports in order: stdlib, third-party (`nacl`, `cryptography`), local
```python
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict

from nacl.signing import SigningKey, VerifyKey

from coc_framework.core.crypto_core import CryptoCore
from coc_framework.interfaces.storage_backend import StorageBackend
```

### Datetime Handling
- **Always use timezone-aware datetimes**
- Use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`
```python
from datetime import datetime, timezone

timestamp = datetime.now(timezone.utc).isoformat()
```

### Formatting
- 4 spaces for indentation (no tabs)
- Max line length: ~100 characters (soft limit)
- Use double quotes for strings
- Add trailing comma in multi-line collections
- One blank line between methods, two between classes

### Type Hints
- Use type hints for all function parameters and return types
- Use `Optional[T]` for nullable types
- Use `List`, `Dict`, `Set` from `typing` module
- Use `TYPE_CHECKING` guard for forward references to avoid circular imports
```python
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Dict

if TYPE_CHECKING:
    from .network_sim import Peer
    from .coc_node import CoCNode

def process_token(self, token: DeletionToken, receiving_peer: Peer) -> None:
```

### Naming Conventions
- Classes: `PascalCase` (e.g., `CoCNode`, `DeletionEngine`, `SimulationEngine`)
- Functions/methods: `snake_case` (e.g., `create_coc_root`, `process_token`)
- Variables: `snake_case` (e.g., `peer_id`, `node_hash`, `recipient_ids`)
- Constants: `UPPER_SNAKE_CASE`
- Private attributes: `_leading_underscore` (e.g., `_nodes`, `_peers`)
- Interfaces/ABCs: Descriptive names (e.g., `StorageBackend`, `NotificationHandler`)

### Error Handling
- Use specific exceptions, not bare `except:`
- Log errors with context before raising/handling
- Use `try-except` for external operations (file I/O, crypto)
- Return `None` or `False` for non-critical failures instead of raising
```python
try:
    verify_key.verify(message.encode('utf-8'), signature)
    return True
except nacl.exceptions.BadSignature:
    return False
```

### Async Patterns
- Use `async/await` for network operations
- Use `asyncio.create_task()` for fire-and-forget operations
- Use `asyncio.sleep()` for simulated delays
- Run async code with `asyncio.run()`

### Documentation
- Docstrings for all public classes and methods
- Use triple quotes with description on first line
- Document parameters and return values for complex methods

## Architecture Patterns

### Abstract Interfaces (in `coc_framework/interfaces/`)
All interfaces use ABC pattern with default implementations:
- `StorageBackend` -> `InMemoryStorage`, `SQLiteStorage`
- `PeerDiscovery` -> `RegistryPeerDiscovery`
- `NotificationHandler` -> `SilentNotificationHandler`, `LoggingNotificationHandler`
- `TransferMonitor` -> `NullTransferMonitor`
- `EncryptionPolicy` -> `NoEncryption`

### Dependency Injection
Components receive dependencies via constructor with sensible defaults:
```python
class Peer:
    def __init__(self, deletion_engine, peer_id=None, storage_backend=None, ...):
        self.storage = storage_backend or InMemoryStorage()
```

### Dataclasses for Data Transfer Objects
Use `@dataclass` for simple data structures:
```python
@dataclass
class DeletionToken:
    node_hash: str
    originator_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""
```

### Serialization Pattern
Objects implement `to_dict()` and `from_dict()` for JSON serialization:
```python
def to_dict(self) -> Dict:
    return asdict(self)

@staticmethod
def from_dict(data: Dict) -> DeletionToken:
    return DeletionToken(**data)
```

## Key Components

| Component | Purpose |
|-----------|---------|
| `SimulationEngine` | In-memory orchestrator, processes scenario events |
| `EventHandler` | Event processing handlers for scenario events |
| `CoCNode` | CoC graph node with cryptographic signatures |
| `Peer` / `Network` | In-memory P2P simulation |
| `DeletionEngine` | Deletion token issuance and propagation |
| `SecretSharingEngine` | Shamir's (k,n) threshold secret sharing |
| `TimeLockEngine` | Time-locked encryption with auto-expiring keys |
| `SteganoEngine` | Invisible watermarking (zero-width, linguistic, whitespace) |
| `NetworkCoordinator` | Multi-process orchestrator using ZeroMQ |
| `NetworkPeer` | Standalone peer process for real network simulation |
| `GossipProtocol` | Gossip-based message propagation |
| `Identity` / `CertificateAuthority` | PKI identity management |
| `EventValidator` | Validation utilities for events |
| `AuditLogger` | Tamper-evident hash-chained logging |

## Scenario Event Types

| Event Type | Description | Required Fields |
|------------|-------------|-----------------|
| `CREATE_MESSAGE` | Originator creates root CoC node | `originator_id`, `recipient_ids`, `content` |
| `FORWARD_MESSAGE` | Sender forwards to new recipients | `sender_id`, `recipient_ids`, `parent_message_id` |
| `DELETE_MESSAGE` | Originator initiates deletion | `originator_id`, `node_hash` |
| `PEER_ONLINE` | Peer comes online, processes queue | `peer_id` |
| `PEER_OFFLINE` | Peer goes offline, starts queuing | `peer_id` |
| `DISTRIBUTE_SHARES` | Split content into secret shares | `peer_id`, `content`, `recipients`, `threshold` |
| `RECONSTRUCT_SECRET` | Reconstruct from collected shares | `peer_id`, `content_hash` |
| `TIMELOCK_CONTENT` | Create time-locked encrypted content | `peer_id`, `content`, `ttl_seconds` |
| `DESTROY_TIMELOCK` | Manually destroy a timelock | `peer_id`, `lock_id` |
| `WATERMARK_FORWARD` | Forward with steganographic watermark | `sender_id`, `recipient_ids`, `parent_message_id` |
| `DETECT_LEAK` | Analyze leaked content for watermarks | `content` |

## Cryptographic Conventions

- **Keypairs**: Ed25519 via PyNaCl (`SigningKey`, `VerifyKey`)
- **Hashing**: SHA-256 for content hashes
- **Signatures**: Sign message string, store as hex
- **Secret Sharing**: Shamir's scheme over 256-bit prime field
- **Timelock Encryption**: AES-256-GCM with automatic key destruction
- **Watermarks**: Zero-width Unicode + linguistic fingerprinting + whitespace patterns

## Common Pitfalls

1. **Async tick()**: `SimulationEngine.tick()` is async - use `await` or `asyncio.run()`
2. **Circular imports**: Use `TYPE_CHECKING` guard for type hints
3. **Node lookup**: Use `storage.get_node(hash)`, not direct dict access
4. **Signature format**: Convert between bytes and hex for serialization
5. **Deletion propagation**: Only node owner can issue deletion tokens
6. **TimeLock cleanup**: Call `engine.shutdown()` to stop background cleanup thread
7. **Datetime**: Use `datetime.now(timezone.utc)` not `datetime.utcnow()`
8. **EventHandler**: Large file (793 lines) - check event_handlers.py for all event types
9. **Identity/PKI**: Import from `coc_framework.core.identity`, not top-level
10. **Validation**: Use `EventValidator` for scenario event validation
