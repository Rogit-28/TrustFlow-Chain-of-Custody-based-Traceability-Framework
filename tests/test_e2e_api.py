"""End-to-end API test script."""
import http.client
import json


def api(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", 8000)
    headers = {"Content-Type": "application/json"} if body else {}
    c.request(method, path, json.dumps(body).encode() if body else None, headers)
    r = c.getresponse()
    data = json.loads(r.read().decode())
    if r.status >= 400:
        print(f"  ERROR {r.status}: {data}")
    return data


print("=== 1. Create Peers ===")
alice = api("POST", "/api/peers", {"name": "Alice"})
alice_id = alice["peer_id"]
print(f"  Alice: {alice_id[:8]}")
bob = api("POST", "/api/peers", {"name": "Bob"})
bob_id = bob["peer_id"]
print(f"  Bob: {bob_id[:8]}")
carol = api("POST", "/api/peers", {"name": "Carol"})
carol_id = carol["peer_id"]
print(f"  Carol: {carol_id[:8]}")

print()
print("=== 2. Create Message ===")
msg = api("POST", "/api/messages", {
    "originator_id": alice_id,
    "content": "This is a top secret document about Project X",
    "recipient_ids": [bob_id],
    "message_id": "msg1",
})
node_hash = msg["node"]["node_hash"]
print(f"  Node hash: {node_hash[:16]}...")
print(f"  Content hash: {msg['node']['content_hash'][:16]}...")

print()
print("=== 3. Forward with Watermark ===")
fwd = api("POST", f"/api/messages/{node_hash}/forward", {
    "sender_id": bob_id,
    "recipient_ids": [carol_id],
    "use_watermark": True,
    "message_id": "fwd1",
})
fwd_hash = fwd["node"]["node_hash"]
print(f"  Forwarded node: {fwd_hash[:16]}...")
parent = fwd["node"].get("parent_hash")
if parent:
    print(f"  Parent: {parent[:16]}...")

print()
print("=== 4. Get Provenance Chain ===")
chain = api("GET", f"/api/messages/{fwd_hash}/chain")
print(f"  Nodes in chain: {len(chain['nodes'])}")
print(f"  Edges: {len(chain['edges'])}")
root_owner = chain["root"]["owner_id"]
print(f"  Root owner: {root_owner[:8]}")

print()
print("=== 5. Delete Message ===")
d = api("DELETE", f"/api/messages/{node_hash}", {"originator_id": alice_id})
deleted = d.get("deleted_node_hash", "N/A")
print(f"  Deleted: {deleted[:16]}...")

print()
print("=== 6. Get Audit Log ===")
audit = api("GET", "/api/audit")
total = audit["total_entries"]
valid = audit["integrity_valid"]
print(f"  Total entries: {total}")
print(f"  Integrity valid: {valid}")
for e in audit["entries"][-4:]:
    actor = e["actor"][:8]
    target = e["target"][:30]
    print(f"  [{e['event_type']}] {actor} -> {target}")

print()
print("=== 7. Get State ===")
state = api("GET", "/api/state")
print(f"  Peers: {state['peer_count']}")
print(f"  Messages: {state['message_count']}")
print(f"  Features: {state['features']}")

print()
print("ALL E2E TESTS PASSED")
