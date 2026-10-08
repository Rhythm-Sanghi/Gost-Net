"""
Ghost Net - Spaces Signed Event Envelope
Handles RFC 9562 UUIDv7 generation, canonical serialization, Ed25519 signing/verification,
and event structural validation.
"""

import os
import time
import json
import uuid
import base64
import threading
from typing import Dict, Any, List, Optional, Tuple, Union
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from .models import SpaceEvent, EventType

DOMAIN_SEPARATOR = b"gostnet_event_v1:"
MAX_EVENT_PAYLOAD_BYTES = 65536  # 64 KB limit per event payload

_v7_lock = threading.Lock()
_last_v7_timestamp_ms = 0
_v7_sequence = 0


def generate_uuidv7(timestamp_ms: Optional[int] = None) -> str:
    """
    Generates an RFC 9562 compliant UUIDv7 identifier.
    48-bit millisecond timestamp + 12-bit monotonic sequence/random + version 7 + variant 2 + 62-bit random.
    Guarantees time-ordered, collision-resistant identifiers offline without central coordination.
    """
    global _last_v7_timestamp_ms, _v7_sequence

    with _v7_lock:
        if timestamp_ms is None:
            now_ms = int(time.time() * 1000)
        else:
            now_ms = timestamp_ms

        if now_ms > _last_v7_timestamp_ms:
            _last_v7_timestamp_ms = now_ms
            # Start sequence at random 12-bit value or 0
            _v7_sequence = int.from_bytes(os.urandom(2), 'big') & 0x0FFF
        else:
            # Monotonic step within same millisecond
            _v7_sequence = (_v7_sequence + 1) & 0x0FFF

        ts_ms = _last_v7_timestamp_ms & 0xFFFFFFFFFFFF
        seq_12 = _v7_sequence & 0x0FFF

        # 62 bits of entropy for rand_b
        rand_b_bytes = os.urandom(8)
        rand_b_int = int.from_bytes(rand_b_bytes, 'big') & 0x3FFFFFFFFFFFFFFF

        # RFC 9562 UUIDv7 bit layout
        # Bits 0..47: unix_ts_ms (48 bits)
        # Bits 48..51: ver (4 bits = 0x7)
        # Bits 52..63: rand_a (12 bits = seq_12)
        # Bits 64..65: var (2 bits = 0b10 = 0x2)
        # Bits 66..127: rand_b (62 bits)
        ms_bits = ts_ms << 80
        ver_seq_bits = (0x7000 | seq_12) << 64
        var_rand_bits = 0x8000000000000000 | rand_b_int

        uuid_int = ms_bits | ver_seq_bits | var_rand_bits
        return str(uuid.UUID(int=uuid_int))


def canonical_serialize(data: Any) -> bytes:
    """
    Deterministically serializes arbitrary nested dict/list/primitives to canonical JSON.
    - Keys sorted recursively
    - Compact separators (',', ':')
    - UTF-8 encoded
    - ASCII safe
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True
    ).encode('utf-8')


def get_event_signing_bytes(event: SpaceEvent) -> bytes:
    """
    Extracts the canonical data payload of a SpaceEvent for digital signature calculation.
    Excludes the signature field itself and transport-local metadata (received_at).
    Prefixes with domain separation tag to prevent cross-protocol signature substitution.
    """
    canonical_dict = {
        "version": event.version,
        "event_id": event.event_id,
        "space_id": event.space_id,
        "author_id": event.author_id,
        "device_id": event.device_id,
        "timestamp": round(float(event.timestamp), 6),
        "logical_clock": int(event.logical_clock),
        "event_type": event.event_type,
        "object_id": event.object_id,
        "payload": event.payload,
        "ref_event_ids": list(event.ref_event_ids),
    }
    return DOMAIN_SEPARATOR + canonical_serialize(canonical_dict)


def sign_event(event: SpaceEvent, signer: Any) -> SpaceEvent:
    """
    Digitally signs a SpaceEvent with Ed25519.
    Signer can be:
    - CryptoManager instance (calls sign_data and get_signing_public_key_bytes)
    - ed25519.Ed25519PrivateKey instance
    Returns the event with signature (and author_pubkey if available) populated.
    """
    data_to_sign = get_event_signing_bytes(event)

    if hasattr(signer, 'sign_data'):
        # CryptoManager
        sig_bytes = signer.sign_data(data_to_sign)
        event.signature = base64.b64encode(sig_bytes).decode('ascii')
        if hasattr(signer, 'get_signing_public_key_bytes'):
            pub_bytes = signer.get_signing_public_key_bytes()
            event.author_pubkey = base64.b64encode(pub_bytes).decode('ascii')
    elif isinstance(signer, ed25519.Ed25519PrivateKey):
        sig_bytes = signer.sign(data_to_sign)
        event.signature = base64.b64encode(sig_bytes).decode('ascii')
        pub_bytes = signer.public_key().public_bytes_raw()
        event.author_pubkey = base64.b64encode(pub_bytes).decode('ascii')
    elif hasattr(signer, 'sign'):
        sig_bytes = signer.sign(data_to_sign)
        event.signature = base64.b64encode(sig_bytes).decode('ascii')
    else:
        raise ValueError(f"Unsupported signer type: {type(signer)}")

    return event


def verify_event_signature(event: SpaceEvent, public_key: Union[bytes, str, ed25519.Ed25519PublicKey]) -> bool:
    """
    Verifies the Ed25519 digital signature of a SpaceEvent.
    Public key can be:
    - 32 raw bytes
    - base64 encoded string
    - ed25519.Ed25519PublicKey instance
    Returns True if valid, False otherwise.
    """
    if not event.signature:
        return False

    try:
        sig_bytes = base64.b64decode(event.signature.encode('ascii'))
        if len(sig_bytes) != 64:
            return False

        if isinstance(public_key, ed25519.Ed25519PublicKey):
            pub_obj = public_key
        elif isinstance(public_key, str):
            pub_bytes = base64.b64decode(public_key.encode('ascii'))
            pub_obj = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        elif isinstance(public_key, (bytes, bytearray)):
            pub_obj = ed25519.Ed25519PublicKey.from_public_bytes(bytes(public_key))
        else:
            return False

        data_to_verify = get_event_signing_bytes(event)
        pub_obj.verify(sig_bytes, data_to_verify)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def validate_event(event: SpaceEvent, max_payload_bytes: int = MAX_EVENT_PAYLOAD_BYTES) -> Tuple[bool, str]:
    """
    Enforces strict structural and security validation rules on a SpaceEvent:
    - Version must be supported (v1)
    - Non-empty event_id, space_id, author_id
    - Logical clock >= 1
    - event_type must belong to EventType.ALL
    - Payload must be a dictionary
    - Payload size must not exceed limit (protects against storage exhaustion)
    - Reasonable timestamp
    - Signature present
    """
    if event.version != 1:
        return False, f"Unsupported event version: {event.version}"

    if not event.event_id or not isinstance(event.event_id, str):
        return False, "Missing or invalid event_id"

    # Validate UUID format
    try:
        u = uuid.UUID(event.event_id)
        if u.version != 7 and u.version != 4:
            return False, f"Invalid event UUID version: {u.version}"
    except Exception:
        return False, "event_id is not a valid UUID"

    if not event.space_id or not isinstance(event.space_id, str):
        return False, "Missing or invalid space_id"

    if not event.author_id or not isinstance(event.author_id, str):
        return False, "Missing or invalid author_id"

    if not isinstance(event.logical_clock, int) or event.logical_clock < 1:
        return False, f"Invalid logical_clock: {event.logical_clock} (must be int >= 1)"

    if not event.event_type or event.event_type not in EventType.ALL:
        return False, f"Unknown or invalid event_type: {event.event_type}"

    if not isinstance(event.payload, dict):
        return False, "Event payload must be a dictionary"

    # Enforce payload size limit
    try:
        payload_bytes = canonical_serialize(event.payload)
        if len(payload_bytes) > max_payload_bytes:
            return False, f"Payload size ({len(payload_bytes)} bytes) exceeds limit ({max_payload_bytes} bytes)"
    except Exception as e:
        return False, f"Payload serialization failed: {e}"

    if not isinstance(event.ref_event_ids, (list, tuple)):
        return False, "ref_event_ids must be a list"

    # Timestamp sanity: between 2024-01-01 and +1 day into future
    now = time.time()
    if not isinstance(event.timestamp, (int, float)):
        return False, "timestamp must be numeric"
    if event.timestamp < 1704067200:  # 2024-01-01
        return False, "Event timestamp is before supported epoch (2024)"
    if event.timestamp > now + 86400:  # > 24 hours into future
        return False, "Event timestamp is too far in the future (>24h)"

    if not event.signature:
        return False, "Event is unsigned (missing signature)"

    return True, ""
