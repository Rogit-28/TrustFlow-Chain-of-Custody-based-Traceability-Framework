# CoC Framework Context Document - V1

## 1. Project Overview

This project is a **Chain of Custody (CoC) Privacy Framework Simulator**, written in Python. Its primary purpose is to simulate the lifecycle of messages within a network of peers, focusing on tracking the chain of custody, handling deletions, and ensuring data privacy and integrity.

**Key Concepts:**

*   **Chain of Custody (CoC):** A chronological record showing the seizure, custody, control, transfer, analysis, and disposition of physical or electronic evidence. In this framework, it's represented as a graph of message transfers.
*   **Peers:** Anonymous entities in the network that can create, send, receive, and forward messages. They are identified by a UUID and a cryptographic keypair.
*   **Simulation Engine:** The core component that orchestrates the simulation by processing a series of events defined in a JSON scenario file.
*   **Graph-Based Structure:** The CoC is modeled as a directed acyclic graph (DAG), where nodes represent messages and edges represent forwarding actions. `CoCNode` objects track parent-child relationships, allowing for efficient traversal.
*   **Extensibility:** The framework is designed to be highly extensible through a set of abstract interfaces for key components like storage, peer discovery, and notification handling.

## 2. Project Structure

```
.
├── coc_framework/
│   ├── core/
│   │   ├── audit_log.py
│   │   ├── coc_engine.py
│   │   ├── crypto_core.py
│   │   ├── deletion_engine.py
│   │   ├── network_sim.py
│   │   └── watermark_engine.py
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── encryption_policy.py
│   │   ├── notification_handler.py
│   │   ├── peer_discovery.py
│   │   └── storage_backend.py
│   └── simulation_engine.py
├── tests/
│   ├── test_deletion_engine.py
│   ├── test_integration.py
│   ├── test_offline_queue.py
│   ├── test_signature_verification.py
│   ├── test_tree_structure.py
│   └── test_watermark_integration.py
├── .gitignore
├── KNOWN_ISSUES.md
├── LICENSE
├── PRD
├── README.md
├── generate_scenario.py
├── requirements.txt
├── scenario.json
└── scenario_runner.py
```

## 3. Core Components Breakdown

### `coc_framework/`

This is the main package containing the core logic of the framework.

#### `coc_framework/core/`

This module contains the fundamental building blocks of the CoC simulation.

*   **`coc_engine.py`:**
    *   **`CoCNode`:** Represents a single message in the chain of custody. It contains metadata such as the message hash, parent hash, sender/receiver IDs, timestamp, and signature. It also tracks its `depth` in the graph and its `children` nodes. **It does not store the message content itself.**
    *   **`CoCEngine`:** Manages the graph of `CoCNode` objects. It's responsible for creating root nodes and adding forward nodes to the graph.

*   **`network_sim.py`:**
    *   **`Peer`:** Represents a participant in the network. Each peer has a unique ID, a cryptographic keypair, and an online/offline status. It uses a `StorageBackend` to store message content and an `offline_queue` to hold messages received while offline.
    *   **`Network`:** Simulates the network itself, responsible for routing messages between peers. It uses a `PeerDiscovery` interface to find and manage peers.

*   **`crypto_core.py`:**
    *   **`CryptoCore`:** A utility class that provides static methods for cryptographic operations, including key generation, content hashing, and signing/verifying messages using `PyNaCl`.

*   **`deletion_engine.py`:**
    *   **`DeletionToken` & `DeletionReceipt`:** Dataclasses representing the tokens and receipts used in the deletion process.
    *   **`DeletionEngine`:** Manages the creation and propagation of deletion tokens. When a peer receives a token, this engine processes it and removes the corresponding message from the peer's storage.

*   **`watermark_engine.py`:**
    *   **`WatermarkEngine`:** Provides functionality to embed and verify watermarks in message content. This is used for leak attribution and tracking message provenance.

*   **`audit_log.py`:**
    *   **`AuditLog`:** A simple logger for recording all significant events that occur during the simulation.

#### `coc_framework/interfaces/`

This module defines the abstract interfaces that make the framework extensible.

*   **`storage_backend.py`:** Defines the `StorageBackend` ABC for message storage and provides a default `InMemoryStorage` implementation.
*   **`peer_discovery.py`:** Defines the `PeerDiscovery` ABC for managing and finding peers and provides a default `RegistryPeerDiscovery` implementation.
*   **`notification_handler.py`:** Defines the `NotificationHandler` ABC for dispatching notifications about simulation events and provides a `SilentNotificationHandler` that prints to the console.
*   **`encryption_policy.py`:** Defines the `EncryptionPolicy` ABC for handling message encryption during transfers and provides a `NoEncryption` default.
*   **`transfer_monitor.py`:** Defines the `TransferMonitor` ABC for monitoring message access and transfers and provides a `NullTransferMonitor` that takes no action.

#### `simulation_engine.py`

*   **`SimulationEngine`:** The main orchestrator of the simulation. It reads a scenario file, sets up the network and peers, and processes events in a tick-based loop. It handles events such as `CREATE_MESSAGE`, `FORWARD_MESSAGE`, `DELETE_MESSAGE`, `PEER_ONLINE`, and `PEER_OFFLINE`.

### `tests/`

This directory contains all the unit and integration tests for the framework.

*   `test_tree_structure.py`: Tests the parent-child relationships and graph traversal logic in `CoCNode`.
*   `test_offline_queue.py`: Tests the offline message queuing and delivery functionality.
*   `test_signature_verification.py`: Tests the cryptographic signature validation for deletion tokens and `CoCNode`s.
*   `test_watermark_integration.py`: Tests the watermark embedding and verification process.
*   `test_integration.py`: Contains end-to-end tests for full message lifecycles.
*   `test_deletion_engine.py`: Contains tests for the deletion logic, including the known failing test for cyclic graphs.

## 4. How It Works

1.  **Initialization:** A `SimulationEngine` is created with a `scenario.json` file. The `setup` method creates the specified number of peers and adds them to the network.
2.  **Event Loop:** The `tick` method advances the simulation one step at a time, processing any events scheduled for the current tick.
3.  **Message Creation:** When a `CREATE_MESSAGE` event is handled, the `SimulationEngine` hashes the content, creates a root `CoCNode` via the `CoCEngine`, and saves the (potentially watermarked) content to the recipients' `StorageBackend`.
4.  **Message Forwarding:** A `FORWARD_MESSAGE` event causes the `SimulationEngine` to retrieve the original content from the sender's storage, create a new `CoCNode` linked to the parent, and save the (newly watermarked) content to the new recipients' storage.
5.  **Offline Handling:** If a recipient is offline, the message is added to its `offline_queue`. When the peer comes online, it processes this queue, handling messages as if they were just received.
6.  **Deletion:** A `DELETE_MESSAGE` event triggers the `DeletionEngine` to issue a `DeletionToken`. The `SimulationEngine` then uses the graph structure (`get_all_descendants`) to find all peers who have handled the message and sends them the token.

## 5. Assumptions

*   **Text-Based Simulation:** The framework currently simulates text-based messages.
*   **Simplified Network:** The `Network` class provides a simplified, synchronous message routing model.
*   **In-Memory Defaults:** The default implementations for the interfaces (`InMemoryStorage`, `RegistryPeerDiscovery`, etc.) are all in-memory and will not persist data.
*   **Known Issue:** There is a known issue with deletion propagation in cyclic graphs, which is documented in `KNOWN_ISSUES.md`.

## 6. How to Use

To run a simulation, you can use the `scenario_runner.py` script (not fully implemented in this version, but the `SimulationEngine` can be used directly). The `scenario.json` file defines the parameters and events of the simulation.

This document provides a comprehensive starting point for understanding the CoC framework. For more specific details, refer to the source code and the docstrings within each file.
