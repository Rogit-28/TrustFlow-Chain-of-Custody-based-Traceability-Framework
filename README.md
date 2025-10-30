# Chain of Custody (CoC) Privacy Framework Simulator

This project is a Python-based, command-line simulator for a Chain of Custody (CoC) Privacy Framework. It is designed to model and validate the architectural feasibility of a decentralized privacy and trust system in a virtual peer-to-peer network.

The simulator tracks content provenance, handles secure deletion propagation, and is architected to support future extensions like traceability watermarks.

## How It Works: A Backend Simulation

The simulator operates as a backend-only, event-driven system.

1.  **The Simulation Engine (`coc_framework/simulation_engine.py`)**:
    *   This is a "tick-based" engine that processes a `scenario.json` file one step at a time.
    *   After each "tick," it calculates the new state (new peers, new messages, etc.).

2.  **The Scenario Runner (`scenario_runner.py`)**:
    *   This is the main entry point for the simulation.
    *   It loads the `scenario.json` file.
    *   It initializes the `SimulationEngine`.
    *   It runs the simulation from start to finish, printing the final state of the audit log to the console.

## Key Features

*   **Graph-Based CoC:** The Chain of Custody is modeled as a directed graph, allowing for complex forwarding scenarios and efficient traversal.
*   **Offline Message Queuing:** Peers can go offline and receive messages in a queue, which are then processed when they come back online.
*   **Watermarking:** Messages can be watermarked with sender metadata for leak attribution.
*   **Extensible Interfaces:** The framework is designed with a set of abstract interfaces for key components, allowing for custom implementations of storage, peer discovery, and more.
*   **Cryptographic Integrity:** All CoC nodes and deletion tokens are cryptographically signed to ensure their integrity.

## Project Structure

```
.
├── coc_framework/         # The core Python package for the simulator
│   ├── core/              # Core logic modules
│   ├── interfaces/        # Abstract interfaces for extensibility
│   └── simulation_engine.py # The main simulation engine
│
├── data/                  # Directory for generated simulation data (ignored by git)
│
├── tests/                 # Unit tests for the core modules
│
├── scenario_runner.py     # Main entry point: runs the simulation
├── scenario.json          # Defines the events for the simulation
├── requirements.txt       # Project dependencies
└── README.md              # This file
```

## Local Setup and Execution

Follow these steps to set up and run the simulation on your local machine.

### Step 1: Clone the Repository & Set Up Environment

```bash
# Clone the repository
git clone <your-repository-url>
cd <repository-folder-name>

# Create and activate a Python virtual environment
python -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies

Install the required Python libraries using pip.

```bash
pip install -r requirements.txt
```

### Step 3: Run the Simulation

Execute the `scenario_runner.py` script from the project's **root directory**.

```bash
python scenario_runner.py
```

You will see the simulation progress tick by tick in your terminal, followed by a printout of the final audit log.

### Step 4: Customize the Scenario

To run your own simulation, you can edit the **`scenario.json`** file. You can change:
*   `total_peers`: The number of anonymous clients in the network.
*   `events`: The list of actions to be performed.
*   `settings`: A variety of settings to control the simulation, such as `watermark_secret_key`, `default_ttl_hours`, and `default_watermark_enabled`.

After saving your changes to `scenario.json`, simply run the `scenario_runner.py` script again to see the results of your new scenario.

## Running the Frontend

The simulator includes a web-based frontend for visualizing the network graph and controlling the simulation in real-time.

### Step 1: Start the Web Server

Run the `main.py` script from the project's **root directory**.

```bash
python main.py
```

This will start the backend web server and WebSocket service.

### Step 2: Open the Frontend in Your Browser

Open your web browser and navigate to the following URL:

[http://127.0.0.1:8080](http://127.0.0.1:8080)

You will see the interactive network graph and be able to control the simulation using the "Play," "Pause," "Step," and "Reset" buttons.
