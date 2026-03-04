# Ghost Net P2P Modules - Developer Quick Reference

**Last Updated:** March 4, 2026  
**API Level:** Android 21-33+  
**Status:** Production Ready ✅

---

## 📦 MODULES AT A GLANCE

| Module | Purpose | Lines | Classes | Key Feature |
|--------|---------|-------|---------|-------------|
| [`android_wifi_direct.py`](android_wifi_direct.py) | Wi-Fi Direct P2P | 644 | 3 | Peer discovery + Group Owner IP |
| [`android_bluetooth.py`](android_bluetooth.py) | Bluetooth RFCOMM | 815 | 5 | RFCOMM sockets + auto-reconnect |
| [`android_permissions.py`](android_permissions.py) | Runtime Permissions | 438 | 3 | API 33+ compliance + fallback |
| [`p2p_platform_adapter.py`](p2p_platform_adapter.py) | Unified Interface | 625 | 3 | Multi-channel + deduplication |

---

## 🚀 GETTING STARTED (5 MINUTES)

### Step 1: Test Locally
```bash
python test_p2p_modules.py
# All tests pass, pyjnius gracefully unavailable on desktop
```

### Step 2: Add to main.py
```python
from p2p_platform_adapter import P2PPlatformAdapter

class GhostApp(MDApp):
    def on_start(self):
        # Initialize adapter
        self.p2p_adapter = P2PPlatformAdapter(
            on_peer_discovered=self.on_peer_discovered,
            on_peer_connected=self.on_peer_connected,
            on_error=self.on_p2p_error
        )
        
        # Request permissions first
        self.p2p_adapter.request_required_permissions()
        
        # Start discovery
        self.p2p_adapter.start_discovery()
    
    def on_peer_discovered(self, peer_dict):
        # peer_dict has: peer_id, device_name, channels, is_connected, etc.
        print(f"Found: {peer_dict['device_name']}")
    
    def on_peer_connected(self, peer_id, channel):
        print(f"Connected via {channel.value}")
    
    def on_p2p_error(self, error_msg):
        print(f"Error: {error_msg}")
```

### Step 3: Build & Test
```bash
buildozer android debug
buildozer android debug deploy run
```

---

## 🎯 COMMON TASKS

### Task 1: Start Peer Discovery
```python
success = self.p2p_adapter.start_discovery()
# Callback: on_peer_discovered(peer_dict) when peers found
```

### Task 2: Connect to Peer
```python
# Automatic channel selection
self.p2p_adapter.connect_to_peer(peer_id="AA:BB:CC:DD:EE:FF")

# Or prefer Wi-Fi Direct
from p2p_platform_adapter import P2PChannel
self.p2p_adapter.connect_to_peer(
    peer_id="AA:BB:CC:DD:EE:FF",
    preferred_channel=P2PChannel.WIFI_DIRECT
)
# Callback: on_peer_connected(peer_id, channel)
```

### Task 3: Send Data via Wi-Fi Direct
```python
# After connection via Wi-Fi Direct, use existing GhostEngine
peer_ip = self.p2p_adapter.get_peer(peer_id)['ip_addresses'][P2PChannel.WIFI_DIRECT]
self.ghost_engine.send_message(peer_ip, "Hello!")
```

### Task 4: Send Data via Bluetooth
```python
# Setup data callback when connecting
def setup_bluetooth(addr):
    self.p2p_adapter.bluetooth_manager.on_data = self.on_bt_data

def on_bt_data(device_addr, data):
    # data = [4-byte length][encrypted message]
    msg_len = struct.unpack('>I', data[:4])[0]
    encrypted_msg = data[4:4+msg_len]
    self.ghost_engine.process_encrypted_message(encrypted_msg)

# To send via Bluetooth
self.p2p_adapter.bluetooth_manager.send_to_device(
    device_addr, 
    b"encrypted_message"
)
```

### Task 5: Check Feature Availability
```python
wifi_available, reason = self.p2p_adapter.permission_manager.check_feature_available('wifi_direct')
if wifi_available:
    print("Wi-Fi Direct ready")
else:
    print(f"Not available: {reason}")
```

### Task 6: List All Peers
```python
peers = self.p2p_adapter.get_peers()
for peer in peers:
    print(f"{peer['device_name']} - {peer['channels']}")
```

### Task 7: Disconnect
```python
self.p2p_adapter.disconnect_from_peer(peer_id)
```

### Task 8: Cleanup on Exit
```python
def on_stop(self):
    self.ghost_engine.stop()
    self.p2p_adapter.shutdown()
```

---

## 📊 CALLBACKS & DATA STRUCTURES

### on_peer_discovered(peer_dict)
```python
peer_dict = {
    'peer_id': 'AA:BB:CC:DD:EE:FF',           # Unique ID
    'device_name': "John's Phone",            # Display name
    'channels': ['wifi_direct', 'bluetooth'], # Available on
    'ip_addresses': {
        'wifi_direct': '192.168.49.1',
        # 'bluetooth': <socket object>
    },
    'signal_strength': -50,                   # Best signal
    'is_connected': False,                    # Connection state
    'last_seen': 1700000000.0,               # Timestamp
    'metadata': {}                            # Extra data
}
```

### on_peer_connected(peer_id, channel)
```python
# Called when connection established
peer_id = 'AA:BB:CC:DD:EE:FF'
channel = P2PChannel.WIFI_DIRECT  # or P2PChannel.BLUETOOTH
```

### on_channel_state_changed(channel, state)
```python
# Track channel lifecycle
channel = P2PChannel.WIFI_DIRECT
state = P2PChannelState.CONNECTED  # IDLE, DISCOVERING, etc.
```

### on_error(error_msg)
```python
# Handle errors gracefully
error_msg = "Wi-Fi Direct disabled due to missing permissions"
```

---

## 🔑 KEY CLASSES

### P2PPlatformAdapter (Main)
```python
adapter = P2PPlatformAdapter(
    on_peer_discovered=callback,
    on_peer_connected=callback,
    on_error=callback
)

# Key methods:
adapter.request_required_permissions()      # Request Android permissions
adapter.start_discovery()                   # Start on all channels
adapter.stop_discovery()                    # Stop all channels
adapter.connect_to_peer(peer_id, channel)  # Connect to peer
adapter.disconnect_from_peer(peer_id)      # Disconnect
adapter.get_peers()                        # List all peers
adapter.get_peer(peer_id)                  # Get specific peer
adapter.get_channel_state(channel)         # Channel state
adapter.shutdown()                         # Cleanup
```

### WiFiDirectManager
```python
# Automatically created by adapter
manager = adapter.wifi_direct_manager

manager.start_discovery()
manager.cancel_discovery()
manager.connect_to_peer(peer_address)
manager.disconnect()
manager.get_peers()
manager.get_group_owner_ip()
```

### BluetoothManager
```python
# Automatically created by adapter
manager = adapter.bluetooth_manager

manager.start_discovery()
manager.cancel_discovery()
manager.start_server()
manager.connect_to_device(device_address)
manager.send_to_device(device_address, data)
manager.disconnect_device(device_address)
manager.get_discovered_devices()
manager.get_paired_devices()
```

### PermissionManager
```python
# Automatically created by adapter
manager = adapter.permission_manager

manager.request_wifi_direct_permissions()
manager.request_bluetooth_permissions()
manager.check_permission('BLUETOOTH_SCAN')
manager.check_critical_permissions()
manager.check_feature_available('wifi_direct')
```

---

## 🔒 PERMISSIONS QUICK REFERENCE

```
API 33+ RUNTIME (request at startup):
  - NEARBY_WIFI_DEVICES                   (Wi-Fi Direct)
  - BLUETOOTH_SCAN                        (Bluetooth)
  - BLUETOOTH_CONNECT                     (Bluetooth)
  - ACCESS_FINE_LOCATION                  (Both)

API 1+ NORMAL (auto-granted if in manifest):
  - CHANGE_WIFI_STATE                     (Wi-Fi Direct)
  - ACCESS_WIFI_STATE                     (Wi-Fi Direct)
  - BLUETOOTH, BLUETOOTH_ADMIN            (Bluetooth)
  - INTERNET, ACCESS_NETWORK_STATE        (Network)
```

**In buildozer.spec:**
```
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,
    CHANGE_WIFI_MULTICAST_STATE,CHANGE_NETWORK_STATE,
    READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,WAKE_LOCK,
    NEARBY_WIFI_DEVICES,BLUETOOTH,BLUETOOTH_ADMIN,
    BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,
    ACCESS_COARSE_LOCATION,CHANGE_WIFI_STATE,LOCAL_MAC_ADDRESS
```

---

## ⚡ PERFORMANCE TIPS

1. **Disable Unused Channels**
   ```python
   adapter.enabled_channels.discard(P2PChannel.BLUETOOTH)
   ```

2. **Increase Discovery Timeout for Slow Networks**
   ```python
   adapter.wifi_direct_manager.DISCOVERY_TIMEOUT = 60  # seconds
   ```

3. **Stop Discovery When Not Needed**
   ```python
   adapter.stop_discovery()  # Saves battery & CPU
   ```

4. **Reuse Connections**
   ```python
   # Keep socket open for multiple messages instead of reconnecting
   peer_ip = adapter.get_peer(peer_id)['ip_addresses'][P2PChannel.WIFI_DIRECT]
   # Use for sending multiple messages
   ```

5. **Increase Chunk Size for Large Files**
   ```python
   # In android_bluetooth.py, increase chunk_size parameter
   bluetooth_manager.send_file(path, chunk_size=16384)  # 16KB chunks
   ```

---

## 🐛 TROUBLESHOOTING QUICK FIXES

| Problem | Cause | Fix |
|---------|-------|-----|
| "No peers found" | Permission not granted | Call `request_wifi_direct_permissions()` |
| "Bluetooth fails to connect" | Device not discoverable | Ensure device has Bluetooth ON and is discoverable |
| "High CPU usage" | Discovery running continuously | Call `stop_discovery()` when not needed |
| "Messages dropped" | Socket buffer full | Reduce send rate or increase buffer |
| "Frequent disconnections" | Weak signal | Move devices closer or switch channel |
| "Permission denied dialog" | User declined | Show why permission needed, ask again |

**Full troubleshooting:** See [`P2P_IMPLEMENTATION_GUIDE.md`](P2P_IMPLEMENTATION_GUIDE.md) Section 5

---

## 📱 TESTING ON DEVICE

**Manual Test Procedure (2 devices):**

Device A:
1. Grant all permissions
2. Tap "Start Discovery"
3. Wait 5-10 seconds
4. Device B should appear

Device B:
1. Grant all permissions
2. Launch app (no tap needed)
3. Should appear in Device A's list

Test Connection:
1. Device A: Tap "Connect to Device B"
2. Should see "Connected via [channel]"
3. Send test message → Device B receives
4. Device B send message → Device A receives

---

## 📚 DOCUMENTATION MAP

| Document | Purpose | Link |
|----------|---------|------|
| **Quick Start** | 5-minute setup | This file ↑ |
| **Implementation Guide** | Detailed docs (1000+ lines) | [`P2P_IMPLEMENTATION_GUIDE.md`](P2P_IMPLEMENTATION_GUIDE.md) |
| **Delivery Summary** | Project overview | [`P2P_DELIVERY_SUMMARY.md`](P2P_DELIVERY_SUMMARY.md) |
| **Main README** | File manifest | [`P2P_MODULES_README.md`](P2P_MODULES_README.md) |
| **Code Comments** | Inline documentation | See source files |

---

## 🎯 CHANNEL SELECTION GUIDE

```
SITUATION                          RECOMMENDED CHANNEL
─────────────────────────────────────────────────────
High bandwidth needed              → Wi-Fi Direct
Max range required                 → Bluetooth + Wi-Fi Direct
Low power consumption              → Bluetooth
Corporate/managed network          → UDP fallback
Quick connection needed            → Wi-Fi Direct
Privacy/encryption critical        → Either (both supported)
File transfer >100MB               → Wi-Fi Direct
Text chat only                     → Bluetooth
Mobile hotspot unavailable         → Wi-Fi Direct + Bluetooth
```

---

## 🔧 API QUICK REFERENCE

### Enums
```python
from p2p_platform_adapter import P2PChannel, P2PChannelState
from android_wifi_direct import WiFiDirectState
from android_bluetooth import BluetoothState
from android_permissions import PermissionStatus, PermissionGroup

# Channel types
P2PChannel.WIFI_DIRECT
P2PChannel.BLUETOOTH
P2PChannel.UDP_BROADCAST
P2PChannel.TCP_SOCKET

# Channel states
P2PChannelState.IDLE
P2PChannelState.DISCOVERING
P2PChannelState.DISCOVERED
P2PChannelState.CONNECTING
P2PChannelState.CONNECTED
P2PChannelState.ERROR
P2PChannelState.DISABLED
```

### Standard UUIDs
```python
# Bluetooth service UUID (Ghost Net standard)
GHOST_NET_SERVICE_UUID = "447d5f51-7a8b-4d6f-a9c2-1234567890ab"

# Wi-Fi Direct: android.net.wifi.p2p.WifiP2pManager
# Bluetooth: android.bluetooth.BluetoothAdapter
```

### Port Numbers (GhostEngine)
```python
UDP_BROADCAST = 37020  # Peer discovery beacons
TCP_MESSAGING = 37021  # Encrypted message transmission
```

---

## 💬 CODE EXAMPLES

### Example 1: Complete Integration
```python
from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel
from kivymd.app import MDApp

class GhostApp(MDApp):
    def on_start(self):
        # Initialize
        self.p2p = P2PPlatformAdapter(
            on_peer_discovered=self.peer_found,
            on_peer_connected=self.peer_connected,
            on_error=self.show_error
        )
        
        # Request & start
        self.p2p.request_required_permissions()
        self.p2p.start_discovery()
    
    def peer_found(self, peer_dict):
        print(f"Found: {peer_dict['device_name']}")
        # Update UI with peer
    
    def peer_connected(self, peer_id, channel):
        print(f"Connected via {channel.value}")
        # Show connected state in UI
    
    def show_error(self, msg):
        print(f"Error: {msg}")
        # Show error dialog to user
    
    def on_stop(self):
        self.p2p.shutdown()
```

### Example 2: Send Message via Best Available Channel
```python
def send_message(self, peer_id, message):
    peer = self.p2p.get_peer(peer_id)
    
    if P2PChannel.WIFI_DIRECT in peer['ip_addresses']:
        # Use Wi-Fi Direct
        ip = peer['ip_addresses'][P2PChannel.WIFI_DIRECT]
        self.ghost_engine.send_message(ip, message)
    elif P2PChannel.BLUETOOTH in peer['ip_addresses']:
        # Use Bluetooth
        self.p2p.bluetooth_manager.send_to_device(peer_id, message.encode())
```

### Example 3: File Transfer
```python
def send_file_to_peer(self, peer_id, file_path):
    peer = self.p2p.get_peer(peer_id)
    
    if P2PChannel.BLUETOOTH in peer['ip_addresses']:
        # Bluetooth file transfer
        success = self.p2p.bluetooth_manager.clients[peer_id].send_file(
            file_path,
            chunk_size=8192
        )
        return success
    elif P2PChannel.WIFI_DIRECT in peer['ip_addresses']:
        # Wi-Fi Direct - use existing GhostEngine file protocol
        ip = peer['ip_addresses'][P2PChannel.WIFI_DIRECT]
        return self.ghost_engine.send_file(ip, file_path)
```

---

## ✅ DEPLOYMENT CHECKLIST

- [ ] Test locally: `python test_p2p_modules.py`
- [ ] Add P2PPlatformAdapter to main.py
- [ ] Handle callbacks: on_peer_discovered, on_peer_connected
- [ ] Request permissions on app start
- [ ] Build APK: `buildozer android debug`
- [ ] Test on device with 2+ devices
- [ ] Verify Wi-Fi Direct discovery works
- [ ] Verify Bluetooth discovery works
- [ ] Test message transmission both directions
- [ ] Check battery impact (idle < 5mA)
- [ ] Verify no UI blocking during discovery
- [ ] Release: `buildozer android release`

---

## 🆘 SUPPORT

**Found a bug?** Check the source code comments - they're comprehensive.

**Need help?** See:
1. [`P2P_IMPLEMENTATION_GUIDE.md`](P2P_IMPLEMENTATION_GUIDE.md) - Detailed docs
2. Module docstrings - Comprehensive class/method documentation
3. Example code - Multiple real-world examples above
4. Test suite - See how modules are used in [`test_p2p_modules.py`](test_p2p_modules.py)

**Want to extend?** All modules are modular and can be extended independently.

---

**Last Updated:** March 4, 2026  
**Status:** ✅ Production Ready  
**Support:** Full documentation included
