import asyncio
import json
from coc_framework.core.network_sim import Network, Peer
from coc_framework.core.deletion_engine import DeletionEngine
from coc_framework.core.audit_log import AuditLog
from coc_framework.interfaces.notification_handler import SilentNotificationHandler

class SimulationEngine:
    def __init__(self, scenario):
        self.scenario = scenario
        self.network = Network()
        self.audit_log = AuditLog()

        # Initialize engines and components
        self.notification_handler = SilentNotificationHandler()
        self.deletion_engine = DeletionEngine(self.network, self.audit_log, self.notification_handler, self.network.peer_discovery)

        self.peers = {}  # Store peers by peer_id
        self.tick_count = 0

        # Load events and sort by time
        self.events = sorted(self.scenario.get("events", []), key=lambda x: x["time"])

        # Initialize the simulation
        self._setup_simulation()

    def _setup_simulation(self):
        """Sets up the simulation based on the scenario file."""
        if "peers" in self.scenario:
            peer_setups = self.scenario.get("peers", [])
            for peer_config in peer_setups:
                peer_id = peer_config["id"]
                peer = Peer(peer_id=peer_id, deletion_engine=self.deletion_engine)
                self.peers[peer_id] = peer
                self.network.add_peer(peer)
        elif "settings" in self.scenario and "total_peers" in self.scenario["settings"]:
            total_peers = self.scenario["settings"]["total_peers"]
            for i in range(total_peers):
                peer_id = f"peer_{i}"
                peer = Peer(peer_id=peer_id, deletion_engine=self.deletion_engine)
                self.peers[peer_id] = peer
                self.network.add_peer(peer)

        print(f"[ENGINE] Setup complete with {len(self.peers)} peers.")

    async def tick(self):
        """Advances the simulation by one time step."""
        print(f"--- Tick {self.tick_count} ---")
        events_for_this_tick = [e for e in self.events if e["time"] == self.tick_count]
        for event in events_for_this_tick:
            try:
                self._handle_event(event)
            except Exception as e:
                print(f"Error handling event {event}: {e}")

        # A crucial delay to allow asynchronous network operations to complete
        await asyncio.sleep(2)

        self.tick_count += 1


    def _handle_event(self, event):
        """Handles a single event from the scenario."""
        event_type = event.get("type")

        if event_type == "PEER_ONLINE":
            peer = self.peers.get(event["peer_id"])
            if peer:
                peer.go_online()
                print(f"[TICK {self.tick_count}] Peer {peer.peer_id[:8]} goes online.")

        elif event_type == "PEER_OFFLINE":
            peer = self.peers.get(event["peer_id"])
            if peer:
                peer.go_offline()
                print(f"[TICK {self.tick_count}] Peer {peer.peer_id[:8]} goes offline.")

        elif event_type == "CREATE_MESSAGE":
            originator = self.peers.get(event["originator_id"])
            if not originator:
                return

            # Create the content and the root CoC node
            node = originator.create_coc_root(
                content=event["content"],
                recipient_ids=event["recipient_ids"]
            )

            # Send the message to recipients
            for recipient_id in event["recipient_ids"]:
                originator.send_message(
                    recipient_id=recipient_id,
                    message_type="coc_data",
                    content={
                        "node_data": node.to_dict(),
                        "content": event["content"]
                    }
                )
            print(f"[TICK {self.tick_count}] Peer {originator.peer_id[:8]} creates message.")

        elif event_type == "FORWARD_MESSAGE":
            sender = self.peers.get(event["sender_id"])
            if not sender:
                return

            # Find the original node to create a child from
            parent_node = sender.storage.get_node(event["parent_node_hash"])
            if not parent_node:
                print(f"Error: parent node {event['parent_node_hash']} not found in {sender.peer_id}'s storage")
                return

            # Create the forwarded CoC node
            child_node = sender.forward_coc_message(
                parent_node=parent_node,
                recipient_ids=event["recipient_ids"]
            )

            # Send the forwarded message
            for recipient_id in event["recipient_ids"]:
                sender.send_message(
                    recipient_id=recipient_id,
                    message_type="coc_data",
                    content={
                        "node_data": child_node.to_dict(),
                        "content": child_node.content_hash
                    }
                )
            print(f"[TICK {self.tick_count}] Peer {sender.peer_id[:8]} forwards message.")

        elif event_type == "DELETE_MESSAGE":
            originator = self.peers.get(event["originator_id"])
            node_to_delete = originator.storage.get_node(event["node_hash"])

            if originator and node_to_delete:
                originator.initiate_deletion(node_to_delete)
                print(f"[TICK {self.tick_count}] Peer {originator.peer_id[:8]} initiates deletion.")

    def get_simulation_state(self):
        """Returns the current state of the simulation for serialization."""
        return {
            "tick": self.tick_count,
            "peers": self.peers,
        }
