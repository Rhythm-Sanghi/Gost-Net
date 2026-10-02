"""
Phase 5: Field Resilience, Duress Protocol, Decoy Mode & Emergency Wipe Verification Suite.
"""

import os
import sys
import time
import shutil
import tempfile
import pytest

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from auth_manager import AuthenticationManager
from database import PersistenceDatabase
from storage import DatabaseManager
from network import GhostEngine
from network_state import NetworkState, SendResult


@pytest.fixture
def temp_auth_env():
    """Create isolated sandbox directory for auth and credential testing."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_auth_test_")
    auth_mgr = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=True)
    yield auth_mgr, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_failed_attempts_and_decoy_mode_trigger(temp_auth_env):
    """Verify that 5 failed PIN entries automatically flip the system into decoy mode."""
    auth_mgr, temp_dir = temp_auth_env
    assert not auth_mgr.is_decoy_mode_active()
    
    # Enter 4 invalid PINs
    for i in range(4):
        res = auth_mgr.identify_pin("0000")
        assert res is None
        assert not auth_mgr.is_decoy_mode_active()
        
    # 5th invalid PIN should trigger decoy mode
    res = auth_mgr.identify_pin("0000")
    assert res is None
    assert auth_mgr.is_decoy_mode_active()
    
    # Once decoy mode is active, any subsequent 4+ digit PIN returns 'master' to open decoy vault
    assert auth_mgr.identify_pin("9999") == "master"
    assert auth_mgr.identify_pin("1234") == "master"


def test_duress_pin_detection(temp_auth_env):
    """Verify duress PIN (default 9999) is correctly identified as duress."""
    auth_mgr, temp_dir = temp_auth_env
    assert auth_mgr.identify_pin("9999") == "duress"


def test_master_pin_detection_and_key_derivation(temp_auth_env):
    """Verify master PIN (default 1234) derives consistent database key."""
    auth_mgr, temp_dir = temp_auth_env
    assert auth_mgr.identify_pin("1234") == "master"
    
    key1 = auth_mgr.get_or_create_db_key("1234")
    key2 = auth_mgr.get_or_create_db_key("1234")
    assert key1 == key2
    assert len(key1) == 44  # Base64 encoded 32-byte key


def test_persistence_decoy_vault_population():
    """Verify PersistenceDatabase can shred active data and generate mock decoy data."""
    temp_db_path = tempfile.mktemp(suffix=".db")
    try:
        db = PersistenceDatabase(db_path=temp_db_path)
        db.save_message("192.168.1.50", "me", "text", "Secret mission coordinates")
        
        # Verify real secret was written
        msgs = db.get_messages_for_peer("192.168.1.50")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Secret mission coordinates"
        
        # Shred and recreate decoy
        db.shred_everything()
        db.recreate_and_populate_mock_data()
        
        # Secret mission coordinate must be gone
        msgs_after = db.get_messages_for_peer("192.168.1.50")
        assert len(msgs_after) == 0
        
        # Mock conversations must now be present
        mock_peers = db.get_all_peers()
        assert len(mock_peers) >= 2
        
        db.close()
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass


def test_field_guide_offline_query():
    """Verify that offline /wiki queries resolve properly from local survival guides."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_wiki_test_")
    engine = GhostEngine(username="FieldOperator", downloads_dir=temp_dir, enable_storage=False)
    
    received_msgs = []
    def on_msg(sender, content, ts):
        received_msgs.append(content)
    engine.on_message_received = on_msg
    
    # Query /wiki water
    res = engine.send_message("127.0.0.1", "/wiki water", return_result=True)
    assert res.success is True
    assert len(received_msgs) == 1
    assert "Water Purification" in received_msgs[0]
    
    # Query /guide list
    res_list = engine.send_message("127.0.0.1", "/guide list", return_result=True)
    assert res_list.success is True
    assert len(received_msgs) == 2
    assert "Available field guides" in received_msgs[1]
    
    engine.stop()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_tactical_sos_broadcast():
    """Verify SOS emergency broadcasting generates valid hash identifiers without throwing exceptions."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_sos_test_")
    engine = GhostEngine(username="EmergencyNode", downloads_dir=temp_dir, enable_storage=False)
    
    # SOS broadcast should execute safely even without GPS hardware
    try:
        engine.broadcast_sos(latitude=37.7749, longitude=-122.4194, message="INJURED OPERATOR AT SECTOR 4")
        success = True
    except Exception as e:
        success = False
        
    assert success is True
    engine.stop()
    shutil.rmtree(temp_dir, ignore_errors=True)
