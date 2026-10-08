"""
Ghost Net - Slice 1 Automated Test Suite
Validates the offline shared field workspace Space model, signed event envelopes,
and the local event store subsystem.
"""

import os
import sys
import time
import tempfile
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

# Ensure src/ is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from spaces.models import (
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
from spaces.envelope import (
    generate_uuidv7,
    canonical_serialize,
    get_event_signing_bytes,
    sign_event,
    verify_event_signature,
    validate_event,
)
from spaces.event_store import EventStore
from security import CryptoManager
from database import PersistenceDatabase


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        if os.path.exists(path):
            os.remove(path)
        wal = path + "-wal"
        shm = path + "-shm"
        if os.path.exists(wal):
            os.remove(wal)
        if os.path.exists(shm):
            os.remove(shm)
    except Exception:
        pass


@pytest.fixture
def crypto_alice():
    return CryptoManager()


@pytest.fixture
def crypto_bob():
    return CryptoManager()


# =============================================================================
# 1. SPACE DATA MODEL TESTS
# =============================================================================

def test_space_creation_defaults():
    sp = Space(
        space_id="spc_campus_fest_01",
        name="Campus Fest",
        created_by="peer_alice",
    )
    assert sp.space_id == "spc_campus_fest_01"
    assert sp.name == "Campus Fest"
    assert sp.expiry_policy == ExpiryPolicy.NEVER
    assert sp.expires_at is None
    assert sp.join_policy == JoinPolicy.OPEN_NEARBY
    assert sp.lifecycle_state == LifecycleState.ACTIVE
    assert sp.local_clock == 0
    assert not sp.is_expired()


def test_space_expiry_policies():
    t0 = 1728362400.0  # reference time

    # 1 hour
    sp_1h = Space(space_id="s1", name="S1", created_at=t0, expiry_policy=ExpiryPolicy.ONE_HOUR)
    assert sp_1h.expires_at == t0 + 3600.0
    assert not sp_1h.is_expired(t0 + 1000)
    assert sp_1h.is_expired(t0 + 3601)

    # 6 hours
    sp_6h = Space(space_id="s6", name="S6", created_at=t0, expiry_policy=ExpiryPolicy.SIX_HOURS)
    assert sp_6h.expires_at == t0 + 21600.0

    # 24 hours
    sp_24h = Space(space_id="s24", name="S24", created_at=t0, expiry_policy=ExpiryPolicy.TWENTY_FOUR_HOURS)
    assert sp_24h.expires_at == t0 + 86400.0

    # 7 days
    sp_7d = Space(space_id="s7d", name="S7D", created_at=t0, expiry_policy=ExpiryPolicy.SEVEN_DAYS)
    assert sp_7d.expires_at == t0 + 604800.0

    # Tonight
    exp_tonight = compute_expires_at(ExpiryPolicy.TONIGHT, created_at=t0)
    assert exp_tonight is not None
    assert exp_tonight > t0

    # Lifecycle state transition
    assert sp_1h.lifecycle_state == LifecycleState.ACTIVE
    new_state = sp_1h.check_and_update_lifecycle(t0 + 4000)
    assert new_state == LifecycleState.EXPIRED
    assert sp_1h.lifecycle_state == LifecycleState.EXPIRED


def test_space_member_model():
    mem = SpaceMember(
        space_id="spc_01",
        peer_id="peer_alice",
        display_name="Alice",
        role=MemberRole.MODERATOR,
        signing_key="pubkey_alice_b64"
    )
    d = mem.to_dict()
    assert d["role"] == MemberRole.MODERATOR
    rebuilt = SpaceMember.from_dict(d)
    assert rebuilt.peer_id == "peer_alice"
    assert rebuilt.role == MemberRole.MODERATOR


# =============================================================================
# 2. SIGNED EVENT ENVELOPE TESTS
# =============================================================================

def test_uuidv7_generation_properties():
    ids = [generate_uuidv7() for _ in range(100)]
    # All must be unique
    assert len(set(ids)) == 100

    # Check UUID version 7 and variant
    import uuid
    for uid_str in ids[:10]:
        u = uuid.UUID(uid_str)
        assert u.version == 7
        assert u.variant == uuid.RFC_4122

    # Natural monotonic ordering
    assert sorted(ids) == ids


def test_canonical_serialization_determinism():
    d1 = {"z": 1, "a": {"b": 2, "a": 1}, "m": [3, 2, 1]}
    d2 = {"a": {"a": 1, "b": 2}, "m": [3, 2, 1], "z": 1}
    assert canonical_serialize(d1) == canonical_serialize(d2)


def test_event_signing_and_verification(crypto_alice, crypto_bob):
    ev = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_alice",
        logical_clock=1,
        event_type=EventType.NOTE_CREATE,
        object_id="note_001",
        payload={"title": "Field Log", "content": "Initial survey started."},
    )

    signed_ev = sign_event(ev, crypto_alice)
    assert signed_ev.signature != ""
    assert signed_ev.author_pubkey is not None

    # Valid signature check with Alice's public key
    alice_pub = crypto_alice.get_signing_public_key_bytes()
    assert verify_event_signature(signed_ev, alice_pub) is True

    # Verification fails with Bob's public key
    bob_pub = crypto_bob.get_signing_public_key_bytes()
    assert verify_event_signature(signed_ev, bob_pub) is False


def test_tamper_detection(crypto_alice):
    ev = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_alice",
        logical_clock=1,
        event_type=EventType.WAYPOINT_ADD,
        object_id="wp_001",
        payload={"lat": 12.9716, "lon": 77.5946, "name": "Basecamp"},
    )
    sign_event(ev, crypto_alice)
    alice_pub = crypto_alice.get_signing_public_key_bytes()

    assert verify_event_signature(ev, alice_pub) is True

    # Tamper payload
    ev.payload["name"] = "Compromised Basecamp"
    assert verify_event_signature(ev, alice_pub) is False

    # Restore payload, tamper clock
    ev.payload["name"] = "Basecamp"
    ev.logical_clock = 999
    assert verify_event_signature(ev, alice_pub) is False

    # Restore clock, tamper author
    ev.logical_clock = 1
    ev.author_id = "peer_eve"
    assert verify_event_signature(ev, alice_pub) is False


def test_event_validation_rules(crypto_alice):
    # Valid event
    ev = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_alice",
        logical_clock=1,
        event_type=EventType.MESSAGE_ADD,
        payload={"text": "Hello field team"},
    )
    sign_event(ev, crypto_alice)

    valid, reason = validate_event(ev)
    assert valid is True
    assert reason == ""

    # Invalid event type
    bad_type = SpaceEvent.from_dict(ev.to_dict())
    bad_type.event_type = "UNRECOGNIZED_ACTION"
    valid, _ = validate_event(bad_type)
    assert valid is False

    # Invalid logical clock (< 1)
    bad_clock = SpaceEvent.from_dict(ev.to_dict())
    bad_clock.logical_clock = 0
    valid, _ = validate_event(bad_clock)
    assert valid is False

    # Oversized payload (> 64KB)
    huge_ev = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_alice",
        logical_clock=1,
        event_type=EventType.MESSAGE_ADD,
        payload={"big_data": "X" * 70000},
    )
    sign_event(huge_ev, crypto_alice)
    valid, reason = validate_event(huge_ev)
    assert valid is False
    assert "exceeds limit" in reason


# =============================================================================
# 3. LOCAL EVENT STORE & DEDUPLICATION TESTS
# =============================================================================

def test_store_space_lifecycle(temp_db_path):
    store = EventStore(temp_db_path)

    sp = Space(space_id="spc_survey", name="Field Survey", created_by="peer_alice")
    assert store.create_space(sp) is True
    # Duplicate creation fails
    assert store.create_space(sp) is False

    fetched = store.get_space("spc_survey")
    assert fetched is not None
    assert fetched.name == "Field Survey"

    spaces = store.list_spaces()
    assert len(spaces) == 1
    assert spaces[0].space_id == "spc_survey"

    # Update lifecycle
    assert store.update_space_lifecycle("spc_survey", LifecycleState.ARCHIVED) is True
    assert store.get_space("spc_survey").lifecycle_state == LifecycleState.ARCHIVED


def test_member_management(temp_db_path):
    store = EventStore(temp_db_path)
    store.create_space(Space(space_id="spc_01", name="Space 1"))

    m1 = SpaceMember(space_id="spc_01", peer_id="p1", display_name="Alice", role=MemberRole.MODERATOR)
    m2 = SpaceMember(space_id="spc_01", peer_id="p2", display_name="Bob", role=MemberRole.MEMBER)

    assert store.add_member(m1) is True
    assert store.add_member(m2) is True

    members = store.get_members("spc_01")
    assert len(members) == 2
    assert {m.peer_id for m in members} == {"p1", "p2"}

    assert store.remove_member("spc_01", "p2") is True
    assert len(store.get_members("spc_01")) == 1


def test_idempotent_deduplication(temp_db_path, crypto_alice):
    store = EventStore(temp_db_path)
    store.create_space(Space(space_id="spc_01", name="Space 1"))

    ev = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_alice",
        logical_clock=1,
        event_type=EventType.NOTE_CREATE,
        payload={"text": "Log 1"},
    )
    sign_event(ev, crypto_alice)

    # First insert: successful
    ok, res = store.store_event(ev, author_pubkey=crypto_alice.get_signing_public_key_bytes())
    assert ok is True
    assert res == "STORED"
    assert store.get_event_count("spc_01") == 1

    # Repeat 50 times: idempotent deduplication returns DUPLICATE without creating extra records
    for _ in range(50):
        ok, res = store.store_event(ev, author_pubkey=crypto_alice.get_signing_public_key_bytes())
        assert ok is False
        assert res == "DUPLICATE"

    assert store.get_event_count("spc_01") == 1


def test_deterministic_ordering_and_out_of_order(temp_db_path, crypto_alice):
    store = EventStore(temp_db_path)
    store.create_space(Space(space_id="spc_01", name="Space 1"))
    pub = crypto_alice.get_signing_public_key_bytes()

    # Create 3 events with different clocks and timestamps
    e1 = SpaceEvent(
        event_id=generate_uuidv7(1728362400000),
        space_id="spc_01",
        author_id="peer_alice",
        timestamp=1728362400.0,
        logical_clock=1,
        event_type=EventType.NOTE_CREATE,
        object_id="note_A",
        payload={"text": "V1"},
    )
    sign_event(e1, crypto_alice)

    e2 = SpaceEvent(
        event_id=generate_uuidv7(1728362401000),
        space_id="spc_01",
        author_id="peer_alice",
        timestamp=1728362401.0,
        logical_clock=2,
        event_type=EventType.NOTE_UPDATE,
        object_id="note_A",
        payload={"text": "V2"},
        ref_event_ids=[e1.event_id],
    )
    sign_event(e2, crypto_alice)

    e3 = SpaceEvent(
        event_id=generate_uuidv7(1728362402000),
        space_id="spc_01",
        author_id="peer_alice",
        timestamp=1728362402.0,
        logical_clock=3,
        event_type=EventType.NOTE_UPDATE,
        object_id="note_A",
        payload={"text": "V3"},
        ref_event_ids=[e2.event_id],
    )
    sign_event(e3, crypto_alice)

    # Insert out of order: e3 first, then e1, then e2
    store.store_event(e3, author_pubkey=pub)
    assert store.get_unresolved_dependencies("spc_01") == {e3.event_id: [e2.event_id]}

    store.store_event(e1, author_pubkey=pub)
    assert store.get_unresolved_dependencies("spc_01") == {e3.event_id: [e2.event_id]}

    store.store_event(e2, author_pubkey=pub)
    # Now all references are resolved!
    assert store.get_unresolved_dependencies("spc_01") == {}

    # Query all events: must be sorted deterministically e1 -> e2 -> e3
    events = store.get_events("spc_01")
    assert [e.event_id for e in events] == [e1.event_id, e2.event_id, e3.event_id]

    # Object history
    obj_events = store.get_events_for_object("spc_01", "note_A")
    assert len(obj_events) == 3


def test_deterministic_state_digest(temp_db_path, crypto_alice, crypto_bob):
    # Two independent stores with identical events inserted in different order
    fd2, path2 = tempfile.mkstemp(suffix=".db")
    os.close(fd2)

    try:
        store1 = EventStore(temp_db_path)
        store2 = EventStore(path2)

        store1.create_space(Space(space_id="spc_sync", name="Sync Space"))
        store2.create_space(Space(space_id="spc_sync", name="Sync Space"))

        alice_pub = crypto_alice.get_signing_public_key_bytes()
        bob_pub = crypto_bob.get_signing_public_key_bytes()

        # Alice creates note
        ea = SpaceEvent(
            event_id=generate_uuidv7(1728362400000),
            space_id="spc_sync",
            author_id="alice",
            logical_clock=1,
            event_type=EventType.NOTE_CREATE,
            payload={"text": "Hello from Alice"},
        )
        sign_event(ea, crypto_alice)

        # Bob adds waypoint
        eb = SpaceEvent(
            event_id=generate_uuidv7(1728362401000),
            space_id="spc_sync",
            author_id="bob",
            logical_clock=2,
            event_type=EventType.WAYPOINT_ADD,
            payload={"name": "WP1", "lat": 10.0, "lon": 20.0},
        )
        sign_event(eb, crypto_bob)

        # store1 receives ea then eb
        store1.store_event(ea, author_pubkey=alice_pub)
        store1.store_event(eb, author_pubkey=bob_pub)

        # store2 receives eb then ea (reverse order)
        store2.store_event(eb, author_pubkey=bob_pub)
        store2.store_event(ea, author_pubkey=alice_pub)

        # Both stores must compute the EXACT SAME state digest!
        d1 = store1.compute_state_digest("spc_sync")
        d2 = store2.compute_state_digest("spc_sync")

        assert len(d1) == 64
        assert d1 == d2

        # Space record state_digest is also updated automatically
        assert store1.get_space("spc_sync").state_digest == d1
        assert store2.get_space("spc_sync").state_digest == d2

        # If a new event is added to store1 only, digests differ
        ec = SpaceEvent(
            event_id=generate_uuidv7(1728362402000),
            space_id="spc_sync",
            author_id="alice",
            logical_clock=3,
            event_type=EventType.MESSAGE_ADD,
            payload={"text": "New msg"},
        )
        sign_event(ec, crypto_alice)
        store1.store_event(ec, author_pubkey=alice_pub)

        assert store1.compute_state_digest("spc_sync") != store2.compute_state_digest("spc_sync")

    finally:
        try:
            if os.path.exists(path2):
                os.remove(path2)
        except Exception:
            pass


def test_persistence_database_integration(temp_db_path, crypto_alice):
    # Ensure PersistenceDatabase initializes EventStore cleanly without breaking legacy tables
    pdb = PersistenceDatabase(db_path=temp_db_path)
    store = pdb.get_event_store()
    assert store is not None

    # Create a space and store an event via pdb's event_store
    sp = Space(space_id="spc_legacy_coexist", name="Coexistence Space")
    assert store.create_space(sp) is True

    ev = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_legacy_coexist",
        author_id="peer_alice",
        logical_clock=1,
        event_type=EventType.STATUS_UPDATE,
        payload={"status": "Online and surveying"},
    )
    sign_event(ev, crypto_alice)
    ok, res = store.store_event(ev, author_pubkey=crypto_alice.get_signing_public_key_bytes())
    assert ok is True
    assert res == "STORED"

    # Legacy tables still function normally
    pdb.save_peer("p_legacy_01", "Device1", "AA:BB:CC:DD:EE:FF", "WIFI")
    peer = pdb.get_peer("p_legacy_01")
    assert peer is not None
    assert peer["device_name"] == "Device1"
