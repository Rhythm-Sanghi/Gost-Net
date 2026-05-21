import socket
import psutil
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
            if self.engine_ref and hasattr(self.engine_ref, 'routing_manager'):
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
            except:
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


def encrypt_telemetry_file(input_path: str, output_path: str) -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.backends import default_backend
        import os
        
        diagnostic_key_material = b'ghostnet_diagnostic_export_key_2024'
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'diagnostic_salt',
            info=b'telemetry_encryption',
            backend=default_backend()
        )
        derived_key = hkdf.derive(diagnostic_key_material)
        
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        nonce = os.urandom(12)
        cipher = AESGCM(derived_key)
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        
        with open(output_path, 'wb') as f:
            f.write(nonce)
            f.write(ciphertext)
        
        return True
    except Exception as e:
        print(f"[TelemetryExport] Encryption error: {e}")
        return False


def copy_to_downloads(file_path: str, file_name: str) -> Optional[str]:
    try:
        import platform as _platform_check
        
        if _platform_check.system() == 'Android':
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
