"""
Tests for Phase 11: Autonomous Mesh Self-Healing, Covert Traffic Camouflage,
Tactical Kademlia DHT, and Differential Privacy Spatial Obfuscation.
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

from mesh_healing import MeshHealingManager
from traffic_camouflage import TrafficCamouflageEngine, CHAFF_MAGIC_HEADER
from tactical_dht import TacticalDHT, hash_key_160
from spatial_privacy import SpatialPrivacyEngine, PrivacyBudget
from bundle_protocol import BundleProtocolManager, Bundle, BundlePriority
from network import GhostEngine


def test_mesh_partition_detection_and_bridge_promotion():
    """Verify BFS graph component discovery, partition detection, fringe bridge ranking, and link restitching."""
    mgr = MeshHealingManager(local_node_id="NODE_A")
    
    # Establish Cluster 1: A - B - C (B connects both A and C)
    mgr.update_link("NODE_A", "NODE_B")
    mgr.update_link("NODE_B", "NODE_C")
    
    # Establish Cluster 2: D - E
    mgr.update_link("NODE_D", "NODE_E")
    
    # Network is partitioned into two disconnected components
    assert mgr.is_partitioned() is True
    comps = mgr.get_connected_components()
    assert len(comps) == 2
    
    local_comp = mgr.find_local_component()
    assert local_comp == {"NODE_A", "NODE_B", "NODE_C"}
    
    # Fringe bridge candidate election: Node B has degree 2 (highest connectivity in Cluster 1)
    fringe_ranked = mgr.elect_fringe_bridge_nodes(local_comp)
    assert len(fringe_ranked) == 3
    assert fringe_ranked[0] == "NODE_B"
    
    # Promote Node B to active gateway bridge mode
    promo = mgr.promote_node_to_bridge("NODE_B")
    assert promo["status"] == "PROMOTED_BRIDGE"
    assert promo["beacon_multiplier"] == 2.5
    assert "NODE_B" in mgr.promoted_bridges
    
    # Mobile bridge connects C - D, restitching the partition
    mgr.update_link("NODE_C", "NODE_D")
    assert mgr.is_partitioned() is False
    assert len(mgr.get_connected_components()) == 1
    
    # Demote bridge once healed
    mgr.demote_bridge_node("NODE_B")
    assert "NODE_B" not in mgr.promoted_bridges


def test_traffic_camouflage_poisson_timing_and_chaff():
    """Verify Poisson process inter-arrival interval generation and dummy chaff frame injection."""
    engine = TrafficCamouflageEngine(mean_rate_lambda=2.0, min_interval_sec=0.05, max_interval_sec=3.0, enable_chaff=True)
    
    # 1. Poisson exponential distribution interval checks
    intervals = [engine.generate_next_interval() for _ in range(50)]
    for iv in intervals:
        assert 0.05 <= iv <= 3.0
    # Mean of exponential distribution with lambda=2.0 is 1/lambda = 0.5
    avg_interval = sum(intervals) / len(intervals)
    assert 0.1 <= avg_interval <= 1.5
    
    # 2. Dummy Chaff Packet Generation & Detection
    chaff_pkt = engine.generate_chaff_packet(target_size_bytes=64)
    assert len(chaff_pkt) == 64
    assert chaff_pkt.startswith(CHAFF_MAGIC_HEADER)
    assert engine.is_chaff_packet(chaff_pkt) is True
    
    real_data = b"AUTHENTICATED_GHOSTNET_PAYLOAD"
    assert engine.is_chaff_packet(real_data) is False
    
    # 3. Covert Schedule Shaping
    real_packets = [b"MSG_ALPHA", b"MSG_BRAVO", b"MSG_CHARLIE"]
    scheduled = engine.schedule_transmissions(real_packets, start_time=100.0)
    assert len(scheduled) >= 3
    
    # Verify chronological ordering
    timestamps = [s[0] for s in scheduled]
    assert timestamps == sorted(timestamps)
    
    # Verify real packets are present
    real_entries = [s for s in scheduled if not s[2]]
    assert len(real_entries) == 3


def test_tactical_dht_xor_metric_and_k_buckets():
    """Verify 160-bit SHA-1 key hashing, XOR distance metric sorting, and decentralized key-value storage."""
    dht = TacticalDHT(local_node_id_str="TACTICAL_BASE_HQ", k_size=4)
    
    # Verify 160-bit integer hash output
    h_int = hash_key_160("asset/rendezvous/grid_7")
    assert isinstance(h_int, int)
    assert h_int > 0
    assert h_int.bit_length() <= 160
    
    # Register swarm peers into k-buckets
    peers = ["NODE_PATROL_1", "NODE_PATROL_2", "NODE_MEDIC_3", "NODE_RECON_4", "NODE_RELAY_5"]
    for p in peers:
        dht.update_peer(p, {"callsign": p, "online": True})
        
    # Query closest nodes to target key using XOR distance
    target_key = hash_key_160("asset/rendezvous/grid_7")
    closest = dht.find_closest_nodes(target_key_int=target_key, count=3)
    assert len(closest) <= 3
    
    # Validate strictly ascending XOR distance
    distances = [nid ^ target_key for nid, info in closest]
    assert distances == sorted(distances)
    
    # Local DHT Key-Value Storage & Retrieval
    val_data = {"grid": "SECTOR_44_BRAVO", "frequency": 903.5, "callsign": "Overwatch"}
    k_stored = dht.store_value("asset/rendezvous/grid_7", val_data, ttl_seconds=3600.0)
    assert k_stored == target_key
    
    retrieved = dht.get_value("asset/rendezvous/grid_7")
    assert retrieved == val_data
    
    # Expired key check
    dht.store_value("asset/temp/short_lived", "EXPIRED_FLAG", ttl_seconds=-10.0)
    assert dht.get_value("asset/temp/short_lived") is None


def test_spatial_privacy_laplace_perturbation_and_budget():
    """Verify geo-indistinguishability via planar Laplace perturbation and differential privacy budget compliance."""
    # 1. Haversine distance accuracy check
    # Distance between identical points is 0
    assert SpatialPrivacyEngine.haversine_distance_meters(52.5200, 13.4050, 52.5200, 13.4050) == 0.0
    # 1 degree latitude is approximately 111.1 - 111.3 km
    dist_1deg = SpatialPrivacyEngine.haversine_distance_meters(0.0, 0.0, 1.0, 0.0)
    assert 111000.0 < dist_1deg < 112000.0
    
    # 2. Polar Laplace Obfuscation
    real_lat, real_lon = 40.7128, -74.0060  # New York City
    
    # High precision budget (epsilon=0.05 -> tighter radius)
    obf_high = SpatialPrivacyEngine.obfuscate_coordinates(real_lat, real_lon, epsilon=PrivacyBudget.HIGH_PRECISION)
    assert obf_high["real_lat"] == real_lat
    assert obf_high["real_lon"] == real_lon
    assert -90.0 <= obf_high["obfuscated_lat"] <= 90.0
    assert -180.0 <= obf_high["obfuscated_lon"] <= 180.0
    
    # Measured distance should closely match perturbation_meters
    measured_dist = SpatialPrivacyEngine.haversine_distance_meters(
        real_lat, real_lon,
        obf_high["obfuscated_lat"], obf_high["obfuscated_lon"]
    )
    assert abs(measured_dist - obf_high["perturbation_meters"]) < 5.0
    
    # Stealth mode budget (epsilon=0.001 -> wider obfuscation radius)
    obf_stealth = SpatialPrivacyEngine.obfuscate_coordinates(real_lat, real_lon, epsilon=PrivacyBudget.MAX_STEALTH)
    assert -90.0 <= obf_stealth["obfuscated_lat"] <= 90.0
    assert -180.0 <= obf_stealth["obfuscated_lon"] <= 180.0


def test_dtn_bundle_draining_on_partition_heal():
    """Verify draining of spooled DTN bundles across a reconnected topological bridge."""
    healing_mgr = MeshHealingManager(local_node_id="NODE_ALICE")
    bundle_mgr = BundleProtocolManager(local_node_id="NODE_ALICE")
    
    # Spool bundles while destination NODE_ZULU is partitioned and unreachable
    b1 = Bundle(
        bundle_id="B_ZULU_01",
        source_id="NODE_ALICE",
        destination_id="NODE_ZULU",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.EXPEDITED,
        payload=b"CRITICAL_ORDER"
    )
    b2 = Bundle(
        bundle_id="B_ZULU_02",
        source_id="NODE_ALICE",
        destination_id="NODE_ZULU",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.STANDARD,
        payload=b"SECONDARY_INTEL"
    )
    b_bcast = Bundle(
        bundle_id="B_BCAST_03",
        source_id="NODE_ALICE",
        destination_id="BROADCAST",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.BULK,
        payload=b"MAP_LAYER"
    )
    b_other = Bundle(
        bundle_id="B_OTHER_04",
        source_id="NODE_ALICE",
        destination_id="NODE_CHARLIE",
        creation_time=time.time(),
        lifetime_sec=3600.0,
        priority=BundlePriority.STANDARD,
        payload=b"UNRELATED_MSG"
    )
    
    bundle_mgr.store_bundle(b1)
    bundle_mgr.store_bundle(b2)
    bundle_mgr.store_bundle(b_bcast)
    bundle_mgr.store_bundle(b_other)
    
    # Drain bundles for NODE_ZULU across healed link (matches ZULU + BROADCAST = 3 bundles)
    drained_count = healing_mgr.drain_bundles_across_healed_link("NODE_ZULU", bundle_mgr)
    assert drained_count == 3


def test_phase11_live_engine_dht_and_chaff_dispatch():
    """Verify live TCP socket replication of Tactical DHT records, dummy chaff resilience, and Merkle audit logging."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase11_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase11_bob_")
    
    alice = GhostEngine(username="AliceP11", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP11", downloads_dir=dir_bob, enable_storage=False)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    # 1. Live DHT Replicated Store from Alice to Bob
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    k_int = alice.dht_store(
        key_str="CACHE_SUPPLY_DROP_ALPHA",
        value={"lat": 34.05, "lon": -118.25, "items": ["MEDKIT", "AMMO_556"]},
        ttl_seconds=3600.0,
        target_peer=target_addr
    )
    assert k_int > 0
    
    # Allow socket delivery to Bob
    time.sleep(0.8)
    
    # Verify Bob received and stored the record in his Tactical DHT
    bob_val = bob.dht_get("CACHE_SUPPLY_DROP_ALPHA")
    assert bob_val is not None
    assert bob_val["items"] == ["MEDKIT", "AMMO_556"]
    
    # 2. Live Dummy Chaff Transmission: Send raw high-entropy chaff frame to Bob's socket
    chaff_frame = alice.generate_chaff_frame(target_size=128)
    assert alice.is_chaff_frame(chaff_frame) is True
    
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        s.connect(("127.0.0.1", bob.tcp_port))
        s.sendall(chaff_frame + alice.HEADER_DELIMITER)
        
    time.sleep(0.5)
    
    # Bob silently absorbed the chaff packet without socket crash or corruption
    # Verify Bob can still serve DHT values
    assert bob.dht_get("CACHE_SUPPLY_DROP_ALPHA") is not None
    
    # 3. Spatial Privacy on Engine
    obf_res = alice.obfuscate_location(lat=48.8566, lon=2.3522, epsilon=0.01)
    assert "obfuscated_lat" in obf_res
    assert "obfuscated_lon" in obf_res
    assert -90.0 <= obf_res["obfuscated_lat"] <= 90.0
    
    # 4. Merkle audit ledger integrity check
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True
    
    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]
    assert "DHT_STORED" in alice_events
    assert "DHT_REPLICATED" in bob_events
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
