# API Reference

This document provides a complete reference for the classes and methods in the Chain of Custody (CoC) Privacy Framework Simulator.

## `coc_framework.core`

### `CoCNode`

Represents a single message in the chain of custody.

*   `__init__(self, content_hash: str, sender: Peer, receivers: List[Peer], parent_hash: Optional[str] = None, depth: int = 0)`
*   `add_child(self, child_node: 'CoCNode')`
*   `get_all_descendants(self) -> List['CoCNode']`

### `CoCEngine`

Manages the graph of `CoCNode` objects.

*   `__init__(self)`
*   `create_root_node(self, content_hash: str, sender: Peer, receivers: List[Peer]) -> CoCNode`
*   `add_forward_node(self, parent_node: CoCNode, content_hash: str, sender: Peer, receivers: List[Peer]) -> CoCNode`
*   `get_node_by_hash(self, node_hash: str) -> Optional[CoCNode]`
*   `verify_node_integrity(self, node: CoCNode, sender_verify_key) -> bool`

### `Peer`

Represents a participant in the network.

*   `__init__(self, coc_engine, deletion_engine, message_ttl_hours: int = 24, storage_backend: StorageBackend = None, transfer_monitor: TransferMonitor = None, notification_handler: NotificationHandler = None)`
*   `go_offline(self)`
*   `go_online(self)`
*   `send_message(self, network, recipient_id, content_type, content_data)`
*   `receive_message(self, message)`

### `Network`

Simulates the network and routes messages between peers.

*   `__init__(self, peer_discovery: PeerDiscovery = None)`
*   `add_peer(self, peer: Peer)`
*   `route_message(self, message)`

## `coc_framework.simulation_engine`

### `SimulationEngine`

The main orchestrator of the simulation.

*   `__init__(self, scenario)`
*   `setup(self)`
*   `tick(self)`
*   `handle_event(self, event)`

## `coc_framework.interfaces`

This module contains the abstract base classes for the extensible components of the framework. Refer to the `DEVELOPER_GUIDE.md` for more information on how to use these interfaces.
