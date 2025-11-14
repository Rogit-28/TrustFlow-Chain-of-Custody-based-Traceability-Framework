# Chain of Custody (CoC) Privacy Framework Simulator: A Deep Dive

This document provides a comprehensive overview of the CoC Privacy Framework Simulator, designed for a technical interview presentation. It covers the project's purpose, architecture, core components, and data flow.

## 1. The "What": High-Level Overview

The Chain of Custody (CoC) Privacy Framework Simulator is a Python-based, command-line tool designed to model and validate a decentralized privacy and trust system.

**The Problem:** In many digital communication systems, it's difficult to track who has a copy of a piece of content, and even more difficult to ensure that when a user deletes content, all copies are verifiably removed. This project tackles that problem by simulating a network where content provenance is tracked, and deletions can be securely propagated.

**The Solution:** The project simulates a peer-to-peer network where every piece of content has a "Chain of Custody," a cryptographically signed, graph-based record of who has received it. This allows the system to not only track the content's journey but also to issue and enforce "deletion tokens" that travel down the chain.

### Key Components:

*   **Simulation Engine:** The heart of the simulator. It's a "tick-based" engine that reads a `scenario.json` file and processes events one step at a time, calculating the new state of the network after each tick.
*   **Peers:** These are the anonymous clients in the simulated network. Each peer can create content, receive content, forward it to others, and go online or offline.
*   **CoC Nodes (Chain of Custody Nodes):** This is the core data structure. Each `CoCNode` represents a link in the chain of custody. It contains a hash of the content, the owner's ID, the recipients' IDs, and a cryptographic signature to ensure its integrity. These nodes form a directed graph, where a parent node points to the children created when a message is forwarded.
*   **Deletion Engine:** This component is responsible for handling the secure deletion of content. It allows a peer to issue a `DeletionToken` for content they own. This token is then propagated to other peers, who process it to delete the content from their local storage.
*   **Audit Log:** An immutable, chained-hash log that records every significant event in the simulation (e.g., creating a peer, sending a message, issuing a deletion token). This provides a verifiable record of the simulation's history.
*   **Watermark Engine:** An optional component that can embed a signed watermark into content. This allows for leak attribution by identifying which peer was responsible for a piece of content leaving the trusted network.

## 2. The "How": Core Logic and Data Flow

This section explains the technical implementation of the simulator's core features.

### A. Cryptographic Integrity

The trust in the system is built on a foundation of public-key cryptography, handled by the `CryptoCore` class.

1.  **Key Generation:** When a `Peer` is created, it generates an Ed25519 keypair: a `SigningKey` (private) and a `VerifyKey` (public). The public key is used as the peer's identifier.
2.  **Signing:** Every `CoCNode` is cryptographically signed by its owner. The signature is created over a string containing the content hash, parent hash, owner ID, and recipient IDs. This ensures that a node cannot be tampered with without invalidating the signature.
3.  **Verification:** When a peer receives a `CoCNode`, it can use the sender's public `VerifyKey` to verify the signature. This confirms that the node was created by the claimed owner and hasn't been altered.

### B. Data Flow: Creating and Sending a Message

Here is the step-by-step flow for creating a new piece of content:

1.  **Content Hashing:** The originator `Peer` takes the raw content (e.g., a text message) and creates a SHA-256 hash of it. This hash, not the content itself, is what's stored in the `CoCNode`.
2.  **Root CoC Node Creation:** The peer creates a "root" `CoCNode`. This node has no parent and contains the content hash, the peer's own ID as the owner, and a list of recipient IDs.
3.  **Signing the Node:** The peer signs the `CoCNode` with its private `SigningKey`.
4.  **Storage:** The peer stores the new `CoCNode` and the original content in its local storage (by default, an in-memory dictionary).
5.  **Transmission:** The peer sends a message to each recipient. The message contains the serialized `CoCNode` and the original content.

### C. Data Flow: Forwarding a Message

When a recipient decides to forward a message:

1.  **Child CoC Node Creation:** The forwarding peer creates a new `CoCNode`. This "child" node references the hash of the original ("parent") node.
2.  **Content Reuse:** The child node contains the *same content hash* as the parent. The content itself is not duplicated, only the record of its transmission.
3.  **Signing and Transmission:** The forwarding peer signs the *new* child node with its *own* private key and sends it to the new recipients.

This process creates the graph-like Chain of Custody. By traversing the graph from a child node up to the root, you can reconstruct the entire forwarding history of a piece of content.

### D. Data Flow: Deleting a Message

The deletion process is designed to be secure and decentralized:

1.  **Token Issuance:** The original owner of a `CoCNode` initiates a deletion by creating a `DeletionToken`. This token contains the hash of the node to be deleted and is signed by the owner.
2.  **Propagation:** The owner sends this token to all direct recipients of the node.
3.  **Token Processing:** When a `Peer` receives a `DeletionToken`, it first verifies the token's signature using the originator's public key.
4.  **Deletion and Recursion:** If the signature is valid, the peer deletes the corresponding `CoCNode` and its associated content from local storage. Crucially, if the peer has forwarded this content and created its *own* child nodes, it will then issue its *own* `DeletionToken`s for those children, propagating the deletion down the chain.

### E. Watermarking

The `WatermarkEngine` provides an optional layer of traceability:

1.  **Embedding:** When a peer sends a message, it can embed a watermark. This watermark contains metadata (like the peer's ID and a timestamp) and a signature (an HMAC-SHA256 hash) created using a shared secret key.
2.  **Extraction and Verification:** If a watermarked piece of content is found "in the wild," the `WatermarkEngine` can extract the metadata and verify the signature. If the signature is valid, it proves which peer was the last one to handle the content before it was leaked.

## 3. The "When": The Simulation Lifecycle

The simulator is not a real-time system but an **event-driven, tick-based simulation**. The entire lifecycle is orchestrated by the `SimulationEngine` and defined by the `scenario.json` file.

### A. The `scenario.json` File

This file is the script for the simulation. It defines:

*   **Peers:** The initial set of peers in the network.
*   **Events:** A list of all actions that will occur during the simulation. Each event has a `time` property, which corresponds to a "tick."
*   **Settings:** Global settings for the simulation, such as the total number of peers and a secret key for watermarking.

### B. The Tick-Based Engine

The `SimulationEngine` processes the simulation in discrete steps called "ticks."

1.  **Initialization:** The engine starts at `tick_count = 0`. It loads all events from `scenario.json` and sorts them by their "time."
2.  **Advancing the Simulation:** When the engine's `tick()` method is called, it advances the simulation by one step:
    *   It identifies all events scheduled for the current `tick_count`.
    *   It executes these events in order (e.g., `CREATE_MESSAGE`, `PEER_OFFLINE`).
    *   It then waits for a short period to allow any asynchronous operations (like message delivery) to complete.
    *   Finally, it increments `tick_count`.

This deterministic, turn-based approach allows for the modeling of complex, asynchronous-like behavior in a controlled and repeatable way.

### C. Example Scenario Flow

Here's how a typical scenario might unfold:

*   **Tick 0:** A `CREATE_MESSAGE` event is triggered. Peer A creates a root `CoCNode` and sends it to Peer B.
*   **Tick 1:** No events are scheduled. The network is quiet.
*   **Tick 2:** A `PEER_OFFLINE` event is triggered. Peer C goes offline.
*   **Tick 3:** A `FORWARD_MESSAGE` event occurs. Peer B attempts to forward the message from Tick 0 to Peer C. Because Peer C is offline, the message is placed in Peer C's offline queue.
*   **Tick 4:** A `PEER_ONLINE` event occurs. Peer C comes back online and immediately processes its message queue, finally receiving the message from Peer B.

## 4. Dependencies and Local Setup

The project is built with standard Python and has a minimal set of external dependencies.

### A. Core Dependencies (`requirements.txt`)

*   **PyNaCl:** A Python binding to the `libsodium` library, used for all cryptographic operations (key generation, signing, and verification).
*   **aiohttp:** An asynchronous HTTP client/server framework, used for the web-based frontend and WebSocket communication.
*   **aiohttp-jinja2 / Jinja2:** Used for templating the HTML for the frontend.

### B. Local Setup

Setting up and running the simulator is straightforward.

**1. Command-Line Simulation:**

This runs the simulation from start to finish based on `scenario.json` and prints the final state of the audit log.

```bash
# 1. Set up a virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the simulation
python scenario_runner.py
```

**2. Interactive Web Frontend:**

This launches a web server that provides a real-time, interactive visualization of the network graph.

```bash
# (Assuming you have already installed dependencies)

# 1. Start the web server
python main.py

# 2. Open your browser and navigate to:
# http://127.0.0.1:8080
```

From the web interface, you can step through the simulation tick by tick, observe which peers are online, and see the Chain of Custody graph evolve.

## 5. Future Scope and Potential Improvements

The simulator is architected with a set of abstract interfaces, making it highly extensible. Here are several ways the project could be taken further:

*   **Pluggable Storage Backends:** The current `InMemoryStorage` is simple, but the `StorageBackend` interface allows for the creation of more persistent or performant storage solutions, such as a database-backed storage engine (e.g., SQLite or PostgreSQL).
*   **Advanced Network Modeling:** The current network model is a simple hub-and-spoke system. The architecture could be extended to simulate more realistic network conditions, such as latency, packet loss, or different network topologies (e.g., a true mesh network).
*   **Alternative Cryptographic Algorithms:** The `CryptoCore` class abstracts the cryptographic operations. This could be extended to support different signing algorithms, such as those that are quantum-resistant, to "future-proof" the system.
*   **Dynamic Scenario Generation:** The `generate_scenario.py` script provides a starting point for creating scenarios. This could be expanded into a more powerful tool for generating complex, realistic scenarios with thousands of events to better stress-test the system's scalability and performance.
*   **Enhanced Frontend Controls:** The web frontend currently supports stepping through and resetting the simulation. It could be enhanced with more powerful features, such as the ability to pause, rewind, or even inject new events into a running simulation.
