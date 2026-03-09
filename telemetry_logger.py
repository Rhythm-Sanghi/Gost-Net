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
        
        if data_dir is None:
            if _platform_check.system() == 'Android':
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
    
    def init_csv(self):
        with self.lock:
            if not os.path.exists(self.csv_path):
                try:
                    with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(['timestamp', 'event_type', 'peer_id', 'metric', 'status'])
                except Exception as e:
                    print(f"[TelemetryLogger] Error initializing CSV: {e}")
    
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
                with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    for row in self.buffer:
                        writer.writerow(row)
                
                self.buffer.clear()
                self.last_flush = time.time()
            except Exception as e:
                print(f"[TelemetryLogger] Error flushing buffer: {e}")
    
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
                    os.remove(self.csv_path)
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
