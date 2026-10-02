"""
Tests for Phase 9: Delay-Tolerant Bundle Protocol, Ephemeral Beacons,
ATAK CoT Streaming Bridge, and Tamper-Evident Merkle Audit Ledger.
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

from bundle_protocol import BundleProtocolManager, Bundle, BundlePriority, CustodyAcceptanceSignal
from ephemeral_handshake import EphemeralBeaconManager
from cot_geojson import export_cot_xml, parse_cot_xml
from merkle_vault import MerkleAuditLedger, GENESIS_PREV_HASH
from network import GhostEngine


def test_bundle_protocol_priority_queuing_and_eviction():
    """Verify priority scheduling (EXPEDITED > STANDARD > BULK) and capacity eviction in BundleProtocolManager."""
    mgr = BundleProtocolManager(local_node_id="NODE_TEST_ALPHA", max_queue_size=3)
    
    b_bulk = Bundle(
        bundle_id="BUNDLE_BULK_01",
        source_id="NODE_TEST_ALPHA",
        destination_id="NODE_BRAVO",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.BULK,
        payload=b"MAP_TILE_DATA_RASTER"
    )
    b_standard = Bundle(
        bundle_id="BUNDLE_STD_02",
        source_id="NODE_TEST_ALPHA",
        destination_id="NODE_BRAVO",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.STANDARD,
        payload=b"TEXT_SITREP_ROUTINE"
    )
    b_expedited = Bundle(
        bundle_id="BUNDLE_EXP_03",
        source_id="NODE_TEST_ALPHA",
        destination_id="NODE_BRAVO",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.EXPEDITED,
        payload=b"URGENT_DISTRESS_AUTHENTICATION"
    )
    
    assert mgr.store_bundle(b_bulk) is True
    assert mgr.store_bundle(b_standard) is True
    assert mgr.store_bundle(b_expedited) is True
    
    # Priority scheduling: EXPEDITED must be selected first regardless of insertion order
    next_bundle = mgr.get_next_bundle_to_transmit()
    assert next_bundle is not None
    assert next_bundle.bundle_id == "BUNDLE_EXP_03"
    assert next_bundle.priority == BundlePriority.EXPEDITED
    
    # Queue is full (3/3). Storing another bundle must evict lowest priority (BULK)
    b_new_std = Bundle(
        bundle_id="BUNDLE_STD_04",
        source_id="NODE_TEST_ALPHA",
        destination_id="NODE_BRAVO",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.STANDARD,
        payload=b"TELEMETRY_REFRESH"
    )
    assert mgr.store_bundle(b_new_std) is True
    assert "BUNDLE_BULK_01" not in mgr.bundles  # Evicted
    assert "BUNDLE_EXP_03" in mgr.bundles      # Preserved
    assert "BUNDLE_STD_04" in mgr.bundles      # Inserted
    
    # Lifetime reclamation
    b_expired = Bundle(
        bundle_id="BUNDLE_EXPIRED_99",
        source_id="NODE_TEST_ALPHA",
        destination_id="NODE_BRAVO",
        creation_time=time.time() - 500.0,
        lifetime_sec=100.0,
        priority=BundlePriority.EXPEDITED,
        payload=b"OLD_SIGNAL"
    )
    # Storing expired bundle directly fails
    assert mgr.store_bundle(b_expired) is False


def test_bundle_protocol_custody_transfer_cas_cycle():
    """Verify RFC-aligned custody assumption, Custody Acceptance Signals (CAS), and custody release."""
    alice_mgr = BundleProtocolManager(local_node_id="NODE_ALICE")
    bob_mgr = BundleProtocolManager(local_node_id="NODE_BOB")
    
    bundle = Bundle(
        bundle_id="BUNDLE_MISSION_CRITICAL",
        source_id="NODE_ALICE",
        destination_id="HQ_STATION",
        creation_time=time.time(),
        lifetime_sec=7200.0,
        priority=BundlePriority.EXPEDITED,
        payload=b"ENCRYPTED_TARGETING_PACKAGE",
        custody_requested=True,
        current_custodian_id="NODE_ALICE"
    )
    
    # Alice stores bundle and holds initial custody
    alice_mgr.store_bundle(bundle)
    assert "BUNDLE_MISSION_CRITICAL" in alice_mgr.held_custodies
    
    # Bob receives bundle, stores it, and accepts custody
    bob_mgr.store_bundle(bundle)
    cas = bob_mgr.accept_custody(bundle.bundle_id)
    assert cas is not None
    assert cas.bundle_id == "BUNDLE_MISSION_CRITICAL"
    assert cas.custodian_id == "NODE_BOB"
    assert "BUNDLE_MISSION_CRITICAL" in bob_mgr.held_custodies
    
    # Bob transmits CAS back to Alice; Alice processes CAS and safely releases local custody
    alice_released = alice_mgr.process_cas(cas)
    assert alice_released is True
    assert "BUNDLE_MISSION_CRITICAL" not in alice_mgr.held_custodies
    assert alice_mgr.bundles["BUNDLE_MISSION_CRITICAL"].current_custodian_id == "NODE_BOB"


def test_ephemeral_beacon_pseudonym_rotation_and_unification():
    """Verify rotating pseudo-random beacon pseudonyms and shared-secret resolution with clock skew tolerance."""
    group_secret = b"DELTA_FORCE_COVERT_BEACON_KEY_2026"
    mgr = EphemeralBeaconManager(group_secret=group_secret, rotation_interval_sec=600.0)
    
    real_peer_id = "PEER_RECON_LEAD_01"
    
    # Within same 600s slot, token remains stable
    token_t0 = mgr.generate_ephemeral_token(real_peer_id, target_time=100.0)
    token_t300 = mgr.generate_ephemeral_token(real_peer_id, target_time=300.0)
    assert token_t0 == token_t300
    
    # After 600s rotation interval, token changes (anti-tracking SIGINT evasion)
    token_t700 = mgr.generate_ephemeral_token(real_peer_id, target_time=700.0)
    assert token_t700 != token_t0
    
    known_peers = [real_peer_id, "PEER_MEDIC_02", "PEER_RADIO_03"]
    
    # Authenticated node with shared secret resolves rotating pseudonym
    resolved = mgr.resolve_ephemeral_token(token_t700, known_peers, target_time=700.0)
    assert resolved == real_peer_id
    
    # Jitter tolerance: token generated at t=605 can still be resolved by node at t=595 (adjacent slot window)
    token_boundary = mgr.generate_ephemeral_token(real_peer_id, target_time=605.0)
    resolved_skew = mgr.resolve_ephemeral_token(token_boundary, known_peers, target_time=595.0)
    assert resolved_skew == real_peer_id
    
    # Adversary with wrong key fails to de-anonymize token
    adversary_mgr = EphemeralBeaconManager(group_secret=b"WRONG_ADVERSARY_KEY_FAIL", rotation_interval_sec=600.0)
    adversary_resolved = adversary_mgr.resolve_ephemeral_token(token_t0, known_peers, target_time=100.0)
    assert adversary_resolved is None


def test_atak_cot_xml_bi_directional_translation():
    """Verify conversion between Gost-Net tactical telemetry and ATAK Cursor-on-Target 2.0 XML."""
    tactical_event = {
        "uid": "GHOST-BEACON-ALPHA-77",
        "callsign": "Overwatch-1",
        "lat": 37.7749,
        "lon": -122.4194,
        "hae": 45.2,
        "ce": 5.0,
        "le": 8.0,
        "marker_type": "rally",
        "remarks": "Tactical Rally Point Bravo"
    }
    
    # 1. Export to Cursor-on-Target XML
    cot_xml = export_cot_xml(tactical_event)
    assert isinstance(cot_xml, str)
    assert '<event version="2.0"' in cot_xml
    assert 'uid="GHOST-BEACON-ALPHA-77"' in cot_xml
    assert 'lat="37.774900"' in cot_xml
    assert 'lon="-122.419400"' in cot_xml
    assert 'hae="45.2"' in cot_xml
    assert 'callsign="Overwatch-1"' in cot_xml
    
    # 2. Parse Cursor-on-Target XML back to Gost-Net representation
    parsed = parse_cot_xml(cot_xml)
    assert parsed is not None
    assert parsed["uid"] == "GHOST-BEACON-ALPHA-77"
    assert parsed["callsign"] == "Overwatch-1"
    assert abs(parsed["lat"] - 37.7749) < 1e-4
    assert abs(parsed["lon"] - -122.4194) < 1e-4
    assert abs(parsed["hae"] - 45.2) < 1e-1
    assert parsed["marker_type"] == "rally"


def test_merkle_audit_ledger_immutability_and_tamper_detection():
    """Verify unbroken append-only Merkle hash chain, inclusion proofs, and cryptographic tamper detection."""
    ledger = MerkleAuditLedger(genesis_salt=b"TACTICAL_MISSION_SECTOR_7")
    
    # Append sequential tactical operations
    rec0 = ledger.append_event("SYSTEM_BOOT", {"firmware": "v2.8.4", "node": "ALFA_1"})
    rec1 = ledger.append_event("WAYPOINT_DROP", {"lat": 52.5200, "lon": 13.4050, "label": "DROP_ZONE_1"})
    rec2 = ledger.append_event("REVOCATION_ISSUED", {"target_peer": "COMPROMISED_UNIT_9"})
    rec3 = ledger.append_event("ZEROIZE_ACK", {"status": "SUCCESS"})
    
    assert len(ledger.entries) == 4
    assert rec0["prev_hash"] == GENESIS_PREV_HASH
    assert rec1["prev_hash"] == rec0["entry_hash"]
    assert rec2["prev_hash"] == rec1["entry_hash"]
    assert rec3["prev_hash"] == rec2["entry_hash"]
    
    # Verify pristine integrity
    is_valid, corrupted_idx, reason = ledger.verify_integrity()
    assert is_valid is True
    assert corrupted_idx is None
    assert reason == "VERIFIED_INTEGRITY"
    
    # Export audit proof for record 2
    proof = ledger.generate_audit_proof(2)
    assert proof is not None
    assert proof["target_index"] == 2
    assert proof["entry_hash"] == rec2["entry_hash"]
    assert len(proof["audit_path"]) == 4
    
    # Tamper Simulation: Malicious adversary modifies payload of record 1 in memory or DB
    original_hash = ledger.entries[1]["payload_hash"]
    ledger.entries[1]["payload_hash"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    
    tamper_valid, tamper_idx, tamper_reason = ledger.verify_integrity()
    assert tamper_valid is False
    assert tamper_idx == 1
    assert "HASH_CORRUPTION" in tamper_reason
    
    # Restore original hash
    ledger.entries[1]["payload_hash"] = original_hash
    restore_valid, _, _ = ledger.verify_integrity()
    assert restore_valid is True


def test_dtn_bundle_live_socket_transfer_and_audit():
    """Verify end-to-end TCP DTN bundle transmission, custody handshake, and Merkle audit logging between GhostEngine nodes."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase9_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase9_bob_")
    
    alice = GhostEngine(username="AliceDTN", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobDTN", downloads_dir=dir_bob, enable_storage=False)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    bob_received_bundles = []
    bob.on_bundle_received = lambda b: bob_received_bundles.append(b)
    
    # Alice constructs a prioritized DTN Bundle with custody requested
    test_payload = b"CRITICAL_OPERATIONAL_SITREP_PHASE_9"
    bundle = Bundle(
        bundle_id="BUNDLE_SEC_ALPHA_99",
        source_id=alice.peer_id,
        destination_id=bob.peer_id,
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.EXPEDITED,
        payload=test_payload,
        custody_requested=True,
        current_custodian_id=alice.peer_id
    )
    
    # Alice sends bundle to Bob
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    sent = alice.send_dtn_bundle(target_ip=target_addr, bundle=bundle)
    assert sent is True
    
    # Allow socket delivery, storage, and CAS handshake
    time.sleep(1.2)
    
    # Verify Bob stored bundle and received payload
    assert len(bob_received_bundles) == 1
    rcvd_bundle = bob_received_bundles[0]
    assert rcvd_bundle.bundle_id == "BUNDLE_SEC_ALPHA_99"
    assert rcvd_bundle.payload == test_payload
    
    # Verify Merkle audit ledgers on both nodes
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True
    
    # Verify audit events were recorded
    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]
    assert "BUNDLE_DISPATCHED" in alice_events
    assert "BUNDLE_STORED" in bob_events
    assert "CUSTODY_ACCEPTED" in bob_events
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
