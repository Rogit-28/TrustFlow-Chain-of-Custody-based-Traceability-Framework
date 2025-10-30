import json
import random

def generate_large_scenario(num_peers, num_actions):
    """
    Generates a large, randomized scenario for the CoC simulator.
    """
    settings = {
        "total_peers": num_peers,
        "simulation_duration": num_actions * 2  # Give enough time for all actions
    }

    events = []
    created_messages = [] # List of message_ids
    message_counter = 0

    for i in range(num_actions):
        time = random.randint(1, settings["simulation_duration"] - 1)
        event_type = random.choices(
            ["CREATE_MESSAGE", "FORWARD_MESSAGE", "DELETE_MESSAGE", "PEER_OFFLINE", "PEER_ONLINE"],
            weights=[0.2, 0.5, 0.1, 0.1, 0.1], # Forwarding is the most common action
            k=1
        )[0]

        event = {"time": time}

        # Ensure logical consistency of events
        if event_type == "CREATE_MESSAGE":
            event["type"] = "CREATE_MESSAGE"
            event["originator_idx"] = random.randint(0, num_peers - 1)
            # Send to 1-5 recipients
            num_recipients = min(random.randint(1, 5), num_peers)
            event["recipient_indices"] = random.sample(range(num_peers), k=num_recipients)
            event["content"] = f"Generated secret message content {message_counter}"

            message_id = f"msg_{message_counter}"
            event["message_id"] = message_id
            created_messages.append(message_id)
            message_counter += 1

        elif event_type == "FORWARD_MESSAGE" and created_messages:
            event["type"] = "FORWARD_MESSAGE"
            event["sender_idx"] = random.randint(0, num_peers - 1)
            # Forward to 1-5 recipients
            num_recipients = min(random.randint(1, 5), num_peers)
            event["recipient_indices"] = random.sample(range(num_peers), k=num_recipients)

            parent_message_id = random.choice(created_messages)
            event["parent_message_id"] = parent_message_id

            forwarded_message_id = f"msg_{message_counter}"
            event["forwarded_message_id"] = forwarded_message_id
            created_messages.append(forwarded_message_id)
            message_counter += 1

        elif event_type == "DELETE_MESSAGE" and created_messages:
            event["type"] = "DELETE_MESSAGE"
            event["originator_idx"] = random.randint(0, num_peers - 1)
            event["message_id"] = random.choice(created_messages) # Can delete any message, not just root

        elif event_type == "PEER_OFFLINE":
            event["type"] = "PEER_OFFLINE"
            event["peer_idx"] = random.randint(0, num_peers - 1)

        elif event_type == "PEER_ONLINE":
            event["type"] = "PEER_ONLINE"
            event["peer_idx"] = random.randint(0, num_peers - 1)

        # If a complex event couldn't be created (e.g., no messages to forward yet),
        # default to creating a message instead.
        if len(event) == 1:
            event["type"] = "CREATE_MESSAGE"
            event["originator_idx"] = random.randint(0, num_peers - 1)
            event["recipient_indices"] = [random.randint(0, num_peers - 1)]
            event["content"] = f"Fallback generated message {message_counter}"
            message_id = f"msg_{message_counter}"
            event["message_id"] = message_id
            created_messages.append(message_id)
            message_counter += 1

        events.append(event)

    # Sort events by time
    events.sort(key=lambda x: x["time"])

    scenario = {
        "settings": settings,
        "events": events
    }

    return scenario

if __name__ == "__main__":
    NUM_PEERS = 1000
    NUM_ACTIONS = 5000

    print(f"Generating scenario for {NUM_PEERS} peers and {NUM_ACTIONS} actions...")

    large_scenario = generate_large_scenario(NUM_PEERS, NUM_ACTIONS)

    with open('scenario.json', 'w') as f:
        json.dump(large_scenario, f, indent=2)

    print("Successfully wrote new scenario to scenario.json")
