# Changelog

## [2.0.0] - 2025-10-28

### Added

*   **Graph-Based CoC:** The Chain of Custody is now modeled as a directed graph, allowing for complex forwarding scenarios and efficient traversal.
*   **Offline Message Queuing:** Peers can now go offline and receive messages in a queue, which are then processed when they come back online.
*   **Watermarking:** Messages can now be watermarked with sender metadata for leak attribution.
*   **Extensible Interfaces:** The framework is now designed with a set of abstract interfaces for key components, allowing for custom implementations of storage, peer discovery, and more.
*   **Cryptographic Integrity:** All CoC nodes and deletion tokens are now cryptographically signed to ensure their integrity.
*   **Comprehensive Tests:** Added a wide range of unit, integration, and performance tests.
*   **Documentation:** Added a `docs` directory with a `DEVELOPER_GUIDE.md`, `API_REFERENCE.md`, and `SCENARIO_GUIDE.md`.

### Changed

*   **`CoCNode`:** The `CoCNode` class now tracks parent-child relationships, including depth and a list of children. It no longer stores the message content itself, only a hash of the content.
*   **`SimulationEngine`:** The `SimulationEngine` has been updated to support the new graph-based architecture, offline message queuing, and watermarking.
*   **`README.md`:** The main `README.md` has been updated to reflect the new features and architectural changes.

### Removed

*   **Legacy Tree-Specific Code:** Removed all legacy code related to the old tree-based architecture.

### Known Issues

*   **Deletion Propagation Race Condition:** There is a known race condition where a deletion token can arrive at a peer before the message it is intended to delete. This causes the deletion to fail for that peer. This is documented in `KNOWN_ISSUES.md`.
