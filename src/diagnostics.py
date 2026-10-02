import socket
try:
    import psutil
except ImportError:
    psutil = None
import threading
import time
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import os
import base64
from pathlib import Path


class NetworkDiagnostics:
    
    def __init__(self):
        self.data_lock = threading.Lock()
        self.local_ip = self._get_local_ip()
        self.local_mac = self._get_local_mac()
        self.start_time = time.time()
        self.routing_table = {}
        self.active_sockets = []
        self.message_queue_size = 0
        self.last_update = 0
        self.update_interval = 1.0
        self.engine_ref = None

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def _get_local_mac(self) -> str:
        try:
            import uuid
            mac = uuid.getnode()
            mac_str = ':'.join(("%012x" % mac)[i:i+2] for i in range(0, 12, 2))
            return mac_str.upper()
        except:
            return "00:00:00:00:00:00"

    def set_engine_reference(self, engine):
        with self.data_lock:
            self.engine_ref = engine

    def update_diagnostics(self):
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return

        with self.data_lock:
            self._update_routing_table()
            self._update_active_sockets()
            self._update_message_queue()
            self.last_update = current_time

    def _update_routing_table(self):
        try:
            routes = {}
            if self.engine_ref and hasattr(self.engine_ref, 'routing_table') and self.engine_ref.routing_table:
                rt = self.engine_ref.routing_table
                for dest_id, entry in rt.get_all_routes().items():
                    routes[dest_id] = {
                        'next_hop': entry.next_hop_id,
                        'metric': entry.metric,
                        'rtt_ms': getattr(entry, 'rtt_ms', 0.0),
                        'pdr': getattr(entry, 'pdr', 1.0),
                        'status': getattr(entry, 'route_status', 'ACTIVE')
                    }
            elif self.engine_ref and hasattr(self.engine_ref, 'routing_manager'):
                routing_mgr = self.engine_ref.routing_manager
                if hasattr(routing_mgr, 'routing_table'):
                    for dest_id, route_info in routing_mgr.routing_table.items():
                        if isinstance(route_info, dict):
                            next_hop = route_info.get('next_hop', 'N/A')
                            metric = route_info.get('metric', 'N/A')
                        else:
                            next_hop = str(route_info)
                            metric = 'N/A'
                        routes[dest_id] = {
                            'next_hop': next_hop,
                            'metric': metric
                        }
            self.routing_table = routes
        except Exception as e:
            self.routing_table = {'error': str(e)}


    def _update_active_sockets(self):
        try:
            sockets = []
            if psutil:
                try:
                    connections = psutil.net_connections()
                    for conn in connections:
                        if conn.status == 'ESTABLISHED':
                            socket_info = {
                                'local': f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else 'N/A',
                                'remote': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else 'N/A',
                                'type': conn.type.name if hasattr(conn.type, 'name') else str(conn.type),
                                'status': conn.status
                            }
                            sockets.append(socket_info)
                except Exception:
                    pass

            if self.engine_ref and hasattr(self.engine_ref, 'p2p_manager'):
                p2p_mgr = self.engine_ref.p2p_manager
                if hasattr(p2p_mgr, 'active_connections'):
                    for peer_id, conn_info in p2p_mgr.active_connections.items():
                        socket_info = {
                            'local': self.local_ip,
                            'remote': peer_id,
                            'type': 'P2P',
                            'status': 'ESTABLISHED'
                        }
                        sockets.append(socket_info)

            self.active_sockets = sockets
        except Exception as e:
            self.active_sockets = [{'error': str(e)}]

    def _update_message_queue(self):
        try:
            queue_size = 0
            if self.engine_ref and hasattr(self.engine_ref, 'forwarding_queue'):
                if hasattr(self.engine_ref.forwarding_queue, 'qsize'):
                    queue_size = self.engine_ref.forwarding_queue.qsize()
                elif hasattr(self.engine_ref.forwarding_queue, '__len__'):
                    queue_size = len(self.engine_ref.forwarding_queue)
            self.message_queue_size = queue_size
        except:
            self.message_queue_size = 0

    def get_uptime_seconds(self) -> float:
        return time.time() - self.start_time

    def get_uptime_string(self) -> str:
        uptime_sec = self.get_uptime_seconds()
        hours, remainder = divmod(int(uptime_sec), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def get_node_status(self) -> Dict:
        with self.data_lock:
            return {
                'local_ip': self.local_ip,
                'local_mac': self.local_mac,
                'uptime': self.get_uptime_string(),
                'service_status': 'Running' if self.engine_ref else 'Paused'
            }

    def get_routing_table(self) -> Dict:
        with self.data_lock:
            return dict(self.routing_table)

    def get_active_sockets(self) -> List[Dict]:
        with self.data_lock:
            return list(self.active_sockets)

    def get_message_queue_size(self) -> int:
        with self.data_lock:
            return self.message_queue_size

    def get_diagnostics_snapshot(self) -> Dict:
        self.update_diagnostics()
        return {
            'node_status': self.get_node_status(),
            'routing_table': self.get_routing_table(),
            'active_sockets': self.get_active_sockets(),
            'message_queue': self.get_message_queue_size(),
            'timestamp': time.time()
        }

_diagnostics_instance = None

def get_diagnostics():
    global _diagnostics_instance
    if _diagnostics_instance is None:
        _diagnostics_instance = NetworkDiagnostics()
    return _diagnostics_instance


def encrypt_telemetry_file(input_path: str, output_path: str, cipher: Optional[object] = None) -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.backends import default_backend
        import os
        import base64
        
        # 1. Load support public key
        SUPPORT_PUBLIC_KEY_HEX = "040a06512a9218b19eb751ed125222e65b7964f86b210c0e9f338ccce5378e0329130faf0b8cbc647ac2622c5e171ec41ff6972a395fbfc5508729f16d380c1447d81547850acf9f3d54c70681aaa9bf98a21373a9224b8d9c313e0ecd48328415"
        support_pub_bytes = bytes.fromhex(SUPPORT_PUBLIC_KEY_HEX)
        support_pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP384R1(), support_pub_bytes)
        
        # 2. Ephemeral EC Keypair for ECDH
        ephemeral_priv_key = ec.generate_private_key(ec.SECP384R1(), backend=default_backend())
        shared_secret = ephemeral_priv_key.exchange(ec.ECDH(), support_pub_key)
        
        # 3. KDF to derive AES symmetric key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'diagnostic_salt_v2',
            info=b'telemetry_hybrid_encryption',
            backend=default_backend()
        )
        aes_key = hkdf.derive(shared_secret)
        
        # 4. Decrypt original rows from input_path
        decrypted_lines = []
        if os.path.exists(input_path):
            with open(input_path, 'rb') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    decrypted_line = None
                    if cipher:
                        try:
                            decrypted_line = cipher.decrypt(line).decode('utf-8')
                        except:
                            pass
                    if decrypted_line is None:
                        if line.startswith(b"BASE64:"):
                            try:
                                decrypted_line = base64.b64decode(line[7:]).decode('utf-8')
                            except:
                                pass
                        else:
                            try:
                                decrypted_line = line.decode('utf-8')
                            except:
                                pass
                    if decrypted_line is not None:
                        decrypted_lines.append(decrypted_line)
                        
        plaintext = ("\n".join(decrypted_lines)).encode('utf-8')
        
        # 5. Encrypt plaintext using AES-GCM
        nonce = os.urandom(12)
        aes_cipher = AESGCM(aes_key)
        ciphertext = aes_cipher.encrypt(nonce, plaintext, None)
        
        # 6. Ephemeral public key serialization
        ephemeral_pub_bytes = ephemeral_priv_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        # 7. Write output file structure: [len_epub (4 bytes)] + [epub_bytes] + [nonce (12 bytes)] + [ciphertext]
        with open(output_path, 'wb') as f:
            f.write(len(ephemeral_pub_bytes).to_bytes(4, 'big'))
            f.write(ephemeral_pub_bytes)
            f.write(nonce)
            f.write(ciphertext)
            
        return True
    except Exception as e:
        print(f"[TelemetryExport] Hybrid encryption error: {e}")
        return False


def copy_to_downloads(file_path: str, file_name: str) -> Optional[str]:
    try:
        try:
            from kivy.utils import platform as kivy_platform
            is_android = (kivy_platform == 'android')
        except ImportError:
            is_android = False
        
        if is_android:
            try:
                from kivy.utils import platform
                from android.permissions import request_permissions, Permission
                
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
                
                from jnius import autoclass
                PythonJavaClass = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                Environment = autoclass('android.os.Environment')
                File = autoclass('java.io.File')
                
                downloads_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                if not downloads_dir.exists():
                    downloads_dir.mkdirs()
                
                dest_file = File(downloads_dir, file_name)
                
                with open(file_path, 'rb') as src:
                    with open(str(dest_file.getAbsolutePath()), 'wb') as dst:
                        dst.write(src.read())
                
                return str(dest_file.getAbsolutePath())
            except Exception as e:
                print(f"[TelemetryExport] Android copy error: {e}")
                return None
        else:
            home_dir = os.path.expanduser('~')
            downloads_dir = os.path.join(home_dir, 'Downloads')
            os.makedirs(downloads_dir, exist_ok=True)
            
            dest_path = os.path.join(downloads_dir, file_name)
            with open(file_path, 'rb') as src:
                with open(dest_path, 'wb') as dst:
                    dst.write(src.read())
            
            return dest_path
    except Exception as e:
        print(f"[TelemetryExport] Copy error: {e}")
        return None
