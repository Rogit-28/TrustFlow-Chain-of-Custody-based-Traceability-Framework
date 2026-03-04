"""
TrustFlow Network Protocol - ZeroMQ message types and serialization.

Security: SignedEnvelope with Ed25519 signatures, timestamp validation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from time import time as time_time
from typing import Any, ClassVar, Dict, Final, List, Optional, Tuple, Type, Union

from ..core.crypto_core import CryptoCore


MESSAGE_MAX_AGE_SECONDS: Final[int] = 300
MESSAGE_MAX_FUTURE_SECONDS: Final[int] = 60


class MessageType(Enum):
    """Message types for peer communication."""
    SHARE = "share"
    COC_NODE = "coc_node"
    CONTENT = "content"
    DELETION_TOKEN = "deletion_token"
    DELETION_ACK = "deletion_ack"
    PEER_STATUS = "peer_status"
    PEER_DISCOVERY = "peer_discovery"
    HEARTBEAT = "heartbeat"
    REQUEST_SHARE = "request_share"
    REQUEST_CONTENT = "request_content"
    RECONSTRUCT_REQUEST = "reconstruct"
    RESPONSE = "response"
    ERROR = "error"
    KEY_EXCHANGE = "key_exchange"
    KEY_EXCHANGE_ACK = "key_exchange_ack"


MESSAGE_TYPE_MAP: Final[Dict[str, MessageType]] = {mt.value: mt for mt in MessageType}


class PeerStatus(Enum):
    """Peer online/offline status."""
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


PEER_STATUS_MAP: Final[Dict[str, PeerStatus]] = {ps.value: ps for ps in PeerStatus}


@dataclass(slots=True)
class NetworkMessage:
    """Base message class for network communication."""
    sender_id: str
    msg_type: MessageType = field(default=MessageType.HEARTBEAT)
    timestamp: float = field(default_factory=time_time)
    msg_id: str = ""
    signature: str = ""
    
    def __post_init__(self) -> None:
        if not self.msg_id:
            content = f"{self.sender_id}:{self.timestamp}:{self.msg_type.value}"
            self.msg_id = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "msg_type": self.msg_type.value,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
            "signature": self.signature,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NetworkMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> NetworkMessage:
        return cls.from_dict(json.loads(json_str))
    
    @classmethod
    def from_bytes(cls, data: bytes) -> NetworkMessage:
        return cls.from_json(data.decode("utf-8"))


@dataclass
class ShareMessage(NetworkMessage):
    """Message for distributing Shamir's secret shares."""
    share_index: int = 0
    share_data: str = ""
    content_hash: str = ""
    threshold: int = 0
    total_shares: int = 0
    metadata: str = ""
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.SHARE
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "share_index": self.share_index,
            "share_data": self.share_data,
            "content_hash": self.content_hash,
            "threshold": self.threshold,
            "total_shares": self.total_shares,
            "metadata": self.metadata,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShareMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class DeletionTokenMessage(NetworkMessage):
    """Message for propagating deletion tokens."""
    node_hash: str = ""
    originator_id: str = ""
    token_signature: str = ""
    cascade: bool = True
    reason: str = ""
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.DELETION_TOKEN
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "node_hash": self.node_hash,
            "originator_id": self.originator_id,
            "token_signature": self.token_signature,
            "cascade": self.cascade,
            "reason": self.reason,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeletionTokenMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class CoCNodeMessage(NetworkMessage):
    """Message for transferring Chain of Custody nodes."""
    node_data: Dict[str, Any] = field(default_factory=dict)
    parent_hash: str = ""
    content_hash: str = ""
    watermark_key: str = ""
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.COC_NODE
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "node_data": self.node_data,
            "parent_hash": self.parent_hash,
            "content_hash": self.content_hash,
            "watermark_key": self.watermark_key,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CoCNodeMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class PeerStatusMessage(NetworkMessage):
    """Message for peer status updates."""
    peer_id: str = ""
    status: PeerStatus = PeerStatus.UNKNOWN
    address: str = ""
    capabilities: List[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.PEER_STATUS
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "peer_id": self.peer_id,
            "status": self.status.value,
            "address": self.address,
            "capabilities": self.capabilities,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PeerStatusMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        status_val = data.get("status")
        if isinstance(status_val, str):
            data["status"] = PEER_STATUS_MAP[status_val]
        return cls(**data)


@dataclass
class ContentMessage(NetworkMessage):
    """Message for transferring encrypted content."""
    content_hash: str = ""
    encrypted_content: str = ""
    timelock_expiry: float = 0
    encryption_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.CONTENT
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "content_hash": self.content_hash,
            "encrypted_content": self.encrypted_content,
            "timelock_expiry": self.timelock_expiry,
            "encryption_metadata": self.encryption_metadata,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContentMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class RequestMessage(NetworkMessage):
    """Message for requesting data from peers."""
    request_type: str = ""
    content_hash: str = ""
    additional_params: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.REQUEST_SHARE
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "request_type": self.request_type,
            "content_hash": self.content_hash,
            "additional_params": self.additional_params,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RequestMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class ResponseMessage(NetworkMessage):
    """Generic response message."""
    request_id: str = ""
    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.RESPONSE
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "request_id": self.request_id,
            "success": self.success,
            "data": self.data,
            "error_message": self.error_message,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResponseMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class HeartbeatMessage(NetworkMessage):
    """Heartbeat message for connection monitoring."""
    sequence: int = 0
    load: int = 0
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.HEARTBEAT
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({"sequence": self.sequence, "load": self.load})
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HeartbeatMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class KeyExchangeMessage(NetworkMessage):
    """Message for exchanging public keys between peers."""
    public_key: str = ""
    peer_address: str = ""
    nonce: str = ""
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.KEY_EXCHANGE
        if not self.nonce:
            self.nonce = secrets.token_hex(16)
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "public_key": self.public_key,
            "peer_address": self.peer_address,
            "nonce": self.nonce,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KeyExchangeMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


@dataclass
class KeyExchangeAckMessage(NetworkMessage):
    """Acknowledgment for key exchange."""
    public_key: str = ""
    peer_address: str = ""
    original_nonce: str = ""
    response_nonce: str = ""
    
    def __post_init__(self) -> None:
        self.msg_type = MessageType.KEY_EXCHANGE_ACK
        if not self.response_nonce:
            self.response_nonce = secrets.token_hex(16)
        super().__post_init__()
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "public_key": self.public_key,
            "peer_address": self.peer_address,
            "original_nonce": self.original_nonce,
            "response_nonce": self.response_nonce,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KeyExchangeAckMessage:
        msg_type_val = data.get("msg_type")
        if isinstance(msg_type_val, str):
            data["msg_type"] = MESSAGE_TYPE_MAP[msg_type_val]
        return cls(**data)


class SignatureVerificationError(Exception):
    """Raised when message signature verification fails."""
    pass


class MessageTimestampError(Exception):
    """Raised when message timestamp is invalid."""
    pass


def validate_message_timestamp(
    timestamp: float,
    max_age: int = MESSAGE_MAX_AGE_SECONDS,
    max_future: int = MESSAGE_MAX_FUTURE_SECONDS
) -> Tuple[bool, str]:
    """Validate message timestamp is within acceptable window."""
    now = time.time()
    age = now - timestamp
    if age > max_age:
        return False, f"Message too old ({age:.0f}s > {max_age}s)"
    if age < -max_future:
        return False, f"Message from future ({-age:.0f}s ahead)"
    return True, ""


@dataclass
class SignedEnvelope:
    """
    Cryptographic wrapper for authenticated message delivery.
    Signature covers: sender_id | timestamp | payload_hash
    """
    sender_id: str
    timestamp: float
    payload: bytes
    signature: str
    
    _DELIMITER: ClassVar[str] = "|"
    
    def _get_signing_data(self) -> str:
        payload_hash = hashlib.sha256(self.payload).hexdigest()
        return f"{self.sender_id}{self._DELIMITER}{self.timestamp}{self._DELIMITER}{payload_hash}"
    
    def sign(self, signing_key) -> None:
        data = self._get_signing_data()
        self.signature = CryptoCore.sign_message(signing_key, data).hex()
    
    def verify(self, verify_key) -> bool:
        if not self.signature:
            return False
        data = self._get_signing_data()
        try:
            return CryptoCore.verify_signature(verify_key, data, bytes.fromhex(self.signature))
        except Exception:
            return False
    
    def validate_timestamp(self) -> Tuple[bool, str]:
        return validate_message_timestamp(self.timestamp)
    
    def unwrap(self) -> NetworkMessage:
        return deserialize_message(self.payload)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "payload": base64.b64encode(self.payload).decode("ascii"),
            "signature": self.signature,
        }
    
    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict()).encode("utf-8")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SignedEnvelope:
        return cls(
            sender_id=data["sender_id"],
            timestamp=data["timestamp"],
            payload=base64.b64decode(data["payload"]),
            signature=data["signature"],
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> SignedEnvelope:
        return cls.from_dict(json.loads(data.decode("utf-8")))
    
    @classmethod
    def wrap(cls, message: NetworkMessage, sender_id: str, signing_key) -> SignedEnvelope:
        envelope = cls(
            sender_id=sender_id,
            timestamp=time.time(),
            payload=message.to_bytes(),
            signature="",
        )
        envelope.sign(signing_key)
        return envelope


def unwrap_and_verify(
    data: bytes,
    get_verify_key,
    validate_time: bool = True
) -> Tuple[NetworkMessage, str]:
    """Unwrap and verify a signed envelope."""
    envelope = SignedEnvelope.from_bytes(data)
    
    verify_key = get_verify_key(envelope.sender_id)
    if verify_key is None:
        raise SignatureVerificationError(f"Unknown sender: {envelope.sender_id}")
    
    if not envelope.verify(verify_key):
        raise SignatureVerificationError(f"Invalid signature from {envelope.sender_id}")
    
    if validate_time:
        valid, error = envelope.validate_timestamp()
        if not valid:
            raise MessageTimestampError(error)
    
    return envelope.unwrap(), envelope.sender_id


MESSAGE_CLASSES: Final[Dict[MessageType, Type[NetworkMessage]]] = {
    MessageType.SHARE: ShareMessage,
    MessageType.COC_NODE: CoCNodeMessage,
    MessageType.DELETION_TOKEN: DeletionTokenMessage,
    MessageType.PEER_STATUS: PeerStatusMessage,
    MessageType.CONTENT: ContentMessage,
    MessageType.REQUEST_SHARE: RequestMessage,
    MessageType.REQUEST_CONTENT: RequestMessage,
    MessageType.RECONSTRUCT_REQUEST: RequestMessage,
    MessageType.RESPONSE: ResponseMessage,
    MessageType.ERROR: ResponseMessage,
    MessageType.HEARTBEAT: HeartbeatMessage,
    MessageType.KEY_EXCHANGE: KeyExchangeMessage,
    MessageType.KEY_EXCHANGE_ACK: KeyExchangeAckMessage,
}


def deserialize_message(data: Union[bytes, str, Dict[str, Any]]) -> NetworkMessage:
    """Deserialize a message from bytes, JSON string, or dictionary."""
    if isinstance(data, bytes):
        data = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        data = json.loads(data)
    
    msg_type_str = data["msg_type"]
    msg_type = MESSAGE_TYPE_MAP.get(msg_type_str) if isinstance(msg_type_str, str) else msg_type_str
    msg_class = MESSAGE_CLASSES.get(msg_type, NetworkMessage)
    return msg_class.from_dict(data)


class SocketConfig:
    """Configuration for ZeroMQ sockets."""
    __slots__ = ()
    
    PUB_PORT_START: ClassVar[int] = 5550
    REP_PORT_START: ClassVar[int] = 5600
    COORDINATOR_PORT: ClassVar[int] = 5500
    RECV_TIMEOUT: ClassVar[int] = 1000
    SEND_TIMEOUT: ClassVar[int] = 1000
    LINGER: ClassVar[int] = 0
    HEARTBEAT_INTERVAL: ClassVar[float] = 5.0
    HEARTBEAT_TIMEOUT: ClassVar[float] = 15.0
    
    @staticmethod
    def get_pub_address(peer_index: int, host: str = "127.0.0.1") -> str:
        return f"tcp://{host}:{SocketConfig.PUB_PORT_START + peer_index}"
    
    @staticmethod
    def get_rep_address(peer_index: int, host: str = "127.0.0.1") -> str:
        return f"tcp://{host}:{SocketConfig.REP_PORT_START + peer_index}"
    
    @staticmethod
    def get_coordinator_address(host: str = "127.0.0.1") -> str:
        return f"tcp://{host}:{SocketConfig.COORDINATOR_PORT}"
