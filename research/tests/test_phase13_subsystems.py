"""
Tests for Phase 13: Hybrid Post-Quantum Key Encapsulation (Ring-LWE Lattice KEM),
Privacy-Preserving Paillier Homomorphic Sensor Aggregation, Direct Sequence Spread Spectrum (DSSS),
and Cooperative Distributed Virtual Antenna Array Coordination.
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

from post_quantum_kem import PostQuantumLatticeKEM, N as PQ_N, Q as PQ_Q
from homomorphic_aggregation import PaillierHomomorphicAggregator
from dsss_modulation import DSSSModulator
from virtual_array import VirtualArrayCoordinator, SPEED_OF_LIGHT
from network import GhostEngine


def test_post_quantum_lattice_kem_keypair_encap_decap():
    """Verify Ring-LWE lattice keypair generation, encapsulation, decapsulation, and hybrid HKDF key derivation."""
    # 1. Keypair generation
    public_key, private_key = PostQuantumLatticeKEM.generate_keypair()
    assert "a" in public_key and "t" in public_key
    assert len(public_key["a"]) == PQ_N
    assert len(public_key["t"]) == PQ_N
    assert len(private_key) == PQ_N
    
    # 2. Encapsulation
    ciphertext, shared_secret_sender = PostQuantumLatticeKEM.encapsulate(public_key)
    assert "u" in ciphertext and "v" in ciphertext
    assert len(ciphertext["u"]) == PQ_N
    assert len(ciphertext["v"]) == PQ_N
    assert len(shared_secret_sender) == 32
    
    # 3. Decapsulation
    shared_secret_receiver = PostQuantumLatticeKEM.decapsulate(private_key, ciphertext)
    assert len(shared_secret_receiver) == 32
    assert shared_secret_sender == shared_secret_receiver
    
    # 4. Hybrid Key Derivation with classical ECDH secret
    ecdh_secret = b"CLASSICAL_CURVE25519_ECDH_SECRET"
    hybrid_key = PostQuantumLatticeKEM.combine_hybrid_keys(ecdh_secret, shared_secret_sender, context="Tactical_Hybrid_Session")
    assert len(hybrid_key) == 32
    
    # 5. Tampered ciphertext recovery failure
    tampered_ct = {"u": list(ciphertext["u"]), "v": list(ciphertext["v"])}
    tampered_ct["v"][0] = (tampered_ct["v"][0] + (PQ_Q // 2)) % PQ_Q
    tampered_secret = PostQuantumLatticeKEM.decapsulate(private_key, tampered_ct)
    assert tampered_secret != shared_secret_sender


def test_paillier_homomorphic_sensor_aggregation():
    """Verify additive homomorphic encryption: sum of encrypted telemetry matches sum of plaintexts."""
    # Keypair generation (64-bit primes for fast test execution)
    pub, priv = PaillierHomomorphicAggregator.generate_keypair(key_bits=64)
    assert "n" in pub and "g" in pub and "n_sq" in pub
    assert "lam" in priv and "mu" in priv
    
    # Detachment sensor readings (e.g. radiation microsieverts/hour recorded by 4 scout mules)
    readings = [142, 89, 215, 60]
    expected_sum = sum(readings)
    
    # Encrypt individual readings
    ciphertexts = [PaillierHomomorphicAggregator.encrypt(pub, val) for val in readings]
    assert len(ciphertexts) == 4
    for c in ciphertexts:
        assert isinstance(c, int)
        assert c > 0
        
    # Intermediate untrusted relay aggregates ciphertexts homomorphically
    aggregated_ciphertext = PaillierHomomorphicAggregator.aggregate_ciphertexts(pub, ciphertexts)
    
    # HQ decrypts aggregated sum using private key
    decrypted_sum = PaillierHomomorphicAggregator.decrypt(priv, pub, aggregated_ciphertext)
    assert decrypted_sum == expected_sum


def test_dsss_gold_code_modulation_and_despreading():
    """Verify 31-chip Gold code sequence generation, bipolar chip spreading, and noise-tolerant matched filter despreading."""
    gold_code = DSSSModulator.generate_gold_sequence(31)
    assert len(gold_code) == 31
    for chip in gold_code:
        assert chip in (-1, 1)
        
    # Spread tactical message payload
    payload = b"TAC_GRID_ALERT"
    chips = DSSSModulator.spread(payload, gold_code)
    expected_chips = len(payload) * 8 * 31
    assert len(chips) == expected_chips
    
    # Exact despreading on noiseless channel
    recovered = DSSSModulator.despread(chips, gold_code)
    assert recovered == payload
    
    # Despreading over simulated noisy channel (additive noise +/- 0.4 on chips)
    import random
    noisy_chips = [c + random.uniform(-0.4, 0.4) for c in chips]
    recovered_noisy = DSSSModulator.despread(noisy_chips, gold_code)
    assert recovered_noisy == payload
    
    # Despreading with wrong Gold code produces completely mismatched output
    wrong_code = [-c for c in gold_code]
    recovered_wrong = DSSSModulator.despread(chips, wrong_code)
    assert recovered_wrong != payload


def test_virtual_antenna_array_beamforming_and_steering():
    """Verify distributed virtual array steering vectors, coherent array power gain, and array factor directivity."""
    coord = VirtualArrayCoordinator(local_node_id="NODE_LEADER", default_carrier_freq_hz=915e6)
    wavelength = coord.get_wavelength()
    assert abs(wavelength - (SPEED_OF_LIGHT / 915e6)) < 1e-4
    
    # Register 4 squad nodes in a linear array along X axis spaced at lambda/2
    d = wavelength / 2.0
    coord.register_node("SQUAD_0", 0.0 * d, 0.0)
    coord.register_node("SQUAD_1", 1.0 * d, 0.0)
    coord.register_node("SQUAD_2", 2.0 * d, 0.0)
    coord.register_node("SQUAD_3", 3.0 * d, 0.0)
    
    # 1. Theoretical Coherent Power Gain for N=4: 20 * log10(4) = 12.04 dB
    gain_db = coord.compute_array_power_gain_db()
    assert abs(gain_db - 12.04) < 0.1
    
    # 2. Steering toward broadside (90 degrees, +Y direction)
    steering_90 = coord.compute_steering_phases(target_azimuth_deg=90.0)
    assert len(steering_90) == 4
    for nid, s in steering_90.items():
        assert "phase_rad" in s
        assert "delay_nanoseconds" in s
        
    # 3. Array Factor magnitude
    # In steering direction (90 deg), main lobe peak must be 1.0
    af_peak = coord.compute_array_factor(steering_azimuth_deg=90.0, observation_azimuth_deg=90.0)
    assert abs(af_peak - 1.0) < 1e-3
    
    # Off-axis observation (e.g. 0 degrees, along the array line) must be significantly attenuated
    af_off = coord.compute_array_factor(steering_azimuth_deg=90.0, observation_azimuth_deg=0.0)
    assert af_off < 0.25


def test_homomorphic_and_pq_kem_edge_cases():
    """Verify edge cases for homomorphic empty aggregation, zero additions, and single node array factor."""
    pub, priv = PaillierHomomorphicAggregator.generate_keypair(key_bits=64)
    
    # Empty aggregation produces 1 (identity ciphertext for multiplication)
    assert PaillierHomomorphicAggregator.aggregate_ciphertexts(pub, []) == 1
    
    # Encrypt zero and add to value
    c_val = PaillierHomomorphicAggregator.encrypt(pub, 77)
    c_zero = PaillierHomomorphicAggregator.encrypt(pub, 0)
    c_sum = PaillierHomomorphicAggregator.aggregate_ciphertexts(pub, [c_val, c_zero])
    assert PaillierHomomorphicAggregator.decrypt(priv, pub, c_sum) == 77
    
    # DSSS on boundary bytes
    gold = DSSSModulator.generate_gold_sequence(31)
    boundary_data = bytes([0x00, 0xFF, 0xAA, 0x55])
    chips = DSSSModulator.spread(boundary_data, gold)
    assert DSSSModulator.despread(chips, gold) == boundary_data
    
    # Virtual Array with 1 node
    solo = VirtualArrayCoordinator("SOLO")
    solo.register_node("SOLO", 0.0, 0.0)
    assert solo.compute_array_power_gain_db() == 0.0
    assert solo.compute_array_factor(45.0, 180.0) == 1.0


def test_phase13_live_engine_socket_integration():
    """Verify live GhostEngine TCP socket replication of Post-Quantum KEM ciphertexts, Homomorphic Telemetry, DSSS, and Merkle audit trails."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase13_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase13_bob_")
    
    alice = GhostEngine(username="AliceP13", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP13", downloads_dir=dir_bob, enable_storage=False)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    # 1. Post-Quantum KEM live TCP handshake from Bob to Alice
    alice_pub, alice_priv = alice.pq_generate_keypair()
    
    # Bob encapsulates against Alice's public key
    bob_ct, bob_secret = bob.pq_encapsulate(alice_pub)
    
    received_cts = []
    alice.on_pq_kem_ciphertext_received = lambda sender_ip, ct: received_cts.append(ct)
    
    # Bob transmits ciphertext over socket to Alice
    target_addr = f"127.0.0.1:{alice.tcp_port}"
    success = bob.send_pq_kem_ciphertext(target_addr, bob_ct)
    assert success is True
    time.sleep(0.8)
    
    assert len(received_cts) == 1
    alice_recovered_secret = alice.pq_decapsulate(alice_priv, received_cts[0])
    assert alice_recovered_secret == bob_secret
    
    # 2. Paillier Homomorphic Telemetry live TCP transmission
    paillier_pub, paillier_priv = alice.homomorphic_generate_keypair(key_bits=64)
    
    received_telemetry = []
    alice.on_homomorphic_telemetry_received = lambda sender_ip, c, st: received_telemetry.append((c, st))
    
    # Bob transmits encrypted sensor reading (e.g. 420 rads)
    ok = bob.send_homomorphic_reading(
        target_peer=f"127.0.0.1:{alice.tcp_port}",
        public_key=paillier_pub,
        reading=420,
        sensor_type="radiation"
    )
    assert ok is True
    time.sleep(0.8)
    
    assert len(received_telemetry) == 1
    c_bob, s_type = received_telemetry[0]
    assert s_type == "radiation"
    
    # Alice adds local reading (80 rads) homomorphically
    c_alice = alice.homomorphic_encrypt(paillier_pub, 80)
    c_total = alice.homomorphic_aggregate(paillier_pub, [c_bob, c_alice])
    total_rads = alice.homomorphic_decrypt(paillier_priv, paillier_pub, c_total)
    assert total_rads == 500
    
    # 3. DSSS modulation & demodulation via engine helpers
    gold = alice.dsss_generate_gold_code(31)
    chips = alice.dsss_spread_packet(b"ENGINE_DSSS_PAYLOAD", gold)
    recovered_data = alice.dsss_despread_packet(chips, gold)
    assert recovered_data == b"ENGINE_DSSS_PAYLOAD"
    
    # 4. Virtual Array coordination on engine
    alice.virtual_array_register_node("ALICE_NODE", 0.0, 0.0)
    alice.virtual_array_register_node("BOB_NODE", 0.16, 0.0)
    gain = alice.virtual_array_get_gain_db()
    assert abs(gain - 6.02) < 0.1
    steering = alice.virtual_array_compute_steering(target_azimuth_deg=45.0)
    assert len(steering) == 2
    
    # 5. Tamper-evident Merkle Audit Ledger verification
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True
    
    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]
    
    assert "PQ_KEM_CIPHERTEXT_INGRESS" in alice_events
    assert "PQ_KEM_DECAPSULATE" in alice_events
    assert "HOMOMORPHIC_TELEMETRY_INGRESS" in alice_events
    assert "HOMOMORPHIC_AGGREGATE" in alice_events
    assert "HOMOMORPHIC_DECRYPT" in alice_events
    assert "DSSS_SPREAD" in alice_events
    assert "DSSS_DESPREAD" in alice_events
    assert "PQ_KEM_ENCAPSULATE" in bob_events
    assert "PQ_KEM_DISPATCHED" in bob_events
    assert "HOMOMORPHIC_DISPATCHED" in bob_events
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
