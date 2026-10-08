"""
Ghost Net - Spaces Subsystem
Offline shared field workspace model, signed event envelopes, and local event store.
"""

from .models import (
    Space,
    SpaceMember,
    SpaceEvent,
    ExpiryPolicy,
    JoinPolicy,
    LifecycleState,
    MemberRole,
    EventType,
    compute_expires_at,
)
from .envelope import (
    generate_uuidv7,
    canonical_serialize,
    sign_event,
    verify_event_signature,
    validate_event,
)
from .event_store import EventStore

__all__ = [
    'Space',
    'SpaceMember',
    'SpaceEvent',
    'ExpiryPolicy',
    'JoinPolicy',
    'LifecycleState',
    'MemberRole',
    'EventType',
    'compute_expires_at',
    'generate_uuidv7',
    'canonical_serialize',
    'sign_event',
    'verify_event_signature',
    'validate_event',
    'EventStore',
]
