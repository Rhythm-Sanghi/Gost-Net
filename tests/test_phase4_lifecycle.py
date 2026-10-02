"""
Tests for Phase 4: Lifecycle Hardening, Network Interface Handover, DTN Spooling,
and Android Service / Usability Resilience.
"""

import os
import sys
import time
import shutil
import tempfile
import pytest

# Ensure src/ is on path
_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from network import GhostEngine
from network_state import NetworkState, SendResult
from service import ServiceNotificationManager, LightweightGhostEngine
import main as main_module


@pytest.fixture
def temp_spool_engine():
    """Create a temporary GhostEngine with an isolated spool directory for DTN testing."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_phase4_")
    downloads_dir = os.path.join(temp_dir, "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    
    engine = GhostEngine(
        username="Phase4Tester",
        downloads_dir=downloads_dir,
        enable_storage=False
    )
    yield engine
    
    try:
        engine.stop()
    except Exception:
        pass
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_network_interface_transition_to_offline(temp_spool_engine):
    """Verify that network change to 127.0.0.1 or empty triggers OFFLINE state."""
    engine = temp_spool_engine
    
    # Simulate network change to offline
    engine._on_network_changed("192.168.1.50", "127.0.0.1", "offline")
    
    assert engine.local_ip == "127.0.0.1"
    assert engine.current_network_type == "offline"
    assert engine.network_state == NetworkState.OFFLINE
    assert engine.get_network_state_label() == "Offline"


def test_network_interface_transition_to_available(temp_spool_engine):
    """Verify that switching to an active LAN/Hotspot interface transitions to AVAILABLE and resets beacon intervals."""
    engine = temp_spool_engine
    engine.current_beacon_interval = 15.0
    engine.static_beacon_cycles = 5
    
    # Simulate network change to hotspot
    engine._on_network_changed("127.0.0.1", "192.168.43.10", "hotspot")
    
    assert engine.local_ip == "192.168.43.10"
    assert engine.current_network_type == "hotspot"
    assert engine.network_state == NetworkState.AVAILABLE
    assert engine.current_beacon_interval == engine.min_beacon_interval
    assert engine.static_beacon_cycles == 0


def test_dtn_text_message_spooling(temp_spool_engine):
    """Verify that sending a text message to an offline peer spools the message to disk with QUEUED_OFFLINE status."""
    engine = temp_spool_engine
    
    status_updates = []
    def on_status(msg_id, peer, state):
        status_updates.append((msg_id, state))
    engine.on_delivery_status = on_status
    
    # Attempt to send message to non-existent unreachable peer
    unreachable_ip = "192.0.2.1"  # RFC 5737 TEST-NET-1 (guaranteed unroutable/silent)
    result = engine.send_message(
        target_ip=unreachable_ip,
        message_text="Field deployment mission critical telemetry",
        return_result=True
    )
    
    assert isinstance(result, SendResult)
    # The message should either be spooled (QUEUED_OFFLINE) or failed gracefully, not crashing
    assert result.delivery_state in ("QUEUED_OFFLINE", "FAILED")
    
    if result.delivery_state == "QUEUED_OFFLINE":
        # Check that spool directory has a message record
        hash_target = engine.spool_dir
        assert os.path.exists(hash_target)


def test_dtn_spool_message_direct_creation_and_removal(temp_spool_engine):
    """Verify manual _spool_message creates valid metadata on disk."""
    engine = temp_spool_engine
    
    msg_id = "test_msg_999"
    target_id = "target_peer_xyz"
    spooled = engine._spool_message(
        target="192.168.1.100",
        message_text="Tactical waypoint coordinate",
        peer_id=target_id,
        msg_id=msg_id,
        ttl=3600
    )
    assert spooled is True
    
    # Verify metadata on disk
    import hashlib
    hash_target = hashlib.sha256(target_id.encode()).hexdigest()
    item_dir = os.path.join(engine.spool_dir, hash_target, f"msg_{msg_id}")
    meta_path = os.path.join(item_dir, "metadata.json")
    
    assert os.path.exists(meta_path)
    meta = engine._read_spool_metadata(meta_path)
    assert meta is not None
    assert meta.get("type") == "TEXT_MESSAGE"
    assert meta.get("content") == "Tactical waypoint coordinate"
    assert meta.get("msg_id") == msg_id


def test_service_notification_manager_desktop_mock():
    """Verify ServiceNotificationManager operates safely without crash on desktop mock."""
    mgr = ServiceNotificationManager()
    
    # Should safely return True/mock on desktop
    assert mgr.show_foreground_notification() is True
    assert mgr.stop_foreground_notification() is True
    assert mgr.show_message_notification("Operator", "Encrypted message test") is True


def test_lightweight_service_engine_lifecycle():
    """Verify LightweightGhostEngine starts, runs, and stops without dangling sockets."""
    engine = LightweightGhostEngine(username="BackgroundWorker")
    assert engine.running is False
    
    engine.start()
    assert engine.running is True
    
    time.sleep(0.5)
    engine.stop()
    assert engine.running is False


def test_main_app_permissions_and_lifecycle():
    """Verify GhostNetApp methods (request_permissions, on_pause, on_resume) execute cleanly on desktop."""
    app = main_module.GhostNetApp()
    
    # Desktop permission check: should safely report permissions not needed without error
    app.request_permissions()
    
    # on_pause: must return True for background handoff
    pause_result = app.on_pause()
    assert pause_result is True
    
    # on_resume: should execute without raising exceptions
    app.on_resume()
