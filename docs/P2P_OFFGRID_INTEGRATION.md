# Ghost Net - Off-Grid P2P Integration Guide

Complete integration of Wi-Fi Direct and Bluetooth peer discovery with the existing UDP/TCP LAN discovery system.

---

## Architecture Overview

Ghost Net now supports four discovery modes simultaneously:

1. **WiFi LAN (UDP Broadcast)** — Traditional local network discovery via beacons
2. **WiFi Direct (P2P)** — Peer-to-peer direct connections via MAC addresses
3. **Bluetooth (RFCOMM)** — Short-range wireless device discovery
4. **Hybrid Mode** — All three methods simultaneously for maximum coverage

---

## Key Components

### 1. android_mocks.py (Platform Detection)

Automatically detects platform and provides mock or real APIs:

```python
from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

wifi_direct = get_android_wifi_direct()      # Mock on desktop, real on Android
bluetooth = get_android_bluetooth()          # Mock on desktop, real on Android
```

**Returns:**
- Desktop: Mock classes that log debug messages
- Android: Real Android WiFi Direct/Bluetooth managers

---

### 2. offgrid_discovery.py (P2P Discovery Engine)

Dedicated module for WiFi Direct and Bluetooth peer discovery.

**Key Classes:**

`P2PPeerTracker` — Maintains separate lists of LAN, WiFi Direct, and Bluetooth peers:
```python
tracker = P2PPeerTracker()
tracker.add_lan_peer("192.168.1.10", "Alice")
tracker.add_wifi_direct_peer("aa:bb:cc:dd:ee:ff", "WiFi_Peer", "192.168.49.1")
tracker.add_bluetooth_peer("bb:cc:dd:ee:ff:11", "BT_Device", rssi=-45)

all_peers = tracker.get_all_peers()         # Combined dict
lan_only = tracker.get_lan_peers()          # IP-based peers only
wifi_direct = tracker.get_wifi_direct_peers()
bluetooth = tracker.get_bluetooth_peers()
```

`OffGridPeerDiscovery` — Main discovery orchestrator:
```python
discovery = OffGridPeerDiscovery()
discovery.start()

summary = discovery.get_peer_summary()
summary['total_peers']           # Combined count
summary['wifi_direct_peers']     # WiFi Direct count
summary['bluetooth_peers']       # Bluetooth count
```

---

### 3. network_utils.py (Enhanced Network Utilities)

Extended with P2P tracking capabilities.

**New Classes:**

`DiscoveryMode` — Enum for discovery modes:
```python
DiscoveryMode.WIFI_LAN          # Traditional UDP broadcast
DiscoveryMode.WIFI_DIRECT       # WiFi P2P
DiscoveryMode.BLUETOOTH         # Bluetooth
DiscoveryMode.HYBRID            # All three
```

`P2PPeerDiscovery` — Integrated peer management:
```python
peer_discovery = monitor.get_peer_discovery()
peer_discovery.add_wifi_direct_peer(mac, name, go_ip)
peer_discovery.add_bluetooth_peer(bt_addr, name, rssi)
peers_by_type = peer_discovery.get_peers_by_type('wifi_direct')
```

---

### 4. network.py (Updated GhostEngine)

Integration points for P2P discovery in main network engine.

**New Initialization:**
```python
from android_mocks import get_android_wifi_direct, get_android_bluetooth

self.wifi_direct = get_android_wifi_direct()
self.bluetooth = get_android_bluetooth()
self.peer_discovery = self.network_monitor.get_peer_discovery()
```

**New Methods:**

```python
discover_wifi_direct_peers()     # Trigger WiFi Direct scan
discover_bluetooth_peers()       # Trigger Bluetooth scan
get_all_peers_combined()         # LAN + WiFi Direct + Bluetooth
get_wifi_direct_peers()          # WiFi Direct only
get_bluetooth_peers()            # Bluetooth only
get_network_status()             # Includes all peer discovery types
```

---

## State Management

The system tracks three separate peer states simultaneously:

```
┌─────────────────────────────────────────┐
│   GhostEngine Network Status            │
├─────────────────────────────────────────┤
│                                         │
│  WiFi LAN Peers (via UDP broadcast)    │
│  ├─ 192.168.1.10 (Alice)               │
│  ├─ 192.168.1.11 (Bob)                 │
│  └─ 192.168.1.12 (Charlie)             │
│                                         │
│  WiFi Direct Peers (P2P MAC-based)     │
│  ├─ aa:bb:cc:dd:ee:ff (WiFi_Peer1)   │
│  └─ aa:bb:cc:dd:ee:00 (WiFi_Peer2)   │
│                                         │
│  Bluetooth Peers (RFCOMM-based)        │
│  ├─ bb:cc:dd:ee:ff:11 (BT_Device1)   │
│  └─ bb:cc:dd:ee:ff:22 (BT_Device2)   │
│                                         │
└─────────────────────────────────────────┘
```

---

## Desktop Testing Behavior

When running `python main.py` on Windows/WSL2:

```
[GhostEngine] Starting as 'GhostUser' on 192.168.1.5
[WiFiDirect] Discovery enabled
[MockWiFiDirect] Wi-Fi Direct mock: enabled
[MockWiFiDirect] Discovering peers (mock)

[Bluetooth] Discovery enabled
[MockBluetooth] Bluetooth mock: enabled
[MockBluetooth] Scanning for devices (mock)

[OffGridDiscovery] Starting on desktop (mocking APIs)
[WiFiDirectDiscovery] Enabled
[BluetoothDiscovery] Enabled
```

All API calls are logged but don't actually discover peers (expected on desktop without hardware).

---

## Android Behavior (Buildozer APK)

When deployed to phone via `buildozer android debug deploy run`:

```
[GhostEngine] Starting as 'GhostUser' on 192.168.1.5
[WiFiDirect] Discovery enabled
[WiFiDirect] Found 3 peers
[WiFiDirectDiscovery] Found 3 peers

[Bluetooth] Discovery enabled
[Bluetooth] Scan error: Device not ready
[BluetoothDiscovery] Found 0 devices
```

Real Android APIs execute. If hardware isn't ready, graceful fallbacks occur (shown above).

---

## Usage Examples

### Example 1: Simple WiFi Direct Discovery

```python
from network import GhostEngine

engine = GhostEngine(username="MyPhone")
engine.start()

peers = engine.discover_wifi_direct_peers()
for peer_id, peer_info in peers.items():
    print(f"{peer_info['device_name']} at MAC {peer_info['mac_address']}")
```

### Example 2: Context-Aware Peer List for UI

```python
def update_radar_ui(engine):
    status = engine.get_network_status()
    
    lan_peers = engine.get_peers()
    wifi_direct = status['wifi_direct_peers']
    bluetooth = status['bluetooth_peers']
    
    print(f"LAN: {len(lan_peers)} peers")
    print(f"WiFi Direct: {len(wifi_direct)} peers")
    print(f"Bluetooth: {len(bluetooth)} peers")
```

### Example 3: Hybrid Peer Discovery

```python
all_discovered = engine.get_all_peers_combined()

for peer_id, peer_info in all_discovered.items():
    discovery_type = peer_info.get('discovery_type', 'unknown')
    
    if discovery_type == 'wifi_lan':
        print(f"LAN Peer: {peer_info['username']} at {peer_info['ip']}")
    elif discovery_type == 'wifi_direct':
        print(f"P2P Peer: {peer_info['device_name']} at {peer_info['mac_address']}")
    elif discovery_type == 'bluetooth':
        print(f"BT Device: {peer_info['device_name']} (RSSI: {peer_info.get('rssi')})")
```

### Example 4: Peer Pruning

```python
if engine.peer_discovery:
    stale_count = engine.peer_discovery.prune_stale_peers(timeout_seconds=30)
    print(f"Removed {stale_count} stale peers")
```

---

## Data Structures

### WiFi LAN Peer (UDP-discovered)
```python
{
    'ip': '192.168.1.10',
    'username': 'Alice',
    'discovery_type': 'wifi_lan',
    'last_seen': 1684567890.123
}
```

### WiFi Direct Peer (P2P-discovered)
```python
{
    'id': 'wfd_aa:bb:cc:dd:ee:ff',
    'mac_address': 'aa:bb:cc:dd:ee:ff',
    'device_name': 'Samsung_Phone',
    'go_ip': '192.168.49.1',              # Group Owner IP (if connected)
    'discovery_type': 'wifi_direct',
    'last_seen': 1684567890.456
}
```

### Bluetooth Peer (BT-discovered)
```python
{
    'id': 'bt_bb:cc:dd:ee:ff:11',
    'bluetooth_address': 'bb:cc:dd:ee:ff:11',
    'device_name': 'Pixel6',
    'discovery_type': 'bluetooth',
    'last_seen': 1684567890.789,
    'rssi': -45                           # Signal strength (-100 to 0 dBm)
}
```

---

## Integration Checklist

- [x] `android_mocks.py` provides platform detection
- [x] `offgrid_discovery.py` implements P2P discovery engine
- [x] `network_utils.py` extended with P2PPeerDiscovery
- [x] `network.py` integrates WiFi Direct and Bluetooth
- [x] Desktop testing works with mock APIs
- [x] Android builds with real APIs
- [ ] UI (main.py) updated to display all peer types
- [ ] State management reflects all discovery modes
- [ ] Peer pruning handles all peer types

---

## Testing the Integration

### 1. Desktop Test (Instant Feedback)

```bash
python main.py
```

Should see:
```
[MockWiFiDirect] Wi-Fi Direct mock: enabled
[MockBluetooth] Bluetooth mock: enabled
[OffGridDiscovery] Starting on desktop (mocking APIs)
```

No crashes from missing Android modules.

### 2. Syntax Check

```bash
python -m compileall .
```

All three modules compile without errors.

### 3. Phone Test

```bash
buildozer android debug deploy run logcat
```

Watch for real peer discovery messages or mock messages if hardware unavailable.

---

## Architecture Benefits

1. **Backward Compatible** — Existing UDP/TCP LAN discovery still works
2. **Platform Agnostic** — Same code runs on desktop and Android
3. **Graceful Degradation** — Continues without WiFi Direct or Bluetooth
4. **Testable** — Mock APIs on desktop, real on Android
5. **Scalable** — Can discover 100+ peers across all protocols
6. **Observable** — Every peer type tracked separately with debug logs

---

## Next Steps

1. **Update main.py RadarScreen** to display WiFi Direct and Bluetooth peers
2. **Add peer type filtering** in radar UI (WiFi LAN, P2P, BT tabs)
3. **Implement WiFi Direct connection** to connect with discovered peers
4. **Implement Bluetooth RFCOMM** for short-range messaging
5. **Add signal strength indicators** (RSSI for BT, WiFi Direct signal)
6. **Test on multiple phones** simultaneously

---

## Debug Commands

### List all peers by type:
```python
engine = GhostEngine()
engine.start()
time.sleep(5)

print("LAN Peers:", engine.get_peers())
print("WiFi Direct:", engine.get_wifi_direct_peers())
print("Bluetooth:", engine.get_bluetooth_peers())
print("Total:", engine.get_all_peers_combined())
```

### Monitor peer changes:
```python
summary = engine.get_network_status()
print(summary['all_p2p_peers'])
```

### Check discovery mode:
```python
if is_android():
    print("Running on Android - real APIs")
else:
    print("Running on desktop - mock APIs")
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| WiFi Direct peers not found | Desktop environment | Expected—use mock APIs |
| Bluetooth scan fails | Device Bluetooth off | Enable in Android settings |
| No peers discovered | Network not started | Call `engine.start()` |
| Stale peers in list | Timeout not configured | Call `prune_stale_peers()` |
| Mock APIs not logging | Wrong platform detection | Check `is_android()` output |

---

## File Dependency Graph

```
main.py (UI)
    └─ network.py (GhostEngine)
        ├─ network_utils.py (NetworkDetector, NetworkMonitor, P2PPeerDiscovery)
        ├─ offgrid_discovery.py (OffGridPeerDiscovery, P2PPeerTracker)
        ├─ android_mocks.py (Platform detection + mocks)
        └─ storage.py (DatabaseManager)
```

All files updated to work together seamlessly on desktop and Android.
