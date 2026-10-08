"""
Ghost Net - Situation Feed & Event Journal Integration Tests
Validates the Event Journal, real action event emissions (peers, messages, waypoints),
restart persistence, and the Situation Feed presentation model.
"""

import os
import sys
import time
import tempfile
import pytest
from unittest.mock import MagicMock

# Ensure src/ is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from spaces.models import Space, SpaceEvent, EventType, ExpiryPolicy
from spaces.event_store import EventStore
from spaces.envelope import generate_uuidv7, sign_event
from security import CryptoManager
from database import PersistenceDatabase
from network import GhostEngine
from ui.screens.feed_screen import FeedScreen, FeedEventRow


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


def test_ghostengine_emits_mesh_events(temp_db_path):
    """Verifies that GhostEngine emits real signed events into the EventStore."""
    pdb = PersistenceDatabase(db_path=temp_db_path)
    crypto = CryptoManager()

    engine = GhostEngine(
        persistence_db=pdb,
        enable_storage=True,
        signing_private_key_bytes=crypto.get_signing_public_key_bytes()  # or private key
    )
    engine.crypto_manager = crypto

    # Track emitted events via callback
    emitted = []
    engine.on_mesh_event = lambda ev: emitted.append(ev)

    # 1. Peer discovery encounter
    engine._persist_peer("peer_riya", "Riya", discovery_type="Direct Wi-Fi")
    # 2. Sent message
    engine._persist_message("peer_riya", sender_type="sent", content_type="text", content="Meet at Gate B")
    # 3. Received message
    engine._persist_message("peer_riya", sender_type="received", content_type="text", content="Understood")

    # Verify events in EventStore
    store = pdb.get_event_store()
    events = store.get_events("spc_local_mesh")

    assert len(events) >= 3
    event_types = [e.event_type for e in events]
    assert EventType.PEER_SEEN in event_types
    assert EventType.MESSAGE_CREATED in event_types
    assert EventType.MESSAGE_RECEIVED in event_types

    # Ensure all events are cryptographically signed and protect message privacy
    for ev in events:
        assert ev.signature != ""
        assert ev.author_id in (engine.peer_id, "peer_riya")
        if ev.event_type in (EventType.MESSAGE_CREATED, EventType.MESSAGE_RECEIVED):
            assert "text" not in ev.payload
            assert "Meet at Gate B" not in str(ev.payload)
            assert "Understood" not in str(ev.payload)
            assert "size_bytes" in ev.payload


def test_event_journal_restart_persistence(temp_db_path):
    """Verifies that the event journal and state digests survive process restart."""
    # Session 1: Create Space and record events
    pdb1 = PersistenceDatabase(db_path=temp_db_path)
    store1 = pdb1.get_event_store()
    store1.create_space(Space(space_id="spc_fest", name="Campus Festival", expiry_policy=ExpiryPolicy.SIX_HOURS))

    crypto = CryptoManager()
    e1 = SpaceEvent(
        event_id=generate_uuidv7(1728362400000),
        space_id="spc_fest",
        author_id="peer_alice",
        timestamp=1728362400.0,
        logical_clock=1,
        event_type=EventType.WAYPOINT_ADDED,
        payload={"title": "Entrance A", "lat": 12.97, "lon": 77.59},
    )
    sign_event(e1, crypto)
    store1.store_event(e1, author_pubkey=crypto.get_signing_public_key_bytes())

    e2 = SpaceEvent(
        event_id=generate_uuidv7(1728362401000),
        space_id="spc_fest",
        author_id="peer_alice",
        timestamp=1728362401.0,
        logical_clock=2,
        event_type=EventType.NOTE_CREATED,
        payload={"title": "Safety Briefing", "content": "Keep radios on channel 3"},
    )
    sign_event(e2, crypto)
    store1.store_event(e2, author_pubkey=crypto.get_signing_public_key_bytes())

    digest1 = store1.compute_state_digest("spc_fest")
    count1 = store1.get_event_count("spc_fest")

    # Simulate shutdown
    pdb1.close()
    del pdb1
    del store1

    # Session 2: Reopen from disk
    pdb2 = PersistenceDatabase(db_path=temp_db_path)
    store2 = pdb2.get_event_store()

    sp_loaded = store2.get_space("spc_fest")
    assert sp_loaded is not None
    assert sp_loaded.name == "Campus Festival"
    assert sp_loaded.expiry_policy == ExpiryPolicy.SIX_HOURS

    events_loaded = store2.get_events("spc_fest")
    assert len(events_loaded) == count1
    assert [e.event_id for e in events_loaded] == [e1.event_id, e2.event_id]

    digest2 = store2.compute_state_digest("spc_fest")
    assert digest1 == digest2


def test_feed_screen_formatting():
    """Validates human-readable formatting of disparate mesh event types."""
    t_ref = 1728362400.0

    # Peer seen
    ev_peer = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_riya",
        timestamp=t_ref,
        logical_clock=1,
        event_type=EventType.PEER_SEEN,
        payload={"username": "Riya", "transport": "Direct Wi-Fi"},
    )
    f_peer = FeedScreen._format_event_row(ev_peer)
    assert f_peer["summary"] == "Riya became reachable"
    assert f_peer["metadata"] == "Direct Wi-Fi"

    # Peer lost
    ev_lost = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_arjun",
        timestamp=t_ref + 60,
        logical_clock=2,
        event_type=EventType.PEER_LOST,
        payload={"username": "Arjun"},
    )
    f_lost = FeedScreen._format_event_row(ev_lost)
    assert f_lost["summary"] == "Arjun no longer reachable"
    assert f_lost["metadata"] == "Offline"

    # Waypoint added
    ev_wp = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_sumit",
        timestamp=t_ref + 120,
        logical_clock=3,
        event_type=EventType.WAYPOINT_ADDED,
        payload={"title": "Water Point", "created_by": "Sumit"},
    )
    f_wp = FeedScreen._format_event_row(ev_wp)
    assert f_wp["summary"] == "Waypoint added: Water Point"
    assert "Sumit" in f_wp["detail"]
    assert f_wp["metadata"] == "Map"

    # Message delivered
    ev_msg = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_01",
        author_id="peer_riya",
        timestamp=t_ref + 180,
        logical_clock=4,
        event_type=EventType.MESSAGE_DELIVERED,
        payload={"text": "Route is clear", "sender": "Riya"},
    )
    f_msg = FeedScreen._format_event_row(ev_msg)
    assert "Message from Riya" in f_msg["summary"]
    assert f_msg["detail"] == "Route is clear"
    assert f_msg["metadata"] == "Delivered"


def test_space_isolation(temp_db_path):
    """Validates that events from different Spaces do not cross-contaminate."""
    pdb = PersistenceDatabase(db_path=temp_db_path)
    store = pdb.get_event_store()

    store.create_space(Space(space_id="spc_alpha", name="Team Alpha"))
    store.create_space(Space(space_id="spc_beta", name="Team Beta"))

    crypto = CryptoManager()

    # Event for Alpha
    ea = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_alpha",
        author_id="alice",
        logical_clock=1,
        event_type=EventType.MESSAGE_ADD,
        payload={"text": "Alpha briefing"},
    )
    sign_event(ea, crypto)
    store.store_event(ea, author_pubkey=crypto.get_signing_public_key_bytes())

    # Event for Beta
    eb = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_beta",
        author_id="bob",
        logical_clock=1,
        event_type=EventType.MESSAGE_ADD,
        payload={"text": "Beta briefing"},
    )
    sign_event(eb, crypto)
    store.store_event(eb, author_pubkey=crypto.get_signing_public_key_bytes())

    # Check isolation
    alpha_events = store.get_events("spc_alpha")
    beta_events = store.get_events("spc_beta")

    assert len(alpha_events) == 1
    assert alpha_events[0].event_id == ea.event_id
    assert len(beta_events) == 1
    assert beta_events[0].event_id == eb.event_id


def test_message_privacy_no_plaintext_in_journal(temp_db_path):
    """Verifies that the event journal NEVER stores plaintext message bodies or previews."""
    pdb = PersistenceDatabase(db_path=temp_db_path)
    crypto = CryptoManager()
    engine = GhostEngine(
        persistence_db=pdb,
        enable_storage=True,
        signing_private_key_bytes=crypto.get_signing_public_key_bytes()
    )
    engine.crypto_manager = crypto

    secret_outgoing = "CONFIDENTIAL_OPERATIONAL_ORDER_77"
    secret_incoming = "TOP_SECRET_COORDINATES_55_33"

    engine._persist_message("peer_bravo", sender_type="sent", content_type="text", content=secret_outgoing)
    engine._persist_message("peer_bravo", sender_type="received", content_type="text", content=secret_incoming)

    store = pdb.get_event_store()
    events = store.get_events("spc_local_mesh")

    for ev in events:
        payload_str = str(ev.payload)
        assert secret_outgoing not in payload_str
        assert secret_incoming not in payload_str
        assert "text" not in ev.payload
        assert "body" not in ev.payload
        assert "preview" not in ev.payload

    # Wait briefly for async persist queue worker to flush
    time.sleep(0.3)

    # However, the authorized message store SHOULD contain the actual text
    loaded_msgs = pdb.get_messages_for_peer("peer_bravo")
    contents = [m["content"] for m in loaded_msgs]
    assert secret_outgoing in contents
    assert secret_incoming in contents


def test_atomic_concurrent_deduplication(temp_db_path):
    """Verifies atomic deduplication under multi-threaded concurrency (20 threads)."""
    import threading
    pdb = PersistenceDatabase(db_path=temp_db_path)
    store = pdb.get_event_store()
    store.create_space(Space(space_id="spc_concur", name="Concurrency Test"))

    crypto = CryptoManager()
    target_event = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_concur",
        author_id="peer_alice",
        timestamp=time.time(),
        logical_clock=1,
        event_type=EventType.STATUS_CHANGED,
        payload={"status": "ACTIVE"},
    )
    sign_event(target_event, crypto)
    pubkey = crypto.get_signing_public_key_bytes()

    results = []

    def insert_worker():
        ok, res = store.store_event(target_event, author_pubkey=pubkey)
        results.append((ok, res))

    threads = [threading.Thread(target=insert_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one thread should succeed, all others must be DUPLICATE
    stored_count = sum(1 for ok, res in results if ok and res == "STORED")
    duplicate_count = sum(1 for ok, res in results if not ok and res == "DUPLICATE")

    assert stored_count == 1
    assert duplicate_count == 19
    assert store.get_event_count("spc_concur") == 1


def test_restart_clock_monotonicity(temp_db_path):
    """Verifies that Lamport logical clock monotonicity survives restarts even with stale space cache."""
    pdb = PersistenceDatabase(db_path=temp_db_path)
    store = pdb.get_event_store()
    store.create_space(Space(space_id="spc_clock", name="Clock Test"))

    crypto = CryptoManager()
    pubkey = crypto.get_signing_public_key_bytes()

    for i in range(1, 6):
        ev = SpaceEvent(
            event_id=generate_uuidv7(),
            space_id="spc_clock",
            author_id="peer_alice",
            logical_clock=i,
            event_type=EventType.NOTE_CREATED,
            payload={"index": i},
        )
        sign_event(ev, crypto)
        store.store_event(ev, author_pubkey=pubkey)

    pdb.close()
    del pdb
    del store

    # Reopen database
    pdb2 = PersistenceDatabase(db_path=temp_db_path)
    store2 = pdb2.get_event_store()

    # Next event with lower proposed clock should advance strictly monotonically
    ev_new = SpaceEvent(
        event_id=generate_uuidv7(),
        space_id="spc_clock",
        author_id="peer_alice",
        logical_clock=1,  # Lower proposed clock
        event_type=EventType.NOTE_CREATED,
        payload={"index": 6},
    )
    sign_event(ev_new, crypto)
    ok, res = store2.store_event(ev_new, author_pubkey=pubkey)
    assert ok is True

    sp_after = store2.get_space("spc_clock")
    # Previous max clock was 5; new clock must be at least 6
    assert sp_after.local_clock >= 6


def test_feed_query_boundedness(temp_db_path):
    """Verifies that get_events bounds queries to prevent runaway memory usage."""
    pdb = PersistenceDatabase(db_path=temp_db_path)
    store = pdb.get_event_store()
    store.create_space(Space(space_id="spc_bulk", name="Bulk Test"))

    crypto = CryptoManager()
    pubkey = crypto.get_signing_public_key_bytes()

    # Insert 600 events
    conn = store._connect()
    try:
        cur = conn.cursor()
        for i in range(600):
            ev_id = generate_uuidv7()
            cur.execute('''
                INSERT INTO space_events (
                    event_id, space_id, author_id, device_id, timestamp,
                    logical_clock, event_type, object_id, payload_json,
                    ref_ids_json, signature, author_pubkey, version, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ev_id, "spc_bulk", "peer_alice", "dev_1", 1000.0 + i, i,
                  EventType.STATUS_UPDATE, None, "{}", "[]", "sig", None, 1, 1000.0 + i))
        conn.commit()
    finally:
        conn.close()

    assert store.get_event_count("spc_bulk") == 600

    # Default query should return bounded limit (200)
    events_default = store.get_events("spc_bulk")
    assert len(events_default) == 200

    # Explicit unbounded request or excessive limit should be capped at max (500)
    events_large = store.get_events("spc_bulk", limit=1000)
    assert len(events_large) == 500

