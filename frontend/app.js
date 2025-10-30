document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('network-graph');
    const nodes = new vis.DataSet([]);
    const edges = new vis.DataSet([]);

    const data = {
        nodes: nodes,
        edges: edges,
    };

    const options = {
        layout: {
            hierarchical: {
                enabled: true,
                direction: 'UD', // Up-Down direction
                sortMethod: 'hubsize', // Arrange nodes based on connections
                levelSeparation: 150,
                nodeSpacing: 100,
                treeSpacing: 200,
            },
        },
        physics: {
            enabled: true,
            hierarchicalRepulsion: {
                centralGravity: 0.0,
                springLength: 100,
                springConstant: 0.01,
                nodeDistance: 120,
                damping: 0.09,
            },
            solver: 'hierarchicalRepulsion',
        },
        nodes: {
            shape: 'ellipse',
            size: 16,
            font: {
                size: 14,
                color: '#333',
            },
            borderWidth: 2,
        },
        edges: {
            width: 1,
            arrows: {
                to: { enabled: true, scaleFactor: 0.5 },
            },
            smooth: {
                type: 'cubicBezier',
                forceDirection: 'vertical',
                roundness: 0.4,
            },
        },
        groups: {
            online: {
                color: {
                    border: '#2B7CE9',
                    background: '#97C2FC',
                    highlight: {
                        border: '#2B7CE9',
                        background: '#D2E5FF',
                    },
                },
            },
            offline: {
                color: {
                    border: '#444',
                    background: '#AAA',
                    highlight: {
                        border: '#444',
                        background: '#DDD',
                    },
                },
            },
        },
    };

    const network = new vis.Network(container, data, options);

    // Make network object and datasets globally accessible
    window.network = network;
    window.nodes = nodes;
    window.edges = edges;
    window.peersInfo = {}; // To store detailed peer data

    // --- WebSocket and Controls ---
    const stepBtn = document.getElementById('step-btn');
    const resetBtn = document.getElementById('reset-btn');
    const playBtn = document.getElementById('play-btn');
    const pauseBtn = document.getElementById('pause-btn');
    let playInterval = null;

    const ws = new WebSocket('ws://127.0.0.1:8080/ws');

    ws.onopen = () => {
        console.log('WebSocket connection established');
    };

    ws.onmessage = (event) => {
        const state = JSON.parse(event.data);
        console.log('Received state:', state);

        // Update nodes
        const newNodes = state.nodes.map(node => ({
            id: node.id,
            label: node.label,
            title: node.title,
            group: node.group,
        }));
        nodes.update(newNodes);

        // Update edges
        // To avoid flickering, we can remove only the edges that are not in the new state
        const existingEdgeIds = edges.getIds();
        const newEdgeIds = new Set(state.edges.map(e => `${e.from}-${e.to}`));
        const edgesToRemove = existingEdgeIds.filter(id => !newEdgeIds.has(id));
        edges.remove(edgesToRemove);
        edges.update(state.edges.map(edge => ({
            id: `${edge.from}-${edge.to}`, // Assign a unique ID to prevent duplicates
            from: edge.from,
            to: edge.to,
            arrows: edge.arrows,
            label: edge.label,
        })));


        // Store peer info for the inspection feature
        window.peersInfo = state.peers_info;
    };

    ws.onerror = (error) => {
        console.error('WebSocket Error:', error);
    };

    ws.onclose = () => {
        console.log('WebSocket connection closed');
        clearInterval(playInterval);
    };

    function sendCommand(command) {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ command }));
        } else {
            console.error('WebSocket is not open. ReadyState:', ws.readyState);
        }
    }

    stepBtn.addEventListener('click', () => sendCommand('step_forward'));
    resetBtn.addEventListener('click', () => sendCommand('reset'));

    playBtn.addEventListener('click', () => {
        if (!playInterval) {
            playInterval = setInterval(() => sendCommand('step_forward'), 1000); // Step every second
            playBtn.disabled = true;
            pauseBtn.disabled = false;
        }
    });

    pauseBtn.addEventListener('click', () => {
        clearInterval(playInterval);
        playInterval = null;
        playBtn.disabled = false;
        pauseBtn.disabled = true;
    });

    // Initial button state
    pauseBtn.disabled = true;

    // --- Node Inspection ---
    const detailsContent = document.getElementById('details-content');

    network.on('click', (params) => {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const peerInfo = window.peersInfo[nodeId];
            if (peerInfo) {
                let detailsHTML = `<strong>Peer ID:</strong> ${nodeId}\n`;
                detailsHTML += `<strong>Status:</strong> ${peerInfo.is_online ? 'Online' : 'Offline'}\n\n`;
                detailsHTML += `<strong>Stored CoC Nodes:</strong>\n`;
                if (peerInfo.storage.length > 0) {
                    peerInfo.storage.forEach(node => {
                        detailsHTML += `  - <strong>Node Hash:</strong> ${node.node_hash.substring(0, 12)}...\n`;
                        detailsHTML += `    <strong>Content Hash:</strong> ${node.content_hash.substring(0, 12)}...\n`;
                        detailsHTML += `    <strong>Owner:</strong> ${node.owner_id.substring(0, 12)}...\n`;
                        detailsHTML += `    <strong>Depth:</strong> ${node.depth}\n`;
                    });
                } else {
                    detailsHTML += `  (No nodes stored)`;
                }
                detailsContent.textContent = detailsHTML;
            } else {
                detailsContent.textContent = `No details available for node ${nodeId}.`;
            }
        } else {
            detailsContent.textContent = 'Click on a node to see its details.';
        }
    });
});
