# Known Issues

## Race Condition in Asynchronous Message Deletion

**Issue:** The `test_full_lifecycle` and `test_loop_safe_deletion_propagation` tests are failing intermittently due to a race condition between message propagation and deletion propagation.

**Description:** The simulation is asynchronous, meaning that message and deletion token deliveries are scheduled with small, random delays. A race condition occurs when a deletion token for a message arrives at a peer *before* the message itself has arrived.

**Step-by-Step Example:**

1.  **Tick 1:** Peer A creates a message and sends it to Peer B. The network schedules this delivery to happen in, for example, 50 milliseconds.
2.  **Tick 2:** Peer B receives the message and immediately forwards it to Peer C. The network schedules this second delivery to happen in, say, 60 milliseconds.
3.  **Tick 3:** Peer A initiates a deletion for the original message and sends a deletion token to Peer B. The network schedules this token to be delivered in just 10 milliseconds.

**The Race:**

4.  Peer B receives the **deletion token** first (after 10ms). It deletes the message from its storage and forwards the deletion token to Peer C.
5.  Peer C receives the **deletion token**, but the original forwarded message from Peer B is still in transit.
6.  Because Peer C doesn't have the message the token refers to, it discards the deletion token.
7.  A few milliseconds later, the forwarded message finally arrives at Peer C. The instruction to delete it has already been discarded, so the message is stored permanently.

**Impact:** This results in test failures where nodes that should have been deleted remain in a peer's storage. This affects `test_full_lifecycle` and is the likely cause of the failure in `test_loop_safe_deletion_propagation` as well.
