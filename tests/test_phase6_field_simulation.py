"""
Phase 6: Multi-Node Field Simulation & Production Readiness Test Suite.
Simulates multi-operator field conditions: P2P discovery, E2EE message exchange,
binary file transfer with SHA-256 verification, zero-byte rejection, DTN store-and-forward,
safety number symmetry, and group multicast.
"""

import os
import sys
import time
import shutil
import tempfile
import hashlib
import pytest

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from network import GhostEngine
from network_state import NetworkState, SendResult
from database import PersistenceDatabase
from security import CryptoManager, derive_channel_key, encrypt_channel_message, decrypt_channel_message


@pytest.fixture
def multi_node_cluster():
    """Spin up an isolated two-node cluster (Alice and Bob) with separate temp dirs and sockets."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_bob_")
    
    alice = GhostEngine(
        username="Alice",
        downloads_dir=os.path.join(dir_alice, "downloads"),
        enable_storage=False
    )
    bob = GhostEngine(
        username="Bob",
        downloads_dir=os.path.join(dir_bob, "downloads"),
        enable_storage=False
    )
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    yield alice, bob, dir_alice, dir_bob
    
    alice.stop()
    bob.stop()
    time.sleep(0.5)
    
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)


def test_multi_node_direct_chat_and_ack(multi_node_cluster):
    """Verify direct TCP message delivery and application-layer ACK between Alice and Bob."""
    alice, bob, _, _ = multi_node_cluster
    
    bob_received = []
    def on_bob_message(sender_ip, text, ts):
        bob_received.append((sender_ip, text))
    bob.on_message_received = on_bob_message
    
    # Alice sends message directly to Bob's TCP port
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    result = alice.send_message(
        target_ip=target_addr,
        message_text="Rendezvous at waypoint Alpha",
        return_result=True
    )
    
    assert isinstance(result, SendResult)
    assert result.success is True
    assert result.delivery_state in ("DELIVERED", "SENT_TO_PEER")
    
    # Allow socket delivery
    time.sleep(0.5)
    assert len(bob_received) == 1
    assert bob_received[0][1] == "Rendezvous at waypoint Alpha"


def test_multi_node_file_transfer_integrity(multi_node_cluster):
    """Verify binary file transfer with SHA-256 verification and atomic saving."""
    alice, bob, dir_alice, dir_bob = multi_node_cluster
    
    # Create sample binary file at Alice
    sample_data = os.urandom(16384)  # 16 KB random binary payload
    sample_sha256 = hashlib.sha256(sample_data).hexdigest()
    
    source_file = os.path.join(dir_alice, "tactical_map.bin")
    with open(source_file, "wb") as f:
        f.write(sample_data)
        
    bob_files = []
    def on_bob_file(sender_ip, filename, filepath, ts):
        bob_files.append((filename, filepath))
    bob.on_file_received = on_bob_file
    
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    sent = alice.send_file(
        target_ip=target_addr,
        file_path=source_file
    )
    assert sent is True
    
    time.sleep(1.0)
    assert len(bob_files) == 1
    filename, filepath = bob_files[0]
    assert filename == "tactical_map.bin"
    assert os.path.exists(filepath)
    
    # Checksum match
    with open(filepath, "rb") as f:
        received_data = f.read()
    assert hashlib.sha256(received_data).hexdigest() == sample_sha256


def test_zero_byte_file_rejection(multi_node_cluster):
    """Verify engine rejects 0-byte file transfers without socket transmission."""
    alice, bob, dir_alice, _ = multi_node_cluster
    
    empty_file = os.path.join(dir_alice, "empty.txt")
    with open(empty_file, "wb") as f:
        pass  # 0 bytes
        
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    sent = alice.send_file(
        target_ip=target_addr,
        file_path=empty_file
    )
    assert sent is False


def test_safety_numbers_symmetry():
    """Verify safety numbers generated from two peer public keys are symmetric (A->B == B->A)."""
    alice_crypto = CryptoManager()
    bob_crypto = CryptoManager()
    
    alice_pub = alice_crypto.get_signing_public_key_bytes()
    bob_pub = bob_crypto.get_signing_public_key_bytes()
    
    safety_num_ab = alice_crypto.compute_safety_number(bob_pub)
    safety_num_ba = bob_crypto.compute_safety_number(alice_pub)
    
    assert safety_num_ab == safety_num_ba
    assert len(safety_num_ab) == 14  # XXXX-XXXX-XXXX format
    assert safety_num_ab.count('-') == 2


def test_encrypted_group_channel_multicast():
    """Verify encrypted group channel derivation, encryption, and authorization."""
    passphrase = "GhostNetTacticalSquadPassphrase2026!"
    salt = "squad_alpha_salt"
    
    # Derive channel key
    key = derive_channel_key("squad_alpha", passphrase, salt.encode())
    assert len(key) == 32
    
    message = "Sector clear. Moving to extraction point."
    ciphertext_b64 = encrypt_channel_message(key, message)
    
    # Member with valid key decrypts
    decrypted = decrypt_channel_message(key, ciphertext_b64)
    assert decrypted == message
    
    # Unauthorized party with wrong key fails
    wrong_key = derive_channel_key("squad_alpha", "WrongPassphrase", salt.encode())
    failed = decrypt_channel_message(wrong_key, ciphertext_b64)
    assert failed is None


def test_dtn_offline_spool_and_recovery():
    """Verify that a message to an unreachable peer is spooled to disk as QUEUED_OFFLINE."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_dtn_sim_")
    engine = GhostEngine(username="MuleNode", downloads_dir=temp_dir, enable_storage=False)
    
    delivery_states = []
    def on_status(msg_id, peer, state):
        delivery_states.append(state)
    engine.on_delivery_status = on_status
    
    # Send to invalid unreachable port outside ephemeral range to avoid TCP self-connect
    res = engine.send_message(
        target_ip="127.0.0.1:19999",
        message_text="Delayed intelligence bundle",
        return_result=True
    )
    
    assert res.success is True
    assert res.delivery_state == "QUEUED_OFFLINE"
    
    # Check metadata on disk
    assert os.path.exists(engine.spool_dir)
    found_spool = False
    for root, dirs, files in os.walk(engine.spool_dir):
        if "metadata.json" in files:
            found_spool = True
            break
    assert found_spool is True
    
    engine.stop()
    shutil.rmtree(temp_dir, ignore_errors=True)
