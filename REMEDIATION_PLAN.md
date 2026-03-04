# TrustFlow Security Remediation Plan

Based on the comprehensive system architecture analysis in `ARCHITECTURAL_ANALYSIS.md`, this document tracks the remediation progress across all phases.

---

## Phase 1: Critical Security Fixes (COMPLETED)

**Timeline:** Immediate (1-2 weeks)
**Status:** COMPLETED

| ID | Task | Status | Files Modified |
|----|------|--------|----------------|
| 1.1 | Fix deprecated `datetime.utcnow()` calls | DONE | `coc_node.py`, `audit_log.py` |
| 1.2 | Normalize SQLite schema with indexed `content_hash` | DONE | `storage_backend.py` |
| 1.3 | Add InMemoryStorage reverse index for O(1) lookup | DONE | `storage_backend.py` |
| 1.4 | Add deletion token replay protection (nonce, expiry, cache) | DONE | `deletion_engine.py` |
| 1.5 | Improve signature data with pipe delimiters | DONE | `coc_node.py`, `deletion_engine.py` |
| 1.6 | Implement gossip protocol for ZMQ (replace O(N^2) mesh) | DONE | `network/gossip.py` (NEW) |
| 1.7 | Add hypothesis/pytest-benchmark to requirements | DONE | `requirements.txt` |
| 1.8 | Implement structured JSON logging | DONE | `core/logging.py` (NEW), multiple files |
| 1.9 | Verify all tests pass | DONE | 385 tests passing |
| 1.10 | Document remaining phases | DONE | This file |

### Key Deliverables
- **New Files:**
  - `coc_framework/core/logging.py` - Structured JSON logging module
  - `coc_framework/network/gossip.py` - Gossip protocol implementation

- **Security Improvements:**
  - Deletion tokens now include nonce and expiration
  - Replay attack protection via `ProcessedTokenCache`
  - SQLite queries use indexes instead of full table scans
  - Signature data uses unambiguous pipe delimiters

---

## Phase 2: Authentication & Message Handling (COMPLETED)

**Timeline:** Short-term (2-4 weeks)
**Status:** COMPLETED

| ID | Task | Status | Files Modified |
|----|------|--------|----------------|
| 2.1 | Add HMAC authentication to secret shares | DONE | `core/secret_sharing.py` |
| 2.2 | Add authorization check to share retrieval | DONE | `core/secret_sharing.py` |
| 2.3 | Add ZMQ message authentication (SignedEnvelope) | DONE | `network/protocol.py`, `network/peer_process.py` |
| 2.4 | Add key exchange protocol for peer connections | DONE | `network/peer_process.py` |
| 2.5 | Add message deduplication in network handlers | DONE | `core/network_sim.py` |
| 2.6 | Sign gossip envelopes with origin verification | DONE | `network/gossip.py` |
| 2.7 | Add timestamp validation to messages | DONE | `network/protocol.py`, `network/gossip.py` |
| 2.8 | Add tests for Phase 2 features | DONE | `tests/test_protocol.py`, `tests/test_gossip.py`, `tests/test_network_sim.py` |

### Key Deliverables

- **New Test Files:**
  - `tests/test_protocol.py` - SignedEnvelope, timestamp validation, key exchange tests (30 tests)
  - `tests/test_gossip.py` - GossipEnvelope signatures, timestamp validation tests (26 tests)
  - `tests/test_network_sim.py` - Message deduplication tests (12 tests)

- **Security Improvements:**
  - **HMAC Authentication:** Secret shares now include HMAC for integrity verification
  - **Authorization:** Share retrieval requires peer to be in authorized recipients list
  - **SignedEnvelope:** All ZMQ messages wrapped in signed envelopes with Ed25519 signatures
  - **Key Exchange:** Peers exchange public keys on connection establishment
  - **Timestamp Validation:** Messages older than 5 minutes or >1 minute in future rejected
  - **Gossip Signatures:** Origin peer signs once, relayers preserve signature
  - **Message Deduplication:** MessageCache prevents duplicate message processing

- **Breaking Changes:**
  - `split_secret()` returns `Tuple[List[Share], bytes]` (shares + hmac_key)
  - Unsigned messages are rejected (except during key exchange)

- **Test Results:** 464 tests passing (was 385, added 79 new tests)

---

## Phase 3: Data Integrity & Architecture (PENDING)

**Timeline:** Mid-term (1-2 months)
**Status:** NOT STARTED

| ID | Task | Priority | Reference |
|----|------|----------|-----------|
| 3.1 | Add content tombstones for deleted content tracking | HIGH | ARCH-ANALYSIS Section 4.1 |
| 3.2 | Refactor SimulationEngine (decompose god object) | MEDIUM | ARCH-ANALYSIS Section 12.1 |
| 3.3 | Add strong typing throughout (TypedDict, Protocol, NewType) | LOW | ARCH-ANALYSIS Section 12.2 |
| 3.4 | Add schema version field to CoCNode | MEDIUM | ARCH-ANALYSIS Section 3.1 Issue 3 |
| 3.5 | Implement hybrid encryption for secret sharing | HIGH | ARCH-ANALYSIS Section 2.3 Issue 2 |

### Details

#### 3.1 Content Tombstones
**Problem:** Race condition between deletion and forwarding can leave orphaned references.
**Solution:**
```python
@dataclass
class ContentTombstone:
    content_hash: str
    deleted_at: datetime
    delete_after: datetime  # Grace period for in-flight forwards
```

#### 3.2 SimulationEngine Decomposition
**Problem:** 571 lines, 20+ methods - violates SRP.
**Solution:** Split into:
- `EventScheduler` - queue, tick loop
- `PeerRegistry` - lifecycle management
- `FeatureManager` - engine composition
- `ScenarioLoader` - config parsing

#### 3.5 Hybrid Encryption for Secret Sharing
**Problem:** Large content creates massive overhead (34K polynomials for 1MB).
**Solution:**
1. Generate random AES-256 key
2. Encrypt content with AES
3. Share only the 32-byte key via Shamir

---

## Phase 4: Testing Enhancements (PENDING)

**Timeline:** Mid-term (1-2 months)
**Status:** NOT STARTED

| ID | Task | Priority | Reference |
|----|------|----------|-----------|
| 4.1 | Add property-based tests with hypothesis | HIGH | ARCH-ANALYSIS Section 10.1 |
| 4.2 | Add Byzantine fault tolerance tests | HIGH | ARCH-ANALYSIS Section 10.1 |
| 4.3 | Add network chaos/partition tests | MEDIUM | ARCH-ANALYSIS Section 5.2 |
| 4.4 | Add performance benchmarks with pytest-benchmark | MEDIUM | ARCH-ANALYSIS Section 10.1 |
| 4.5 | Implement ChaosNetwork for realistic simulation | MEDIUM | ARCH-ANALYSIS Section 5.2 |

### Details

#### 4.1 Property-Based Tests
**Example:**
```python
from hypothesis import given, strategies as st

@given(
    content=st.text(min_size=1, max_size=1000),
    threshold=st.integers(min_value=2, max_value=5),
    total_shares=st.integers(min_value=2, max_value=10)
)
def test_secret_sharing_roundtrip(content, threshold, total_shares):
    assume(threshold <= total_shares)
    shares = split_secret(content, threshold, total_shares)
    reconstructed = combine_shares(shares[:threshold])
    assert reconstructed == content
```

#### 4.5 ChaosNetwork
**Implementation:**
```python
class ChaosNetwork:
    def __init__(self, latency_ms: Tuple[float, float], loss_rate: float):
        self.latency_range = latency_ms
        self.loss_rate = loss_rate
    
    async def deliver_message(self, recipient, message):
        if random.random() < self.loss_rate:
            return  # Drop message
        delay = random.uniform(*self.latency_range) / 1000
        await asyncio.sleep(delay)
        recipient.receive_message(message)
```

---

## Phase 5: Observability & Operations (PENDING)

**Timeline:** Long-term (2-3 months)
**Status:** NOT STARTED

| ID | Task | Priority | Reference |
|----|------|----------|-----------|
| 5.1 | Add OpenTelemetry tracing integration | MEDIUM | ARCH-ANALYSIS Section 6.2 |
| 5.2 | Implement audit log rotation (epoch-based sealing) | MEDIUM | ARCH-ANALYSIS Section 6.1 Issue 3 |
| 5.3 | Add external anchoring for audit logs | LOW | ARCH-ANALYSIS Section 6.1 Issue 2 |
| 5.4 | Add configuration management (environment variables) | MEDIUM | ARCH-ANALYSIS Section 9.1 |
| 5.5 | Add Prometheus metrics export | LOW | ARCH-ANALYSIS Section 6.2 |
| 5.6 | Add Merkle tree for localized audit verification | LOW | ARCH-ANALYSIS Section 6.1 Issue 1 |

### Details

#### 5.1 OpenTelemetry Integration
```python
from opentelemetry import trace, metrics

tracer = trace.get_tracer(__name__)
message_counter = metrics.get_meter(__name__).create_counter("messages_sent")

@tracer.start_as_current_span("forward_message")
def forward_message(self, node: CoCNode, recipients: List[str]):
    span = trace.get_current_span()
    span.set_attribute("node_hash", node.node_hash)
    span.set_attribute("recipient_count", len(recipients))
    message_counter.add(len(recipients))
```

#### 5.2 Epoch-Based Log Sealing
```python
class EpochLog:
    def seal_epoch(self, epoch_id: int):
        final_hash = self._entries[-1].hash
        signature = sign(final_hash)
        archive(epoch_id, self._entries, signature)
        self._entries.clear()
        self._sealed_epochs[epoch_id] = (final_hash, signature)
```

---

## Phase 6: Production Hardening (FUTURE)

**Timeline:** Long-term (3-6 months)
**Status:** NOT STARTED

| ID | Task | Priority | Reference |
|----|------|----------|-----------|
| 6.1 | Replace ZMQ with libp2p/DHT for discovery | LOW | ARCH-ANALYSIS Section 5.1 |
| 6.2 | Implement proper time-lock encryption (threshold decryption) | LOW | ARCH-ANALYSIS Section 2.4 |
| 6.3 | Add rate limiting for DoS protection | MEDIUM | ARCH-ANALYSIS Section 11.1 |
| 6.4 | Implement key rotation strategy | MEDIUM | ARCH-ANALYSIS Section 2.1 |
| 6.5 | Add encryption at rest for storage | MEDIUM | ARCH-ANALYSIS Section 11.1 |
| 6.6 | Add TLS 1.3 for transport encryption | MEDIUM | ARCH-ANALYSIS Section 11.1 |

---

## Summary

| Phase | Status | Tasks | Completed |
|-------|--------|-------|-----------|
| Phase 1: Critical Security | COMPLETED | 10 | 10 |
| Phase 2: Authentication | COMPLETED | 8 | 8 |
| Phase 3: Data Integrity | NOT STARTED | 5 | 0 |
| Phase 4: Testing | NOT STARTED | 5 | 0 |
| Phase 5: Observability | NOT STARTED | 6 | 0 |
| Phase 6: Production | NOT STARTED | 6 | 0 |
| **TOTAL** | | **40** | **18** |

---

## References

- `ARCHITECTURAL_ANALYSIS.md` - Full security audit document
- `AGENTS.md` - Development guidelines and project structure
- `coc_framework/core/logging.py` - Structured logging patterns
- `coc_framework/network/gossip.py` - Gossip protocol implementation

---

*Last Updated: 2026-01-06*
*Phase 1 Completed: 2026-01-06*
*Phase 2 Completed: 2026-01-06*
