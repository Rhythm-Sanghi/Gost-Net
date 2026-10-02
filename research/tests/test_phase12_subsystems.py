"""
Tests for Phase 12: Autonomous Collaborative Electronic Countermeasures (ECM),
Random Linear Network Coding (RLNC) over GF(256), Dynamic Token-Bucket Tactical QoS,
and Zero-Knowledge Peer Authentication (Schnorr ZKP).
"""

import os
import sys
import time
import math
import shutil
import tempfile
import pytest

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from collaborative_ecm import CollaborativeECMManager, JammerObservation
from network_coding import RLNCEncoder, RLNCDecoder, _gf_mul, _gf_div, _gf_add
from qos_shaper import TacticalQoSShaper, TokenBucket, QoSClass
from zkp_auth import SchnorrZKP, P, G, Q
from network import GhostEngine


def test_collaborative_ecm_trilateration_and_nulling_bearing():
    """Verify log-distance path loss distance estimation, weighted centroid multilateration, and nulling azimuth calculation."""
    ecm = CollaborativeECMManager(local_node_id="NODE_OVERWATCH", observation_ttl_sec=30.0)
    
    # 1. Path-loss distance estimation
    # RSSI = P0 - 10 * n * log10(d). At d=10m, n=2.5, P0=-30: RSSI = -30 - 25 = -55 dBm
    dist_10m = ecm.estimate_distance_from_rssi(rssi_dbm=-55.0, p0_dbm=-30.0, path_loss_exp=2.5)
    assert abs(dist_10m - 10.0) < 0.1
    
    # 2. Insufficient observations (< 3) returns None
    ecm.record_observation("OBSERVER_1", 34.051, -118.251, -50.0)
    ecm.record_observation("OBSERVER_2", 34.049, -118.249, -52.0)
    assert ecm.triangulate_jammer() is None
    
    # Add 3rd and 4th observers centered symmetrically around target jammer (34.050, -118.250)
    ecm.record_observation("OBSERVER_3", 34.051, -118.249, -51.0)
    ecm.record_observation("OBSERVER_4", 34.049, -118.251, -51.0)
    
    tri = ecm.triangulate_jammer(p0_dbm=-30.0, path_loss_exp=2.5)
    assert tri is not None
    assert "estimated_lat" in tri
    assert "estimated_lon" in tri
    assert abs(tri["estimated_lat"] - 34.050) < 0.005
    assert abs(tri["estimated_lon"] - (-118.250)) < 0.005
    assert len(tri["contributing_nodes"]) == 4
    assert tri["confidence_score"] > 0.5
    
    # 3. Nulling bearing calculation
    # Jammer due North of friendly node: bearing should be 0 degrees
    bearing_north = CollaborativeECMManager.calculate_nulling_bearing(
        friendly_lat=0.0, friendly_lon=0.0,
        jammer_lat=1.0, jammer_lon=0.0
    )
    assert abs(bearing_north - 0.0) < 0.1
    
    # Jammer due East of friendly node: bearing should be 90 degrees
    bearing_east = CollaborativeECMManager.calculate_nulling_bearing(
        friendly_lat=0.0, friendly_lon=0.0,
        jammer_lat=0.0, jammer_lon=1.0
    )
    assert abs(bearing_east - 90.0) < 0.1
    
    # 4. Stale observation pruning
    with ecm.lock:
        ecm.observations["OBSERVER_1"].timestamp = time.time() - 100.0
    ecm.prune_stale_observations()
    assert "OBSERVER_1" not in ecm.observations
    assert len(ecm.observations) == 3


def test_rlnc_encoding_and_gaussian_elimination_decoding():
    """Verify GF(256) arithmetic, random linear combination coding, and full matrix rank decoding."""
    # 1. Verify GF(256) basic field laws
    for a in [1, 2, 42, 128, 255]:
        assert _gf_add(a, a) == 0  # Characteristic 2
        assert _gf_mul(a, 1) == a  # Multiplicative identity
        inv_a = _gf_div(1, a)
        assert _gf_mul(a, inv_a) == 1  # Multiplicative inverse
        
    # 2. Source Generation
    source_packets = [
        b"TACTICAL_SITREP_GRID_ALPHA_001",
        b"TARGET_COORDINATES_34.05_-118.25",
        b"AIR_SUPPORT_FLIGHT_CALLSIGN_VIPER",
        b"EVACUATION_LZ_SECURE_HOLD_POSITION"
    ]
    gen_size = len(source_packets)
    max_len = max(len(p) for p in source_packets)
    
    encoder = RLNCEncoder(source_packets)
    decoder = RLNCDecoder(generation_size=gen_size, packet_len=max_len)
    
    # Produce innovative coded packets until decoded
    packets_fed = 0
    while not decoder.is_complete() and packets_fed < 20:
        coeffs, coded_data = encoder.produce_coded_packet()
        assert len(coeffs) == gen_size
        assert len(coded_data) == max_len
        decoder.add_coded_packet(coeffs, coded_data)
        packets_fed += 1
        
    assert decoder.is_complete() is True
    assert decoder.rank == gen_size
    
    # Reconstruct original packets via back-substitution
    recovered = decoder.decode()
    assert recovered is not None
    assert len(recovered) == gen_size
    for orig, rec in zip(source_packets, recovered):
        # Rec matches orig (accounting for trailing padding)
        assert rec[:len(orig)] == orig


def test_rlnc_lossy_channel_and_redundancy_resilience():
    """Verify RLNC performance across lossy channels: duplicate packet rejection and recovery with extra linear combinations."""
    source_packets = [
        b"MISSION_CODE_ALPHA_OMEGA_001",
        b"AUTHENTICATION_CHALLENGE_987654",
        b"CRYPTOGRAPHIC_NONCE_ABCDEF012345"
    ]
    gen_size = len(source_packets)
    packet_len = max(len(p) for p in source_packets)
    
    encoder = RLNCEncoder(source_packets)
    decoder = RLNCDecoder(generation_size=gen_size, packet_len=packet_len)
    
    # First coded packet
    c1, d1 = encoder.produce_coded_packet()
    assert decoder.add_coded_packet(c1, d1) is True
    assert decoder.rank == 1
    
    # Re-feeding the EXACT same packet is linearly dependent (redundant)
    assert decoder.add_coded_packet(c1, d1) is False
    assert decoder.rank == 1
    
    # A scaled copy (e.g. * 5 over GF(256)) is also linearly dependent
    c1_scaled = [_gf_mul(val, 5) for val in c1]
    d1_scaled = bytes(_gf_mul(b, 5) for b in d1)
    assert decoder.add_coded_packet(c1_scaled, d1_scaled) is False
    assert decoder.rank == 1
    
    # Feed innovative packets until complete
    while not decoder.is_complete():
        c, d = encoder.produce_coded_packet()
        decoder.add_coded_packet(c, d)
        
    assert decoder.is_complete() is True
    recovered = decoder.decode()
    for orig, rec in zip(source_packets, recovered):
        assert rec[:len(orig)] == orig


def test_tactical_qos_token_bucket_and_congestion_throttling():
    """Verify multi-tier priority scheduling, token-bucket metering, and bulk traffic congestion backoff."""
    shaper = TacticalQoSShaper(
        tactical_rate_bytes_sec=1000.0,
        bulk_rate_bytes_sec=500.0,
        congestion_pdr_threshold=0.70
    )
    
    # 1. Priority Preemption: Enqueue BULK, then TACTICAL, then CRITICAL
    p_bulk = b"LARGE_MAP_RASTER_DATA_TILE_CHUNK_01"
    p_tac = b"SITREP_FRIENDLY_POSITION_BEACON"
    p_crit = b"EMERGENCY_SOS_FLASH_COMMAND"
    
    shaper.enqueue_packet(p_bulk, QoSClass.BULK)
    shaper.enqueue_packet(p_tac, QoSClass.TACTICAL)
    shaper.enqueue_packet(p_crit, QoSClass.CRITICAL)
    
    depth = shaper.get_queue_depth()
    assert depth["critical"] == 1
    assert depth["tactical"] == 1
    assert depth["bulk"] == 1
    assert depth["is_congested"] is False
    
    # CRITICAL must dequeue FIRST regardless of enqueue order
    pkt1, cls1 = shaper.dequeue_packet()
    assert cls1 == QoSClass.CRITICAL
    assert pkt1 == p_crit
    
    # TACTICAL dequeues next
    pkt2, cls2 = shaper.dequeue_packet()
    assert cls2 == QoSClass.TACTICAL
    assert pkt2 == p_tac
    
    # 2. Link Congestion Throttling
    # Under high packet loss (PDR = 0.40 < 0.70 threshold)
    shaper.report_link_health(pdr=0.40, rtt_ms=120.0)
    assert shaper.is_congested is True
    
    # Bulk packet must be blocked/suppressed during congestion
    assert shaper.dequeue_packet() is None
    assert len(shaper.queues[QoSClass.BULK]) == 1
    
    # But a fresh CRITICAL packet immediately bypasses congestion block
    shaper.enqueue_packet(b"ZEROIZE_IMMEDIATE", QoSClass.CRITICAL)
    crit_pkt, crit_cls = shaper.dequeue_packet()
    assert crit_cls == QoSClass.CRITICAL
    assert crit_pkt == b"ZEROIZE_IMMEDIATE"
    
    # Once link recovers (PDR = 0.95 >= 0.70), bulk traffic unblocks
    shaper.report_link_health(pdr=0.95, rtt_ms=25.0)
    assert shaper.is_congested is False
    bulk_pkt, bulk_cls = shaper.dequeue_packet()
    assert bulk_cls == QoSClass.BULK
    assert bulk_pkt == p_bulk


def test_schnorr_zkp_authentication_protocol():
    """Verify Schnorr Sigma-Protocol NIZK key generation, proof creation, verification, and tamper detection."""
    # 1. Keypair generation
    priv_x, pub_y = SchnorrZKP.generate_keypair()
    assert 2 <= priv_x < Q
    assert 1 < pub_y < P
    assert pow(G, priv_x, P) == pub_y
    
    # 2. Proof Generation & Verification
    context_str = "Tactical_Unit_Authorization_Mission_Red"
    proof = SchnorrZKP.create_proof(priv_x, pub_y, context=context_str)
    assert "R" in proof
    assert "s" in proof
    assert "c" in proof
    assert proof["context"] == context_str
    
    # Legitimate proof verifies successfully
    assert SchnorrZKP.verify_proof(pub_y, proof, context=context_str) is True
    
    # 3. Context mismatch fails verification
    assert SchnorrZKP.verify_proof(pub_y, proof, context="Wrong_Context_Mission") is False
    
    # 4. Wrong public key fails verification
    _, wrong_pub_y = SchnorrZKP.generate_keypair()
    assert SchnorrZKP.verify_proof(wrong_pub_y, proof, context=context_str) is False
    
    # 5. Tampered proof response 's' fails verification
    tampered_proof = dict(proof)
    tampered_s = (int(proof["s"], 16) + 1) % Q
    tampered_proof["s"] = hex(tampered_s)
    assert SchnorrZKP.verify_proof(pub_y, tampered_proof, context=context_str) is False


def test_phase12_live_engine_socket_integration():
    """Verify live GhostEngine socket replication for ECM observations, ZKP authentication, QoS shaper, and Merkle audit trails."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase12_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase12_bob_")
    
    alice = GhostEngine(username="AliceP12", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP12", downloads_dir=dir_bob, enable_storage=False)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    # 1. Live ECM Jammer Observation replication from Bob to Alice
    target_addr = f"127.0.0.1:{alice.tcp_port}"
    bob.record_ecm_observation(
        observer_id="BOB_RECON_1",
        lat=34.052,
        lon=-118.252,
        rssi_dbm=-48.0,
        target_peer=target_addr
    )
    time.sleep(0.8)
    
    # Alice must have received and ingested Bob's observation into her ECM manager
    assert "BOB_RECON_1" in alice.collaborative_ecm.observations
    obs = alice.collaborative_ecm.observations["BOB_RECON_1"]
    assert obs.lat == 34.052
    assert obs.lon == -118.252
    assert obs.rssi_dbm == -48.0
    
    # Record remaining observations directly into Alice to test engine triangulation
    alice.record_ecm_observation("ALICE_BASE", 34.048, -118.248, -52.0)
    alice.record_ecm_observation("CHARLIE_OVERWATCH", 34.051, -118.249, -50.0)
    
    tri = alice.triangulate_ecm_jammer()
    assert tri is not None
    assert abs(tri["estimated_lat"] - 34.050) < 0.01
    
    # Bearing from Alice to estimated jammer
    bearing = alice.get_ecm_nulling_bearing(
        friendly_lat=34.040, friendly_lon=-118.250,
        jammer_lat=tri["estimated_lat"], jammer_lon=tri["estimated_lon"]
    )
    assert 0.0 <= bearing <= 360.0
    
    # 2. Live Schnorr ZKP Peer Authentication over TCP Socket from Bob to Alice
    bob_priv, bob_pub = bob.zkp_generate_keypair()
    
    auth_verified = []
    alice.on_zkp_auth_received = lambda sender_ip, pub_y, valid: auth_verified.append((pub_y, valid))
    
    success = bob.send_zkp_auth_proof(
        target_peer=f"127.0.0.1:{alice.tcp_port}",
        private_x=bob_priv,
        public_y=bob_pub,
        context="Tactical_Mesh_Join_Authorization"
    )
    assert success is True
    time.sleep(0.8)
    
    assert len(auth_verified) == 1
    assert auth_verified[0][0] == bob_pub
    assert auth_verified[0][1] is True
    
    # 3. RLNC encoding & decoding via engine helpers
    packets = [b"ENGINE_PAYLOAD_01", b"ENGINE_PAYLOAD_02", b"ENGINE_PAYLOAD_03"]
    coded = alice.rlnc_encode_generation(packets, redundancy_factor=2.0)
    assert len(coded) == 6
    decoded = alice.rlnc_decode_generation(coded[:3], generation_size=3, packet_len=max(len(p) for p in packets))
    assert decoded is not None
    assert decoded[0][:len(packets[0])] == packets[0]
    
    # 4. Engine QoS shaper queueing
    alice.qos_enqueue(b"TEST_QOS_PACKET", QoSClass.TACTICAL)
    depth = alice.qos_get_queue_depth()
    assert depth["tactical"] >= 1
    dq_pkt, dq_cls = alice.qos_dequeue()
    assert dq_pkt == b"TEST_QOS_PACKET"
    assert dq_cls == QoSClass.TACTICAL
    
    # 5. Tamper-evident Merkle Audit Ledger verification
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True
    
    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]
    
    assert "ECM_OBSERVATION_INGRESS" in alice_events
    assert "ZKP_AUTH_VERIFIED" in alice_events
    assert "RLNC_ENCODE_GENERATION" in alice_events
    assert "RLNC_DECODE_SUCCESS" in alice_events
    assert "ECM_OBSERVATION_RECORDED" in bob_events
    assert "ZKP_AUTH_DISPATCHED" in bob_events
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
