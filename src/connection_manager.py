import threading
import time
import socket
from typing import Dict, Optional, Callable
from enum import Enum
from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

try:
    from security import CryptoManager
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    print("[ConnectionManager] Security module not available")


class ConnectionState(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    DISCONNECTED = "disconnected"


class P2PConnection:
    
    def __init__(self, peer_id: str, peer_info: Dict, on_connected: Optional[Callable] = None, on_failed: Optional[Callable] = None):
        self.peer_id = peer_id
        self.peer_info = peer_info
        self.discovery_type = peer_info.get('discovery_type', 'unknown')
        self.state = ConnectionState.IDLE
        self.on_connected = on_connected
        self.on_failed = on_failed
        
        self.socket = None
        self.connected_ip = None
        self.session_key = None
        self.crypto_manager = None

    def _perform_ecdh_handshake(self, sock: socket.socket) -> bool:
        if not SECURITY_AVAILABLE:
            return True

        try:
            if not self.crypto_manager:
                self.crypto_manager = CryptoManager()

            # 1. Send our ECDH public key (97 bytes)
            local_pub_key = self.crypto_manager.get_public_key_bytes()
            sock.sendall(local_pub_key)

            # 2. Receive peer's ECDH public key (97 bytes)
            peer_pub_key = b''
            while len(peer_pub_key) < 97:
                chunk = sock.recv(97 - len(peer_pub_key))
                if not chunk:
                    print(f"[P2PConnection] Peer {self.peer_id} disconnected during key exchange")
                    return False
                peer_pub_key += chunk

            # Now we have both ECDH keys. Sign local_pub_key + peer_pub_key
            local_signing_pub = self.crypto_manager.get_signing_public_key_bytes()
            sig_input = local_pub_key + peer_pub_key
            signature = self.crypto_manager.sign_data(sig_input)
            
            # Send our signing public key (32 bytes) and signature (64 bytes)
            sock.sendall(local_signing_pub + signature)
            
            # Receive peer's signing public key (32 bytes) and signature (64 bytes)
            peer_auth_data = b''
            expected_auth_len = 96
            while len(peer_auth_data) < expected_auth_len:
                chunk = sock.recv(expected_auth_len - len(peer_auth_data))
                if not chunk:
                    print(f"[P2PConnection] Peer {self.peer_id} disconnected during auth exchange")
                    return False
                peer_auth_data += chunk
                
            peer_signing_key = peer_auth_data[:32]
            peer_signature = peer_auth_data[32:]
            
            # Verify peer signature against peer_pub_key + local_pub_key
            verify_input = peer_pub_key + local_pub_key
            verified = self.crypto_manager.verify_signature(peer_signature, verify_input, peer_signing_key)
            if not verified:
                print(f"[P2PConnection] CRITICAL: Handshake signature verification failed for {self.peer_id}!")
                return False

            self.crypto_manager.set_peer_public_key(self.peer_id, peer_pub_key)

            # TOFU check against the database
            import base64
            peer_signing_key_b64 = base64.b64encode(peer_signing_key).decode('utf-8')
            
            app = None
            try:
                from kivymd.app import MDApp
                app = MDApp.get_running_app()
            except:
                pass
                
            persistence_db = None
            if app and hasattr(app, 'persistence_db'):
                persistence_db = app.persistence_db
            
            if persistence_db:
                stored_peer = persistence_db.get_peer(self.peer_id)
                if stored_peer:
                    stored_key = stored_peer.get('signing_key')
                    if stored_key:
                        if stored_key != peer_signing_key_b64:
                            print(f"[P2PConnection] CRITICAL: Peer identity key mismatch for {self.peer_id}! Potential MitM attack detected!")
                            return False
                    else:
                        # Database has peer but no key yet (migrated or pre-existing peer entry). Save it!
                        persistence_db.update_peer_signing_key(self.peer_id, peer_signing_key_b64, 0)
                else:
                    # Save peer to database first, then update key
                    persistence_db.save_peer(
                        peer_id=self.peer_id,
                        device_name=self.peer_info.get('username', 'Unknown'),
                        mac_address=self.peer_info.get('mac_address'),
                        discovery_type=self.discovery_type
                    )
                    persistence_db.update_peer_signing_key(self.peer_id, peer_signing_key_b64, 0)

            shared_secret = self.crypto_manager.derive_shared_secret(self.peer_id)
            if not shared_secret:
                print(f"[P2PConnection] Failed to derive shared secret for {self.peer_id}")
                return False

            aes_key = self.crypto_manager.derive_aes_key(self.peer_id, shared_secret)
            if not aes_key:
                print(f"[P2PConnection] Failed to derive AES key for {self.peer_id}")
                return False

            self.session_key = aes_key
            print(f"[P2PConnection] Authenticated secure handshake completed for {self.peer_id}")
            return True

        except Exception as e:
            print(f"[P2PConnection] ECDH handshake error for {self.peer_id}: {e}")
            return False


class WiFiDirectConnection(P2PConnection):
    
    def __init__(self, peer_id: str, peer_info: Dict, wifi_direct=None, on_connected: Optional[Callable] = None, on_failed: Optional[Callable] = None):
        super().__init__(peer_id, peer_info, on_connected, on_failed)
        self.wifi_direct = wifi_direct or get_android_wifi_direct()
        self.mac_address = peer_info.get('mac_address')
        self.go_ip = peer_info.get('go_ip')
    
    def connect(self):
        self.state = ConnectionState.CONNECTING
        
        def _connect_worker():
            try:
                print(f"[WiFiDirectConnection] Connecting to {self.mac_address}...")
                
                success = self.wifi_direct.connect(self.mac_address)
                
                if success:
                    time.sleep(2)
                    
                    self.connected_ip = self.wifi_direct.get_go_ip_for_peer(self.mac_address)
                    
                    if self.connected_ip:
                        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.socket.settimeout(10.0)
                        
                        try:
                            self.socket.connect((self.connected_ip, 37021))
                            print(f"[WiFiDirectConnection] Raw socket connected to {self.connected_ip}")

                            if not self._perform_ecdh_handshake(self.socket):
                                print(f"[WiFiDirectConnection] ECDH handshake failed")
                                self.state = ConnectionState.FAILED
                                if self.on_failed:
                                    self.on_failed(self, "ECDH handshake failed")
                                return

                            self.state = ConnectionState.CONNECTED
                            print(f"[WiFiDirectConnection] Secure connection established")
                            if self.on_connected:
                                self.on_connected(self)
                        except socket.error as e:
                            print(f"[WiFiDirectConnection] TCP connection failed: {e}")
                            self.state = ConnectionState.FAILED
                            if self.on_failed:
                                self.on_failed(self, str(e))
                    else:
                        print(f"[WiFiDirectConnection] Could not resolve GO IP")
                        self.state = ConnectionState.FAILED
                        if self.on_failed:
                            self.on_failed(self, "No GO IP")
                else:
                    print(f"[WiFiDirectConnection] Connection handshake failed")
                    self.state = ConnectionState.FAILED
                    if self.on_failed:
                        self.on_failed(self, "Handshake failed")
            
            except Exception as e:
                print(f"[WiFiDirectConnection] Error: {e}")
                self.state = ConnectionState.FAILED
                if self.on_failed:
                    self.on_failed(self, str(e))
        
        thread = threading.Thread(target=_connect_worker, daemon=True)
        thread.start()
    
    def disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        
        try:
            self.wifi_direct.disconnect()
        except:
            pass
        
        self.state = ConnectionState.DISCONNECTED
        self.connected_ip = None
        self.socket = None


class BluetoothConnection(P2PConnection):
    
    def __init__(self, peer_id: str, peer_info: Dict, bluetooth=None, on_connected: Optional[Callable] = None, on_failed: Optional[Callable] = None):
        super().__init__(peer_id, peer_info, on_connected, on_failed)
        self.bluetooth = bluetooth or get_android_bluetooth()
        self.bluetooth_address = peer_info.get('bluetooth_address')
        self.device_name = peer_info.get('device_name')
        self.rfcomm_socket = None
    
    def connect(self):
        self.state = ConnectionState.CONNECTING
        
        def _connect_worker():
            try:
                print(f"[BluetoothConnection] Connecting to {self.bluetooth_address}...")
                
                success = self.bluetooth.connect(self.bluetooth_address)
                
                if success:
                    time.sleep(3)
                    
                    self.rfcomm_socket = self.bluetooth.create_rfcomm_socket(self.bluetooth_address)
                    
                    if self.rfcomm_socket:
                        print(f"[BluetoothConnection] RFCOMM socket created")

                        if not self._perform_ecdh_handshake(self.rfcomm_socket):
                            print(f"[BluetoothConnection] ECDH handshake failed")
                            self.state = ConnectionState.FAILED
                            if self.on_failed:
                                self.on_failed(self, "ECDH handshake failed")
                            return

                        self.state = ConnectionState.CONNECTED
                        print(f"[BluetoothConnection] Secure connection established via RFCOMM")
                        if self.on_connected:
                            self.on_connected(self)
                    else:
                        print(f"[BluetoothConnection] RFCOMM socket creation failed")
                        self.state = ConnectionState.FAILED
                        if self.on_failed:
                            self.on_failed(self, "RFCOMM socket failed")
                else:
                    print(f"[BluetoothConnection] BT connection failed")
                    self.state = ConnectionState.FAILED
                    if self.on_failed:
                        self.on_failed(self, "BT pairing failed")
            
            except Exception as e:
                print(f"[BluetoothConnection] Error: {e}")
                self.state = ConnectionState.FAILED
                if self.on_failed:
                    self.on_failed(self, str(e))
        
        thread = threading.Thread(target=_connect_worker, daemon=True)
        thread.start()
    
    def disconnect(self):
        if self.rfcomm_socket:
            try:
                self.rfcomm_socket.close()
            except:
                pass
        
        try:
            self.bluetooth.disconnect()
        except:
            pass
        
        self.state = ConnectionState.DISCONNECTED
        self.rfcomm_socket = None


class ConnectionManager:
    
    def __init__(self, engine=None):
        self.engine = engine
        self.active_connections: Dict[str, P2PConnection] = {}
        self.peer_id_map: Dict[str, str] = {}
        self.connections_lock = threading.Lock()
        
        self.wifi_direct = get_android_wifi_direct()
        self.bluetooth = get_android_bluetooth()
        
        self.bluetooth_server_thread = None
        self.bluetooth_server_running = False
        self._start_bluetooth_server()
    
    def _start_bluetooth_server(self):
        if not is_android():
            print("[BluetoothServer] Mock server started (desktop)")
            return
        
        def _server_worker():
            try:
                print("[BluetoothServer] Starting RFCOMM server...")
                self.bluetooth_server_running = True
                
                while self.bluetooth_server_running:
                    try:
                        incoming_socket = self.bluetooth.listen_rfcomm()
                        
                        if incoming_socket:
                            print("[BluetoothServer] Incoming connection")
                            threading.Thread(
                                target=self._handle_bluetooth_connection,
                                args=(incoming_socket,),
                                daemon=True
                            ).start()
                    
                    except Exception as e:
                        print(f"[BluetoothServer] Error: {e}")
                        time.sleep(1)
            
            except Exception as e:
                print(f"[BluetoothServer] Fatal error: {e}")
        
        self.bluetooth_server_thread = threading.Thread(target=_server_worker, daemon=True)
        self.bluetooth_server_thread.start()
    
    def _handle_bluetooth_connection(self, incoming_socket):
        try:
            data = incoming_socket.recv(1024)
            if data:
                print(f"[BluetoothServer] Received {len(data)} bytes")
                
                if self.engine and self.engine.on_message_received:
                    sender_addr = incoming_socket.getpeername()
                    sender_id = sender_addr[0]

                    is_stego = False
                    stego_type = None
                    if data.startswith(b'\x89PNG\r\n\x1a\n'):
                        stego_type = "png"
                    elif data.startswith(b'RIFF') and b'WAVE' in data[8:12]:
                        stego_type = "wav"
                        
                    if stego_type:
                        try:
                            import os
                            import sys
                            sys.path.insert(0, os.path.dirname(__file__))
                            import steganography
                            if stego_type == "png":
                                decoded = steganography.decode_lsb(data)
                            else:
                                decoded = steganography.decode_wav_lsb(data)
                            if decoded:
                                downloads_dir = getattr(self.engine, 'downloads_dir', 'downloads')
                                os.makedirs(downloads_dir, exist_ok=True)
                                carrier_path = os.path.join(downloads_dir, f"stego_bt_{int(time.time())}.{stego_type}")
                                with open(carrier_path, 'wb') as f:
                                    f.write(data)
                                data = decoded
                                is_stego = True
                        except Exception as e:
                            print(f"[BluetoothServer] Stego decoding error: {e}")

                    decrypted_data = data
                    if self.engine.crypto_manager and len(data) > 12:
                        decryption_result = self.engine.crypto_manager.decrypt_message(
                            sender_id,
                            data[:12],
                            data[12:]
                        )
                        if decryption_result:
                            decrypted_data = decryption_result
                        else:
                            print(f"[BluetoothServer] Decryption failed, dropping packet from {sender_id}")
                            return

                    try:
                        message = decrypted_data.decode('utf-8', errors='ignore') if isinstance(decrypted_data, bytes) else decrypted_data
                    except:
                        message = str(decrypted_data)

                    if is_stego:
                        message = "[Stego Image Decoded] " + message

                    import time as time_module
                    timestamp = time_module.strftime("%H:%M:%S")
                    self.engine.on_message_received(sender_id, message, timestamp)
        
        except Exception as e:
            print(f"[BluetoothServer] Connection error: {e}")
        
        finally:
            try:
                incoming_socket.close()
            except:
                pass
    
    def connect_to_peer(self, peer_id: str, peer_info: Dict, on_connected: Optional[Callable] = None, on_failed: Optional[Callable] = None):
        discovery_type = peer_info.get('discovery_type', 'unknown')
        
        if discovery_type == 'wifi_lan':
            print(f"[ConnectionManager] WiFi LAN peer {peer_id} - using existing UDP/TCP")
            if on_connected:
                on_connected(None)
            return
        
        elif discovery_type == 'wifi_direct':
            connection = WiFiDirectConnection(
                peer_id,
                peer_info,
                self.wifi_direct,
                on_connected=on_connected,
                on_failed=on_failed
            )
            if self.engine:
                connection.crypto_manager = self.engine.crypto_manager
        
        elif discovery_type == 'bluetooth':
            connection = BluetoothConnection(
                peer_id,
                peer_info,
                self.bluetooth,
                on_connected=on_connected,
                on_failed=on_failed
            )
            if self.engine:
                connection.crypto_manager = self.engine.crypto_manager
        
        else:
            print(f"[ConnectionManager] Unknown peer type: {discovery_type}")
            if on_failed:
                on_failed(None, "Unknown peer type")
            return
        
        with self.connections_lock:
            self.active_connections[peer_id] = connection
            self.peer_id_map[peer_id] = peer_id
        
        connection.connect()
    
    def get_connection(self, peer_id: str) -> Optional[P2PConnection]:
        with self.connections_lock:
            return self.active_connections.get(peer_id)
    
    def get_peer_connection_state(self, peer_id: str) -> ConnectionState:
        connection = self.get_connection(peer_id)
        if connection:
            return connection.state
        return ConnectionState.IDLE
    
    def disconnect_peer(self, peer_id: str):
        with self.connections_lock:
            connection = self.active_connections.pop(peer_id, None)
            self.peer_id_map.pop(peer_id, None)
        
        if connection:
            connection.disconnect()
            print(f"[ConnectionManager] Disconnected from {peer_id}")
    
    def send_message_to_peer(self, peer_id: str, message: str) -> bool:
        connection = self.get_connection(peer_id)
        
        if not connection:
            print(f"[ConnectionManager] No active connection to {peer_id}")
            return False
        
        if connection.state != ConnectionState.CONNECTED:
            print(f"[ConnectionManager] Connection to {peer_id} not ready: {connection.state.value}")
            return False
        
        try:
            payload = message.encode('utf-8') if isinstance(message, str) else message
            
            if connection.discovery_type == 'wifi_direct':
                if connection.socket:
                    connection.socket.sendall(payload)
                    print(f"[ConnectionManager] Message sent via WiFi Direct to {peer_id}")
                    return True
            
            elif connection.discovery_type == 'bluetooth':
                if connection.rfcomm_socket:
                    connection.rfcomm_socket.send(payload)
                    print(f"[ConnectionManager] Message sent via Bluetooth to {peer_id}")
                    return True
        
        except Exception as e:
            print(f"[ConnectionManager] Send error to {peer_id}: {e}")
            return False
        
        return False
    
    def shutdown(self):
        self.bluetooth_server_running = False
        
        with self.connections_lock:
            for peer_id, connection in list(self.active_connections.items()):
                connection.disconnect()
        
        self.active_connections.clear()
        self.peer_id_map.clear()
        print("[ConnectionManager] Shutdown complete")
