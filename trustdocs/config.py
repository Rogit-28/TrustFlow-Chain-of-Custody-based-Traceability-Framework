"""TrustDocs configuration.

Reads from environment variables with sensible defaults for development.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration loaded from environment."""

    # ── Database ──────────────────────────────────────────────────────────
    db_host: str = field(default_factory=lambda: os.getenv("TRUSTDOCS_DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("TRUSTDOCS_DB_PORT", "5432")))
    db_name: str = field(default_factory=lambda: os.getenv("TRUSTDOCS_DB_NAME", "trustdocs"))
    db_user: str = field(default_factory=lambda: os.getenv("TRUSTDOCS_DB_USER", "trustdocs"))
    db_password: str = field(default_factory=lambda: os.getenv("TRUSTDOCS_DB_PASSWORD", "trustdocs_dev"))

    @property
    def db_dsn(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # ── File Storage ──────────────────────────────────────────────────────
    storage_dir: str = field(
        default_factory=lambda: os.getenv(
            "TRUSTDOCS_STORAGE_DIR",
            str(Path(__file__).resolve().parent.parent / "data" / "trustdocs_files"),
        )
    )

    # ── Server ────────────────────────────────────────────────────────────
    host: str = field(default_factory=lambda: os.getenv("TRUSTDOCS_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("TRUSTDOCS_PORT", "8100")))
    node_id: str = field(default_factory=lambda: os.getenv("TRUSTDOCS_NODE_ID", "B"))

    # ── Security ──────────────────────────────────────────────────────────
    session_ttl_hours: int = 24
    max_file_size_mb: int = 50
    argon2_time_cost: int = 2
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 2

    # ── TrustFlow ─────────────────────────────────────────────────────────
    secret_sharing_threshold: int = 2
    tombstone_grace_seconds: int = 300  # 5 minutes


config = Config()
