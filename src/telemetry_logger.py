import os
import csv
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import platform as _platform_check


class TelemetryLogger:
    
    def __init__(self, data_dir: Optional[str] = None):
        self.lock = threading.Lock()
        self.buffer_lock = threading.Lock()
        self.buffer = []
        self.buffer_size = 10
        self.flush_interval = 5.0
        self.last_flush = time.time()
        self.cipher = None
        
        if data_dir is None:
            is_android = False
            try:
                from kivy.utils import platform as _kivy_platform
                is_android = (_kivy_platform == 'android')
            except ImportError:
                is_android = (_platform_check.system() == 'Android')

            if is_android:
                try:
                    from android.storage import app_storage_path
                    base_dir = app_storage_path()
                except:
                    base_dir = '/data/data/org.ghostnet'
            else:
                base_dir = os.path.expanduser('~/.ghostnet')
        else:
            base_dir = data_dir
        
        self.data_dir = base_dir
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.csv_path = os.path.join(self.data_dir, 'mission_telemetry.csv')
        self.init_csv()

    def set_cipher(self, cipher):
        self.cipher = cipher
    
    def init_csv(self):
        # Initialized lazily during flush to ensure header is encrypted under the active cipher
        pass
    
    def log_event(self, event_type: str, peer_id: str = '', metric: str = '', status: str = ''):
        try:
            timestamp = datetime.utcnow().isoformat() + 'Z'
            peer_truncated = peer_id[:16] if peer_id else ''
            
            row = [timestamp, event_type, peer_truncated, metric, status]
            
            with self.buffer_lock:
                self.buffer.append(row)
                
                if len(self.buffer) >= self.buffer_size:
                    self._flush_buffer()
        except Exception as e:
            print(f"[TelemetryLogger] Error logging event: {e}")
    
    def _flush_buffer(self):
        if not self.buffer:
            return
        
        with self.lock:
            try:
                import io
                import csv
                import base64
                
                write_header = not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0
                
                with open(self.csv_path, 'ab') as f:
                    if write_header:
                        header = ['timestamp', 'event_type', 'peer_id', 'metric', 'status']
                        out = io.StringIO()
                        writer = csv.writer(out)
                        writer.writerow(header)
                        hdr_str = out.getvalue().strip()
                        if self.cipher:
                            f.write(self.cipher.encrypt(hdr_str.encode('utf-8')) + b"\n")
                        else:
                            f.write(b"BASE64:" + base64.b64encode(hdr_str.encode('utf-8')) + b"\n")
                            
                    for row in self.buffer:
                        out = io.StringIO()
                        writer = csv.writer(out)
                        writer.writerow(row)
                        row_str = out.getvalue().strip()
                        if self.cipher:
                            f.write(self.cipher.encrypt(row_str.encode('utf-8')) + b"\n")
                        else:
                            f.write(b"BASE64:" + base64.b64encode(row_str.encode('utf-8')) + b"\n")
                
                self.buffer.clear()
                self.last_flush = time.time()
            except Exception as e:
                print(f"[TelemetryLogger] Error flushing buffer: {e}")
    
    def record_metric(self, name: str, value: str = '', status: str = ''):
        """Convenience method to record a named metric or telemetry event."""
        self.log_event(event_type=name, metric=str(value), status=status)

    def flush(self):
        with self.buffer_lock:
            self._flush_buffer()
    
    def log_route_discovered(self, peer_id: str, metric: int = 0):
        self.log_event('ROUTE_DISCOVERED', peer_id=peer_id, metric=str(metric), status='active')
    
    def log_route_dropped(self, peer_id: str):
        self.log_event('ROUTE_DROPPED', peer_id=peer_id, status='inactive')
    
    def log_packet_relayed(self, peer_id: str, dest_peer_id: str = ''):
        status = f"relay_to:{dest_peer_id[:8] if dest_peer_id else 'unknown'}"
        self.log_event('PACKET_RELAYED', peer_id=peer_id, status=status)
    
    def log_handshake_failed(self, peer_id: str, reason: str = ''):
        self.log_event('HANDSHAKE_FAILED', peer_id=peer_id, status=reason or 'unknown_error')
    
    def log_connection_lost(self, peer_id: str, reason: str = ''):
        self.log_event('CONNECTION_LOST', peer_id=peer_id, status=reason or 'unknown_reason')
    
    def get_log_path(self) -> str:
        return self.csv_path
    
    def clear_logs(self):
        with self.lock:
            try:
                self.buffer.clear()
                if os.path.exists(self.csv_path):
                    try:
                        from security import shred_file
                    except ImportError:
                        from src.security import shred_file
                    shred_file(self.csv_path)
                self.init_csv()
            except Exception as e:
                print(f"[TelemetryLogger] Error clearing logs: {e}")
    
    def get_log_size(self) -> int:
        try:
            if os.path.exists(self.csv_path):
                return os.path.getsize(self.csv_path)
            return 0
        except:
            return 0


_telemetry_instance = None
_telemetry_lock = threading.Lock()


def get_telemetry_logger(data_dir: Optional[str] = None) -> TelemetryLogger:
    global _telemetry_instance
    if _telemetry_instance is None:
        with _telemetry_lock:
            if _telemetry_instance is None:
                _telemetry_instance = TelemetryLogger(data_dir)
    return _telemetry_instance
