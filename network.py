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

# Import network utilities for multi-interface detection
try:
    from network_utils import NetworkDetector, NetworkMonitor
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

# Import config module (optional)
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
    BEACON_INTERVAL = 2  # seconds
    PEER_TIMEOUT = 10    # seconds
    BUFFER_SIZE = 4096
    HEADER_DELIMITER = b"<HEADER_END>"
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB limit
    
    def __init__(self, username: str = None, on_message_received: Optional[Callable] = None,
                 on_peer_update: Optional[Callable] = None,
                 on_file_received: Optional[Callable] = None,
                 downloads_dir: Optional[str] = None,
                 enable_storage: bool = True,
                 db_manager: Optional['DatabaseManager'] = None,
                 config_manager: Optional['ConfigManager'] = None):
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
        # Configuration manager
        self.config_manager = config_manager
        if not self.config_manager and CONFIG_AVAILABLE:
            self.config_manager = ConfigManager()
        
        # Get username from config if not provided
        if username:
            self.username = username
        elif self.config_manager:
            self.username = self.config_manager.get_username()
        else:
            self.username = "GhostUser"
        
        # Network detection with multi-interface support
        self.network_detector = None
        self.network_monitor = None
        if NETWORK_UTILS_AVAILABLE:
            self.network_detector = NetworkDetector()
            self.network_monitor = NetworkMonitor(on_network_changed=self._on_network_changed)
        
        self.local_ip = self._get_local_ip()
        self.current_network_type = 'unknown'
        self.peers: Dict[str, dict] = {}  # {ip: {username, last_seen}}
        self.running = False
        
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
                import platform
                if platform.system() == 'Android':
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
        
        # Database storage
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
        
        print(f"[GhostEngine] {threads_started} threads started successfully.")
        
        # Don't fail if no threads started - app can still function with limited capability
        if threads_started == 0:
            print("[GhostEngine] WARNING: No background threads started - limited functionality")
    
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
        
        # Wait for threads to finish
        for thread in [self.beacon_thread, self.listener_thread, 
                      self.tcp_server_thread, self.pruning_thread]:
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
                
                beacon = {
                    "type": "BEACON",
                    "username": current_username,
                    "ip": self.local_ip
                }
                message = json.dumps(beacon).encode('utf-8')
                
                # Broadcast to 255.255.255.255
                self.udp_socket.sendto(message, ('<broadcast>', self.UDP_PORT))
                # print(f"[Beacon] Broadcasted: {beacon}")
                
            except Exception as e:
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
                    
                    # Update peers list
                    with self.peers_lock:
                        self.peers[sender_ip] = {
                            "username": username,
                            "last_seen": current_time
                        }
                    
                    # Save to database
                    if self.db_manager:
                        threading.Thread(
                            target=self.db_manager.save_peer,
                            args=(sender_ip, username, current_time),
                            daemon=True
                        ).start()
                    
                    # Notify UI
                    if self.on_peer_update:
                        self.on_peer_update(self.get_peers())
                    
                    # print(f"[Listener] Discovered peer: {username} @ {sender_ip}")
                
            except socket.timeout:
                continue
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
                    self.on_peer_update(self.get_peers())
                    
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
            # Step 1: Read the header
            header_data = b""
            while True:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                header_data += chunk
                
                # Check for header delimiter
                if self.HEADER_DELIMITER in header_data:
                    # Split at delimiter
                    header_part, remaining_data = header_data.split(self.HEADER_DELIMITER, 1)
                    
                    # Decrypt and parse header
                    try:
                        header_json = self._decrypt_message(header_part)
                        header = json.loads(header_json)
                    except (ValueError, json.JSONDecodeError) as e:
                        print(f"[TCP Handler] Invalid header from {sender_ip}: {e}")
                        return
                    
                    # Process based on type
                    if header.get("type") == "TEXT":
                        self._handle_text_message(sender_ip, header, remaining_data, conn)
                    elif header.get("type") == "FILE":
                        self._handle_file_transfer(sender_ip, header, remaining_data, conn)
                    else:
                        print(f"[TCP Handler] Unknown type: {header.get('type')}")
                    
                    break
        
        except Exception as e:
            print(f"[TCP Handler] Error handling connection from {sender_ip}: {e}")
        finally:
            conn.close()
    
    def _handle_text_message(self, sender_ip: str, header: dict, initial_data: bytes, conn: socket.socket):
        """Handle incoming text message."""
        try:
            message_text = header.get("content", "")
            timestamp = datetime.now().strftime("%H:%M:%S")
            timestamp_unix = time.time()
            
            print(f"[TCP] Message from {sender_ip}: {message_text}")
            
            # Save to database (in background)
            if self.db_manager:
                threading.Thread(
                    target=self.db_manager.save_message,
                    args=(sender_ip, "PEER", message_text, "TEXT", None, timestamp_unix),
                    daemon=True
                ).start()
            
            # Notify UI via callback
            if self.on_message_received:
                self.on_message_received(sender_ip, message_text, timestamp)
        
        except Exception as e:
            print(f"[TCP Handler] Text message error: {e}")
    
    def _handle_file_transfer(self, sender_ip: str, header: dict, initial_data: bytes, conn: socket.socket):
        """Handle incoming file transfer (runs in background thread)."""
        try:
            filename = header.get("filename", "unknown_file")
            filesize = header.get("filesize", 0)
            checksum = header.get("checksum", "")
            
            print(f"[File Transfer] Receiving '{filename}' ({filesize} bytes) from {sender_ip}")
            
            # Validate file size
            if filesize > self.MAX_FILE_SIZE:
                print(f"[File Transfer] File too large: {filesize} bytes (max {self.MAX_FILE_SIZE})")
                return
            
            # Create safe filename
            safe_filename = self._sanitize_filename(filename)
            filepath = os.path.join(self.downloads_dir, safe_filename)
            
            # If file exists, add number suffix
            base, ext = os.path.splitext(filepath)
            counter = 1
            while os.path.exists(filepath):
                filepath = f"{base}_{counter}{ext}"
                counter += 1
            
            # Write file in chunks
            bytes_received = len(initial_data)
            
            with open(filepath, 'wb') as f:
                # Write initial data
                f.write(initial_data)
                
                # Receive remaining chunks
                while bytes_received < filesize:
                    chunk = conn.recv(min(self.BUFFER_SIZE, filesize - bytes_received))
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_received += len(chunk)
                    
                    # Progress indicator
                    progress = (bytes_received / filesize) * 100
                    if bytes_received % (self.BUFFER_SIZE * 10) == 0:
                        print(f"[File Transfer] Progress: {progress:.1f}%")
            
            # Verify checksum
            received_checksum = self._calculate_checksum(filepath)
            if checksum and received_checksum != checksum:
                print(f"[File Transfer] Checksum mismatch! Expected {checksum}, got {received_checksum}")
                os.remove(filepath)
                return
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            timestamp_unix = time.time()
            print(f"[File Transfer] Successfully received '{filename}' → {filepath}")
            
            # Save to database (in background)
            if self.db_manager:
                threading.Thread(
                    target=self.db_manager.save_message,
                    args=(sender_ip, "PEER", filename, "FILE", filepath, timestamp_unix),
                    daemon=True
                ).start()
            
            # Notify UI via callback
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
    
    def _calculate_checksum(self, filepath: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def send_message(self, target_ip: str, message_text: str) -> bool:
        """
        Send an encrypted text message to a target peer via TCP.
        
        Args:
            target_ip: IP address of the target peer
            message_text: The message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create header
            header = {
                "type": "TEXT",
                "content": message_text,
                "timestamp": datetime.now().isoformat()
            }
            
            # Encrypt header
            header_json = json.dumps(header)
            encrypted_header = self._encrypt_message(header_json)
            
            # Create TCP connection
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10.0)  # 10 second timeout
            client_socket.connect((target_ip, self.TCP_PORT))
            
            # Send header + delimiter
            client_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
            
            client_socket.close()
            print(f"[Send] Message sent to {target_ip}")
            
            # Save to database (in background)
            if self.db_manager:
                timestamp_unix = time.time()
                threading.Thread(
                    target=self.db_manager.save_message,
                    args=(target_ip, "ME", message_text, "TEXT", None, timestamp_unix),
                    daemon=True
                ).start()
            
            return True
            
        except Exception as e:
            print(f"[Send] Error sending to {target_ip}: {e}")
            return False
    
    def send_file(self, target_ip: str, file_path: str, progress_callback: Optional[Callable] = None) -> bool:
        """
        Send a file to a target peer via TCP (runs in background thread).
        
        Args:
            target_ip: IP address of the target peer
            file_path: Path to the file to send
            progress_callback: Optional callback(bytes_sent, total_size) for progress updates
            
        Returns:
            True if sent successfully, False otherwise
        """
        def _send_file_worker():
            try:
                # Validate file
                if not os.path.isfile(file_path):
                    print(f"[Send File] File not found: {file_path}")
                    return False
                
                filesize = os.path.getsize(file_path)
                
                if filesize > self.MAX_FILE_SIZE:
                    print(f"[Send File] File too large: {filesize} bytes (max {self.MAX_FILE_SIZE})")
                    return False
                
                filename = os.path.basename(file_path)
                checksum = self._calculate_checksum(file_path)
                
                print(f"[Send File] Sending '{filename}' ({filesize} bytes) to {target_ip}")
                
                # Create header
                header = {
                    "type": "FILE",
                    "filename": filename,
                    "filesize": filesize,
                    "checksum": checksum,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Encrypt header
                header_json = json.dumps(header)
                encrypted_header = self._encrypt_message(header_json)
                
                # Create TCP connection
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(30.0)  # 30 second timeout for files
                client_socket.connect((target_ip, self.TCP_PORT))
                
                # Send header + delimiter
                client_socket.sendall(encrypted_header + self.HEADER_DELIMITER)
                
                # Send file in chunks
                bytes_sent = 0
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(self.BUFFER_SIZE)
                        if not chunk:
                            break
                        
                        client_socket.sendall(chunk)
                        bytes_sent += len(chunk)
                        
                        # Progress callback
                        if progress_callback:
                            progress_callback(bytes_sent, filesize)
                        
                        # Progress log
                        if bytes_sent % (self.BUFFER_SIZE * 10) == 0:
                            progress = (bytes_sent / filesize) * 100
                            print(f"[Send File] Progress: {progress:.1f}%")
                
                client_socket.close()
                print(f"[Send File] Successfully sent '{filename}' to {target_ip}")
                
                # Save to database (in background)
                if self.db_manager:
                    timestamp_unix = time.time()
                    threading.Thread(
                        target=self.db_manager.save_message,
                        args=(target_ip, "ME", filename, "FILE", file_path, timestamp_unix),
                        daemon=True
                    ).start()
                
                return True
                
            except Exception as e:
                print(f"[Send File] Error: {e}")
                return False
        
        # Run in background thread to avoid blocking
        threading.Thread(target=_send_file_worker, daemon=True).start()
        return True  # Return immediately
    
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
                            self.on_peer_update(self.get_peers())
            
            except Exception as e:
                if self.running:
                    print(f"[Network Monitor] Error: {e}")
    
    def _on_network_changed(self, old_ip, new_ip, network_type):
        """Callback when network changes."""
        print(f"[GhostEngine] Network changed: {old_ip} → {new_ip} ({network_type})")
        self.local_ip = new_ip
        self.current_network_type = network_type
    
    def get_network_status(self) -> Dict[str, any]:
        """Get current network status for UI display."""
        if self.network_detector:
            interfaces = self.network_detector.get_all_interfaces()
        else:
            interfaces = {}
        
        return {
            'ip': self.local_ip,
            'type': self.current_network_type,
            'interfaces': interfaces,
            'is_connected': self.local_ip != "127.0.0.1"
        }
    
    def get_peers(self) -> Dict[str, dict]:
        """Get a copy of the current peers dictionary."""
        with self.peers_lock:
            return self.peers.copy()
    
    def get_peer_username(self, ip: str) -> str:
        """Get the username of a peer by IP address."""
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
