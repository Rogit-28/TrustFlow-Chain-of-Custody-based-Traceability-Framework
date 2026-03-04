# TrustDocs
## Product Requirements Document
**Version:** 1.0 | **Status:** Approved for Development
**Stack:** Python 3.11 · FastAPI · PostgreSQL 16 · TrustFlow 2.0.0 · Vanilla JS · Pico.css

---

## 1. Product Vision

TrustDocs is a secure P2P document collaboration platform that makes cryptographic provenance invisible to users but inescapable in the system. Every document uploaded, shared, or deleted leaves a mathematically verifiable trail — not because a server says so, but because the cryptography enforces it.

Users experience a familiar document workspace: upload files, share them, comment, chat. What they don't see is TrustFlow operating beneath every action — building a chain-of-custody graph, embedding steganographic watermarks in every shared copy, and propagating cryptographically-signed deletion tokens across the distributed network when a document is removed.

**Positioning:** TrustDocs is to Google Drive what Signal is to SMS. The UX is familiar. The trust model is fundamentally different.

---

## 2. Problem Statement

Existing cloud document platforms operate on a trust-the-server model. Access logs are server-controlled and mutable. Deletion is unverifiable — the server says it deleted your file, and you have no recourse if it didn't. When a document leaks, there is no cryptographic mechanism to identify which authorised recipient forwarded it.

TrustDocs solves three problems that no existing product solves simultaneously:

1. **Verifiable deletion:** When an owner deletes a document, a cryptographically-signed deletion token propagates to every node that holds a copy. Deletion is provable, not promised.
2. **Leak attribution:** Every shared copy is uniquely watermarked using steganographic techniques. A leaked document identifies its forwarder without ambiguity.
3. **Tamper-evident audit:** Every action is recorded in a hash-chained audit log. Any retrospective tampering with the log is mathematically detectable.

**Academic gap this fills:** No existing system closes the loop between hybrid access control, verifiable deletion propagation, and steganographic leak attribution in a single distributed document platform. Xue et al. (2018) addresses access control without provenance. Blockchain ABE systems (2024) provide immutable logs without leak attribution. TrustDocs unifies all three.

---

## 3. Users

### 3.1 End User
A professional who uploads, receives, and collaborates on sensitive documents. They are not expected to understand cryptography. They interact with a document workspace that looks and feels like any modern file sharing tool.

### 3.2 Document Owner
An end user who has uploaded a document. They have exclusive rights to share it, revoke access, and delete it. Deletion is permanent and propagates to all recipients — this is a product guarantee, not a setting.

### 3.3 Document Recipient
An end user who has received a shared document. They can view, download, comment, and chat around the document. They cannot share it further in MVP (forward control is a future feature).

### 3.4 Platform Admin
Operates Node A. Has read-only access to the audit dashboard: the live CoC graph, the hash-chained audit log, and the leak attribution tool. Cannot modify any document data.

---

## 4. System Architecture

### 4.1 Node Topology

```
┌─────────────────────────────────────┐
│         Node A — Trust Anchor        │
│                                     │
│  PostgreSQL 16 (single DB)          │
│  TrustFlow ZeroMQ Coordinator       │
│  TrustFlow AuditLog (hash-chained)  │
│  Admin Dashboard (FastAPI + WS)     │
│  SSH tunnel listener (B, C)         │
└──────────────┬──────────────────────┘
               │ ZeroMQ over SSH tunnel
       ┌───────┴────────┐
       ▼                ▼
┌─────────────┐  ┌─────────────┐
│   Node B    │  │   Node C    │
│             │  │             │
│ TrustDocs   │  │ TrustDocs   │
│ FastAPI App │  │ FastAPI App │
│             │  │             │
│ TrustFlow   │  │ TrustFlow   │
│ Peer Process│  │ Peer Process│
│ (ZeroMQ)    │  │ (ZeroMQ)    │
└─────────────┘  └─────────────┘
```

Nodes B and C are architecturally identical. They are stateless with respect to the database — all persistence goes to Node A's PostgreSQL over a connection pool. File ciphertext is stored locally on the node that received the upload, with the storage path recorded in PostgreSQL.

Node A is the trust anchor. Its availability is a deliberate architectural constraint, not a limitation — it enforces that all custody events are witnessed by a neutral third party. This is noted as a conscious design decision in the academic report.

### 4.2 Communication Layers

| Layer | Protocol | Purpose |
|---|---|---|
| User ↔ Node B/C | HTTPS + WebSocket | Document operations, chat, real-time updates |
| Node B/C ↔ Node A | ZeroMQ DEALER/ROUTER over SSH tunnel | TrustFlow custody events, audit log writes |
| Node B/C ↔ PostgreSQL | TCP (pg connection pool) | All persistent data reads/writes |
| Inter-node gossip | ZeroMQ via Node A coordinator | Deletion token propagation, peer status |

### 4.3 TrustFlow as Internal Service

TrustFlow runs as an in-process service on each peer node (B and C), instantiated at application startup as a `TrustFlowService` singleton. FastAPI route handlers on the critical path — upload, share, delete — call `TrustFlowService` methods directly within async endpoints. This eliminates network hops on operations where latency and atomicity matter.

TrustFlow's REST API (`coc_framework.api.server`) is reserved exclusively for two surfaces: the Node A admin dashboard (which needs a queryable snapshot of the CoC graph state) and any future external integrations. It is not in the request path for any user-facing operation on Nodes B or C.

This boundary is intentional. The in-process model gives the product path the performance and simplicity of direct method calls. The REST API gives the admin and integration surface the queryability of HTTP without coupling it to the product's latency requirements.

---

## 5. Feature Specifications

### 5.1 Authentication & Identity

**Registration:**
- User provides username, email, password.
- Server generates an Ed25519 keypair via `CryptoCore.generate_keypair()`.
- An Argon2id KDF (time=2, memory=65536, parallelism=2) derives a 256-bit wrapping key from the user's password.
- The signing key is encrypted with AES-256-GCM using the derived wrapping key. Only the ciphertext is stored in PostgreSQL. The server never holds a plaintext signing key after the request completes.
- A TrustFlow `Identity` object is created and registered with the node's `CertificateAuthority`.
- The verify key (public) is stored in plaintext in PostgreSQL for recipient lookup during sharing.

**Login:**
- Password submitted, Argon2id re-derives the wrapping key, signing key decrypted in memory for the session duration.
- Session token (cryptographically random 32 bytes, stored server-side in PostgreSQL) returned as an HTTP-only cookie.

**Logout:** Session token invalidated server-side. Signing key discarded from memory.

### 5.2 Document Upload

**User flow:** User selects a file from the upload panel. Progress indicator while encrypting and uploading.

**System behaviour:**
1. Client generates a random AES-256-GCM content key using the WebCrypto API.
2. File is encrypted in-browser. Ciphertext and the content key (encrypted with the user's public key, also via WebCrypto) are sent to the server.
3. FastAPI endpoint receives ciphertext, writes it to local disk on the receiving node. File path and size recorded in PostgreSQL.
4. Server computes SHA-256 of the plaintext content (sent alongside as a hash commitment from the client, verifiable).
5. TrustFlow `Peer.create_coc_root()` called with `content_hash` and `recipient_ids=[]` (no recipients yet). Returns a signed `CoCNode`.
6. `node_hash` and `content_hash` stored in the `documents` PostgreSQL table.
7. ZeroMQ `LOG_EVENT` sent to Node A — AuditLog records `UPLOAD` event.
8. WebSocket push to admin dashboard — new node appears in CoC graph.

**Supported formats:** PDF, DOCX, XLSX, PNG, JPG, TXT. Max file size: 50MB.

### 5.3 Document Sharing

**User flow:** Owner opens a document, clicks Share, searches for a recipient by username, confirms. Recipient sees the document appear in their workspace immediately if online.

**System behaviour:**
1. Server looks up recipient's `verify_key` from PostgreSQL.
2. A unique watermark is embedded in the document content via `WatermarkEngine.embed_watermark()` with the recipient's `peer_id` and the current `CoCNode` depth. Each recipient receives a cryptographically distinct copy.
3. The watermarked content is re-encrypted with the recipient's public key. A new ciphertext file is written to disk.
4. TrustFlow `Peer.forward_coc_message()` called — creates a child `CoCNode` signed by the owner, linking to the root node.
5. A `SHARE` record inserted into PostgreSQL with `owner_id`, `recipient_id`, `document_id`, `child_node_hash`.
6. If recipient is online: ZeroMQ message to their peer process delivers the CoC node. Document appears in their workspace via WebSocket push.
7. If recipient is offline: TrustFlow offline queue holds the delivery. Document delivered when they next connect.
8. ZeroMQ `LOG_EVENT` to Node A — AuditLog records `SHARE` event with both peer IDs.

### 5.4 Document Download & Decryption

**User flow:** User clicks a document. It downloads and opens.

**System behaviour:**
1. Server verifies the requesting user has access (owner or active share record).
2. TransferMonitor fires `on_message_accessed()` — recorded in audit log.
3. Encrypted ciphertext streamed to client.
4. Client decrypts using their content key (stored encrypted in the browser session, decrypted with their private key via WebCrypto).
5. File opened in browser or saved to disk.

### 5.5 Document Deletion

**User flow:** Owner clicks Delete on a document. A confirmation modal explains this is permanent and propagates to all recipients. Owner confirms.

**System behaviour:**
1. Server verifies requester is the document owner. Non-owners receive a 403 — there are no exceptions.
2. `DeletionEngine.issue_token()` creates a signed `DeletionToken` for the root `CoCNode`.
3. `get_all_descendants()` traverses the CoC graph to collect every child node and its owning peer.
4. Deletion token propagated to every peer holding a descendant node via ZeroMQ. Each peer's `DeletionEngine.process_token()` verifies the signature and removes the node and content from storage.
5. PostgreSQL `documents` record soft-deleted (status → `deleted`). Ciphertext files removed from disk on all nodes.
6. `file_shares` records for this document marked `revoked`.
7. Recipients who are offline receive the deletion token when they reconnect via the offline queue — their copy is deleted on first connection after the owner's deletion.
8. ZeroMQ `LOG_EVENT` to Node A — AuditLog records `DELETE` event. CoC graph node turns red, then fades from the admin dashboard.
9. Document disappears from all recipient workspaces via WebSocket push.

**Tombstone grace period:** Upon deletion, a `ContentTombstone` is written for the document's `content_hash` with a 5-minute TTL. During this window, any in-flight download or re-insertion attempt for this content hash is blocked at the application layer and returns a specific 409 response: `"This document has been deleted and is pending full propagation across all nodes."` The UI renders this as a non-generic notice distinguishable from a standard 404. After the TTL expires, the tombstone is removed. This prevents a race condition where a deletion token and an in-flight forward arrive at a peer out of order.

**Product guarantee stated explicitly in UI:** "Deletion is permanent and cryptographically enforced across all nodes. Recipients who are currently offline will have their copies deleted when they reconnect."

### 5.6 Comments

- Per-document threaded comments, visible to owner and all active recipients.
- Stored in PostgreSQL `comments` table, scoped by `document_id`.
- Access check on every read: if share record is `revoked` or document is `deleted`, comments return 404.
- New comments pushed to all connected document viewers via WebSocket.
- Comments are not CoC-tracked in this version. Noted as future work.

### 5.7 Messaging (Chat)

- Per-document chat room, accessible to owner and active recipients.
- Stored in PostgreSQL `messages` table, scoped by `document_id`.
- Delivered via WebSocket. Room keyed on `document_id`. Users join the room on document open, leave on close.
- Message history loaded on room join (last 100 messages).
- Same access model as comments: revoked shares lose chat access immediately.
- Messages are not CoC-tracked in this version. Noted as future work.

### 5.8 Admin Dashboard (Node A)

- **Live CoC Graph:** vis.js force-directed graph. Nodes = peers. Edges = custody relationships. Node colour = online/offline. Deletion events animate in real-time (edge removal, node fade).
- **Audit Log Viewer:** Paginated table of all events. "Verify Integrity" button runs `AuditLog.verify_log_integrity()` and returns pass/fail with chain length.
- **Leak Attribution Tool:** Admin pastes or uploads a suspected leaked document. `WatermarkEngine.extract_and_verify_watermark()` runs and returns the `peer_id` of the forwarder, timestamp, and CoC depth. Result displayed with confidence indicator.
- **Peer Status Panel:** Online/offline status of all registered peers, last-seen timestamp, queued message count.

---

## 6. Data Model

```sql
users
  id UUID PK
  username TEXT UNIQUE NOT NULL
  email TEXT UNIQUE NOT NULL
  password_hash TEXT NOT NULL          -- bcrypt
  encrypted_signing_key BYTEA NOT NULL -- AES-256-GCM, Argon2id-derived key
  verify_key_hex TEXT NOT NULL         -- Ed25519 public key, plaintext
  peer_id TEXT UNIQUE NOT NULL         -- TrustFlow peer identity
  node_id TEXT NOT NULL                -- Which node (A/B/C) they registered on
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

documents
  id UUID PK
  owner_id UUID FK → users.id
  filename TEXT NOT NULL
  mime_type TEXT NOT NULL
  size_bytes BIGINT NOT NULL
  storage_path TEXT NOT NULL           -- Local ciphertext path on the storing node
  storage_node TEXT NOT NULL           -- Which node holds the ciphertext
  content_hash TEXT NOT NULL           -- SHA-256 of plaintext
  coc_node_hash TEXT NOT NULL          -- TrustFlow root CoCNode hash
  status TEXT NOT NULL DEFAULT 'active' -- active | deleted
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at TIMESTAMPTZ

file_shares
  id UUID PK
  document_id UUID FK → documents.id
  owner_id UUID FK → users.id
  recipient_id UUID FK → users.id
  child_coc_node_hash TEXT NOT NULL    -- TrustFlow child CoCNode hash
  status TEXT NOT NULL DEFAULT 'active' -- active | revoked
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  revoked_at TIMESTAMPTZ

comments
  id UUID PK
  document_id UUID FK → documents.id
  author_id UUID FK → users.id
  body TEXT NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

messages
  id UUID PK
  document_id UUID FK → documents.id
  sender_id UUID FK → users.id
  body TEXT NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

sessions
  id UUID PK
  user_id UUID FK → users.id
  token_hash TEXT NOT NULL             -- SHA-256 of session token
  expires_at TIMESTAMPTZ NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

---

## 7. API Surface

All endpoints require a valid session cookie except `/auth/register` and `/auth/login`.

```
POST   /auth/register
POST   /auth/login
POST   /auth/logout

GET    /documents                      -- List owned + shared documents
POST   /documents                      -- Upload document
GET    /documents/{id}                 -- Document metadata
DELETE /documents/{id}                 -- Owner-only deletion
POST   /documents/{id}/share           -- Share with recipient
DELETE /documents/{id}/share/{user_id} -- Revoke share

GET    /documents/{id}/comments        -- List comments
POST   /documents/{id}/comments        -- Post comment

GET    /documents/{id}/messages        -- Message history (last 100)

WS     /ws/documents/{id}             -- Real-time: chat messages, comment pushes
WS     /ws/admin                      -- Real-time: CoC graph updates, peer status

POST   /admin/verify-log              -- Trigger AuditLog integrity check
POST   /admin/detect-leak             -- Watermark attribution on uploaded content
GET    /admin/peers                   -- Peer status list
GET    /admin/graph                   -- Current CoC graph state (snapshot)
```

---

## 8. Non-Functional Requirements

| Concern | Requirement | Rationale |
|---|---|---|
| Encryption at rest | AES-256-GCM for all file content | NIST SP 800-38D compliant |
| Key derivation | Argon2id (RFC 9106 recommended parameters) | Resistant to GPU brute-force |
| Signing | Ed25519 via PyNaCl | 128-bit security, fast verification |
| Transport | WSS + HTTPS for production, HTTP acceptable for demo LAN | |
| Session tokens | 32 cryptographically random bytes, server-side storage | No JWT — no stateless token forgery surface |
| File op latency | ≤ 5s for files ≤ 10MB on LAN | Acceptable for demo and real-world LAN use |
| Deletion guarantee | Token delivery to all online peers within 3s on LAN | Measured and reported as evaluation metric |
| Audit integrity | Hash chain verification must complete in ≤ 2s for 10,000 entries | Measured and reported |
| DB availability | Single PostgreSQL on Node A — B/C reconnect with exponential backoff on connection loss | |

---

## 9. Dependency Stack

```
# Python 3.11 — all versions conflict-verified

# Existing TrustFlow (do not modify versions)
PyNaCl==1.5.0
aiohttp==3.9.1
aiohttp-jinja2==1.6
Jinja2==3.1.3

# TrustDocs application layer
fastapi==0.111.0
uvicorn[standard]==0.29.0
websockets==12.0
asyncpg==0.29.0              # async PostgreSQL driver, no ORM overhead
bcrypt==4.1.3
argon2-cffi==23.1.0
python-multipart==0.0.9      # FastAPI file upload support
aiofiles==23.2.1             # Async file I/O

# No additional ZeroMQ packages needed — pyzmq already a TrustFlow transitive dep
```

**Architecture note on async:** FastAPI runs on uvicorn's asyncio event loop. TrustFlow's `SimulationEngine.tick()` is async-native. Both coexist on the same event loop — no thread pools, no monkey-patching, no process boundaries between the API and TrustFlow. ZeroMQ communication to Node A uses `pyzmq`'s async interface (`zmq.asyncio`). This is the clean architecture the stack deserves.

---

## 10. Technical Debt in TrustFlow to Resolve Before Integration

These must be resolved before any CloudNote code is written. They are not optional.

| Item | File | Fix |
|---|---|---|
| Event field dialect split (`originator_idx` vs `originator_id`) | `simulation_engine.py` | Standardise to ID-based throughout |
| `FORWARD_MESSAGE` requires runtime `parent_node_hash` injection | `simulation_engine.py` | Add `message_id → node_hash` registry |
| `AuditLog` writes locally on each peer | `audit_log.py` | Peer nodes emit `LOG_EVENT` via ZeroMQ to Node A; only Node A writes to disk |
| `datetime.utcnow()` deprecated | `audit_log.py`, `deletion_engine.py` | Replace with `datetime.now(timezone.utc)` |
| `watermark_engine.py` `__main__` block calls removed kwarg `chain_position` | `watermark_engine.py` | Update to `depth` |

---

## 11. Out of Scope (MVP)

The following are explicitly deferred and must be cited as future work in the academic report — each maps to a real literature gap.

- Forward control (recipients cannot re-share) — maps to dynamic access revocation (Garrison et al. 2016)
- CoC-tracked chat messages — natural TrustFlow extension, noted
- Role-Based Access Control / ABE policies — maps to Xue et al. 2018 and blockchain ABE papers
- Multi-cloud storage distribution — maps to CloudLock (2025)
- Mobile client — standard future work
- Shamir secret sharing UI — TrustFlow has the engine; the product surface is deferred
