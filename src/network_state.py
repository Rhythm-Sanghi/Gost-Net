"""
Ghost Net - Network State Machine & Delivery Models
Defines explicit lifecycle states for transport connections, peer availability,
message delivery states, and typed send results.
"""

from enum import Enum
from typing import Optional


class NetworkState(Enum):
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    DISCOVERING = "DISCOVERING"
    AVAILABLE = "AVAILABLE"
    PEER_VISIBLE = "PEER_VISIBLE"
    CONNECTING = "CONNECTING"
    SESSION_READY = "SESSION_READY"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"


class MessageDeliveryState(Enum):
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT_TO_PEER = "SENT_TO_PEER"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class SendResult(int):
    """Integer/boolean compatible result with delivery lifecycle metadata."""
    def __new__(cls, success: bool, msg_id: str, state: str, error: Optional[str] = None):
        val = 1 if success else 0
        obj = super().__new__(cls, val)
        obj.success = bool(success)
        obj.msg_id = str(msg_id)
        obj.state = str(state)
        obj.error = error
        return obj

    @property
    def delivery_state(self) -> str:
        return self.state

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        return f"SendResult(success={self.success}, msg_id='{self.msg_id}', state='{self.state}', error={self.error})"
