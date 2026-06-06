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
from typing import Dict, Callable, Optional
from cryptography.fernet import Fernet
import hashlib
import base64
from pathlib import Path

from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

try:
    from routing import RoutingTable
    ROUTING_AVAILABLE = True
except ImportError:
    ROUTING_AVAILABLE = False
    print("[GhostEngine] Routing module not available - mesh networking disabled")

try:
    from security import CryptoManager
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    print("[GhostEngine] Security module not available")

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
                    self.downloads_dir = os.path.join(os.path.expanduser("~"), ".ghostnet", "downloads")
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
    
    def _encrypt_message(self, message: str) -> bytes:
        """Encrypt a message string."""
        if self.cipher is None:
            print("[GhostEngine] WARNING: Cipher not available, storing unencrypted")
            return message.encode('utf-8')
        
        try:
            return self.cipher.encrypt(message.encode('utf-8'))
        except Exception as e:
            print(f"[GhostEngine] Encryption error: {e}")
            return message.encode('utf-8')
    
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
        
        for thread in [self.beacon_thread, self.listener_thread,
                      self.tcp_server_thread, self.pruning_thread,
                      self.routing_maintenance_thread, self.relay_forwarding_thread,
                      self.chaffing_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        
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

    def _beacon_worker(self):
        """Broadcast beacon packets every BEACON_INTERVAL seconds."""
        while self.running:
            try:
                # Skip if no UDP socket available
                if not self.udp_socket:
                    time.sleep(self.BEACON_INTERVAL)
                    continue
                
                # Get current username from config (supports dynamic updates)
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
                    "tcp_port": self.tcp_port,
                    "timestamp": time.time()
                }
                message = json.dumps(beacon).encode('utf-8')
                
                # Broadcast to 255.255.255.255
                self.udp_socket.sendto(message, ('<broadcast>', self.UDP_PORT))
                # print(f"[Beacon] Broadcasted: {beacon}")
                
            except (OSError, AttributeError):
                # Socket was closed by stop() — suppress error during clean shutdown
                if self.running:
                    print(f"[Beacon] Socket error during shutdown")
            except Exception as e:
                if self.running:
                    print(f"[Beacon] Error broadcasting: {e}")
            
            # Sleep: throttle interval if battery is low (< 20%)
            sleep_interval = self.BEACON_INTERVAL
            try:
                if self._get_battery_level() < 20:
                    sleep_interval = 300  # 5 minutes
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
                
                # Ignore our own beacons
                if sender_ip == self.local_ip:
                    continue
                
                # Rate limit processing: ignore beacons from the same IP if processed less than 1.0 second ago
                current_time = time.time()
                last_processed = self.last_beacon_processed.get(sender_ip, 0.0)
                if current_time - last_processed < 1.0:
                    continue
                self.last_beacon_processed[sender_ip] = current_time
                
                # Parse beacon
                try:
                    beacon = json.loads(data.decode('utf-8', errors='ignore'))
                except Exception:
                    continue
                
                if beacon.get("type") == "CHAFF":
                    continue
                
                if beacon.get("type") == "BEACON":
                    # Enforce MAX_PEERS capacity limit (500)
                    with self.peers_lock:
                        if len(self.peers) >= 500 and sender_ip not in self.peers:
                            continue
                            
                    username = beacon.get("username", "Unknown")
                    current_time = time.time()
                    beacon_peer_id = beacon.get("peer_id", sender_ip)
                    visible_peers = beacon.get("visible_peers", [])[:10]
                    battery_level = beacon.get("battery", 100)
                    
                    tcp_port = beacon.get("tcp_port")
                    sender_timestamp = beacon.get("timestamp")
                    
                    if sender_timestamp is not None:
                        offset = sender_timestamp - current_time
                        with self.peers_lock:
                            self.mesh_offsets[beacon_peer_id] = offset
                        self._update_mesh_time_offset()
                    
                    with self.peers_lock:
                        self.peers[sender_ip] = {
                            "username": username,
                            "last_seen": current_time,
                            "peer_id": beacon_peer_id,
                            "visible_peers": visible_peers,
                            "battery": battery_level,
                            "tcp_port": tcp_port
                        }
                    
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
                    
                    if self.persistence_db:
                        threading.Thread(
                            target=self.persistence_db.save_peer,
                            args=(sender_ip, responder, None, "udp", current_time),
                            daemon=True
                        ).start()
                    
                    if self.db_manager:
                        threading.Thread(
                            target=self.db_manager.save_peer,
                            args=(sender_ip, responder, current_time),
                            daemon=True
                        ).start()
                    
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
                    if is_stego:
                        header["stego"] = True
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"[TCP Handler] Invalid header from {sender_ip}: {e}")
                    return
                
                target_peer_id = header.get("target_peer_id")
                network_ttl = header.get("network_ttl", 10)
                
                if target_peer_id and target_peer_id != self.peer_id and network_ttl > 0 and self.routing_table:
                    route = self.routing_table.get_route(target_peer_id)
                    if route:
                        self._queue_packet_forward(sender_ip, target_peer_id, header, remaining_data, network_ttl)
                        return
                
                if header.get("type") == "TEXT":
                    self._handle_text_message(sender_ip, header, remaining_data, conn)
                elif header.get("type") == "FILE":
                    self._handle_file_transfer(sender_ip, header, remaining_data, conn)
                elif header.get("message_type") == "SOS":
                    self._handle_sos_message(sender_ip, header, remaining_data)
                else:
                    print(f"[TCP Handler] Unknown type: {header.get('type')}")
        
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
        """Handle incoming text message."""
        try:
            message_text = header.get("content", "")
            if header.get("stego"):
                message_text = "[Stego Image Decoded] " + message_text
            timestamp = datetime.now().strftime("%H:%M:%S")
            timestamp_unix = time.time()
            ttl = header.get("ttl")
            
            print(f"[TCP] Message from {sender_ip}: {message_text}")
            
            if self.persistence_db:
                threading.Thread(
                    target=self.persistence_db.save_message,
                    args=(sender_ip, "them", "text", message_text, timestamp_unix, ttl),
                    daemon=True
                ).start()
            
            if self.db_manager:
                threading.Thread(
                    target=self.db_manager.save_message,
                    args=(sender_ip, "PEER", message_text, "TEXT", None, timestamp_unix),
                    daemon=True
                ).start()
            
            if self.on_message_received:
                self.on_message_received(sender_ip, message_text, timestamp)
        
        except Exception as e:
            print(f"[TCP Handler] Text message error: {e}")
    
    def _handle_file_transfer(self, sender_ip: str, header: dict, initial_data: bytes, conn: socket.socket):
        """Handle incoming file transfer with chunk reassembly."""
        try:
            filename = header.get("filename", "unknown_file")
            filesize = header.get("filesize", 0)
            file_id = header.get("file_id", "unknown")
            is_chunked = header.get("chunked", False)
            checksum = header.get("checksum", "")
            ttl = header.get("ttl")
            
            print(f"[File Transfer] Receiving '{filename}' ({filesize} bytes) from {sender_ip}")
            
            if filesize > self.MAX_FILE_SIZE:
                print(f"[File Transfer] File too large: {filesize} bytes (max {self.MAX_FILE_SIZE})")
                return
            
            target_peer_id = header.get("target_peer_id")
            my_hash = hashlib.sha256(self.peer_id.encode()).hexdigest()
            is_target = (target_peer_id == self.peer_id or target_peer_id == my_hash)
            is_carrier = (target_peer_id and not is_target)
            
            if is_carrier:
                hash_target = target_peer_id
                if len(target_peer_id) != 64 or not all(c in '0123456789abcdefABCDEF' for c in target_peer_id):
                    hash_target = hashlib.sha256(target_peer_id.encode()).hexdigest()
                spool_item_dir = os.path.join(self.spool_dir, hash_target, file_id)
                os.makedirs(spool_item_dir, exist_ok=True)
                filepath = os.path.join(spool_item_dir, "file.dat")
            else:
                safe_filename = self._sanitize_filename(filename)
                filepath = os.path.join(self.downloads_dir, safe_filename)
                
                base, ext = os.path.splitext(filepath)
                counter = 1
                while os.path.exists(filepath):
                    filepath = f"{base}_{counter}{ext}"
                    counter += 1
            
            bytes_received = len(initial_data)
            
            if is_chunked:
                self._handle_chunked_file_transfer(filepath, filesize, bytes_received, initial_data, conn, sender_ip, filename, checksum, ttl, is_carrier, header)
            else:
                with open(filepath, 'wb') as f:
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
                
                received_checksum = self._calculate_checksum(filepath)
                if checksum and received_checksum != checksum:
                    print(f"[File Transfer] Checksum mismatch! Expected {checksum}, got {received_checksum}")
                    from security import shred_file
                    shred_file(filepath)
                    return
                
                if is_carrier:
                    metadata = {
                        "target": target_peer_id,
                        "original_filename": filename,
                        "filesize": filesize,
                        "file_id": file_id,
                        "checksum": checksum,
                        "chunked": is_chunked,
                        "ttl": ttl,
                        "timestamp": datetime.now().isoformat(),
                        "replicated_to": [header.get("sender_peer_id", "")]
                    }
                    self._write_spool_metadata(os.path.join(os.path.dirname(filepath), "metadata.json"), metadata)
                    print(f"[Epidemic DTN] Spooled carrier file '{filename}' (file_id: {file_id}) for target {target_peer_id}")
                    return
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                timestamp_unix = time.time()
                print(f"[File Transfer] Successfully received '{filename}' → {filepath}")
                
                if self.persistence_db:
                    threading.Thread(
                        target=self.persistence_db.save_message,
                        args=(sender_ip, "them", "file", filename, timestamp_unix, ttl),
                        daemon=True
                    ).start()
                
                if self.db_manager:
                    threading.Thread(
                        target=self.db_manager.save_message,
                        args=(sender_ip, "PEER", filename, "FILE", filepath, timestamp_unix),
                        daemon=True
                    ).start()
                
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
        """Handle chunked encrypted file transfer with on-the-fly decryption."""
        try:
            with open(filepath, 'wb') as f:
                f.write(initial_data)
                bytes_received = initial_bytes
                
                while bytes_received < filesize:
                    chunk_header = conn.recv(32)
                    if not chunk_header or len(chunk_header) < 32:
                        break
                    
                    nonce = chunk_header[:12]
                    chunk_size_bytes = chunk_header[12:16]
                    chunk_size = int.from_bytes(chunk_size_bytes, 'big')
                    
                    encrypted_chunk = b''
                    while len(encrypted_chunk) < chunk_size:
                        remaining = chunk_size - len(encrypted_chunk)
                        data = conn.recv(min(self.CHUNK_SIZE, remaining))
                        if not data:
                            break
                        encrypted_chunk += data
                    
                    if self.crypto_manager:
                        decrypted = self.crypto_manager.decrypt_file_chunk(sender_ip, nonce, encrypted_chunk)
                        if decrypted:
                            f.write(decrypted)
                    else:
                        f.write(encrypted_chunk)
                    
                    bytes_received += len(encrypted_chunk)
                    progress = (bytes_received / filesize) * 100
                    if bytes_received % (self.CHUNK_SIZE * 10) == 0:
                        print(f"[File Transfer] Progress: {progress:.1f}%")
            
            received_checksum = self._calculate_checksum(filepath)
            if checksum and received_checksum != checksum:
                print(f"[File Transfer] Checksum mismatch! Expected {checksum}, got {received_checksum}")
                from security import shred_file
                shred_file(filepath)
                return
            
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
            print(f"[File Transfer] Successfully received chunked '{filename}' → {filepath}")
            
            if self.persistence_db:
                threading.Thread(
                    target=self.persistence_db.save_message,
                    args=(sender_ip, "them", "file", filename, timestamp_unix, ttl),
                    daemon=True
                ).start()
            
            if self.db_manager:
                threading.Thread(
                    target=self.db_manager.save_message,
                    args=(sender_ip, "PEER", filename, "FILE", filepath, timestamp_unix),
                    daemon=True
                ).start()
            
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
    
    def send_message(self, target_ip: str, message_text: str, peer_id: str = None, ttl: Optional[int] = None) -> bool:
        """
            ttl: Time-to-live in seconds for message expiration (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if message_text.startswith('/wiki '):
                query = message_text[6:].strip()
                if self.udp_socket:
                    beacon = {
                        "type": "WIKI_QUERY",
                        "query": query,
                        "sender_name": self.username,
                        "peer_id": self.peer_id
                    }
                    msg = json.dumps(beacon).encode('utf-8')
                    try:
                        self.udp_socket.sendto(msg, ('<broadcast>', self.UDP_PORT))
                        print(f"[Wiki Search] Broadcasted query for '{query}'")
                        return True
                    except Exception as e:
                        print(f"[Wiki Search] Broadcast failed: {e}")
                return False

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
                    if self.persistence_db:
                        threading.Thread(
                            target=self.persistence_db.save_message,
                            args=(peer_id, "me", "text", message_text, timestamp_unix, ttl),
                            daemon=True
                        ).start()
                    if self.db_manager:
                        threading.Thread(
                            target=self.db_manager.save_message,
                            args=(peer_id, "ME", message_text, "TEXT", None, timestamp_unix),
                            daemon=True
                        ).start()
                    return True
                return False
            
            header = {
                "type": "TEXT",
                "content": message_text,
                "timestamp": datetime.now().isoformat(),
                "target_peer_id": target_ip,
                "network_ttl": 10
            }
            
            if ttl is not None and ttl > 0:
                header["ttl"] = ttl
            
            header_json = json.dumps(header)
            encrypted_header = self._encrypt_message(header_json)
            
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10.0)
            client_socket.connect((target_ip, self._get_peer_port(target_ip)))
            
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
            client_socket.close()
            print(f"[Send] Message sent to {target_ip}")
            
            timestamp_unix = time.time()
            if self.persistence_db:
                threading.Thread(
                    target=self.persistence_db.save_message,
                    args=(target_ip, "me", "text", message_text, timestamp_unix, ttl),
                    daemon=True
                ).start()
            if self.db_manager:
                threading.Thread(
                    target=self.db_manager.save_message,
                    args=(target_ip, "ME", message_text, "TEXT", None, timestamp_unix),
                    daemon=True
                ).start()
            
            return True
            
        except Exception as e:
            print(f"[Send] Error sending to {target_ip}: {e}")
            return False
    
    def send_file(self, target_ip: str, file_path: str, progress_callback: Optional[Callable] = None, peer_id: str = None, use_chunking: bool = True, ttl: Optional[int] = None) -> bool:
        """
        Send a file with encrypted chunking to target peer (background thread).
        
        Args:
            target_ip: IP address of target peer
            file_path: Path to file to send
            progress_callback: Optional callback(bytes_sent, total_size)
            peer_id: Peer ID for off-grid peers
            use_chunking: Enable encrypted chunking (default True)
            ttl: Time-to-live in seconds for file expiration (optional)
            
        Returns:
            True if started successfully
        """
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
                
                if not is_reachable and target_ip and not (target_ip.startswith('wfd_') or target_ip.startswith('bt_')):
                    try:
                        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test_sock.settimeout(2.0)
                        test_sock.connect((target_ip, self._get_peer_port(target_ip)))
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
                                    
                                    nonce, ciphertext = self.crypto_manager.encrypt_file_chunk(peer_id, chunk)
                                    if not nonce or not ciphertext:
                                        chunk_data = chunk
                                        nonce = b'\x00' * 12
                                    else:
                                        chunk_data = ciphertext
                                    
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
                        if self.persistence_db:
                            threading.Thread(
                                target=self.persistence_db.save_message,
                                args=(peer_id, "me", "file", filename, timestamp_unix, ttl),
                                daemon=True
                            ).start()
                        if self.db_manager:
                            threading.Thread(
                                target=self.db_manager.save_message,
                                args=(peer_id, "ME", filename, "FILE", file_path, timestamp_unix),
                                daemon=True
                            ).start()
                        print(f"[Send File] Successfully sent Bluetooth file '{filename}' to {peer_id}")
                        return True
                    else:
                        print(f"[Send File] Bluetooth connection not active or socket unavailable for {peer_id}")
                        return False
                
                if not os.path.isfile(file_path):
                    print(f"[Send File] File not found: {file_path}")
                    return False
                
                filesize = os.path.getsize(file_path)
                
                if filesize > self.MAX_FILE_SIZE:
                    print(f"[Send File] File too large: {filesize} bytes (max {self.MAX_FILE_SIZE})")
                    return False
                
                filename = os.path.basename(file_path)
                checksum = self._calculate_checksum(file_path)
                file_id = hashlib.sha256(f"{filename}{time.time()}".encode()).hexdigest()[:16]
                
                print(f"[Send File] Sending '{filename}' ({filesize} bytes) to {target_ip}")
                
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
                
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(30.0)
                client_socket.connect((target_ip, self._get_peer_port(target_ip)))
                
                client_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
                
                bytes_sent = 0
                
                if use_chunking and self.crypto_manager:
                    with open(file_path, 'rb') as f:
                        while True:
                            chunk = f.read(self.CHUNK_SIZE)
                            if not chunk:
                                break
                            
                            nonce, ciphertext = self.crypto_manager.encrypt_file_chunk(target_ip, chunk)
                            if not nonce or not ciphertext:
                                chunk_data = chunk
                                nonce = b'\x00' * 12
                            else:
                                chunk_data = ciphertext
                            
                            chunk_header = nonce + len(chunk_data).to_bytes(4, 'big')
                            client_socket.sendall(chunk_header + chunk_data)
                            
                            bytes_sent += len(chunk_data)
                            
                            if progress_callback:
                                progress_callback(bytes_sent, filesize)
                            
                            if bytes_sent % (self.CHUNK_SIZE * 10) == 0:
                                progress = (bytes_sent / filesize) * 100
                                print(f"[Send File] Progress: {progress:.1f}%")
                else:
                    with open(file_path, 'rb') as f:
                        while True:
                            chunk = f.read(self.BUFFER_SIZE)
                            if not chunk:
                                break
                            
                            client_socket.sendall(chunk)
                            bytes_sent += len(chunk)
                            
                            if progress_callback:
                                progress_callback(bytes_sent, filesize)
                            
                            if bytes_sent % (self.BUFFER_SIZE * 10) == 0:
                                progress = (bytes_sent / filesize) * 100
                                print(f"[Send File] Progress: {progress:.1f}%")
                
                client_socket.close()
                print(f"[Send File] Successfully sent '{filename}' to {target_ip}")
                
                timestamp_unix = time.time()
                if self.persistence_db:
                    threading.Thread(
                        target=self.persistence_db.save_message,
                        args=(target_ip, "me", "file", filename, timestamp_unix, ttl),
                        daemon=True
                    ).start()
                if self.db_manager:
                    threading.Thread(
                        target=self.db_manager.save_message,
                        args=(target_ip, "ME", filename, "FILE", file_path, timestamp_unix),
                        daemon=True
                    ).start()
                
                return True
                
            except Exception as e:
                print(f"[Send File] Error: {e}")
                return False
        
        threading.Thread(target=_send_file_worker, daemon=True).start()
        return True
    
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
                    
                    if os.path.exists(meta_path) and os.path.exists(data_path):
                        try:
                            meta = self._read_spool_metadata(meta_path)
                            if meta:
                                print(f"[DTN Spool] Peer {resolved_peer_id} is reachable. Forwarding spooled file: {meta['original_filename']}")
                                success = self._send_spooled_file(connection_target, data_path, meta)
                                if success:
                                    import shutil
                                    shutil.rmtree(item_path)
                                    print(f"[DTN Spool] Spooled item sent successfully and removed: {meta['original_filename']}")
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
                            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            client_socket.settimeout(5.0)
                            client_socket.connect((ip, self._get_peer_port(ip)))
                            
                            client_socket.sendall(encrypted_header + self.HEADER_DELIMITER + payload)
                            client_socket.close()
                            
                            print(f"[Relay] Forwarded packet for {target_peer_id} via {next_hop_id} (TTL: {ttl-1})")
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
                                                    
                                                    fallback_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                                    fallback_socket.settimeout(5.0)
                                                    fallback_socket.connect((f_ip, self._get_peer_port(f_ip)))
                                                    fallback_socket.sendall(fallback_encrypted_header + self.HEADER_DELIMITER + payload)
                                                    fallback_socket.close()
                                                    print(f"[Relay] Fallback forwarding successful via {fallback_peer_id}!")
                                                    return
                                                except Exception as ex:
                                                    print(f"[Relay] Fallback via {fallback_peer_id} failed: {ex}")
                        return
        
        except Exception as e:
            print(f"[Relay] Forward execution error: {e}")
    
    def _on_network_changed(self, old_ip, new_ip, network_type):
        """Callback when network changes."""
        print(f"[GhostEngine] Network changed: {old_ip} → {new_ip} ({network_type})")
        self.local_ip = new_ip
        self.current_network_type = network_type
    
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


# Test the engine
if __name__ == "__main__":
    def on_msg(sender_ip, msg, ts):
        print(f"\n💬 [{ts}] Message from {sender_ip}: {msg}\n")
    
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
