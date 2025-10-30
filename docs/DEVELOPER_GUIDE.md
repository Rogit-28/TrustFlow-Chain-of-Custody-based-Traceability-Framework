# Developer Guide

This guide provides a deep dive into the internal workings of the Chain of Custody (CoC) Privacy Framework Simulator and offers best practices for extending its functionality.

## Core Architecture

The framework is built around a few key components:

*   **`SimulationEngine`:** The central orchestrator that manages the simulation's state and processes events from a `scenario.json` file.
*   **`CoCEngine`:** Manages the graph of `CoCNode` objects, which represents the chain of custody.
*   **`Peer`:** Represents a participant in the network.
*   **`Network`:** Simulates the network and routes messages between peers.
*   **Interfaces:** A set of abstract base classes in the `coc_framework/interfaces/` directory that define the contracts for extensible components.

## Extending the Framework

The framework is designed to be extended through its abstract interfaces. To create a custom component, you can inherit from one of the following base classes and implement the required methods:

*   **`StorageBackend`:** Implement a custom storage solution, such as a database or an encrypted file system.
*   **`PeerDiscovery`:** Implement a custom peer discovery mechanism, such as a DHT or a DNS-based service.
*   **`NotificationHandler`:** Implement a custom notification handler to send alerts to a UI or an external service.
*   **`EncryptionPolicy`:** Implement a custom encryption policy to define how messages are encrypted for transfer.
*   **`TransferMonitor`:** Implement a custom transfer monitor to track and control message access and transfers.

### Example: Custom Storage Backend

To create a custom storage backend, you would create a new class that inherits from `StorageBackend` and implement the abstract methods:

```python
from coc_framework.interfaces.storage_backend import StorageBackend

class MyCustomStorage(StorageBackend):
    def save_message(self, msg_hash: str, content: str, metadata: dict) -> None:
        # Implement your custom save logic here
        pass

    def get_message(self, msg_hash: str) -> Optional[str]:
        # Implement your custom get logic here
        pass

    # ... and so on for the other abstract methods
```

You can then inject an instance of your custom storage class into the `Peer` objects when you create them in the `SimulationEngine`.

## Best Practices

*   **Use the Interfaces:** When extending the framework, always try to use the provided interfaces to ensure that your custom components are compatible with the rest of the system.
*   **Write Tests:** When you add new features, be sure to add corresponding unit and integration tests to ensure that they work correctly and don't introduce regressions.
*   **Keep it Modular:** Try to keep your custom components as modular as possible to make them easier to test and maintain.
*   **Refer to the Context Document:** The `CONTEXT_V1.md` file provides a detailed overview of the codebase and can be a useful reference when you're working on new features.
