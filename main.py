import asyncio
import json
import logging
from aiohttp import web, WSMsgType
import aiohttp_jinja2
import jinja2
from coc_framework.simulation_engine import SimulationEngine

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def scenario_loader(filepath):
    """Loads a scenario from a JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Scenario file not found: {filepath}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {filepath}")
        return None

def serialize_simulation_state(engine):
    """Serializes the current state of the simulation to a dictionary."""
    nodes = []
    edges = []
    peers_info = {}

    for peer_id, peer in engine.peers.items():
        nodes.append({
            "id": peer_id,
            "label": f"Peer {peer_id[:4]}...",
            "title": f"Peer ID: {peer_id}\nStatus: {'Online' if peer.online else 'Offline'}",
            "group": "online" if peer.online else "offline"
        })
        peers_info[peer_id] = {
            "is_online": peer.online,
            "storage": [
                {
                    "node_hash": node.node_hash,
                    "content_hash": node.content_hash,
                    "owner_id": node.owner_id,
                    "parent_hash": node.parent_hash,
                    "children_hashes": list(node.children_hashes),
                    "depth": node.depth,
                } for node in peer.storage.get_all_nodes()
            ]
        }

    # Generate edges from the CoC graph structure
    for peer in engine.peers.values():
        for node in peer.storage.get_all_nodes():
            if node.parent_hash:
                # Find the peer that holds the parent node
                parent_peer_id = None
                for p in engine.peers.values():
                    if p.storage.get_node(node.parent_hash):
                        parent_peer_id = p.peer_id
                        break
                if parent_peer_id:
                    edges.append({
                        "from": parent_peer_id,
                        "to": peer.peer_id,
                        "arrows": "to",
                        "label": f"CoC Link\n{node.content_hash[:8]}..."
                    })

    return {
        "tick": engine.tick_count,
        "nodes": nodes,
        "edges": list({tuple(sorted(edge.items())) for edge in edges}), # Remove duplicates
        "peers_info": peers_info
    }


async def websocket_handler(request):
    """Handles WebSocket connections for the simulation."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    request.app['websockets'].add(ws)
    logging.info("WebSocket connection established.")

    try:
        # Send initial state
        engine = request.app['simulation_engine']
        state = serialize_simulation_state(engine)
        await ws.send_json(state)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                command = data.get("command")
                logging.info(f"Received command: {command}")

                if command == "step_forward":
                    await engine.tick()
                    state = serialize_simulation_state(engine)
                    for client in request.app['websockets']:
                        await client.send_json(state)
                elif command == "reset":
                    # Reload scenario and re-initialize engine
                    scenario = await scenario_loader('scenario.json')
                    if scenario:
                        request.app['simulation_engine'] = SimulationEngine(scenario)
                        logging.info("Simulation reset.")
                        state = serialize_simulation_state(request.app['simulation_engine'])
                        for client in request.app['websockets']:
                            await client.send_json(state)
                # Add other commands like 'play', 'pause' here in the future
            elif msg.type == WSMsgType.ERROR:
                logging.error(f"WebSocket connection closed with exception {ws.exception()}")
    finally:
        request.app['websockets'].remove(ws)
        logging.info("WebSocket connection closed.")
    return ws

@aiohttp_jinja2.template('index.html')
async def index(request):
    """Serves the main index.html file."""
    return {}

async def init_app():
    """Initializes the web application."""
    app = web.Application()
    app['websockets'] = set()

    # Load scenario and initialize the simulation engine
    scenario = await scenario_loader('scenario.json')
    if not scenario:
        raise RuntimeError("Failed to load scenario.json. Cannot start application.")
    app['simulation_engine'] = SimulationEngine(scenario)

    # Setup Jinja2 templates
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('frontend'))

    # Setup routes
    app.router.add_get('/', index)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/', path='frontend', name='static')


    return app

if __name__ == "__main__":
    web.run_app(init_app(), host='127.0.0.1', port=8080)
    logging.info("Server started on http://127.0.0.1:8080")
