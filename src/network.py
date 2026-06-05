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
                 connection_manager: Optional['ConnectionManager'] = None):
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
        """
        self.crypto_manager = None
        if SECURITY_AVAILABLE:
            self.crypto_manager = CryptoManager()
        
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
        
        # Encryption
        self.cipher = self._generate_cipher()
        
        # Sockets (initialized in start())
        self.udp_socket = None
        self.tcp_socket = None
        
        # Threads
        self.beacon_thread = None
        self.listener_thread = None
        self.tcp_server_thread = None
        self.pruning_thread = None
        self.routing_maintenance_thread = None
        self.relay_forwarding_thread = None
        
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
        
        # Initialize TCP server socket for incoming messages with retry logic
        tcp_success = False
        for port_offset in range(0, 5):  # Try ports 37021-37025
            try:
                tcp_port = self.TCP_PORT + port_offset
                self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.tcp_socket.bind(('0.0.0.0', tcp_port))
                self.tcp_socket.listen(5)
                self.tcp_socket.settimeout(1.0)
                self.TCP_PORT = tcp_port  # Update to working port
                print(f"[GhostEngine] TCP server listening on port {tcp_port}")
                tcp_success = True
                break
            except OSError as e:
                print(f"[GhostEngine] TCP port {tcp_port} failed: {e}")
                if self.tcp_socket:
                    try:
                        self.tcp_socket.close()
                    except:
                        pass
                continue
            except Exception as e:
                print(f"[GhostEngine] TCP socket error: {e}")
                break
        
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
                      self.routing_maintenance_thread, self.relay_forwarding_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        
        print("[GhostEngine] Shutdown complete.")
    
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
                    "visible_peers": visible_peers
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
            
            time.sleep(self.BEACON_INTERVAL)
    
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
                
                # Parse beacon
                beacon = json.loads(data.decode('utf-8'))
                
                if beacon.get("type") == "BEACON":
                    username = beacon.get("username", "Unknown")
                    current_time = time.time()
                    beacon_peer_id = beacon.get("peer_id", sender_ip)
                    visible_peers = beacon.get("visible_peers", [])
                    
                    with self.peers_lock:
                        self.peers[sender_ip] = {
                            "username": username,
                            "last_seen": current_time,
                            "peer_id": beacon_peer_id,
                            "visible_peers": visible_peers
                        }
                    
                    if self.routing_table:
                        self.routing_table.add_direct_route(beacon_peer_id)
                        
                        for visible_peer_id in visible_peers:
                            if visible_peer_id != self.peer_id:
                                self.routing_table.add_route(
                                    visible_peer_id,
                                    beacon_peer_id,
                                    1,
                                    [visible_peer_id, beacon_peer_id]
                                )
                    
                    if self.persistence_db:
                        threading.Thread(
                            target=self.persistence_db.save_peer,
                            args=(sender_ip, username, None, "udp", current_time),
                            daemon=True
                        ).start()
                    
                    if self.db_manager:
                        threading.Thread(
                            target=self.db_manager.save_peer,
                            args=(sender_ip, username, current_time),
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
                        del self.peers[ip]
                        print(f"[Pruning] Removed stale peer: {username} @ {ip}")
                
                # Notify UI if peers were removed
                if stale_ips and self.on_peer_update:
                    self.on_peer_update(self.get_all_peers_combined())
                    
            except Exception as e:
                print(f"[Pruning] Error: {e}")
    
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
        
        try:
            header_data = b""
            while True:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                header_data += chunk
                
                if self.HEADER_DELIMITER in header_data:
                    header_part, remaining_data = header_data.split(self.HEADER_DELIMITER, 1)
                    
                    try:
                        header_json = self._decrypt_message(header_part)
                        header = json.loads(header_json)
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
                    
                    break
        
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
            
            safe_filename = self._sanitize_filename(filename)
            filepath = os.path.join(self.downloads_dir, safe_filename)
            
            base, ext = os.path.splitext(filepath)
            counter = 1
            while os.path.exists(filepath):
                filepath = f"{base}_{counter}{ext}"
                counter += 1
            
            bytes_received = len(initial_data)
            
            if is_chunked:
                self._handle_chunked_file_transfer(filepath, filesize, bytes_received, initial_data, conn, sender_ip, filename, checksum, ttl)
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
                    os.remove(filepath)
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
    
    def _handle_chunked_file_transfer(self, filepath: str, filesize: int, initial_bytes: int, initial_data: bytes, conn: socket.socket, sender_ip: str, filename: str, checksum: str, ttl: Optional[int] = None):
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
                os.remove(filepath)
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
            
            print(f"[GhostEngine] SOS received from {sos_payload.get('sender_name')}")
            
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
                        sock.connect((peer_ip, self.TCP_PORT))
                        
                        header = {
                            'type': 'message',
                            'message_type': 'SOS',
                            'sender_id': sos_payload.get('sender_id'),
                            'sender_name': sos_payload.get('sender_name')
                        }
                        header_json = json.dumps(header)
                        header_bytes = header_json.encode('utf-8')
                        
                        encrypted_sos = self._encrypt_message(sos_json)
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
        Send an encrypted text message to a target peer via TCP or P2P connection.
        
        Args:
            target_ip: IP address of the target peer (or peer_id for off-grid peers)
            message_text: The message to send
            peer_id: Peer ID for off-grid peers (WiFi Direct/Bluetooth)
            ttl: Time-to-live in seconds for message expiration (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
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
            client_socket.connect((target_ip, self.TCP_PORT))
            
            client_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
            
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
                if target_ip and (target_ip.startswith('wfd_') or target_ip.startswith('bt_')):
                    peer_id = target_ip
                
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
                    "network_ttl": 10
                }
                
                if ttl is not None and ttl > 0:
                    header["ttl"] = ttl
                
                header_json = json.dumps(header)
                encrypted_header = self._encrypt_message(header_json)
                
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(30.0)
                client_socket.connect((target_ip, self.TCP_PORT))
                
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
                        encrypted_header = self._encrypt_message(header_json)
                        
                        try:
                            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            client_socket.settimeout(5.0)
                            client_socket.connect((ip, self.TCP_PORT))
                            
                            client_socket.sendall(encrypted_header + self.HEADER_DELIMITER + payload)
                            client_socket.close()
                            
                            print(f"[Relay] Forwarded packet for {target_peer_id} via {next_hop_id} (TTL: {ttl-1})")
                        except Exception as e:
                            print(f"[Relay] Forward to {ip} failed: {e}")
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
                    sock.connect((peer_ip, self.TCP_PORT))
                    
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
                        sock.connect((peer_ip, self.TCP_PORT))
                        
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
