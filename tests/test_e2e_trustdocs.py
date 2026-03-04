"""TrustDocs end-to-end API test.

Tests the full flow: register → login → upload → share → comments → delete → audit
Run with: python tests/test_e2e_trustdocs.py
Requires TrustDocs server running on http://127.0.0.1:8100
"""

import http.client
import http.cookiejar
import json
import os
import sys
import tempfile
import urllib.request


BASE = "127.0.0.1"
PORT = 8100
_cookies = {}


def api(method, path, body=None, cookies=None):
    """Make an API call, handling cookies manually."""
    c = http.client.HTTPConnection(BASE, PORT)
    headers = {}
    if body and not isinstance(body, bytes):
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    elif isinstance(body, bytes):
        pass  # multipart handled separately

    # Add cookie header
    if _cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in _cookies.items())

    c.request(method, path, body, headers)
    r = c.getresponse()

    # Extract Set-Cookie
    for header in r.getheaders():
        if header[0].lower() == "set-cookie":
            parts = header[1].split(";")[0]
            key, val = parts.split("=", 1)
            _cookies[key.strip()] = val.strip()

    data = r.read().decode()
    try:
        data = json.loads(data)
    except Exception:
        pass

    return r.status, data


def multipart_upload(path, filepath, filename):
    """Upload a file via multipart/form-data."""
    boundary = "----TrustDocsTestBoundary"
    with open(filepath, "rb") as f:
        file_content = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()

    c = http.client.HTTPConnection(BASE, PORT)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if _cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in _cookies.items())

    c.request("POST", path, body, headers)
    r = c.getresponse()

    for header in r.getheaders():
        if header[0].lower() == "set-cookie":
            parts = header[1].split(";")[0]
            key, val = parts.split("=", 1)
            _cookies[key.strip()] = val.strip()

    data = json.loads(r.read().decode())
    return r.status, data


def main():
    print("=" * 60)
    print("TrustDocs E2E Test")
    print("=" * 60)

    # 1. Register users
    print("\n=== 1. Register Users ===")
    status, data = api("POST", "/auth/register", {
        "username": "alice", "email": "alice@test.com", "password": "password123"
    })
    assert status == 200, f"Register Alice failed: {status} {data}"
    alice_id = data["id"]
    alice_peer = data["peer_id"]
    print(f"  Alice registered: {alice_id[:8]} peer={alice_peer[:8]}")

    status, data = api("POST", "/auth/register", {
        "username": "bob", "email": "bob@test.com", "password": "password456"
    })
    assert status == 200, f"Register Bob failed: {status} {data}"
    bob_id = data["id"]
    print(f"  Bob registered: {bob_id[:8]}")

    # 2. Login as Alice
    print("\n=== 2. Login ===")
    status, data = api("POST", "/auth/login", {
        "username": "alice", "password": "password123"
    })
    assert status == 200, f"Login failed: {status} {data}"
    print(f"  Alice logged in: {data['user']['username']}")
    assert "session_token" in _cookies, "No session cookie"

    # 3. Check /auth/me
    status, data = api("GET", "/auth/me")
    assert status == 200, f"Me check failed: {status} {data}"
    print(f"  Verified session: user={data['username']}")

    # 4. Upload document
    print("\n=== 3. Upload Document ===")
    tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w")
    tmpfile.write("This is a top-secret TrustDocs test document.\n" * 10)
    tmpfile.close()

    status, data = multipart_upload("/documents", tmpfile.name, "secret_report.txt")
    os.unlink(tmpfile.name)
    assert status == 200, f"Upload failed: {status} {data}"
    doc_id = data["id"]
    print(f"  Uploaded: {data['filename']} ({data['size_bytes']} bytes)")
    print(f"  Content hash: {data['content_hash'][:16]}...")
    print(f"  CoC node: {data['coc_node_hash'][:16]}...")

    # 5. List documents
    print("\n=== 4. List Documents ===")
    status, data = api("GET", "/documents")
    assert status == 200
    print(f"  Owned: {len(data['owned'])} | Shared with me: {len(data['shared_with_me'])}")

    # 6. Share with Bob
    print("\n=== 5. Share with Bob ===")
    status, data = api("POST", f"/documents/{doc_id}/share", {
        "recipient_username": "bob"
    })
    assert status == 200, f"Share failed: {status} {data}"
    print(f"  Shared! Child CoC node: {data['child_coc_node_hash'][:16]}...")

    # 7. Post a comment
    print("\n=== 6. Post Comment ===")
    status, data = api("POST", f"/documents/{doc_id}/comments", {
        "body": "Please review this document."
    })
    assert status == 200, f"Comment failed: {status} {data}"
    print(f"  Comment posted by {data['author_username']}")

    # 8. Read comments
    status, data = api("GET", f"/documents/{doc_id}/comments")
    assert status == 200
    print(f"  Total comments: {len(data)}")

    # 9. Admin: check graph
    print("\n=== 7. Admin Dashboard ===")
    status, data = api("GET", "/admin/graph")
    assert status == 200
    print(f"  CoC nodes: {len(data['nodes'])}, edges: {len(data['edges'])}")

    status, data = api("GET", "/admin/peers")
    assert status == 200
    print(f"  Peers: {len(data)}")

    # 10. Verify audit log
    status, data = api("POST", "/admin/verify-log")
    assert status == 200
    print(f"  Audit: valid={data['valid']}, entries={data['chain_length']}")

    # 11. Delete document
    print("\n=== 8. Delete Document ===")
    status, data = api("DELETE", f"/documents/{doc_id}")
    assert status == 200, f"Delete failed: {status} {data}"
    print(f"  Deleted! Shares revoked: {data['shares_revoked']}")

    # 12. Verify deletion
    status, data = api("GET", f"/documents/{doc_id}")
    assert status == 404, f"Expected 404 after delete, got {status}"
    print(f"  Confirmed: document returns 404 after deletion")

    # 13. Logout
    print("\n=== 9. Logout ===")
    status, data = api("POST", "/auth/logout")
    assert status == 200
    print(f"  Logged out: {data['message']}")

    # Verify session invalidated
    _cookies.clear()
    status, data = api("GET", "/auth/me")
    assert status == 401, f"Expected 401 after logout, got {status}"
    print(f"  Session invalidated: 401 on /auth/me")

    print("\n" + "=" * 60)
    print("ALL E2E TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
