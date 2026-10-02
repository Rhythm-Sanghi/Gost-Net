"""
Tests for Phase 14: Covert Timing Channel (IPD Steganography), Tactical RF Link Budget Calculator,
Distributed Sub-Millisecond Mesh Clock Synchronisation, and RF Emission Signature Minimisation Advisor.
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

from covert_channel import CovertTimingChannel, KeyedTimingChannel
from link_budget import LinkBudgetCalculator, RadioParameters, Antenna, EnvironmentalLoss, LinkBudgetResult
from mesh_time_sync import MeshTimeSynchroniser, CristiansEstimator, MarzulloAlgorithm, SyncSample
from rf_signature import RFSignatureAdvisor, EmitterProfile, InterceptReceiverProfile, SignatureReport
from network import GhostEngine


def test_covert_timing_channel_encoding_and_decoding():
    """Verify IPD steganographic encoding into timing bucket centres and accurate decoding."""
    ctc = CovertTimingChannel(t_min_ms=10.0, t_max_ms=250.0, num_buckets=16, sigma_jitter_ms=0.5)
    assert ctc.bits_per_symbol == 4
    
    secret_payload = b"TACTICAL_EXTRACTION_ALPHA"
    delays = ctc.encode(secret_payload)
    assert len(delays) > 0
    for d in delays:
        assert 10.0 <= d <= 250.0
        
    recovered = ctc.decode(delays)
    assert recovered == secret_payload
    
    # KeyedTimingChannel variant
    shared_key = b"TOP_SECRET_MISSION_KEY_99"
    ktc = KeyedTimingChannel(key=shared_key, t_min_ms=10.0, t_max_ms=250.0, num_buckets=16, sigma_jitter_ms=0.5)
    keyed_delays = ktc.encode(secret_payload)
    
    # Decoding with correct key recovers payload
    recovered_keyed = ktc.decode(keyed_delays)
    assert recovered_keyed == secret_payload
    
    # Decoding with wrong key fails to recover original payload
    wrong_ktc = KeyedTimingChannel(key=b"WRONG_KEY_8888888888888888", t_min_ms=10.0, t_max_ms=250.0, num_buckets=16, sigma_jitter_ms=0.5)
    wrong_recovered = wrong_ktc.decode(keyed_delays)
    assert wrong_recovered != secret_payload
    
    # Capacity in bits per second
    bps = ctc.channel_capacity_bps(mean_ipd_ms=100.0)
    assert abs(bps - 40.0) < 1e-2


def test_tactical_link_budget_calculation_and_range():
    """Verify Friis path loss, thermal noise floor, SNR, link margin, and environmental rain/foliage attenuation."""
    radio = RadioParameters(tx_power_dbm=27.0, frequency_hz=915e6, bandwidth_hz=125e3, noise_figure_db=6.0, required_snr_db=-15.0)
    tx_ant = Antenna(gain_dbi=2.15, cable_loss_db=0.5)
    rx_ant = Antenna(gain_dbi=2.15, cable_loss_db=0.5)
    env_clear = EnvironmentalLoss()
    
    # 1. Clear-sky Link Budget at 1 km
    res_1km = LinkBudgetCalculator.calculate(radio, tx_ant, rx_ant, env_clear, distance_m=1000.0)
    assert 91.0 < res_1km.fspl_db < 92.5
    assert res_1km.noise_floor_dbm < -115.0
    assert res_1km.link_margin_db > 20.0  # LoRa SF12 has substantial margin at 1 km
    assert res_1km.max_range_m > 5000.0
    
    # 2. Environmental Degradation: heavy rain + dense foliage
    env_harsh = EnvironmentalLoss(rain_rate_mm_hr=50.0, foliage_depth_m=40.0, foliage_loss_db_per_m=0.25)
    res_harsh = LinkBudgetCalculator.calculate(radio, tx_ant, rx_ant, env_harsh, distance_m=1000.0)
    assert res_harsh.foliage_loss_db == 10.0
    assert res_harsh.link_margin_db < res_1km.link_margin_db
    
    # 3. Maximum range binary search
    max_range = LinkBudgetCalculator.max_range_meters(radio, tx_ant, rx_ant, env_clear)
    assert max_range > 1000.0
    
    # 4. BPSK BER estimate
    ber_high_snr = LinkBudgetCalculator.bpsk_ber(snr_linear=20.0)
    ber_low_snr = LinkBudgetCalculator.bpsk_ber(snr_linear=0.5)
    assert ber_high_snr < 1e-4
    assert ber_low_snr > 0.05


def test_mesh_time_synchronisation_cristian_and_marzullo():
    """Verify Cristian RTT and offset calculations, Marzullo Byzantine fault-tolerant clock intersection, and MeshTimeSynchroniser."""
    # 1. Cristian algorithm offset & RTT
    # Local T1=10.0, Remote T2=15.0, Remote T3=15.002, Local T4=10.006
    # RTT = (10.006 - 10.0) - (15.002 - 15.0) = 0.006 - 0.002 = 0.004 s (4 ms)
    # Offset = ((15.0 - 10.0) + (15.002 - 10.006)) / 2 = (5.0 + 4.996) / 2 = 4.998 s
    offset, rtt = CristiansEstimator.compute_offset(t1=10.0, t2=15.0, t3=15.002, t4=10.006)
    assert abs(rtt - 0.004) < 1e-6
    assert abs(offset - 4.998) < 1e-6
    
    lo, hi = CristiansEstimator.confidence_interval(offset, rtt)
    assert abs(lo - 4.996) < 1e-6
    assert abs(hi - 5.000) < 1e-6
    
    # 2. Marzullo intersection with Byzantine outlier
    # 3 honest peers reporting offsets around 0.100 s with +/- 0.010 uncertainty
    # 1 faulty/spoofed peer reporting offset at 5.000 s
    intervals = [
        (0.090, 0.110),
        (0.092, 0.112),
        (0.088, 0.108),
        (4.900, 5.100)   # Byzantine outlier
    ]
    
    # Requiring 0 faults fails to find consensus among all 4
    inter_0 = MarzulloAlgorithm.find_intersection(intervals, max_faulty=0)
    assert inter_0 is None
    
    # Tolerating 1 fault finds consensus among the 3 honest peers
    inter_1 = MarzulloAlgorithm.find_intersection(intervals, max_faulty=1)
    assert inter_1 is not None
    assert 0.088 <= inter_1[0] <= 0.100
    assert 0.100 <= inter_1[1] <= 0.112
    
    # 3. MeshTimeSynchroniser instance
    sync = MeshTimeSynchroniser(node_id="NODE_ALPHA")
    sync.record_sync_sample("PEER_BRAVO", t1=1.0, t2=1.050, t3=1.051, t4=1.003)
    sync.record_sync_sample("PEER_CHARLIE", t1=1.0, t2=1.049, t3=1.050, t4=1.003)
    st = sync.run_synchronisation_round(max_faulty=0)
    assert st.is_synchronised is True
    assert sync.precision_ms() < 10.0
    assert abs(sync.adjusted_time() - time.time()) > 0.0


def test_rf_signature_minimisation_advisor():
    """Verify EIRP computation, adversary intercept range estimation, emission score, and power reduction recommendations."""
    emitter = EmitterProfile(tx_power_dbm=27.0, antenna_gain_dbi=2.15, cable_loss_db=0.5, frequency_hz=915e6, duty_cycle=0.1, burst_duration_ms=50.0)
    intercept = InterceptReceiverProfile(noise_figure_db=3.0, required_snr_db=10.0, bandwidth_hz=1e6)
    
    # 1. EIRP: 27 + 2.15 - 0.5 = 28.65 dBm
    eirp_dbm, eirp_w = RFSignatureAdvisor.compute_eirp(emitter)
    assert abs(eirp_dbm - 28.65) < 1e-2
    assert 0.70 < eirp_w < 0.75
    
    # 2. Minimum Detectable Signal (MDS)
    mds = RFSignatureAdvisor.compute_mds(intercept)
    assert abs(mds - (-101.0)) < 1e-2
    
    # 3. Passive intercept range
    int_range_m = RFSignatureAdvisor.compute_intercept_range(emitter, intercept)
    assert int_range_m > 500.0
    
    # 4. Emission threat score in [0.0, 1.0]
    score = RFSignatureAdvisor.emission_score(emitter, intercept)
    assert 0.0 < score < 1.0
    
    # 5. Recommendation report
    rep = RFSignatureAdvisor.recommend(emitter, intercept, link_margin_db=12.0)
    assert isinstance(rep, SignatureReport)
    # Available link margin was 12 dB -> recommends reducing Tx power by 12 dB (from 27 to 15 dBm)
    assert abs(rep.recommended_tx_power_dbm - 15.0) < 1e-2
    assert rep.recommended_burst_duration_ms <= 20.0
    
    # 6. Frequency ranking: higher frequency has shorter intercept range
    freqs = [433e6, 915e6, 2.4e9]
    ranked = RFSignatureAdvisor.rank_frequencies(freqs, emitter, intercept)
    assert len(ranked) == 3
    # Ascending intercept range: 2.4 GHz first, 433 MHz last
    assert ranked[0][0] == 2.4e9
    assert ranked[-1][0] == 433e6


def test_edge_cases_covert_timing_and_link_budget():
    """Verify edge cases for empty payloads, zero distances, zero rain, and empty sample lists."""
    ctc = CovertTimingChannel()
    assert ctc.decode([]) == b""
    assert ctc.channel_capacity_bps(mean_ipd_ms=0.0) == 0.0
    
    # Link budget zero distance
    assert LinkBudgetCalculator.free_space_path_loss_db(0.0, 915e6) == 0.0
    assert LinkBudgetCalculator.rain_attenuation_db(0.0, 915e6, 1000.0) == 0.0
    
    # Marzullo empty intervals
    assert MarzulloAlgorithm.find_intersection([], max_faulty=0) is None
    
    # MeshTimeSynchroniser empty state
    empty_sync = MeshTimeSynchroniser("EMPTY_NODE")
    st = empty_sync.run_synchronisation_round()
    assert st.is_synchronised is False


def test_phase14_live_engine_socket_integration():
    """Verify live GhostEngine socket replication for precision time synchronisation, link budget, and RF signature audit trails."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase14_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase14_bob_")
    
    alice = GhostEngine(username="AliceP14", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP14", downloads_dir=dir_bob, enable_storage=False)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    # 1. Live Cristian / Marzullo Precision Time Sync round over TCP Socket
    sync_notifications = []
    bob.on_time_sync_updated = lambda peer_id, offset, unc: sync_notifications.append((peer_id, offset, unc))
    
    target_addr = f"127.0.0.1:{alice.tcp_port}"
    ok = bob.request_peer_time_sync(target_addr)
    assert ok is True
    time.sleep(0.8)
    
    # Bob must have received Alice's timestamps and updated his synchronised clock
    assert len(sync_notifications) >= 1
    assert bob.mesh_time_sync.state.is_synchronised is True
    assert bob.get_mesh_time_sync_precision() < 50.0  # Localhost LAN RTT is sub-millisecond
    
    # 2. Covert Timing Channel via Engine
    secret_msg = b"COVERT_TACTICAL_DATA_CHUNK"
    delays = bob.encode_covert_timing(secret_msg)
    assert len(delays) > 0
    recovered_msg = alice.decode_covert_timing(delays)
    assert recovered_msg == secret_msg
    
    # 3. Keyed Covert Timing Channel via Engine
    keyed_delays = bob.encode_covert_timing(secret_msg, key=b"SHARED_CONVOY_KEY")
    recovered_keyed = alice.decode_covert_timing(keyed_delays, key=b"SHARED_CONVOY_KEY")
    assert recovered_keyed == secret_msg
    
    # 4. Link Budget Calculation via Engine
    budget = alice.calculate_link_budget(distance_m=1200.0, tx_power_dbm=25.0)
    assert budget["viable"] is True
    assert budget["link_margin_db"] > 10.0
    assert budget["max_range_m"] > 1200.0
    
    # 5. RF Emission Signature Advisor via Engine
    sig = alice.evaluate_rf_signature(tx_power_dbm=27.0, link_margin_db=15.0)
    assert sig["emission_score"] > 0.0
    assert sig["recommended_tx_power_dbm"] == 12.0  # 27 - 15 = 12 dBm
    
    ranked_freqs = alice.rank_operational_frequencies([433e6, 915e6, 2.4e9])
    assert len(ranked_freqs) == 3
    
    # 6. Tamper-evident Merkle Audit Ledger verification
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True
    
    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]
    
    assert "TIME_SYNC_REQUEST_PROCESSED" in alice_events
    assert "COVERT_TIMING_DECODE" in alice_events
    assert "LINK_BUDGET_CALCULATED" in alice_events
    assert "RF_SIGNATURE_EVALUATED" in alice_events
    assert "TIME_SYNC_REQUEST_SENT" in bob_events
    assert "TIME_SYNC_SAMPLE_RECORDED" in bob_events
    assert "COVERT_TIMING_ENCODE" in bob_events
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
