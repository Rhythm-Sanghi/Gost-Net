"""
Comprehensive automated unit test suite for Gost-Net core subsystems.
All tests run headless without requiring an active display or OpenGL context.
"""
import os
import sys
import shutil
import tempfile
import socket
import time
import json
import struct
import threading
import hashlib
from cryptography.fernet import Fernet
import pytest

# Ensure repository root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import ConfigManager
from src.database import PersistenceDatabase
from src.security import CryptoManager, DoubleRatchetSession, shred_file
from src.routing import RoutingTable
from src.auth_manager import AuthenticationManager
from src.steganography import get_or_create_default_carrier, encode_lsb, decode_lsb
from src.telemetry_logger import TelemetryLogger
from src.localization import LocalizationManager
from src.mission_analyzer import parse_csv_data, analyze_telemetry, decrypt_telemetry_file, derive_decryption_key
from src.network import GhostEngine
try:
    from acoustic_handshake import fingerprint_to_wav, wav_to_fingerprint
except ImportError:
    from research.acoustic_handshake import fingerprint_to_wav, wav_to_fingerprint

from src.network_utils import NetworkDetector
from src.p2p_platform_adapter import P2PPlatformAdapter
from src.storage import DatabaseManager
from src.diagnostics import get_diagnostics, encrypt_telemetry_file
from src.logger import activate_opsec, deactivate_opsec, is_opsec_active
from src.audio_manager import AudioManager, get_audio_manager, get_audio_duration
from src.gps_manager import GPSManager, get_gps_manager

try:
    from cot_geojson import export_cot_xml, parse_cot_xml, export_geojson, import_geojson
except ImportError:
    from research.cot_geojson import export_cot_xml, parse_cot_xml, export_geojson, import_geojson

from src.security import create_revocation_token, verify_revocation_token, derive_channel_key, encrypt_channel_message, decrypt_channel_message

try:
    from compact_framing import pack_compact_frame, unpack_compact_frame, json_to_compact_frame, compact_frame_to_json
    from transport_bearer import PacketFragmenter, TransportBearer, SerialRadioBearer, BearerManager
    from duty_cycler import DutyCycleManager, PowerProfile
    from multipath_routing import MultiPathRouter, find_disjoint_paths, wrap_onion_packet, unwrap_onion_layer
    from remote_wipe import RemoteWipeManager
    from fec_engine import FECEngine
    from geocast import GeoCastRouter, haversine_distance_meters, point_in_polygon
    from stego_transport import embed_payload_in_wav, extract_payload_from_wav, CovertDeadDropManager
    from mesh_topology import TopologyGraphManager
    from frequency_agility import FrequencyAgilityManager
    from proximity_crypto import ProximityVerifier, encode_geohash, get_adjacent_geohashes
    from quantum_resilient import OTPStreamVault
    from anti_jamming import JammingDetector, DefensivePosture
    from bundle_protocol import BundleProtocolManager, Bundle, BundlePriority, CustodyAcceptanceSignal
    from ephemeral_handshake import EphemeralBeaconManager
    from tak_bridge import TakMulticastBridge
    from merkle_vault import MerkleAuditLedger
    from cognitive_radio import SpectrumSensingEngine
    from swarm_consensus import SwarmConsensusManager, ConsensusProposal, ConsensusBallot
    from dtn_pubsub import DTNPubSubRouter, TopicMessage, BloomFilter
    from sovereign_identity import WebOfTrustKeyring, KeyCertification, TrustLevel, ShamirThresholdCrypto
    from mesh_healing import MeshHealingManager
    from traffic_camouflage import TrafficCamouflageEngine
    from tactical_dht import TacticalDHT, hash_key_160
    from spatial_privacy import SpatialPrivacyEngine, PrivacyBudget
    from collaborative_ecm import CollaborativeECMManager, JammerObservation
    from network_coding import RLNCEncoder, RLNCDecoder
    from qos_shaper import TacticalQoSShaper, QoSClass
    from zkp_auth import SchnorrZKP
    from post_quantum_kem import PostQuantumLatticeKEM
    from homomorphic_aggregation import PaillierHomomorphicAggregator
    from dsss_modulation import DSSSModulator
    from virtual_array import VirtualArrayCoordinator
    from covert_channel import CovertTimingChannel, KeyedTimingChannel
    from link_budget import (
        LinkBudgetCalculator, RadioParameters, Antenna, EnvironmentalLoss
    )
    from mesh_time_sync import (
        CristiansEstimator, MarzulloAlgorithm, MeshTimeSynchroniser
    )
    from rf_signature import (
        RFSignatureAdvisor, EmitterProfile, InterceptReceiverProfile
    )
except ImportError:
    pass

from service import LightweightGhostEngine




@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="ghostnet_unit_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestConfigManager:
    def test_config_load_and_update(self, temp_dir):
        config_path = os.path.join(temp_dir, "test_settings.json")
        cfg = ConfigManager(config_path)

        assert cfg.get("retention_hours") == 24
        assert cfg.get("dark_mode") is True

        cfg.set("retention_hours", 48)
        cfg.set("username", "Ghost-Lead")

        assert cfg.get("retention_hours") == 48
        assert cfg.get("username") == "Ghost-Lead"

        # Reload from disk to verify persistence
        cfg_reloaded = ConfigManager(config_path)
        assert cfg_reloaded.get("retention_hours") == 48
        assert cfg_reloaded.get("username") == "Ghost-Lead"


class TestCryptoSubsystem:
    def test_keypair_generation_and_export(self):
        crypto = CryptoManager()
        pub_bytes = crypto.get_public_key_bytes()
        sign_pub_bytes = crypto.get_signing_public_key_bytes()

        assert pub_bytes is not None and len(pub_bytes) > 0
        assert sign_pub_bytes is not None and len(sign_pub_bytes) == 32

    def test_ed25519_sign_and_verify(self):
        crypto = CryptoManager()
        msg = b"CRITICAL_COORDINATES: 34.0522,-118.2437"
        signature = crypto.sign_data(msg)
        assert signature is not None

        pub_key = crypto.get_signing_public_key_bytes()
        assert crypto.verify_signature(signature, msg, pub_key) is True
        assert crypto.verify_signature(signature, b"TAMPERED_PAYLOAD", pub_key) is False

    def test_ecdh_shared_secret_derivation(self):
        alice = CryptoManager()
        bob = CryptoManager()

        alice.set_peer_public_key("Bob", bob.get_public_key_bytes())
        bob.set_peer_public_key("Alice", alice.get_public_key_bytes())

        secret_alice = alice.derive_shared_secret("Bob")
        secret_bob = bob.derive_shared_secret("Alice")

        assert secret_alice is not None
        assert secret_bob is not None
        assert secret_alice == secret_bob


class TestDoubleRatchet:
    def test_ratchet_session_encryption_and_decryption(self):
        shared_secret = os.urandom(32)
        alice = DoubleRatchetSession(peer_id="Bob", shared_secret=shared_secret, is_initiator=True)
        bob = DoubleRatchetSession(peer_id="Alice", shared_secret=shared_secret, is_initiator=False)

        # Alice sends message 1 to Bob
        msg1_plaintext = b"Field report alpha-1"
        nonce1, ciphertext1 = alice.encrypt(msg1_plaintext)
        decrypted1 = bob.decrypt(ciphertext1, nonce1)
        assert decrypted1 == msg1_plaintext

        # Bob replies to Alice
        reply_plaintext = b"Roger that, team moving to rally point"
        nonce2, ciphertext2 = bob.encrypt(reply_plaintext)
        decrypted2 = alice.decrypt(ciphertext2, nonce2)
        assert decrypted2 == reply_plaintext


class TestRoutingTable:
    def test_direct_and_multi_hop_routes(self):
        rt = RoutingTable(max_route_age=30.0)

        # Add direct connection to Node-B
        assert rt.add_direct_route("Node-B") is True
        assert "Node-B" in rt.get_direct_peers()

        # Add multi-hop route to Node-C via Node-B
        assert rt.add_route("Node-C", next_hop_id="Node-B", metric=2, hops=["Node-B", "Node-C"]) is True

        route_c = rt.get_route("Node-C")
        assert route_c is not None
        assert route_c.next_hop_id == "Node-B"
        assert route_c.metric == 2

    def test_battery_metric_penalty(self):
        rt = RoutingTable(max_route_age=30.0)
        # Node with low battery (<20%) should get a penalty (+5 metric)
        rt.add_route("Node-D", next_hop_id="LowBatteryNode", metric=2, hops=["LowBatteryNode", "Node-D"], next_hop_battery=15)
        route_d = rt.get_route("Node-D")
        assert route_d is not None
        assert route_d.metric == 7  # 2 + 5 penalty

    def test_stale_route_pruning(self):
        rt = RoutingTable(max_route_age=0.01)
        rt.add_route("ExpiringNode", next_hop_id="Relay", metric=1, hops=["Relay", "ExpiringNode"])
        import time
        time.sleep(0.05)
        stale = rt.remove_stale_routes()
        assert "ExpiringNode" in stale
        assert rt.get_route("ExpiringNode") is None


class TestPersistenceDatabase:
    def test_peer_and_tofu_verification(self, temp_dir):
        db_path = os.path.join(temp_dir, "test.db")
        db = PersistenceDatabase(db_path)

        # Add peer
        db.save_peer("peer_007", "JamesBond", discovery_type="wifi_direct")
        peer = db.get_peer("peer_007")
        assert peer is not None
        assert peer["device_name"] == "JamesBond"
        assert peer["is_verified"] == 0

        # Update signing key & verify TOFU
        test_key_hex = "a" * 64
        db.update_peer_signing_key("peer_007", test_key_hex, is_verified=1)
        peer_updated = db.get_peer("peer_007")
        assert peer_updated["signing_key"] == test_key_hex
        assert peer_updated["is_verified"] == 1

    def test_message_persistence_and_retrieval(self, temp_dir):
        db_path = os.path.join(temp_dir, "test.db")
        db = PersistenceDatabase(db_path)

        # Save sent message
        assert db.save_message("peer_007", sender_type="sent", content_type="text", content="Check frequency 142.5") is True

        # Retrieve messages
        msgs = db.get_messages_for_peer("peer_007")
        assert len(msgs) >= 1
        assert msgs[0]["content"] == "Check frequency 142.5"
        assert msgs[0]["sender_type"] == "sent"

    def test_scrub_expired_messages_and_shred_file(self, temp_dir):
        db_path = os.path.join(temp_dir, "ttl_test.db")
        db = PersistenceDatabase(db_path)

        dummy_attachment = os.path.join(temp_dir, "temp_intel.txt")
        with open(dummy_attachment, "w") as f:
            f.write("SENSITIVE ATTACHMENT CONTENT")
        assert os.path.exists(dummy_attachment)

        import time
        now = time.time()
        # Expired file message (expired 10 seconds ago)
        db.save_message("peer_agent", "sent", "file", dummy_attachment, timestamp=now - 20, ttl_seconds=10)
        # Expired text message (expired 5 seconds ago)
        db.save_message("peer_agent", "sent", "text", "Self-destruct note", timestamp=now - 10, ttl_seconds=5)
        # Active text message (expires in 1 hour)
        db.save_message("peer_agent", "sent", "text", "Keep alive note", timestamp=now, ttl_seconds=3600)

        # Total count before scrub
        assert db.get_message_count_for_peer("peer_agent") == 3

        # Scrub expired messages
        deleted = db.scrub_expired_messages()
        assert deleted == 2
        assert db.get_message_count_for_peer("peer_agent") == 1

        # The expired attachment file must be shredded
        assert not os.path.exists(dummy_attachment)

        # Full shred everything
        assert db.shred_everything() is True
        assert not os.path.exists(db_path)


class TestAuthenticationManager:
    def test_pin_verification_and_duress(self, temp_dir):
        auth = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=True)
        # Default initialization in auth_manager initializes master "1234", duress "9999"
        assert auth.verify_master_pin("1234") is True
        assert auth.verify_master_pin("wrong") is False
        assert auth.verify_duress_pin("9999") is True
        assert auth.verify_duress_pin("1234") is False

    def test_decoy_mode_flag(self, temp_dir):
        auth = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=True)
        assert auth.is_decoy_mode_active() is False
        auth.activate_decoy_mode()
        assert auth.is_decoy_mode_active() is True

    def test_pin_strength_policy(self):
        # Trivial / weak patterns must be rejected under production policy
        assert AuthenticationManager.validate_pin_strength("", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("123", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("000000", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("111111", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("123456", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("654321", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("121212", allow_test_pins=False)[0] is False
        assert AuthenticationManager.validate_pin_strength("abcabc", allow_test_pins=False)[0] is False
        # Strong PINs / passphrases must pass
        assert AuthenticationManager.validate_pin_strength("849102", allow_test_pins=False)[0] is True
        assert AuthenticationManager.validate_pin_strength("Vault#Alpha2026", allow_test_pins=False)[0] is True

    def test_kdf_v1_to_v2_migration(self, temp_dir):
        # Simulate legacy v1 vault (80 bytes auth_secrets, 16 bytes db_salt)
        salt = os.urandom(16)
        import hashlib, base64
        m_hash = hashlib.pbkdf2_hmac('sha256', b'Master1234', salt, 65536, 32)
        d_hash = hashlib.pbkdf2_hmac('sha256', b'Duress9876', salt, 65536, 32)
        with open(os.path.join(temp_dir, '.auth_secrets'), 'wb') as f:
            f.write(salt + m_hash + d_hash)

        db_salt = os.urandom(16)
        with open(os.path.join(temp_dir, '.db_salt'), 'wb') as f:
            f.write(db_salt)
        kek = hashlib.pbkdf2_hmac('sha256', b'Master1234', db_salt, 100000, 32)
        cipher = Fernet(base64.urlsafe_b64encode(kek))
        original_db_key = Fernet.generate_key()
        with open(os.path.join(temp_dir, 'secret.key.enc'), 'wb') as f:
            f.write(cipher.encrypt(original_db_key))

        auth = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=False)
        assert auth.kdf_version == 1
        assert auth.identify_pin("Master1234") == "master"
        assert auth.kdf_version == 2
        assert auth.verify_duress_pin("Duress9876") is True

        decrypted_key = auth.get_or_create_db_key("Master1234")
        assert decrypted_key == original_db_key
        assert len(open(os.path.join(temp_dir, '.db_salt'), 'rb').read()) == 27

    def test_kdf_parser_corruption_and_edge_cases(self, temp_dir):
        # 1. Truncated GNKDF2 header (<95 bytes)
        auth_file = os.path.join(temp_dir, '.auth_secrets')
        with open(auth_file, 'wb') as f:
            f.write(b"GNKDF2\x00" + b"\x00" * 30)  # Only 37 bytes
        auth = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=False)
        assert auth.is_configured() is False
        assert auth.master_pin_hash is None

        # 2. Corrupt magic bytes with 95 bytes length
        with open(auth_file, 'wb') as f:
            f.write(b"CORRUPT" + b"\x00" * 88)
        auth = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=False)
        assert auth.is_configured() is False

        # 3. GNKDF2 header with zero iterations (fail-safe clamp to >= 1000)
        salt = os.urandom(16)
        m_hash = hashlib.pbkdf2_hmac('sha256', b'Master1234', salt, 200000, 32)
        d_hash = hashlib.pbkdf2_hmac('sha256', b'Duress9876', salt, 200000, 32)
        zero_iters = (0).to_bytes(4, 'big')
        with open(auth_file, 'wb') as f:
            f.write(b"GNKDF2\x00" + zero_iters + zero_iters + salt + m_hash + d_hash)
        auth = AuthenticationManager(storage_dir=temp_dir, auto_init_defaults=False)
        assert auth.master_iterations >= 1000
        assert auth.duress_iterations >= 1000
        # Verification should succeed because clamp uses 200000
        assert auth.verify_master_pin("Master1234") is True

        # 4. Truncated GNDBS2 salt (<27 bytes)
        salt_file = os.path.join(temp_dir, '.db_salt')
        with open(salt_file, 'wb') as f:
            f.write(b"GNDBS2\x00" + b"\x10\x20")  # Only 9 bytes
        # Should not raise exception
        key = auth.get_or_create_db_key("Master1234")
        assert key is not None and len(key) > 0

        # 5. GNDBS2 salt with zero iterations
        with open(salt_file, 'wb') as f:
            f.write(b"GNDBS2\x00" + (0).to_bytes(4, 'big') + os.urandom(16))
        # Should clamp to 200000 and not raise ValueError in PBKDF2
        kek = auth._derive_kek("Master1234", os.urandom(16), iterations=0)
        assert kek is not None and len(kek) == 32



class TestSteganographySubsystem:
    def test_carrier_generation_and_payload_embed_extract(self):
        carrier_bytes = get_or_create_default_carrier()
        assert carrier_bytes is not None and len(carrier_bytes) > 0

        secret_message = b"COVERT_TACTICAL_DATA_PACKET_99"
        stego_png_bytes = encode_lsb(carrier_bytes, secret_message)
        assert stego_png_bytes is not None
        assert stego_png_bytes != carrier_bytes

        extracted = decode_lsb(stego_png_bytes)
        assert extracted == secret_message


class TestTelemetryLogger:
    def test_telemetry_event_logging_and_flush(self, temp_dir):
        logger = TelemetryLogger(data_dir=temp_dir)
        logger.log_route_discovered("peer_alpha", metric=2)
        logger.log_packet_relayed("peer_alpha", "peer_beta")
        logger.record_metric("battery_level", "85", status="nominal")

        logger.flush()
        log_path = logger.get_log_path()
        assert os.path.exists(log_path)
        assert logger.get_log_size() > 0

        # Verify clear logs
        logger.clear_logs()
        assert logger.get_log_size() == 0


class TestLocalizationManager:
    def test_translation_loading_and_fallback(self):
        loc = LocalizationManager()
        # Verify languages loaded
        assert "en" in loc.translations
        assert len(loc.translations["en"]) > 0

        # Verify key translation
        radar_title = loc.get_text("radar_screen_title")
        assert radar_title is not None and len(radar_title) > 0

        # Switch language to Spanish
        assert loc.set_language("es") is True
        assert loc.get_current_language() == "es"
        es_title = loc.get_text("radar_screen_title")
        assert es_title is not None

        # Verify fallback for unknown key returns key
        assert loc.get_text("non_existent_key_xyz") == "non_existent_key_xyz"


class TestMissionAnalyzer:
    def test_csv_parsing_and_telemetry_analysis(self):
        sample_csv = (
            "timestamp,event_type,peer_id,metric,status\n"
            "2026-03-09T10:00:00.000Z,ROUTE_DISCOVERED,peer_1,2,active\n"
            "2026-03-09T10:01:00.000Z,PACKET_RELAYED,peer_1,0,relay_to:peer_2\n"
            "2026-03-09T10:02:00.000Z,ROUTE_DROPPED,peer_1,0,inactive\n"
        )
        rows = parse_csv_data(sample_csv)
        assert len(rows) == 3

        stats = analyze_telemetry(rows)
        assert stats is not None
        assert stats["total_events"] == 3
        assert stats["route_discovered"] == 1
        assert stats["route_dropped"] == 1
        assert stats["relay_events"] == 1
        assert stats["most_active_relay"] == "peer_1"

    def test_encrypted_telemetry_roundtrip(self, temp_dir):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        sample_csv = "timestamp,event_type,peer_id,metric,status\n2026-03-09T10:00:00.000Z,TEST,peer_0,1,ok\n"
        key = derive_decryption_key()
        nonce = os.urandom(12)
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(nonce, sample_csv.encode("utf-8"), None)

        enc_path = os.path.join(temp_dir, "test_telemetry.enc")
        with open(enc_path, "wb") as f:
            f.write(nonce + ciphertext)

        decrypted = decrypt_telemetry_file(enc_path)
        assert decrypted == sample_csv


class TestFieldGuideSubsystem:
    def test_offline_field_guide_lookup(self):
        received_messages = []

        def mock_on_message(sender, msg, timestamp):
            received_messages.append((sender, msg))

        engine = GhostEngine(on_message_received=mock_on_message, enable_storage=False)
        
        # Test general guide list
        result = engine.send_message("127.0.0.1", "/guide")
        assert result is True
        assert len(received_messages) == 1
        assert "Available field guides" in received_messages[0][1]

        # Test specific query
        result_water = engine.send_message("127.0.0.1", "/wiki water")
        assert result_water is True
        assert len(received_messages) == 2
        assert "Water Purification" in received_messages[1][1]


class TestAcousticHandshake:
    def test_dtmf_fingerprint_roundtrip(self):
        fingerprint = "c3f0a9b2"
        wav_data = fingerprint_to_wav(fingerprint, sample_rate=8000, tone_duration=0.08, silence_duration=0.04)
        assert wav_data.startswith(b"RIFF")
        assert len(wav_data) > 44

        decoded = wav_to_fingerprint(wav_data, sample_rate=8000, tone_duration=0.08, silence_duration=0.04)
        assert decoded == fingerprint


class TestNetworkDetector:
    def test_interface_enumeration_and_classification(self):
        interfaces = NetworkDetector.get_all_interfaces()
        assert isinstance(interfaces, dict)
        # Any active system running tests should have at least loopback or physical/virtual interface
        best_ip = NetworkDetector.get_best_interface()
        assert best_ip is None or isinstance(best_ip, str)
        net_type = NetworkDetector.get_network_type()
        assert isinstance(net_type, str)


from src.p2p_platform_adapter import P2PChannel
import sqlite3


class TestPlatformAdapter:
    def test_platform_adapter_initialization_and_status(self):
        adapter = P2PPlatformAdapter()
        assert len(adapter.enabled_channels) >= 2
        assert P2PChannel.UDP_BROADCAST in adapter.enabled_channels
        assert P2PChannel.TCP_SOCKET in adapter.enabled_channels

        peers = adapter.get_peers()
        assert isinstance(peers, list)
        adapter.shutdown()


class TestStorageDatabaseManager:
    def test_database_init_and_encryption_at_rest(self, temp_dir):
        db_path = os.path.join(temp_dir, "db", "ghostnet.db")
        key_path = os.path.join(temp_dir, "keys", "secret.key")
        db = DatabaseManager(db_path=db_path, key_path=key_path)

        assert os.path.exists(db_path)
        assert os.path.exists(key_path)

        db.save_peer("10.0.0.1", "Operator-Alpha")
        assert db.get_peer_username("10.0.0.1") == "Operator-Alpha"

        # Save sensitive message
        plaintext = "ALPHA: Coordinates confirmed at grid 44-bravo"
        db.save_message("10.0.0.1", "PEER", plaintext, "TEXT")

        # Decrypted retrieval via API
        history = db.get_history("10.0.0.1")
        assert len(history) == 1
        assert history[0]["content"] == plaintext
        assert history[0]["sender"] == "PEER"

        # Raw SQLite check to prove encryption at rest
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT content FROM messages WHERE peer_ip = '10.0.0.1'")
        raw_blob = cur.fetchone()[0]
        conn.close()

        assert raw_blob != plaintext.encode("utf-8")
        assert b"Coordinates confirmed" not in raw_blob

        db.close()

    def test_ephemeral_mode_does_not_persist(self, temp_dir):
        db_path = os.path.join(temp_dir, "ephem.db")
        key_path = os.path.join(temp_dir, "ephem.key")
        db = DatabaseManager(db_path=db_path, key_path=key_path)

        db.set_ephemeral_mode(True)
        db.save_message("10.0.0.2", "ME", "RAM_ONLY_BURST", "TEXT")

        # In-memory history available
        history = db.get_history("10.0.0.2")
        assert len(history) == 1
        assert history[0]["content"] == "RAM_ONLY_BURST"

        # Verify disk database contains 0 rows
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM messages")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0

        # Clear ephemeral messages
        db.clear_ephemeral_messages()
        assert len(db.get_history("10.0.0.2")) == 0
        db.close()

    def test_cleanup_and_export_chat(self, temp_dir):
        db_path = os.path.join(temp_dir, "clean.db")
        key_path = os.path.join(temp_dir, "clean.key")
        db = DatabaseManager(db_path=db_path, key_path=key_path)

        import time
        now = time.time()
        # Message from 48 hours ago
        db.save_message("10.0.0.3", "ME", "Old message", "TEXT", timestamp=now - (48 * 3600))
        # Message from now
        db.save_message("10.0.0.3", "PEER", "Recent message", "TEXT", timestamp=now)

        assert len(db.get_history("10.0.0.3")) == 2

        # Clean messages older than 24 hours
        deleted = db.cleanup_old_messages(hours=24)
        assert deleted == 1

        history = db.get_history("10.0.0.3")
        assert len(history) == 1
        assert history[0]["content"] == "Recent message"

        # Test export
        export_file = os.path.join(temp_dir, "exports", "chat_log.txt")
        assert db.export_chat("10.0.0.3", export_file) is True
        assert os.path.exists(export_file)

        with open(export_file, "r", encoding="utf-8") as f:
            exported_content = f.read()
        assert "Recent message" in exported_content

        # Test stats and vacuum
        stats = db.get_statistics()
        assert stats["total_messages"] == 1
        db.vacuum_database()

        # Delete peer history
        db.delete_peer_history("10.0.0.3")
        assert len(db.get_history("10.0.0.3")) == 0
        db.close()


class TestDiagnosticsSubsystem:
    def test_diagnostics_node_status_and_uptime(self):
        diag = get_diagnostics()
        status = diag.get_node_status()
        assert "local_ip" in status
        assert "local_mac" in status
        assert "uptime" in status

        assert diag.get_uptime_seconds() >= 0
        snapshot = diag.get_diagnostics_snapshot()
        assert "node_status" in snapshot
        assert "routing_table" in snapshot
        assert "active_sockets" in snapshot

    def test_hybrid_telemetry_encryption_roundtrip(self, temp_dir):
        telemetry_csv = (
            "timestamp,event_type,peer_id,metric,status\n"
            "2026-03-09T12:00:00.000Z,ROUTE_DISCOVERED,node_x,1,ready\n"
        )
        input_log = os.path.join(temp_dir, "raw_telemetry.csv")
        output_enc = os.path.join(temp_dir, "mission_export.enc")

        with open(input_log, "w", encoding="utf-8") as f:
            f.write(telemetry_csv)

        # Encrypt using diagnostics module (ECDH SECP384R1 + AES-GCM)
        success = encrypt_telemetry_file(input_log, output_enc)
        assert success is True
        assert os.path.exists(output_enc)

        # Decrypt using mission analyzer module
        decrypted_text = decrypt_telemetry_file(output_enc)
        assert decrypted_text.strip() == telemetry_csv.strip()


class TestOpsecLogger:
    def test_opsec_activation_and_deactivation(self):
        assert is_opsec_active() is False
        activate_opsec()
        assert is_opsec_active() is True
        # Output should be suppressed cleanly without errors
        print("This should be suppressed")
        deactivate_opsec()
        assert is_opsec_active() is False


class TestAntiForensics:
    def test_secure_shred_file(self, temp_dir):
        target_file = os.path.join(temp_dir, "confidential.dat")
        with open(target_file, "wb") as f:
            f.write(b"TOP_SECRET_COORDINATES_AND_ENCRYPTION_KEYS" * 50)
        
        assert os.path.exists(target_file)
        assert os.path.getsize(target_file) > 0

        shred_file(target_file)
        assert not os.path.exists(target_file)

        # Shred non-existent file should be a safe no-op
        shred_file(os.path.join(temp_dir, "ghost_file_missing.dat"))


class TestAudioManager:
    def test_audio_recording_and_cancel_lifecycle(self, temp_dir):
        audio_mgr = AudioManager()
        # Override recording_dir to clean temp_dir
        audio_mgr.recording_dir = temp_dir

        assert audio_mgr.start_recording() is True
        assert audio_mgr.is_recording is True
        assert audio_mgr.current_recording_path is not None
        assert os.path.exists(audio_mgr.current_recording_path)

        # Cancel recording should stop and securely shred the file
        recorded_path = audio_mgr.current_recording_path
        audio_mgr.cancel_recording()
        assert audio_mgr.is_recording is False
        assert not os.path.exists(recorded_path)

        # Cache shredding test
        assert audio_mgr.shred_cache() is True
        audio_mgr.cleanup()

        # Singleton check
        singleton = get_audio_manager()
        assert singleton is not None


class TestGPSManager:
    def test_gps_location_and_coordinates(self):
        gps_mgr = GPSManager()
        loc = gps_mgr.get_location()
        assert "latitude" in loc
        assert "longitude" in loc
        assert "accuracy" in loc

        coords = gps_mgr.get_coordinates()
        assert isinstance(coords, tuple)
        assert len(coords) == 2
        assert isinstance(coords[0], float)
        assert isinstance(coords[1], float)

        assert gps_mgr.start() is True
        assert gps_mgr.is_started is True
        gps_mgr.stop()
        assert gps_mgr.is_started is False

        singleton = get_gps_manager()
        assert singleton is not None


class TestLightweightServiceEngine:
    def test_beacon_handling_safe_json(self):
        engine = LightweightGhostEngine(username="PatrolNode")
        
        # Valid JSON beacon
        valid_payload = b'{"type": "BEACON", "username": "ScoutLeader", "timestamp": 1700000000.0}'
        engine._handle_beacon(valid_payload, ("192.168.1.155", 37020))

        assert "192.168.1.155" in engine.peers
        assert engine.peers["192.168.1.155"]["username"] == "ScoutLeader"

        # Malicious string payload (verifies no eval() execution)
        malicious_payload = b'__import__("sys").exit(1)'
        engine._handle_beacon(malicious_payload, ("192.168.1.199", 37020))
        assert "192.168.1.199" not in engine.peers


class TestPhase2NetworkHardening:
    """Rigorous tests for hostile network inputs, delivery lifecycle, deduplication, and atomic transfers."""

    def test_hostile_network_inputs_rejected(self):
        """Verify TCP server safely discards malformed JSON, non-dict headers, path traversals, and cleans up dropped transfers."""
        received = []
        engine = GhostEngine(on_message_received=lambda s, m, t: received.append(m), enable_storage=False)
        threading.Thread(target=engine.start, daemon=True).start()
        time.sleep(0.5)

        port = engine.TCP_PORT

        try:
            # 1. Non-JSON garbage
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', port))
            s.sendall(b"NOT_A_VALID_HEADER" + engine.HEADER_DELIMITER)
            s.close()

            # 2. Non-dict JSON header (e.g. integer or list)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', port))
            encrypted_list = engine._encrypt_message(json.dumps([1, 2, 3]))
            s.sendall(encrypted_list + engine.HEADER_DELIMITER)
            s.close()

            # 3. Path traversal attack in FILE header
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', port))
            header = {
                "type": "FILE",
                "filename": "../../traversal_test.bin",
                "filesize": 10
            }
            s.sendall(engine._encrypt_message(json.dumps(header)) + engine.HEADER_DELIMITER)
            s.sendall(b"0123456789")
            s.close()
            time.sleep(0.3)
            assert not os.path.exists("traversal_test.bin")
            assert not os.path.exists("../../traversal_test.bin")

            # 4. Truncated connection during file transfer cleans up .part file
            part_filename = "interrupted_test.dat"
            part_path = os.path.join(engine.downloads_dir, part_filename + ".part")
            final_path = os.path.join(engine.downloads_dir, part_filename)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', port))
            header = {
                "type": "FILE",
                "filename": part_filename,
                "filesize": 5000,
                "checksum": "fake_checksum"
            }
            s.sendall(engine._encrypt_message(json.dumps(header)) + engine.HEADER_DELIMITER)
            s.sendall(b"HALF_DATA_CHUNK")
            s.close()
            time.sleep(0.3)
            assert not os.path.exists(part_path)
            assert not os.path.exists(final_path)

        finally:
            engine.stop()

    def test_message_delivery_lifecycle_and_ack(self):
        """Verify delivery states: SENDING -> DELIVERED via TCP application ACK."""
        receiver_messages = []
        receiver = GhostEngine(
            on_message_received=lambda s, m, t: receiver_messages.append((s, m)),
            enable_storage=False
        )
        threading.Thread(target=receiver.start, daemon=True).start()
        time.sleep(0.5)

        sender = GhostEngine(enable_storage=False)
        threading.Thread(target=sender.start, daemon=True).start()
        time.sleep(0.5)

        status_updates = []
        def track_status(mid, st):
            status_updates.append(st)

        try:
            res = sender.send_message(
                f"127.0.0.1:{receiver.TCP_PORT}",
                "Status Check Test",
                delivery_callback=track_status,
                return_result=True
            )
            assert res.success is True
            assert res.state == "DELIVERED"
            assert "SENDING" in status_updates
            assert "DELIVERED" in status_updates
            
            # Poll for async message processing on receiver thread
            for _ in range(20):
                if len(receiver_messages) > 0:
                    break
                time.sleep(0.1)

            assert len(receiver_messages) == 1
            assert receiver_messages[0][1] == "Status Check Test"
        finally:
            sender.stop()
            receiver.stop()

    def test_message_deduplication(self):
        """Verify duplicate msg_ids are discarded without processing twice."""
        received = []
        receiver = GhostEngine(
            on_message_received=lambda s, m, t: received.append(m),
            enable_storage=False
        )
        threading.Thread(target=receiver.start, daemon=True).start()
        time.sleep(0.5)

        sender = GhostEngine(enable_storage=False)
        threading.Thread(target=sender.start, daemon=True).start()
        time.sleep(0.5)

        try:
            stable_id = "uniq_msg_001"
            res1 = sender.send_message(f"127.0.0.1:{receiver.TCP_PORT}", "Hello Once", msg_id=stable_id, return_result=True)
            res2 = sender.send_message(f"127.0.0.1:{receiver.TCP_PORT}", "Hello Once Duplicate", msg_id=stable_id, return_result=True)
            assert res1.success is True
            
            # Poll for async message processing on receiver thread
            for _ in range(20):
                if len(received) > 0:
                    break
                time.sleep(0.1)

            # Receiver must have deduplicated and only recorded the first message
            assert len(received) == 1
            assert received[0] == "Hello Once"
        finally:
            sender.stop()
            receiver.stop()


class TestEncryptedAtRestInspection:
    """Inspect raw SQLite file bytes on disk to confirm data is encrypted at rest."""

    def test_persistence_db_raw_bytes_inspection(self, tmp_path):
        from src.database import PersistenceDatabase
        test_db = str(tmp_path / "raw_inspect.db")
        secret_content = "TOP_SECRET_COORDINATES_448899"
        
        valid_key = Fernet.generate_key().decode()
        db = PersistenceDatabase(db_path=test_db, decrypted_key=valid_key)
        db.save_message("192.168.1.50", "me", "text", secret_content)

        with open(test_db, "rb") as f:
            raw_bytes = f.read()

        assert secret_content.encode('utf-8') not in raw_bytes


class TestTwoNodeCommunication:
    """Two independent GhostEngine nodes communicating over localhost."""

    def test_two_node_peer_discovery_and_messaging(self):
        node_a = GhostEngine(username="NodeAlpha", enable_storage=False)
        node_b = GhostEngine(username="NodeBravo", enable_storage=False)

        node_b_messages = []
        node_b.on_message_received = lambda s, m, t: node_b_messages.append((s, m))

        threading.Thread(target=node_a.start, daemon=True).start()
        threading.Thread(target=node_b.start, daemon=True).start()
        time.sleep(0.5)

        try:
            result = node_a.send_message(f"127.0.0.1:{node_b.TCP_PORT}", "Tactical Check-in Alpha to Bravo", return_result=True)
            assert result.success is True
            assert result.state == "DELIVERED"
            time.sleep(0.3)

            assert len(node_b_messages) == 1
            assert node_b_messages[0][1] == "Tactical Check-in Alpha to Bravo"
        finally:
            node_a.stop()
            node_b.stop()


class TestPhase3Hardening:
    """Comprehensive test coverage for Phase 3: Mesh Routing, Power Optimization, and Safety Numbers."""

    def test_safety_number_symmetry_and_determinism(self):
        from src.security import CryptoManager
        crypto_a = CryptoManager()
        crypto_b = CryptoManager()

        key_a_bytes = crypto_a.get_signing_public_key_bytes()
        key_b_bytes = crypto_b.get_signing_public_key_bytes()

        # Both parties must calculate the identical 12-digit safety number
        safety_num_a = crypto_a.compute_safety_number(key_b_bytes)
        safety_num_b = crypto_b.compute_safety_number(key_a_bytes)

        assert safety_num_a == safety_num_b
        assert len(safety_num_a) == 14  # XXXX-XXXX-XXXX
        assert safety_num_a.replace('-', '').isdigit()
        assert len(safety_num_a.replace('-', '')) == 12

        # Fingerprints must be colon-separated hex
        fp_a = crypto_a.compute_key_fingerprint(key_a_bytes)
        assert ":" in fp_a
        assert fp_a == fp_a.upper()

    def test_out_of_band_peer_verification_db(self, tmp_path):
        from src.database import PersistenceDatabase
        test_db = str(tmp_path / "verify_test.db")
        db = PersistenceDatabase(db_path=test_db)

        peer_id = "test_peer_99"
        db.save_peer(peer_id, "ReconOperator", discovery_type="LAN")
        assert db.is_peer_verified(peer_id) is False

        # Simulate out-of-band key verification
        db.set_peer_verified(peer_id, True)
        assert db.is_peer_verified(peer_id) is True

        # Revocation
        db.set_peer_verified(peer_id, False)
        assert db.is_peer_verified(peer_id) is False

    def test_adaptive_beaconing_parameters_and_reset(self):
        engine = GhostEngine(username="TestBeaconer", enable_storage=False)
        assert engine.min_beacon_interval == float(engine.BEACON_INTERVAL)
        assert engine.max_beacon_interval >= 30.0

        # Simulate backoff
        engine.current_beacon_interval = 25.0
        engine.static_beacon_cycles = 5
        engine.reset_beacon_backoff()

        assert engine.current_beacon_interval == engine.min_beacon_interval
        assert engine.static_beacon_cycles == 0

    def test_three_node_multihop_relay_mesh(self):
        """Verify 3-node simulated relay topology: Node A -> Node B (Relay) -> Node C."""
        node_a = GhostEngine(username="NodeA", enable_storage=False)
        node_b = GhostEngine(username="NodeB_Relay", enable_storage=False)
        node_c = GhostEngine(username="NodeC", enable_storage=False)

        node_c_received = []
        node_c.on_message_received = lambda sender, text, ts: node_c_received.append((sender, text))

        threading.Thread(target=node_a.start, daemon=True).start()
        threading.Thread(target=node_b.start, daemon=True).start()
        threading.Thread(target=node_c.start, daemon=True).start()
        time.sleep(0.5)

        try:
            # Node B knows Node C directly (direct neighbor)
            node_b.peers[f"127.0.0.1:{node_c.TCP_PORT}"] = {
                "username": node_c.username,
                "peer_id": node_c.peer_id,
                "tcp_port": node_c.TCP_PORT,
                "last_seen": time.time()
            }
            node_b.routing_table.add_direct_route(node_c.peer_id)

            # Node A knows Node B directly
            node_a.peers[f"127.0.0.1:{node_b.TCP_PORT}"] = {
                "username": node_b.username,
                "peer_id": node_b.peer_id,
                "tcp_port": node_b.TCP_PORT,
                "last_seen": time.time()
            }
            node_a.routing_table.add_direct_route(node_b.peer_id)

            # Node A learns route to Node C via next-hop Node B
            node_a.routing_table.add_route(
                destination_id=node_c.peer_id,
                next_hop_id=node_b.peer_id,
                metric=1,
                hops=[node_c.peer_id, node_b.peer_id]
            )

            # Node A sends message destined for Node C's peer_id
            result = node_a.send_message(node_c.peer_id, "Relay Check: Hello C from A through B", return_result=True)
            assert result.success is True

            # Wait for Node B relay forwarding worker to deliver to Node C
            for _ in range(30):
                if len(node_c_received) > 0:
                    break
                time.sleep(0.1)

            assert len(node_c_received) == 1
            # Message must be attributed to Node A, not the intermediary Node B
            assert node_c_received[0][0] == node_a.peer_id
            assert node_c_received[0][1] == "Relay Check: Hello C from A through B"
        finally:
            node_a.stop()
            node_b.stop()
            node_c.stop()

    def test_multihop_loop_prevention(self):
        """Verify packets containing local node in visited_nodes are dropped."""
        receiver = GhostEngine(username="LoopDefender", enable_storage=False)
        threading.Thread(target=receiver.start, daemon=True).start()
        time.sleep(0.3)

        try:
            # Craft looped header where receiver is already marked as visited
            looped_header = {
                "type": "TEXT",
                "content": "Ping-pong loop packet",
                "target_peer_id": "remote_target",
                "sender_peer_id": "malicious_node",
                "network_ttl": 5,
                "visited_nodes": [receiver.peer_id, "other_node"]
            }
            payload = json.dumps(looped_header)
            encrypted = receiver._encrypt_message(payload)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", receiver.TCP_PORT))
            s.sendall(encrypted + receiver.HEADER_DELIMITER)
            s.close()
            time.sleep(0.2)

            # Receiver should NOT forward or queue the packet
            assert len(receiver.pending_forwards) == 0
        finally:
            receiver.stop()

    def test_android_service_power_manager_safe_desktop_noop(self):
        from service import AndroidPowerManager, LightweightGhostEngine
        mgr = AndroidPowerManager()
        # Verify no crash on non-Android platform
        mgr.acquire()
        mgr.release()

        engine = LightweightGhostEngine(username="TestLight")
        assert engine.power_manager is not None


class TestPhase4Capabilities:
    """
    Automated verification of Phase 4 Tactical & Resiliency Upgrades:
    - Cursor-on-Target (CoT 2.0 XML) & RFC 7946 GeoJSON translation and bounds validation
    - Offline tactical waypoints persistence and TTL lifecycle scrubbing
    - Signed peer cryptographic revocation tokens and ingress filtering
    - Memory zeroization for ephemeral keys
    - Voice notes audio container integrity and duration detection
    - Resumable chunked file transfers and pacing
    """

    def test_cot_xml_generation_and_parsing(self):
        # 1. Test friendly peer position CoT event
        peer_data = {
            "uid": "ghost-alpha-01",
            "cot_type": "peer",
            "lat": 34.052235,
            "lon": -118.243683,
            "hae": 120.5,
            "ce": 5.0,
            "le": 8.0,
            "callsign": "ALPHA_LEAD",
            "remarks": "Patrol route checkpoint",
            "ttl_seconds": 1800
        }
        cot_xml = export_cot_xml(peer_data)
        assert "<event" in cot_xml
        assert 'version="2.0"' in cot_xml
        assert 'type="a-f-G-u-C"' in cot_xml
        assert 'uid="ghost-alpha-01"' in cot_xml
        assert 'lat="34.052235"' in cot_xml
        assert 'lon="-118.243683"' in cot_xml
        assert 'callsign="ALPHA_LEAD"' in cot_xml

        # 2. Test parsing back from XML
        parsed = parse_cot_xml(cot_xml)
        assert parsed is not None
        assert parsed["uid"] == "ghost-alpha-01"
        assert parsed["cot_type"] == "a-f-G-u-C"
        assert parsed["marker_type"] == "peer"
        assert abs(parsed["lat"] - 34.052235) < 0.0001
        assert abs(parsed["lon"] - (-118.243683)) < 0.0001
        assert abs(parsed["hae"] - 120.5) < 0.1
        assert parsed["callsign"] == "ALPHA_LEAD"
        assert parsed["remarks"] == "Patrol route checkpoint"

        # 3. Test tactical markers (rally, sos, hazard, cache)
        sos_xml = export_cot_xml({"uid": "sos-911", "type": "sos", "lat": 10.0, "lon": 20.0})
        assert 'type="b-m-p-s-m"' in sos_xml
        parsed_sos = parse_cot_xml(sos_xml)
        assert parsed_sos["marker_type"] == "sos"

        rally_xml = export_cot_xml({"uid": "rally-pt-1", "type": "rally", "lat": 10.0, "lon": 20.0})
        assert 'type="b-m-p-w-R"' in rally_xml
        parsed_rally = parse_cot_xml(rally_xml)
        assert parsed_rally["marker_type"] == "rally"

    def test_geojson_export_import_and_bounds_validation(self):
        items = [
            {
                "waypoint_id": "wp-base",
                "title": "Alpha Outpost",
                "description": "Primary operating cache",
                "waypoint_type": "cache",
                "lat": 37.7749,
                "lon": -122.4194,
                "alt": 45.0,
                "created_by": "Operator-1"
            },
            {
                "waypoint_id": "wp-hazard",
                "title": "Bridge Out",
                "description": "River impassable",
                "waypoint_type": "hazard",
                "lat": 37.7833,
                "lon": -122.4167,
                "alt": 10.0,
                "created_by": "Operator-2"
            }
        ]
        geojson_str = export_geojson(items)
        assert '"type": "FeatureCollection"' in geojson_str
        assert '"Point"' in geojson_str
        assert "Alpha Outpost" in geojson_str

        # Import valid GeoJSON
        imported = import_geojson(geojson_str)
        assert len(imported) == 2
        assert imported[0]["waypoint_id"] == "wp-base"
        assert imported[0]["title"] == "Alpha Outpost"
        assert abs(imported[0]["latitude"] - 37.7749) < 0.0001
        assert abs(imported[0]["longitude"] - (-122.4194)) < 0.0001

        # Reject out-of-bounds coordinates (RFC 7946 bounds: lat [-90, 90], lon [-180, 180])
        invalid_geojson = json.dumps({
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [250.0, 120.0]},
                    "properties": {"title": "Invalid Marker"}
                }
            ]
        })
        rejected = import_geojson(invalid_geojson)
        assert len(rejected) == 0

    def test_waypoint_database_persistence_and_ttl_scrubbing(self, temp_dir):
        db_path = os.path.join(temp_dir, "test_waypoints.db")
        db = PersistenceDatabase(db_path)

        now = time.time()
        # Active waypoint: expires in 2 hours
        db.save_waypoint(
            waypoint_id="wp-active",
            title="Safehouse",
            description="Operational sanctuary",
            waypoint_type="rally",
            latitude=45.5152,
            longitude=-122.6784,
            altitude=15.0,
            created_by="Unit-7",
            created_at=now,
            expires_at=now + 7200
        )

        # Expired waypoint: expired 1 hour ago
        db.save_waypoint(
            waypoint_id="wp-expired",
            title="Old Rendezvous",
            description="Do not use",
            waypoint_type="checkpoint",
            latitude=45.5200,
            longitude=-122.6800,
            altitude=10.0,
            created_by="Unit-7",
            created_at=now - 7200,
            expires_at=now - 3600
        )

        # Permanent waypoint: expires_at is None
        db.save_waypoint(
            waypoint_id="wp-permanent",
            title="HQ",
            description="Command post",
            waypoint_type="waypoint",
            latitude=45.5000,
            longitude=-122.6500,
            altitude=50.0,
            created_by="Command",
            created_at=now,
            expires_at=None
        )

        # Check all waypoints query filters out expired ones automatically
        active_wps = db.get_all_waypoints()
        active_ids = [w["waypoint_id"] for w in active_wps]
        assert "wp-active" in active_ids
        assert "wp-permanent" in active_ids
        assert "wp-expired" not in active_ids

        # Run explicit scrub_expired_waypoints
        scrubbed_count = db.scrub_expired_waypoints()
        assert scrubbed_count >= 1

        # Delete waypoint
        assert db.delete_waypoint("wp-active") is True
        remaining = db.get_all_waypoints()
        assert "wp-active" not in [w["waypoint_id"] for w in remaining]

    def test_signed_peer_revocation_token_and_verification(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization

        # Create operator signing key
        operator_priv = ed25519.Ed25519PrivateKey.generate()
        operator_pub = operator_priv.public_key()
        operator_pub_bytes = operator_pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        # Create valid revocation token
        token = create_revocation_token(
            peer_id="rogue_node_42",
            reason="Physical device seized",
            signing_private_key=operator_priv
        )
        assert token["peer_id"] == "rogue_node_42"
        assert token["reason"] == "Physical device seized"
        assert "signature" in token
        assert "signing_pubkey" in token

        # Verify with trusted pubkey bytes
        assert verify_revocation_token(token, trusted_pubkey_bytes=operator_pub_bytes) is True
        # Verify without explicit pubkey (using embedded signing_pubkey)
        assert verify_revocation_token(token) is True

        # Verify tampered token fails
        tampered_token = dict(token)
        tampered_token["reason"] = "Tampered message content"
        assert verify_revocation_token(tampered_token, trusted_pubkey_bytes=operator_pub_bytes) is False

        # Verify wrong public key fails
        other_priv = ed25519.Ed25519PrivateKey.generate()
        other_pub_bytes = other_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        assert verify_revocation_token(token, trusted_pubkey_bytes=other_pub_bytes) is False

    def test_peer_revocation_database_persistence(self, temp_dir):
        db_path = os.path.join(temp_dir, "test_revocation.db")
        db = PersistenceDatabase(db_path)

        assert db.is_peer_revoked("compromised_node") is False
        assert db.revoke_peer("compromised_node", reason="Key leak", signature="mock_sig") is True
        assert db.is_peer_revoked("compromised_node") is True

        revoked_list = db.get_revoked_peers()
        assert len(revoked_list) == 1
        assert revoked_list[0]["peer_id"] == "compromised_node"
        assert revoked_list[0]["reason"] == "Key leak"

        # Un-revoke
        assert db.unrevoke_peer("compromised_node") is True
        assert db.is_peer_revoked("compromised_node") is False

    def test_ephemeral_key_zeroization(self):
        crypto = CryptoManager()
        crypto.peer_aes_keys["peer_target_1"] = bytearray(b"0123456789abcdef0123456789abcdef")
        crypto.peer_keys["peer_target_1"] = bytearray(b"abcdef0123456789abcdef0123456789")

        assert "peer_target_1" in crypto.peer_aes_keys
        assert "peer_target_1" in crypto.peer_keys

        crypto.zeroize_ephemeral_keys()

        assert len(crypto.peer_aes_keys) == 0
        assert len(crypto.peer_keys) == 0

    def test_revoked_peer_ingress_filtering(self):
        receiver = GhostEngine(username="FirewallLead", enable_storage=False)
        threading.Thread(target=receiver.start, daemon=True).start()
        time.sleep(0.3)

        received_packets = []
        receiver.on_message_received = lambda msg, sender, callsign: received_packets.append((msg, sender))

        try:
            # Blacklist bad actor
            receiver.revoked_peers.add("blacklisted_peer_66")

            # Craft normal payload
            payload = json.dumps({
                "type": "TEXT",
                "content": "Malicious payload attempt",
                "target_peer_id": receiver.peer_id,
                "sender_peer_id": "blacklisted_peer_66",
                "network_ttl": 3,
                "visited_nodes": []
            })
            encrypted = receiver._encrypt_message(payload)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", receiver.TCP_PORT))
            s.sendall(encrypted + receiver.HEADER_DELIMITER)
            s.close()
            time.sleep(0.2)

            # Receiver must drop message from revoked peer
            assert len(received_packets) == 0
        finally:
            receiver.stop()

    def test_audio_recording_wav_container_and_duration(self, temp_dir):
        mgr = AudioManager()
        mgr.recording_dir = temp_dir
        
        # Test desktop recording start/stop
        assert mgr.start_recording() is True
        assert mgr.is_recording is True
        rec_path = mgr.current_recording_path
        assert rec_path is not None
        
        stopped_path = mgr.stop_recording()
        assert stopped_path == rec_path
        assert mgr.is_recording is False
        assert os.path.exists(rec_path)
        
        # Verify valid WAV container header
        with open(rec_path, "rb") as f:
            header = f.read(12)
            assert header.startswith(b"RIFF")
            assert header.endswith(b"WAVE")
            
        # Verify duration calculation
        dur = get_audio_duration(rec_path)
        assert dur > 0.5

    def test_resumable_file_chunk_transfer(self, temp_dir):
        """Verify .part file creation, offset seeking, and atomic file promotion."""
        engine = GhostEngine(username="FileTransceiver", enable_storage=False)
        engine.crypto_manager = None
        
        test_filename = "tactical_imagery.bin"
        final_filepath = os.path.join(temp_dir, test_filename)
        part_filepath = os.path.join(temp_dir, f"{test_filename}.part")
        
        total_data = b"0123456789ABCDEF" * 100  # 1600 bytes payload
        import hashlib
        expected_hash = hashlib.sha256(total_data).hexdigest()
        
        chunk1 = total_data[:800]
        chunk2 = total_data[800:]
        
        class DummyConn:
            def recv(self, n):
                return b""
        
        # 1. First chunk written at offset 0 (simulate network drop after 800 bytes)
        engine._handle_chunked_file_transfer(
            filepath=final_filepath,
            filesize=len(total_data),
            initial_bytes=len(chunk1),
            initial_data=chunk1,
            conn=DummyConn(),
            sender_ip="127.0.0.1",
            filename=test_filename,
            checksum=expected_hash,
            header={"offset": 0}
        )
        assert os.path.exists(part_filepath)
        assert os.path.getsize(part_filepath) == 800
        assert not os.path.exists(final_filepath)
        
        # 2. Resumed second chunk written at offset 800 (completes transfer)
        engine._handle_chunked_file_transfer(
            filepath=final_filepath,
            filesize=len(total_data),
            initial_bytes=len(chunk2),
            initial_data=chunk2,
            conn=DummyConn(),
            sender_ip="127.0.0.1",
            filename=test_filename,
            checksum=expected_hash,
            header={"offset": 800}
        )
        # Upon completion and checksum match, .part is atomically promoted
        assert not os.path.exists(part_filepath)
        assert os.path.exists(final_filepath)
        assert os.path.getsize(final_filepath) == len(total_data)
        with open(final_filepath, "rb") as f:
            assert f.read() == total_data


class TestPhase5Capabilities:
    """
    Automated verification of Phase 5 Tactical Mesh & Hardware OpSec:
    - Ultra-compact binary framing and adaptive zlib compression
    - Encrypted multi-party group channels and key derivation
    - Group channel persistence and message history
    - Mesh multicast relay and packet deduplication
    - AODV on-demand reactive route discovery (RREQ/RREP) and error propagation (RERR)
    - Exponential Moving Average (EMA) link quality scoring
    - Anti-tamper failed PIN attempts counter and automatic decoy mode flip
    - Dead Man's Switch heartbeat tracking and physical wipe on expiration
    """

    def test_compact_binary_framing_and_compression(self):
        # 1. Uncompressed short payload
        short_payload = b"Short plain text"
        frame = pack_compact_frame(
            packet_type="TEXT",
            payload_data=short_payload,
            seq_id=12345,
            ttl=8,
            auto_compress=True
        )
        unpacked = unpack_compact_frame(frame)
        assert unpacked is not None
        assert unpacked["packet_type"] == "TEXT"
        assert unpacked["seq_id"] == 12345
        assert unpacked["ttl"] == 8
        assert unpacked["is_compressed"] is False
        assert unpacked["payload"] == short_payload

        # 2. Large repetitive compressible payload (>128 bytes)
        large_payload = b"CONFIDENTIAL TACTICAL MESH PACKET DATA " * 10
        compressed_frame = pack_compact_frame(
            packet_type="GROUP_TEXT",
            payload_data=large_payload,
            seq_id=54321,
            auto_compress=True
        )
        unpacked_comp = unpack_compact_frame(compressed_frame)
        assert unpacked_comp is not None
        assert unpacked_comp["packet_type"] == "GROUP_TEXT"
        assert unpacked_comp["is_compressed"] is True
        # Verify frame size is smaller than original payload
        assert len(compressed_frame) < len(large_payload)
        # Verify decompressed content matches
        assert unpacked_comp["payload"] == large_payload

        # 3. JSON dictionary to compact frame conversion
        dict_payload = {
            "type": "LOCATION_UPDATE",
            "peer_id": "node_77",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "network_ttl": 5
        }
        json_frame = json_to_compact_frame(dict_payload)
        assert json_frame.startswith(b"GN")
        decoded_dict = compact_frame_to_json(json_frame)
        assert decoded_dict["type"] == "LOCATION_UPDATE"
        assert decoded_dict["peer_id"] == "node_77"
        assert decoded_dict["latitude"] == 37.7749

        # 4. Corrupted / truncated frame returns None
        assert unpack_compact_frame(b"XXbadframe") is None
        assert unpack_compact_frame(frame[:5]) is None

    def test_group_channel_key_derivation_and_encryption(self):
        salt = os.urandom(16)
        key1 = derive_channel_key("recon_team", "BravoPassphrase123", salt)
        key2 = derive_channel_key("recon_team", "BravoPassphrase123", salt)
        key3 = derive_channel_key("recon_team", "WrongPassphrase", salt)
        key4 = derive_channel_key("medic_net", "BravoPassphrase123", salt)

        assert key1 == key2
        assert key1 != key3
        assert key1 != key4
        assert len(key1) == 32

        # Encryption and Decryption
        plaintext = "Rendezvous at waypoint Alpha-01 at 0800Z"
        ciphertext = encrypt_channel_message(key1, plaintext)
        assert isinstance(ciphertext, str)
        assert ciphertext != plaintext

        decrypted = decrypt_channel_message(key1, ciphertext)
        assert decrypted == plaintext

        # Decryption with wrong key returns None
        wrong_decrypted = decrypt_channel_message(key3, ciphertext)
        assert wrong_decrypted is None

    def test_group_channels_database_persistence(self, temp_dir):
        db_path = os.path.join(temp_dir, "test_group_channels.db")
        db = PersistenceDatabase(db_path)

        now = time.time()
        assert db.create_group_channel("alpha_channel", "Alpha Squad", "salt_abc123", now) is True

        channels = db.get_all_group_channels()
        assert len(channels) == 1
        assert channels[0]["channel_id"] == "alpha_channel"
        assert channels[0]["channel_name"] == "Alpha Squad"

        # Save messages
        assert db.save_group_message("grp_msg_1", "alpha_channel", "node_1", "Lead", "Check in", now) is True
        assert db.save_group_message("grp_msg_2", "alpha_channel", "node_2", "Scout", "All quiet", now + 1.0) is True

        messages = db.get_group_messages("alpha_channel")
        assert len(messages) == 2
        assert messages[0]["content"] == "Check in"
        assert messages[1]["content"] == "All quiet"

        # Delete channel cascades to messages
        assert db.delete_group_channel("alpha_channel") is True
        assert len(db.get_all_group_channels()) == 0
        assert len(db.get_group_messages("alpha_channel")) == 0

    def test_group_channel_multicast_relay_and_deduplication(self):
        receiver = GhostEngine(username="MulticastReceiver", enable_storage=False)
        threading.Thread(target=receiver.start, daemon=True).start()
        time.sleep(0.3)

        received_group_msgs = []
        receiver.on_group_message_received = lambda ch, sender, name, msg, ts: received_group_msgs.append((ch, sender, msg))

        try:
            # Join channel
            assert receiver.join_group_channel("ops_net", "Ops Net", "OpsPassword456") is True
            key = receiver.channel_keys["ops_net"]

            # Craft group message
            raw_text = "Tactical regroup complete"
            enc_text = encrypt_channel_message(key, raw_text)

            msg_payload = {
                "type": "GROUP_TEXT",
                "message_id": "test_grp_msg_unique_101",
                "channel_id": "ops_net",
                "sender_peer_id": "sender_scout",
                "sender_name": "ScoutLead",
                "content": enc_text,
                "timestamp": time.time(),
                "network_ttl": 5,
                "visited_nodes": ["sender_scout"]
            }
            payload_str = json.dumps(msg_payload)
            encrypted = receiver._encrypt_message(payload_str)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", receiver.TCP_PORT))
            s.sendall(encrypted + receiver.HEADER_DELIMITER)
            s.close()
            time.sleep(0.2)

            assert len(received_group_msgs) == 1
            assert received_group_msgs[0][0] == "ops_net"
            assert received_group_msgs[0][1] == "sender_scout"
            assert received_group_msgs[0][2] == "Tactical regroup complete"

            # Re-send same message: verify deduplication ignores duplicate
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s2.connect(("127.0.0.1", receiver.TCP_PORT))
            s2.sendall(encrypted + receiver.HEADER_DELIMITER)
            s2.close()
            time.sleep(0.2)

            # Count should still be 1
            assert len(received_group_msgs) == 1
        finally:
            receiver.stop()

    def test_aodv_route_discovery_and_rrep(self):
        rt_a = RoutingTable()
        rt_b = RoutingTable()

        # Node A creates RREQ looking for Node B
        rreq = rt_a.create_rreq("NodeA", "NodeB")
        assert rreq["type"] == "RREQ"
        assert rreq["originator_id"] == "NodeA"
        assert rreq["destination_id"] == "NodeB"
        assert rreq["hop_count"] == 0

        # Node B processes RREQ: since Node B is the target destination, returns RREP
        rrep = rt_b.process_rreq(rreq, "NodeB")
        assert rrep is not None
        assert rrep["type"] == "RREP"
        assert rrep["destination_id"] == "NodeB"
        assert rrep["originator_id"] == "NodeA"

        # Node B should also have recorded reverse route to Node A
        route_to_a = rt_b.get_route("NodeA")
        assert route_to_a is not None
        assert route_to_a.next_hop_id == "NodeA"

        # Node A processes RREP: installs forward route to Node B
        installed = rt_a.process_rrep(rrep, "NodeA")
        assert installed is True
        route_to_b = rt_a.get_route("NodeB")
        assert route_to_b is not None
        assert route_to_b.destination_peer_id == "NodeB"
        assert route_to_b.route_status == "ACTIVE"

    def test_aodv_rerr_route_break_invalidation(self):
        rt = RoutingTable()
        rt.add_route("RemoteNodeZ", "IntermediaryHop", metric=2, hops=["RemoteNodeZ", "IntermediaryHop"])
        assert rt.get_route("RemoteNodeZ") is not None
        assert rt.get_route("RemoteNodeZ").route_status == "ACTIVE"

        # Broken link detected for IntermediaryHop
        rerr = rt.create_rerr("IntermediaryHop")
        assert rerr["type"] == "RERR"
        invalidated = rt.process_rerr(rerr)
        assert "RemoteNodeZ" in invalidated
        assert rt.get_route("RemoteNodeZ").route_status == "BROKEN"

    def test_link_quality_metric_ema(self):
        rt = RoutingTable()
        rt.add_direct_route("PeerLink1")

        # Initial default metric
        m0 = rt.get_link_metric("PeerLink1")
        assert m0["pdr"] == 1.0

        # Simulate transmission failure
        rt.update_link_metric("PeerLink1", rtt_ms=0.0, success=False)
        m1 = rt.get_link_metric("PeerLink1")
        assert m1["pdr"] < 1.0
        assert rt.get_route("PeerLink1").pdr == m1["pdr"]

        # Simulate subsequent fast successful transmissions
        rt.update_link_metric("PeerLink1", rtt_ms=15.0, success=True)
        m2 = rt.get_link_metric("PeerLink1")
        assert m2["pdr"] > m1["pdr"]
        assert m2["rtt_ms"] > 0.0

    def test_anti_tamper_failed_attempts_decoy_flip(self, temp_dir):
        auth = AuthenticationManager(temp_dir, auto_init_defaults=True)
        assert auth.get_failed_attempts() == 0
        assert auth.is_decoy_mode_active() is False

        # Attempt 4 invalid PIN entries
        for i in range(1, 5):
            assert auth.identify_pin("9998") is None
            assert auth.get_failed_attempts() == i
            assert auth.is_decoy_mode_active() is False

        # 5th invalid attempt reaches threshold (max_failed_attempts = 5)
        assert auth.identify_pin("9998") is None
        assert auth.is_decoy_mode_active() is True

        # Decoy mode is now active
        assert auth.identify_pin("1234") == "master"

    def test_dead_man_switch_expiration_wipe(self, temp_dir):
        auth = AuthenticationManager(temp_dir, auto_init_defaults=True)
        dummy_secret = os.path.join(temp_dir, "secret.key.enc")
        with open(dummy_secret, "wb") as f:
            f.write(b"TOP_SECRET_DB_ENCRYPTION_KEY")
        assert os.path.exists(dummy_secret)

        # Configure Dead Man's Switch for 1 hour
        assert auth.set_dead_man_switch(enabled=True, interval_hours=1.0) is True
        status = auth.get_dead_man_switch_status()
        assert status["enabled"] is True

        # Fresh heartbeat: switch should not expire
        assert auth.check_dead_man_switch() is False
        assert os.path.exists(dummy_secret)

        # Simulate passage of 2 hours without heartbeat
        status["last_heartbeat"] = time.time() - 7200
        with open(auth.dms_file, "w") as f:
            json.dump(status, f)

        # Now checking Dead Man's Switch should detect expiration and trigger wipe
        assert auth.check_dead_man_switch() is True
        assert not os.path.exists(dummy_secret)


class TestPhase6Capabilities:
    """Automated unit and integration test suite for Gost-Net Phase 6 subsystems."""

    def test_packet_fragmenter_slicing_and_reassembly(self):
        fragmenter = PacketFragmenter(reassembly_timeout=5.0)
        # Create a payload larger than MTU (e.g. 350 bytes with MTU 100)
        test_payload = b"TACTICAL_LORA_PAYLOAD_CHUNK_" * 12
        mtu = 100

        fragments = fragmenter.fragment_packet(test_payload, mtu=mtu)
        assert len(fragments) > 1

        # Each fragment must fit within MTU
        for frag in fragments:
            assert len(frag) <= mtu
            assert frag[:4] == b'FRAG'

        # Reassemble fragments incrementally
        reassembled = None
        for frag in fragments:
            reassembled = fragmenter.reassemble_fragment(frag)

        assert reassembled is not None
        assert reassembled == test_payload

    def test_packet_fragmenter_checksum_corruption_detection(self):
        fragmenter = PacketFragmenter(reassembly_timeout=5.0)
        test_payload = b"SENSITIVE_RECONNAISSANCE_DATA" * 5
        fragments = fragmenter.fragment_packet(test_payload, mtu=60)
        assert len(fragments) >= 2

        # Corrupt the payload chunk of the first fragment
        corrupted_frag = bytearray(fragments[0])
        corrupted_frag[-1] ^= 0xFF  # Flip bits in data
        fragments[0] = bytes(corrupted_frag)

        reassembled = None
        for frag in fragments:
            res = fragmenter.reassemble_fragment(frag)
            if res:
                reassembled = res

        # Checksum mismatch should cause reassembly to fail and return None
        assert reassembled is None

    def test_serial_radio_bearer_lifecycle_and_loopback(self):
        bearer = SerialRadioBearer(port="COM99", baudrate=115200, mtu=220)
        assert bearer.start() is True
        assert bearer.is_available() is True
        assert bearer.mtu == 220

        received_packets = []
        bearer.on_data_received = lambda data, sender: received_packets.append((data, sender))

        # Test transmission in loopback/simulated mode
        test_packet = b"RADIO_PACKET_FRAME_TEST"
        assert bearer.send(test_packet) is True
        assert test_packet in bearer.mock_rx_buffer

        # Test simulated RX injection
        bearer.inject_mock_rx(test_packet, sender="LORA_NODE_9")
        assert len(received_packets) == 1
        assert received_packets[0][0] == test_packet
        assert received_packets[0][1] == "LORA_NODE_9"

        bearer.stop()
        assert bearer.is_running is False

    def test_bearer_manager_transparent_multi_bearer_sar(self):
        manager = BearerManager()
        bearer = SerialRadioBearer(port="COM88", mtu=64)
        bearer.start()
        manager.register_bearer(bearer)

        received_payloads = []
        manager.on_packet_received = lambda pkt, sender, bname: received_payloads.append((pkt, sender, bname))

        # Send a packet that exceeds the bearer MTU (150 bytes > 64 MTU)
        large_packet = b"CROSS_BEARER_TACTICAL_TELEMETRY_" * 4
        success = manager.send_packet(large_packet)
        assert success is True

        # Verify bearer mock buffer holds fragments
        assert len(bearer.mock_rx_buffer) >= 3

        # Simulate delivery of each fragment through bearer manager
        for frag in bearer.mock_rx_buffer:
            manager._handle_raw_bearer_data(frag, sender="REMOTE_RELAY", bearer_name=bearer.bearer_name)

        assert len(received_payloads) == 1
        assert received_payloads[0][0] == large_packet
        assert received_payloads[0][1] == "REMOTE_RELAY"
        assert received_payloads[0][2] == bearer.bearer_name

        manager.unregister_bearer(bearer.bearer_name)
        assert bearer.bearer_name not in manager.bearers

    def test_duty_cycler_power_profiles_and_schedules(self):
        # Continuous mode: always awake
        dc_continuous = DutyCycleManager(profile=PowerProfile.CONTINUOUS)
        assert dc_continuous.is_awake(target_time=100.0) is True
        assert dc_continuous.is_awake(target_time=125.0) is True
        assert dc_continuous.time_until_next_wake(target_time=125.0) == 0.0

        # Standard saver mode: 5s wake window every 30s
        dc_standard = DutyCycleManager(profile=PowerProfile.STANDARD_SAVER, clock_offset=0.0)
        # At t=2.0 (2.0 % 30 = 2.0 < 5.0) -> awake
        assert dc_standard.is_awake(target_time=2.0) is True
        assert dc_standard.time_until_next_wake(target_time=2.0) == 0.0

        # At t=10.0 (10.0 % 30 = 10.0 >= 5.0) -> asleep
        assert dc_standard.is_awake(target_time=10.0) is False
        assert dc_standard.time_until_next_wake(target_time=10.0) == 20.0  # 30 - 10 = 20s

        # Test mesh clock offset adjustment (+5s offset)
        dc_standard.set_clock_offset(5.0)
        # At t=27.0 with offset 5.0 -> synced_time = 32.0 % 30 = 2.0 < 5.0 -> awake
        assert dc_standard.is_awake(target_time=27.0) is True

    def test_duty_cycler_packet_spooling_and_priority_flush(self):
        dc = DutyCycleManager(profile=PowerProfile.STANDARD_SAVER)
        # Artificially simulate sleeping state by evaluating at sleep offset
        dc.wake_duration = 0.001
        dc.cycle_period = 1000.0

        dispatched = []
        def mock_sender(pkt, peer):
            dispatched.append((pkt, peer))
            return True

        # Queue normal priority packets while sleeping
        assert dc.queue_or_send(b"DATA_LOW", "Peer1", priority=1, sender_func=mock_sender) is True
        assert dc.queue_or_send(b"DATA_MED", "Peer2", priority=3, sender_func=mock_sender) is True
        assert len(dispatched) == 0
        assert len(dc.spool_queue) == 2

        # Critical priority message (priority >= 9) forces immediate emergency transmission
        assert dc.queue_or_send(b"DATA_EMERGENCY_SOS", "Peer3", priority=9, sender_func=mock_sender) is True
        assert len(dispatched) == 1
        assert dispatched[0][0] == b"DATA_EMERGENCY_SOS"

        # Window rendezvous flush: drains spool in descending priority order
        flushed_count = dc.flush_spool()
        assert flushed_count == 2
        assert len(dc.spool_queue) == 0
        assert len(dispatched) == 3
        # Peer2 (priority 3) should have been dispatched before Peer1 (priority 1)
        assert dispatched[1][0] == b"DATA_MED"
        assert dispatched[2][0] == b"DATA_LOW"

    def test_multipath_k2_disjoint_path_discovery(self):
        # Topology:
        # Source (A) -> B -> D -> Destination (Z)
        # Source (A) -> C -> E -> Destination (Z)
        mesh_graph = {
            "A": {"B", "C"},
            "B": {"A", "D"},
            "C": {"A", "E"},
            "D": {"B", "Z"},
            "E": {"C", "Z"},
            "Z": {"D", "E"}
        }

        paths = find_disjoint_paths(mesh_graph, "A", "Z", k=2)
        assert len(paths) == 2

        path1, path2 = paths[0], paths[1]
        assert path1[0] == "A" and path1[-1] == "Z"
        assert path2[0] == "A" and path2[-1] == "Z"

        # Intermediate nodes must be strictly disjoint
        inter1 = set(path1[1:-1])
        inter2 = set(path2[1:-1])
        assert inter1.isdisjoint(inter2)
        assert len(inter1) > 0 and len(inter2) > 0

    def test_multipath_onion_wrapping_and_layered_unwrapping(self):
        path = ["NodeA", "NodeB", "NodeC", "NodeD"]
        # Generate distinct keys for each hop
        key_b = os.urandom(32)
        key_c = os.urandom(32)
        key_d = os.urandom(32)
        hop_keys = {
            "NodeB": key_b,
            "NodeC": key_c,
            "NodeD": key_d
        }

        secret_payload = b"CRITICAL_OPERATIONAL_ORDER_ALPHA"

        # NodeA wraps the onion packet
        onion_packet = wrap_onion_packet(secret_payload, path, hop_keys)
        assert onion_packet != secret_payload

        # Hop 1: NodeB unwraps layer
        next_hop_b, payload_b = unwrap_onion_layer(onion_packet, key_b)
        assert next_hop_b == "NodeC"
        assert payload_b != secret_payload  # Still encapsulated for downstream hops

        # Hop 2: NodeC unwraps layer
        next_hop_c, payload_c = unwrap_onion_layer(payload_b, key_c)
        assert next_hop_c == "NodeD"
        assert payload_c != secret_payload

        # Hop 3: NodeD unwraps layer (final destination)
        next_hop_d, final_payload = unwrap_onion_layer(payload_c, key_d)
        assert next_hop_d is None  # Final destination reached
        assert final_payload == secret_payload

    def test_multipath_router_deduplication(self):
        router = MultiPathRouter(dedup_ttl=10.0)
        msg_id = "tactical_msg_987"

        # First arrival: novel packet
        assert router.is_duplicate(msg_id) is False

        # Redundant arrival across parallel disjoint path: duplicate detected
        assert router.is_duplicate(msg_id) is True

    def test_ota_burn_token_ed25519_signature_and_replay_protection(self):
        manager = RemoteWipeManager(max_token_age=300.0)
        commander_priv, commander_pub_bytes = RemoteWipeManager.generate_commander_keypair()
        manager.commander_public_key_bytes = commander_pub_bytes

        # Create valid burn token targeted to TargetRelay
        token = manager.create_burn_token(
            commander_private_key=commander_priv,
            commander_id="COMMANDER_ALPHA",
            target_peer_id="TargetRelay",
            reason="PHYSICAL_NODE_CAPTURE"
        )

        # 1. Successful verification
        valid, reason = manager.verify_burn_token(token, local_peer_id="TargetRelay")
        assert valid is True
        assert reason == "VERIFIED"

        # 2. Replay rejection with identical nonce
        replayed, replay_reason = manager.verify_burn_token(token, local_peer_id="TargetRelay")
        assert replayed is False
        assert replay_reason == "NONCE_REPLAYED"

        # 3. Target mismatch
        token2 = manager.create_burn_token(commander_priv, "COMMANDER_ALPHA", target_peer_id="OtherRelay")
        valid_mismatch, reason_mismatch = manager.verify_burn_token(token2, local_peer_id="TargetRelay")
        assert valid_mismatch is False
        assert "TARGET_MISMATCH" in reason_mismatch

        # 4. Forged payload signature failure
        token3 = manager.create_burn_token(commander_priv, "COMMANDER_ALPHA", target_peer_id="TargetRelay")
        token3["payload"]["reason"] = "FORGED_TAMPERED_REASON"
        valid_forged, reason_forged = manager.verify_burn_token(token3, local_peer_id="TargetRelay")
        assert valid_forged is False
        assert "SIGNATURE_INVALID" in reason_forged

    def test_ota_detachment_zeroize_execution(self, temp_dir):
        manager = RemoteWipeManager()
        fake_db = os.path.join(temp_dir, "tactical.db")
        fake_wal = f"{fake_db}-wal"
        fake_key = os.path.join(temp_dir, "db.key")

        for fpath in [fake_db, fake_wal, fake_key]:
            with open(fpath, "wb") as f:
                f.write(b"TOP_SECRET_OPERATIONAL_DATA" * 10)
            assert os.path.exists(fpath)

        memory_zeroized_flag = [False]
        def mock_zeroize_cb():
            memory_zeroized_flag[0] = True

        # Execute detachment zeroization
        results = manager.execute_detachment_zeroize(
            db_path=fake_db,
            key_zeroize_callback=mock_zeroize_cb,
            extra_files_to_shred=[fake_key]
        )

        assert results["status"] == "COMPLETED"
        assert results["memory_zeroized"] is True
        assert memory_zeroized_flag[0] is True
        assert fake_db in results["files_shredded"]

        # Persistent files should be logically overwritten and removed
        assert not os.path.exists(fake_db)
        assert not os.path.exists(fake_wal)
        assert not os.path.exists(fake_key)

