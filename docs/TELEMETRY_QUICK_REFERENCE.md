TELEMETRY BLACK BOX - QUICK REFERENCE
======================================

## Files Created/Modified

### NEW FILES
1. telemetry_logger.py - Core telemetry module
2. TELEMETRY_INTEGRATION.md - Integration guide

### MODIFIED FILES
1. diagnostics.py - Added encryption and export functions
2. main.py - Updated DiagnosticsScreen with export/clear buttons

## Quick Start

### 1. Import Telemetry Logger
python
from telemetry_logger import get_telemetry_logger

telemetry = get_telemetry_logger()


### 2. Log Network Events

python
telemetry.log_route_discovered(peer_id='abc123', metric=2)
telemetry.log_route_dropped(peer_id='def456')
telemetry.log_packet_relayed(peer_id='ghi789', dest_peer_id='xyz123')
telemetry.log_handshake_failed(peer_id='jkl012', reason='timeout')
telemetry.log_connection_lost(peer_id='mno345', reason='network_error')


### 3. Export & Encryption (via UI)
- Tap title bar 7 times rapidly on RadarScreen to unlock DiagnosticsScreen
- Tap "Export Mission Logs" button
- Encrypted .enc file copied to Downloads folder
- Status shows in real-time on DiagnosticsScreen

### 4. Clear Telemetry (via UI)
- From DiagnosticsScreen, tap "Clear Telemetry"
- CSV file deleted and reset with fresh header
- Ready for next physical test

## CSV Output Example

```
timestamp,event_type,peer_id,metric,status
2026-03-09T19:06:00.123Z,ROUTE_DISCOVERED,a1b2c3d4e5f6g7h,0,active
2026-03-09T19:06:01.456Z,HANDSHAKE_FAILED,x9y8z7w6v5u4t3s,0,shared_secret_derivation_failed
2026-03-09T19:06:02.789Z,PACKET_RELAYED,m1n2o3p4q5r6s7t,0,relay_to:a1b2c3d4
2026-03-09T19:06:03.012Z,ROUTE_DROPPED,b2c3d4e5f6g7h8i,0,inactive
2026-03-09T19:06:04.345Z,CONNECTION_LOST,c3d4e5f6g7h8i9j,0,peer_timeout
```

## Performance Profile

- Event Buffer: 10 entries
- Auto-Flush: Every 5 seconds OR when buffer full
- Thread-Safe: Yes (uses RLock)
- Disk I/O: Minimal, buffered writes
- Memory Impact: ~2KB per 100 events

## Encryption Details

- Algorithm: AES-GCM
- Key Material: b'ghostnet_diagnostic_export_key_2024'
- KDF: HKDF-SHA256
- Nonce: 12 random bytes (prepended to ciphertext)
- Authentication: Built-in with GCM mode

## File Locations

### Android
- Logs: `/data/data/org.ghostnet/mission_telemetry.csv`
- Encrypted Export: `/sdcard/Download/mission_telemetry_YYYYMMDD_HHMMSS.enc`

### Desktop
- Logs: `~/.ghostnet/mission_telemetry.csv`
- Encrypted Export: `~/Downloads/mission_telemetry_YYYYMMDD_HHMMSS.enc`

## Integration Hooks (Copy-Paste Ready)

### In network.py (GhostEngine)
```python
from telemetry_logger import get_telemetry_logger

class GhostEngine:
    def __init__(self, username: str = None, ...):
        ...
        self.telemetry = get_telemetry_logger()
    
    def on_peer_discovered(self, peer_id, rssi=0):
        self.telemetry.log_route_discovered(peer_id, metric=rssi)
    
    def on_peer_lost(self, peer_id):
        self.telemetry.log_connection_lost(peer_id, reason='discovery_timeout')
```

### In routing.py (RoutingTable)
```python
from telemetry_logger import get_telemetry_logger

class RoutingTable:
    def __init__(self, max_route_age: float = 30.0):
        ...
        self.telemetry = get_telemetry_logger()
    
    def add_route(self, destination_id: str, next_hop_id: str, metric: int, hops: List[str]):
        if metric > 15:
            return False
        
        with self.lock:
            if destination_id not in self.routes:
                self.routes[destination_id] = RouteEntry(...)
                self.telemetry.log_route_discovered(destination_id, metric=metric)
                self.table_version += 1
                return True
        return False
    
    def remove_stale_routes(self):
        with self.lock:
            stale_peers = []
            for peer_id in [...]:
                del self.routes[peer_id]
                self.telemetry.log_route_dropped(peer_id)
                stale_peers.append(peer_id)
        return stale_peers
```

### In connection_manager.py (P2PConnection)
```python
from telemetry_logger import get_telemetry_logger

class P2PConnection:
    def __init__(self, peer_id: str, peer_info: Dict, ...):
        ...
        self.telemetry = get_telemetry_logger()
    
    def _perform_ecdh_handshake(self, sock: socket.socket) -> bool:
        try:
            ...
            if not shared_secret:
                self.telemetry.log_handshake_failed(self.peer_id, reason='shared_secret_failed')
                return False
            
            aes_key = self.crypto_manager.derive_aes_key(self.peer_id, shared_secret)
            if not aes_key:
                self.telemetry.log_handshake_failed(self.peer_id, reason='aes_key_failed')
                return False
            
            self.session_key = aes_key
            return True
        except Exception as e:
            self.telemetry.log_handshake_failed(self.peer_id, reason=str(e)[:40])
            return False
```

## Decryption (Post-Mission)

```bash
openssl enc -d -aes-256-gcm -in mission_telemetry_20260309_190650.enc -K <derived_key> -iv <nonce> -out telemetry.csv
```

Or use Python:
```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend

diagnostic_key_material = b'ghostnet_diagnostic_export_key_2024'
hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'diagnostic_salt', info=b'telemetry_encryption', backend=default_backend())
derived_key = hkdf.derive(diagnostic_key_material)

with open('mission_telemetry_20260309_190650.enc', 'rb') as f:
    nonce = f.read(12)
    ciphertext = f.read()

cipher = AESGCM(derived_key)
plaintext = cipher.decrypt(nonce, ciphertext, None)

with open('telemetry.csv', 'wb') as f:
    f.write(plaintext)
```

## Analysis Tips

After decryption, import mission_telemetry.csv into analysis tools:

Python (pandas):
```python
import pandas as pd
df = pd.read_csv('telemetry.csv')
route_discoveries = df[df['event_type'] == 'ROUTE_DISCOVERED']
handshake_failures = df[df['event_type'] == 'HANDSHAKE_FAILED']
packet_relays = df[df['event_type'] == 'PACKET_RELAYED']
```

Spreadsheet Applications:
1. Open mission_telemetry.csv in Excel/LibreOffice
2. Create pivot tables for event frequency
3. Timeline charts for connection stability
4. Peer analysis for network topology

## Compliance Checklist

- [x] NO comments in Python code (OPSEC requirement)
- [x] Thread-safe file operations
- [x] Buffered I/O (minimal bottleneck)
- [x] AES-GCM encryption before export
- [x] Android-compatible paths
- [x] CSV format (vendor-neutral)
- [x] Timestamp in ISO 8601 UTC
- [x] Peer IDs truncated (16 chars max)
- [x] Status < 50 chars
- [x] Real-time UI feedback

## Troubleshooting

### Logs not showing up
- Check `~/.ghostnet/mission_telemetry.csv` exists
- Verify telemetry = get_telemetry_logger() called
- Check log_event() calls in integration points

### Export fails
- Ensure write permissions to Downloads folder
- Check available disk space
- Verify cryptography library installed

### Clear not working
- Confirm app has write access to app data directory
- Check file isn't locked by another process

## Notes

- Logging is silent (no print statements)
- Events logged in background threads
- Buffer automatically flushed on app close
- Encryption key is hardcoded (OPSEC approved)
- CSV handles special characters in peer IDs
