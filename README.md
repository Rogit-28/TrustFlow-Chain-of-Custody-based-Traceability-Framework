# TrustFlow - Chain of Custody Privacy Framework

A Python-based simulator for modeling decentralized privacy and trust in P2P networks with message provenance tracking, secure deletion propagation, cryptographic signatures, and steganographic watermarking for leak attribution.

## Features

- **Graph-Based Chain of Custody**: Directed graph model for complex forwarding scenarios with cryptographic signatures
- **Secure Deletion Propagation**: Token-based deletion that propagates through the custody chain
- **Shamir's Secret Sharing**: Split sensitive content into (k,n) threshold shares
- **Time-Lock Encryption**: Content with automatic expiration using AES-256-GCM
- **Steganographic Watermarking**: Invisible watermarks for leak attribution (zero-width Unicode, linguistic fingerprinting, whitespace patterns)
- **Offline Message Queuing**: Peers can go offline and receive queued messages when back online
- **Dual Network Layer**: In-memory simulation for testing + ZeroMQ multi-process for realistic scenarios
- **Extensible Architecture**: Abstract interfaces for storage, peer discovery, notifications, and more

## Project Structure

```
TrustFlow/
├── coc_framework/
│   ├── core/                    # Core domain logic
│   │   ├── coc_node.py          # CoC graph node with signatures
│   │   ├── crypto_core.py       # Ed25519 signing, SHA-256 hashing
│   │   ├── deletion_engine.py   # Deletion token propagation
│   │   ├── network_sim.py       # In-memory Peer/Network simulation
│   │   ├── secret_sharing.py    # Shamir's Secret Sharing
│   │   ├── steganography.py     # Invisible watermarking
│   │   ├── timelock.py          # Time-lock encryption
│   │   └── audit_log.py         # Hash-chained logging
│   ├── interfaces/              # Abstract interfaces + defaults
│   │   ├── storage_backend.py   # StorageBackend + InMemoryStorage
│   │   ├── notification_handler.py
│   │   ├── peer_discovery.py
│   │   └── ...
│   ├── network/                 # ZeroMQ multi-process layer
│   │   ├── coordinator.py       # Process orchestrator
│   │   ├── peer_process.py      # Standalone peer process
│   │   └── protocol.py          # Message serialization
│   └── simulation_engine.py     # In-memory orchestrator
├── scenario_runner.py           # CLI entry point
├── scenario.json                # Sample scenario
├── requirements.txt
└── README.md
```

## Quick Start

### 1. Setup Environment

```bash
# Clone and enter the repository
git clone <repository-url>
cd TrustFlow

# Create virtual environment
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Simulation

```bash
# Run with default scenario
python scenario_runner.py

# Run with custom scenario
python scenario_runner.py path/to/scenario.json

# Run with verbose output
python scenario_runner.py -v

# Run with custom tick delay
python scenario_runner.py --tick-delay 0.5
```

### 3. Create Custom Scenarios

Edit `scenario.json` to define your simulation:

```json
{
  "settings": {
    "total_peers": 5,
    "simulation_duration": 10,
    "enable_secret_sharing": true,
    "enable_timelock": false,
    "enable_steganography": true
  },
  "events": [
    {
      "time": 1,
      "type": "CREATE_MESSAGE",
      "originator_id": "peer_0",
      "recipient_ids": ["peer_1", "peer_2"],
      "content": "Confidential message content"
    },
    {
      "time": 2,
      "type": "FORWARD_MESSAGE",
      "sender_id": "peer_1",
      "recipient_ids": ["peer_3"],
      "parent_message_id": "msg_001"
    }
  ]
}
```

## Event Types

| Event | Description |
|-------|-------------|
| `CREATE_MESSAGE` | Create a root CoC node with content |
| `FORWARD_MESSAGE` | Forward existing content to new recipients |
| `DELETE_MESSAGE` | Initiate deletion propagation |
| `PEER_ONLINE` / `PEER_OFFLINE` | Change peer status |
| `DISTRIBUTE_SHARES` | Split content using Shamir's Secret Sharing |
| `RECONSTRUCT_SECRET` | Reconstruct content from shares |
| `TIMELOCK_CONTENT` | Create time-locked encrypted content |
| `WATERMARK_FORWARD` | Forward with steganographic watermark |
| `DETECT_LEAK` | Analyze content for watermarks |

## Dependencies

- **PyNaCl**: Ed25519 cryptographic signatures
- **cryptography**: AES-256-GCM for timelock encryption
- **pyzmq**: ZeroMQ for multi-process networking

## License

MIT License - see [LICENSE](LICENSE) for details.
