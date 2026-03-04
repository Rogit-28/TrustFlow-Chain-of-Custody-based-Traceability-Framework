import os
import random
import string
import requests
import subprocess

BASE_URL = "http://127.0.0.1:8100"

def random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_file_content(filename):
    return f"This is highly confidential data for {filename}.\n" + random_string(500)

def fetch_existing_users():
    """Fetch all agent_* users from the pg primary container to reuse their keys."""
    print("Fetching existing users from DB...")
    cmd = ['docker', 'exec', 'trustdocs-pg-primary', 'psql', '-U', 'trustdocs', '-d', 'trustdocs', '-t', '-c', "SELECT username FROM users WHERE username LIKE 'agent_%';"]
    try:
        output = subprocess.check_output(cmd).decode('utf-8')
        users = [line.strip() for line in output.split('\n') if line.strip()]
        return users
    except Exception as e:
        print(f"Failed to fetch users: {e}")
        return []

def main():
    print(f"Starting Robust Topology Generator against {BASE_URL}...")
    users = fetch_existing_users()
    
    if not users:
        print("No users found. Ensure the agents exist.")
        return
        
    print(f"Loaded {len(users)} existing peers.")
    sessions = {}

    # 1. Login to all users to harvest sessions
    print("Authenticating peers...")
    for username in users:
        session = requests.Session()
        res = session.post(f"{BASE_URL}/auth/login", json={"username": username, "password": "Password123!"})
        if res.status_code == 200:
            sessions[username] = session
        else:
            print(f"[WARN] Failed to auth {username}")
            
    active_users = list(sessions.keys())
    if len(active_users) < 20:
        print("Not enough active sessions to build topologies.")
        return

    # 2. Originator Uploads
    originators = random.sample(active_users, 15)
    docs = []
    
    print("\n--- Generating Base Documents ---")
    for origin in originators:
        session = sessions[origin]
        # Upload 1-2 docs per originator
        for _ in range(random.randint(1, 2)):
            filename = f"Project_Onyx_Brief_{random_string(4)}.txt"
            content = generate_file_content(filename)
            res = session.post(f"{BASE_URL}/documents", files={'file': (filename, content, 'text/plain')})
            if res.status_code == 200:
                doc = res.json()
                docs.append((origin, doc['id']))
                print(f"[ORIGIN] {origin} uploaded {filename}")

    # 3. Robust Share Behaviors
    print("\n--- Initiating Topography Generation ---")
    
    # Behavior A: The Deep Cascading Chain (Depth 3 to 5)
    for _ in range(5): # Create 5 separate deep chains
        root_user, doc_id = random.choice(docs)
        current_sender = root_user
        depth = random.randint(3, 5)
        visited = {current_sender}
        
        print(f"\n[START CASCADE] Depth: {depth} for Doc: {doc_id[:8]}")
        for hop in range(depth):
            candidates = [u for u in active_users if u not in visited]
            if not candidates:
                break
            target = random.choice(candidates)
            
            sess = sessions[current_sender]
            res = sess.post(f"{BASE_URL}/documents/{doc_id}/share", json={"recipient_username": target})
            if res.status_code == 200:
                print(f"  [HOP {hop+1}] {current_sender} -> {target}")
                visited.add(target)
                current_sender = target # Recevier is now the sender!
            else:
                print(f"  [HOP FAIL] {current_sender} -> {target}")
                break

    # Behavior B: Spoke & Wheel Deployment
    print("\n[START SPOKE & WHEEL]")
    hub_origin = random.choice(active_users)
    filename = f"Global_Directive_{random_string(4)}.txt"
    doc_res = sessions[hub_origin].post(f"{BASE_URL}/documents", files={'file': (filename, generate_file_content(filename), 'text/plain')})
    if doc_res.status_code == 200:
        hub_doc_id = doc_res.json()['id']
        lieutenants = random.sample([u for u in active_users if u != hub_origin], 5)
        
        for lt in lieutenants:
            res = sessions[hub_origin].post(f"{BASE_URL}/documents/{hub_doc_id}/share", json={"recipient_username": lt})
            if res.status_code == 200:
                print(f"  [L1] {hub_origin} -> {lt}")
                
                # Lieutenant shares to 3 Officers
                officers = random.sample([u for u in active_users if u not in [lt, hub_origin]], 3)
                for off in officers:
                    res2 = sessions[lt].post(f"{BASE_URL}/documents/{hub_doc_id}/share", json={"recipient_username": off})
                    if res2.status_code == 200:
                        print(f"    [L2] {lt} -> {off}")
                        
                        # Officer shares to 2 Agents
                        agents = random.sample([u for u in active_users if u not in [off, lt, hub_origin]], 2)
                        for ag in agents:
                            sessions[off].post(f"{BASE_URL}/documents/{hub_doc_id}/share", json={"recipient_username": ag})
                            print(f"      [L3] {off} -> {ag}")

    # Behavior C: Mesh sync to 'root'
    print("\n--- Mesh Syncing with root ---")
    for _ in range(8):
        root_user, doc_id = random.choice(docs)
        sess = sessions[root_user]
        res = sess.post(f"{BASE_URL}/documents/{doc_id}/share", json={"recipient_username": "root"})

    print("\n[SUCCESS] Robust deep-chain synthetic graph built!")

if __name__ == '__main__':
    main()
