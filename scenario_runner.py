import json
import sys
import os

# Add the project root to the Python path to allow for module imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from coc_framework.simulation_engine import SimulationEngine

def run_simulation():
    """
    Loads a scenario, runs the simulation from start to finish,
    and prints the final audit log.
    """
    # Load the scenario from the JSON file
    scenario_path = 'scenario.json'
    try:
        with open(scenario_path, 'r') as f:
            scenario = json.load(f)
    except FileNotFoundError:
        print(f"Error: Scenario file not found at '{scenario_path}'")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{scenario_path}'")
        return

    print("--- Starting Simulation ---")

    # Initialize and set up the simulation engine
    engine = SimulationEngine(scenario)
    engine.setup()

    # Run the simulation tick by tick until it's over
    duration = scenario.get("settings", {}).get("simulation_duration", 1)
    for tick in range(duration):
        print(f"\n--- Tick {tick + 1}/{duration} ---")
        engine.tick()

    print("\n--- Simulation Complete ---")

    # Print the final audit log to show the results
    print("\n--- Final Audit Log ---")
    try:
        with open(engine.audit_log.log_file, 'r') as f:
            print(f.read())
    except FileNotFoundError:
        print("Audit log file not found.")

if __name__ == "__main__":
    run_simulation()
