"""
Tests for Phase 16: Protocol Chaos Fuzzer, Unified Tactical HUD & Dashboard Controller,
Multi-Bearer Autonomous Failover & Redundancy Controller, and In-Memory Panic Zeroization Scrubber.
"""

import os
import sys
import time
import json
import shutil
import tempfile
import pytest

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from chaos_fuzzer import ProtocolChaosFuzzer, FuzzResult
from tactical_hud import TacticalHUDController, HUDState, TacticalAlert
from bearer_failover import BearerFailoverController, BearerType, BearerProfile
from memory_scrubber import MemoryScrubber, ZeroizationReceipt
from network import GhostEngine


def test_protocol_chaos_fuzzer_and_mutation_containment():
    """Verify mutation strategies and parser crash containment under hostile malformed frames."""
    fuzzer = ProtocolChaosFuzzer(seed=1337)
    valid_packet = json.dumps({"type": "CHAT", "sender": "ALICE", "content": "GRID_CHECK"}).encode() + b"\n\n\n"

    # 1. Verify all individual mutation strategies
    for strat in ProtocolChaosFuzzer.MUTATION_STRATEGIES:
        mutated, used = fuzzer.mutate_packet(valid_packet, strategy=strat)
        assert len(mutated) >= 0
        assert used == strat

    # 2. Mock packet parser representing Gost-Net TCP wire reception
    def mock_parser(raw_bytes: bytes) -> bool:
        parts = raw_bytes.split(b"\n\n\n")
        if not parts or not parts[0]:
            return False
        header = json.loads(parts[0].decode('utf-8'))
        return header.get("type") == "CHAT"

    # 3. Execute 50 fuzzing iterations; every single one must be safely contained
    fuzz_results = fuzzer.fuzz_parser(mock_parser, valid_packet, iterations=50)
    assert len(fuzz_results) == 50
    for res in fuzz_results:
        assert res.parser_contained is True  # Zero uncaught fatal crashes


def test_tactical_hud_controller_and_ascii_rendering():
    """Verify diagnostic aggregation, alert queue bounding, and ASCII HUD dashboard generation."""
    hud = TacticalHUDController(callsign="RAVEN_LEADER", peer_id="NODE_TEST_ALPHA_99")

    # 1. Alert queue insertion and bounding (max 50)
    for i in range(60):
        hud.add_alert(severity="WARNING", subsystem="RF", message=f"Signal margin drop test #{i}")
    assert len(hud.alerts) == 50
    assert "test #59" in hud.alerts[-1].message

    # 2. Mock engine representing active operational node
    class MockEngine:
        def __init__(self):
            self.network_state = "SESSION_READY"
            self.adaptive_modulation = None
            self.rf_signature_advisor = None
            self.topology_manager = None
            self.anti_replay = None
            self.lkh_rekeying = None
            self.merkle_ledger = None
            self.anti_jamming = None

        def get_network_state_label(self):
            return "Secure session ready"

    mock_eng = MockEngine()
    state = hud.compile_hud_state(mock_eng)

    assert state.callsign == "RAVEN_LEADER"
    assert state.network_state == "Secure session ready"
    assert len(state.alerts) == 50

    # 3. ASCII Dashboard Rendering
    ascii_out = hud.render_ascii_dashboard(state)
    assert "[GOST-NET TACTICAL HUD]" in ascii_out
    assert "RAVEN_LEADER" in ascii_out
    assert "[RF & PHYSICAL LAYER]" in ascii_out
    assert "[MESH TOPOLOGY & ROUTING]" in ascii_out
    assert "[CRYPTOGRAPHY & INTEGRITY]" in ascii_out
    assert "[ELECTRONIC WARFARE (EW)]" in ascii_out
    assert "RECENT ALERTS" in ascii_out


def test_bearer_failover_controller_and_dynamic_redundancy():
    """Verify link health degradation, autonomous bearer failover, and hysteresis recovery."""
    controller = BearerFailoverController(failure_threshold=0.35, recovery_threshold=0.75, max_consecutive_failures=3)

    # 1. Register multiple interfaces with distinct priorities and MTUs
    controller.register_bearer(BearerType.LAN_TCP, priority=0, mtu_bytes=1500)
    controller.register_bearer(BearerType.WIFI_DIRECT, priority=1, mtu_bytes=1400)
    controller.register_bearer(BearerType.LORA_SERIAL, priority=2, mtu_bytes=240)

    # Initially LAN_TCP is active primary
    assert controller.active_bearer_type == BearerType.LAN_TCP
    assert controller.get_active_bearer().mtu_bytes == 1500

    # 2. Degrade LAN_TCP via consecutive failures
    controller.update_bearer_heartbeat(BearerType.LAN_TCP, rtt_ms=100.0, success=False)
    controller.update_bearer_heartbeat(BearerType.LAN_TCP, rtt_ms=100.0, success=False)
    controller.update_bearer_heartbeat(BearerType.LAN_TCP, rtt_ms=100.0, success=False)

    # Must automatically failover to next highest-priority viable bearer: WIFI_DIRECT
    assert controller.active_bearer_type == BearerType.WIFI_DIRECT
    assert len(controller.failover_history) >= 1

    # 3. Payload slicing per active bearer MTU
    big_payload = b"X" * 2000
    b_type, framed = controller.route_payload(big_payload)
    assert b_type == BearerType.WIFI_DIRECT
    assert len(framed) == 1400

    # 4. Hysteresis Recovery: LAN_TCP recovers with multiple low-latency successes
    for _ in range(5):
        controller.update_bearer_heartbeat(BearerType.LAN_TCP, rtt_ms=10.0, success=True)

    # Should switch back to LAN_TCP once health exceeds 0.75
    assert controller.active_bearer_type == BearerType.LAN_TCP


def test_memory_scrubber_multi_pass_panic_zeroization():
    """Verify in-place multi-pass cryptographic buffer sanitization and panic zeroization."""
    scrubber = MemoryScrubber()

    # 1. In-place buffer overwriting
    secret = bytearray(b"HIGHLY_CONFIDENTIAL_SQUAD_AES_KEY_32")
    orig_len = len(secret)
    overwritten = MemoryScrubber.scrub_buffer(secret, passes=3)
    assert overwritten == orig_len
    # Memory must be completely zeroized
    assert secret == bytearray(b"\x00" * orig_len)

    # 2. Buffer registry and panic zeroization
    key_buf_1 = bytearray(b"ECDH_PRIVATE_KEY_BYTES_384_RAND")
    key_buf_2 = bytearray(b"ROOT_IDENTITY_SEED_MATERIAL_64")

    scrubber.register_buffer(key_buf_1)
    scrubber.register_buffer(key_buf_2)

    receipt = scrubber.execute_panic_zeroization()
    assert isinstance(receipt, ZeroizationReceipt)
    assert receipt.buffers_scrubbed_count == 2
    assert receipt.bytes_overwritten_total == len(key_buf_1) + len(key_buf_2)
    assert receipt.passes_completed == 4
    assert len(receipt.verification_digest) == 64

    # Both buffers must now contain all 0x00
    assert key_buf_1 == bytearray(b"\x00" * len(key_buf_1))
    assert key_buf_2 == bytearray(b"\x00" * len(key_buf_2))


def test_phase16_edge_cases_and_boundary_conditions():
    """Verify edge cases for empty buffer scrub, empty bearer failover, and invalid bearer names."""
    # Empty buffer scrub
    assert MemoryScrubber.scrub_buffer(bytearray()) == 0
    assert MemoryScrubber.scrub_buffer(None) == 0

    # Bearer failover with no bearers
    empty_controller = BearerFailoverController()
    with pytest.raises(RuntimeError):
        empty_controller.route_payload(b"HELLO")

    # Unregister buffer
    scrubber = MemoryScrubber()
    b = bytearray(b"TEST")
    scrubber.register_buffer(b)
    scrubber.unregister_buffer(b)
    receipt = scrubber.execute_panic_zeroization()
    assert receipt.buffers_scrubbed_count == 0


def test_phase16_live_engine_socket_integration():
    """Verify live GhostEngine socket replication for tactical alerts, HUD compilation, bearer health, and panic scrub."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase16_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase16_bob_")

    alice = GhostEngine(username="AliceP16", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP16", downloads_dir=dir_bob, enable_storage=False)

    alice.start()
    bob.start()
    time.sleep(0.5)

    # 1. Live Tactical Alert transmission over TCP Socket
    alerts_received = []
    alice.on_tactical_alert_received = lambda alt: alerts_received.append(alt)

    target_alice = f"127.0.0.1:{alice.tcp_port}"
    ok = bob.send_tactical_alert(
        target_peer=target_alice,
        severity="CRITICAL",
        subsystem="ELECTRONIC_WARFARE",
        message="Hostile jammer active on 915 MHz"
    )
    assert ok is True
    time.sleep(0.6)

    # Alice must have received the alert and recorded it in her HUD
    assert len(alerts_received) == 1
    assert alerts_received[0]["severity"] == "CRITICAL"
    assert "Hostile jammer" in alerts_received[0]["message"]
    assert len(alice.tactical_hud.alerts) >= 1

    # 2. Compile Tactical HUD on Alice
    hud_state = alice.compile_tactical_hud()
    assert hud_state["callsign"] == "AliceP16"
    assert "amc_profile" in hud_state
    assert hud_state["alerts_count"] >= 1

    # 3. ASCII Dashboard Rendering
    ascii_hud = alice.render_tactical_hud_ascii()
    assert "[GOST-NET TACTICAL HUD]" in ascii_hud
    assert "AliceP16" in ascii_hud

    # 4. Bearer Failover Management on Alice
    alice.register_bearer_interface("LAN_TCP", priority=0, mtu_bytes=1500)
    alice.register_bearer_interface("WIFI_DIRECT", priority=1, mtu_bytes=1400)
    active_b = alice.update_bearer_link_health("LAN_TCP", rtt_ms=15.0, success=True)
    assert active_b == "LAN_TCP"

    # 5. In-Memory Panic Zeroization
    scrub_receipt = alice.execute_memory_panic_scrub()
    assert "passes" in scrub_receipt
    assert len(scrub_receipt["verification_digest"]) == 64

    # 6. Tamper-evident Merkle Audit Ledger verification
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True

    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]

    assert "TACTICAL_ALERT_RECEIVED" in alice_events
    assert "TACTICAL_HUD_COMPILED" in alice_events
    assert "BEARER_HEALTH_UPDATED" in alice_events
    assert "PANIC_ZEROIZATION_EXECUTED" in alice_events
    assert "TACTICAL_ALERT_SENT" in bob_events

    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
