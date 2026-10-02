"""
Automated Verification Suite for Gost-Net Phase 8 Subsystems:
- Dynamic Frequency Agility & Pseudo-Random Channel Hopping (FHSS)
- Jamming Channel Blacklisting & Autonomous Evading
- Zero-Knowledge Spatial Proximity Verification (No Coordinate Leakage)
- Information-Theoretic One-Time Pad Stream Vault (Non-reusable Keystream)
- EW Jamming Detection & Defensive Posture Upgrades (K=4,M=2 -> K=2,M=4)
- End-to-End Socket Transmission of OTP Frames between Nodes
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

from frequency_agility import FrequencyAgilityManager
from proximity_crypto import ProximityVerifier, encode_geohash, get_adjacent_geohashes
from anti_jamming import JammingDetector, DefensivePosture
from quantum_resilient import OTPStreamVault
from network import GhostEngine


def test_fhss_pseudo_random_hopping_and_rendezvous():
    """Verify deterministic frequency agility hopping and periodic rendezvous slots."""
    seed = b"TACTICAL_SQUAD_MESH_SEED_2026"
    alice_fhss = FrequencyAgilityManager(mesh_seed=seed, hop_interval_sec=2.0)
    bob_fhss = FrequencyAgilityManager(mesh_seed=seed, hop_interval_sec=2.0)
    
    # 1. Monotonic slot progression
    assert alice_fhss.get_current_slot(target_time=10.0) == 5
    assert alice_fhss.get_current_slot(target_time=11.9) == 5
    assert alice_fhss.get_current_slot(target_time=12.0) == 6
    
    # 2. Synchronized channel determinism between Alice and Bob
    for slot in range(1, 30):
        a_idx, a_freq = alice_fhss.get_channel_for_slot(slot)
        b_idx, b_freq = bob_fhss.get_channel_for_slot(slot)
        assert a_idx == b_idx
        assert a_freq == b_freq
        
    # 3. Rendezvous slot guarantee (every 10th slot is rendezvous channel 0)
    for r_slot in (0, 10, 20, 50, 100):
        ch_idx, freq = alice_fhss.get_channel_for_slot(r_slot)
        assert ch_idx == 0
        assert freq == alice_fhss.channels[0]
        assert alice_fhss.is_rendezvous_slot(r_slot) is True
        
    # 4. Receiver jitter tolerance window (+/- 1 hop slot)
    adj_channels = alice_fhss.get_adjacent_channels(target_time=20.0)
    assert len(adj_channels) == 3


def test_fhss_dynamic_channel_jamming_evasion():
    """Verify automatic blacklisting and evasion of jammed frequencies."""
    fhss = FrequencyAgilityManager(mesh_seed=b"JAMMING_EVASION_TEST", hop_interval_sec=1.0)
    jammed_channel = 2
    
    # Simulate repeated spot-jamming failures on channel 2
    for _ in range(8):
        fhss.record_channel_result(channel_idx=jammed_channel, success=False)
        
    assert jammed_channel in fhss.blacklisted_channels
    
    # Verify channel 2 is strictly avoided across non-rendezvous slots
    for slot in range(1, 40):
        if slot % 10 != 0:
            ch_idx, _ = fhss.get_channel_for_slot(slot)
            assert ch_idx != jammed_channel
            
    # Unblacklist channel when RF path clears
    fhss.unblacklist_channel(jammed_channel)
    assert jammed_channel not in fhss.blacklisted_channels


def test_zero_knowledge_proximity_verification():
    """Verify zero-knowledge spatial co-location without disclosing absolute coordinates."""
    shared_salt = b"OPERATIONAL_SECTOR_SALT_BRAVO"
    
    # Co-located operators (Berlin Mitte: ~35 meters apart)
    alice_lat, alice_lon = 52.5200, 13.4050
    bob_lat, bob_lon = 52.5203, 13.4052
    
    # Distant operator (Hamburg)
    charlie_lat, charlie_lon = 53.5511, 9.9937
    
    token_alice = ProximityVerifier.create_proximity_token(alice_lat, alice_lon, shared_salt, precision=6)
    token_bob = ProximityVerifier.create_proximity_token(bob_lat, bob_lon, shared_salt, precision=6)
    token_charlie = ProximityVerifier.create_proximity_token(charlie_lat, charlie_lon, shared_salt, precision=6)
    
    # Zero coordinate leakage verification
    assert "lat" not in token_alice and "latitude" not in token_alice
    assert "lon" not in token_alice and "longitude" not in token_alice
    assert isinstance(token_alice["center_commitment"], str)
    assert len(token_alice["neighbor_commitments"]) >= 8
    
    # Mutual co-location verification
    assert ProximityVerifier.verify_proximity(token_alice, token_bob) is True
    assert ProximityVerifier.verify_proximity(token_bob, token_alice) is True
    
    # Distant non-co-located verification
    assert ProximityVerifier.verify_proximity(token_alice, token_charlie) is False
    assert ProximityVerifier.verify_proximity(token_bob, token_charlie) is False


def test_otp_stream_vault_monotonicity_and_replay_rejection():
    """Verify information-theoretic OTP encryption, secure erasure on disk, and replay rejection."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_otp_test_")
    pad_bytes = OTPStreamVault.generate_random_pad(size_bytes=2048)
    
    alice_pad = os.path.join(temp_dir, "alice_vault.pad")
    bob_pad = os.path.join(temp_dir, "bob_vault.pad")
    
    with open(alice_pad, "wb") as f:
        f.write(pad_bytes)
    with open(bob_pad, "wb") as f:
        f.write(pad_bytes)
        
    alice_vault = OTPStreamVault(alice_pad)
    bob_vault = OTPStreamVault(bob_pad)
    
    # Message 1
    msg1 = b"TACTICAL_AIR_SUPPORT_COORDINATES_VECTOR_99"
    frame1 = alice_vault.encrypt_otp(msg1)
    assert frame1["pad_offset"] == 0
    assert frame1["length"] == len(msg1)
    
    # Verify consumed keystream bytes are immediately zeroed in Alice's vault on disk
    with open(alice_pad, "rb") as f:
        erased_segment = f.read(len(msg1))
        assert erased_segment == b'\x00' * len(msg1)
        
    # Bob decrypts message 1
    pt1 = bob_vault.decrypt_otp(frame1)
    assert pt1 == msg1
    assert bob_vault.recv_offset == len(msg1)
    
    # Verify Bob's vault also zeroed consumed bytes
    with open(bob_pad, "rb") as f:
        bob_erased_segment = f.read(len(msg1))
        assert bob_erased_segment == b'\x00' * len(msg1)
        
    # Message 2 with advanced monotonic offset
    msg2 = b"EXECUTE_EXTRACTION_PLAN_CHARLIE"
    frame2 = alice_vault.encrypt_otp(msg2)
    assert frame2["pad_offset"] == len(msg1)
    
    pt2 = bob_vault.decrypt_otp(frame2)
    assert pt2 == msg2
    
    # Replay Attack: Replaying frame 1 must be rejected
    replay_res = bob_vault.decrypt_otp(frame1)
    assert replay_res is None
    
    # Exhaustion guard
    remaining = alice_vault.remaining_pad_bytes()
    assert remaining == 2048 - len(msg1) - len(msg2)
    
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_ew_jamming_detection_and_fec_posture_upgrade():
    """Verify EW jamming detection triggers automated defensive posture and FEC upgrade."""
    detector = JammingDetector(pdr_threshold=0.25, min_affected_neighbors=2)
    
    # 1. Normal healthy RF environment
    detector.record_link_observation("NodeAlpha", pdr=0.98, cca_busy=0.05)
    detector.record_link_observation("NodeBravo", pdr=0.92, cca_busy=0.08)
    detector.record_link_observation("NodeCharlie", pdr=0.89, cca_busy=0.10)
    
    status_healthy = detector.evaluate_jamming_status()
    assert status_healthy["jamming_detected"] is False
    assert status_healthy["posture"] == DefensivePosture.NORMAL
    
    # 2. Single node distance fading: elevated interference, not systemic jamming
    detector.record_link_observation("NodeAlpha", pdr=0.10, cca_busy=0.20)
    status_fade = detector.evaluate_jamming_status()
    assert status_fade["jamming_detected"] is False
    assert status_fade["posture"] == DefensivePosture.ELEVATED_INTERFERENCE
    
    # 3. Hostile EW Jamming: simultaneous multi-neighbor collapse + high channel busy
    detector.record_link_observation("NodeBravo", pdr=0.04, cca_busy=0.95)
    detector.record_link_observation("NodeCharlie", pdr=0.02, cca_busy=0.90)
    
    posture_callbacks = []
    detector.on_posture_changed = lambda posture, details: posture_callbacks.append(posture)
    
    status_jammed = detector.evaluate_jamming_status()
    assert status_jammed["jamming_detected"] is True
    assert status_jammed["posture"] == DefensivePosture.EW_JAMMING_ACTIVE
    assert status_jammed["confidence"] > 0.6
    assert DefensivePosture.EW_JAMMING_ACTIVE in posture_callbacks


def test_otp_e2e_engine_socket_transmission():
    """Verify live TCP transmission of One-Time Pad encrypted frames between GhostEngine nodes."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_otp_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_otp_bob_")
    
    pad_bytes = OTPStreamVault.generate_random_pad(size_bytes=4096)
    alice_pad_path = os.path.join(dir_alice, "shared.pad")
    bob_pad_path = os.path.join(dir_bob, "shared.pad")
    
    with open(alice_pad_path, "wb") as f:
        f.write(pad_bytes)
    with open(bob_pad_path, "wb") as f:
        f.write(pad_bytes)
        
    alice = GhostEngine(username="AliceOTP", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobOTP", downloads_dir=dir_bob, enable_storage=False)
    
    alice.init_otp_vault(alice_pad_path)
    bob.init_otp_vault(bob_pad_path)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    bob_received_messages = []
    bob.on_message_received = lambda sender, text, ts: bob_received_messages.append((sender, text))
    
    # Alice sends OTP message to Bob
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    sent = alice.send_otp_message(target_ip=target_addr, message_text="STRATEGIC_COMMAND_V7")
    assert sent is True
    
    # Allow socket delivery and decryption
    time.sleep(1.0)
    
    assert len(bob_received_messages) == 1
    sender, text = bob_received_messages[0]
    assert "[OTP]: STRATEGIC_COMMAND_V7" in text
    
    # Verify pad offset advanced on both nodes
    assert alice.otp_vault.send_offset == len("STRATEGIC_COMMAND_V7".encode('utf-8'))
    assert bob.otp_vault.recv_offset == len("STRATEGIC_COMMAND_V7".encode('utf-8'))
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
