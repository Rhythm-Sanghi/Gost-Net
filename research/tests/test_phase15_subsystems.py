"""
Tests for Phase 15: Adaptive Modulation & Coding (AMC), Logical Key Hierarchy (LKH) Group Rekeying,
Multi-Criteria Fuzzy Logic / AHP Route Optimization, and Anti-Replay Sliding Window Engine.
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

from adaptive_modulation import AdaptiveModulationEngine, LinkAdaptationReport, ModulationProfile, TACTICAL_PROFILES
from group_rekeying import LogicalKeyHierarchy, RekeyMessage
from fuzzy_routing import FuzzyRoutingEngine, NodeMetrics, FuzzyEvaluation, PathRank, MissionMode
from anti_replay import AntiReplayManager, SlidingWindow
from network import GhostEngine


def test_adaptive_modulation_and_coding_engine():
    """Verify dynamic AMC profile selection, hysteresis filtering, Shannon capacity, and CQI feedback."""
    engine = AdaptiveModulationEngine(bandwidth_hz=125000.0, upward_hysteresis_db=1.5, default_profile_name="QPSK_1_2")
    assert engine.current_profile.name == "QPSK_1_2"

    # 1. Extreme negative SNR -> Fallback to LoRa SF12
    rep_low = engine.select_profile(measured_snr_db=-18.0)
    assert rep_low.active_profile.name == "LORA_SF12"
    assert rep_low.active_profile.is_lora is True
    assert rep_low.target_cqi == 1

    # 2. Medium SNR -> QPSK
    rep_med = engine.select_profile(measured_snr_db=5.0)
    assert "QPSK" in rep_med.active_profile.name

    # 3. Upward Hysteresis:
    # 16QAM_1_2 requires min_snr_db = 10.5 dB. With 1.5 dB upward hysteresis, threshold is 12.0 dB.
    # At 11.0 dB, it should NOT jump to 16QAM_1_2 because of hysteresis.
    engine.current_profile = [p for p in engine.profiles if p.name == "QPSK_3_4"][0]  # min 6.5 dB
    rep_hyst = engine.select_profile(measured_snr_db=11.0)
    assert rep_hyst.active_profile.name == "QPSK_3_4"
    assert rep_hyst.hysteresis_active is True

    # When SNR clears 12.0 dB (e.g. 13.0 dB), it cleanly transitions to 16QAM_1_2
    rep_clear = engine.select_profile(measured_snr_db=13.0)
    assert rep_clear.active_profile.name == "16QAM_1_2"
    assert rep_clear.hysteresis_active is False

    # 4. High SNR -> 64QAM
    rep_high = engine.select_profile(measured_snr_db=25.0)
    assert "64QAM" in rep_high.active_profile.name
    assert rep_high.spectral_efficiency >= 4.0
    assert rep_high.effective_throughput_bps > rep_med.effective_throughput_bps

    # 5. Shannon Capacity verification
    cap = AdaptiveModulationEngine.shannon_capacity(125000.0, 10.0)
    # At SNR = 10 dB (linear 10), log2(11) ~ 3.4594 * 125000 ~ 432,429 bps
    assert 400000.0 < cap < 460000.0

    # 6. Closed-loop CQI feedback encoding/decoding
    feedback = engine.encode_cqi_feedback()
    assert feedback["cqi"] == rep_high.target_cqi
    assert feedback["profile"] == rep_high.active_profile.name

    new_engine = AdaptiveModulationEngine(default_profile_name="BPSK_1_2")
    assert new_engine.current_profile.name == "BPSK_1_2"
    applied = new_engine.decode_and_apply_cqi(feedback)
    assert applied.name == rep_high.active_profile.name


def test_logical_key_hierarchy_group_rekeying():
    """Verify LKH key tree construction, forward and backward secrecy upon member join and eviction."""
    lkh = LogicalKeyHierarchy(root_id=1)
    initial_root_key = lkh.group_key

    # 1. Add squad members: Alice, Bob, Charlie, Dave
    alice_keys, rekey_alice = lkh.add_member("ALICE")
    assert "ALICE" in lkh.member_to_leaf
    bob_keys, rekey_bob = lkh.add_member("BOB")
    charlie_keys, rekey_charlie = lkh.add_member("CHARLIE")
    dave_keys, rekey_dave = lkh.add_member("DAVE")

    assert len(lkh.member_to_leaf) == 4
    # Root key should have changed from initial (backward secrecy)
    assert lkh.group_key != initial_root_key

    # 2. Member key ring contains path to root
    dave_ring = lkh.get_member_key_ring("DAVE")
    assert lkh.root_id in dave_ring
    assert dave_ring[lkh.root_id] == lkh.group_key

    # 3. Multicast group message encryption
    plaintext = b"SECURE_SQUAD_TACTICAL_BRIEFING"
    encrypted_msg = lkh.encrypt_group_message(plaintext)

    # Bob decrypts with his current group key
    bob_group_key = lkh.get_member_key_ring("BOB")[lkh.root_id]
    decrypted_bob = LogicalKeyHierarchy.decrypt_group_message(encrypted_msg, bob_group_key)
    assert decrypted_bob == plaintext

    # 4. Member Eviction (Dave is captured / compromised)
    # Evicting Dave rotates all ancestor keys up to root (forward secrecy)
    old_group_key_before_evict = lkh.group_key
    rekey_msgs = lkh.evict_member("DAVE")
    assert "DAVE" not in lkh.member_to_leaf
    assert lkh.group_key != old_group_key_before_evict

    # Dave attempts to decrypt new group message with his old key -> FAILS
    new_plaintext = b"POST_EVICTION_COORDINATES_TOP_SECRET"
    new_encrypted_msg = lkh.encrypt_group_message(new_plaintext)
    with pytest.raises(Exception):
        LogicalKeyHierarchy.decrypt_group_message(new_encrypted_msg, dave_ring[lkh.root_id])

    # 5. Remaining members (e.g. Alice) process rekey messages to obtain new root key
    alice_updated_keys = dict(lkh.get_member_key_ring("ALICE"))
    # In tree, Alice's key path matches the current tree
    alice_group_key = lkh.get_member_key_ring("ALICE")[lkh.root_id]
    assert alice_group_key == lkh.group_key

    decrypted_alice = LogicalKeyHierarchy.decrypt_group_message(new_encrypted_msg, alice_group_key)
    assert decrypted_alice == new_plaintext


def test_fuzzy_routing_multi_criteria_optimization():
    """Verify fuzzy membership evaluation, battery starvation avoidance, mission modes, and path ranking."""
    engine = FuzzyRoutingEngine(mode=MissionMode.STANDARD)

    # 1. Fuzzy membership properties
    # Full battery, strong RSSI, 100% PDR, low RTT -> OPTIMAL
    healthy_node = NodeMetrics(
        node_id="NODE_ALPHA",
        battery_pct=95.0,
        rssi_dbm=-55.0,
        pdr=0.98,
        rtt_ms=15.0,
        hop_count=1
    )
    eval_healthy = engine.evaluate_node(healthy_node)
    assert eval_healthy.classification == "OPTIMAL"
    assert eval_healthy.composite_score >= 0.80

    # 2. Battery Starvation Avoidance: Node with 8% battery should be PRUNED
    dying_node = NodeMetrics(
        node_id="NODE_DYING",
        battery_pct=8.0,
        rssi_dbm=-60.0,
        pdr=0.95,
        rtt_ms=20.0,
        hop_count=1
    )
    eval_dying = engine.evaluate_node(dying_node)
    assert eval_dying.battery_score < 0.20
    assert eval_dying.composite_score < eval_healthy.composite_score

    # 3. Mission Modes comparison
    # Low-power mode penalizes battery drain heavily
    engine_lp = FuzzyRoutingEngine(mode=MissionMode.LOW_POWER)
    eval_lp = engine_lp.evaluate_node(dying_node)
    assert eval_lp.classification in ("PRUNED", "DEGRADED")
    assert eval_lp.composite_score < eval_dying.composite_score

    # Emergency mode prioritizes PDR & RSSI above battery
    engine_em = FuzzyRoutingEngine(mode=MissionMode.EMERGENCY)
    eval_em = engine_em.evaluate_node(dying_node)
    assert eval_em.composite_score > eval_lp.composite_score

    # 4. Multi-hop Path Ranking
    # Path 1: 2 hops through healthy nodes
    path_1 = [
        NodeMetrics("RELAY_1", 90.0, -65.0, 0.95, 25.0, 1),
        NodeMetrics("RELAY_2", 85.0, -70.0, 0.90, 30.0, 2)
    ]
    # Path 2: 1 hop through severely degraded link
    path_2 = [
        NodeMetrics("RELAY_BAD", 90.0, -112.0, 0.30, 450.0, 1)
    ]

    ranked = engine.rank_paths([path_1, path_2])
    assert len(ranked) == 2
    # Path 1 should rank higher than Path 2
    assert ranked[0].path_nodes == ["RELAY_1", "RELAY_2"]
    assert ranked[0].is_viable is True
    assert ranked[1].is_viable is False


def test_anti_replay_sliding_window_engine():
    """Verify sliding window bitmask verification, out-of-order acceptance, duplicate rejection, and epoch isolation."""
    win = SlidingWindow(window_size=128)

    # 1. Initial packet
    ok, reason = win.check_and_update(100)
    assert ok is True
    assert reason == "OK_IN_ORDER"
    assert win.max_seq == 100

    # 2. Sequential in-order packets
    ok, reason = win.check_and_update(101)
    assert ok is True
    assert reason == "OK_IN_ORDER"
    assert win.max_seq == 101

    # 3. Packet advancing window ahead (skipping sequence 102)
    ok, reason = win.check_and_update(105)
    assert ok is True
    assert reason == "OK_IN_ORDER"
    assert win.max_seq == 105

    # 4. Out-of-order packet arrives within window (sequence 102) -> ACCEPT
    ok, reason = win.check_and_update(102)
    assert ok is True
    assert reason == "OK_OUT_OF_ORDER"

    # 5. Exact Replay Attack: Re-sending sequence 102 -> REJECT
    ok, reason = win.check_and_update(102)
    assert ok is False
    assert reason == "REPLAY_DUPLICATE"

    # 6. Re-sending max_seq 105 -> REJECT
    ok, reason = win.check_and_update(105)
    assert ok is False
    assert reason == "REPLAY_DUPLICATE"

    # 7. Expired packet outside 128-bit window horizon
    # Current max_seq = 105. Window horizon is (105 - 128) = -23.
    # Advance window far ahead to 300:
    win.check_and_update(300)
    # Now sequence 100 is (300 - 100 = 200 > 128) -> TOO_OLD
    ok, reason = win.check_and_update(100)
    assert ok is False
    assert reason == "TOO_OLD"

    # 8. AntiReplayManager with multi-peer and epoch isolation
    mgr = AntiReplayManager(window_size=128)
    ok, reason = mgr.verify_and_accept("PEER_ALICE", seq_num=10, epoch=1)
    assert ok is True

    # Peer Alice replay
    ok, reason = mgr.verify_and_accept("PEER_ALICE", seq_num=10, epoch=1)
    assert ok is False
    assert reason == "REPLAY_DUPLICATE"

    # Peer Bob sending same sequence number 10 is independent
    ok, reason = mgr.verify_and_accept("PEER_BOB", seq_num=10, epoch=1)
    assert ok is True

    # Alice advances epoch to 2 (e.g. session rekey) -> Resets window cleanly
    ok, reason = mgr.verify_and_accept("PEER_ALICE", seq_num=10, epoch=2)
    assert ok is True

    # Alice stale epoch 1 packet arriving late -> REJECT
    ok, reason = mgr.verify_and_accept("PEER_ALICE", seq_num=20, epoch=1)
    assert ok is False
    assert reason == "STALE_EPOCH"


def test_phase15_edge_cases_and_boundary_conditions():
    """Verify edge cases for zero bandwidth, empty paths, invalid memberships, and window normalization."""
    # Adaptive Modulation zero bandwidth
    cap_zero = AdaptiveModulationEngine.shannon_capacity(0.0, 10.0)
    assert cap_zero == 0.0

    # LKH eviction of non-existent member
    lkh = LogicalKeyHierarchy()
    with pytest.raises(KeyError):
        lkh.evict_member("NON_EXISTENT_MEMBER")

    # LKH duplicate member addition
    lkh.add_member("OPERATOR_1")
    with pytest.raises(ValueError):
        lkh.add_member("OPERATOR_1")

    # Fuzzy Routing empty candidate paths
    router = FuzzyRoutingEngine()
    assert router.rank_paths([]) == []
    assert router.rank_paths([[]]) == []

    # Anti-replay negative sequence numbers
    win = SlidingWindow(window_size=128)
    ok, reason = win.check_and_update(-5)
    assert ok is False
    assert reason == "TOO_OLD"

    # Non power-of-two window size normalizes to 128
    odd_win = SlidingWindow(window_size=99)
    assert odd_win.window_size == 128


def test_phase15_live_engine_socket_integration():
    """Verify live GhostEngine socket replication for CQI feedback, LKH rekeying, fuzzy routing, and anti-replay audit trails."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase15_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase15_bob_")

    alice = GhostEngine(username="AliceP15", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP15", downloads_dir=dir_bob, enable_storage=False)

    alice.start()
    bob.start()
    time.sleep(0.5)

    # 1. Live Closed-Loop CQI Feedback over TCP Socket
    target_addr = f"127.0.0.1:{alice.tcp_port}"
    ok = bob.send_cqi_feedback(target_addr, cqi_data={"cqi": 10, "profile": "64QAM_2_3", "snr_db": 19.5})
    assert ok is True
    time.sleep(0.6)

    # Alice must have updated her modulation profile from Bob's CQI feedback
    assert alice.adaptive_modulation.current_profile.cqi_index == 10
    assert alice.adaptive_modulation.current_profile.name == "64QAM_2_3"

    # 2. Live LKH Rekey message distribution over TCP Socket
    rekey_received = []
    alice.on_lkh_rekey_received = lambda rk: rekey_received.append(rk)
    
    target_alice = f"127.0.0.1:{alice.tcp_port}"
    dummy_rekey = {"target_node_id": 3, "enc_by_node_id": 1, "nonce": "010203", "ciphertext": "aabbcc"}
    ok_rekey = bob.send_lkh_rekey_message(target_alice, dummy_rekey)
    assert ok_rekey is True
    time.sleep(0.6)

    assert len(rekey_received) == 1
    assert rekey_received[0]["target_node_id"] == 3

    # 3. Engine Link Modulation Adaptation
    adapt_rep = alice.adapt_link_modulation(measured_snr_db=14.5)
    assert "profile" in adapt_rep
    assert adapt_rep["shannon_capacity_bps"] > 0

    # 4. Engine Fuzzy Route Evaluation & Path Ranking
    route_eval = alice.evaluate_fuzzy_route(
        node_id="RELAY_CHARLIE",
        battery_pct=88.0,
        rssi_dbm=-68.0,
        pdr=0.92,
        rtt_ms=25.0,
        hop_count=2,
        mode="STANDARD"
    )
    assert route_eval["classification"] in ("OPTIMAL", "ACCEPTABLE")
    assert route_eval["composite_score"] > 0.60

    candidate_paths = [
        [
            {"node_id": "N1", "battery_pct": 90.0, "rssi_dbm": -60.0, "pdr": 0.95, "rtt_ms": 20.0, "hop_count": 1},
            {"node_id": "N2", "battery_pct": 85.0, "rssi_dbm": -70.0, "pdr": 0.90, "rtt_ms": 30.0, "hop_count": 2}
        ],
        [
            {"node_id": "N_WEAK", "battery_pct": 12.0, "rssi_dbm": -110.0, "pdr": 0.40, "rtt_ms": 500.0, "hop_count": 1}
        ]
    ]
    ranked_paths = alice.rank_fuzzy_paths(candidate_paths, mode="STANDARD")
    assert len(ranked_paths) == 2
    assert ranked_paths[0]["is_viable"] is True

    # 5. Engine Anti-Replay Sliding Window Check
    valid_1, reason_1 = alice.verify_anti_replay("PEER_BOB", seq_num=50, epoch=1)
    assert valid_1 is True
    assert reason_1 == "OK_IN_ORDER"

    # Replay attack attempt
    valid_replay, reason_replay = alice.verify_anti_replay("PEER_BOB", seq_num=50, epoch=1)
    assert valid_replay is False
    assert reason_replay == "REPLAY_DUPLICATE"

    # Out-of-order within window
    alice.verify_anti_replay("PEER_BOB", seq_num=55, epoch=1)
    valid_ooo, reason_ooo = alice.verify_anti_replay("PEER_BOB", seq_num=52, epoch=1)
    assert valid_ooo is True
    assert reason_ooo == "OK_OUT_OF_ORDER"

    state = alice.get_anti_replay_peer_state("PEER_BOB")
    assert state is not None
    assert state["max_seq"] == 55

    # 6. Tamper-evident Merkle Audit Ledger verification
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True

    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]

    assert "CQI_FEEDBACK_PROCESSED" in alice_events
    assert "LKH_REKEY_RECEIVED" in alice_events
    assert "LINK_ADAPTATION_EVALUATED" in alice_events
    assert "FUZZY_ROUTE_EVALUATED" in alice_events
    assert "FUZZY_PATHS_RANKED" in alice_events
    assert "ANTI_REPLAY_CHECK" in alice_events
    assert "CQI_FEEDBACK_SENT" in bob_events
    assert "LKH_REKEY_SENT" in bob_events

    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
