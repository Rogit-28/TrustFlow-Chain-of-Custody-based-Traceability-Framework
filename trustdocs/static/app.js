/**
 * TrustDocs Frontend Application
 * Vanilla JS — No build step, no framework dependencies.
 */

// ── State ───────────────────────────────────────────────────────────────────
let currentUser = null;
let chatWs = null;
let currentDocId = null;

// ── API Helper ──────────────────────────────────────────────────────────────

async function api(method, path, body = null) {
    const opts = {
        method,
        headers: {},
        credentials: 'include',
    };
    if (body && !(body instanceof FormData)) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    } else if (body instanceof FormData) {
        opts.body = body;
    }

    const res = await fetch(path, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || err.message || res.statusText);
    }
    return res.json();
}

// ── Toast ───────────────────────────────────────────────────────────────────

function toast(message, type = '') {
    const el = document.getElementById('toast');
    el.textContent = message;
    el.className = 'toast show ' + type;
    setTimeout(() => el.className = 'toast', 3000);
}

// ── View Management ─────────────────────────────────────────────────────────

function showView(view) {
    document.getElementById('auth-view').style.display = 'none';
    document.getElementById('workspace-view').style.display = 'none';
    document.getElementById('admin-view').style.display = 'none';

    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

    if (view === 'auth') {
        document.getElementById('auth-view').style.display = 'block';
    } else if (view === 'workspace') {
        document.getElementById('workspace-view').style.display = 'block';
        document.getElementById('nav-docs').classList.add('active');
        loadDocuments();
    } else if (view === 'admin') {
        document.getElementById('admin-view').style.display = 'block';
        document.getElementById('nav-admin').classList.add('active');
        loadGraph();
        loadPeers();
    }
}

// ── Auth ─────────────────────────────────────────────────────────────────────

async function register(e) {
    e.preventDefault();
    try {
        const data = await api('POST', '/auth/register', {
            username: document.getElementById('reg-username').value,
            email: document.getElementById('reg-email').value,
            password: document.getElementById('reg-password').value,
        });
        toast('Account created! Ed25519 keypair generated. Please log in.', 'success');
        document.getElementById('login-username').value = document.getElementById('reg-username').value;
        document.getElementById('reg-username').value = '';
        document.getElementById('reg-email').value = '';
        document.getElementById('reg-password').value = '';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function loginUser(e) {
    e.preventDefault();
    try {
        const data = await api('POST', '/auth/login', {
            username: document.getElementById('login-username').value,
            password: document.getElementById('login-password').value,
        });
        currentUser = data.user;
        document.getElementById('nav-user-info').innerHTML =
            `<span class="badge badge-owner"><i class="fas fa-user"></i> ${currentUser.username}</span>`;
        document.getElementById('nav-logout').style.display = 'block';
        showView('workspace');
        toast(`Welcome, ${currentUser.username}!`, 'success');
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function logout() {
    try {
        await api('POST', '/auth/logout');
    } catch { }
    currentUser = null;
    document.getElementById('nav-user-info').innerHTML = '';
    document.getElementById('nav-logout').style.display = 'none';
    showView('auth');
    toast('Logged out');
}

async function checkSession() {
    try {
        const user = await api('GET', '/auth/me');
        currentUser = user;
        document.getElementById('nav-user-info').innerHTML =
            `<span class="badge badge-owner"><i class="fas fa-user"></i> ${currentUser.username}</span>`;
        document.getElementById('nav-logout').style.display = 'block';
        showView('workspace');
    } catch {
        showView('auth');
    }
}

// ── Documents ────────────────────────────────────────────────────────────────

async function loadDocuments() {
    try {
        const data = await api('GET', '/documents');
        const container = document.getElementById('doc-list');

        if (data.owned.length === 0 && data.shared_with_me.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-folder-open"></i>
                    <p>No documents yet. Upload your first document!</p>
                </div>`;
            return;
        }

        let html = '';

        if (data.owned.length > 0) {
            html += '<p class="section-label">Owned by me</p>';
            data.owned.forEach(doc => {
                html += renderDocCard(doc, true);
            });
        }

        if (data.shared_with_me.length > 0) {
            html += '<p class="section-label" style="margin-top:1.5rem">Shared with me</p>';
            data.shared_with_me.forEach(doc => {
                html += renderDocCard(doc, false);
            });
        }

        container.innerHTML = html;
    } catch (err) {
        toast('Failed to load documents: ' + err.message, 'error');
    }
}

function renderDocCard(doc, isOwner) {
    const icon = getFileIcon(doc.mime_type);
    const size = formatBytes(doc.size_bytes);
    const date = new Date(doc.created_at).toLocaleDateString();

    let actions = `
        <button class="outline" onclick="event.stopPropagation(); downloadDoc('${doc.id}', '${doc.filename}')">
            <i class="fas fa-download"></i> Download
        </button>
        <button class="outline secondary" onclick="event.stopPropagation(); openDocDetail('${doc.id}')">
            <i class="fas fa-comments"></i> Details
        </button>`;

    if (isOwner) {
        actions += `
        <button class="outline" onclick="event.stopPropagation(); openShareDialog('${doc.id}')">
            <i class="fas fa-share-nodes"></i> Share
        </button>
        <button class="outline" style="color:var(--td-danger);border-color:var(--td-danger)" onclick="event.stopPropagation(); deleteDoc('${doc.id}', '${doc.filename}')">
            <i class="fas fa-trash"></i> Delete
        </button>`;
    }

    return `
        <div class="doc-card" onclick="openDocDetail('${doc.id}')">
            <div class="doc-title"><i class="${icon}"></i> ${escapeHtml(doc.filename)}</div>
            <div class="doc-meta">
                ${size} · ${date}
                ${isOwner ? `<span class="badge badge-owner">Owner</span>` : `<span class="badge badge-shared">Shared by ${escapeHtml(doc.owner_username)}</span>`}
                ${doc.share_count > 0 ? `· <i class="fas fa-users"></i> ${doc.share_count} recipients` : ''}
            </div>
            <div class="doc-meta hash"><i class="fas fa-fingerprint"></i> ${doc.content_hash.substring(0, 16)}...</div>
            <div class="doc-actions">${actions}</div>
        </div>`;
}

async function uploadDocument(e) {
    e.preventDefault();
    const fileInput = document.getElementById('upload-file');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const data = await api('POST', '/documents', formData);
        document.getElementById('upload-dialog').close();
        fileInput.value = '';
        toast(`"${data.filename}" uploaded. CoC root node created.`, 'success');
        loadDocuments();
    } catch (err) {
        toast(err.message, 'error');
    }
}

function openShareDialog(docId) {
    document.getElementById('share-doc-id').value = docId;
    document.getElementById('share-username').value = '';
    document.getElementById('share-dialog').showModal();
}

async function shareDocument(e) {
    e.preventDefault();
    const docId = document.getElementById('share-doc-id').value;
    const username = document.getElementById('share-username').value;

    try {
        await api('POST', `/documents/${docId}/share`, { recipient_username: username });
        document.getElementById('share-dialog').close();
        toast(`Document shared with ${username}. Watermark embedded.`, 'success');
        loadDocuments();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function downloadDoc(docId, filename) {
    try {
        const res = await fetch(`/documents/${docId}/download`, { credentials: 'include' });
        if (res.status === 409) {
            toast('This document has been deleted and is pending propagation across all nodes.', 'error');
            return;
        }
        if (!res.ok) throw new Error('Download failed');
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function deleteDoc(docId, filename) {
    if (!confirm(`Delete "${filename}"?\n\nThis is permanent and will propagate to all recipients. Deletion is cryptographically enforced.`)) return;

    try {
        const data = await api('DELETE', `/documents/${docId}`);
        toast(`Deleted. ${data.shares_revoked} shares revoked. Deletion propagated.`, 'success');
        loadDocuments();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// ── Document Detail (Comments + Chat) ────────────────────────────────────────

async function openDocDetail(docId) {
    currentDocId = docId;
    document.getElementById('comment-doc-id').value = docId;

    try {
        const doc = await api('GET', `/documents/${docId}`);
        document.getElementById('detail-title').innerHTML =
            `<i class="${getFileIcon(doc.mime_type)}"></i> ${escapeHtml(doc.filename)}`;
        document.getElementById('detail-meta').innerHTML = `
            <p><strong>Owner:</strong> ${escapeHtml(doc.owner_username)} · <strong>Size:</strong> ${formatBytes(doc.size_bytes)}</p>
            <p class="hash"><strong>Content Hash:</strong> ${doc.content_hash}</p>
            <p class="hash"><strong>CoC Node:</strong> ${doc.coc_node_hash}</p>
        `;

        // Load comments
        await loadComments(docId);

        // Connect chat WebSocket
        connectChat(docId);

        document.getElementById('doc-detail-dialog').showModal();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function loadComments(docId) {
    try {
        const comments = await api('GET', `/documents/${docId}/comments`);
        const container = document.getElementById('detail-comments');
        if (comments.length === 0) {
            container.innerHTML = '<p style="opacity:0.5">No comments yet</p>';
        } else {
            container.innerHTML = comments.map(c => `
                <div class="comment-item">
                    <span class="comment-author">${escapeHtml(c.author_username)}</span>
                    <span class="comment-time">${new Date(c.created_at).toLocaleString()}</span>
                    <p style="margin:0.2rem 0 0">${escapeHtml(c.body)}</p>
                </div>
            `).join('');
        }
    } catch { }
}

async function postComment(e) {
    e.preventDefault();
    const docId = document.getElementById('comment-doc-id').value;
    const body = document.getElementById('comment-body').value;

    try {
        await api('POST', `/documents/${docId}/comments`, { body });
        document.getElementById('comment-body').value = '';
        await loadComments(docId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

function connectChat(docId) {
    if (chatWs) {
        chatWs.close();
        chatWs = null;
    }

    document.getElementById('detail-chat').innerHTML = '<p style="opacity:0.5">Connecting...</p>';

    // Get session token from cookie for WS auth
    const token = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('session_token='));
    const tokenValue = token ? token.split('=')[1] : '';

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    chatWs = new WebSocket(`${protocol}//${location.host}/ws/documents/${docId}`);

    chatWs.onopen = () => {
        chatWs.send(JSON.stringify({ token: tokenValue, type: 'join' }));
    };

    chatWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const container = document.getElementById('detail-chat');

        if (data.type === 'joined') {
            container.innerHTML = '';
            // Load history
            loadChatHistory(docId);
        } else if (data.type === 'message') {
            container.innerHTML += `
                <div class="chat-msg">
                    <span class="chat-sender">${escapeHtml(data.sender)}</span>
                    <span class="chat-time">${data.created_at ? new Date(data.created_at).toLocaleTimeString() : ''}</span>
                    <p style="margin:0.1rem 0 0">${escapeHtml(data.body)}</p>
                </div>`;
            container.scrollTop = container.scrollHeight;
        } else if (data.type === 'error') {
            container.innerHTML = `<p style="color:var(--td-danger)">${escapeHtml(data.message)}</p>`;
        }
    };

    chatWs.onerror = () => {
        document.getElementById('detail-chat').innerHTML = '<p style="opacity:0.5">Chat unavailable</p>';
    };
}

async function loadChatHistory(docId) {
    try {
        const messages = await api('GET', `/documents/${docId}/messages`);
        const container = document.getElementById('detail-chat');
        container.innerHTML = messages.map(m => `
            <div class="chat-msg">
                <span class="chat-sender">${escapeHtml(m.sender_username)}</span>
                <span class="chat-time">${new Date(m.created_at).toLocaleTimeString()}</span>
                <p style="margin:0.1rem 0 0">${escapeHtml(m.body)}</p>
            </div>
        `).join('') || '<p style="opacity:0.5">No messages yet. Say hello!</p>';
        container.scrollTop = container.scrollHeight;
    } catch { }
}

function sendChat(e) {
    e.preventDefault();
    const body = document.getElementById('chat-body').value;
    if (chatWs && chatWs.readyState === WebSocket.OPEN && body) {
        chatWs.send(JSON.stringify({ type: 'message', body }));
        document.getElementById('chat-body').value = '';
    }
}

// ── Admin Dashboard ──────────────────────────────────────────────────────────

async function loadGraph() {
    try {
        const data = await api('GET', '/admin/graph');
        const container = document.getElementById('coc-graph');

        if (data.nodes.length === 0) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-diagram-project"></i><p>No CoC nodes yet</p></div>';
            return;
        }

        const nodes = new vis.DataSet(data.nodes.map(n => ({
            id: n.node_hash,
            label: `${n.owner_id.substring(0, 8)}\n${n.node_hash.substring(0, 8)}...`,
            color: n.parent_hash ? '#a29bfe' : '#6c5ce7',
            shape: n.parent_hash ? 'dot' : 'diamond',
            size: n.parent_hash ? 15 : 25,
            title: `Hash: ${n.node_hash}\nOwner: ${n.owner_id}\nDepth: ${n.depth || 0}`,
        })));

        const edges = new vis.DataSet(data.edges.map((e, i) => ({
            id: i,
            from: e.from,
            to: e.to,
            arrows: 'to',
            color: { color: '#a29bfe', opacity: 0.6 },
        })));

        new vis.Network(container, { nodes, edges }, {
            physics: {
                solver: 'forceAtlas2Based',
                forceAtlas2Based: { gravitationalConstant: -30, springLength: 100 },
            },
            nodes: { font: { color: '#ffffff', size: 10 } },
            edges: { smooth: { type: 'cubicBezier' } },
        });
    } catch (err) {
        toast('Failed to load graph: ' + err.message, 'error');
    }
}

async function loadPeers() {
    try {
        const peers = await api('GET', '/admin/peers');
        const container = document.getElementById('peer-list');
        if (peers.length === 0) {
            container.innerHTML = '<p style="opacity:0.5">No peers registered</p>';
            return;
        }
        container.innerHTML = peers.map(p => `
            <span class="badge ${p.is_online ? 'badge-online' : 'badge-offline'}" style="margin:0.2rem">
                <i class="fas fa-${p.is_online ? 'circle-check' : 'circle-xmark'}"></i>
                ${p.peer_id.substring(0, 8)}
            </span>
        `).join('');
    } catch { }
}

async function verifyLog() {
    const el = document.getElementById('audit-result');
    el.innerHTML = '<span class="spinner"></span> Verifying...';
    try {
        const data = await api('POST', '/admin/verify-log');
        el.innerHTML = data.valid
            ? `<span style="color:var(--td-success)"><i class="fas fa-check-circle"></i> Integrity VALID — ${data.chain_length} entries verified</span>`
            : `<span style="color:var(--td-danger)"><i class="fas fa-times-circle"></i> Integrity FAILED — tampering detected</span>`;
    } catch (err) {
        el.innerHTML = `<span style="color:var(--td-danger)">${err.message}</span>`;
    }
}

async function detectLeak(e) {
    e.preventDefault();
    const content = document.getElementById('leak-content').value;
    const el = document.getElementById('leak-result');
    el.innerHTML = '<span class="spinner"></span> Analyzing watermarks...';

    try {
        const data = await api('POST', '/admin/detect-leak', { content });
        if (data.leak_detected) {
            el.innerHTML = `
                <span style="color:var(--td-danger)"><i class="fas fa-exclamation-triangle"></i> LEAK DETECTED</span><br>
                <strong>Suspected peer:</strong> ${data.suspected_peer_id.substring(0, 12)}...<br>
                <strong>Confidence:</strong> ${(data.confidence * 100).toFixed(1)}%<br>
                <strong>Method:</strong> ${data.method}`;
        } else {
            el.innerHTML = `<span style="color:var(--td-success)"><i class="fas fa-check-circle"></i> No watermark detected — content appears clean</span>`;
        }
    } catch (err) {
        el.innerHTML = `<span style="color:var(--td-danger)">${err.message}</span>`;
    }
}

// ── Utilities ────────────────────────────────────────────────────────────────

function getFileIcon(mimeType) {
    if (!mimeType) return 'fas fa-file';
    if (mimeType.includes('pdf')) return 'fas fa-file-pdf';
    if (mimeType.includes('word') || mimeType.includes('doc')) return 'fas fa-file-word';
    if (mimeType.includes('excel') || mimeType.includes('sheet')) return 'fas fa-file-excel';
    if (mimeType.includes('image')) return 'fas fa-file-image';
    if (mimeType.includes('text')) return 'fas fa-file-lines';
    return 'fas fa-file';
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', checkSession);
