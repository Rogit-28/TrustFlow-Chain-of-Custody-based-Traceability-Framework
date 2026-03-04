# TrustFlow File Audit

Comprehensive audit of all 27 source files (excluding tests). For each file: purpose, key dependencies, constants, classes (attributes, methods), and functions.

---
## Root Level

### scenario_runner.py (132 lines)
- **Purpose:** CLI entry to run scenario simulations using `SimulationEngine`.
- **Dependencies:** `argparse`, `json`, `asyncio`, `pathlib.Path`; local `coc_framework.config.ScenarioConfig`, `SimulationSettings`; `SimulationEngine`.
- **Constants:** `DEFAULT_SCENARIO = "scenario.json"`.
- **Functions:**
  - `load_scenario(path: Path) -> ScenarioConfig`: Load JSON into `ScenarioConfig`.
  - `run_scenario(config: ScenarioConfig, settings: SimulationSettings, verbose: bool) -> None`: Instantiate engine and run.
  - `main() -> None`: Parse CLI args (`scenario_path`, `--tick-delay`, `-v`), load scenario, run.
- **Notes:** Uses `asyncio.run(engine.run())`.

---
## Package Level (coc_framework)

### __init__.py (160 lines)
- **Purpose:** Aggregate exports for framework components; convenience factory helpers.
- **Dependencies:** Imports core interfaces/engines (`SimulationEngine`, `Config`, crypto/steg/timelock/secret sharing`).
- **Functions:**
  - `create_default_engine(settings: SimulationSettings = None) -> SimulationEngine`: Build engine with default dependencies.
  - `load_scenario_file(path: str) -> ScenarioConfig`: JSON loader.
- **Exports:** Exposes classes from config, simulation, handlers, core modules, interfaces.

### __version__.py (2 lines)
- **Purpose:** Version string.
- **Constants:** `__version__ = "0.1.0"`.

### config.py (221 lines)
- **Purpose:** Scenario and settings configuration dataclasses.
- **Dependencies:** `dataclasses`, `typing`; local `SimulationEngine` types via forward refs.
- **Constants:** Defaults for peers/thresholds/intervals.
- **Dataclasses:**
  - `SimulationSettings`: Fields `tick_delay: float = 0.1`, `total_peers: int = 5`, `secret_sharing_threshold: int = 3`, `timelock_cleanup_interval: float = 1.0`, `log_level: str = "INFO"`.
  - `ScenarioConfig`: Fields `events: List[Dict]`, `peers: List[Dict]`, `settings: Dict`; method `from_dict(dict) -> ScenarioConfig`.

### simulation_engine.py (571 lines)
- **Purpose:** Core orchestrator for in-memory simulation; manages peers, events, engines, tick loop.
- **Dependencies:** `asyncio`, `collections`, `logging`, `random`; local `config`, `event_handlers`, `core.network_sim.Network/Peer`, `core.deletion_engine.DeletionEngine`, `core.audit_log.AuditLog/AuditLogger`, `core.secret_sharing.SecretSharingEngine`, `core.timelock.TimeLockEngine`, `core.steganography.SteganoEngine`, `core.identity.IdentityStore`, `core.crypto_core.CryptoCore`, `core.validation.EventValidator`.
- **Classes:**
  - `SimulationEngine`:
    - **Attributes:** settings (`SimulationSettings`), peers map, network (`Network`), engines (deletion, audit, secret sharing, timelock, steganography), identity_store, event_handlers registry, event queue.
    - **Key Methods:**
      - `__init__(settings: SimulationSettings)`: initialize engines and registry.
      - `load_scenario(config: ScenarioConfig) -> None`: configure peers, queue events.
      - `run() -> None`: main async loop; calls `process_events` and `tick` until queue empty.
      - `tick() -> None`: process network ticks; handle offline queues.
      - `process_events()`: iterate queued events invoking handlers.
      - `register_peer(peer_id)`, `get_peer(peer_id)`, `create_peer`: peer lifecycle helpers.
      - `handle_event(event: Dict)`: validate via `EventValidator`, dispatch to `EventRegistry`.
      - `shutdown()`: cleanup timelock engine.

### event_handlers.py (794 lines)
- **Purpose:** Event registry and concrete handlers for scenario events.
- **Dependencies:** `logging`, `asyncio`; local `core` modules (coc_node, deletion_engine, secret_sharing, timelock, steganography, crypto_core, audit_log), `interfaces.notification_handler`.
- **Classes:**
  - `EventHandler` (ABC): `handle(engine, event)` abstract.
  - `EventRegistry`: map event type -> handler; `register`, `get_handler`.
  - Handlers (all implement `handle(engine, event)`):
    - `PeerOnlineHandler`, `PeerOfflineHandler`
    - `CreateMessageHandler` (creates root node, watermark, store, audit)
    - `ForwardMessageHandler` (create child node, watermark, audit)
    - `DeleteMessageHandler` (issue deletion token, broadcast, audit)
    - `DistributeSharesHandler` (split secret, send shares)
    - `ReconstructSecretHandler` (collect shares, reconstruct)
    - `TimelockContentHandler` (encrypt with timelock)
    - `DestroyTimelockHandler` (manual destroy)
    - `WatermarkForwardHandler` (watermark forward content)
    - `DetectLeakHandler` (extract watermark, audit)
- **Helper Functions:** `register_default_handlers(registry)` sets defaults.

---
## Core Module (coc_framework/core)

### __init__.py (131 lines)
- **Purpose:** Export core classes/engines; helper factory `create_default_peer`.
- **Functions:**
  - `create_default_peer(peer_id: str) -> Peer`: Build `Peer` with default storage/notification/transfer monitor.
- **Exports:** `CoCNode`, `CryptoCore`, `DeletionEngine`, `DeletionToken`, `DeletionReceipt`, `DeletionTracker`, `AuditLog`, `AuditLogger`, `TamperEvidentLog`, `SecretSharingEngine`, `TimeLockEngine`, `SteganoEngine`, `Identity`, `Certificate`, `CertificateAuthority`, `IdentityStore`.

### crypto_core.py (56 lines)
- **Purpose:** Crypto helpers for hashing and Ed25519 signing/verification.
- **Functions:**
  - `hash_content(content: str) -> str`
  - `sign_message(signing_key: SigningKey, message: str) -> bytes`
  - `verify_signature(verify_key: VerifyKey, message: str, signature: bytes) -> bool`

### coc_node.py (92 lines)
- **Purpose:** Chain-of-custody node model with signatures.
- **Dependencies:** `dataclasses`, `typing`; `CryptoCore`.
- **Classes:**
  - `SignatureVerificationError(Exception)`
  - `CoCNode` (dataclass): fields `node_hash`, `parent_hash`, `owner_id`, `content_hash`, `signature`, `timestamp`.
    - **Factory Methods:** `create_root(content, owner_id, signing_key)`, `create_child(parent, new_owner_id, signing_key)`.
    - **Methods:** `to_dict()`, `from_dict(data)`, `verify_signature(verify_key)`.

### network_sim.py (173 lines)
- **Purpose:** In-memory network/peer simulation (non-ZMQ).
- **Classes:**
  - `Peer`: attributes `peer_id`, `storage` (InMemoryStorage), `online`, `queue`, `notification_handler`, `transfer_monitor`; methods to send/receive nodes, shares, deletion tokens, go online/offline, process queue.
  - `Network`: manages peers dict; methods `add_peer`, `broadcast_deletion`, `send_node`, `send_share`, `get_peer`.

### deletion_engine.py (220 lines)
- **Purpose:** Deletion token issuance/processing and tracking receipts.
- **Dataclasses:** `DeletionToken` (node_hash, originator_id, timestamp, signature), `DeletionReceipt` (node_hash, peer_id, timestamp, status), `DeletionTracker` (track receipts).
- **Class:** `DeletionEngine`:
  - Methods: `issue_token(node_hash, originator_id, signing_key) -> DeletionToken`; `verify_token(token, verify_key) -> bool`; `process_token(token, receiving_peer)`; `record_receipt(token, peer_id, status)`; getters for receipts.

### audit_log.py (358 lines)
- **Purpose:** Tamper-evident audit logging.
- **Enums/Dataclasses:**
  - `AuditEventType(Enum)` with values (CREATE, FORWARD, DELETE, SHARE_DISTRIBUTED, SHARE_RECONSTRUCTED, TIMELOCK_CREATED, TIMELOCK_DESTROYED, WATERMARK_EMBEDDED, WATERMARK_DETECTED, LEAK_DETECTED).
  - `AuditEvent` (event_type, data, timestamp).
  - `LogEntry` (event, prev_hash, hash).
- **Classes:**
  - `TamperEvidentLog`: maintains hash chain; `append(event)`, `verify_chain()`.
  - `AuditLogger`: convenience to log events.
  - `AuditLog`: wraps `TamperEvidentLog`; `add_event(event_type, data)`, `verify()`.

### secret_sharing.py (321 lines)
- **Purpose:** Shamir Secret Sharing (k-of-n) utilities.
- **Dataclass:** `Share(index: int, value: str, content_hash: str, threshold: int, total_shares: int)`.
- **Functions:** Finite field operations: `_eval_polynomial`, `_lagrange_interpolate`, `_mod_inverse`, `_random_coefficients`, `split_secret`, `combine_shares`.
- **Class:** `SecretSharingEngine` with methods: `split_content(content, recipients, threshold) -> Dict[peer_id, Share]`; `reconstruct(shares: List[Share]) -> Optional[str]`; `validate_shares(shares)`.

### timelock.py (479 lines)
- **Purpose:** Time-locked encryption with auto key expiry using AES-256-GCM.
- **Enums/Dataclasses:** `TimeLockStatus(Enum {ACTIVE, EXPIRED, DESTROYED})`; `TimeLockMetadata`; `EncryptedContent`.
- **Classes:**
  - `CryptoUnavailableError`: raised if `cryptography` missing.
  - `KeyStore`: in-memory key storage with cleanup daemon; methods `store_key`, `get_key`, `destroy_key`, `has_key`, `get_expiry`, `start_cleanup_daemon`, `stop_cleanup_daemon`.
  - `TimeLockEngine`: methods `encrypt(content, ttl_seconds, on_expire=None) -> EncryptedContent`, `decrypt(encrypted) -> Optional[str]`, `destroy(lock_id)`, `get_status(lock_id)`, `get_remaining_time(lock_id)`, `extend_ttl(lock_id, additional_seconds)`, context-manager support, `shutdown()`.
  - `SimulatedTimeLockService`: deterministic time control for tests; methods `set_time`, `advance_time`, `encrypt`, `decrypt`, `is_expired`.

### steganography.py (519 lines)
- **Purpose:** Invisible watermarking using zero-width chars, linguistic and whitespace fingerprints.
- **Constants:** ZERO_WIDTH_CHARS, markers, synonym dicts, regex caches.
- **Dataclasses:** `WatermarkData`, `ExtractionResult`.
- **Functions:** Encoding/decoding bits, zero-width embedding/extraction, linguistic fingerprint apply/detect, whitespace fingerprint add/detect, convenience `embed_invisible_watermark`, `extract_invisible_watermark`.
- **Class:** `SteganoEngine`:
  - Methods: `register_peer`, `embed_watermark(content, peer_id, depth=0, timestamp=None, use_zero_width=True, use_linguistic=True, use_whitespace=True) -> str`, `extract_watermark(content, candidate_peers=None) -> ExtractionResult`, `strip_all_watermarks`, `verify_watermark`, `get_visible_diff`.

### identity.py (490 lines)
- **Purpose:** PKI identities and certificates; CA issuance/verification; identity store.
- **Dataclasses:** `Identity`, `Certificate` with helpers `to_dict/from_dict`, validity checks, self-signed detection, canonical signed data.
- **Classes:**
  - `CertificateAuthority`: issue/verify certificates; caching; `create_self_signed`, `verify_self_signed`, `invalidate_cache`.
  - `IdentityStore`: store identities/certificates; add/get/revoke/list; `get_valid_certificate(peer_id)`.

### validation.py (477 lines)
- **Purpose:** Input validation for events, scenarios, hashes, timestamps, signatures, keys.
- **Dataclasses/Exceptions:** `ValidationError`, `ValidationResult` (add_error, merge).
- **Class:** `EventValidator`: required fields map, alternative fields, type checks; methods `validate_event`, `_validate_field_values`, `validate_scenario`.
- **Functions:** `validate_peer_id`, `validate_content_hash`, `validate_timestamp`, `validate_signature_hex`, `validate_public_key_hex`.

---
## Interfaces Module (coc_framework/interfaces)

### __init__.py (42 lines)
- **Purpose:** Export ABCs/default implementations; conditional `SQLiteStorage` import.

### storage_backend.py (233 lines)
- **Purpose:** Storage abstraction; in-memory and SQLite implementations.
- **Classes:**
  - `StorageBackend` (ABC): node/content CRUD and reference check methods.
  - `InMemoryStorage`: dict-based storage; aliases `store_node`, `store_content`.
  - `SQLiteStorage`: persistent storage using sqlite3; tables `nodes`, `content`; implements CRUD; context manager.

### peer_discovery.py (52 lines)
- **Purpose:** Peer discovery interface and registry implementation.
- **Classes:** `PeerDiscovery` (ABC with find/register/unregister/list/status); `RegistryPeerDiscovery` (in-memory registry using `peer.peer_id`, `peer.online`).

### notification_handler.py (61 lines)
- **Purpose:** Notification callbacks.
- **Classes:** `NotificationHandler` ABC (message received/forwarded, deletion requested, peer status, queue processed); implementations `SilentNotificationHandler`, `LoggingNotificationHandler` (stdout prints).

### transfer_monitor.py (44 lines)
- **Purpose:** Transfer monitoring and encryption policy hints.
- **Enums:** `TransferAccessType`, `EncryptionPolicyEnum`.
- **Classes:** `TransferMonitor` ABC (accessed, transfer attempt, allow, encryption policy); `NullTransferMonitor` (no-op, allow all, encryption policy ALLOW).

### encryption_policy.py (39 lines)
- **Purpose:** Encryption policy abstraction.
- **Enums:** `EncryptionMode` (NONE, RECOVERABLE, IRRECOVERABLE).
- **Classes:** `EncryptionPolicy` ABC; `NoEncryption` (pass-through bytes/strings, always decryptable).

---
## Network Module (coc_framework/network)

### __init__.py (34 lines)
- **Purpose:** Export network message classes and coordinator/peer.

### protocol.py (552 lines)
- **Purpose:** Message types and serialization for ZeroMQ network.
- **Enums/Constants:** `MessageType`, `PeerStatus`, maps `MESSAGE_TYPE_MAP`, `PEER_STATUS_MAP`; `MESSAGE_CLASSES` lookup; `SocketConfig` (port constants, timeouts, heartbeat intervals, address builders).
- **Dataclasses:** `NetworkMessage` (base with msg_id hash generation), `ShareMessage`, `DeletionTokenMessage`, `CoCNodeMessage`, `PeerStatusMessage`, `ContentMessage`, `RequestMessage`, `ResponseMessage`, `HeartbeatMessage` (each sets `msg_type`, adds fields, to_dict/from_dict).
- **Functions:** `deserialize_message(data) -> NetworkMessage` (bytes/str/dict supported).

### coordinator.py (612 lines)
- **Purpose:** Multiprocess coordinator to spawn peers and execute scenarios (uses ZeroMQ).
- **Dependencies:** `asyncio`, `multiprocessing.Process`, `zmq.asyncio` (optional), `SigningKey`, protocol classes, `peer_process` helpers, core modules.
- **Dataclasses:** `PeerInfo` (peer metadata, addresses, signing key), `ScenarioEvent` (event_type, timestamp, params, executed flag).
- **Class:** `NetworkCoordinator`:
  - Peer management: `create_peer`, `start_peer`, `stop_peer`, start/stop all.
  - In-process mode: `run_in_process(num_peers) -> List[NetworkPeer]`, `stop_in_process_peers`.
  - Scenario: `load_scenario(path)`, `add_event`, `execute_scenario`, `_execute_event` dispatchers for create/forward/delete/online/offline/distribute_shares.
  - Helpers: `_find_peer`, results/audit getters, event callback setter.
- **Demo:** `demo()` async runner and `__main__` guard.

### peer_process.py (620 lines)
- **Purpose:** Standalone peer process using ZeroMQ PUB/SUB/REP; manages storage, shares, content, deletion, heartbeats.
- **Dependencies:** `asyncio`, `zmq.asyncio`, `SigningKey/VerifyKey`, protocol classes, `CryptoCore`, `InMemoryStorage`.
- **Dataclasses:** `PeerConfig` (id, index, host, signing_key, feature flags), `PeerState` (online status, connections, pending messages, heartbeats).
- **Class:** `NetworkPeer`:
  - Attributes: config, peer_id, signing/verify keys, storage, shares, content, peer_keys, message handlers map, zmq context/sockets, offline queue, state.
  - Lifecycle: `start()`, `stop()`, connect/disconnect peers.
  - Message loops: `_rep_loop`, `_sub_loop`, `_heartbeat_loop`.
  - Handlers: `_handle_share`, `_handle_deletion`, `_handle_coc_node`, `_handle_peer_status`, `_handle_content`, `_handle_request_share`, `_handle_request_content`, `_handle_heartbeat`.
  - Sending: `_broadcast`, `_broadcast_status`, `send_direct`, `broadcast_deletion`, `send_share`, `send_coc_node`.
  - Offline: `go_offline`, `go_online`, `process_pending_messages`.
  - Utilities: `register_peer_key`, `get_share`, `get_content`.
- **Function:** `run_peer_process(config_dict)` entrypoint; `__main__` CLI guard.

---
## Summary Statistics
- Files audited: 27
- Total source lines (approx): 6,478
- Key domains: simulation engine, event handling, crypto (hash/signature), deletion, audit, secret sharing, timelock encryption, steganography, identity/PKI, validation, interfaces (storage/notifications/monitoring/encryption), network (protocol, coordinator, peer process).
