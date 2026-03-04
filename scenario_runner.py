"""
TrustFlow Scenario Runner

CLI entry point for running CoC simulations from scenario JSON files.
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path

# Add the project root to the Python path to allow for module imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from coc_framework.simulation_engine import SimulationEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_scenario(scenario_path: str) -> dict:
    """Load a scenario from a JSON file."""
    try:
        with open(scenario_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Scenario file not found: {scenario_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in scenario file: {e}")
        raise


async def run_simulation(scenario: dict, tick_delay: float = 0.1) -> None:
    """
    Run the simulation from start to finish.
    
    Args:
        scenario: The scenario dictionary
        tick_delay: Delay between ticks in seconds (default 0.1 for CLI)
    """
    logger.info("--- Starting Simulation ---")
    
    # Initialize the simulation engine
    engine = SimulationEngine(scenario)
    
    # Get simulation duration
    duration = scenario.get("settings", {}).get("simulation_duration", 10)
    logger.info(f"Running simulation for {duration} ticks with {len(engine.peers)} peers")
    
    try:
        # Run the simulation tick by tick
        for tick in range(duration):
            logger.info(f"--- Tick {tick + 1}/{duration} ---")
            await engine.tick(tick_delay=tick_delay)
        
        logger.info("--- Simulation Complete ---")
        
        # Print final state summary
        peers = engine.peers
        logger.info(f"Final state: {len(peers)} peers")
        for peer_id, peer in peers.items():
            node_count = len(peer.storage.get_all_nodes())
            status = "online" if peer.online else "offline"
            logger.info(f"  Peer {peer_id[:8]}...: {node_count} nodes, {status}")
        
        # Print audit log info
        logger.info("--- Audit Log ---")
        logger.info(f"Audit log file: {engine.audit_log.log_file}")
        if engine.audit_log.verify_log_integrity():
            logger.info("Audit log integrity: VERIFIED")
        else:
            logger.warning("Audit log integrity: FAILED")
    
    finally:
        # Clean shutdown
        engine.shutdown()
        logger.info("Engine shutdown complete")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Run a TrustFlow Chain of Custody simulation'
    )
    parser.add_argument(
        'scenario',
        nargs='?',
        default='scenario.json',
        help='Path to the scenario JSON file (default: scenario.json)'
    )
    parser.add_argument(
        '--tick-delay',
        type=float,
        default=0.1,
        help='Delay between simulation ticks in seconds (default: 0.1)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose (DEBUG) logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        scenario = load_scenario(args.scenario)
        asyncio.run(run_simulation(scenario, tick_delay=args.tick_delay))
    except FileNotFoundError:
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Simulation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
