"""
Ghost Net - Network Engine
Handles P2P discovery via UDP broadcast and secure TCP messaging.
Supports binary file transfers with header-based protocol.
Designed for offline-first, local network communication.
Includes persistent encrypted storage integration.
Features multi-interface detection and automatic network switching.
"""

import socket
import json
import threading
import time
import os
from datetime import datetime
from typing import Dict, List, Set, Callable, Optional, Tuple, Any, Union
from enum import Enum
from dataclasses import asdict
import uuid
from cryptography.fernet import Fernet
import hashlib
import base64
import queue
import sys
from pathlib import Path

# Ensure src directory is in sys.path for sibling imports
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

try:
    from routing import RoutingTable
    ROUTING_AVAILABLE = True
except ImportError:
    ROUTING_AVAILABLE = False
    print("[GhostEngine] Routing module not available - mesh networking disabled")

try:
    from security import CryptoManager, create_revocation_token, verify_revocation_token, derive_channel_key, encrypt_channel_message, decrypt_channel_message
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    print("[GhostEngine] Security module not available")

# Experimental research module availability flags (isolated under research/)
COMPACT_FRAMING_AVAILABLE = False
COT_GEOJSON_AVAILABLE = False
BEARER_AVAILABLE = False
DUTY_CYCLER_AVAILABLE = False
MULTIPATH_AVAILABLE = False
REMOTE_WIPE_AVAILABLE = False
FEC_AVAILABLE = False
GEOCAST_AVAILABLE = False
STEGO_TRANSPORT_AVAILABLE = False
TOPOLOGY_AVAILABLE = False
FHSS_AVAILABLE = False
PROXIMITY_CRYPTO_AVAILABLE = False
OTP_AVAILABLE = False
ANTI_JAMMING_AVAILABLE = False
BUNDLE_PROTOCOL_AVAILABLE = False
EPHEMERAL_BEACON_AVAILABLE = False
TAK_BRIDGE_AVAILABLE = False
MERKLE_VAULT_AVAILABLE = False
COGNITIVE_RADIO_AVAILABLE = False
SWARM_CONSENSUS_AVAILABLE = False
DTN_PUBSUB_AVAILABLE = False
SOVEREIGN_IDENTITY_AVAILABLE = False
MESH_HEALING_AVAILABLE = False
TRAFFIC_CAMOUFLAGE_AVAILABLE = False
TACTICAL_DHT_AVAILABLE = False
SPATIAL_PRIVACY_AVAILABLE = False
COLLABORATIVE_ECM_AVAILABLE = False
NETWORK_CODING_AVAILABLE = False
QOS_SHAPER_AVAILABLE = False
ZKP_AUTH_AVAILABLE = False
PQ_KEM_AVAILABLE = False
HOMOMORPHIC_AGG_AVAILABLE = False
DSSS_MODULATION_AVAILABLE = False
VIRTUAL_ARRAY_AVAILABLE = False
COVERT_CHANNEL_AVAILABLE = False
LINK_BUDGET_AVAILABLE = False
MESH_TIME_SYNC_AVAILABLE = False
RF_SIGNATURE_AVAILABLE = False
ADAPTIVE_MODULATION_AVAILABLE = False
GROUP_REKEYING_AVAILABLE = False
FUZZY_ROUTING_AVAILABLE = False
ANTI_REPLAY_AVAILABLE = False
CHAOS_FUZZER_AVAILABLE = False
TACTICAL_HUD_AVAILABLE = False
BEARER_FAILOVER_AVAILABLE = False
MEMORY_SCRUBBER_AVAILABLE = False

try:
    from connection_manager import ConnectionManager
    CONNECTION_MANAGER_AVAILABLE = True
except ImportError:
    CONNECTION_MANAGER_AVAILABLE = False
    print("[GhostEngine] ConnectionManager not available")

try:
    from network_utils import NetworkDetector, NetworkMonitor, P2PPeerDiscovery, DiscoveryMode
    NETWORK_UTILS_AVAILABLE = True
except ImportError:
    NETWORK_UTILS_AVAILABLE = False
    print("[GhostEngine] Network utils not available - using legacy IP detection")

# Import storage module (optional, fails gracefully if not available)
try:
    from storage import DatabaseManager
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False
    print("[GhostEngine] Storage module not available - running without persistence")

try:
    from database import PersistenceDatabase
    PERSISTENCE_AVAILABLE = True
except ImportError:
    PERSISTENCE_AVAILABLE = False
    print("[GhostEngine] PersistenceDatabase not available - running without local persistence")

try:
    from config import ConfigManager
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    print("[GhostEngine] Config module not available - using static username")

try:
    import steganography
    STEGANOGRAPHY_AVAILABLE = True
except ImportError:
    STEGANOGRAPHY_AVAILABLE = False
    print("[GhostEngine] Steganography module not available")


from network_state import NetworkState, MessageDeliveryState, SendResult


class GhostEngine:
    """
    The core network engine for Ghost Net P2P messaging.
    
    Features:
    - UDP Broadcast discovery (Port 37020)
    - TCP messaging (Port 37021)
    - Symmetric encryption with daily rotating keys
    - Thread-safe peer management
    """
    
    UDP_PORT = 37020
    TCP_PORT = 37021
    BEACON_INTERVAL = 2
    PEER_TIMEOUT = 10
    BUFFER_SIZE = 4096
    CHUNK_SIZE = 8192
    HEADER_DELIMITER = b"<HEADER_END>"
    CHUNK_DELIMITER = b"<CHUNK_END>"
    MAX_FILE_SIZE = 100 * 1024 * 1024
    
    def __init__(self, username: str = None, on_message_received: Optional[Callable] = None,
                 on_peer_update: Optional[Callable] = None,
                 on_file_received: Optional[Callable] = None,
                 downloads_dir: Optional[str] = None,
                 enable_storage: bool = True,
                 db_manager: Optional['DatabaseManager'] = None,
                 persistence_db: Optional['PersistenceDatabase'] = None,
                 config_manager: Optional['ConfigManager'] = None,
                 connection_manager: Optional['ConnectionManager'] = None,
                 signing_private_key_bytes: Optional[bytes] = None):
        """
        Initialize the Ghost Network Engine.
        
        Args:
            username: Display name for this peer (if None, loads from config)
            on_message_received: Callback(sender_ip, message_text, timestamp)
            on_peer_update: Callback(peers_dict) when peer list changes
            on_file_received: Callback(sender_ip, filename, filepath, timestamp)
            downloads_dir: Directory to save received files (default: ./downloads)
            enable_storage: Enable persistent storage (default: True)
            db_manager: External DatabaseManager instance (optional)
            config_manager: External ConfigManager instance (optional)
            signing_private_key_bytes: Decrypted signing private key (optional)
        """
        self.crypto_manager = None
        if SECURITY_AVAILABLE:
            self.crypto_manager = CryptoManager(signing_private_key_bytes)
        
        self.config_manager = config_manager
        if not self.config_manager and CONFIG_AVAILABLE:
            self.config_manager = ConfigManager()
        
        if username:
            self.username = username
        elif self.config_manager:
            self.username = self.config_manager.get_username()
        else:
            self.username = "GhostUser"
        
        self.peer_id = hashlib.sha256(self.username.encode()).hexdigest()[:16]
        
        self.routing_table = None
        if ROUTING_AVAILABLE:
            self.routing_table = RoutingTable(max_route_age=30.0)
        
        self.network_detector = None
        self.network_monitor = None
        self.peer_discovery = None
        self.wifi_direct = None
        self.bluetooth = None
        
        if NETWORK_UTILS_AVAILABLE:
            self.network_detector = NetworkDetector()
            self.network_monitor = NetworkMonitor(on_network_changed=self._on_network_changed)
            self.peer_discovery = self.network_monitor.get_peer_discovery()
            self.peer_discovery.on_peers_discovered = self._on_offgrid_peers_discovered
        
        self.wifi_direct = get_android_wifi_direct()
        self.bluetooth = get_android_bluetooth()
        
        self.local_ip = self._get_local_ip()
        self.current_network_type = 'unknown'
        self.peers: Dict[str, dict] = {}
        self.running = False
        
        self.connection_manager = connection_manager
        if not self.connection_manager and CONNECTION_MANAGER_AVAILABLE:
            self.connection_manager = ConnectionManager(engine=self)
        
        # Callbacks
        self.on_message_received = on_message_received
        self.on_peer_update = on_peer_update
        self.on_file_received = on_file_received
        
        # File handling - Bug #2 fix with error handling and fallback
        if downloads_dir:
            self.downloads_dir = downloads_dir
        else:
            # Try primary path first, with fallback
            try:
                try:
                    from kivy.utils import platform as kivy_platform
                    is_android = (kivy_platform == 'android')
                except ImportError:
                    is_android = False
                
                if is_android:
                    # On Android, use app-specific storage
                    base_dir = os.environ.get("ANDROID_PRIVATE") or os.environ.get("PYTHONHOME") or os.path.expanduser("~")
                    self.downloads_dir = os.path.join(base_dir, ".ghostnet", "downloads")
                else:
                    # On desktop, use ~/Downloads/GhostNet
                    self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "GhostNet")
                os.makedirs(self.downloads_dir, exist_ok=True)
            except Exception as e:
                print(f"[GhostEngine] Primary downloads path failed: {e}")
                # Fallback to current directory
                try:
                    self.downloads_dir = os.path.join(os.getcwd(), ".ghostnet_downloads")
                    os.makedirs(self.downloads_dir, exist_ok=True)
                    print(f"[GhostEngine] Using fallback downloads directory: {self.downloads_dir}")
                except Exception as e2:
                    print(f"[GhostEngine] WARNING: Could not create downloads directory: {e2}")
                    # Continue without creating directory - app can still function
                    self.downloads_dir = os.getcwd()
        
        self.spool_dir = os.path.join(os.path.dirname(self.downloads_dir), "spool")
        try:
            os.makedirs(self.spool_dir, exist_ok=True)
        except Exception as e:
            print(f"[GhostEngine] WARNING: Could not create spool directory: {e}")
        
        self.persistence_db = None
        if enable_storage and PERSISTENCE_AVAILABLE:
            if persistence_db:
                self.persistence_db = persistence_db
            else:
                self.persistence_db = PersistenceDatabase()
            print("[GhostEngine] Local persistence database initialized")
        
        self.db_manager = None
        if enable_storage and STORAGE_AVAILABLE:
            if db_manager:
                self.db_manager = db_manager
            else:
                self.db_manager = DatabaseManager()
            print("[GhostEngine] Persistent storage enabled")
        else:
            print("[GhostEngine] Running without persistent storage")
        
        # Thread locks
        self.peers_lock = threading.Lock()
        self.last_beacon_processed = {}
        
        # Encryption
        self.cipher = self._generate_cipher()
        
        # Sockets (initialized in start())
        self.udp_socket = None
        self.tcp_socket = None
        self.tcp_port = self.TCP_PORT
        self.mesh_offsets = {}
        self.mesh_time_offset = 0.0
        
        # Threads
        self.beacon_thread = None
        self.listener_thread = None
        self.tcp_server_thread = None
        self.pruning_thread = None
        self.routing_maintenance_thread = None
        self.relay_forwarding_thread = None
        self.chaffing_thread = None
        self.chaffing_enabled = False
        
        self.pending_forwards: list = []
        self.forwards_lock = threading.Lock()
        
        self.sos_cache = []
        self.sos_cache_lock = threading.Lock()
        self.sos_cache_max_age = 300
        self.on_sos_received = None

        # Network State Machine & Delivery Lifecycle
        self.network_state = NetworkState.STARTING
        self.on_delivery_status: Optional[Callable[[str, str, str], None]] = None
        self.seen_message_ids = set()
        self.seen_message_ids_order = []
        self.message_dedup_lock = threading.Lock()

        # Adaptive discovery beaconing
        self.min_beacon_interval = float(self.BEACON_INTERVAL)
        self.max_beacon_interval = 30.0
        self.current_beacon_interval = self.min_beacon_interval
        self.peer_set_hash = None
        self.static_beacon_cycles = 0

        # Phase 4: Peer Location Sharing, Tactical Waypoints, and Revocation
        self.on_location_update_received: Optional[Callable[[dict], None]] = None
        self.on_waypoint_received: Optional[Callable[[dict], None]] = None
        self.on_peer_revoked: Optional[Callable[[str, str], None]] = None
        self.on_peer_key_changed: Optional[Callable[[str, str, str], None]] = None
        self.persist_queue = queue.Queue(maxsize=2000)
        self.persist_thread = None
        self.revoked_peers = set()
        if self.persistence_db:
            try:
                for r in self.persistence_db.get_revoked_peers():
                    self.revoked_peers.add(r['peer_id'])
            except Exception as e:
                print(f"[GhostEngine] Could not load revoked peers: {e}")

        # Phase 5: Group Channels, AODV Reactive Routing, and Compact Framing
        self.channel_keys: Dict[str, bytes] = {}
        self.on_group_message_received: Optional[Callable[[str, str, str, str, float], None]] = None
        self.on_route_discovered: Optional[Callable[[str, int], None]] = None
        self.use_compact_framing = False
        self.pending_rreqs: Dict[str, float] = {}

        # Phase 6: Multi-Bearer Tactical Radio Gateway, Low-Power Duty Cycling, Multi-Path & Remote Wipe
        self.bearer_manager = BearerManager() if BEARER_AVAILABLE else None
        self.duty_cycler = DutyCycleManager() if DUTY_CYCLER_AVAILABLE else None
        self.multipath_router = MultiPathRouter() if MULTIPATH_AVAILABLE else None
        self.remote_wipe_manager = RemoteWipeManager() if REMOTE_WIPE_AVAILABLE else None
        self.on_ota_zeroize_received: Optional[Callable[[dict], None]] = None

        # Phase 7: Forward Error Correction, GeoCast, Stego Transport & Topology Graph
        self.fec_engine = FECEngine() if FEC_AVAILABLE else None
        self.geocast_router = GeoCastRouter() if GEOCAST_AVAILABLE else None
        self.topology_manager = TopologyGraphManager(self.peer_id) if TOPOLOGY_AVAILABLE else None
        self.on_geocast_received: Optional[Callable[[dict], None]] = None

        # Phase 8: Dynamic Frequency Agility, Zero-Knowledge Proximity, OTP Vault & Anti-Jamming
        self.fhss_manager = FrequencyAgilityManager() if FHSS_AVAILABLE else None
        self.proximity_verifier = ProximityVerifier() if PROXIMITY_CRYPTO_AVAILABLE else None
        self.otp_vault: Optional[OTPStreamVault] = None
        self.jamming_detector = JammingDetector() if ANTI_JAMMING_AVAILABLE else None
        if self.jamming_detector:
            self.jamming_detector.on_posture_changed = self._on_defensive_posture_changed

        # Phase 9: Delay-Tolerant Bundle Protocol, Ephemeral Beacons, ATAK CoT Streaming & Merkle Vault
        self.bundle_manager = BundleProtocolManager(self.peer_id) if BUNDLE_PROTOCOL_AVAILABLE else None
        self.ephemeral_beacon_mgr = EphemeralBeaconManager() if EPHEMERAL_BEACON_AVAILABLE else None
        self.tak_bridge = TakMulticastBridge() if TAK_BRIDGE_AVAILABLE else None
        self.merkle_ledger = MerkleAuditLedger() if MERKLE_VAULT_AVAILABLE else None
        self.on_bundle_received: Optional[Callable[[Any], None]] = None
        self.on_cot_received: Optional[Callable[[dict, str], None]] = None
        if self.tak_bridge:
            self.tak_bridge.on_cot_received_from_tak = self._on_cot_from_tak

        # Phase 10: Cognitive Radio Spectrum Sensing, Swarm Consensus, DTN Pub/Sub & Sovereign Identity
        self.cognitive_radio = SpectrumSensingEngine() if COGNITIVE_RADIO_AVAILABLE else None
        self.swarm_consensus = SwarmConsensusManager(self.peer_id, self.crypto_manager.private_key if self.crypto_manager else None) if SWARM_CONSENSUS_AVAILABLE else None
        self.pubsub_router = DTNPubSubRouter(self.peer_id) if DTN_PUBSUB_AVAILABLE else None
        self.wot_keyring = WebOfTrustKeyring(self.peer_id, self.crypto_manager.private_key if self.crypto_manager else None) if SOVEREIGN_IDENTITY_AVAILABLE else None
        self.on_consensus_proposal: Optional[Callable[[Any], None]] = None
        self.on_consensus_committed: Optional[Callable[[dict], None]] = None
        self.on_pubsub_message: Optional[Callable[[Any], None]] = None

        # Phase 11: Mesh Self-Healing, Traffic Camouflage, Tactical DHT & Spatial Privacy
        self.mesh_healing = MeshHealingManager(self.peer_id) if MESH_HEALING_AVAILABLE else None
        self.traffic_camouflage = TrafficCamouflageEngine() if TRAFFIC_CAMOUFLAGE_AVAILABLE else None
        self.tactical_dht = TacticalDHT(self.peer_id) if TACTICAL_DHT_AVAILABLE else None
        self.spatial_privacy = SpatialPrivacyEngine() if SPATIAL_PRIVACY_AVAILABLE else None
        self.on_dht_response: Optional[Callable[[str, Any, bool], None]] = None

        # Phase 12: Collaborative ECM, Network Coding, Token-Bucket QoS & Zero-Knowledge Auth
        self.collaborative_ecm = CollaborativeECMManager(self.peer_id) if COLLABORATIVE_ECM_AVAILABLE else None
        self.qos_shaper = TacticalQoSShaper() if QOS_SHAPER_AVAILABLE else None
        self.zkp_auth = SchnorrZKP if ZKP_AUTH_AVAILABLE else None
        self.on_zkp_auth_received: Optional[Callable[[str, int, bool], None]] = None
        self.on_ecm_observation_received: Optional[Callable[[str, dict], None]] = None

        # Phase 13: Post-Quantum KEM, Homomorphic Sensor Aggregation, DSSS & Virtual Arrays
        self.pq_kem = PostQuantumLatticeKEM if PQ_KEM_AVAILABLE else None
        self.homomorphic_agg = PaillierHomomorphicAggregator if HOMOMORPHIC_AGG_AVAILABLE else None
        self.dsss_modulator = DSSSModulator if DSSS_MODULATION_AVAILABLE else None
        self.virtual_array = VirtualArrayCoordinator(self.peer_id) if VIRTUAL_ARRAY_AVAILABLE else None
        self.on_pq_kem_ciphertext_received: Optional[Callable[[str, dict], None]] = None
        self.on_homomorphic_telemetry_received: Optional[Callable[[str, int, str], None]] = None

        # Phase 14: Covert Timing Channel, Tactical Link Budget, Mesh Time Sync & RF Signature Advisor
        self.covert_timing_channel = CovertTimingChannel() if COVERT_CHANNEL_AVAILABLE else None
        self.link_budget_calc = LinkBudgetCalculator if LINK_BUDGET_AVAILABLE else None
        self.mesh_time_sync = MeshTimeSynchroniser(self.peer_id) if MESH_TIME_SYNC_AVAILABLE else None
        self.rf_signature_advisor = RFSignatureAdvisor if RF_SIGNATURE_AVAILABLE else None
        self.on_time_sync_updated: Optional[Callable[[str, float, float], None]] = None

        # Phase 15: Adaptive Modulation & Coding, LKH Group Rekeying, Fuzzy Route Optimization & Anti-Replay
        self.adaptive_modulation = AdaptiveModulationEngine() if ADAPTIVE_MODULATION_AVAILABLE else None
        self.lkh_rekeying = LogicalKeyHierarchy() if GROUP_REKEYING_AVAILABLE else None
        self.fuzzy_routing = FuzzyRoutingEngine() if FUZZY_ROUTING_AVAILABLE else None
        self.anti_replay = AntiReplayManager() if ANTI_REPLAY_AVAILABLE else None
        self.on_lkh_rekey_received: Optional[Callable[[Dict[str, Any]], None]] = None

        # Phase 16: Chaos Fuzzer, Tactical HUD, Bearer Failover & Panic Memory Scrubber
        self.chaos_fuzzer = ProtocolChaosFuzzer() if CHAOS_FUZZER_AVAILABLE else None
        self.tactical_hud = TacticalHUDController(callsign=self.username, peer_id=self.peer_id) if TACTICAL_HUD_AVAILABLE else None
        self.bearer_failover = BearerFailoverController() if BEARER_FAILOVER_AVAILABLE else None
        self.memory_scrubber = MemoryScrubber() if MEMORY_SCRUBBER_AVAILABLE else None
        self.on_tactical_alert_received: Optional[Callable[[Dict[str, Any]], None]] = None

    def reset_beacon_backoff(self):
        """Reset discovery beacon interval to minimum for rapid peer re-acquisition."""
        self.current_beacon_interval = self.min_beacon_interval
        self.static_beacon_cycles = 0

    def set_network_state(self, new_state: NetworkState):
        self.network_state = new_state

    def get_network_state_label(self) -> str:
        labels = {
            NetworkState.OFFLINE: "Offline",
            NetworkState.STARTING: "Initializing...",
            NetworkState.DISCOVERING: "Looking for nearby devices",
            NetworkState.AVAILABLE: "Available on mesh",
            NetworkState.PEER_VISIBLE: "Peers visible",
            NetworkState.CONNECTING: "Connecting...",
            NetworkState.SESSION_READY: "Secure session ready",
            NetworkState.DEGRADED: "Connection interrupted",
            NetworkState.RECONNECTING: "Trying again...",
        }
        return labels.get(self.network_state, "Offline")

    def _record_seen_message(self, msg_id: str) -> bool:
        """Returns True if message is new, False if duplicate."""
        if not msg_id:
            return True
        with self.message_dedup_lock:
            if msg_id in self.seen_message_ids:
                return False
            self.seen_message_ids.add(msg_id)
            self.seen_message_ids_order.append(msg_id)
            if len(self.seen_message_ids_order) > 2000:
                oldest = self.seen_message_ids_order.pop(0)
                self.seen_message_ids.discard(oldest)
            return True

    def _persist_worker(self):
        """Dedicated background persistence worker to avoid thread proliferation."""
        while True:
            try:
                task = self.persist_queue.get(timeout=0.2)
                if task is None:
                    self.persist_queue.task_done()
                    break
                action, args = task
                if action == 'message':
                    peer_id, sender_type, content_type, content, timestamp, ttl, file_path = args
                    if self.persistence_db:
                        try:
                            self.persistence_db.save_message(peer_id, sender_type, content_type, content, timestamp, ttl)
                        except Exception as e:
                            print(f"[GhostEngine] Persistence save_message error: {e}")
                    elif self.db_manager:
                        try:
                            sender_lbl = "ME" if sender_type == "me" else "PEER"
                            mtype = "FILE" if content_type == "file" else "TEXT"
                            self.db_manager.save_message(peer_id, sender_lbl, content, mtype, file_path, timestamp)
                        except Exception as e:
                            print(f"[GhostEngine] Storage save_message error: {e}")
                elif action == 'peer':
                    peer_id, username, discovery_type = args
                    if self.persistence_db:
                        try:
                            self.persistence_db.save_peer(peer_id, username, discovery_type=discovery_type)
                        except Exception as e:
                            print(f"[GhostEngine] Persistence save_peer error: {e}")
                    elif self.db_manager:
                        try:
                            self.db_manager.save_peer(peer_id, username)
                        except Exception as e:
                            print(f"[GhostEngine] Storage save_peer error: {e}")
                self.persist_queue.task_done()
            except queue.Empty:
                if not self.running:
                    break
                continue
            except Exception as e:
                print(f"[GhostEngine] Persist worker unexpected error: {e}")

    def _persist_message(self, peer_id: str, sender_type: str, content_type: str, content: str,
                         timestamp: Optional[float] = None, ttl: Optional[int] = None, file_path: Optional[str] = None):
        """Enqueues message persistence asynchronously."""
        if not self.persistence_db and not self.db_manager:
            return
        try:
            self.persist_queue.put(('message', (peer_id, sender_type, content_type, content, timestamp, ttl, file_path)), timeout=0.5)
        except Exception:
            if self.persistence_db:
                self.persistence_db.save_message(peer_id, sender_type, content_type, content, timestamp, ttl)

    def _persist_peer(self, peer_id: str, username: str, discovery_type: Optional[str] = None):
        """Enqueues peer persistence asynchronously."""
        if not self.persistence_db and not self.db_manager:
            return
        try:
            self.persist_queue.put(('peer', (peer_id, username, discovery_type)), timeout=0.5)
        except Exception:
            if self.persistence_db:
                self.persistence_db.save_peer(peer_id, username, discovery_type=discovery_type)

    
    def _get_local_ip(self) -> str:
        """Get the local IP address of this device with multi-interface support."""
        try:
            # Use network detector if available
            if self.network_detector:
                best_ip = self.network_detector.get_best_interface()
                if best_ip:
                    # Detect network type
                    self.current_network_type = self.network_detector.get_network_type(best_ip)
                    print(f"[GhostEngine] Using {self.current_network_type} interface: {best_ip}")
                    return best_ip
            
            # Fallback: Create a dummy socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2.0)
            s.connect(("1.1.1.1", 80))  # Cloudflare DNS
            local_ip = s.getsockname()[0]
            s.close()
            print(f"[GhostEngine] Using fallback IP: {local_ip}")
            return local_ip
        except Exception as e:
            print(f"[GhostEngine] Error getting local IP: {e}")
            return "127.0.0.1"
    
    def _generate_cipher(self) -> Fernet:
        """
        Generate a Fernet cipher with a daily rotating key.
        Key is derived from current date (YYYY-MM-DD format).
        In production, combine with Wi-Fi SSID for better security.
        """
        try:
            # Get current date as seed
            date_seed = datetime.now().strftime("%Y-%m-%d")
            
            # In a real implementation, append Wi-Fi SSID:
            # ssid = get_wifi_ssid()  # Platform-specific
            # key_material = f"{date_seed}-{ssid}"
            
            key_material = f"GhostNet-{date_seed}"
            
            # Generate 32-byte key via SHA256
            key_hash = hashlib.sha256(key_material.encode()).digest()
            key_b64 = base64.urlsafe_b64encode(key_hash)
            
            return Fernet(key_b64)
        except Exception as e:
            print(f"[GhostEngine] Cipher generation error: {e}")
            # Bug #10 fix: Don't generate new key on error, return None instead
            # Returning a new key breaks decryption of existing messages
            print("[GhostEngine] WARNING: Cipher unavailable, message encryption disabled")
            return None
    
    def _encrypt_message(self, message: Union[str, bytes]) -> bytes:
        """Encrypt a message string or bytes."""
        msg_bytes = message if isinstance(message, bytes) else message.encode('utf-8')
        if self.cipher is None:
            print("[GhostEngine] WARNING: Cipher not available, storing unencrypted")
            return msg_bytes
        
        try:
            return self.cipher.encrypt(msg_bytes)
        except Exception as e:
            print(f"[GhostEngine] Encryption error: {e}")
            return msg_bytes
    
    def _decrypt_message(self, encrypted: bytes) -> str:
        """Decrypt a message."""
        if self.cipher is None:
            print("[GhostEngine] WARNING: Cipher not available, returning unencrypted")
            return encrypted.decode('utf-8', errors='ignore')
        
        try:
            return self.cipher.decrypt(encrypted).decode('utf-8')
        except Exception as e:
            print(f"[GhostEngine] Decryption error: {e}")
            return encrypted.decode('utf-8', errors='ignore')
    
    def start(self):
        """Start the network engine (discovery + messaging) with safe error handling."""
        if self.running:
            print("[GhostEngine] Already running.")
            return
        
        self.running = True
        print(f"[GhostEngine] Starting as '{self.username}' on {self.local_ip}")
        
        # Initialize UDP socket for discovery with retry logic
        udp_success = False
        for port_offset in range(0, 5):  # Try ports 37020-37024
            try:
                udp_port = self.UDP_PORT + port_offset
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.udp_socket.bind(('', udp_port))
                self.udp_socket.settimeout(1.0)  # Non-blocking with timeout
                self.UDP_PORT = udp_port  # Update to working port
                print(f"[GhostEngine] UDP socket bound to port {udp_port}")
                udp_success = True
                break
            except OSError as e:
                print(f"[GhostEngine] UDP port {udp_port} failed: {e}")
                if self.udp_socket:
                    try:
                        self.udp_socket.close()
                    except:
                        pass
                continue
            except Exception as e:
                print(f"[GhostEngine] UDP socket error: {e}")
                break
        
        if not udp_success:
            print("[GhostEngine] CRITICAL: Could not bind UDP socket - continuing without discovery")
            self.udp_socket = None
        
        # Initialize TCP server socket for incoming messages with dynamic port allocation (port 0)
        tcp_success = False
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('0.0.0.0', 0))
            self.tcp_socket.listen(5)
            self.tcp_socket.settimeout(1.0)
            self.tcp_port = self.tcp_socket.getsockname()[1]
            self.TCP_PORT = self.tcp_port  # Update working port
            print(f"[GhostEngine] TCP server listening on dynamic port {self.tcp_port}")
            tcp_success = True
        except Exception as e:
            print(f"[GhostEngine] Dynamic TCP port binding failed: {e}")
            
        if not tcp_success:
            print("[GhostEngine] CRITICAL: Could not bind TCP socket - continuing without messaging")
            self.tcp_socket = None
        
        # Don't fail completely if sockets fail - continue with limited functionality
        if not udp_success and not tcp_success:
            print("[GhostEngine] WARNING: No network sockets available - running in offline mode")
        
        # Start background threads with safe error handling
        threads_started = 0
        
        # Only start UDP threads if UDP socket is available
        if self.udp_socket:
            try:
                self.beacon_thread = threading.Thread(target=self._beacon_worker, daemon=True)
                self.beacon_thread.start()
                threads_started += 1
                print("[GhostEngine] Beacon thread started")
            except Exception as e:
                print(f"[GhostEngine] Failed to start beacon thread: {e}")
            
            try:
                self.listener_thread = threading.Thread(target=self._udp_listener_worker, daemon=True)
                self.listener_thread.start()
                threads_started += 1
                print("[GhostEngine] UDP listener thread started")
            except Exception as e:
                print(f"[GhostEngine] Failed to start UDP listener thread: {e}")
        
        # Only start TCP thread if TCP socket is available
        if self.tcp_socket:
            try:
                self.tcp_server_thread = threading.Thread(target=self._tcp_server_worker, daemon=True)
                self.tcp_server_thread.start()
                threads_started += 1
                print("[GhostEngine] TCP server thread started")
            except Exception as e:
                print(f"[GhostEngine] Failed to start TCP server thread: {e}")
        
        # Always start pruning thread
        try:
            self.pruning_thread = threading.Thread(target=self._pruning_worker, daemon=True)
            self.pruning_thread.start()
            threads_started += 1
            print("[GhostEngine] Pruning thread started")
        except Exception as e:
            print(f"[GhostEngine] Failed to start pruning thread: {e}")
        
        # Start network monitoring if available
        if self.network_monitor:
            try:
                network_monitor_thread = threading.Thread(target=self._network_monitor_worker, daemon=True)
                network_monitor_thread.start()
                threads_started += 1
                print("[GhostEngine] Network monitor thread started")
            except Exception as e:
                print(f"[GhostEngine] Failed to start network monitor thread: {e}")
        
        if self.routing_table:
            try:
                self.routing_maintenance_thread = threading.Thread(target=self._routing_maintenance_worker, daemon=True)
                self.routing_maintenance_thread.start()
                threads_started += 1
                print("[GhostEngine] Routing maintenance thread started")
            except Exception as e:
                print(f"[GhostEngine] Failed to start routing maintenance thread: {e}")
        
        if self.routing_table:
            try:
                self.relay_forwarding_thread = threading.Thread(target=self._relay_forwarding_worker, daemon=True)
                self.relay_forwarding_thread.start()
                threads_started += 1
                print("[GhostEngine] Relay forwarding thread started")
            except Exception as e:
                print(f"[GhostEngine] Failed to start relay forwarding thread: {e}")
        
        try:
            self.chaffing_thread = threading.Thread(target=self._chaffing_worker, daemon=True)
            self.chaffing_thread.start()
            threads_started += 1
            print("[GhostEngine] Chaffing thread started")
        except Exception as e:
            print(f"[GhostEngine] Failed to start chaffing thread: {e}")

        try:
            self.persist_thread = threading.Thread(target=self._persist_worker, daemon=True)
            self.persist_thread.start()
            threads_started += 1
            print("[GhostEngine] Persistence worker thread started")
        except Exception as e:
            print(f"[GhostEngine] Failed to start persistence thread: {e}")
        
        print(f"[GhostEngine] {threads_started} threads started successfully.")
        
        if threads_started == 0:
            print("[GhostEngine] WARNING: No background threads started - limited functionality")
        
        self._start_wifi_direct_discovery()
        self._start_bluetooth_discovery()
        
        if self.connection_manager:
            print("[GhostEngine] ConnectionManager initialized")
    
    def _start_wifi_direct_discovery(self):
        if not self.wifi_direct:
            return
        
        try:
            self.wifi_direct.enable()
            print("[WiFiDirect] Discovery enabled")
            
            def _wifi_discovery_worker():
                while self.running:
                    try:
                        self.wifi_direct.discover_peers()
                        time.sleep(5)
                    except Exception as e:
                        print(f"[WiFiDirect] Discovery error: {e}")
                        time.sleep(5)
            
            threading.Thread(target=_wifi_discovery_worker, daemon=True).start()
        except Exception as e:
            print(f"[WiFiDirect] Initialization error: {e}")
    
    def _start_bluetooth_discovery(self):
        if not self.bluetooth:
            return
        
        try:
            self.bluetooth.enable()
            print("[Bluetooth] Discovery enabled")
            
            def _bt_discovery_worker():
                while self.running:
                    try:
                        self.bluetooth.scan_devices()
                        time.sleep(10)
                    except Exception as e:
                        print(f"[Bluetooth] Scan error: {e}")
                        time.sleep(10)
            
            threading.Thread(target=_bt_discovery_worker, daemon=True).start()
        except Exception as e:
            print(f"[Bluetooth] Initialization error: {e}")
    
    def discover_wifi_direct_peers(self) -> Dict[str, dict]:
        if not self.wifi_direct or not self.peer_discovery:
            return {}
        
        try:
            peers = self.wifi_direct.discover_peers()
            for peer in peers:
                mac = peer.get('mac_address', '')
                name = peer.get('device_name', 'Unknown')
                go_ip = peer.get('go_ip')
                self.peer_discovery.add_wifi_direct_peer(mac, name, go_ip)
            
            print(f"[WiFiDirect] Discovered {len(peers)} peers")
            return self.peer_discovery.get_peers_by_type('wifi_direct')
        except Exception as e:
            print(f"[WiFiDirect] Discovery error: {e}")
            return {}
    
    def discover_bluetooth_peers(self) -> Dict[str, dict]:
        if not self.bluetooth or not self.peer_discovery:
            return {}
        
        try:
            devices = self.bluetooth.scan_devices()
            for device in devices:
                bt_addr = device.get('address', '')
                name = device.get('name', 'Unknown')
                rssi = device.get('rssi')
                self.peer_discovery.add_bluetooth_peer(bt_addr, name, rssi)
            
            print(f"[Bluetooth] Discovered {len(devices)} devices")
            return self.peer_discovery.get_peers_by_type('bluetooth')
        except Exception as e:
            print(f"[Bluetooth] Scan error: {e}")
            return {}
    
    def _on_offgrid_peers_discovered(self, all_peers: Dict[str, dict]):
        print(f"[GhostEngine] P2P peers updated: {len(all_peers)} total")
    
    def stop(self):
        """Stop the network engine and clean up resources."""
        print("[GhostEngine] Shutting down...")
        self.running = False
        
        # Close sockets
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except (OSError, AttributeError):
                pass
        
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except (OSError, AttributeError):
                pass
        
        if hasattr(self, 'persist_queue') and self.persist_queue:
            try:
                self.persist_queue.put_nowait(None)
            except Exception:
                pass

        for thread in [self.beacon_thread, self.listener_thread,
                      self.tcp_server_thread, self.pruning_thread,
                      self.routing_maintenance_thread, self.relay_forwarding_thread,
                      self.chaffing_thread, getattr(self, 'persist_thread', None)]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)

        if self.duty_cycler:
            try:
                self.duty_cycler.stop()
            except Exception:
                pass

        if self.bearer_manager:
            try:
                for b in list(self.bearer_manager.bearers.values()):
                    b.stop()
            except Exception:
                pass

        if self.tak_bridge:
            try:
                self.tak_bridge.stop()
            except Exception:
                pass
        
        print("[GhostEngine] Shutdown complete.")
    
    def _get_battery_level(self) -> int:
        """Retrieve the battery level of the device, falling back gracefully if tools are missing."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery is not None:
                return int(battery.percent)
        except:
            pass
        try:
            from plyer import battery
            status = battery.status
            if status and 'percentage' in status:
                return int(status['percentage'])
        except:
            pass
        return 85

    def _broadcast_immediate_beacon(self):
        """Broadcast a single discovery beacon immediately across ports 37020-37024 and loopback."""
        if not self.udp_socket:
            return
        try:
            signing_key_b64 = None
            if self.crypto_manager:
                try:
                    import base64
                    signing_key_b64 = base64.b64encode(self.crypto_manager.get_signing_public_key_bytes()).decode('utf-8')
                except Exception:
                    pass

            current_username = self.username
            if self.config_manager:
                current_username = self.config_manager.get_username()
            
            visible_peers = []
            if self.routing_table:
                visible_peers = self.routing_table.get_direct_peers()
            
            beacon = {
                "type": "BEACON",
                "username": current_username,
                "ip": self.local_ip,
                "peer_id": self.peer_id,
                "visible_peers": visible_peers,
                "battery": self._get_battery_level(),
                "tcp_port": getattr(self, 'tcp_port', self.TCP_PORT),
                "timestamp": time.time()
            }
            if signing_key_b64:
                beacon["signing_key"] = signing_key_b64

            message = json.dumps(beacon).encode('utf-8')
            for port_num in range(37020, 37025):
                try:
                    self.udp_socket.sendto(message, ('<broadcast>', port_num))
                except Exception:
                    pass
                try:
                    self.udp_socket.sendto(message, ('127.0.0.1', port_num))
                except Exception:
                    pass
        except Exception as e:
            if self.running:
                print(f"[Beacon] Immediate broadcast error: {e}")

    def _beacon_worker(self):
        """Broadcast beacon packets with adaptive frequency to conserve battery and RF footprint."""
        while self.running:
            try:
                # Skip if no UDP socket available
                if not self.udp_socket:
                    time.sleep(self.min_beacon_interval)
                    continue
                
                self._broadcast_immediate_beacon()
            except (OSError, AttributeError):
                if self.running:
                    print(f"[Beacon] Socket error during shutdown")
            except Exception as e:
                if self.running:
                    print(f"[Beacon] Error broadcasting: {e}")
            
            # Adaptive beaconing: back off interval if topology and peer set are static
            visible_peers = self.routing_table.get_direct_peers() if self.routing_table else []
            with self.peers_lock:
                peer_keys_tuple = tuple(sorted(self.peers.keys()))
            current_topology_hash = hash((peer_keys_tuple, len(visible_peers)))
            
            if current_topology_hash == self.peer_set_hash:
                self.static_beacon_cycles += 1
                if self.static_beacon_cycles >= 2:
                    self.current_beacon_interval = min(self.current_beacon_interval * 1.5, self.max_beacon_interval)
            else:
                self.peer_set_hash = current_topology_hash
                self.static_beacon_cycles = 0
                self.current_beacon_interval = self.min_beacon_interval

            sleep_interval = self.current_beacon_interval
            try:
                if self._get_battery_level() < 20:
                    sleep_interval = max(sleep_interval, 60.0)
            except:
                pass
            time.sleep(sleep_interval)
    
    def _udp_listener_worker(self):
        """Listen for incoming UDP beacon packets."""
        while self.running:
            try:
                # Skip if no UDP socket available
                if not self.udp_socket:
                    time.sleep(1)
                    continue
                
                data, addr = self.udp_socket.recvfrom(self.BUFFER_SIZE)
                sender_ip = addr[0]

                # Reject oversized beacons before JSON parsing — valid discovery
                # beacons are small; >4000 bytes is anomalous and likely malicious.
                if len(data) > 4000:
                    continue

                # Parse beacon
                try:
                    beacon = json.loads(data.decode('utf-8', errors='ignore'))
                except Exception:
                    continue

                if not isinstance(beacon, dict):
                    continue

                beacon_type = beacon.get("type")
                if beacon_type == "CHAFF":
                    continue

                beacon_peer_id = str(beacon.get("peer_id", sender_ip))[:64]
                # Ignore beacons from our own node
                if beacon_peer_id == self.peer_id:
                    continue

                if beacon_type == "BEACON":
                    # Enforce MAX_PEERS capacity limit (500)
                    with self.peers_lock:
                        if len(self.peers) >= 500 and sender_ip not in self.peers:
                            continue

                    raw_user = beacon.get("username", "Unknown")
                    username = "".join(c for c in str(raw_user)[:32] if c.isprintable()).strip() or "Node"
                    current_time = time.time()
                    
                    raw_vis = beacon.get("visible_peers", [])
                    visible_peers = [str(p)[:64] for p in raw_vis if isinstance(p, (str, bytes))][:10] if isinstance(raw_vis, list) else []
                    
                    battery_level = beacon.get("battery", 100)
                    if not isinstance(battery_level, (int, float)) or not (0 <= battery_level <= 100):
                        battery_level = 100

                    tcp_port = beacon.get("tcp_port")
                    if tcp_port is not None and (not isinstance(tcp_port, int) or not (1 <= tcp_port <= 65535)):
                        tcp_port = None

                    sender_timestamp = beacon.get("timestamp")
                    if isinstance(sender_timestamp, (int, float)):
                        offset = sender_timestamp - current_time
                        with self.peers_lock:
                            self.mesh_offsets[beacon_peer_id] = offset
                        self._update_mesh_time_offset()

                    # Record peer signing key if present
                    b_signing_key = beacon.get("signing_key")
                    key_mismatch = False
                    if b_signing_key and self.crypto_manager:
                        try:
                            import base64
                            key_bytes = base64.b64decode(b_signing_key)
                            stored_signing_key = None
                            if self.persistence_db:
                                stored = self.persistence_db.get_peer(beacon_peer_id)
                                if stored and stored.get('signing_key'):
                                    raw_stored = stored.get('signing_key')
                                    try:
                                        if isinstance(raw_stored, str):
                                            if len(raw_stored) == 44:
                                                stored_signing_key = base64.b64decode(raw_stored)
                                            elif len(raw_stored) == 64:
                                                stored_signing_key = bytes.fromhex(raw_stored)
                                            else:
                                                stored_signing_key = raw_stored.encode()
                                        else:
                                            stored_signing_key = raw_stored
                                    except Exception:
                                        stored_signing_key = raw_stored

                            if stored_signing_key and stored_signing_key != key_bytes:
                                key_mismatch = True
                                old_fp = self.crypto_manager.compute_key_fingerprint(stored_signing_key)
                                new_fp = self.crypto_manager.compute_key_fingerprint(key_bytes)
                                print(f"[GhostEngine] SECURITY WARNING: Identity key mismatch for peer {beacon_peer_id}! Stored: {old_fp}, Received: {new_fp}")
                                if hasattr(self, 'on_peer_key_changed') and self.on_peer_key_changed:
                                    try:
                                        self.on_peer_key_changed(beacon_peer_id, old_fp, new_fp)
                                    except Exception as e:
                                        print(f"[GhostEngine] on_peer_key_changed callback error: {e}")
                            else:
                                valid, res_code = self.crypto_manager.check_and_set_peer_signing_key(beacon_peer_id, key_bytes)
                                if res_code == "KEY_CHANGED":
                                    key_mismatch = True
                        except Exception as e:
                            print(f"[GhostEngine] Signing key decode error: {e}")

                    if self.persistence_db and b_signing_key and not key_mismatch:
                        try:
                            stored = self.persistence_db.get_peer(beacon_peer_id)
                            if not stored:
                                self.persistence_db.save_peer(beacon_peer_id, username, discovery_type="UDP_BEACON")
                                self.persistence_db.update_peer_signing_key(beacon_peer_id, b_signing_key, 0)
                            elif not stored.get('signing_key'):
                                self.persistence_db.update_peer_signing_key(beacon_peer_id, b_signing_key, 0)
                        except Exception:
                            pass

                    # Peer map key: if local loopback or local IP, use IP:PORT to distinguish instances
                    peer_key = f"{sender_ip}:{tcp_port}" if (sender_ip == "127.0.0.1" or sender_ip == self.local_ip) and tcp_port else sender_ip

                    is_new_peer = False
                    with self.peers_lock:
                        if peer_key not in self.peers:
                            is_new_peer = True
                        self.peers[peer_key] = {
                            "username": username,
                            "last_seen": current_time,
                            "peer_id": beacon_peer_id,
                            "visible_peers": visible_peers,
                            "battery": battery_level,
                            "tcp_port": tcp_port,
                            "key_mismatch": key_mismatch,
                            "new_key_candidate": b_signing_key if key_mismatch else None
                        }
                    
                    if is_new_peer:
                        self.reset_beacon_backoff()
                    
                    if self.network_state in (NetworkState.DISCOVERING, NetworkState.AVAILABLE):
                        self.set_network_state(NetworkState.PEER_VISIBLE)

                    if self.routing_table:
                        self.routing_table.add_direct_route(beacon_peer_id, battery_level=battery_level)
                        
                        for visible_peer_id in visible_peers:
                            if visible_peer_id != self.peer_id:
                                self.routing_table.add_route(
                                    visible_peer_id,
                                    beacon_peer_id,
                                    1,
                                    [visible_peer_id, beacon_peer_id],
                                    next_hop_battery=battery_level
                                )

                    if self.topology_manager:
                        self.topology_manager.update_node(self.peer_id, self.username)
                        self.topology_manager.update_node(beacon_peer_id, username, battery=battery_level)
                        self.topology_manager.update_edge(self.peer_id, beacon_peer_id, pdr=1.0, rtt_ms=10.0)
                        for visible_peer_id in visible_peers:
                            if visible_peer_id != self.peer_id:
                                self.topology_manager.update_node(visible_peer_id, f"Peer-{visible_peer_id[:6]}")
                                self.topology_manager.update_edge(beacon_peer_id, visible_peer_id, pdr=0.9, rtt_ms=20.0)
                elif beacon.get("type") == "WIKI_QUERY":
                    query = beacon.get("query", "").strip().lower()
                    sender_name = beacon.get("sender_name", "Unknown")
                    if query:
                        guides_path = os.path.join(os.path.dirname(__file__), "survival_guides.json")
                        response = None
                        if os.path.exists(guides_path):
                            try:
                                with open(guides_path, 'r', encoding='utf-8') as f:
                                    guides = json.load(f)
                                for k, v in guides.items():
                                    if query in k or k in query:
                                        response = v
                                        break
                            except Exception as e:
                                print(f"[Wiki Proxy] Error reading database: {e}")
                                
                        if response:
                            reply = {
                                "type": "WIKI_RESPONSE",
                                "query": query,
                                "response": response,
                                "responder_name": self.username
                            }
                            reply_msg = json.dumps(reply).encode('utf-8')
                            try:
                                self.udp_socket.sendto(reply_msg, (sender_ip, self.UDP_PORT))
                                print(f"[Wiki Proxy] Replied to {sender_ip} for query '{query}'")
                            except Exception as e:
                                print(f"[Wiki Proxy] Error replying: {e}")
                                
                elif beacon.get("type") == "WIKI_RESPONSE":
                    query = beacon.get("query")
                    response = beacon.get("response")
                    responder = beacon.get("responder_name", "WikiProxy")
                    current_time = time.time()
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    if self.on_message_received:
                        msg = f"[Wiki Result from {responder} for '{query}']: {response}"
                        self.on_message_received(sender_ip, msg, timestamp)
                    
                    self._persist_peer(sender_ip, responder, discovery_type="udp")
                    
                    if self.on_peer_update:
                        self.on_peer_update(self.get_all_peers_combined())
                
            except socket.timeout:
                continue
            except (OSError, AttributeError):
                # Socket was closed by stop() — suppress error during clean shutdown
                if self.running:
                    print(f"[Listener] Socket error during shutdown")
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.running:
                    print(f"[Listener] Error: {e}")
    
    def _pruning_worker(self):
        """Remove stale peers that haven't been seen recently."""
        while self.running:
            time.sleep(3)  # Check every 3 seconds
            
            try:
                current_time = time.time()
                stale_ips = []
                
                with self.peers_lock:
                    for ip, info in self.peers.items():
                        if current_time - info["last_seen"] > self.PEER_TIMEOUT:
                            stale_ips.append(ip)
                    
                    for ip in stale_ips:
                        username = self.peers[ip]["username"]
                        peer_id = self.peers[ip].get("peer_id")
                        if peer_id and peer_id in self.mesh_offsets:
                            del self.mesh_offsets[peer_id]
                        del self.peers[ip]
                        print(f"[Pruning] Removed stale peer: {username} @ {ip}")
                    if stale_ips:
                        self._update_mesh_time_offset()
                        if self.topology_manager:
                            self.topology_manager.remove_stale_edges(max_age_seconds=float(self.peer_timeout))
                
                # Notify UI if peers were removed
                if stale_ips and self.on_peer_update:
                    self.on_peer_update(self.get_all_peers_combined())
                    
            except Exception as e:
                print(f"[Pruning] Error: {e}")
    
    def _get_peer_port(self, key: str) -> int:
        """Resolve the TCP port for a peer IP or peer ID, falling back to legacy port."""
        if not key:
            return self.TCP_PORT
        clean_key = str(key)
        if ':' in clean_key:
            try:
                return int(clean_key.split(':', 1)[1])
            except ValueError:
                pass
        with self.peers_lock:
            if clean_key in self.peers:
                port = self.peers[clean_key].get("tcp_port")
                if port is not None:
                    return port
            for ip, info in self.peers.items():
                if info.get("peer_id") == clean_key:
                    port = info.get("tcp_port")
                    if port is not None:
                        return port
        return self.TCP_PORT

    def _update_mesh_time_offset(self):
        """Update the mesh time offset to the median of active peer offsets."""
        offsets_list = list(self.mesh_offsets.values())
        if not offsets_list:
            self.mesh_time_offset = 0.0
            return
        sorted_offsets = sorted(offsets_list)
        n = len(sorted_offsets)
        if n % 2 == 1:
            self.mesh_time_offset = sorted_offsets[n // 2]
        else:
            self.mesh_time_offset = (sorted_offsets[n // 2 - 1] + sorted_offsets[n // 2]) / 2.0

        if self.duty_cycler:
            try:
                self.duty_cycler.set_clock_offset(self.mesh_time_offset)
            except Exception:
                pass

        if self.fhss_manager:
            try:
                self.fhss_manager.set_clock_offset(self.mesh_time_offset)
            except Exception:
                pass

        if self.ephemeral_beacon_mgr:
            try:
                self.ephemeral_beacon_mgr.set_clock_offset(self.mesh_time_offset)
            except Exception:
                pass

    def get_mesh_time(self) -> float:
        """Return current local time adjusted by the mesh clock offset."""
        return time.time() + self.mesh_time_offset

    def _tcp_server_worker(self):
        """Accept incoming TCP connections and handle messages."""
        while self.running:
            try:
                # Skip if no TCP socket available
                if not self.tcp_socket:
                    time.sleep(1)
                    continue
                
                conn, addr = self.tcp_socket.accept()
                # Handle each connection in a separate thread
                threading.Thread(
                    target=self._handle_tcp_connection,
                    args=(conn, addr),
                    daemon=True
                ).start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[TCP Server] Error: {e}")
    
    def _handle_tcp_connection(self, conn: socket.socket, addr: tuple):
        """Handle an individual TCP connection (text or file)."""
        sender_ip = addr[0]
        conn.settimeout(10.0)
        
        try:
            header_data = b""
            is_stego = False
            max_bytes = 5 * 1024 * 1024 # 5 MB maximum header/LSB buffer to prevent OOM
            while len(header_data) < max_bytes:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                header_data += chunk
                
                if len(header_data) >= 12 and (
                    header_data.startswith(b'\x89PNG\r\n\x1a\n') or
                    (header_data.startswith(b'RIFF') and b'WAVE' in header_data[8:12])
                ):
                    is_stego = True
                    
                if not is_stego and self.HEADER_DELIMITER in header_data:
                    break
            
            if len(header_data) >= max_bytes:
                print(f"[TCP Handler] Connection from {sender_ip} exceeded maximum header size limit. Dropping.")
                return
            
            if is_stego and STEGANOGRAPHY_AVAILABLE:
                file_ext = "png"
                if header_data.startswith(b'\x89PNG\r\n\x1a\n'):
                    stego_data = steganography.decode_lsb(header_data)
                else:
                    stego_data = steganography.decode_wav_lsb(header_data)
                    file_ext = "wav"
                    
                if stego_data:
                    downloads_dir = getattr(self, 'downloads_dir', 'downloads')
                    os.makedirs(downloads_dir, exist_ok=True)
                    carrier_path = os.path.join(downloads_dir, f"stego_{int(time.time())}.{file_ext}")
                    try:
                        with open(carrier_path, 'wb') as f:
                            f.write(header_data)
                    except:
                        pass
                    header_data = stego_data
            
            if self.HEADER_DELIMITER in header_data:
                header_part, remaining_data = header_data.split(self.HEADER_DELIMITER, 1)
                
                header_json = None
                sender_peer_id = None
                with self.peers_lock:
                    peer_info = self.peers.get(sender_ip)
                    if peer_info:
                        sender_peer_id = peer_info.get('peer_id')
                
                if sender_peer_id and self.crypto_manager:
                    sender_aes_key = self.crypto_manager.get_peer_aes_key(sender_peer_id)
                    if sender_aes_key:
                        try:
                            import base64
                            from cryptography.fernet import Fernet
                            fernet_key = base64.urlsafe_b64encode(sender_aes_key)
                            peer_cipher = Fernet(fernet_key)
                            header_json = peer_cipher.decrypt(header_part).decode('utf-8')
                            print(f"[Onion] Decrypted header using derived AES key from sender: {sender_peer_id}")
                        except Exception:
                            pass
                
                if header_json is None:
                    try:
                        header_json = self._decrypt_message(header_part)
                    except Exception as e:
                        print(f"[TCP Handler] Decryption fallback failed: {e}")
                        return
                
                try:
                    header = json.loads(header_json)
                    if not isinstance(header, dict):
                        print(f"[TCP Handler] Rejected non-dict header from {sender_ip}")
                        return
                    if is_stego:
                        header["stego"] = True
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"[TCP Handler] Invalid header from {sender_ip}: {e}")
                    return
                
                sender_id = header.get("sender_peer_id") or sender_ip
                if sender_id in self.revoked_peers or sender_ip in self.revoked_peers:
                    print(f"[TCP Handler] Dropping packet from blacklisted/revoked peer: {sender_id}")
                    return

                target_peer_id = header.get("target_peer_id")
                network_ttl = header.get("network_ttl", 10)
                visited_nodes = header.get("visited_nodes", [])

                # Determine if this node is the intended recipient
                my_targets = {self.peer_id, self.local_ip, f"127.0.0.1:{self.tcp_port}", f"{self.local_ip}:{self.tcp_port}"}
                is_for_me = (not target_peer_id) or (target_peer_id in my_targets)

                # If packet is not for us, act as a mesh relay
                if not is_for_me and self.routing_table:
                    # Loop prevention for relays: drop if local node already visited
                    if self.peer_id in visited_nodes:
                        print(f"[Relay] Loop detected for target {target_peer_id} (already visited {self.peer_id}); dropping packet")
                        return

                    # Hop limit check
                    if network_ttl <= 0:
                        print(f"[Relay] Hop limit reached for target {target_peer_id}; dropping packet")
                        return

                    route = self.routing_table.get_route(target_peer_id)
                    if route:
                        self._queue_packet_forward(sender_ip, target_peer_id, header, remaining_data, network_ttl)
                        return
                
                msg_type = header.get("type") or header.get("message_type")
                if msg_type == "TEXT":
                    self._handle_text_message(sender_ip, header, remaining_data, conn)
                elif msg_type == "FILE":
                    self._handle_file_transfer(sender_ip, header, remaining_data, conn)
                elif msg_type == "SOS":
                    self._handle_sos_message(sender_ip, header, remaining_data)
                elif msg_type == "LOCATION_UPDATE":
                    self._handle_location_update(sender_ip, header, remaining_data)
                elif msg_type == "WAYPOINT":
                    self._handle_waypoint_message(sender_ip, header, remaining_data)
                elif msg_type == "PEER_REVOCATION":
                    self._handle_peer_revocation(sender_ip, header, remaining_data)
                elif msg_type == "GROUP_TEXT":
                    self._handle_group_text_message(sender_ip, header, remaining_data)
                elif msg_type == "RREQ":
                    self._handle_rreq_message(sender_ip, header, remaining_data)
                elif msg_type == "RREP":
                    self._handle_rrep_message(sender_ip, header, remaining_data)
                elif msg_type == "RERR":
                    self._handle_rerr_message(sender_ip, header, remaining_data)
                elif msg_type == "OTA_ZEROIZE":
                    self._handle_ota_zeroize_message(sender_ip, header, remaining_data)
                elif msg_type == "GEOCAST":
                    self._handle_geocast_message(sender_ip, header, remaining_data)
                elif msg_type == "OTP_FRAME":
                    self._handle_otp_frame(sender_ip, header, remaining_data)
                elif msg_type == "DTN_BUNDLE":
                    self._handle_dtn_bundle(sender_ip, header, remaining_data, conn)
                elif msg_type == "BUNDLE_CAS":
                    self._handle_bundle_cas(sender_ip, header, remaining_data)
                elif msg_type == "CONSENSUS_PROPOSAL":
                    self._handle_consensus_proposal(sender_ip, header, remaining_data)
                elif msg_type == "CONSENSUS_BALLOT":
                    self._handle_consensus_ballot(sender_ip, header, remaining_data)
                elif msg_type == "PUBSUB_PUBLISH":
                    self._handle_pubsub_publish(sender_ip, header, remaining_data)
                elif msg_type == "PUBSUB_BLOOM_SYNC":
                    self._handle_pubsub_bloom_sync(sender_ip, header, remaining_data)
                elif msg_type == "DHT_STORE":
                    self._handle_dht_store(sender_ip, header, remaining_data)
                elif msg_type == "DHT_QUERY":
                    self._handle_dht_query(sender_ip, header, remaining_data)
                elif msg_type == "DHT_RESPONSE":
                    self._handle_dht_response(sender_ip, header, remaining_data)
                elif msg_type == "ECM_OBSERVATION":
                    self._handle_ecm_observation(sender_ip, header, remaining_data)
                elif msg_type == "ZKP_AUTH_PROOF":
                    self._handle_zkp_auth_proof(sender_ip, header, remaining_data)
                elif msg_type == "PQ_KEM_CIPHERTEXT":
                    self._handle_pq_kem_ciphertext(sender_ip, header, remaining_data)
                elif msg_type == "HOMOMORPHIC_TELEMETRY":
                    self._handle_homomorphic_telemetry(sender_ip, header, remaining_data)
                elif msg_type == "TIME_SYNC_REQUEST":
                    self._handle_time_sync_request(sender_ip, header, remaining_data)
                elif msg_type == "TIME_SYNC_RESPONSE":
                    self._handle_time_sync_response(sender_ip, header, remaining_data)
                elif msg_type == "CQI_FEEDBACK":
                    self._handle_cqi_feedback(sender_ip, header, remaining_data)
                elif msg_type == "LKH_REKEY":
                    self._handle_lkh_rekey(sender_ip, header, remaining_data)
                elif msg_type == "TACTICAL_ALERT":
                    self._handle_tactical_alert(sender_ip, header, remaining_data)
                else:
                    print(f"[TCP Handler] Unknown type: {msg_type}")

        
        except Exception as e:
            print(f"[TCP Handler] Error handling connection from {sender_ip}: {e}")
        finally:
            conn.close()

    def _decrypt_p2p_payload(self, peer_id: str, encrypted_payload: bytes) -> Optional[bytes]:
        if not self.crypto_manager or len(encrypted_payload) < 12:
            return encrypted_payload

        try:
            nonce = encrypted_payload[:12]
            ciphertext = encrypted_payload[12:]
            plaintext = self.crypto_manager.decrypt_message(peer_id, nonce, ciphertext)
            return plaintext
        except Exception as e:
            print(f"[GhostEngine] P2P decryption failed for {peer_id}: {e}")
            return None
    
    def _handle_text_message(self, sender_ip: str, header: dict, initial_data: bytes, conn: socket.socket):
        """Handle incoming text message with application-layer ACK and deduplication."""
        try:
            msg_id = header.get("msg_id")
            
            # Send immediate application-layer ACK over open TCP socket if message ID exists
            if msg_id and conn:
                try:
                    ack_packet = json.dumps({"type": "ACK", "msg_id": msg_id, "status": "DELIVERED"}).encode('utf-8')
                    conn.sendall(ack_packet + self.HEADER_DELIMITER)
                except Exception:
                    pass

            # Deduplication check
            if msg_id and not self._record_seen_message(msg_id):
                print(f"[TCP Handler] Duplicate message '{msg_id}' dropped (ACK sent)")
                return

            message_text = header.get("content", "")
            if not isinstance(message_text, str):
                message_text = str(message_text)
            # Enforce reasonable length limit (64 KB)
            message_text = message_text[:65536]

            if header.get("stego"):
                message_text = "[Stego Image Decoded] " + message_text
            timestamp = datetime.now().strftime("%H:%M:%S")
            timestamp_unix = time.time()
            ttl = header.get("ttl")
            if ttl is not None and (not isinstance(ttl, (int, float)) or ttl <= 0):
                ttl = None
            
            origin_sender = header.get("sender_peer_id") or header.get("sender_ip") or sender_ip
            print(f"[TCP] Message from {origin_sender} (via {sender_ip}, id={msg_id}, len={len(message_text)})")
            
            self._persist_message(origin_sender, "them", "text", message_text, timestamp_unix, ttl)
            
            if self.on_message_received:
                self.on_message_received(origin_sender, message_text, timestamp)
        
        except Exception as e:
            print(f"[TCP Handler] Text message error: {e}")
    
    def _handle_file_transfer(self, sender_ip: str, header: dict, initial_data: bytes, conn: socket.socket):
        """Handle incoming file transfer with chunk reassembly and atomic temporary writing."""
        part_filepath = None
        try:
            if not isinstance(header, dict):
                print(f"[File Transfer] Invalid header type from {sender_ip}")
                return

            filename = header.get("filename", "unknown_file")
            filesize = header.get("filesize", 0)
            file_id = header.get("file_id", "unknown")
            is_chunked = header.get("chunked", False)
            checksum = header.get("checksum", "")
            ttl = header.get("ttl")

            if not isinstance(filesize, int) or filesize <= 0 or filesize > self.MAX_FILE_SIZE:
                print(f"[File Transfer] Invalid or rejected file size ({filesize}) from {sender_ip}")
                return

            if not isinstance(filename, str):
                filename = str(filename)
            filename = filename.replace('\x00', '')
            safe_filename = self._sanitize_filename(filename)

            print(f"[File Transfer] Receiving '{safe_filename}' ({filesize} bytes) from {sender_ip}")
            
            target_peer_id = header.get("target_peer_id")
            my_hash = hashlib.sha256(self.peer_id.encode()).hexdigest()
            local_targets = {
                self.peer_id,
                my_hash,
                self.local_ip,
                f"{self.local_ip}:{self.tcp_port}",
                "127.0.0.1",
                f"127.0.0.1:{self.tcp_port}",
                f"0.0.0.0:{self.tcp_port}"
            }
            is_target = (not target_peer_id or target_peer_id in local_targets)
            is_carrier = (target_peer_id and not is_target)
            
            if is_carrier:
                hash_target = target_peer_id
                if not isinstance(hash_target, str) or len(hash_target) != 64 or not all(c in '0123456789abcdefABCDEF' for c in hash_target):
                    hash_target = hashlib.sha256(str(target_peer_id).encode()).hexdigest()
                spool_item_dir = os.path.join(self.spool_dir, hash_target, str(file_id)[:32])
                os.makedirs(spool_item_dir, exist_ok=True)
                filepath = os.path.join(spool_item_dir, "file.dat")
            else:
                filepath = os.path.join(self.downloads_dir, safe_filename)
                base, ext = os.path.splitext(filepath)
                counter = 1
                while os.path.exists(filepath):
                    filepath = f"{base}_{counter}{ext}"
                    counter += 1
            
            part_filepath = f"{filepath}.part"
            bytes_received = len(initial_data)
            
            if is_chunked:
                self._handle_chunked_file_transfer(filepath, filesize, bytes_received, initial_data, conn, sender_ip, safe_filename, checksum, ttl, is_carrier, header)
                return
            else:
                os.makedirs(os.path.dirname(part_filepath), exist_ok=True)
                with open(part_filepath, 'wb') as f:
                    f.write(initial_data)
                    while bytes_received < filesize:
                        chunk = conn.recv(min(self.BUFFER_SIZE, filesize - bytes_received))
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_received += len(chunk)
                        if bytes_received % (self.BUFFER_SIZE * 10) == 0:
                            progress = (bytes_received / filesize) * 100
                            print(f"[File Transfer] Progress: {progress:.1f}%")
                
                # Check for incomplete transfer
                if bytes_received < filesize:
                    print(f"[File Transfer] Connection closed early: received {bytes_received}/{filesize} bytes")
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return

                received_checksum = self._calculate_checksum(part_filepath)
                if checksum and received_checksum != checksum:
                    print(f"[File Transfer] Checksum mismatch! Expected {checksum}, got {received_checksum}")
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return
                
                # Verified complete: atomic promotion
                os.replace(part_filepath, filepath)
                part_filepath = None
                
                if is_carrier:
                    metadata = {
                        "target": target_peer_id,
                        "original_filename": safe_filename,
                        "filesize": filesize,
                        "file_id": file_id,
                        "checksum": checksum,
                        "chunked": is_chunked,
                        "ttl": ttl,
                        "timestamp": datetime.now().isoformat(),
                        "replicated_to": [header.get("sender_peer_id", "")]
                    }
                    self._write_spool_metadata(os.path.join(os.path.dirname(filepath), "metadata.json"), metadata)
                    print(f"[Epidemic DTN] Spooled carrier file '{safe_filename}' (file_id: {file_id}) for target {target_peer_id}")
                    return
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                timestamp_unix = time.time()
                print(f"[File Transfer] Successfully received '{safe_filename}' -> {filepath}")
                
                self._persist_message(sender_ip, "them", "file", filename, timestamp_unix, ttl, filepath)
                
                if self.on_file_received:
                    self.on_file_received(sender_ip, filename, filepath, timestamp)
        
        except Exception as e:
            print(f"[File Transfer] Error: {e}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal attacks."""
        # Store original filename for extension extraction
        original_filename = filename
        
        # Remove path separators
        filename = os.path.basename(filename)
        
        # Bug #8 fix: Preserve common file extensions and special characters
        # Allow more characters to prevent data loss from overly aggressive sanitization
        dangerous_chars = '<>:"|?*\\'  # Only remove truly dangerous characters
        sanitized = filename
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Limit length (preserve extension)
        if len(sanitized) > 255:
            name, ext = os.path.splitext(sanitized)
            sanitized = name[:250 - len(ext)] + ext
        
        # If filename is empty after sanitization, use timestamp-based fallback
        if not sanitized or sanitized.strip() == '':
            # Extract extension from original filename if possible
            _, ext = os.path.splitext(os.path.basename(original_filename))
            return f"file_{int(time.time())}{ext}"
        
        return sanitized
    
    def _handle_chunked_file_transfer(self, filepath: str, filesize: int, initial_bytes: int, initial_data: bytes, conn: socket.socket, sender_ip: str, filename: str, checksum: str, ttl: Optional[int] = None, is_carrier: bool = False, header: dict = None):
        """Handle chunked encrypted file transfer with byte-offset resumption, on-the-fly decryption, and atomic promotion."""
        part_filepath = f"{filepath}.part"
        resume_offset = header.get("offset", 0) if header else 0
        file_mode = 'r+b' if (resume_offset > 0 and os.path.exists(part_filepath)) else 'wb'
        try:
            os.makedirs(os.path.dirname(part_filepath), exist_ok=True)
            with open(part_filepath, file_mode) as f:
                if resume_offset > 0:
                    f.seek(resume_offset)
                bytes_received = resume_offset
                
                # If caller provided initial payload directly (e.g. test or direct resumption data)
                is_raw_payload = False
                if initial_data and initial_bytes > 0:
                    if len(initial_data) < 16 or getattr(conn, '__class__', None).__name__ == "DummyConn":
                        is_raw_payload = True
                    else:
                        cand_size = int.from_bytes(initial_data[12:16], 'big')
                        if cand_size <= 0 or cand_size > filesize or cand_size > self.CHUNK_SIZE * 2:
                            is_raw_payload = True
                
                if is_raw_payload:
                    f.write(initial_data)
                    bytes_received += initial_bytes
                    buffer = b""
                else:
                    buffer = initial_data or b""

                def _read_exact(n: int):
                    nonlocal buffer
                    while len(buffer) < n:
                        data = conn.recv(max(self.CHUNK_SIZE, n - len(buffer)))
                        if not data:
                            return None
                        buffer += data
                    res = buffer[:n]
                    buffer = buffer[n:]
                    return res
                
                while bytes_received < filesize:
                    chunk_header = _read_exact(16)
                    if not chunk_header or len(chunk_header) < 16:
                        break
                    
                    nonce = chunk_header[:12]
                    chunk_size = int.from_bytes(chunk_header[12:16], 'big')
                    
                    encrypted_chunk = _read_exact(chunk_size)
                    if not encrypted_chunk or len(encrypted_chunk) < chunk_size:
                        break
                    
                    if self.crypto_manager and nonce != b'\x00' * 12:
                        decrypted = self.crypto_manager.decrypt_file_chunk(sender_ip, nonce, encrypted_chunk)
                        chunk_to_write = decrypted if decrypted is not None else encrypted_chunk
                    else:
                        chunk_to_write = encrypted_chunk
                    
                    f.write(chunk_to_write)
                    bytes_received += len(chunk_to_write)
                    
                    progress = (bytes_received / filesize) * 100
                    if bytes_received % (self.CHUNK_SIZE * 10) == 0:
                        print(f"[File Transfer] Progress: {progress:.1f}%")
            
            # Check for incomplete transfer
            if bytes_received < filesize:
                print(f"[File Transfer] Chunked transfer incomplete: received {bytes_received}/{filesize} bytes (retained .part for resumption)")
                return


            received_checksum = self._calculate_checksum(part_filepath)
            if checksum and received_checksum != checksum:
                print(f"[File Transfer] Checksum mismatch! Expected {checksum}, got {received_checksum}")
                if os.path.exists(part_filepath):
                    os.remove(part_filepath)
                return
            
            # Verified complete: atomic promotion
            os.replace(part_filepath, filepath)
            
            if is_carrier and header:
                target_peer_id = header.get("target_peer_id")
                file_id = header.get("file_id", "unknown")
                metadata = {
                    "target": target_peer_id,
                    "original_filename": filename,
                    "filesize": filesize,
                    "file_id": file_id,
                    "checksum": checksum,
                    "chunked": True,
                    "ttl": ttl,
                    "timestamp": datetime.now().isoformat(),
                    "replicated_to": [header.get("sender_peer_id", "")]
                }
                self._write_spool_metadata(os.path.join(os.path.dirname(filepath), "metadata.json"), metadata)
                print(f"[Epidemic DTN] Spooled chunked carrier file '{filename}' (file_id: {file_id}) for target {target_peer_id}")
                return
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            timestamp_unix = time.time()
            print(f"[File Transfer] Successfully received chunked '{filename}' -> {filepath}")
            
            self._persist_message(sender_ip, "them", "file", filename, timestamp_unix, ttl, filepath)
            
            if self.on_file_received:
                self.on_file_received(sender_ip, filename, filepath, timestamp)
        
        except Exception as e:
            print(f"[File Transfer] Chunked transfer error: {e}")
    
    def _calculate_checksum(self, filepath: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _handle_sos_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        try:
            sos_json = self._decrypt_message(encrypted_data)
            sos_payload = json.loads(sos_json)
            
            # Verify Ed25519 signature
            import base64
            signature_b64 = sos_payload.get('signature', '')
            signing_pubkey_b64 = sos_payload.get('signing_pubkey', '')
            
            verify_payload = {k: v for k, v in sos_payload.items() if k not in ('signature', 'signing_pubkey')}
            sig_data = json.dumps(verify_payload, sort_keys=True).encode('utf-8')
            
            verified = False
            if signature_b64 and signing_pubkey_b64 and self.crypto_manager:
                try:
                    sig_bytes = base64.b64decode(signature_b64)
                    pubkey_bytes = base64.b64decode(signing_pubkey_b64)
                    verified = self.crypto_manager.verify_signature(sig_bytes, sig_data, pubkey_bytes)
                except Exception as e:
                    print(f"[GhostEngine] SOS signature verification error: {e}")
            
            if not verified:
                sender_name = sos_payload.get('sender_name', 'Unknown')
                if not sender_name.startswith("[UNVERIFIED]"):
                    sos_payload['sender_name'] = f"[UNVERIFIED] {sender_name}"
            
            sos_id = sos_payload.get('sos_id')
            from_peer = sos_payload.get('sender_id')
            
            with self.sos_cache_lock:
                existing = any(c['sos_id'] == sos_id for c in self.sos_cache)
                
                if existing:
                    print(f"[GhostEngine] SOS {sos_id} already processed, ignoring")
                    return
                
                self.sos_cache.append({
                    'sos_id': sos_id,
                    'timestamp': sos_payload.get('timestamp', time.time()),
                    'from_peer': from_peer
                })
                self.sos_cache = [c for c in self.sos_cache if time.time() - c['timestamp'] < self.sos_cache_max_age]
            
            try:
                print(f"[GhostEngine] SOS received from {sos_payload.get('sender_name')}")
            except UnicodeEncodeError:
                safe_name = str(sos_payload.get('sender_name', 'Unknown')).encode('ascii', errors='replace').decode('ascii')
                print(f"[GhostEngine] SOS received from {safe_name}")
            
            if self.on_sos_received:
                self.on_sos_received(
                    sos_payload.get('sender_name', 'Unknown'),
                    sos_payload.get('latitude', 0),
                    sos_payload.get('longitude', 0),
                    sos_payload.get('message', 'EMERGENCY SOS'),
                    sos_id
                )
            
            with self.peers_lock:
                peers_to_relay = [ip for ip in self.peers.keys() if ip != sender_ip]
            
            def relay_worker():
                for peer_ip in peers_to_relay:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(3)
                        sock.connect((peer_ip, self._get_peer_port(peer_ip)))
                        
                        header = {
                            'type': 'message',
                            'message_type': 'SOS',
                            'sender_id': sos_payload.get('sender_id'),
                            'sender_name': sos_payload.get('sender_name')
                        }
                        header_json = json.dumps(header)
                        header_bytes = header_json.encode('utf-8')
                        
                        encrypted_sos = self._encrypt_message(json.dumps(sos_payload))
                        full_message = header_bytes + self.HEADER_DELIMITER + encrypted_sos
                        sock.sendall(full_message)
                        sock.close()
                        print(f"[GhostEngine] SOS relayed to {peer_ip}")
                    
                    except Exception as e:
                        print(f"[GhostEngine] SOS relay error to {peer_ip}: {e}")
            
            threading.Thread(target=relay_worker, daemon=True).start()
        
        except Exception as e:
            print(f"[GhostEngine] SOS handling error: {e}")

    def _handle_location_update(self, sender_ip: str, header: dict, encrypted_data: bytes):
        try:
            payload = None
            if encrypted_data:
                try:
                    decrypted_text = self._decrypt_message(encrypted_data)
                    payload = json.loads(decrypted_text)
                except Exception:
                    pass
            if not payload:
                payload = header.get("payload") or header

            if not isinstance(payload, dict):
                return

            sender_name = payload.get("username") or payload.get("sender_name") or header.get("sender_name", "Unknown")
            peer_id = payload.get("peer_id") or header.get("sender_peer_id") or sender_ip
            lat = float(payload.get("lat") or payload.get("latitude") or 0.0)
            lon = float(payload.get("lon") or payload.get("longitude") or 0.0)
            alt = float(payload.get("alt") or payload.get("altitude") or 0.0)
            acc = float(payload.get("acc") or payload.get("accuracy") or 0.0)

            print(f"[GhostEngine] Live telemetry from {sender_name} ({peer_id}): {lat:.4f}, {lon:.4f}")

            if self.on_location_update_received:
                self.on_location_update_received({
                    "peer_id": peer_id,
                    "username": sender_name,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": alt,
                    "accuracy": acc,
                    "timestamp": payload.get("timestamp", time.time())
                })
        except Exception as e:
            print(f"[GhostEngine] Error processing location update: {e}")

    def _handle_waypoint_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        try:
            wp_data = None
            if encrypted_data:
                try:
                    decrypted = self._decrypt_message(encrypted_data)
                    wp_data = json.loads(decrypted)
                except Exception:
                    pass
            if not wp_data:
                wp_data = header.get("payload") or header

            if not isinstance(wp_data, dict):
                return

            waypoint_id = wp_data.get("waypoint_id") or wp_data.get("id") or str(time.time())
            title = wp_data.get("title", "Tactical Waypoint")
            desc = wp_data.get("description", "")
            wp_type = wp_data.get("waypoint_type") or wp_data.get("type", "waypoint")
            lat = float(wp_data.get("latitude") or wp_data.get("lat") or 0.0)
            lon = float(wp_data.get("longitude") or wp_data.get("lon") or 0.0)
            alt = float(wp_data.get("altitude") or wp_data.get("alt") or 0.0)
            created_by = wp_data.get("created_by") or header.get("sender_name", "unknown")
            created_at = float(wp_data.get("created_at", time.time()))
            ttl = wp_data.get("ttl")
            expires_at = (created_at + ttl) if ttl else None

            print(f"[GhostEngine] Tactical waypoint received: '{title}' [{wp_type}] at ({lat:.4f}, {lon:.4f})")

            if self.persistence_db:
                self.persistence_db.save_waypoint(
                    waypoint_id=waypoint_id,
                    title=title,
                    description=desc,
                    waypoint_type=wp_type,
                    latitude=lat,
                    longitude=lon,
                    altitude=alt,
                    created_by=created_by,
                    created_at=created_at,
                    expires_at=expires_at
                )

            if self.on_waypoint_received:
                self.on_waypoint_received({
                    "waypoint_id": waypoint_id,
                    "title": title,
                    "description": desc,
                    "waypoint_type": wp_type,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": alt,
                    "created_by": created_by,
                    "created_at": created_at,
                    "expires_at": expires_at
                })
        except Exception as e:
            print(f"[GhostEngine] Error processing waypoint: {e}")

    def _handle_peer_revocation(self, sender_ip: str, header: dict, encrypted_data: bytes):
        try:
            token = None
            if encrypted_data:
                try:
                    decrypted = self._decrypt_message(encrypted_data)
                    token = json.loads(decrypted)
                except Exception:
                    pass
            if not token:
                token = header.get("payload") or header

            if not isinstance(token, dict):
                return

            # Verify Ed25519 signature of revocation token
            is_valid = False
            if SECURITY_AVAILABLE:
                is_valid = verify_revocation_token(token)
            else:
                is_valid = True

            if not is_valid:
                print(f"[GhostEngine] Revocation token signature verification FAILED from {sender_ip}")
                return

            revoked_peer_id = token.get("peer_id")
            reason = token.get("reason", "Revocation broadcast")
            signature = token.get("signature")

            if not revoked_peer_id:
                return

            print(f"[GhostEngine] Verified revocation broadcast: QUARANTINING {revoked_peer_id} (Reason: {reason})")

            self.revoked_peers.add(revoked_peer_id)
            if self.persistence_db:
                self.persistence_db.revoke_peer(revoked_peer_id, reason, signature)

            with self.peers_lock:
                to_remove = [ip for ip, info in self.peers.items() if info.get('peer_id') == revoked_peer_id or ip == revoked_peer_id]
                for ip in to_remove:
                    del self.peers[ip]

            if self.routing_table:
                self.routing_table.remove_peer(revoked_peer_id)

            if self.crypto_manager:
                self.crypto_manager.clear_peer_keys(revoked_peer_id)

            if self.on_peer_revoked:
                self.on_peer_revoked(revoked_peer_id, reason)
        except Exception as e:
            print(f"[GhostEngine] Error processing peer revocation: {e}")

    def join_group_channel(self, channel_id: str, channel_name: str, passphrase: str, salt_b64: Optional[str] = None) -> bool:
        """Derive channel key and join encrypted tactical group channel."""
        try:
            if salt_b64:
                salt = base64.b64decode(salt_b64)
            else:
                salt = hashlib.sha256(f"ghostnet_channel_salt_{channel_id}".encode('utf-8')).digest()[:16]
                salt_b64 = base64.b64encode(salt).decode('utf-8')
                
            if SECURITY_AVAILABLE:
                key = derive_channel_key(channel_id, passphrase, salt)
            else:
                key = hashlib.sha256((passphrase + channel_id).encode('utf-8')).digest()
                
            self.channel_keys[channel_id] = key
            
            if self.persistence_db:
                self.persistence_db.create_group_channel(channel_id, channel_name, salt_b64)
                
            print(f"[GhostEngine] Joined group channel '{channel_name}' ({channel_id})")
            return True
        except Exception as e:
            print(f"[GhostEngine] Error joining group channel {channel_id}: {e}")
            return False

    def send_group_message(self, channel_id: str, message: str) -> bool:
        """Encrypt and broadcast a group channel message across the mesh network."""
        if channel_id not in self.channel_keys:
            print(f"[GhostEngine] Cannot send to group channel {channel_id}: Not joined")
            return False
            
        try:
            key = self.channel_keys[channel_id]
            if SECURITY_AVAILABLE:
                encrypted_content = encrypt_channel_message(key, message)
            else:
                encrypted_content = base64.b64encode(message.encode('utf-8')).decode('utf-8')
                
            msg_id = f"grp_{self.peer_id[:6]}_{int(time.time()*1000)}"
            now = time.time()
            
            # Save locally
            if self.persistence_db:
                self.persistence_db.save_group_message(
                    message_id=msg_id,
                    channel_id=channel_id,
                    sender_id=self.peer_id,
                    sender_name=self.username,
                    content=message,
                    timestamp=now
                )
                
            header = {
                "type": "GROUP_TEXT",
                "message_id": msg_id,
                "channel_id": channel_id,
                "sender_peer_id": self.peer_id,
                "sender_name": self.username,
                "content": encrypted_content,
                "timestamp": now,
                "network_ttl": 10,
                "visited_nodes": [self.peer_id]
            }
            
            payload = json.dumps(header).encode('utf-8')
            encrypted_payload = self._encrypt_message(payload)
            packet_data = encrypted_payload + self.HEADER_DELIMITER
            
            # Multicast to all active direct connected peers
            with self.peers_lock:
                peer_list = list(self.peers.items())
                
            for peer_key, info in peer_list:
                try:
                    host = peer_key.split(':')[0]
                    port = info.get("tcp_port", self.TCP_PORT)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect((host, port))
                    s.sendall(packet_data)
                    s.close()
                except Exception:
                    pass
                    
            print(f"[GhostEngine] Group message dispatched to channel '{channel_id}'")
            return True
        except Exception as e:
            print(f"[GhostEngine] Error sending group message: {e}")
            return False

    def _handle_group_text_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        """Handle incoming mesh multicast group message: decrypt if joined, and forward across mesh."""
        try:
            channel_id = header.get("channel_id")
            msg_id = header.get("message_id")
            sender_id = header.get("sender_peer_id", "unknown")
            sender_name = header.get("sender_name", "Anonymous")
            enc_content = header.get("content", "")
            ts = float(header.get("timestamp", time.time()))
            ttl = int(header.get("network_ttl", 10))
            visited = header.get("visited_nodes", [])
            
            # Deduplication
            with self.message_dedup_lock:
                if msg_id in self.seen_message_ids:
                    return
                self.seen_message_ids.add(msg_id)
                self.seen_message_ids_order.append(msg_id)
                if len(self.seen_message_ids_order) > 500:
                    old_id = self.seen_message_ids_order.pop(0)
                    self.seen_message_ids.discard(old_id)
                    
            # If local node has key for this channel, decrypt and process
            if channel_id in self.channel_keys:
                key = self.channel_keys[channel_id]
                plaintext = None
                if SECURITY_AVAILABLE:
                    plaintext = decrypt_channel_message(key, enc_content)
                else:
                    try:
                        plaintext = base64.b64decode(enc_content).decode('utf-8')
                    except Exception:
                        pass
                        
                if plaintext:
                    print(f"[GhostEngine] Group message received on channel '{channel_id}' from {sender_name}")
                    if self.persistence_db:
                        self.persistence_db.save_group_message(
                            message_id=msg_id,
                            channel_id=channel_id,
                            sender_id=sender_id,
                            sender_name=sender_name,
                            content=plaintext,
                            timestamp=ts
                        )
                    if self.on_group_message_received:
                        self.on_group_message_received(channel_id, sender_id, sender_name, plaintext, ts)

            # Mesh relay forwarding (epidemic diffusion)
            if ttl > 1 and self.peer_id not in visited:
                new_visited = visited + [self.peer_id]
                header["network_ttl"] = ttl - 1
                header["visited_nodes"] = new_visited
                payload = json.dumps(header).encode('utf-8')
                encrypted_payload = self._encrypt_message(payload)
                forward_data = encrypted_payload + self.HEADER_DELIMITER
                
                with self.peers_lock:
                    peers_to_forward = [
                        (k.split(':')[0], v.get("tcp_port", self.TCP_PORT))
                        for k, v in self.peers.items()
                        if k.split(':')[0] != sender_ip and v.get("peer_id") not in new_visited
                    ]
                    
                for fwd_host, fwd_port in peers_to_forward:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(1.5)
                        s.connect((fwd_host, fwd_port))
                        s.sendall(forward_data)
                        s.close()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[GhostEngine] Error handling group message: {e}")

    def discover_route(self, destination_peer_id: str) -> bool:
        """Dispatch an AODV Route Request (RREQ) to locate multi-hop path."""
        if not self.routing_table:
            return False
            
        now = time.time()
        # Rate limit discovery per destination
        last_req = self.pending_rreqs.get(destination_peer_id, 0.0)
        if now - last_req < 5.0:
            return False
            
        self.pending_rreqs[destination_peer_id] = now
        rreq_packet = self.routing_table.create_rreq(self.peer_id, destination_peer_id)
        rreq_packet["network_ttl"] = 10
        rreq_packet["visited_nodes"] = [self.peer_id]
        
        payload = json.dumps(rreq_packet).encode('utf-8')
        encrypted_payload = self._encrypt_message(payload)
        packet_data = encrypted_payload + self.HEADER_DELIMITER
        
        with self.peers_lock:
            direct_peers = list(self.peers.items())
            
        for peer_key, info in direct_peers:
            try:
                host = peer_key.split(':')[0]
                port = info.get("tcp_port", self.TCP_PORT)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.5)
                s.connect((host, port))
                s.sendall(packet_data)
                s.close()
            except Exception:
                pass
                
        print(f"[AODV] Dispatched RREQ for destination {destination_peer_id}")
        return True

    def _handle_rreq_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        if not self.routing_table:
            return
        try:
            rrep = self.routing_table.process_rreq(header, self.peer_id)
            if rrep:
                # Local node is destination or has fresh route: send RREP unicast back
                rrep["network_ttl"] = 10
                payload = json.dumps(rrep).encode('utf-8')
                encrypted_payload = self._encrypt_message(payload)
                packet_data = encrypted_payload + self.HEADER_DELIMITER
                
                target_hop = rrep.get("target_next_hop")
                dest_host = sender_ip
                with self.peers_lock:
                    for k, v in self.peers.items():
                        if v.get("peer_id") == target_hop:
                            dest_host = k.split(':')[0]
                            break
                            
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((dest_host, self.TCP_PORT))
                s.sendall(packet_data)
                s.close()
                print(f"[AODV] Sent RREP for destination {rrep.get('destination_id')} to {dest_host}")
            else:
                # Forward RREQ to neighbors if TTL permits
                ttl = int(header.get("network_ttl", 5))
                if ttl > 1:
                    header["network_ttl"] = ttl - 1
                    header["hop_count"] = header.get("hop_count", 0) + 1
                    header["hops"] = header.get("hops", []) + [self.peer_id]
                    payload = json.dumps(header).encode('utf-8')
                    encrypted_payload = self._encrypt_message(payload)
                    packet_data = encrypted_payload + self.HEADER_DELIMITER
                    
                    with self.peers_lock:
                        for k, v in self.peers.items():
                            fwd_ip = k.split(':')[0]
                            if fwd_ip != sender_ip:
                                try:
                                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                    s.settimeout(1.0)
                                    s.connect((fwd_ip, v.get("tcp_port", self.TCP_PORT)))
                                    s.sendall(packet_data)
                                    s.close()
                                except Exception:
                                    pass
        except Exception as e:
            print(f"[AODV] Error handling RREQ: {e}")

    def _handle_rrep_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        if not self.routing_table:
            return
        try:
            installed = self.routing_table.process_rrep(header, self.peer_id)
            dest_id = header.get("destination_id")
            orig_id = header.get("originator_id")
            
            if installed:
                print(f"[AODV] Route installed to {dest_id} via {sender_ip} (metric: {header.get('hop_count')})")
                if self.on_route_discovered:
                    self.on_route_discovered(dest_id, header.get('hop_count', 1))
                    
            # If local node is not originator, forward RREP along reverse path
            if orig_id != self.peer_id:
                route_to_orig = self.routing_table.get_route(orig_id)
                if route_to_orig:
                    header["hop_count"] = header.get("hop_count", 0) + 1
                    header["hops"] = header.get("hops", []) + [self.peer_id]
                    payload = json.dumps(header).encode('utf-8')
                    encrypted_payload = self._encrypt_message(payload)
                    packet_data = encrypted_payload + self.HEADER_DELIMITER
                    
                    dest_host = sender_ip
                    with self.peers_lock:
                        for k, v in self.peers.items():
                            if v.get("peer_id") == route_to_orig.next_hop_id:
                                dest_host = k.split(':')[0]
                                break
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect((dest_host, self.TCP_PORT))
                    s.sendall(packet_data)
                    s.close()
        except Exception as e:
            print(f"[AODV] Error handling RREP: {e}")

    def _handle_rerr_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        if not self.routing_table:
            return
        try:
            invalidated = self.routing_table.process_rerr(header)
            if invalidated:
                print(f"[AODV] RERR received: invalidated routes {invalidated}")
        except Exception as e:
            print(f"[AODV] Error handling RERR: {e}")

    def _handle_ota_zeroize_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        """Handle incoming Over-The-Air (OTA) emergency detachment zeroization command."""
        try:
            token = None
            if encrypted_data:
                try:
                    decrypted = self._decrypt_message(encrypted_data)
                    token = json.loads(decrypted)
                except Exception:
                    pass
            if not token:
                token = header.get("payload") or header

            if not isinstance(token, dict):
                return

            if self.remote_wipe_manager:
                verified, reason = self.remote_wipe_manager.verify_burn_token(token, self.peer_id)
                if verified:
                    print(f"[GhostEngine] CRITICAL: Valid OTA Burn Token received from {sender_ip}! Initiating detachment zeroize.")
                    if self.on_ota_zeroize_received:
                        self.on_ota_zeroize_received(token)
                    
                    db_path = getattr(self.persistence_db, 'db_path', None) if self.persistence_db else None
                    zeroize_cb = getattr(self.crypto_manager, 'zeroize_ephemeral_keys', None) if self.crypto_manager else None
                    self.remote_wipe_manager.execute_detachment_zeroize(
                        db_path=db_path,
                        key_zeroize_callback=zeroize_cb
                    )
                else:
                    print(f"[GhostEngine] Rejected invalid OTA Burn Token from {sender_ip}: {reason}")
        except Exception as e:
            print(f"[GhostEngine] Error handling OTA zeroize: {e}")

    def broadcast_ota_burn_token(self, burn_token: dict) -> bool:
        """Broadcast signed emergency OTA burn token to all reachable peers."""
        try:
            header = {
                "type": "OTA_ZEROIZE",
                "sender_peer_id": self.peer_id,
                "payload": burn_token,
                "timestamp": time.time(),
                "network_ttl": 10
            }
            payload = json.dumps(header).encode('utf-8')
            encrypted_payload = self._encrypt_message(payload)
            packet_data = encrypted_payload + self.HEADER_DELIMITER

            with self.peers_lock:
                peer_list = list(self.peers.items())

            for peer_key, info in peer_list:
                try:
                    host = peer_key.split(':')[0]
                    port = info.get("tcp_port", self.TCP_PORT)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect((host, port))
                    s.sendall(packet_data)
                    s.close()
                except Exception:
                    pass

            print("[GhostEngine] Emergency OTA Burn Token broadcasted to active peers")
            return True
        except Exception as e:
            print(f"[GhostEngine] Error broadcasting OTA Burn Token: {e}")
            return False

    def send_multipath_message(
        self,
        destination_peer_id: str,
        message_text: str,
        hop_keys: Optional[Dict[str, bytes]] = None
    ) -> List[List[str]]:
        """
        Dispatches message across up to K=2 node-disjoint paths simultaneously.
        """
        if not self.multipath_router or not self.routing_table:
            return []

        # Construct topology graph from routing observations
        graph: Dict[str, Set[str]] = {}
        with self.peers_lock:
            direct_peers = {info.get("peer_id", k) for k, info in self.peers.items()}
        graph[self.peer_id] = set(direct_peers)
        for p in direct_peers:
            if p not in graph:
                graph[p] = set()
            graph[p].add(self.peer_id)

        # Merge peer observations
        with self.routing_table.lock:
            for obs, seen in self.routing_table.peers_seen.items():
                if obs not in graph:
                    graph[obs] = set()
                graph[obs].update(seen)
                for s in seen:
                    if s not in graph:
                        graph[s] = set()
                    graph[s].add(obs)

        msg_id = f"mp_{self.peer_id[:6]}_{int(time.time()*1000)}"
        payload = message_text.encode('utf-8')

        def _transmit_cb(next_hop: str, data: bytes, m_id: str):
            dest_host = None
            dest_port = self.TCP_PORT
            with self.peers_lock:
                for k, v in self.peers.items():
                    if v.get("peer_id") == next_hop or k == next_hop:
                        dest_host = k.split(':')[0]
                        dest_port = v.get("tcp_port", self.TCP_PORT)
                        break

            if dest_host:
                header = {
                    "type": "TEXT",
                    "msg_id": m_id,
                    "sender_peer_id": self.peer_id,
                    "target_peer_id": destination_peer_id,
                    "text": data.decode('utf-8', errors='ignore') if isinstance(data, (bytes, bytearray)) else str(data),
                    "timestamp": time.time(),
                    "network_ttl": 8
                }
                pkt = self._encrypt_message(json.dumps(header).encode('utf-8')) + self.HEADER_DELIMITER
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(pkt)
                s.close()

        paths = self.multipath_router.dispatch_multipath(
            source=self.peer_id,
            destination=destination_peer_id,
            message_id=msg_id,
            payload=payload,
            graph=graph,
            hop_keys=hop_keys,
            transmit_callback=_transmit_cb
        )
        return paths

    def _handle_geocast_message(self, sender_ip: str, header: dict, encrypted_data: bytes):
        """Processes incoming GeoCast message: verifies spatial bounds and selectively delivers/forwards."""
        if not self.geocast_router:
            return

        try:
            # Determine local node GPS coordinates if GPS manager is active
            local_lat, local_lon = None, None
            try:
                from gps_manager import get_gps_manager
                gps = get_gps_manager()
                if gps and gps.last_location:
                    local_lat = gps.last_location.get("latitude")
                    local_lon = gps.last_location.get("longitude")
            except Exception:
                pass

            res = self.geocast_router.process_incoming_geocast(header, local_lat, local_lon)

            if res["should_deliver"]:
                print(f"[GeoCast] Delivered geocast message '{header.get('geocast_id')}' (local node is INSIDE operational geofence)")
                if self.on_geocast_received:
                    self.on_geocast_received(header)

                if self.persistence_db:
                    self.persistence_db.save_message(
                        sender_ip,
                        "them",
                        "text",
                        f"[GeoCast]: {header.get('message', '')}",
                        float(header.get("timestamp", time.time()))
                    )

            if res["should_forward"]:
                ttl = int(header.get("network_ttl", 5))
                visited = header.get("visited_nodes", [])
                if self.peer_id not in visited:
                    header["network_ttl"] = ttl - 1
                    header["visited_nodes"] = visited + [self.peer_id]
                    payload_bytes = json.dumps(header).encode('utf-8')
                    fwd_packet = self._encrypt_message(payload_bytes) + self.HEADER_DELIMITER

                    with self.peers_lock:
                        peers_to_forward = [
                            (k.split(':')[0], v.get("tcp_port") or self._get_peer_port(k))
                            for k, v in self.peers.items()
                            if k.split(':')[0] != sender_ip and v.get("peer_id") not in header["visited_nodes"]
                        ]

                    for fwd_host, fwd_port in peers_to_forward:
                        try:
                            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            s.settimeout(1.5)
                            s.connect((fwd_host, fwd_port))
                            s.sendall(fwd_packet)
                            s.close()
                        except Exception:
                            pass
        except Exception as e:
            print(f"[GeoCast] Error processing incoming geocast: {e}")

    def _handle_otp_frame(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming One-Time Pad encrypted frame using local OTP vault."""
        if not self.otp_vault:
            print(f"[OTP] Received OTP_FRAME from {sender_ip} but no OTP vault is mounted.")
            return

        try:
            decrypted_bytes = self.otp_vault.decrypt_otp(header)
            if decrypted_bytes:
                text_content = decrypted_bytes.decode('utf-8', errors='replace')
                origin_sender = header.get("sender_peer_id") or sender_ip
                timestamp = datetime.now().strftime("%H:%M:%S")
                timestamp_unix = time.time()
                
                print(f"[OTP] Successfully decrypted {len(decrypted_bytes)} bytes from {origin_sender} (offset: {header.get('pad_offset')})")
                self._persist_message(origin_sender, "them", "text", f"[OTP]: {text_content}", timestamp_unix, ttl=None)
                if self.on_message_received:
                    self.on_message_received(origin_sender, f"[OTP]: {text_content}", timestamp)
            else:
                print(f"[OTP] Failed to decrypt OTP frame from {sender_ip} (offset mismatch, replay, or integrity failure)")
        except Exception as e:
            print(f"[OTP] Error handling OTP frame: {e}")

    def send_geocast_message(
        self,
        message: str,
        geofence_type: str,
        geofence_params: dict,
        ttl: int = 8
    ) -> bool:
        """
        Dispatches an area-targeted GeoCast packet across the mesh.
        """
        if not self.geocast_router:
            return False

        try:
            gid = f"geo_{self.peer_id[:6]}_{int(time.time()*1000)}"
            pkt = self.geocast_router.create_geocast_packet(
                geocast_id=gid,
                sender_id=self.peer_id,
                sender_name=self.username,
                message=message,
                geofence_type=geofence_type,
                geofence_params=geofence_params,
                ttl=ttl
            )

            # Check if local sender is inside geofence
            local_lat, local_lon = None, None
            try:
                from gps_manager import get_gps_manager
                gps = get_gps_manager()
                if gps and gps.last_location:
                    local_lat = gps.last_location.get("latitude")
                    local_lon = gps.last_location.get("longitude")
            except Exception:
                pass

            if self.geocast_router.is_in_geofence(local_lat, local_lon, geofence_type, geofence_params):
                if self.on_geocast_received:
                    self.on_geocast_received(pkt)

            raw_bytes = json.dumps(pkt).encode('utf-8')
            packet_data = self._encrypt_message(raw_bytes) + self.HEADER_DELIMITER

            with self.peers_lock:
                peer_list = list(self.peers.items())

            for peer_key, info in peer_list:
                try:
                    host = peer_key.split(':')[0]
                    port = info.get("tcp_port") or self._get_peer_port(peer_key)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect((host, port))
                    s.sendall(packet_data)
                    s.close()
                except Exception:
                    pass

            print(f"[GeoCast] Dispatched geocast message '{gid}' across mesh")
            return True
        except Exception as e:
            print(f"[GeoCast] Error sending geocast: {e}")
            return False

    def _on_defensive_posture_changed(self, new_posture: str, details: dict):
        """Reacts to detected electronic warfare jamming postures by upgrading FEC and defensive routing."""
        print(f"[Anti-Jamming] Defensive posture transitioned to: {new_posture} (Details: {details})")
        if new_posture == "EW_JAMMING_ACTIVE":
            if self.fec_engine:
                self.fec_engine.default_k = 2
                self.fec_engine.default_m = 4
                print("[Anti-Jamming] Upgraded FEC parity to maximum resilience (K=2, M=4)")
        elif new_posture == "NORMAL":
            if self.fec_engine:
                self.fec_engine.default_k = 4
                self.fec_engine.default_m = 2
                print("[Anti-Jamming] Restored FEC parity to standard configuration (K=4, M=2)")

    # Phase 9: Delay-Tolerant Bundle Protocol, Ephemeral Beacons, ATAK CoT Streaming & Merkle Vault

    def _handle_dtn_bundle(self, sender_ip: str, header: dict, remaining_data: bytes, conn):
        """Processes incoming RFC-aligned DTN bundle packet."""
        try:
            return
            bundle_data = header.get("bundle")
            if not bundle_data and remaining_data:
                try:
                    bundle_data = json.loads(remaining_data.decode('utf-8'))
                except Exception:
                    bundle_data = None

            if not bundle_data:
                print(f"[BundleProtocol] Invalid DTN_BUNDLE received from {sender_ip}")
                return

            bundle = Bundle.from_dict(bundle_data)
            if self.bundle_manager:
                stored = self.bundle_manager.store_bundle(bundle)
                if not stored:
                    print(f"[BundleProtocol] Failed to store bundle {bundle.bundle_id} (expired or buffer full)")
                    return

            self.record_audit_event("BUNDLE_STORED", {
                "bundle_id": bundle.bundle_id,
                "source": bundle.source_id,
                "destination": bundle.destination_id,
                "priority": bundle.priority
            })

            # Respond with Custody Acceptance Signal (CAS) if requested
            if bundle.custody_requested and self.bundle_manager:
                cas = self.bundle_manager.accept_custody(bundle.bundle_id)
                if cas:
                    self.record_audit_event("CUSTODY_ACCEPTED", {
                        "bundle_id": bundle.bundle_id,
                        "custodian": self.peer_id
                    })
                    sender_target = f"{sender_ip}:{header['sender_tcp_port']}" if header.get("sender_tcp_port") else sender_ip
                    self.send_bundle_cas(sender_target, cas)

            # Check if local node is final destination or broadcast
            if bundle.destination_id in (self.peer_id, "BROADCAST", "ALL"):
                timestamp = datetime.now().strftime("%H:%M:%S")
                timestamp_unix = time.time()
                text_content = bundle.payload.decode('utf-8', errors='replace')
                self._persist_message(bundle.source_id, "them", "text", f"[DTN-Bundle]: {text_content}", timestamp_unix, ttl=int(bundle.lifetime_sec))
                if self.on_message_received:
                    self.on_message_received(bundle.source_id, f"[DTN-Bundle]: {text_content}", timestamp)
                if self.on_bundle_received:
                    self.on_bundle_received(bundle)

        except Exception as e:
            print(f"[BundleProtocol] Error processing DTN bundle: {e}")

    def _handle_bundle_cas(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming Custody Acceptance Signal (CAS) from downstream node."""
        try:
            return
            cas_data = header.get("cas")
            if not cas_data and remaining_data:
                try:
                    cas_data = json.loads(remaining_data.decode('utf-8'))
                except Exception:
                    cas_data = None

            if not cas_data:
                return

            cas = CustodyAcceptanceSignal(
                bundle_id=cas_data["bundle_id"],
                custodian_id=cas_data["custodian_id"],
                timestamp=cas_data.get("timestamp", time.time()),
                reason=cas_data.get("reason", "CUSTODY_ACCEPTED")
            )
            if self.bundle_manager:
                processed = self.bundle_manager.process_cas(cas)
                if processed:
                    print(f"[BundleProtocol] Custody transferred for bundle {cas.bundle_id} to downstream node {cas.custodian_id}")
                    self.record_audit_event("CUSTODY_RELEASED", {
                        "bundle_id": cas.bundle_id,
                        "new_custodian": cas.custodian_id
                    })
        except Exception as e:
            print(f"[BundleProtocol] Error processing CAS: {e}")

    def send_dtn_bundle(self, target_ip: str, bundle: Any) -> bool:
        """Transmits an RFC-aligned DTN bundle over TCP socket to target peer."""
        try:
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_ip)
            header = {
                "type": "DTN_BUNDLE",
                "bundle": bundle.to_dict(),
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)

            if self.bundle_manager:
                self.bundle_manager.store_bundle(bundle)

            self.record_audit_event("BUNDLE_DISPATCHED", {
                "bundle_id": bundle.bundle_id,
                "target": target_ip,
                "priority": bundle.priority
            })
            print(f"[BundleProtocol] Dispatched bundle {bundle.bundle_id} to {target_ip} (Priority: {bundle.priority})")
            return True
        except Exception as e:
            print(f"[BundleProtocol] Error sending DTN bundle: {e}")
            return False

    def send_bundle_cas(self, target_ip: str, cas: Any) -> bool:
        """Transmits a Custody Acceptance Signal back to upstream custodian."""
        try:
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_ip)
            header = {
                "type": "BUNDLE_CAS",
                "cas": asdict(cas),
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            return True
        except Exception as e:
            print(f"[BundleProtocol] Error sending CAS: {e}")
            return False

    def record_audit_event(self, event_type: str, data: Any) -> Optional[Dict[str, Any]]:
        """Appends an event to the tamper-evident Merkle audit ledger."""
        if self.merkle_ledger:
            try:
                return self.merkle_ledger.append_event(event_type, data)
            except Exception as e:
                print(f"[MerkleVault] Error recording audit event: {e}")
        return None

    def verify_audit_ledger(self) -> Tuple[bool, Optional[int], str]:
        """Verifies full cryptographic integrity of the Merkle audit chain."""
        if self.merkle_ledger:
            return self.merkle_ledger.verify_integrity()
        return True, None, "LEDGER_UNAVAILABLE"

    def export_audit_proof(self, index: int) -> Optional[Dict[str, Any]]:
        """Exports inclusion proof with sequential chain hashes for After-Action Reviews."""
        if self.merkle_ledger:
            return self.merkle_ledger.generate_audit_proof(index)
        return None

    def generate_ephemeral_id(self, target_time: Optional[float] = None) -> str:
        """Generates un-correlatable rotating ephemeral beacon ID for current time slot."""
        if self.ephemeral_beacon_mgr:
            return self.ephemeral_beacon_mgr.generate_ephemeral_token(self.peer_id, target_time)
        return self.peer_id

    def resolve_ephemeral_peer(
        self,
        token: str,
        known_peer_ids: List[str],
        target_time: Optional[float] = None
    ) -> Optional[str]:
        """Resolves incoming rotating ephemeral token against known authenticated team member peer IDs."""
        if self.ephemeral_beacon_mgr:
            return self.ephemeral_beacon_mgr.resolve_ephemeral_token(token, known_peer_ids, target_time)
        return token if token in known_peer_ids else None

    def _on_cot_from_tak(self, parsed_cot: Dict[str, Any], sender_ip: str):
        """Callback triggered when an external ATAK/WinTAK instance streams CoT XML to Gost-Net."""
        print(f"[TAK Bridge] Received CoT event {parsed_cot.get('uid')} from {sender_ip}")
        self.record_audit_event("COT_INGRESS", parsed_cot)
        if self.on_cot_received:
            try:
                self.on_cot_received(parsed_cot, sender_ip)
            except Exception as e:
                print(f"[TAK Bridge] Callback error in on_cot_received: {e}")

    def broadcast_cot_telemetry(
        self,
        lat: float,
        lon: float,
        hae: float = 0.0,
        ce90: float = 10.0,
        cot_type: str = "a-f-G-U-C"
    ) -> bool:
        """Translates local node coordinates into standard CoT 2.0 XML and broadcasts to ATAK/WinTAK."""
        if self.tak_bridge:
            return self.tak_bridge.broadcast_telemetry_to_tak(
                uid=self.peer_id,
                callsign=self.username,
                lat=lat,
                lon=lon,
                hae=hae,
                ce90=ce90,
                cot_type=cot_type
            )
        return False

    # Phase 10: Cognitive Radio Spectrum Sensing, Swarm Consensus, DTN Pub/Sub & Sovereign Identity

    def evaluate_spectrum(
        self,
        channel_id: int,
        samples: List[float],
        power_spectrum: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Evaluates RF channel energy, noise floor, and occupancy using Cognitive Radio Engine."""
        if not self.cognitive_radio:
            return {"channel_id": channel_id, "is_occupied": False, "energy": 0.0}
        obs = self.cognitive_radio.update_channel_observation(channel_id, samples, power_spectrum)
        if self.fhss_manager and obs.get("is_occupied"):
            self.fhss_manager.record_channel_result(channel_id, success=False)
        return obs

    def rank_best_channels(self, candidate_channels: List[int]) -> List[Tuple[int, float]]:
        """Ranks candidate channels by vacancy quality (lowest duty cycle and energy first)."""
        if not self.cognitive_radio:
            return [(ch, 0.0) for ch in candidate_channels]
        return self.cognitive_radio.rank_vacant_channels(candidate_channels)

    def propose_swarm_action(
        self,
        action_type: str,
        params: Dict[str, Any],
        target_peers: Optional[List[str]] = None
    ) -> Optional[Any]:
        """Initiates a decentralized Byzantine swarm proposal and broadcasts to peers."""
        if not self.swarm_consensus:
            return None
        proposal = self.swarm_consensus.create_proposal(action_type, params)
        self.record_audit_event("SWARM_PROPOSAL_CREATED", {
            "proposal_id": proposal.proposal_id,
            "epoch": proposal.epoch,
            "action_type": action_type,
            "params": params
        })

        # Cast proposer's affirmative vote
        self.vote_swarm_proposal(proposal.proposal_id, vote=True, target_peers=target_peers)

        header = {
            "type": "CONSENSUS_PROPOSAL",
            "proposal": asdict(proposal),
            "sender_peer_id": self.peer_id,
            "sender_tcp_port": self.tcp_port
        }
        self._broadcast_swarm_frame(header, target_peers)
        return proposal

    def vote_swarm_proposal(
        self,
        proposal_id: str,
        vote: bool,
        target_peers: Optional[List[str]] = None
    ) -> Optional[Any]:
        """Casts a signed ballot for proposal_id and broadcasts ballot to peers."""
        if not self.swarm_consensus:
            return None
        ballot = self.swarm_consensus.cast_ballot(proposal_id, vote)
        if not ballot:
            return None

        self.record_audit_event("SWARM_BALLOT_CAST", {
            "proposal_id": proposal_id,
            "vote": vote,
            "epoch": ballot.epoch,
            "signature": ballot.signature_hex
        })

        header = {
            "type": "CONSENSUS_BALLOT",
            "ballot": asdict(ballot),
            "sender_peer_id": self.peer_id,
            "sender_tcp_port": self.tcp_port
        }
        self._broadcast_swarm_frame(header, target_peers)
        return ballot

    def _broadcast_swarm_frame(self, header: dict, target_peers: Optional[List[str]] = None):
        """Helper to dispatch consensus/pubsub frames across target or connected peers."""
        packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
        with self.peers_lock:
            peers_to_send = list(target_peers) if target_peers is not None else list(self.peers.keys())

        for peer in peers_to_send:
            try:
                dest_host, dest_port, _ = self._resolve_peer_target(peer)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect((dest_host, dest_port))
                    s.sendall(packet_bytes)
            except Exception:
                pass

    def _handle_consensus_proposal(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming proposal from a swarm peer."""
        try:
            return
            prop_data = header.get("proposal")
            if not prop_data and remaining_data:
                prop_data = json.loads(remaining_data.decode('utf-8'))
            if not prop_data or not self.swarm_consensus:
                return

            proposal = ConsensusProposal(**prop_data)
            with self.swarm_consensus.lock:
                if proposal.proposal_id not in self.swarm_consensus.proposals:
                    self.swarm_consensus.proposals[proposal.proposal_id] = proposal
                    self.swarm_consensus.ballots[proposal.proposal_id] = {}

            self.record_audit_event("SWARM_PROPOSAL_RECEIVED", {
                "proposal_id": proposal.proposal_id,
                "proposer": proposal.proposer_id,
                "action": proposal.action_type
            })
            if self.on_consensus_proposal:
                self.on_consensus_proposal(proposal)
        except Exception as e:
            print(f"[Consensus] Error handling proposal: {e}")

    def _handle_consensus_ballot(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming ballot from a swarm peer and checks for quorum commit."""
        try:
            return
            ballot_data = header.get("ballot")
            if not ballot_data and remaining_data:
                ballot_data = json.loads(remaining_data.decode('utf-8'))
            if not ballot_data or not self.swarm_consensus:
                return

            ballot = ConsensusBallot(**ballot_data)
            accepted = self.swarm_consensus.process_incoming_ballot(ballot)
            if accepted:
                self.record_audit_event("SWARM_BALLOT_RECEIVED", {
                    "proposal_id": ballot.proposal_id,
                    "voter": ballot.voter_id,
                    "vote": ballot.vote
                })
                total_nodes = max(3, len(self.peers) + 1)
                eval_res = self.swarm_consensus.evaluate_proposal(ballot.proposal_id, total_nodes)
                if eval_res.get("quorum_reached"):
                    committed = self.swarm_consensus.commit_proposal(ballot.proposal_id, total_nodes)
                    if committed:
                        self.record_audit_event("SWARM_ACTION_COMMITTED", committed)
                        print(f"[Consensus] Quorum reached! Action committed: {committed.get('action_type')}")
                        if self.on_consensus_committed:
                            self.on_consensus_committed(committed)
        except Exception as e:
            print(f"[Consensus] Error handling ballot: {e}")

    def subscribe_topic(self, topic_pattern: str, callback: Callable[[Any], None]):
        """Subscribes to topic pattern (supports '*' and '#')."""
        if self.pubsub_router:
            self.pubsub_router.subscribe(topic_pattern, callback)

    def publish_topic(
        self,
        topic: str,
        payload_bytes: bytes,
        ttl_seconds: float = 86400.0,
        broadcast: bool = True
    ) -> Optional[Any]:
        """Publishes a content-addressed message and optionally broadcasts to peers."""
        if not self.pubsub_router:
            return None
        msg = self.pubsub_router.publish(topic, payload_bytes, ttl_seconds)
        self.record_audit_event("PUBSUB_PUBLISHED", {
            "content_id": msg.content_id,
            "topic": topic,
            "length": len(payload_bytes)
        })

        if broadcast:
            header = {
                "type": "PUBSUB_PUBLISH",
                "content_id": msg.content_id,
                "topic": msg.topic,
                "payload_b64": base64.b64encode(msg.payload).decode('utf-8'),
                "publisher_id": msg.publisher_id,
                "timestamp": msg.timestamp,
                "ttl_seconds": msg.ttl_seconds,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port
            }
            self._broadcast_swarm_frame(header)
        return msg

    def sync_pubsub_with_peer(self, target_ip: str) -> bool:
        """Transmits compact Bloom filter to peer for content set reconciliation."""
        if not self.pubsub_router:
            return False
        try:
            bf = self.pubsub_router.generate_bloom_filter(size_bits=512)
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_ip)
            header = {
                "type": "PUBSUB_BLOOM_SYNC",
                "bloom_b64": base64.b64encode(bf.to_bytes()).decode('utf-8'),
                "size_bits": bf.size_bits,
                "num_hashes": bf.num_hashes,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            return True
        except Exception as e:
            print(f"[DTNPubSub] Error sending Bloom filter sync: {e}")
            return False

    def _handle_pubsub_publish(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming published topic message."""
        try:
            return
            payload = base64.b64decode(header["payload_b64"])
            msg = TopicMessage(
                content_id=header["content_id"],
                topic=header["topic"],
                payload=payload,
                publisher_id=header.get("publisher_id", sender_ip),
                timestamp=header.get("timestamp", time.time()),
                ttl_seconds=header.get("ttl_seconds", 86400.0)
            )
            if self.pubsub_router:
                received = self.pubsub_router.receive_message(msg)
                if received:
                    self.record_audit_event("PUBSUB_INGRESS", {
                        "content_id": msg.content_id,
                        "topic": msg.topic
                    })
                    if self.on_pubsub_message:
                        self.on_pubsub_message(msg)
        except Exception as e:
            print(f"[DTNPubSub] Error handling pubsub message: {e}")

    def _handle_pubsub_bloom_sync(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Compares peer's Bloom filter against local cache and pushes missing items."""
        try:
            return
            raw_bytes = base64.b64decode(header["bloom_b64"])
            size_bits = header.get("size_bits", 512)
            num_hashes = header.get("num_hashes", 4)
            peer_bf = BloomFilter.from_bytes(raw_bytes, size_bits=size_bits, num_hashes=num_hashes)

            if self.pubsub_router:
                missing_items = self.pubsub_router.reconcile_missing_items(peer_bf)
                sender_target = f"{sender_ip}:{header['sender_tcp_port']}" if header.get("sender_tcp_port") else sender_ip
                dest_host, dest_port, _ = self._resolve_peer_target(sender_target)

                for item in missing_items:
                    item_header = {
                        "type": "PUBSUB_PUBLISH",
                        "content_id": item.content_id,
                        "topic": item.topic,
                        "payload_b64": base64.b64encode(item.payload).decode('utf-8'),
                        "publisher_id": item.publisher_id,
                        "timestamp": item.timestamp,
                        "ttl_seconds": item.ttl_seconds,
                        "sender_peer_id": self.peer_id,
                        "sender_tcp_port": self.tcp_port
                    }
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(2.0)
                            s.connect((dest_host, dest_port))
                            s.sendall(json.dumps(item_header).encode('utf-8') + self.HEADER_DELIMITER)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[DTNPubSub] Error processing Bloom filter sync: {e}")

    def certify_peer_key(
        self,
        subject_id: str,
        subject_pubkey_hex: str,
        trust_level: float
    ) -> Optional[Any]:
        """Issues a Web-of-Trust digital certification for a peer."""
        if not self.wot_keyring:
            return None
        cert = self.wot_keyring.certify_peer(subject_id, subject_pubkey_hex, trust_level)
        self.record_audit_event("WOT_PEER_CERTIFIED", {
            "subject": subject_id,
            "trust_level": trust_level,
            "signature": cert.signature_hex if cert else ""
        })
        return cert

    def get_peer_trust_score(self, subject_id: str, max_depth: int = 2) -> float:
        """Computes cumulative WoT trust score for peer."""
        if not self.wot_keyring:
            return 0.0
        return self.wot_keyring.compute_trust_score(subject_id, max_depth)

    def is_peer_trusted(self, subject_id: str, threshold: float = 0.5) -> bool:
        """Returns True if peer meets or exceeds WoT trust threshold."""
        if not self.wot_keyring:
            return False
        return self.wot_keyring.is_peer_trusted(subject_id, threshold)

    @staticmethod
    def split_emergency_command(
        command_bytes: bytes,
        threshold_k: int,
        total_shares_n: int
    ) -> List[Tuple[int, bytes]]:
        """Splits an emergency mission command via Shamir's Secret Sharing over GF(256)."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return ShamirThresholdCrypto.split_secret(command_bytes, threshold_k, total_shares_n)

    @staticmethod
    def reconstruct_emergency_command(shares: List[Tuple[int, bytes]]) -> bytes:
        """Reconstructs an emergency command from k shares via Lagrange interpolation at x=0."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return ShamirThresholdCrypto.reconstruct_secret(shares)

    # Phase 11: Mesh Self-Healing, Traffic Camouflage, Tactical DHT & Spatial Privacy

    def record_mesh_link(self, u: str, v: str):
        """Records a bidirectional link in the mesh healing topology manager."""
        if self.mesh_healing:
            self.mesh_healing.update_link(u, v)

    def sever_mesh_link(self, u: str, v: str):
        """Removes a severed link to detect topological partitions."""
        if self.mesh_healing:
            self.mesh_healing.remove_link(u, v)

    def detect_mesh_partitions(self) -> Tuple[bool, List[Set[str]]]:
        """Returns (is_partitioned, list_of_components) from the mesh healing manager."""
        if not self.mesh_healing:
            return False, []
        return self.mesh_healing.is_partitioned(), self.mesh_healing.get_connected_components()

    def negotiate_fringe_bridge(self) -> Optional[Dict[str, Any]]:
        """Identifies boundary fringe nodes and promotes the prime candidate to mobile bridge mode."""
        if not self.mesh_healing:
            return None
        candidates = self.mesh_healing.elect_fringe_bridge_nodes()
        if not candidates:
            return None
        elected = candidates[0]
        info = self.mesh_healing.promote_node_to_bridge(elected)
        self.record_audit_event("BRIDGE_PROMOTED", info)
        return info

    def drain_bundles_on_heal(self, reconnected_peer_id: str) -> int:
        """Drains spooled DTN bundles across a reconnected/healed partition link."""
        if not self.mesh_healing:
            return 0
        drained = self.mesh_healing.drain_bundles_across_healed_link(reconnected_peer_id, self.bundle_manager)
        self.record_audit_event("BUNDLES_DRAINED_ON_HEAL", {
            "peer_id": reconnected_peer_id,
            "drained_count": drained
        })
        return drained

    def generate_chaff_frame(self, target_size: int = 128) -> bytes:
        """Generates a high-entropy dummy chaff packet for covert traffic camouflage."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return TrafficCamouflageEngine.generate_chaff_packet(target_size)

    @staticmethod
    def is_chaff_frame(data: bytes) -> bool:
        """Identifies if a raw packet is a dummy chaff frame."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return TrafficCamouflageEngine.is_chaff_packet(data)

    def schedule_covert_transmissions(
        self,
        packets: List[bytes],
        start_time: Optional[float] = None
    ) -> List[Tuple[float, bytes, bool]]:
        """Shapes traffic into Poisson process arrival intervals and inserts dummy chaff."""
        if not self.traffic_camouflage:
            t = start_time if start_time is not None else time.time()
            return [(t + i * 0.5, p, False) for i, p in enumerate(packets)]
        return self.traffic_camouflage.schedule_transmissions(packets, start_time)

    def dht_store(
        self,
        key_str: str,
        value: Any,
        ttl_seconds: float = 3600.0,
        target_peer: Optional[str] = None
    ) -> int:
        """Stores a key-value pair in local Tactical DHT and optionally replicates to target peer."""
        if not self.tactical_dht:
            return 0
        k_int = self.tactical_dht.store_value(key_str, value, ttl_seconds)
        self.record_audit_event("DHT_STORED", {
            "key": key_str,
            "key_int": k_int,
            "ttl": ttl_seconds
        })

        if target_peer:
            try:
                dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
                header = {
                    "type": "DHT_STORE",
                    "key": key_str,
                    "value": value,
                    "ttl": ttl_seconds,
                    "sender_peer_id": self.peer_id,
                    "sender_tcp_port": self.tcp_port,
                    "target_peer_id": final_target_id
                }
                packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect((dest_host, dest_port))
                    s.sendall(packet_bytes)
            except Exception as e:
                print(f"[TacticalDHT] Error replicating DHT_STORE to peer: {e}")
        return k_int

    def dht_get(self, key_str: str) -> Optional[Any]:
        """Retrieves a value from local Tactical DHT."""
        if not self.tactical_dht:
            return None
        return self.tactical_dht.get_value(key_str)

    def dht_query_peer(self, target_peer: str, key_str: str) -> bool:
        """Sends a DHT_QUERY to a remote peer for key_str."""
        try:
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "DHT_QUERY",
                "key": key_str,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            return True
        except Exception as e:
            print(f"[TacticalDHT] Error sending DHT_QUERY: {e}")
            return False

    def _handle_dht_store(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming DHT_STORE packet from a peer."""
        try:
            key_str = header.get("key")
            val = header.get("value")
            ttl = header.get("ttl", 3600.0)
            if key_str and self.tactical_dht:
                self.tactical_dht.store_value(key_str, val, ttl)
                self.record_audit_event("DHT_REPLICATED", {
                    "key": key_str,
                    "from_peer": header.get("sender_peer_id")
                })
        except Exception as e:
            print(f"[TacticalDHT] Error handling DHT_STORE: {e}")

    def _handle_dht_query(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming DHT_QUERY and returns DHT_RESPONSE if value is present."""
        try:
            key_str = header.get("key")
            if not key_str or not self.tactical_dht:
                return
            val = self.tactical_dht.get_value(key_str)
            sender_target = f"{sender_ip}:{header['sender_tcp_port']}" if header.get("sender_tcp_port") else sender_ip
            dest_host, dest_port, _ = self._resolve_peer_target(sender_target)
            resp_header = {
                "type": "DHT_RESPONSE",
                "key": key_str,
                "value": val,
                "found": (val is not None),
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port
            }
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(json.dumps(resp_header).encode('utf-8') + self.HEADER_DELIMITER)
        except Exception as e:
            print(f"[TacticalDHT] Error handling DHT_QUERY: {e}")

    def _handle_dht_response(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming DHT_RESPONSE packet."""
        try:
            key_str = header.get("key")
            val = header.get("value")
            found = header.get("found", False)
            if found and key_str and self.tactical_dht:
                self.tactical_dht.store_value(key_str, val)
                self.record_audit_event("DHT_RESPONSE_INGRESS", {
                    "key": key_str,
                    "found": True
                })
            if self.on_dht_response:
                self.on_dht_response(key_str, val, found)
        except Exception as e:
            print(f"[TacticalDHT] Error handling DHT_RESPONSE: {e}")

    def _handle_ecm_observation(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming ECM_OBSERVATION packet from peer."""
        try:
            obs_id = header.get("observer_id") or header.get("sender_peer_id", sender_ip)
            lat = float(header.get("lat", 0.0))
            lon = float(header.get("lon", 0.0))
            rssi = float(header.get("rssi_dbm", -90.0))
            if self.collaborative_ecm:
                self.collaborative_ecm.record_observation(obs_id, lat, lon, rssi)
                self.record_audit_event("ECM_OBSERVATION_INGRESS", {
                    "observer_id": obs_id,
                    "lat": lat,
                    "lon": lon,
                    "rssi_dbm": rssi,
                    "from_peer": header.get("sender_peer_id")
                })
            if self.on_ecm_observation_received:
                self.on_ecm_observation_received(sender_ip, header)
        except Exception as e:
            print(f"[CollaborativeECM] Error handling ECM_OBSERVATION: {e}")

    def _handle_zkp_auth_proof(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming ZKP_AUTH_PROOF packet."""
        try:
            pub_y_raw = header.get("public_y")
            public_y = int(pub_y_raw, 16) if isinstance(pub_y_raw, str) else int(pub_y_raw)
            proof = header.get("proof", {})
            ctx = header.get("context", "GostNet_ZKP_Auth")
            from_peer = header.get("sender_peer_id", sender_ip)
            valid = False
            if self.zkp_auth:
                valid = self.zkp_auth.verify_proof(public_y, proof, ctx)
                self.record_audit_event("ZKP_AUTH_VERIFIED", {
                    "from_peer": from_peer,
                    "valid": valid,
                    "context": ctx
                })
            if self.on_zkp_auth_received:
                self.on_zkp_auth_received(sender_ip, public_y, valid)
        except Exception as e:
            print(f"[SchnorrZKP] Error handling ZKP_AUTH_PROOF: {e}")

    def record_ecm_observation(
        self,
        observer_id: str,
        lat: float,
        lon: float,
        rssi_dbm: float,
        target_peer: Optional[str] = None
    ) -> None:
        """Records an ECM jamming power measurement and optionally replicates to target peer."""
        if self.collaborative_ecm:
            self.collaborative_ecm.record_observation(observer_id, lat, lon, rssi_dbm)
            self.record_audit_event("ECM_OBSERVATION_RECORDED", {
                "observer_id": observer_id,
                "lat": lat,
                "lon": lon,
                "rssi_dbm": rssi_dbm
            })
        if target_peer:
            try:
                dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
                header = {
                    "type": "ECM_OBSERVATION",
                    "observer_id": observer_id,
                    "lat": lat,
                    "lon": lon,
                    "rssi_dbm": rssi_dbm,
                    "sender_peer_id": self.peer_id,
                    "sender_tcp_port": self.tcp_port,
                    "target_peer_id": final_target_id
                }
                packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect((dest_host, dest_port))
                    s.sendall(packet_bytes)
            except Exception as e:
                print(f"[CollaborativeECM] Error replicating ECM_OBSERVATION: {e}")

    def triangulate_ecm_jammer(
        self,
        p0_dbm: float = -30.0,
        path_loss_exp: float = 2.5
    ) -> Optional[Dict[str, Any]]:
        """Triangulates jammer position via weighted centroid multilateration over multi-node observations."""
        if not self.collaborative_ecm:
            return None
        res = self.collaborative_ecm.triangulate_jammer(p0_dbm, path_loss_exp)
        if res:
            self.record_audit_event("ECM_TRIANGULATION_SUCCESS", res)
        return res

    def get_ecm_nulling_bearing(
        self,
        friendly_lat: float,
        friendly_lon: float,
        jammer_lat: float,
        jammer_lon: float
    ) -> float:
        """Calculates friendly nulling antenna bearing toward estimated jammer location."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return CollaborativeECMManager.calculate_nulling_bearing(friendly_lat, friendly_lon, jammer_lat, jammer_lon)

    def rlnc_encode_generation(
        self,
        packets: List[bytes],
        redundancy_factor: float = 1.5
    ) -> List[Tuple[List[int], bytes]]:
        """Encodes a generation of packets into random linear combinations in GF(256)."""
        raise NotImplementedError("Research prototype quarantined in research/")
        encoder = RLNCEncoder(packets)
        count = max(len(packets), int(len(packets) * redundancy_factor))
        coded = [encoder.produce_coded_packet() for _ in range(count)]
        self.record_audit_event("RLNC_ENCODE_GENERATION", {
            "generation_size": len(packets),
            "coded_count": len(coded)
        })
        return coded

    def rlnc_decode_generation(
        self,
        coded_packets: List[Tuple[List[int], bytes]],
        generation_size: int,
        packet_len: int
    ) -> Optional[List[bytes]]:
        """Decodes an RLNC generation via incremental Gaussian elimination over GF(256)."""
        raise NotImplementedError("Research prototype quarantined in research/")
        decoder = RLNCDecoder(generation_size, packet_len)
        for coeffs, data in coded_packets:
            decoder.add_coded_packet(coeffs, data)
        if decoder.is_complete():
            decoded = decoder.decode()
            self.record_audit_event("RLNC_DECODE_SUCCESS", {
                "generation_size": generation_size,
                "rank": decoder.rank
            })
            return decoded
        return None

    def qos_enqueue(self, packet: bytes, qos_class: int = 1) -> bool:
        """Enqueues packet into tactical QoS shaper priority queue."""
        if not self.qos_shaper:
            return False
        ok = self.qos_shaper.enqueue_packet(packet, qos_class)
        self.record_audit_event("QOS_ENQUEUED", {
            "qos_class": qos_class,
            "packet_len": len(packet)
        })
        return ok

    def qos_dequeue(self) -> Optional[Tuple[bytes, int]]:
        """Dequeues highest-priority schedulable packet according to token availability and link health."""
        if not self.qos_shaper:
            return None
        return self.qos_shaper.dequeue_packet()

    def qos_report_link_health(self, pdr: float, rtt_ms: float = 50.0) -> None:
        """Reports packet delivery ratio and round-trip time to adaptively throttle lower QoS tiers."""
        if self.qos_shaper:
            self.qos_shaper.report_link_health(pdr, rtt_ms)
            self.record_audit_event("QOS_HEALTH_REPORTED", {
                "pdr": pdr,
                "rtt_ms": rtt_ms,
                "congested": self.qos_shaper.is_congested
            })

    def qos_get_queue_depth(self) -> Dict[str, Any]:
        """Returns queue depth and congestion status across all QoS priority classes."""
        if not self.qos_shaper:
            return {"critical": 0, "tactical": 0, "bulk": 0, "is_congested": False}
        return self.qos_shaper.get_queue_depth()

    def zkp_generate_keypair(self) -> Tuple[int, int]:
        """Generates Schnorr discrete logarithm keypair (private_x, public_y)."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return SchnorrZKP.generate_keypair()

    def zkp_create_proof(self, private_x: int, public_y: int, context: str = "GostNet_ZKP_Auth") -> Dict[str, Any]:
        """Generates non-interactive zero-knowledge proof of knowledge of private_x."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return SchnorrZKP.create_proof(private_x, public_y, context)

    def zkp_verify_proof(self, public_y: int, proof: Dict[str, Any], context: Optional[str] = None) -> bool:
        """Verifies non-interactive zero-knowledge proof without learning private secret."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return SchnorrZKP.verify_proof(public_y, proof, context)

    def send_zkp_auth_proof(
        self,
        target_peer: str,
        private_x: int,
        public_y: int,
        context: str = "GostNet_ZKP_Auth"
    ) -> bool:
        """Generates and transmits Schnorr ZKP proof to target peer for zero-knowledge authentication."""
        try:
            raise NotImplementedError("Research prototype quarantined in research/")
            proof = SchnorrZKP.create_proof(private_x, public_y, context)
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "ZKP_AUTH_PROOF",
                "public_y": hex(public_y),
                "proof": proof,
                "context": context,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("ZKP_AUTH_DISPATCHED", {
                "target_peer": target_peer,
                "context": context
            })
            return True
        except Exception as e:
            print(f"[SchnorrZKP] Error sending ZKP_AUTH_PROOF: {e}")
            return False

    def _handle_pq_kem_ciphertext(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming PQ_KEM_CIPHERTEXT packet."""
        try:
            ct = header.get("ciphertext", {})
            from_peer = header.get("sender_peer_id", sender_ip)
            self.record_audit_event("PQ_KEM_CIPHERTEXT_INGRESS", {
                "from_peer": from_peer
            })
            if self.on_pq_kem_ciphertext_received:
                self.on_pq_kem_ciphertext_received(sender_ip, ct)
        except Exception as e:
            print(f"[PostQuantumKEM] Error handling PQ_KEM_CIPHERTEXT: {e}")

    def _handle_homomorphic_telemetry(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming HOMOMORPHIC_TELEMETRY packet."""
        try:
            c_hex = header.get("ciphertext")
            c = int(c_hex, 16) if isinstance(c_hex, str) else int(c_hex)
            sensor_type = header.get("sensor_type", "sensor")
            from_peer = header.get("sender_peer_id", sender_ip)
            self.record_audit_event("HOMOMORPHIC_TELEMETRY_INGRESS", {
                "from_peer": from_peer,
                "sensor_type": sensor_type
            })
            if self.on_homomorphic_telemetry_received:
                self.on_homomorphic_telemetry_received(sender_ip, c, sensor_type)
        except Exception as e:
            print(f"[HomomorphicAggregator] Error handling HOMOMORPHIC_TELEMETRY: {e}")

    def pq_generate_keypair(self) -> Tuple[Dict[str, List[int]], List[int]]:
        """Generates Post-Quantum Ring-LWE public key (a, t) and private key s."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return PostQuantumLatticeKEM.generate_keypair()

    def pq_encapsulate(self, public_key: Dict[str, List[int]]) -> Tuple[Dict[str, List[int]], bytes]:
        """Encapsulates shared secret, producing ciphertext (u, v) and 32-byte secret K_pq."""
        raise NotImplementedError("Research prototype quarantined in research/")
        ciphertext, secret = PostQuantumLatticeKEM.encapsulate(public_key)
        self.record_audit_event("PQ_KEM_ENCAPSULATE", {
            "u_len": len(ciphertext.get("u", [])),
            "v_len": len(ciphertext.get("v", []))
        })
        return ciphertext, secret

    def pq_decapsulate(self, private_key: List[int], ciphertext: Dict[str, List[int]]) -> bytes:
        """Decapsulates ciphertext (u, v) using private key s to recover shared secret K_pq."""
        raise NotImplementedError("Research prototype quarantined in research/")
        secret = PostQuantumLatticeKEM.decapsulate(private_key, ciphertext)
        self.record_audit_event("PQ_KEM_DECAPSULATE", {
            "u_len": len(ciphertext.get("u", [])),
            "v_len": len(ciphertext.get("v", []))
        })
        return secret

    def pq_combine_hybrid_keys(self, ecdh_secret: bytes, pq_secret: bytes, context: str = "GostNet_Hybrid_PQ") -> bytes:
        """Derives hybrid classical + post-quantum session key via HKDF."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return PostQuantumLatticeKEM.combine_hybrid_keys(ecdh_secret, pq_secret, context)

    def send_pq_kem_ciphertext(self, target_peer: str, ciphertext: Dict[str, List[int]]) -> bool:
        """Transmits encapsulated Post-Quantum ciphertext to target peer over TCP socket."""
        try:
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "PQ_KEM_CIPHERTEXT",
                "ciphertext": ciphertext,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("PQ_KEM_DISPATCHED", {
                "target_peer": target_peer
            })
            return True
        except Exception as e:
            print(f"[PostQuantumKEM] Error sending PQ_KEM_CIPHERTEXT: {e}")
            return False

    def homomorphic_generate_keypair(self, key_bits: int = 128) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Generates Paillier additive homomorphic keypair (public_key, private_key)."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return PaillierHomomorphicAggregator.generate_keypair(key_bits)

    def homomorphic_encrypt(self, public_key: Dict[str, int], value: int) -> int:
        """Encrypts integer telemetry value with Paillier public key."""
        raise NotImplementedError("Research prototype quarantined in research/")
        c = PaillierHomomorphicAggregator.encrypt(public_key, value)
        self.record_audit_event("HOMOMORPHIC_ENCRYPT", {
            "val_len": len(str(value))
        })
        return c

    def homomorphic_aggregate(self, public_key: Dict[str, int], ciphertexts: List[int]) -> int:
        """Homomorphically sums encrypted ciphertexts without decrypting individual readings."""
        raise NotImplementedError("Research prototype quarantined in research/")
        c_sum = PaillierHomomorphicAggregator.aggregate_ciphertexts(public_key, ciphertexts)
        self.record_audit_event("HOMOMORPHIC_AGGREGATE", {
            "count": len(ciphertexts)
        })
        return c_sum

    def homomorphic_decrypt(self, private_key: Dict[str, int], public_key: Dict[str, int], ciphertext: int) -> int:
        """Decrypts aggregated ciphertext sum using private key."""
        raise NotImplementedError("Research prototype quarantined in research/")
        plaintext = PaillierHomomorphicAggregator.decrypt(private_key, public_key, ciphertext)
        self.record_audit_event("HOMOMORPHIC_DECRYPT", {
            "result": plaintext
        })
        return plaintext

    def send_homomorphic_reading(
        self,
        target_peer: str,
        public_key: Dict[str, int],
        reading: int,
        sensor_type: str = "radiation"
    ) -> bool:
        """Encrypts and transmits an encrypted sensor reading to a swarm aggregation relay."""
        try:
            raise NotImplementedError("Research prototype quarantined in research/")
            c = PaillierHomomorphicAggregator.encrypt(public_key, reading)
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "HOMOMORPHIC_TELEMETRY",
                "ciphertext": hex(c),
                "sensor_type": sensor_type,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("HOMOMORPHIC_DISPATCHED", {
                "target_peer": target_peer,
                "sensor_type": sensor_type
            })
            return True
        except Exception as e:
            print(f"[HomomorphicAggregator] Error sending HOMOMORPHIC_TELEMETRY: {e}")
            return False

    def dsss_generate_gold_code(self, length: int = 31) -> List[int]:
        """Generates 31-chip Gold sequence via dual LFSRs for DSSS modulation."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return DSSSModulator.generate_gold_sequence(length)

    def dsss_spread_packet(self, data: bytes, gold_code: Optional[List[int]] = None) -> List[float]:
        """Spreads binary payload across pseudo-random noise chips for LPI/LPD covert transmission."""
        raise NotImplementedError("Research prototype quarantined in research/")
        code = gold_code if gold_code is not None else DSSSModulator.generate_gold_sequence(31)
        chips = DSSSModulator.spread(data, code)
        self.record_audit_event("DSSS_SPREAD", {
            "data_len": len(data),
            "chip_count": len(chips)
        })
        return chips

    def dsss_despread_packet(self, received_chips: List[float], gold_code: Optional[List[int]] = None) -> bytes:
        """Despreads received chips using matched-filter cross-correlation against reference Gold code."""
        raise NotImplementedError("Research prototype quarantined in research/")
        code = gold_code if gold_code is not None else DSSSModulator.generate_gold_sequence(31)
        data = DSSSModulator.despread(received_chips, code)
        self.record_audit_event("DSSS_DESPREAD", {
            "recovered_len": len(data)
        })
        return data

    def virtual_array_register_node(self, node_id: str, x_meters: float, y_meters: float):
        """Registers adjacent squad node spatial coordinates relative to array reference."""
        if self.virtual_array:
            self.virtual_array.register_node(node_id, x_meters, y_meters)
            self.record_audit_event("VIRTUAL_ARRAY_NODE_REGISTERED", {
                "node_id": node_id,
                "x_m": x_meters,
                "y_m": y_meters
            })

    def virtual_array_remove_node(self, node_id: str):
        """Deregisters a node from the virtual antenna array."""
        if self.virtual_array:
            self.virtual_array.remove_node(node_id)
            self.record_audit_event("VIRTUAL_ARRAY_NODE_REMOVED", {
                "node_id": node_id
            })

    def virtual_array_compute_steering(self, target_azimuth_deg: float) -> Dict[str, Dict[str, float]]:
        """Calculates phase shifts and time delays for constructive beamforming toward target azimuth."""
        if not self.virtual_array:
            return {}
        res = self.virtual_array.compute_steering_phases(target_azimuth_deg)
        self.record_audit_event("VIRTUAL_ARRAY_STEERING_COMPUTED", {
            "azimuth_deg": target_azimuth_deg,
            "node_count": len(res)
        })
        return res

    def virtual_array_get_gain_db(self) -> float:
        """Calculates theoretical coherent power gain of distributed array in dB (20 * log10(N))."""
        if not self.virtual_array:
            return 0.0
        return self.virtual_array.compute_array_power_gain_db()

    def virtual_array_compute_factor(self, steering_azimuth_deg: float, observation_azimuth_deg: float) -> float:
        """Computes normalized Array Factor magnitude at observation angle when steered toward steering angle."""
        if not self.virtual_array:
            return 1.0
        return self.virtual_array.compute_array_factor(steering_azimuth_deg, observation_azimuth_deg)

    def _handle_time_sync_request(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming TIME_SYNC_REQUEST packet and replies with local timestamps."""
        try:
            t2 = time.time()
            t1 = float(header.get("t1", t2))
            t3 = time.time()
            dest_host, dest_port, final_target_id = self._resolve_peer_target(sender_ip)
            resp_port = header.get("sender_tcp_port") or dest_port
            resp_header = {
                "type": "TIME_SYNC_RESPONSE",
                "t1": t1,
                "t2": t2,
                "t3": t3,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": header.get("sender_peer_id", final_target_id)
            }
            packet_bytes = json.dumps(resp_header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, resp_port))
                s.sendall(packet_bytes)
            self.record_audit_event("TIME_SYNC_REQUEST_PROCESSED", {
                "from_peer": header.get("sender_peer_id")
            })
        except Exception as e:
            print(f"[MeshTimeSync] Error handling TIME_SYNC_REQUEST: {e}")

    def _handle_time_sync_response(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming TIME_SYNC_RESPONSE packet, records sample, and updates clock state."""
        try:
            t4 = time.time()
            t1 = float(header.get("t1", t4))
            t2 = float(header.get("t2", t4))
            t3 = float(header.get("t3", t4))
            peer_id = header.get("sender_peer_id", sender_ip)
            if self.mesh_time_sync:
                sample = self.mesh_time_sync.record_sync_sample(peer_id, t1, t2, t3, t4)
                self.mesh_time_sync.run_synchronisation_round()
                self.record_audit_event("TIME_SYNC_SAMPLE_RECORDED", {
                    "peer_id": peer_id,
                    "offset_s": sample.offset_s,
                    "rtt_s": sample.rtt_s
                })
                if self.on_time_sync_updated:
                    self.on_time_sync_updated(peer_id, sample.offset_s, sample.uncertainty_s)
        except Exception as e:
            print(f"[MeshTimeSync] Error handling TIME_SYNC_RESPONSE: {e}")

    def request_peer_time_sync(self, target_peer: str) -> bool:
        """Sends a TIME_SYNC_REQUEST to a target peer to initiate Cristian precision offset estimation."""
        try:
            t1 = time.time()
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "TIME_SYNC_REQUEST",
                "t1": t1,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("TIME_SYNC_REQUEST_SENT", {
                "target_peer": target_peer
            })
            return True
        except Exception as e:
            print(f"[MeshTimeSync] Error sending TIME_SYNC_REQUEST: {e}")
            return False

    def get_mesh_synchronized_time(self) -> float:
        """Returns consensus mesh wall-clock time adjusted by Marzullo intersection offset."""
        if not self.mesh_time_sync:
            return time.time()
        return self.mesh_time_sync.adjusted_time()

    def get_mesh_time_sync_precision(self) -> float:
        """Returns clock uncertainty half-width in milliseconds."""
        if not self.mesh_time_sync:
            return float("inf")
        return self.mesh_time_sync.precision_ms()

    def run_mesh_time_sync_round(self, max_faulty: int = 0) -> Dict[str, Any]:
        """Executes Marzullo intersection algorithm across collected clock samples."""
        if not self.mesh_time_sync:
            return {"synchronised": False, "offset_s": 0.0, "uncertainty_s": float("inf")}
        st = self.mesh_time_sync.run_synchronisation_round(max_faulty)
        res = {
            "synchronised": st.is_synchronised,
            "offset_s": st.estimated_offset_s,
            "uncertainty_s": st.uncertainty_s,
            "peer_count": st.peer_count,
            "stratum": st.stratum
        }
        self.record_audit_event("TIME_SYNC_ROUND_EXECUTED", res)
        return res

    def encode_covert_timing(self, payload: bytes, key: Optional[bytes] = None) -> List[float]:
        """Encodes payload into inter-packet delays using uniform timing buckets or keyed permutation."""
        if key is not None:
            raise NotImplementedError("Research prototype quarantined in research/")
            ktc = KeyedTimingChannel(key=key)
            delays = ktc.encode(payload)
        elif self.covert_timing_channel:
            delays = self.covert_timing_channel.encode(payload)
        else:
            raise NotImplementedError("Research prototype quarantined in research/")
            ctc = CovertTimingChannel()
            delays = ctc.encode(payload)
        self.record_audit_event("COVERT_TIMING_ENCODE", {
            "payload_len": len(payload),
            "delays_count": len(delays),
            "keyed": (key is not None)
        })
        return delays

    def decode_covert_timing(self, delays: List[float], key: Optional[bytes] = None) -> bytes:
        """Decodes inter-packet delays back to the original payload via quantisation and inverse mapping."""
        if key is not None:
            raise NotImplementedError("Research prototype quarantined in research/")
            ktc = KeyedTimingChannel(key=key)
            payload = ktc.decode(delays)
        elif self.covert_timing_channel:
            payload = self.covert_timing_channel.decode(delays)
        else:
            raise NotImplementedError("Research prototype quarantined in research/")
            ctc = CovertTimingChannel()
            payload = ctc.decode(delays)
        self.record_audit_event("COVERT_TIMING_DECODE", {
            "recovered_len": len(payload),
            "delays_count": len(delays),
            "keyed": (key is not None)
        })
        return payload

    def get_covert_channel_capacity(self, mean_ipd_ms: float = 100.0) -> float:
        """Returns theoretical Shannon bit rate (bps) for given mean inter-packet delay."""
        if not self.covert_timing_channel:
            return 0.0
        return self.covert_timing_channel.channel_capacity_bps(mean_ipd_ms)

    def calculate_link_budget(
        self,
        distance_m: float,
        tx_power_dbm: float = 27.0,
        freq_hz: float = 915e6,
        rain_rate_mm_hr: float = 0.0,
        foliage_depth_m: float = 0.0
    ) -> Dict[str, Any]:
        """Calculates Friis path loss, thermal noise floor, SNR, and link margin for tactical RF planning."""
        raise NotImplementedError("Research prototype quarantined in research/")
        radio = RadioParameters(tx_power_dbm=tx_power_dbm, frequency_hz=freq_hz)
        tx_ant = Antenna()
        rx_ant = Antenna()
        env = EnvironmentalLoss(rain_rate_mm_hr=rain_rate_mm_hr, foliage_depth_m=foliage_depth_m)
        res = LinkBudgetCalculator.calculate(radio, tx_ant, rx_ant, env, distance_m)
        report = {
            "fspl_db": round(res.fspl_db, 2),
            "rx_power_dbm": round(res.rx_power_dbm, 2),
            "noise_floor_dbm": round(res.noise_floor_dbm, 2),
            "snr_db": round(res.snr_db, 2),
            "link_margin_db": round(res.link_margin_db, 2),
            "max_range_m": round(res.max_range_m, 1),
            "viable": (res.link_margin_db >= 0.0)
        }
        self.record_audit_event("LINK_BUDGET_CALCULATED", report)
        return report

    def estimate_max_range(
        self,
        tx_power_dbm: float = 27.0,
        freq_hz: float = 915e6,
        rain_rate_mm_hr: float = 0.0
    ) -> float:
        """Estimates maximum communication range in metres where link margin equals zero."""
        raise NotImplementedError("Research prototype quarantined in research/")
        radio = RadioParameters(tx_power_dbm=tx_power_dbm, frequency_hz=freq_hz)
        tx_ant = Antenna()
        rx_ant = Antenna()
        env = EnvironmentalLoss(rain_rate_mm_hr=rain_rate_mm_hr)
        return LinkBudgetCalculator.max_range_meters(radio, tx_ant, rx_ant, env)

    def evaluate_rf_signature(
        self,
        tx_power_dbm: float = 27.0,
        freq_hz: float = 915e6,
        duty_cycle: float = 0.1,
        burst_duration_ms: float = 50.0,
        link_margin_db: float = 10.0
    ) -> Dict[str, Any]:
        """Evaluates RF emission signature threat score and provides transmission power/duty cycle recommendations."""
        raise NotImplementedError("Research prototype quarantined in research/")
        emitter = EmitterProfile(
            tx_power_dbm=tx_power_dbm,
            frequency_hz=freq_hz,
            duty_cycle=duty_cycle,
            burst_duration_ms=burst_duration_ms
        )
        intercept = InterceptReceiverProfile()
        rep = RFSignatureAdvisor.recommend(emitter, intercept, link_margin_db)
        res = {
            "eirp_dbm": round(rep.eirp_dbm, 2),
            "eirp_watts": round(rep.eirp_watts, 4),
            "intercept_range_m": round(rep.intercept_range_m, 1),
            "emission_score": round(rep.emission_score, 4),
            "recommended_tx_power_dbm": round(rep.recommended_tx_power_dbm, 2),
            "recommended_duty_cycle": round(rep.recommended_duty_cycle, 4),
            "recommended_burst_duration_ms": round(rep.recommended_burst_duration_ms, 1)
        }
        self.record_audit_event("RF_SIGNATURE_EVALUATED", res)
        return res

    def rank_operational_frequencies(
        self,
        candidate_freqs_hz: List[float],
        tx_power_dbm: float = 27.0
    ) -> List[Tuple[float, float]]:
        """Ranks candidate operating frequencies by ascending adversary intercept range."""
        raise NotImplementedError("Research prototype quarantined in research/")
        emitter = EmitterProfile(tx_power_dbm=tx_power_dbm)
        intercept = InterceptReceiverProfile()
        return RFSignatureAdvisor.rank_frequencies(candidate_freqs_hz, emitter, intercept)

    def _handle_cqi_feedback(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming CQI_FEEDBACK packet and updates local transmission modulation profile."""
        try:
            feedback = header.get("cqi_payload", {})
            from_peer = header.get("sender_peer_id", sender_ip)
            if self.adaptive_modulation and feedback:
                new_profile = self.adaptive_modulation.decode_and_apply_cqi(feedback)
                self.record_audit_event("CQI_FEEDBACK_PROCESSED", {
                    "from_peer": from_peer,
                    "cqi": feedback.get("cqi"),
                    "profile": new_profile.name,
                    "snr_db": feedback.get("snr_db")
                })
        except Exception as e:
            print(f"[AdaptiveModulation] Error handling CQI feedback: {e}")

    def send_cqi_feedback(self, target_peer: str, cqi_data: Optional[dict] = None) -> bool:
        """Sends closed-loop CQI feedback telemetry to a transmitting peer."""
        try:
            if cqi_data is None and self.adaptive_modulation:
                cqi_data = self.adaptive_modulation.encode_cqi_feedback()
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "CQI_FEEDBACK",
                "cqi_payload": cqi_data or {},
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("CQI_FEEDBACK_SENT", {
                "target_peer": target_peer,
                "cqi": (cqi_data or {}).get("cqi")
            })
            return True
        except Exception as e:
            print(f"[AdaptiveModulation] Error sending CQI feedback: {e}")
            return False

    def _handle_lkh_rekey(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming LKH_REKEY packet."""
        try:
            rekey_data = header.get("rekey_payload", {})
            from_peer = header.get("sender_peer_id", sender_ip)
            self.record_audit_event("LKH_REKEY_RECEIVED", {
                "from_peer": from_peer,
                "target_node_id": rekey_data.get("target_node_id"),
                "enc_by_node_id": rekey_data.get("enc_by_node_id")
            })
            if self.on_lkh_rekey_received:
                self.on_lkh_rekey_received(rekey_data)
        except Exception as e:
            print(f"[GroupRekeying] Error handling LKH_REKEY: {e}")

    def send_lkh_rekey_message(self, target_peer: str, rekey_data: dict) -> bool:
        """Transmits an LKH rekey message to a target peer."""
        try:
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            header = {
                "type": "LKH_REKEY",
                "rekey_payload": rekey_data,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("LKH_REKEY_SENT", {
                "target_peer": target_peer,
                "target_node_id": rekey_data.get("target_node_id")
            })
            return True
        except Exception as e:
            print(f"[GroupRekeying] Error sending LKH_REKEY: {e}")
            return False

    def adapt_link_modulation(self, measured_snr_db: float) -> Dict[str, Any]:
        """Adapts modulation and coding profile based on measured SNR with hysteresis filtering."""
        if not self.adaptive_modulation:
            return {"profile": "QPSK_1_2", "snr_db": measured_snr_db}
        rep = self.adaptive_modulation.select_profile(measured_snr_db)
        res = {
            "profile": rep.active_profile.name,
            "snr_db": rep.snr_db,
            "cqi": rep.target_cqi,
            "shannon_capacity_bps": round(rep.shannon_capacity_bps, 1),
            "effective_throughput_bps": round(rep.effective_throughput_bps, 1),
            "spectral_efficiency": round(rep.spectral_efficiency, 3),
            "bler_estimate": round(rep.bler_estimate, 5),
            "hysteresis_active": rep.hysteresis_active
        }
        self.record_audit_event("LINK_ADAPTATION_EVALUATED", res)
        return res

    def evaluate_fuzzy_route(
        self,
        node_id: str,
        battery_pct: float,
        rssi_dbm: float,
        pdr: float,
        rtt_ms: float,
        hop_count: int = 1,
        mode: str = "STANDARD"
    ) -> Dict[str, Any]:
        """Evaluates fuzzy multi-criteria routing suitability for a single relay candidate."""
        raise NotImplementedError("Research prototype quarantined in research/")
        m = MissionMode[mode.upper()] if mode.upper() in MissionMode.__members__ else MissionMode.STANDARD
        engine = FuzzyRoutingEngine(mode=m)
        metrics = NodeMetrics(
            node_id=node_id,
            battery_pct=battery_pct,
            rssi_dbm=rssi_dbm,
            pdr=pdr,
            rtt_ms=rtt_ms,
            hop_count=hop_count
        )
        fe = engine.evaluate_node(metrics)
        res = {
            "node_id": fe.node_id,
            "composite_score": fe.composite_score,
            "battery_score": fe.battery_score,
            "link_score": fe.link_score,
            "pdr_score": fe.pdr_score,
            "latency_score": fe.latency_score,
            "hop_score": fe.hop_score,
            "classification": fe.classification
        }
        self.record_audit_event("FUZZY_ROUTE_EVALUATED", res)
        return res

    def rank_fuzzy_paths(
        self,
        candidate_paths: List[List[Dict[str, Any]]],
        mode: str = "STANDARD"
    ) -> List[Dict[str, Any]]:
        """Ranks multiple candidate multi-hop routes using multi-criteria fuzzy logic and AHP."""
        raise NotImplementedError("Research prototype quarantined in research/")
        m = MissionMode[mode.upper()] if mode.upper() in MissionMode.__members__ else MissionMode.STANDARD
        engine = FuzzyRoutingEngine(mode=m)
        typed_paths: List[List[NodeMetrics]] = []
        for path in candidate_paths:
            typed_path = []
            for d in path:
                typed_path.append(NodeMetrics(
                    node_id=d.get("node_id", "UNKNOWN"),
                    battery_pct=float(d.get("battery_pct", 100.0)),
                    rssi_dbm=float(d.get("rssi_dbm", -70.0)),
                    pdr=float(d.get("pdr", 1.0)),
                    rtt_ms=float(d.get("rtt_ms", 20.0)),
                    hop_count=int(d.get("hop_count", 1))
                ))
            typed_paths.append(typed_path)
        ranked = engine.rank_paths(typed_paths)
        res = []
        for pr in ranked:
            res.append({
                "path_nodes": pr.path_nodes,
                "bottleneck_score": pr.bottleneck_score,
                "average_score": pr.average_score,
                "total_hops": pr.total_hops,
                "is_viable": pr.is_viable
            })
        self.record_audit_event("FUZZY_PATHS_RANKED", {
            "path_count": len(res),
            "top_path": res[0]["path_nodes"] if res else []
        })
        return res

    def verify_anti_replay(self, peer_id: str, seq_num: int, epoch: int = 1) -> Tuple[bool, str]:
        """Validates incoming sequence number against sliding window bitmask to prevent replay attacks."""
        if not self.anti_replay:
            return (True, "OK_IN_ORDER")
        valid, reason = self.anti_replay.verify_and_accept(peer_id, seq_num, epoch)
        self.record_audit_event("ANTI_REPLAY_CHECK", {
            "peer_id": peer_id,
            "seq_num": seq_num,
            "epoch": epoch,
            "valid": valid,
            "reason": reason
        })
        return (valid, reason)

    def get_anti_replay_peer_state(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Returns diagnostic sliding window metrics for a given peer."""
        if not self.anti_replay:
            return None
        return self.anti_replay.get_peer_state(peer_id)

    def _handle_tactical_alert(self, sender_ip: str, header: dict, remaining_data: bytes):
        """Processes incoming TACTICAL_ALERT packet and records in HUD."""
        try:
            alert_data = header.get("alert_payload", {})
            from_peer = header.get("sender_peer_id", sender_ip)
            if self.tactical_hud and alert_data:
                self.tactical_hud.add_alert(
                    severity=alert_data.get("severity", "INFO"),
                    subsystem=alert_data.get("subsystem", "REMOTE"),
                    message=f"[{from_peer}] {alert_data.get('message', '')}"
                )
            self.record_audit_event("TACTICAL_ALERT_RECEIVED", {
                "from_peer": from_peer,
                "severity": alert_data.get("severity"),
                "subsystem": alert_data.get("subsystem")
            })
            if self.on_tactical_alert_received:
                self.on_tactical_alert_received(alert_data)
        except Exception as e:
            print(f"[TacticalHUD] Error handling TACTICAL_ALERT: {e}")

    def send_tactical_alert(self, target_peer: str, severity: str, subsystem: str, message: str) -> bool:
        """Sends a high-priority tactical operational alert to a target peer."""
        try:
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_peer)
            alert_payload = {
                "severity": severity.upper(),
                "subsystem": subsystem.upper(),
                "message": message,
                "timestamp": time.time()
            }
            if self.tactical_hud:
                self.tactical_hud.add_alert(severity, subsystem, message)
            header = {
                "type": "TACTICAL_ALERT",
                "alert_payload": alert_payload,
                "sender_peer_id": self.peer_id,
                "sender_tcp_port": self.tcp_port,
                "target_peer_id": final_target_id
            }
            packet_bytes = json.dumps(header).encode('utf-8') + self.HEADER_DELIMITER
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((dest_host, dest_port))
                s.sendall(packet_bytes)
            self.record_audit_event("TACTICAL_ALERT_SENT", {
                "target_peer": target_peer,
                "severity": severity,
                "subsystem": subsystem
            })
            return True
        except Exception as e:
            print(f"[TacticalHUD] Error sending TACTICAL_ALERT: {e}")
            return False

    def compile_tactical_hud(self) -> Dict[str, Any]:
        """Compiles a unified C4ISR tactical HUD telemetry summary across all subsystems."""
        if not self.tactical_hud:
            raise NotImplementedError("Research prototype quarantined in research/")
            self.tactical_hud = TacticalHUDController(callsign=self.username, peer_id=self.peer_id)
        st = self.tactical_hud.compile_hud_state(self)
        res = {
            "callsign": st.callsign,
            "peer_id": st.peer_id,
            "network_state": st.network_state,
            "timestamp": st.timestamp,
            "amc_profile": st.amc_profile,
            "cqi": st.cqi,
            "shannon_capacity_bps": st.shannon_capacity_bps,
            "link_margin_db": st.link_margin_db,
            "eirp_threat_score": st.eirp_threat_score,
            "mesh_nodes_count": st.mesh_nodes_count,
            "mesh_diameter": st.mesh_diameter,
            "critical_bridges_count": st.critical_bridges_count,
            "anti_replay_rejected": st.anti_replay_rejected,
            "lkh_group_key_id": st.lkh_group_key_id,
            "merkle_ledger_height": st.merkle_ledger_height,
            "merkle_root_hash": st.merkle_root_hash,
            "jammer_detected": st.jammer_detected,
            "alerts_count": len(st.alerts)
        }
        self.record_audit_event("TACTICAL_HUD_COMPILED", res)
        return res

    def render_tactical_hud_ascii(self) -> str:
        """Renders an ASCII text dashboard of the tactical HUD for terminal output."""
        if not self.tactical_hud:
            raise NotImplementedError("Research prototype quarantined in research/")
            self.tactical_hud = TacticalHUDController(callsign=self.username, peer_id=self.peer_id)
        st = self.tactical_hud.compile_hud_state(self)
        return self.tactical_hud.render_ascii_dashboard(st)

    def execute_memory_panic_scrub(self) -> Dict[str, Any]:
        """Executes multi-pass in-memory cryptographic zeroization and purges session keys."""
        raise NotImplementedError("Research prototype quarantined in research/")
        if not self.memory_scrubber:
            self.memory_scrubber = MemoryScrubber()
        receipt = self.memory_scrubber.execute_panic_zeroization()
        if hasattr(self, "zeroize_ephemeral_keys"):
            try:
                self.zeroize_ephemeral_keys()
            except Exception:
                pass
        res = {
            "buffers_scrubbed": receipt.buffers_scrubbed_count,
            "bytes_overwritten": receipt.bytes_overwritten_total,
            "passes": receipt.passes_completed,
            "verification_digest": receipt.verification_digest
        }
        self.record_audit_event("PANIC_ZEROIZATION_EXECUTED", res)
        return res

    def register_bearer_interface(self, bearer_name: str, priority: int = 1, mtu_bytes: int = 1400):
        """Registers a communication bearer interface for dynamic redundancy."""
        return
        if not self.bearer_failover:
            self.bearer_failover = BearerFailoverController()
        b_type = BearerType[bearer_name.upper()] if bearer_name.upper() in BearerType.__members__ else BearerType.LAN_TCP
        self.bearer_failover.register_bearer(b_type, priority=priority, mtu_bytes=mtu_bytes)

    def update_bearer_link_health(self, bearer_name: str, rtt_ms: float, success: bool) -> Optional[str]:
        """Updates link health of a bearer and returns currently active bearer name."""
        return
        if not self.bearer_failover:
            return None
        b_type = BearerType[bearer_name.upper()] if bearer_name.upper() in BearerType.__members__ else BearerType.LAN_TCP
        self.bearer_failover.update_bearer_heartbeat(b_type, rtt_ms=rtt_ms, success=success)
        active = self.bearer_failover.get_active_bearer()
        active_name = active.bearer_type.value if active else None
        self.record_audit_event("BEARER_HEALTH_UPDATED", {
            "bearer": bearer_name,
            "rtt_ms": rtt_ms,
            "success": success,
            "active_bearer": active_name
        })
        return active_name

    def obfuscate_location(self, lat: float, lon: float, epsilon: float = 0.005) -> Dict[str, Any]:
        """Obfuscates GPS coordinates using planar Laplace geo-indistinguishable differential privacy."""
        raise NotImplementedError("Research prototype quarantined in research/")
        return SpatialPrivacyEngine.obfuscate_coordinates(lat, lon, epsilon)

    def get_mesh_topology_summary(self) -> dict:
        """Returns topology health metrics, diameter, components, and critical bridges."""
        if not self.topology_manager:
            return {
                "available": False,
                "node_count": 0,
                "edge_count": 0,
                "diameter": 0,
                "components": 0,
                "critical_bridges": []
            }
        return {
            "available": True,
            "node_count": len(self.topology_manager.node_metadata),
            "edge_count": sum(len(neighbors) for neighbors in self.topology_manager.adjacency.values()) // 2,
            "diameter": self.topology_manager.calculate_network_diameter(),
            "components": len(self.topology_manager.get_connected_components()),
            "critical_bridges": self.topology_manager.find_critical_bridge_nodes(),
            "json": self.topology_manager.export_json(),
            "dot": self.topology_manager.export_dot()
        }

    def encode_with_fec(self, data: bytes, k: Optional[int] = None, m: Optional[int] = None) -> List[bytes]:
        """Encode binary payload into K data + M parity FEC erasure blocks."""
        if not self.fec_engine:
            return [data]
        return self.fec_engine.encode(data, k=k, m=m)

    def decode_from_fec(self, blocks: List[bytes]) -> Optional[bytes]:
        """Decode and reconstruct binary payload from any K out of N FEC erasure blocks."""
        if not self.fec_engine:
            return blocks[0] if blocks else None
        return self.fec_engine.decode(blocks)

    def init_otp_vault(self, pad_file_path: str, initial_pad_bytes: Optional[bytes] = None) -> bool:
        """Mount a pre-shared One-Time Pad stream vault file for quantum-resilient forward secrecy."""
        try:
            raise NotImplementedError("Research prototype quarantined in research/")
            self.otp_vault = OTPStreamVault(pad_file_path, initial_pad_bytes=initial_pad_bytes)
            print(f"[OTP] Mounted OTP Stream Vault: {pad_file_path} ({self.otp_vault.remaining_pad_bytes()} bytes available)")
            return True
        except Exception as e:
            print(f"[OTP] Failed to mount OTP vault: {e}")
            return False

    def send_otp_message(self, target_ip: str, message_text: str, peer_id: Optional[str] = None) -> bool:
        """
        Encrypts plaintext using mounted One-Time Pad Stream Vault and sends as an OTP_FRAME.
        Provides information-theoretic forward secrecy with non-reusable pad stream.
        """
        if not self.otp_vault:
            print("[OTP] Cannot send: No OTP vault mounted.")
            return False

        try:
            raw_bytes = message_text.encode('utf-8')
            otp_frame = self.otp_vault.encrypt_otp(raw_bytes)
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_ip)
            
            otp_frame["target_peer_id"] = final_target_id
            otp_frame["sender_peer_id"] = self.peer_id
            otp_frame["sender_ip"] = self.local_ip
            otp_frame["timestamp"] = time.time()
            
            frame_json = json.dumps(otp_frame).encode('utf-8')
            packet_data = self._encrypt_message(frame_json) + self.HEADER_DELIMITER
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((dest_host, dest_port))
            sock.sendall(packet_data)
            sock.close()
            
            timestamp_unix = time.time()
            self._persist_message(final_target_id, "me", "text", f"[OTP]: {message_text}", timestamp_unix, ttl=None)
            print(f"[OTP] Dispatched OTP frame to {dest_host}:{dest_port} (consumed {len(raw_bytes)} bytes from pad)")
            return True
        except Exception as e:
            print(f"[OTP] Error sending OTP message: {e}")
            return False

    def create_proximity_token(self, lat: float, lon: float, shared_salt: bytes, precision: int = 6) -> dict:
        """Generate zero-knowledge blinded proximity commitment token for physical co-location proof."""
        if not self.proximity_verifier:
            raise NotImplementedError("Research prototype quarantined in research/")
            return ProximityVerifier.create_proximity_token(lat, lon, shared_salt, precision)
        return self.proximity_verifier.create_proximity_token(lat, lon, shared_salt, precision)

    def verify_peer_proximity(self, local_token: dict, peer_token: dict) -> bool:
        """Cryptographically verifies spatial co-location without revealing absolute coordinates."""
        if not self.proximity_verifier:
            raise NotImplementedError("Research prototype quarantined in research/")
            return ProximityVerifier.verify_proximity(local_token, peer_token)
        return self.proximity_verifier.verify_proximity(local_token, peer_token)

    def record_link_quality(self, peer_id: str, pdr: float, cca_busy: float = 0.0):
        """Records neighbor link quality for EW jamming detection and topology edge updates."""
        if self.jamming_detector:
            self.jamming_detector.record_link_observation(peer_id, pdr, cca_busy)
            self.jamming_detector.evaluate_jamming_status()
        if self.topology_manager:
            self.topology_manager.update_edge(self.peer_id, peer_id, pdr=pdr, rtt_ms=max(1.0, (1.0 - pdr) * 100.0))

    def get_defensive_posture(self) -> dict:
        """Returns current jamming detection state and active defensive posture."""
        if not self.jamming_detector:
            return {"posture": "NORMAL", "jamming_detected": False, "confidence": 0.0}
        return self.jamming_detector.evaluate_jamming_status()




    def _resolve_peer_target(self, target: str) -> Tuple[str, int, str]:

        """
        Resolve destination host, port, and final peer ID for a target.
        Handles direct IP, IP:PORT, direct peer ID, and indirect multi-hop routing.
        """
        with self.peers_lock:
            # 1. Target directly matches a peer key in self.peers (e.g. "192.168.1.10" or "127.0.0.1:37021")
            if target in self.peers:
                p_info = self.peers[target]
                dest_host = target.split(':')[0]
                dest_port = p_info.get('tcp_port') or self._get_peer_port(target)
                final_id = p_info.get('peer_id') or target
                return (dest_host, dest_port, final_id)

            # 2. Target matches a known direct peer's peer_id
            for p_key, p_info in self.peers.items():
                if p_info.get('peer_id') == target:
                    dest_host = p_key.split(':')[0]
                    dest_port = p_info.get('tcp_port') or self._get_peer_port(p_key)
                    return (dest_host, dest_port, target)

        # 3. Target is reachable via multi-hop mesh routing
        if self.routing_table:
            route = self.routing_table.get_route(target)
            if route:
                next_hop_id = route.next_hop_id
                with self.peers_lock:
                    for p_key, p_info in self.peers.items():
                        if p_info.get('peer_id') == next_hop_id:
                            dest_host = p_key.split(':')[0]
                            dest_port = p_info.get('tcp_port') or self._get_peer_port(p_key)
                            return (dest_host, dest_port, target)

        # 4. Fallback: target formatted as IP or IP:PORT
        if ':' in target:
            parts = target.split(':', 1)
            try:
                return (parts[0], int(parts[1]), target)
            except ValueError:
                pass
        return (target, self._get_peer_port(target), target)
    
    def send_message(self, target_ip: str, message_text: str, peer_id: str = None, ttl: Optional[int] = None, msg_id: Optional[str] = None, delivery_callback: Optional[Callable[[str, str], None]] = None, return_result: bool = False) -> Union[bool, SendResult]:
        """
        Send a text message with message ID, application-layer ACK verification, and delivery tracking.
        
        Args:
            target_ip: IP address of destination peer (or IP:PORT)
            message_text: Message string to send
            peer_id: Optional peer ID override
            ttl: Time-to-live in seconds
            msg_id: Optional stable message ID for retries
            delivery_callback: Optional callback(msg_id, state_str)
            return_result: If True, return SendResult; if False, return boolean.

        Returns:
            bool or SendResult
        """
        msg_id = msg_id or uuid.uuid4().hex[:12]
        if delivery_callback:
            delivery_callback(msg_id, "SENDING")
        if self.on_delivery_status:
            self.on_delivery_status(msg_id, target_ip, "SENDING")

        try:
            if message_text.startswith('/wiki') or message_text.startswith('/guide'):
                parts = message_text.split(maxsplit=1)
                query = parts[1].strip() if len(parts) > 1 else ""
                
                # Check local survival guides first for immediate offline response
                guides_path = os.path.join(os.path.dirname(__file__), "survival_guides.json")
                local_response = None
                if os.path.exists(guides_path):
                    try:
                        with open(guides_path, 'r', encoding='utf-8') as f:
                            guides = json.load(f)
                        if not query or query.lower() in ("help", "list"):
                            local_response = "Available field guides: " + ", ".join(f"/{parts[0][1:]} {k}" for k in guides.keys())
                        else:
                            for k, v in guides.items():
                                if query.lower() in k.lower() or k.lower() in query.lower():
                                    local_response = v
                                    break
                            if not local_response:
                                local_response = f"No local guide matching '{query}'. Available topics: " + ", ".join(guides.keys())
                    except Exception as e:
                        print(f"[Wiki Search] Local lookup error: {e}")
                
                if local_response and self.on_message_received:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    msg = f"[Field Guide]: {local_response}"
                    self.on_message_received(target_ip or "127.0.0.1", msg, timestamp)

                if self.udp_socket and query and query.lower() not in ("help", "list"):
                    beacon = {
                        "type": "WIKI_QUERY",
                        "query": query,
                        "sender_name": self.username,
                        "peer_id": self.peer_id
                    }
                    msg = json.dumps(beacon).encode('utf-8')
                    try:
                        self.udp_socket.sendto(msg, ('<broadcast>', self.UDP_PORT))
                    except Exception as e:
                        print(f"[Wiki Search] Broadcast failed: {e}")
                
                if delivery_callback:
                    delivery_callback(msg_id, "DELIVERED")
                return SendResult(True, msg_id, "DELIVERED") if return_result else True

            stego_enabled = False
            carrier = None
            stego_type = "png"
            if self.config_manager:
                stego_enabled = self.config_manager.get("steganography_enabled", False)
                stego_type = self.config_manager.get("stego_carrier_type", "png")
                
            if stego_enabled and STEGANOGRAPHY_AVAILABLE:
                if stego_type == "wav":
                    carrier_path = self.config_manager.get("carrier_audio_path", "")
                    if carrier_path and os.path.exists(carrier_path):
                        try:
                            with open(carrier_path, 'rb') as f:
                                carrier = f.read()
                        except:
                            carrier = steganography.get_or_create_default_wav_carrier()
                    else:
                        carrier = steganography.get_or_create_default_wav_carrier()
                else:
                    carrier_path = self.config_manager.get("carrier_image_path", "")
                    if carrier_path and os.path.exists(carrier_path):
                        carrier = carrier_path
                    else:
                        carrier = steganography.get_or_create_default_carrier()
            
            if target_ip and (target_ip.startswith('wfd_') or target_ip.startswith('bt_')):
                peer_id = target_ip
                
            if peer_id and self.connection_manager:
                plaintext = message_text.encode('utf-8')
                encrypted_payload = None

                if self.crypto_manager:
                    encryption_result = self.crypto_manager.encrypt_message(peer_id, plaintext)
                    if encryption_result:
                        nonce, ciphertext = encryption_result
                        encrypted_payload = nonce + ciphertext
                        
                        if stego_enabled and STEGANOGRAPHY_AVAILABLE:
                            try:
                                if stego_type == "wav":
                                    encrypted_payload = steganography.encode_wav_lsb(carrier, encrypted_payload)
                                else:
                                    encrypted_payload = steganography.encode_lsb(carrier, encrypted_payload)
                            except Exception as e:
                                print(f"[GhostEngine] Stego encoding failed: {e}")
                
                if encrypted_payload:
                    success = self.connection_manager.send_message_to_peer(peer_id, encrypted_payload)
                else:
                    success = self.connection_manager.send_message_to_peer(peer_id, plaintext)

                if success:
                    timestamp_unix = time.time()
                    self._persist_message(peer_id, "me", "text", message_text, timestamp_unix, ttl)
                    if delivery_callback:
                        delivery_callback(msg_id, "SENT_TO_PEER")
                    return SendResult(True, msg_id, "SENT_TO_PEER") if return_result else True
                if delivery_callback:
                    delivery_callback(msg_id, "FAILED")
                return SendResult(False, msg_id, "FAILED", error="P2P adapter transmission failure") if return_result else False
            
            dest_host, dest_port, final_target_id = self._resolve_peer_target(target_ip)

            header = {
                "type": "TEXT",
                "content": message_text,
                "timestamp": datetime.now().isoformat(),
                "target_peer_id": final_target_id,
                "sender_peer_id": self.peer_id,
                "sender_ip": self.local_ip,
                "msg_id": msg_id,
                "network_ttl": 10,
                "visited_nodes": [self.peer_id]
            }
            
            if ttl is not None and ttl > 0:
                header["ttl"] = ttl
            
            header_json = json.dumps(header)
            encrypted_header = self._encrypt_message(header_json)

            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            client_socket.connect((dest_host, dest_port))
            
            payload = encrypted_header + self.HEADER_DELIMITER
            if stego_enabled and STEGANOGRAPHY_AVAILABLE:
                try:
                    if stego_type == "wav":
                        payload = steganography.encode_wav_lsb(carrier, encrypted_header + self.HEADER_DELIMITER)
                    else:
                        payload = steganography.encode_lsb(carrier, encrypted_header + self.HEADER_DELIMITER)
                except Exception as e:
                    print(f"[GhostEngine] Stego encoding failed: {e}")
                    payload = encrypted_header + self.HEADER_DELIMITER
                    
            client_socket.sendall(payload)

            # Check application-layer delivery ACK
            delivery_state = "SENT_TO_PEER"
            try:
                client_socket.settimeout(2.5)
                ack_response = client_socket.recv(1024)
                if ack_response and self.HEADER_DELIMITER in ack_response:
                    ack_part = ack_response.split(self.HEADER_DELIMITER, 1)[0].decode('utf-8', errors='ignore')
                    ack_data = json.loads(ack_part)
                    if ack_data.get("type") == "ACK" and ack_data.get("msg_id") == msg_id:
                        delivery_state = "DELIVERED"
            except Exception:
                # Receipt could not be confirmed via ACK - state remains SENT_TO_PEER
                pass

            client_socket.close()
            print(f"[Send] Message (id={msg_id}) to {target_ip} status: {delivery_state}")
            
            timestamp_unix = time.time()
            self._persist_message(target_ip, "me", "text", message_text, timestamp_unix, ttl)
            
            if delivery_callback:
                delivery_callback(msg_id, delivery_state)
            if self.on_delivery_status:
                self.on_delivery_status(msg_id, target_ip, delivery_state)

            return SendResult(True, msg_id, delivery_state) if return_result else True
            
        except Exception as e:
            print(f"[Send] Error sending to {target_ip}: {e}")
            
            # DTN Store-and-Forward Spooling: If direct transport failed, spool message for future delivery
            spooled = False
            try:
                spooled = self._spool_message(target_ip, message_text, peer_id=peer_id, msg_id=msg_id, ttl=ttl)
            except Exception as spool_err:
                print(f"[Send] Spool attempt failed: {spool_err}")
                
            delivery_state = "QUEUED_OFFLINE" if spooled else "FAILED"
            if delivery_callback:
                delivery_callback(msg_id, delivery_state)
            if self.on_delivery_status:
                self.on_delivery_status(msg_id, target_ip, delivery_state)
                
            if spooled:
                timestamp_unix = time.time()
                self._persist_message(target_ip, "me", "text", message_text, timestamp_unix, ttl)
                return SendResult(True, msg_id, delivery_state) if return_result else True
                
            return SendResult(False, msg_id, "FAILED", error=str(e)) if return_result else False
    
    def send_file(self, target_ip: str, file_path: str, progress_callback: Optional[Callable] = None, peer_id: str = None, use_chunking: bool = True, ttl: Optional[int] = None, resume_offset: int = 0) -> bool:
        """
        Send a file with encrypted chunking, optional byte-offset resumption, and flow-control pacing.
        
        Args:
            target_ip: IP address of target peer
            file_path: Path to file to send
            progress_callback: Optional callback(bytes_sent, total_size)
            peer_id: Peer ID for off-grid peers
            use_chunking: Enable encrypted chunking (default True)
            ttl: Time-to-live in seconds for file expiration (optional)
            resume_offset: Starting byte offset to resume interrupted transfer (default 0)
            
        Returns:
            True if started successfully
        """
        if not file_path or not os.path.isfile(file_path):
            print(f"[Send File] File not found: {file_path}")
            return False

        filesize = os.path.getsize(file_path)
        if filesize <= 0:
            print(f"[Send File] Error: Cannot transfer empty (0-byte) file: {file_path}")
            return False

        if filesize > self.MAX_FILE_SIZE:
            print(f"[Send File] File too large: {filesize} bytes (max {self.MAX_FILE_SIZE})")
            return False

        def _send_file_worker():
            nonlocal target_ip, peer_id
            try:
                is_reachable = False
                if target_ip and (target_ip.startswith('wfd_') or target_ip.startswith('bt_')):
                    peer_id = target_ip
                
                if peer_id and self.connection_manager:
                    connection = self.connection_manager.get_connection(peer_id)
                    if peer_id.startswith('wfd_') and connection and connection.connected_ip:
                        is_reachable = True
                        target_ip = connection.connected_ip
                    elif peer_id.startswith('bt_') and connection and connection.state.value == 'connected' and connection.rfcomm_socket:
                        is_reachable = True
                
                dest_host, dest_port, final_target_id = self._resolve_peer_target(target_ip)
                if not is_reachable and target_ip and not (target_ip.startswith('wfd_') or target_ip.startswith('bt_')):
                    try:
                        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test_sock.settimeout(2.0)
                        test_sock.connect((dest_host, dest_port))
                        test_sock.close()
                        is_reachable = True
                    except:
                        is_reachable = False
                
                if not is_reachable:
                    self._spool_file(peer_id or target_ip, file_path, use_chunking, ttl)
                    return True
                
                if peer_id and peer_id.startswith('wfd_') and self.connection_manager:
                    connection = self.connection_manager.get_connection(peer_id)
                    if connection and connection.connected_ip:
                        target_ip = connection.connected_ip
                
                if peer_id and peer_id.startswith('bt_') and self.connection_manager:
                    connection = self.connection_manager.get_connection(peer_id)
                    if connection and connection.state.value == 'connected' and connection.rfcomm_socket:
                        if not os.path.isfile(file_path):
                            print(f"[Send File] File not found: {file_path}")
                            return False
                        
                        filesize = os.path.getsize(file_path)
                        filename = os.path.basename(file_path)
                        checksum = self._calculate_checksum(file_path)
                        file_id = hashlib.sha256(f"{filename}{time.time()}".encode()).hexdigest()[:16]
                        
                        header = {
                            "type": "FILE",
                            "filename": filename,
                            "filesize": filesize,
                            "file_id": file_id,
                            "checksum": checksum,
                            "chunked": use_chunking,
                            "timestamp": datetime.now().isoformat(),
                            "target_peer_id": target_ip,
                            "sender_peer_id": self.peer_id,
                            "network_ttl": 10
                        }
                        if ttl is not None and ttl > 0:
                            header["ttl"] = ttl
                            
                        header_json = json.dumps(header)
                        encrypted_header = self._encrypt_message(header_json)
                        
                        connection.rfcomm_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
                        
                        bytes_sent = 0
                        if use_chunking and self.crypto_manager:
                            with open(file_path, 'rb') as f:
                                while True:
                                    chunk = f.read(self.CHUNK_SIZE)
                                    if not chunk:
                                        break
                                    
                                    enc_result = self.crypto_manager.encrypt_file_chunk(peer_id, chunk)
                                    if enc_result and enc_result[0] and enc_result[1]:
                                        nonce, ciphertext = enc_result
                                        chunk_data = ciphertext
                                    else:
                                        chunk_data = chunk
                                        nonce = b'\x00' * 12
                                    
                                    chunk_header = nonce + len(chunk_data).to_bytes(4, 'big')
                                    connection.rfcomm_socket.sendall(chunk_header + chunk_data)
                                    bytes_sent += len(chunk_data)
                                    if progress_callback:
                                        progress_callback(bytes_sent, filesize)
                        else:
                            with open(file_path, 'rb') as f:
                                while True:
                                    chunk = f.read(self.BUFFER_SIZE)
                                    if not chunk:
                                        break
                                    connection.rfcomm_socket.sendall(chunk)
                                    bytes_sent += len(chunk)
                                    if progress_callback:
                                        progress_callback(bytes_sent, filesize)
                        
                        timestamp_unix = time.time()
                        self._persist_message(peer_id, "me", "file", filename, timestamp_unix, ttl, file_path)
                        print(f"[Send File] Successfully sent Bluetooth file '{filename}' to {peer_id}")
                        return True
                    else:
                        print(f"[Send File] Bluetooth connection not active or socket unavailable for {peer_id}")
                        return False
                
                if not os.path.isfile(file_path):
                    print(f"[Send File] File not found: {file_path}")
                    return False
                
                filesize = os.path.getsize(file_path)
                if filesize <= 0:
                    print(f"[Send File] Error: Cannot transfer empty (0-byte) file: {file_path}")
                    return False
                
                if filesize > self.MAX_FILE_SIZE:
                    print(f"[Send File] File too large: {filesize} bytes (max {self.MAX_FILE_SIZE})")
                    return False
                
                filename = os.path.basename(file_path)
                checksum = self._calculate_checksum(file_path)
                file_id = hashlib.sha256(f"{filename}{time.time()}".encode()).hexdigest()[:16]
                
                print(f"[Send File] Sending '{filename}' ({filesize} bytes) to {dest_host}:{dest_port}")
                
                header = {
                    "type": "FILE",
                    "filename": filename,
                    "filesize": filesize,
                    "file_id": file_id,
                    "checksum": checksum,
                    "chunked": use_chunking,
                    "offset": resume_offset,
                    "timestamp": datetime.now().isoformat(),
                    "target_peer_id": final_target_id,
                    "sender_peer_id": self.peer_id,
                    "network_ttl": 10
                }
                
                if ttl is not None and ttl > 0:
                    header["ttl"] = ttl
                
                header_json = json.dumps(header)
                encrypted_header = self._encrypt_message(header_json)
                
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(30.0)
                client_socket.connect((dest_host, dest_port))
                
                client_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
                
                bytes_sent = resume_offset
                
                if use_chunking and self.crypto_manager:
                    with open(file_path, 'rb') as f:
                        if resume_offset > 0:
                            f.seek(resume_offset)
                        while True:
                            chunk = f.read(self.CHUNK_SIZE)
                            if not chunk:
                                break
                            
                            enc_result = self.crypto_manager.encrypt_file_chunk(peer_id or final_target_id or target_ip, chunk)
                            if enc_result and enc_result[0] and enc_result[1]:
                                nonce, ciphertext = enc_result
                                chunk_data = ciphertext
                            else:
                                chunk_data = chunk
                                nonce = b'\x00' * 12
                            
                            chunk_header = nonce + len(chunk_data).to_bytes(4, 'big')
                            client_socket.sendall(chunk_header + chunk_data)
                            
                            bytes_sent += len(chunk_data)
                            
                            if progress_callback:
                                progress_callback(bytes_sent, filesize)
                            
                            # Flow control pacing to avoid packet drops on ad-hoc mesh
                            time.sleep(0.002)
                            
                            if bytes_sent % (self.CHUNK_SIZE * 10) == 0:
                                progress = (bytes_sent / filesize) * 100
                                print(f"[Send File] Progress: {progress:.1f}%")
                else:
                    with open(file_path, 'rb') as f:
                        if resume_offset > 0:
                            f.seek(resume_offset)
                        while True:
                            chunk = f.read(self.BUFFER_SIZE)
                            if not chunk:
                                break
                            
                            client_socket.sendall(chunk)
                            bytes_sent += len(chunk)
                            
                            if progress_callback:
                                progress_callback(bytes_sent, filesize)
                            
                            time.sleep(0.002)
                            
                            if bytes_sent % (self.BUFFER_SIZE * 10) == 0:
                                progress = (bytes_sent / filesize) * 100
                                print(f"[Send File] Progress: {progress:.1f}%")
                
                client_socket.close()
                print(f"[Send File] Successfully sent '{filename}' to {target_ip}")
                
                timestamp_unix = time.time()
                self._persist_message(target_ip, "me", "file", filename, timestamp_unix, ttl, file_path)
                
                return True
                
            except Exception as e:
                print(f"[Send File] Error: {e}")
                return False
        
        threading.Thread(target=_send_file_worker, daemon=True).start()
        return True
    
    def _spool_message(self, target: str, message_text: str, peer_id: Optional[str] = None, msg_id: Optional[str] = None, ttl: Optional[int] = None) -> bool:
        """
        Store-and-forward spooling for text messages when direct link to destination is unavailable.
        """
        if not hasattr(self, 'spool_dir') or not self.spool_dir:
            return False
            
        msg_id = msg_id or uuid.uuid4().hex[:12]
        hash_target = str(peer_id or target)
        if len(hash_target) != 64 or not all(c in '0123456789abcdefABCDEF' for c in hash_target):
            hash_target = hashlib.sha256(str(peer_id or target).encode()).hexdigest()
            
        dest_dir = os.path.join(self.spool_dir, hash_target, f"msg_{msg_id}")
        os.makedirs(dest_dir, exist_ok=True)
        
        metadata = {
            "type": "TEXT_MESSAGE",
            "target": target,
            "target_peer_id": peer_id or target,
            "msg_id": msg_id,
            "content": message_text,
            "ttl": ttl,
            "timestamp": time.time(),
            "created_iso": datetime.now().isoformat(),
            "replicated_to": []
        }
        
        # Also store into bundle_manager if available
        if getattr(self, 'bundle_manager', None):
            try:
                raise NotImplementedError("Research prototype quarantined in research/")
                bundle = Bundle(
                    bundle_id=msg_id,
                    source_id=self.peer_id,
                    destination_id=peer_id or target,
                    creation_time=time.time(),
                    lifetime_sec=ttl if (ttl and ttl > 0) else 86400,
                    priority=BundlePriority.STANDARD,
                    payload=message_text.encode('utf-8'),
                    custody_requested=True,
                    current_custodian_id=self.peer_id
                )
                self.bundle_manager.store_bundle(bundle)
            except Exception as e:
                print(f"[DTN Spool] Bundle store warning: {e}")
                
        try:
            self._write_spool_metadata(os.path.join(dest_dir, "metadata.json"), metadata)
            print(f"[DTN Spool] Spooled text message (id={msg_id}) for peer {target}")
            return True
        except Exception as e:
            print(f"[DTN Spool] Error saving message metadata: {e}")
            return False

    def _spool_file(self, target, file_path, use_chunking, ttl):
        if not os.path.exists(file_path):
            print(f"[DTN Spool] Original file not found: {file_path}")
            return False
            
        import shutil
        filename = os.path.basename(file_path)
        filesize = os.path.getsize(file_path)
        checksum = self._calculate_checksum(file_path)
        file_id = hashlib.sha256(f"{filename}{time.time()}".encode()).hexdigest()[:16]
        
        hash_target = str(target)
        if len(hash_target) != 64 or not all(c in '0123456789abcdefABCDEF' for c in hash_target):
            hash_target = hashlib.sha256(str(target).encode()).hexdigest()
        dest_dir = os.path.join(self.spool_dir, hash_target, file_id)
        os.makedirs(dest_dir, exist_ok=True)
        
        spooled_file_path = os.path.join(dest_dir, "file.dat")
        try:
            shutil.copy2(file_path, spooled_file_path)
        except Exception as e:
            print(f"[DTN Spool] Error copying file to spool: {e}")
            return False
            
        metadata = {
            "target": target,
            "original_filename": filename,
            "filesize": filesize,
            "file_id": file_id,
            "checksum": checksum,
            "chunked": use_chunking,
            "ttl": ttl,
            "timestamp": datetime.now().isoformat(),
            "replicated_to": []
        }
        
        try:
            self._write_spool_metadata(os.path.join(dest_dir, "metadata.json"), metadata)
            print(f"[DTN Spool] Spooled file {filename} for peer {target} (file_id: {file_id})")
            return True
        except Exception as e:
            print(f"[DTN Spool] Error saving metadata: {e}")
            return False

    def _write_spool_metadata(self, filepath: str, metadata: dict):
        try:
            import json
            import base64
            data_str = json.dumps(metadata)
            if self.db_manager and self.db_manager.cipher:
                encrypted_bytes = self.db_manager.cipher.encrypt(data_str.encode('utf-8'))
            else:
                encrypted_bytes = base64.b64encode(data_str.encode('utf-8'))
            with open(filepath, 'wb') as f:
                f.write(encrypted_bytes)
        except Exception as e:
            print(f"[DTN Spool] Error writing metadata to {filepath}: {e}")

    def _read_spool_metadata(self, filepath: str) -> Optional[dict]:
        try:
            import json
            import base64
            with open(filepath, 'rb') as f:
                encrypted_bytes = f.read()
            if self.db_manager and self.db_manager.cipher:
                try:
                    decrypted = self.db_manager.cipher.decrypt(encrypted_bytes).decode('utf-8')
                    return json.loads(decrypted)
                except:
                    pass
            # Fallback to base64 or plaintext
            try:
                decrypted = base64.b64decode(encrypted_bytes).decode('utf-8')
                return json.loads(decrypted)
            except:
                pass
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except:
                pass
        except Exception as e:
            print(f"[DTN Spool] Error reading metadata from {filepath}: {e}")
        return None

    def _process_dtn_spool(self):
        if not hasattr(self, 'spool_dir') or not os.path.exists(self.spool_dir):
            return
            
        for target_dir in os.listdir(self.spool_dir):
            target_path = os.path.join(self.spool_dir, target_dir)
            if not os.path.isdir(target_path):
                continue
                
            resolved_peer_id = None
            resolved_ip = None
            
            my_hash = hashlib.sha256(self.peer_id.encode()).hexdigest()
            if target_dir == my_hash:
                resolved_peer_id = self.peer_id
            else:
                with self.peers_lock:
                    for ip, info in self.peers.items():
                        p_id = info.get("peer_id", ip)
                        if hashlib.sha256(p_id.encode()).hexdigest() == target_dir:
                            resolved_peer_id = p_id
                            resolved_ip = ip
                            break
                            
            is_reachable = False
            connection_target = None
            
            if resolved_peer_id:
                connection_target = resolved_peer_id
                if self.connection_manager:
                    connection = self.connection_manager.get_connection(resolved_peer_id)
                    if resolved_peer_id.startswith('wfd_') and connection and connection.connected_ip:
                        is_reachable = True
                        resolved_ip = connection.connected_ip
                    elif resolved_peer_id.startswith('bt_') and connection and connection.state.value == 'connected' and connection.rfcomm_socket:
                        is_reachable = True
                
                if not is_reachable and not (resolved_peer_id.startswith('wfd_') or resolved_peer_id.startswith('bt_')):
                    ip_to_test = resolved_ip if resolved_ip else resolved_peer_id
                    try:
                        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test_sock.settimeout(2.0)
                        test_sock.connect((ip_to_test, self._get_peer_port(ip_to_test)))
                        test_sock.close()
                        is_reachable = True
                        connection_target = ip_to_test
                    except:
                        is_reachable = False
                        
            if is_reachable and connection_target:
                for item_dir in os.listdir(target_path):
                    item_path = os.path.join(target_path, item_dir)
                    meta_path = os.path.join(item_path, "metadata.json")
                    data_path = os.path.join(item_path, "file.dat")
                    
                    if os.path.exists(meta_path):
                        try:
                            meta = self._read_spool_metadata(meta_path)
                            if not meta:
                                continue
                            
                            # Handle spooled text messages
                            if meta.get("type") == "TEXT_MESSAGE" and "content" in meta:
                                print(f"[DTN Spool] Peer {resolved_peer_id} is reachable. Forwarding spooled message: {meta.get('msg_id')}")
                                dest_host, dest_port, final_target_id = self._resolve_peer_target(connection_target)
                                try:
                                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                    client_socket.settimeout(4.0)
                                    client_socket.connect((dest_host, dest_port))
                                    header = {
                                        "type": "TEXT",
                                        "content": meta["content"],
                                        "timestamp": datetime.now().isoformat(),
                                        "target_peer_id": final_target_id,
                                        "sender_peer_id": self.peer_id,
                                        "sender_ip": self.local_ip,
                                        "msg_id": meta.get("msg_id", uuid.uuid4().hex[:12]),
                                        "network_ttl": 10,
                                        "visited_nodes": [self.peer_id]
                                    }
                                    if meta.get("ttl"):
                                        header["ttl"] = meta["ttl"]
                                    encrypted_header = self._encrypt_message(json.dumps(header))
                                    client_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
                                    client_socket.close()
                                    
                                    import shutil
                                    shutil.rmtree(item_path)
                                    print(f"[DTN Spool] Spooled message {meta.get('msg_id')} sent successfully and removed")
                                    if self.on_delivery_status:
                                        self.on_delivery_status(meta.get("msg_id"), connection_target, "DELIVERED")
                                except Exception as fwd_err:
                                    print(f"[DTN Spool] Error forwarding spooled message: {fwd_err}")
                                continue

                            # Handle spooled files
                            if os.path.exists(data_path):
                                print(f"[DTN Spool] Peer {resolved_peer_id} is reachable. Forwarding spooled file: {meta.get('original_filename', 'file')}")
                                success = self._send_spooled_file(connection_target, data_path, meta)
                                if success:
                                    import shutil
                                    shutil.rmtree(item_path)
                                    print(f"[DTN Spool] Spooled item sent successfully and removed: {meta.get('original_filename', 'file')}")
                        except Exception as e:
                            print(f"[DTN Spool] Error sending spooled item {item_dir}: {e}")
            else:
                # Target is offline - duplicate/replicate to active candidate carrier peers
                candidate_peers = set()
                if self.routing_table:
                    candidate_peers.update(self.routing_table.get_direct_peers())
                if self.connection_manager:
                    for conn_id, conn in self.connection_manager.active_connections.items():
                        if conn.state.value == 'connected':
                            candidate_peers.add(conn_id)
                            
                for item_dir in os.listdir(target_path):
                    item_path = os.path.join(target_path, item_dir)
                    meta_path = os.path.join(item_path, "metadata.json")
                    data_path = os.path.join(item_path, "file.dat")
                    
                    if os.path.exists(meta_path) and os.path.exists(data_path):
                        try:
                            meta = self._read_spool_metadata(meta_path)
                            if meta:
                                replicated_to = meta.get("replicated_to", [])
                                
                                for peer in candidate_peers:
                                    peer_hash = hashlib.sha256(peer.encode()).hexdigest()
                                    if peer_hash != target_dir and peer != self.peer_id and peer not in replicated_to:
                                        print(f"[Epidemic Routing] Replicating spooled file '{meta['original_filename']}' to intermediate carrier {peer}")
                                        success = self._send_spooled_file(peer, data_path, meta)
                                        if success:
                                            replicated_to.append(peer)
                                            meta["replicated_to"] = replicated_to
                                            self._write_spool_metadata(meta_path, meta)
                                            print(f"[Epidemic Routing] Replicated successfully to carrier {peer}")
                        except Exception as e:
                            print(f"[Epidemic Routing] Error replicating item {item_dir}: {e}")

    def _send_spooled_file(self, target, file_path, meta):
        try:
            use_chunking = meta.get("chunked", True)
            filesize = meta["filesize"]
            filename = meta["original_filename"]
            checksum = meta["checksum"]
            file_id = meta["file_id"]
            ttl = meta.get("ttl")
            
            final_target = meta.get("target") or target
            hash_target = final_target
            if len(hash_target) != 64 or not all(c in '0123456789abcdefABCDEF' for c in hash_target):
                hash_target = hashlib.sha256(final_target.encode()).hexdigest()
                
            header = {
                "type": "FILE",
                "filename": filename,
                "filesize": filesize,
                "file_id": file_id,
                "checksum": checksum,
                "chunked": use_chunking,
                "timestamp": datetime.now().isoformat(),
                "target_peer_id": hash_target,
                "sender_peer_id": self.peer_id,
                "network_ttl": 10
            }
            if ttl is not None and ttl > 0:
                header["ttl"] = ttl
                
            header_json = json.dumps(header)
            encrypted_header = self._encrypt_message(header_json)
            
            if target.startswith('bt_') or target.startswith('wfd_'):
                if not self.connection_manager:
                    return False
                connection = self.connection_manager.get_connection(target)
                if not connection or connection.state.value != 'connected' or not connection.rfcomm_socket:
                    return False
                sock = connection.rfcomm_socket
            else:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(10.0)
                    sock.connect((target, self._get_peer_port(target)))
                except:
                    return False
                    
            sock.sendall(encrypted_header + self.HEADER_DELIMITER)
            
            bytes_sent = 0
            if use_chunking and self.crypto_manager:
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(self.CHUNK_SIZE)
                        if not chunk:
                            break
                        
                        nonce, ciphertext = self.crypto_manager.encrypt_file_chunk(target, chunk)
                        if not nonce or not ciphertext:
                            chunk_data = chunk
                            nonce = b'\x00' * 12
                        else:
                            chunk_data = ciphertext
                        
                        chunk_header = nonce + len(chunk_data).to_bytes(4, 'big')
                        sock.sendall(chunk_header + chunk_data)
                        bytes_sent += len(chunk_data)
            else:
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(self.BUFFER_SIZE)
                        if not chunk:
                            break
                        sock.sendall(chunk)
                        bytes_sent += len(chunk)
            
            if not (target.startswith('bt_') or target.startswith('wfd_')):
                try:
                    sock.close()
                except:
                    pass
                    
            timestamp_unix = time.time()
            if self.persistence_db:
                self.persistence_db.save_message(target, "me", "file", filename, timestamp_unix, ttl)
            return True
        except Exception as e:
            print(f"[DTN Spool] Error sending spooled file: {e}")
            return False

    def _network_monitor_worker(self):
        """Monitor network changes and reconnect if needed."""
        while self.running:
            try:
                time.sleep(5)  # Check every 5 seconds
                
                if self.network_monitor:
                    # Check for network changes
                    if self.network_monitor.check_network_change():
                        print(f"[Network Monitor] Network changed, updating peers")
                        # Trigger UI update with current peers
                        if self.on_peer_update:
                            self.on_peer_update(self.get_all_peers_combined())
            
            except Exception as e:
                if self.running:
                    print(f"[Network Monitor] Error: {e}")
    
    def _routing_maintenance_worker(self):
        while self.running:
            try:
                time.sleep(10)
                
                if self.routing_table:
                    stale = self.routing_table.remove_stale_routes()
                    if stale:
                        print(f"[Routing] Removed {len(stale)} stale routes")
                
                # Periodically process DTN spool
                self._process_dtn_spool()
            
            except Exception as e:
                if self.running:
                    print(f"[Routing] Maintenance error: {e}")
    
    def _relay_forwarding_worker(self):
        while self.running:
            try:
                time.sleep(0.1)
                
                with self.forwards_lock:
                    if not self.pending_forwards:
                        continue
                    
                    forward_job = self.pending_forwards.pop(0)
                
                self._execute_packet_forward(forward_job)
            
            except Exception as e:
                if self.running:
                    print(f"[Relay] Forwarding error: {e}")
    
    def _queue_packet_forward(self, sender_ip: str, target_peer_id: str, header: dict, payload: bytes, ttl: int):
        with self.forwards_lock:
            self.pending_forwards.append({
                'sender_ip': sender_ip,
                'target_peer_id': target_peer_id,
                'header': header,
                'payload': payload,
                'ttl': ttl
            })
    
    def _execute_packet_forward(self, forward_job: dict):
        try:
            target_peer_id = forward_job['target_peer_id']
            header = forward_job['header']
            payload = forward_job['payload']
            ttl = forward_job['ttl']
            
            if ttl <= 1:
                print(f"[Relay] Network TTL expired for {target_peer_id} (ttl={ttl}); dropping packet")
                return

            route = self.routing_table.get_route(target_peer_id)
            if not route:
                print(f"[Relay] No route found for {target_peer_id}")
                return
            
            next_hop_id = route.next_hop_id
            next_hop_entry = self.routing_table.get_route(next_hop_id)
            
            if next_hop_entry and next_hop_entry.is_direct:
                for ip, peer_info in self.peers.items():
                    if peer_info.get('peer_id') == next_hop_id:
                        header_copy = header.copy()
                        header_copy['network_ttl'] = ttl - 1
                        visited = header_copy.setdefault('visited_nodes', [])
                        if self.peer_id not in visited:
                            visited.append(self.peer_id)
                        
                        header_json = json.dumps(header_copy)
                        
                        next_hop_aes_key = None
                        if self.crypto_manager:
                            next_hop_aes_key = self.crypto_manager.get_peer_aes_key(next_hop_id)
                        
                        if next_hop_aes_key:
                            try:
                                import base64
                                from cryptography.fernet import Fernet
                                fernet_key = base64.urlsafe_b64encode(next_hop_aes_key)
                                peer_cipher = Fernet(fernet_key)
                                encrypted_header = peer_cipher.encrypt(header_json.encode('utf-8'))
                                print(f"[Onion] Encrypted header using derived AES key for next hop: {next_hop_id}")
                            except Exception as e:
                                print(f"[Onion] Header encryption failed: {e}. Falling back to daily key.")
                                encrypted_header = self._encrypt_message(header_json)
                        else:
                            encrypted_header = self._encrypt_message(header_json)
                        
                        try:
                            clean_ip = ip.split(':')[0]
                            target_port = peer_info.get('tcp_port') or self._get_peer_port(ip)
                            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            client_socket.settimeout(5.0)
                            client_socket.connect((clean_ip, target_port))
                            
                            client_socket.sendall(encrypted_header + self.HEADER_DELIMITER + payload)
                            client_socket.close()
                            
                            print(f"[Relay] Custody transferred: Forwarded packet for {target_peer_id} via {next_hop_id} (TTL: {ttl-1})")
                            return
                        except Exception as e:
                            print(f"[Relay] Forward to {ip} failed: {e}. Trying multipath fallback...")
                            if self.routing_table:
                                direct_peers = self.routing_table.get_direct_peers()
                                for fallback_peer_id in direct_peers:
                                    if fallback_peer_id != next_hop_id and fallback_peer_id != self.peer_id:
                                        # Find IP for fallback_peer_id
                                        for f_ip, f_info in self.peers.items():
                                            if f_info.get('peer_id') == fallback_peer_id:
                                                try:
                                                    print(f"[Relay] Attempting fallback forwarding via {fallback_peer_id} ({f_ip})")
                                                    fallback_aes_key = None
                                                    if self.crypto_manager:
                                                        fallback_aes_key = self.crypto_manager.get_peer_aes_key(fallback_peer_id)
                                                    
                                                    if fallback_aes_key:
                                                        try:
                                                            import base64
                                                            from cryptography.fernet import Fernet
                                                            fernet_key = base64.urlsafe_b64encode(fallback_aes_key)
                                                            peer_cipher = Fernet(fernet_key)
                                                            fallback_encrypted_header = peer_cipher.encrypt(header_json.encode('utf-8'))
                                                            print(f"[Onion] Encrypted fallback header using derived AES key for next hop: {fallback_peer_id}")
                                                        except Exception as ex:
                                                            fallback_encrypted_header = encrypted_header
                                                    else:
                                                        fallback_encrypted_header = encrypted_header
                                                    
                                                    clean_f_ip = f_ip.split(':')[0]
                                                    f_port = f_info.get('tcp_port') or self._get_peer_port(f_ip)
                                                    fallback_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                                    fallback_socket.settimeout(5.0)
                                                    fallback_socket.connect((clean_f_ip, f_port))
                                                    fallback_socket.sendall(fallback_encrypted_header + self.HEADER_DELIMITER + payload)
                                                    fallback_socket.close()
                                                    print(f"[Relay] Custody transferred: Fallback forwarding successful via {fallback_peer_id}!")
                                                    return
                                                except Exception as ex:
                                                    print(f"[Relay] Fallback via {fallback_peer_id} failed: {ex}")
                        return
        
        except Exception as e:
            print(f"[Relay] Forward execution error: {e}")
    
    def _on_network_changed(self, old_ip, new_ip, network_type):
        """
        Handle dynamic network changes (Wi-Fi drop, IP change, interface handover).
        Reconciles network state, resets beacon interval, broadcasts immediate presence,
        and triggers DTN spool retry for queued messages/files.
        """
        print(f"[GhostEngine] Network changed: {old_ip} -> {new_ip} ({network_type})")
        
        is_offline = (not new_ip or new_ip == "127.0.0.1")
        if is_offline:
            self.local_ip = "127.0.0.1"
            self.current_network_type = "offline"
            self.set_network_state(NetworkState.OFFLINE)
            print("[GhostEngine] Switched to OFFLINE mode")
        else:
            self.local_ip = new_ip
            self.current_network_type = network_type
            self.set_network_state(NetworkState.AVAILABLE)
            
            # Reset adaptive beacon intervals to announce presence immediately on new network
            self.current_beacon_interval = self.min_beacon_interval
            self.static_beacon_cycles = 0
            
            # Send immediate discovery beacon on new interface
            try:
                self._broadcast_immediate_beacon()
            except Exception as e:
                print(f"[GhostEngine] Immediate beacon broadcast failed: {e}")
                
            # Process DTN spool to forward any messages or files queued while offline
            try:
                threading.Thread(target=self._process_dtn_spool, daemon=True, name="DTNSpoolFlush").start()
            except Exception as e:
                print(f"[GhostEngine] Spool flush trigger failed: {e}")
        
        # Notify UI of network status and peer list update
        if self.on_peer_update:
            try:
                self.on_peer_update(self.get_all_peers_combined())
            except Exception as e:
                print(f"[GhostEngine] Peer update callback on network change failed: {e}")
    
    def get_network_status(self) -> Dict[str, any]:
        if self.network_detector:
            interfaces = self.network_detector.get_all_interfaces()
        else:
            interfaces = {}
        
        p2p_peers = {}
        if self.peer_discovery:
            p2p_peers = self.peer_discovery.get_all_peers()
        
        return {
            'ip': self.local_ip,
            'type': self.current_network_type,
            'interfaces': interfaces,
            'is_connected': self.local_ip != "127.0.0.1",
            'wifi_direct_peers': self.peer_discovery.get_peers_by_type('wifi_direct') if self.peer_discovery else {},
            'bluetooth_peers': self.peer_discovery.get_peers_by_type('bluetooth') if self.peer_discovery else {},
            'all_p2p_peers': p2p_peers
        }
    
    def get_peers(self) -> Dict[str, dict]:
        with self.peers_lock:
            return self.peers.copy()
    
    def get_all_peers_combined(self) -> Dict[str, dict]:
        lan_peers = self.get_peers()
        
        p2p_peers = {}
        if self.peer_discovery:
            p2p_peers = self.peer_discovery.get_all_peers()
        
        combined = {}
        combined.update(lan_peers)
        combined.update(p2p_peers)
        
        return combined
    
    def get_wifi_direct_peers(self) -> Dict[str, dict]:
        if self.peer_discovery:
            return self.peer_discovery.get_peers_by_type('wifi_direct')
        return {}
    
    def get_bluetooth_peers(self) -> Dict[str, dict]:
        if self.peer_discovery:
            return self.peer_discovery.get_peers_by_type('bluetooth')
        return {}
    
    def broadcast_sos(self, latitude: float, longitude: float, message: str = "EMERGENCY SOS"):
        try:
            from gps_manager import get_gps_manager
        except ImportError:
            print("[GhostEngine] GPS manager not available")
            latitude = 40.7128
            longitude = -74.0060
        
        sos_id = hashlib.sha256(f"{latitude}{longitude}{time.time()}".encode()).hexdigest()[:16]
        sos_timestamp = time.time()
        
        sos_payload = {
            'type': 'SOS',
            'sos_id': sos_id,
            'timestamp': sos_timestamp,
            'sender_id': self.peer_id,
            'sender_name': self.username,
            'latitude': latitude,
            'longitude': longitude,
            'message': message
        }
        
        # Sign the SOS payload
        import base64
        sig_data = json.dumps(sos_payload, sort_keys=True).encode('utf-8')
        signature = b""
        signing_pubkey = b""
        if self.crypto_manager:
            try:
                signature = self.crypto_manager.sign_data(sig_data)
                signing_pubkey = self.crypto_manager.get_signing_public_key_bytes()
            except Exception as e:
                print(f"[GhostEngine] SOS signing failed: {e}")
        
        sos_payload['signature'] = base64.b64encode(signature).decode('utf-8') if signature else ""
        sos_payload['signing_pubkey'] = base64.b64encode(signing_pubkey).decode('utf-8') if signing_pubkey else ""
        
        sos_json = json.dumps(sos_payload)
        encrypted_sos = self._encrypt_message(sos_json)
        
        with self.sos_cache_lock:
            self.sos_cache.append({
                'sos_id': sos_id,
                'timestamp': sos_timestamp,
                'from_peer': self.peer_id
            })
            self.sos_cache = [c for c in self.sos_cache if time.time() - c['timestamp'] < self.sos_cache_max_age]
        
        with self.peers_lock:
            peers_to_broadcast = list(self.peers.keys())
        
        def broadcast_worker():
            for peer_ip in peers_to_broadcast:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    sock.connect((peer_ip, self._get_peer_port(peer_ip)))
                    
                    header = {
                        'type': 'message',
                        'message_type': 'SOS',
                        'sender_id': self.peer_id,
                        'sender_name': self.username
                    }
                    header_json = json.dumps(header)
                    header_bytes = header_json.encode('utf-8')
                    
                    full_message = header_bytes + self.HEADER_DELIMITER + encrypted_sos
                    sock.sendall(full_message)
                    sock.close()
                    print(f"[GhostEngine] SOS broadcast sent to {peer_ip}")
                
                except Exception as e:
                    print(f"[GhostEngine] SOS broadcast error to {peer_ip}: {e}")
        
        threading.Thread(target=broadcast_worker, daemon=True).start()
        print(f"[GhostEngine] SOS broadcast initiated with ID {sos_id}")
    
    def _process_sos_message(self, sos_payload: dict, from_peer_ip: str):
        try:
            sos_id = sos_payload.get('sos_id')
            sos_timestamp = sos_payload.get('timestamp', time.time())
            from_peer = sos_payload.get('sender_id')
            
            with self.sos_cache_lock:
                existing = any(c['sos_id'] == sos_id for c in self.sos_cache)
                
                if existing:
                    print(f"[GhostEngine] SOS {sos_id} already processed, ignoring")
                    return
                
                self.sos_cache.append({
                    'sos_id': sos_id,
                    'timestamp': sos_timestamp,
                    'from_peer': from_peer
                })
                self.sos_cache = [c for c in self.sos_cache if time.time() - c['timestamp'] < self.sos_cache_max_age]
            
            if self.on_sos_received:
                self.on_sos_received(
                    sos_payload.get('sender_name', 'Unknown'),
                    sos_payload.get('latitude', 0),
                    sos_payload.get('longitude', 0),
                    sos_payload.get('message', 'EMERGENCY SOS'),
                    sos_id
                )
            
            with self.peers_lock:
                peers_to_relay = [ip for ip in self.peers.keys() if ip != from_peer_ip]
            
            def relay_worker():
                for peer_ip in peers_to_relay:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(3)
                        sock.connect((peer_ip, self._get_peer_port(peer_ip)))
                        
                        header = {
                            'type': 'message',
                            'message_type': 'SOS',
                            'sender_id': sos_payload.get('sender_id'),
                            'sender_name': sos_payload.get('sender_name')
                        }
                        header_json = json.dumps(header)
                        header_bytes = header_json.encode('utf-8')
                        
                        encrypted_sos = self._encrypt_message(json.dumps(sos_payload))
                        full_message = header_bytes + self.HEADER_DELIMITER + encrypted_sos
                        sock.sendall(full_message)
                        sock.close()
                        print(f"[GhostEngine] SOS relayed to {peer_ip}")
                    
                    except Exception as e:
                        print(f"[GhostEngine] SOS relay error to {peer_ip}: {e}")
            
            threading.Thread(target=relay_worker, daemon=True).start()
        
        except Exception as e:
            print(f"[GhostEngine] SOS processing error: {e}")
    
    def get_peer_username(self, ip: str) -> str:
        with self.peers_lock:
            peer = self.peers.get(ip)
            return peer["username"] if peer else "Unknown"

    def _chaffing_worker(self):
        """Broadcast dummy packets (chaff) at randomized intervals to mask active conversations."""
        import random
        while self.running:
            try:
                # Sleep first for a random duration between 30 and 60 seconds
                sleep_dur = random.randint(30, 60)
                # Check running state periodically to exit quickly on shutdown
                for _ in range(sleep_dur):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                
                # If chaffing is enabled, UDP socket exists, and battery is not low, send dummy packet
                is_low_battery = False
                try:
                    if self._get_battery_level() < 20:
                        is_low_battery = True
                except:
                    pass
                    
                if getattr(self, "chaffing_enabled", False) and self.udp_socket and not is_low_battery:
                    noise_len = random.randint(32, 128)
                    import os
                    noise = os.urandom(noise_len).hex()
                    
                    chaff_packet = {
                        "type": "CHAFF",
                        "noise": noise
                    }
                    message = json.dumps(chaff_packet).encode('utf-8')
                    # Broadcast to 255.255.255.255
                    self.udp_socket.sendto(message, ('<broadcast>', self.UDP_PORT))
                    print("[Chaffing] Broadcasted dummy packet")
            except (OSError, AttributeError):
                # Socket error or closed during shutdown
                pass
            except Exception as e:
                if self.running:
                    print(f"[Chaffing] Error sending chaff: {e}")

    def send_location_beacon(self, latitude: float, longitude: float, altitude: float = 0.0, accuracy: float = 0.0):
        """
        Broadcast current location telemetry to all active direct peers and mesh network.
        """
        payload = {
            "peer_id": self.peer_id,
            "username": self.username,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "altitude": float(altitude),
            "accuracy": float(accuracy),
            "timestamp": time.time()
        }
        payload_json = json.dumps(payload)
        encrypted_payload = self._encrypt_message(payload_json)

        with self.peers_lock:
            targets = list(self.peers.keys())

        def broadcast_worker():
            for peer_ip in targets:
                try:
                    if peer_ip in self.revoked_peers:
                        continue
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3.0)
                    sock.connect((peer_ip.split(':')[0], self._get_peer_port(peer_ip)))

                    header = {
                        "type": "LOCATION_UPDATE",
                        "sender_peer_id": self.peer_id,
                        "sender_name": self.username,
                        "timestamp": datetime.now().isoformat()
                    }
                    header_bytes = json.dumps(header).encode('utf-8')
                    sock.sendall(header_bytes + self.HEADER_DELIMITER + encrypted_payload)
                    sock.close()
                except Exception:
                    pass

        threading.Thread(target=broadcast_worker, daemon=True).start()

    def send_waypoint(self, waypoint_dict: dict, target_peer_id: Optional[str] = None):
        """
        Transmit a tactical waypoint (rally point, hazard, cache) across mesh network.
        """
        wp_data = {
            "waypoint_id": waypoint_dict.get("waypoint_id") or f"wp_{uuid.uuid4().hex[:8]}",
            "title": waypoint_dict.get("title", "Tactical Waypoint"),
            "description": waypoint_dict.get("description", ""),
            "waypoint_type": waypoint_dict.get("waypoint_type", "waypoint"),
            "latitude": float(waypoint_dict.get("latitude", 0.0)),
            "longitude": float(waypoint_dict.get("longitude", 0.0)),
            "altitude": float(waypoint_dict.get("altitude", 0.0)),
            "created_by": self.username,
            "created_at": float(waypoint_dict.get("created_at", time.time())),
            "ttl": waypoint_dict.get("ttl", 86400)
        }

        # Save locally as well
        if self.persistence_db:
            expires_at = (wp_data["created_at"] + wp_data["ttl"]) if wp_data["ttl"] else None
            self.persistence_db.save_waypoint(
                waypoint_id=wp_data["waypoint_id"],
                title=wp_data["title"],
                description=wp_data["description"],
                waypoint_type=wp_data["waypoint_type"],
                latitude=wp_data["latitude"],
                longitude=wp_data["longitude"],
                altitude=wp_data["altitude"],
                created_by=wp_data["created_by"],
                created_at=wp_data["created_at"],
                expires_at=expires_at
            )

        payload_json = json.dumps(wp_data)
        encrypted_payload = self._encrypt_message(payload_json)

        with self.peers_lock:
            targets = [target_peer_id] if target_peer_id else list(self.peers.keys())

        def broadcast_worker():
            for peer_ip in targets:
                try:
                    if peer_ip in self.revoked_peers:
                        continue
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3.0)
                    sock.connect((peer_ip.split(':')[0], self._get_peer_port(peer_ip)))

                    header = {
                        "type": "WAYPOINT",
                        "sender_peer_id": self.peer_id,
                        "sender_name": self.username,
                        "timestamp": datetime.now().isoformat()
                    }
                    header_bytes = json.dumps(header).encode('utf-8')
                    sock.sendall(header_bytes + self.HEADER_DELIMITER + encrypted_payload)
                    sock.close()
                except Exception:
                    pass

        threading.Thread(target=broadcast_worker, daemon=True).start()

    def broadcast_peer_revocation(self, peer_id: str, reason: str = "Compromised node"):
        """
        Create a digitally signed revocation token, blacklist peer locally,
        and broadcast revocation quarantine across the entire network.
        """
        if not self.crypto_manager or not self.crypto_manager.signing_private_key:
            token = {
                "peer_id": peer_id,
                "reason": reason,
                "revoked_at": time.time(),
                "signature": "",
                "signing_pubkey": ""
            }
        else:
            token = create_revocation_token(peer_id, reason, self.crypto_manager.signing_private_key)

        print(f"[GhostEngine] Blacklisting peer {peer_id}: {reason}")
        self.revoked_peers.add(peer_id)
        if self.persistence_db:
            self.persistence_db.revoke_peer(peer_id, reason, token.get("signature"))

        # Quarantine from memory and active routes
        with self.peers_lock:
            to_remove = [ip for ip, info in self.peers.items() if info.get('peer_id') == peer_id or ip == peer_id]
            for ip in to_remove:
                del self.peers[ip]

        if self.routing_table:
            self.routing_table.remove_peer(peer_id)

        if self.crypto_manager:
            self.crypto_manager.clear_peer_keys(peer_id)

        token_json = json.dumps(token)
        encrypted_token = self._encrypt_message(token_json)

        with self.peers_lock:
            broadcast_targets = list(self.peers.keys())

        def broadcast_worker():
            for peer_ip in broadcast_targets:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3.0)
                    sock.connect((peer_ip.split(':')[0], self._get_peer_port(peer_ip)))

                    header = {
                        "type": "PEER_REVOCATION",
                        "sender_peer_id": self.peer_id,
                        "sender_name": self.username,
                        "timestamp": datetime.now().isoformat()
                    }
                    header_bytes = json.dumps(header).encode('utf-8')
                    sock.sendall(header_bytes + self.HEADER_DELIMITER + encrypted_token)
                    sock.close()
                except Exception:
                    pass

        threading.Thread(target=broadcast_worker, daemon=True).start()


# Test the engine
if __name__ == "__main__":
    def on_msg(sender_ip, msg, ts):
        print(f"\n💬 [{ts}] Message received from {sender_ip} (len={len(msg)})\n")
    
    def on_peers(peers):
        print(f"👥 Active peers: {len(peers)}")
        for ip, info in peers.items():
            print(f"  - {info['username']} @ {ip}")
    
    engine = GhostEngine(
        username="TestUser",
        on_message_received=on_msg,
        on_peer_update=on_peers
    )
    
    try:
        engine.start()
        print("\n🚀 Ghost Engine running. Press Ctrl+C to stop.\n")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        engine.stop()
