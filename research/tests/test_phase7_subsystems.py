"""
Automated Verification Suite for Gost-Net Phase 7 Subsystems:
- Forward Error Correction (Reed-Solomon / Cauchy-Vandermonde MDS erasure coding)
- Adaptive FEC under electronic warfare jamming (K=4,M=2 -> K=2,M=4)
- Geofenced Geographic Mesh Casting (GeoCast) with circular & polygonal boundaries
- Spatial DTN muling (in-zone operator delivery vs. out-of-zone silent relay forwarding)
- Covert Stego Transport (RIFF/WAV LSB carrier injection & pseudo-random dispersion)
- Covert dead-drop storage deposit, discovery, and extraction
- Live Mesh Topology graph modeling, network diameter, and critical bridge identification
"""

import os
import sys
import struct
import tempfile
import pytest

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fec_engine import FECEngine
from geocast import GeoCastRouter, haversine_distance_meters, point_in_polygon
from stego_transport import (
    embed_payload_in_wav,
    extract_payload_from_wav,
    CovertDeadDropManager
)
from mesh_topology import TopologyGraphManager
from network import GhostEngine


def _create_synthetic_wav(sample_count: int = 5000) -> bytes:
    """Helper to generate a well-formed 16-bit 8000Hz mono PCM WAV container."""
    pcm_data = os.urandom(sample_count * 2)
    total_size = 36 + len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", total_size, b"WAVE", b"fmt ", 16, 1, 1, 8000, 16000, 2, 16, b"data", len(pcm_data)
    )
    return header + pcm_data


def test_dynamic_mesh_topology_modeling_and_critical_bridges():
    """Verify topology graph dynamics, network diameter calculation, and bridge centrality."""
    topo = TopologyGraphManager(local_node_id="AlphaHQ")
    
    # Register 5 tactical nodes
    topo.update_node("AlphaHQ", "Alpha HQ", battery=99, role="COMMAND")
    topo.update_node("Relay1", "Relay Unit 1", battery=85, role="RELAY")
    topo.update_node("BridgeNode", "Choke Point Node", battery=70, role="RELAY")
    topo.update_node("SquadA", "Recon Squad A", battery=65, role="FORWARD")
    topo.update_node("SquadB", "Recon Squad B", battery=60, role="FORWARD")
    
    # Topology layout:
    # AlphaHQ -- Relay1 -- BridgeNode -- SquadA
    #                                \-- SquadB
    topo.update_edge("AlphaHQ", "Relay1", pdr=0.99, rtt_ms=8.0)
    topo.update_edge("Relay1", "BridgeNode", pdr=0.95, rtt_ms=12.0)
    topo.update_edge("BridgeNode", "SquadA", pdr=0.92, rtt_ms=18.0)
    topo.update_edge("BridgeNode", "SquadB", pdr=0.90, rtt_ms=20.0)
    
    # 1. Connected components: fully connected (1 component containing all 5 nodes)
    comps = topo.get_connected_components()
    assert len(comps) == 1
    assert len(comps[0]) == 5
    
    # 2. Network diameter: longest shortest path (AlphaHQ -> SquadA/B is 3 hops)
    assert topo.calculate_network_diameter() == 3
    
    # 3. Critical bridge nodes: BridgeNode and Relay1 are cut-vertices
    bridges = topo.find_critical_bridge_nodes()
    assert "BridgeNode" in bridges
    assert "Relay1" in bridges
    # Leaf nodes are not bridges
    assert "SquadA" not in bridges
    assert "SquadB" not in bridges
    assert "AlphaHQ" not in bridges
    
    # 4. JSON and Graphviz exports
    json_export = topo.export_json()
    assert '"node_count": 5' in json_export
    assert '"edge_count": 4' in json_export
    
    dot_export = topo.export_dot()
    assert "graph MeshTopology {" in dot_export
    assert "BridgeNode" in dot_export


def test_ghost_engine_topology_summary():
    """Verify GhostEngine exposes real-time topology summary metrics."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_topo_")
    engine = GhostEngine(username="TopoTester", downloads_dir=temp_dir, enable_storage=False)
    
    summary = engine.get_mesh_topology_summary()
    assert summary["available"] is True
    assert summary["diameter"] == 0
    assert summary["node_count"] == 0
    
    # Feed peer beacon updates to engine's topology manager
    engine.topology_manager.update_node(engine.peer_id, "TopoTester")
    engine.topology_manager.update_node("Peer1", "Outpost-1")
    engine.topology_manager.update_edge(engine.peer_id, "Peer1")
    
    updated_summary = engine.get_mesh_topology_summary()
    assert updated_summary["node_count"] == 2
    assert updated_summary["edge_count"] == 1
    assert updated_summary["diameter"] == 1
    
    engine.stop()


def test_geocast_spatial_filtering_and_dtn_mule_forwarding():
    """Verify GeoCast selective delivery in-zone vs. silent DTN muling out-of-zone."""
    router = GeoCastRouter(dedup_ttl=60.0)
    
    # Operational Area: Berlin Brandenburg Gate (52.5163, 13.3777), 500m radius
    op_lat, op_lon = 52.5163, 13.3777
    geofence = {"center_lat": op_lat, "center_lon": op_lon, "radius_m": 500.0}
    
    packet = router.create_geocast_packet(
        geocast_id="geocast_berlin_01",
        sender_id="CommanderHQ",
        sender_name="AlphaCommand",
        message="SECURE_CORRIDOR_GREEN",
        geofence_type="CIRCULAR",
        geofence_params=geofence,
        ttl=6
    )
    
    # Case 1: In-zone operator (inside 500m radius, ~150m away at 52.5175, 13.3777)
    in_zone_res = router.process_incoming_geocast(packet, local_lat=52.5175, local_lon=13.3777)
    assert in_zone_res["should_deliver"] is True
    assert in_zone_res["should_forward"] is True
    assert in_zone_res["in_zone"] is True
    
    # Case 2: Duplicate packet received: dropped without delivery or forward
    dup_res = router.process_incoming_geocast(packet, local_lat=52.5175, local_lon=13.3777)
    assert dup_res["should_deliver"] is False
    assert dup_res["should_forward"] is False
    assert dup_res["reason"] == "DUPLICATE_PACKET"
    
    # Case 3: Out-of-zone operator (Munich: 48.1351, 11.5820)
    packet2 = router.create_geocast_packet(
        geocast_id="geocast_berlin_02",
        sender_id="CommanderHQ",
        sender_name="AlphaCommand",
        message="ZONE_RESTRICTED_DATA",
        geofence_type="CIRCULAR",
        geofence_params=geofence,
        ttl=4
    )
    out_res = router.process_incoming_geocast(packet2, local_lat=48.1351, local_lon=11.5820)
    # Delivered to operator? NO! Forwarded as DTN carrier mule? YES!
    assert out_res["should_deliver"] is False
    assert out_res["should_forward"] is True
    assert out_res["in_zone"] is False
    assert out_res["reason"] == "OUT_OF_ZONE_RELAY_ONLY"
    
    # Case 4: No GPS available (None) -> Fail closed
    packet3 = router.create_geocast_packet(
        geocast_id="geocast_berlin_03",
        sender_id="CommanderHQ",
        sender_name="AlphaCommand",
        message="GPS_DENIED_TEST",
        geofence_type="CIRCULAR",
        geofence_params=geofence,
        ttl=3
    )
    no_gps_res = router.process_incoming_geocast(packet3, local_lat=None, local_lon=None)
    assert no_gps_res["should_deliver"] is False
    assert no_gps_res["should_forward"] is True


def test_geocast_polygonal_geofence_filtering():
    """Verify polygonal non-circular geofence boundary calculations."""
    router = GeoCastRouter()
    
    # Irregular polygon vertices: Pentagon around sector
    polygon_vertices = [
        (10.0, 10.0),
        (15.0, 12.0),
        (17.0, 18.0),
        (12.0, 20.0),
        (8.0, 15.0)
    ]
    params = {"vertices": polygon_vertices}
    
    # Test point inside polygon
    assert router.is_in_geofence(12.0, 15.0, "POLYGONAL", params) is True
    assert router.is_in_geofence(14.0, 14.0, "POLYGONAL", params) is True
    
    # Test points outside polygon
    assert router.is_in_geofence(5.0, 5.0, "POLYGONAL", params) is False
    assert router.is_in_geofence(25.0, 25.0, "POLYGONAL", params) is False
    assert router.is_in_geofence(12.0, 5.0, "POLYGONAL", params) is False
    
    # Test point with None
    assert router.is_in_geofence(None, 15.0, "POLYGONAL", params) is False


def test_fec_adaptive_erasure_coding_under_severe_jamming():
    """Verify MDS erasure coding resilience under standard (33%) and severe (66%) packet loss."""
    # 1. Standard Posture (K=4 data, M=2 parity -> N=6 blocks)
    fec_standard = FECEngine(default_k=4, default_m=2)
    mission_payload = b"CRITICAL_TACTICAL_ASSET_COORDINATES_VECTOR_Z9" * 4
    blocks = fec_standard.encode(mission_payload)
    assert len(blocks) == 6
    
    # Simulate 33% packet loss (drop blocks 0 and 2; retain 1, 3, 4, 5)
    surviving_blocks = [blocks[1], blocks[3], blocks[4], blocks[5]]
    assert len(surviving_blocks) == 4
    reconstructed = fec_standard.decode(surviving_blocks)
    assert reconstructed == mission_payload
    
    # 2. Electronic Warfare Anti-Jamming Posture (K=2 data, M=4 parity -> N=6 blocks)
    fec_ew = FECEngine(default_k=2, default_m=4)
    ew_payload = b"EMERGENCY_EXTRACTION_AUTHENTICATION_TOKEN_9999"
    ew_blocks = fec_ew.encode(ew_payload)
    assert len(ew_blocks) == 6
    
    # Simulate 66% massive channel jamming loss: drop 4 out of 6 blocks!
    # Only 2 blocks survive (e.g. Parity block 1 and Parity block 3)
    severely_jammed_blocks = [ew_blocks[4], ew_blocks[5]]
    assert len(severely_jammed_blocks) == 2
    ew_reconstructed = fec_ew.decode(severely_jammed_blocks)
    assert ew_reconstructed == ew_payload
    
    # When surviving blocks < K (only 1 block for K=2), reconstruction fails cleanly
    assert fec_ew.decode([ew_blocks[5]]) is None


def test_stego_wav_bit_dispersion_and_tamper_detection():
    """Verify LSB WAV steganography carrier injection, keyed bit dispersion, and tamper resilience."""
    carrier_wav = _create_synthetic_wav(sample_count=6000)
    secret_key = os.urandom(32)
    sensitive_order = b"COVERT_OPERATIONAL_DROP_ZONE_GRID_4492"
    
    # Embed payload into WAV carrier
    stego_wav = embed_payload_in_wav(carrier_wav, sensitive_order, secret_key=secret_key)
    assert len(stego_wav) == len(carrier_wav)
    assert stego_wav[:4] == b"RIFF"
    
    # Extract with correct key
    extracted = extract_payload_from_wav(stego_wav, secret_key=secret_key)
    assert extracted == sensitive_order
    
    # Extract with incorrect key fails
    wrong_key = os.urandom(32)
    assert extract_payload_from_wav(stego_wav, secret_key=wrong_key) is None
    
    # Tamper detection: corrupt an embedded bit in the header
    from stego_transport import _get_pseudo_random_indices, STEGO_HEADER_SIZE
    header_indices = _get_pseudo_random_indices(len(carrier_wav) - 44, STEGO_HEADER_SIZE * 8, secret_key)
    tampered_bytes = bytearray(stego_wav)
    tampered_bytes[44 + header_indices[0]] ^= 0x01
    # Checksum or authentication failure prevents corrupted delivery
    assert extract_payload_from_wav(bytes(tampered_bytes), secret_key=secret_key) is None


def test_covert_dead_drop_deposit_scan_lifecycle():
    """Verify asynchronous covert dead drop deposit, filesystem isolation, and discovery."""
    temp_dir = tempfile.mkdtemp(prefix="ghostnet_deaddrop_")
    drop_manager = CovertDeadDropManager(storage_dir=os.path.join(temp_dir, "drops"))
    
    # Create base ambient audio carrier
    base_wav_path = os.path.join(temp_dir, "ambient_forest.wav")
    with open(base_wav_path, "wb") as f:
        f.write(_create_synthetic_wav(sample_count=8000))
        
    secret_key = os.urandom(32)
    intel_memo = b"ENEMY_RADAR_POSITION_LAT_53.11_LON_14.22"
    
    # 1. Deposit dead drop
    drop_path = drop_manager.deposit_dead_drop(
        base_wav_path=base_wav_path,
        output_filename="memo_intel_alpha.wav",
        payload_bytes=intel_memo,
        secret_key=secret_key
    )
    assert drop_path is not None
    assert os.path.exists(drop_path)
    
    # 2. Scanning with valid key recovers the memo
    scanned = drop_manager.scan_dead_drops(secret_key=secret_key)
    assert len(scanned) == 1
    filename, recovered_payload = scanned[0]
    assert filename == "memo_intel_alpha.wav"
    assert recovered_payload == intel_memo
    
    # 3. Scanning with unauthorized key returns nothing
    unauth_scan = drop_manager.scan_dead_drops(secret_key=os.urandom(32))
    assert len(unauth_scan) == 0
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
