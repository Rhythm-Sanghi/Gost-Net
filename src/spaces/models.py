"""
Ghost Net - Spaces Data Models
Core data structures for offline shared field workspaces, membership,
and signed mutable state events.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict


class ExpiryPolicy:
    ONE_HOUR = "1_hour"
    SIX_HOURS = "6_hours"
    TONIGHT = "tonight"
    TWENTY_FOUR_HOURS = "24_hours"
    SEVEN_DAYS = "7_days"
    NEVER = "never"

    ALL = {ONE_HOUR, SIX_HOURS, TONIGHT, TWENTY_FOUR_HOURS, SEVEN_DAYS, NEVER}


class JoinPolicy:
    OPEN_NEARBY = "open_nearby"
    INVITE_ONLY = "invite_only"

    ALL = {OPEN_NEARBY, INVITE_ONLY}


class LifecycleState:
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"

    ALL = {ACTIVE, ARCHIVED, EXPIRED}


class MemberRole:
    MEMBER = "member"
    MODERATOR = "moderator"

    ALL = {MEMBER, MODERATOR}


class EventType:
    SPACE_CREATE = "SPACE_CREATE"
    SPACE_CREATED = "SPACE_CREATED"
    SPACE_JOIN = "SPACE_JOIN"
    SPACE_JOINED = "SPACE_JOINED"
    SPACE_LEAVE = "SPACE_LEAVE"
    SPACE_LEFT = "SPACE_LEFT"
    MESSAGE_ADD = "MESSAGE_ADD"
    MESSAGE_CREATED = "MESSAGE_CREATED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MESSAGE_QUEUED = "MESSAGE_QUEUED"
    MESSAGE_DELIVERED = "MESSAGE_DELIVERED"
    MESSAGE_RELAYED = "MESSAGE_RELAYED"
    NOTE_CREATE = "NOTE_CREATE"
    NOTE_CREATED = "NOTE_CREATED"
    NOTE_UPDATE = "NOTE_UPDATE"
    NOTE_UPDATED = "NOTE_UPDATED"
    FILE_ANNOUNCE = "FILE_ANNOUNCE"
    FILE_SHARED = "FILE_SHARED"
    FILE_AVAILABLE = "FILE_AVAILABLE"
    WAYPOINT_ADD = "WAYPOINT_ADD"
    WAYPOINT_ADDED = "WAYPOINT_ADDED"
    WAYPOINT_UPDATE = "WAYPOINT_UPDATE"
    WAYPOINT_UPDATED = "WAYPOINT_UPDATED"
    WAYPOINT_REMOVE = "WAYPOINT_REMOVE"
    WAYPOINT_REMOVED = "WAYPOINT_REMOVED"
    AREA_ADD = "AREA_ADD"
    AREA_UPDATE = "AREA_UPDATE"
    ROUTE_ADD = "ROUTE_ADD"
    ROUTE_UPDATE = "ROUTE_UPDATE"
    ROUTE_AVAILABLE = "ROUTE_AVAILABLE"
    ROUTE_LOST = "ROUTE_LOST"
    OBSERVATION_ADD = "OBSERVATION_ADD"
    STATUS_UPDATE = "STATUS_UPDATE"
    STATUS_CHANGED = "STATUS_CHANGED"
    PEER_SEEN = "PEER_SEEN"
    PEER_LOST = "PEER_LOST"
    DELIVERY_UPDATE = "DELIVERY_UPDATE"
    NETWORK_SPLIT = "NETWORK_SPLIT"
    NETWORK_REJOIN = "NETWORK_REJOIN"
    STATE_MERGED = "STATE_MERGED"
    CONFLICT_RESOLVE = "CONFLICT_RESOLVE"

    ALL = {
        SPACE_CREATE, SPACE_CREATED,
        SPACE_JOIN, SPACE_JOINED,
        SPACE_LEAVE, SPACE_LEFT,
        MESSAGE_ADD, MESSAGE_CREATED, MESSAGE_RECEIVED, MESSAGE_QUEUED,
        MESSAGE_DELIVERED, MESSAGE_RELAYED,
        NOTE_CREATE, NOTE_CREATED, NOTE_UPDATE, NOTE_UPDATED,
        FILE_ANNOUNCE, FILE_SHARED, FILE_AVAILABLE,
        WAYPOINT_ADD, WAYPOINT_ADDED, WAYPOINT_UPDATE, WAYPOINT_UPDATED,
        WAYPOINT_REMOVE, WAYPOINT_REMOVED,
        AREA_ADD, AREA_UPDATE,
        ROUTE_ADD, ROUTE_UPDATE, ROUTE_AVAILABLE, ROUTE_LOST,
        OBSERVATION_ADD,
        STATUS_UPDATE, STATUS_CHANGED,
        PEER_SEEN, PEER_LOST,
        DELIVERY_UPDATE,
        NETWORK_SPLIT, NETWORK_REJOIN,
        STATE_MERGED,
        CONFLICT_RESOLVE,
    }


def compute_expires_at(policy: str, created_at: Optional[float] = None) -> Optional[float]:
    """
    Computes absolute expiration timestamp (epoch seconds) from policy and creation time.
    """
    if created_at is None:
        created_at = time.time()

    if policy == ExpiryPolicy.ONE_HOUR:
        return created_at + 3600.0
    elif policy == ExpiryPolicy.SIX_HOURS:
        return created_at + 21600.0
    elif policy == ExpiryPolicy.TWENTY_FOUR_HOURS:
        return created_at + 86400.0
    elif policy == ExpiryPolicy.SEVEN_DAYS:
        return created_at + 604800.0
    elif policy == ExpiryPolicy.TONIGHT:
        dt = datetime.fromtimestamp(created_at)
        # End of current day (23:59:59)
        end_of_day = datetime(dt.year, dt.month, dt.day, 23, 59, 59)
        target_ts = end_of_day.timestamp()
        # If created within 1 hour of midnight, extend to end of following day
        if target_ts - created_at < 3600:
            target_ts += 86400.0
        return target_ts
    elif policy == ExpiryPolicy.NEVER:
        return None
    return None


@dataclass
class Space:
    """
    A shared offline field workspace.
    Exists across participating peers without any central server or account.
    """
    space_id: str
    name: str
    description: str = ""
    created_at: float = field(default_factory=time.time)
    created_by: str = ""
    expiry_policy: str = ExpiryPolicy.NEVER
    expires_at: Optional[float] = None
    join_policy: str = JoinPolicy.OPEN_NEARBY
    lifecycle_state: str = LifecycleState.ACTIVE
    local_clock: int = 0
    state_digest: Optional[str] = None

    def __post_init__(self):
        if self.expires_at is None and self.expiry_policy != ExpiryPolicy.NEVER:
            self.expires_at = compute_expires_at(self.expiry_policy, self.created_at)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        if self.lifecycle_state == LifecycleState.EXPIRED:
            return True
        if self.expires_at is None:
            return False
        now = current_time if current_time is not None else time.time()
        return now >= self.expires_at

    def check_and_update_lifecycle(self, current_time: Optional[float] = None) -> str:
        """Evaluates expiry policy and updates lifecycle state if expired."""
        if self.lifecycle_state == LifecycleState.ACTIVE and self.is_expired(current_time):
            self.lifecycle_state = LifecycleState.EXPIRED
        return self.lifecycle_state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "space_id": self.space_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "expiry_policy": self.expiry_policy,
            "expires_at": self.expires_at,
            "join_policy": self.join_policy,
            "lifecycle_state": self.lifecycle_state,
            "local_clock": self.local_clock,
            "state_digest": self.state_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Space':
        return cls(
            space_id=data["space_id"],
            name=data["name"],
            description=data.get("description", ""),
            created_at=data.get("created_at", time.time()),
            created_by=data.get("created_by", ""),
            expiry_policy=data.get("expiry_policy", ExpiryPolicy.NEVER),
            expires_at=data.get("expires_at"),
            join_policy=data.get("join_policy", JoinPolicy.OPEN_NEARBY),
            lifecycle_state=data.get("lifecycle_state", LifecycleState.ACTIVE),
            local_clock=data.get("local_clock", 0),
            state_digest=data.get("state_digest"),
        )


@dataclass
class SpaceMember:
    """A participant in a Space."""
    space_id: str
    peer_id: str
    display_name: str
    role: str = MemberRole.MEMBER
    signing_key: Optional[str] = None
    joined_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "space_id": self.space_id,
            "peer_id": self.peer_id,
            "display_name": self.display_name,
            "role": self.role,
            "signing_key": self.signing_key,
            "joined_at": self.joined_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpaceMember':
        return cls(
            space_id=data["space_id"],
            peer_id=data["peer_id"],
            display_name=data.get("display_name", ""),
            role=data.get("role", MemberRole.MEMBER),
            signing_key=data.get("signing_key"),
            joined_at=data.get("joined_at", time.time()),
        )


@dataclass
class SpaceEvent:
    """
    An immutable, append-only signed record of a state transition in a Space.
    Ordered deterministically across peers via (logical_clock, timestamp, event_id).
    """
    event_id: str
    space_id: str
    author_id: str
    device_id: str = ""
    timestamp: float = field(default_factory=time.time)
    logical_clock: int = 1
    event_type: str = ""
    object_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    ref_event_ids: List[str] = field(default_factory=list)
    signature: str = ""
    author_pubkey: Optional[str] = None
    version: int = 1
    received_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "event_id": self.event_id,
            "space_id": self.space_id,
            "author_id": self.author_id,
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "logical_clock": self.logical_clock,
            "event_type": self.event_type,
            "object_id": self.object_id,
            "payload": self.payload,
            "ref_event_ids": list(self.ref_event_ids),
            "signature": self.signature,
            "author_pubkey": self.author_pubkey,
            "received_at": self.received_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpaceEvent':
        return cls(
            event_id=data["event_id"],
            space_id=data["space_id"],
            author_id=data["author_id"],
            device_id=data.get("device_id", ""),
            timestamp=data.get("timestamp", time.time()),
            logical_clock=data.get("logical_clock", 1),
            event_type=data.get("event_type", ""),
            object_id=data.get("object_id"),
            payload=data.get("payload", {}),
            ref_event_ids=data.get("ref_event_ids", []),
            signature=data.get("signature", ""),
            author_pubkey=data.get("author_pubkey"),
            version=data.get("version", 1),
            received_at=data.get("received_at", time.time()),
        )
