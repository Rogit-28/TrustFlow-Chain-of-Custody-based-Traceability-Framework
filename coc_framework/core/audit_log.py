from datetime import datetime
import hashlib
import os

class AuditLog:
    def __init__(self, log_directory=None):
        if log_directory is None:
            # Default to a 'data/logs' directory relative to the project root
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__))) # Go up three levels from core
            log_directory = os.path.join(script_dir, "data", "logs")

        os.makedirs(log_directory, exist_ok=True)
        self.log_file = os.path.join(log_directory, "audit.log")
        self.last_hash = self._get_last_hash()
        if not self.last_hash:
            self._initialize_log()
        print(f"[AUDIT] Audit Log Initialized. Log file at: {self.log_file}")

    def _get_last_hash(self) -> str:
        """Reads the last line of the log to get the last hash."""
        try:
            with open(self.log_file, 'rb') as f:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
                last_line = f.readline().decode().strip()
                return last_line.split(" | ")[-1] # The hash is the last element
        except (IOError, IndexError):
            return ""

    def _initialize_log(self):
        """Creates the header and genesis entry for the log file."""
        with open(self.log_file, 'w') as f:
            f.write("# Audit Log - Chain of Custody Simulator\n")
            f.write("# Each entry is chained by hashing the previous entry's hash.\n")
        self.log_event("GENESIS", "SYSTEM", "Log Initialized", "Initial state.")

    def log_event(self, event_type: str, actor: str, target: str, details: str = ""):
        """Appends a new, hashed event to the log."""
        timestamp = datetime.utcnow().isoformat()

        # Prepare the log entry content without the new hash
        log_entry_content = f"{event_type} | {actor} | {target} | {timestamp} | {details} | {self.last_hash}"

        # Create the new hash based on this content
        new_hash = hashlib.sha256(log_entry_content.encode('utf-8')).hexdigest()

        # Create the final, full log entry
        full_log_entry = f"{log_entry_content} | {new_hash}\n"

        with open(self.log_file, 'a') as f:
            f.write(full_log_entry)

        print(f"[AUDIT] Logged: {event_type} by {actor} on {target}")

        # Update the last hash for the next event
        self.last_hash = new_hash

    def verify_log_integrity(self) -> bool:
        """Verifies the entire log by re-calculating the hash chain."""
        print("[AUDIT] Verifying log integrity...")
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()

            # Skip headers
            log_entries = [line.strip() for line in lines if not line.startswith("#")]

            current_hash_from_prev_line = ""
            for i, entry in enumerate(log_entries):
                parts = entry.split(" | ")
                if len(parts) != 7: continue # Skip malformed lines

                prev_hash_in_entry = parts[5]
                if prev_hash_in_entry != current_hash_from_prev_line:
                    print(f"[AUDIT] Chain broken at line {i+1}! Expected hash {current_hash_from_prev_line}, found {prev_hash_in_entry}")
                    return False

                # Recalculate hash
                content_to_hash = " | ".join(parts[:-1])
                recalculated_hash = hashlib.sha256(content_to_hash.encode('utf-8')).hexdigest()

                stored_hash = parts[6]
                if recalculated_hash != stored_hash:
                    print(f"[AUDIT] Hash mismatch at line {i+1}! Recalculated hash is {recalculated_hash}, stored hash is {stored_hash}")
                    return False

                current_hash_from_prev_line = stored_hash

            print("[AUDIT] Log integrity verified successfully.")
            return True
        except FileNotFoundError:
            print("[AUDIT] Log file not found.")
            return False

if __name__ == '__main__':
    # --- DEMONSTRATION ---
    audit = AuditLog()

    audit.log_event("CREATE_PEER", "SYSTEM", "Alice", "Peer Alice created with keypair.")
    audit.log_event("SEND_MESSAGE", "Alice", "Bob", "Message hash: abc123def456")
    audit.log_event("DELETE_TOKEN", "Alice", "abc123def456", "Token issued for message.")

    # Verify integrity
    audit.verify_log_integrity()
