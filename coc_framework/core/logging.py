"""Structured JSON logging for TrustFlow framework."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Union


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Component(Enum):
    PEER = "PEER"
    NETWORK = "NETWORK"
    COORDINATOR = "COORD"
    GOSSIP = "GOSSIP"
    DELETE = "DELETE"
    AUDIT = "AUDIT"
    CRYPTO = "CRYPTO"
    STORAGE = "STORAGE"
    TIMELOCK = "TIMELOCK"
    SECRET_SHARE = "SECRET_SHARE"
    STEGANO = "STEGANO"
    NOTIFICATION = "NOTIFICATION"
    SIMULATION = "SIM"
    VALIDATION = "VALIDATION"


class JSONFormatter(logging.Formatter):
    """Outputs log records as JSON with timestamp, level, component, message, and context."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "UNKNOWN"),
            "message": record.getMessage(),
        }
        if hasattr(record, "peer_id") and record.peer_id:
            log_entry["peer_id"] = record.peer_id
        if hasattr(record, "context") and record.context:
            log_entry["context"] = record.context
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class StructuredLogger:
    """Structured logger for TrustFlow components."""
    
    _global_level: int = logging.INFO
    _handlers_configured: bool = False
    
    def __init__(
        self,
        component: Union[Component, str],
        peer_id: Optional[str] = None,
        logger_name: Optional[str] = None,
    ):
        if isinstance(component, Component):
            self.component = component.value
        else:
            self.component = component
        self.peer_id = peer_id
        name = logger_name or f"trustflow.{self.component.lower()}"
        self._logger = logging.getLogger(name)
        self._ensure_handlers()
    
    @classmethod
    def _ensure_handlers(cls) -> None:
        if cls._handlers_configured:
            return
        root_logger = logging.getLogger("trustflow")
        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(JSONFormatter())
            root_logger.addHandler(handler)
            root_logger.setLevel(cls._global_level)
            root_logger.propagate = False
        cls._handlers_configured = True
    
    @classmethod
    def set_level(cls, level: Union[LogLevel, str, int]) -> None:
        if isinstance(level, LogLevel):
            level_int = getattr(logging, level.value)
        elif isinstance(level, str):
            level_int = getattr(logging, level.upper())
        else:
            level_int = level
        cls._global_level = level_int
        logging.getLogger("trustflow").setLevel(level_int)
    
    @classmethod
    def disable(cls) -> None:
        logging.getLogger("trustflow").setLevel(logging.CRITICAL + 1)
    
    @classmethod
    def enable(cls) -> None:
        logging.getLogger("trustflow").setLevel(cls._global_level)
    
    def _log(self, level: int, message: str, **context: Any) -> None:
        extra = {
            "component": self.component,
            "peer_id": self.peer_id,
            "context": context if context else None,
        }
        self._logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **context: Any) -> None:
        self._log(logging.DEBUG, message, **context)
    
    def info(self, message: str, **context: Any) -> None:
        self._log(logging.INFO, message, **context)
    
    def warning(self, message: str, **context: Any) -> None:
        self._log(logging.WARNING, message, **context)
    
    def error(self, message: str, **context: Any) -> None:
        self._log(logging.ERROR, message, **context)
    
    def critical(self, message: str, **context: Any) -> None:
        self._log(logging.CRITICAL, message, **context)
    
    def with_peer(self, peer_id: str) -> "StructuredLogger":
        return StructuredLogger(
            component=self.component,
            peer_id=peer_id,
            logger_name=self._logger.name,
        )


def get_logger(component: Union[Component, str], peer_id: Optional[str] = None) -> StructuredLogger:
    return StructuredLogger(component, peer_id)


def peer_logger(peer_id: Optional[str] = None) -> StructuredLogger:
    return StructuredLogger(Component.PEER, peer_id)


def network_logger() -> StructuredLogger:
    return StructuredLogger(Component.NETWORK)


def coordinator_logger() -> StructuredLogger:
    return StructuredLogger(Component.COORDINATOR)


def gossip_logger(peer_id: Optional[str] = None) -> StructuredLogger:
    return StructuredLogger(Component.GOSSIP, peer_id)


def deletion_logger() -> StructuredLogger:
    return StructuredLogger(Component.DELETE)


def audit_logger() -> StructuredLogger:
    return StructuredLogger(Component.AUDIT)


def crypto_logger() -> StructuredLogger:
    return StructuredLogger(Component.CRYPTO)


def storage_logger() -> StructuredLogger:
    return StructuredLogger(Component.STORAGE)


def configure_logging(level: Union[LogLevel, str, int] = LogLevel.INFO, json_output: bool = True) -> None:
    StructuredLogger.set_level(level)
    if not json_output:
        root_logger = logging.getLogger("trustflow")
        for handler in root_logger.handlers:
            handler.setFormatter(logging.Formatter(
                "[%(asctime)s] %(levelname)s [%(component)s] %(message)s"
            ))


def silence_logging() -> None:
    StructuredLogger.disable()


def restore_logging() -> None:
    StructuredLogger.enable()


__all__ = [
    "StructuredLogger",
    "JSONFormatter",
    "LogLevel",
    "Component",
    "get_logger",
    "peer_logger",
    "network_logger",
    "coordinator_logger",
    "gossip_logger",
    "deletion_logger",
    "audit_logger",
    "crypto_logger",
    "storage_logger",
    "configure_logging",
    "silence_logging",
    "restore_logging",
]
