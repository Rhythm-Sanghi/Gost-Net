"""
GHOST NET P2P MODULES - COMPREHENSIVE IMPLEMENTATION GUIDE
Android Wi-Fi Direct & Bluetooth Integration for Offline-First P2P Communication

VERSION: 1.0.0
API LEVEL: 33+ (with fallbacks to API 21+)
LAST UPDATED: 2026-03-04
"""

# ============================================================================
# SECTION 1: OVERVIEW
# ============================================================================

"""
OBJECTIVE:
Enable Ghost Net with true internet-free peer-to-peer communication via:
1. Wi-Fi Direct (Android P2P) - Direct device-to-device Wi-Fi connections
2. Bluetooth RFCOMM - Classic Bluetooth socket connections
3. UDP Broadcast + TCP - Legacy fallback for broader compatibility

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────┐
│                    Ghost Net Kivy UI (main.py)                   │
├─────────────────────────────────────────────────────────────────┤
│                  P2P Platform Adapter                            │
│          (p2p_platform_adapter.py - Unified Interface)          │
├─────────────────────────────────────────────────────────────────┤
│  WiFiDirect  │  Bluetooth  │  Permissions  │  GhostEngine (TCP) │
│  Manager     │  Manager    │  Manager      │  (Existing)        │
├─────────────────────────────────────────────────────────────────┤
│                   Android Hardware APIs (pyjnius)               │
│  android.net.wifi.p2p  │  android.bluetooth  │  Android Perms   │
└─────────────────────────────────────────────────────────────────┘

KEY DESIGN PRINCIPLES:
✓ Non-blocking, threaded operations (no UI thread blocking in Kivy)
✓ Comprehensive error handling with logging
✓ Graceful degradation for unsupported APIs or denied permissions
✓ Thread-safe peer management across multiple channels
✓ Automatic fallback when primary channel unavailable
✓ Modular architecture enabling independent testing
✓ Clear Java-to-Python marshaling documentation via pyjnius
"""

# ============================================================================
# SECTION 2: MODULE DESCRIPTIONS
# ============================================================================

"""
MODULE 1: android_wifi_direct.py (644 lines)
─────────────────────────────────────────────────────────────────────

PURPOSE:
Encapsulates Android Wi-Fi Direct (P2P) functionality with complete
peer discovery, connection establishment, and group owner resolution.

KEY CLASSES:

1. WiFiDirectState (Enum)
   - IDLE: Not doing anything
   - DISCOVERING: Active peer discovery
   - PEERS_FOUND: Peers discovered, waiting for action
   - CONNECTING: Attempting connection to peer
   - CONNECTED: Active connection established
   - GROUP_FORMED: P2P group established with IP
   - ERROR: Error occurred

2. WiFiPeer (@dataclass)
   - device_name: Human-readable peer name
   - device_address: MAC address (AA:BB:CC:DD:EE:FF)
   - is_group_owner: Whether this peer is group owner
   - ip_address: Assigned IP if connected
   - signal_level: Signal strength indicator
   
   Methods: to_dict() for serialization

3. WiFiDirectBroadcastReceiver (PythonJavaClass)
   - Implements android/content/BroadcastReceiver
   - Listens for Android system Wi-Fi P2P events
   - Three critical intents:
     * WIFI_P2P_STATE_CHANGED: P2P enabled/disabled
     * WIFI_P2P_PEERS_CHANGED: Peer list updated
     * WIFI_P2P_CONNECTION_CHANGED: Connection state
   - Thread-safe event queue for main manager
   
   KEY METHOD: onReceive(context, intent) - Called by Android system

4. WiFiDirectManager (Main Manager)
   
   DISCOVERY:
   - start_discovery() - Initiates peer discovery with exponential backoff
   - cancel_discovery() - Stops active discovery
   - _discovery_loop() - Background retry logic (max 5 retries)
   
   CONNECTION:
   - connect_to_peer(peer_address) - Connect to specific peer
   - _request_connection_info() - Get Group Owner IP after connect
   
   STATE MANAGEMENT:
   - Thread-safe state machine with _change_state()
   - Callbacks for peer discovered, connected, errors
   - Non-blocking background event loop
   
   TIMEOUT HANDLING:
   - Discovery timeout: 30 seconds
   - Connection timeout: 15 seconds
   - Peer stale timeout: 10 seconds
   - Exponential backoff: 1s → 16s max
   
   ERROR RECOVERY:
   - Automatic retry on discovery failure
   - Connection fallback options
   - Graceful handling of missing pyjnius

INTEGRATION WITH GhostEngine:
After Wi-Fi Direct group forms and Group Owner IP is resolved:
1. Obtain IP from _request_connection_info()
2. Accept connection or establish TCP socket to GO:37021
3. Use existing GhostEngine for encrypted message transmission
4. Multicast UDP discovery still functional on local network


MODULE 2: android_bluetooth.py (815 lines)
─────────────────────────────────────────────────────────────────────

PURPOSE:
Complete Bluetooth RFCOMM implementation supporting device discovery,
pairing workflows, and bidirectional socket communication.

KEY CLASSES:

1. BluetoothState (Enum)
   - IDLE: No operations
   - DISCOVERING: Active device scan
   - DEVICES_FOUND: Devices discovered
   - PAIRING: Pairing in progress
   - PAIRED: Device paired
   - CONNECTING: Attempting RFCOMM connection
   - CONNECTED: Active RFCOMM connection
   - LISTENING: Server accepting connections
   - ERROR: Error occurred

2. BluetoothDevice (@dataclass)
   - device_name: Bluetooth device name
   - device_address: MAC address
   - device_class: Device class code (e.g., phone, headset)
   - is_paired: Whether already paired
   - rssi: Signal strength (-100 to -30 dBm)
   
   Methods: to_dict() for serialization

3. BluetoothBroadcastReceiver
   - Listens for Bluetooth system events:
     * ACTION_DISCOVERY_STARTED/FINISHED
     * ACTION_FOUND: New device found
     * ACTION_BOND_STATE_CHANGED: Pairing/unpairing
     * ACTION_PAIRING_REQUEST: User pairing prompt

4. BluetoothRFCOMMServer (Threading)
   - Listens for incoming RFCOMM connections
   - Uses listenUsingInsecureRfcommWithServiceRecord
   - Service UUID: "447d5f51-7a8b-4d6f-a9c2-1234567890ab"
   - Handles multiple concurrent clients
   
   KEY METHODS:
   - run() - Main server loop (daemon thread)
   - _accept_connections() - Wait for incoming connections
   - _handle_client_data() - Read from connected clients
   - send_data(device_addr, data) - Send framed data
   
   FRAME FORMAT: [4-byte length][data...]
   
5. BluetoothRFCOMMClient
   - Connects to remote device
   - Uses createInsecureRfcommSocketToServiceRecord
   - Handles automatic reconnection with exponential backoff
   
   KEY METHODS:
   - connect() - Establish connection (blocking)
   - _read_loop() - Receive data in background thread
   - send_data(data) - Send framed data
   - send_text(text) - Send UTF-8 text
   - send_file(file_path) - Transfer file with progress
   
   RECONNECTION:
   - Automatic retry up to 10 times
   - Exponential backoff: 1s → 32s max
   - Callback on successful reconnection
   
6. BluetoothManager (Main Manager)
   
   DISCOVERY:
   - start_discovery() - Begin device scan
   - cancel_discovery() - Stop scanning
   - get_discovered_devices() - List found devices
   - get_paired_devices() - List already paired devices
   
   PAIRING:
   - pair_device(address) - Initiate pairing
   - unpair_device(address) - Remove pairing
   
   SERVER:
   - start_server() - Enable RFCOMM server listening
   
   CLIENT:
   - connect_to_device(address) - Initiate connection
   - send_to_device(address, data) - Send data to peer
   - disconnect_device(address) - Close connection

INTEGRATION WITH GhostEngine:
After RFCOMM connection established:
1. Use send_data() for encrypted message frames
2. on_data callback receives binary message frames
3. Parse frames and hand to GhostEngine message handler
4. File transfers handled natively via send_file()


MODULE 3: android_permissions.py (438 lines)
─────────────────────────────────────────────────────────────────────

PURPOSE:
Runtime permission request and checking for API 33+ compliance.
Manages permission groups, request dialogs, and graceful fallback.

KEY CLASSES:

1. PermissionStatus (Enum)
   - GRANTED: Permission confirmed granted
   - DENIED: Permission explicitly denied
   - PENDING: Request in progress
   - NOT_AVAILABLE: Not required on this API

2. PermissionGroup (Enum)
   - WIFI_P2P: Wi-Fi Direct permissions
   - BLUETOOTH: Bluetooth permissions
   - LOCATION: Location permissions
   - STORAGE: File access permissions

3. PermissionConfig (@dataclass)
   - name: Full permission string
   - min_api: Minimum API level required
   - group: Associated permission group
   - critical: If denied, disables feature
   - fallback_message: User-friendly error message

4. PERMISSION_DEFINITIONS (Dict)
   
   WIFI_P2P GROUP:
   - NEARBY_WIFI_DEVICES (API 33+, runtime)
   - CHANGE_WIFI_STATE (API 1+)
   - ACCESS_WIFI_STATE (API 1+)
   - LOCAL_MAC_ADDRESS (API 33+)
   
   BLUETOOTH GROUP:
   - BLUETOOTH_SCAN (API 31+, runtime)
   - BLUETOOTH_CONNECT (API 31+, runtime)
   - BLUETOOTH (API 1+)
   - BLUETOOTH_ADMIN (API 1+)
   
   LOCATION GROUP:
   - ACCESS_FINE_LOCATION (API 6+, runtime)
   - ACCESS_COARSE_LOCATION (API 1+)

5. PermissionRequestDialog (PythonJavaClass)
   - Implements ActivityCompat OnRequestPermissionsResultCallback
   - Receives Android permission dialog results
   - Routes results to event queue for processing

6. PermissionManager (Main Manager)
   
   REQUEST METHODS:
   - request_permission_group(group) - Request all in group
   - request_wifi_direct_permissions()
   - request_bluetooth_permissions()
   - request_location_permissions()
   
   CHECK METHODS:
   - check_permission(key) - Check single permission
   - check_permissions(keys) - Check multiple
   - check_critical_permissions() - Required for P2P
   - check_feature_available(feature) - Feature availability
   
   EVENT HANDLING:
   - _process_permission_events() - Background thread
   - _handle_permission_result() - Process results
   - Caches permission status to avoid repeated checks

API 33+ COMPLIANCE NOTES:
- NEARBY_WIFI_DEVICES required on API 33+ (was ACCESS_FINE_LOCATION)
- BLUETOOTH_SCAN/CONNECT required on API 31+
- Location still required for Wi-Fi Direct scanning
- Graceful fallback if permissions denied


MODULE 4: p2p_platform_adapter.py (625 lines)
─────────────────────────────────────────────

PURPOSE:
Unified interface managing all P2P channels (Wi-Fi Direct, Bluetooth,
UDP Broadcast, TCP) with automatic peer deduplication and fallback.

KEY CLASSES:

1. P2PChannel (Enum)
   - WIFI_DIRECT: Android Wi-Fi Direct
   - BLUETOOTH: Bluetooth RFCOMM
   - UDP_BROADCAST: Legacy UDP discovery
   - TCP_SOCKET: Standard TCP sockets

2. P2PChannelState (Enum)
   - IDLE, DISCOVERING, DISCOVERED, CONNECTING, CONNECTED, ERROR, DISABLED

3. P2PPeer (@dataclass)
   - Unified representation across all channels
   - peer_id: Unique identifier (MAC address)
   - device_name: Display name
   - channels: Set of channels peer found on
   - ip_addresses: Dict mapping channel to IP
   - signal_strength: Best signal across channels
   - is_connected: Connection state
   - metadata: Additional per-channel data
   
   Methods: to_dict() for serialization

4. P2PPlatformAdapter (Main Adapter)
   
   INITIALIZATION:
   - Detects available channels on platform
   - Initializes all available managers
   - Registers callbacks for all events
   
   PERMISSIONS:
   - request_required_permissions() - Request all needed
   - _on_permissions_result() - Handle results
   - Disables channels for denied permissions
   
   DISCOVERY:
   - start_discovery() - Start on all channels simultaneously
   - stop_discovery() - Stop all channels
   - Callbacks for peer discovered, state changed
   
   PEER MANAGEMENT:
   - _add_or_update_peer() - Deduplication logic
   - get_peers() - List all peers
   - get_peer(id) - Specific peer info
   - Deduplicates same peer found on multiple channels
   
   CONNECTION:
   - connect_to_peer(id, preferred_channel)
   - Tries preferred channel first
   - Falls back to other available channels
   - Channels attempted in availability order
   
   STATE MANAGEMENT:
   - _change_channel_state() - Thread-safe transitions
   - get_channel_state() - Current state of channel
   - Callbacks on state changes

PEER DEDUPLICATION ALGORITHM:
1. Peer discovered on Wi-Fi Direct with MAC "AA:BB:CC:DD:EE:FF"
2. Later discovered on Bluetooth with same MAC
3. Both added to same P2PPeer object
4. P2PPeer.channels now contains both {WIFI_DIRECT, BLUETOOTH}
5. P2PPeer.ip_addresses maps both channels to their IPs
6. On_peer_discovered callback fires only once


MODULE 5: AndroidManifest_P2P_Template.xml
──────────────────────────────────────────────────────────────────

PURPOSE:
Complete Android manifest template with API 33+ compliance,
intent-filters for BroadcastReceivers, and permission declarations.

SECTIONS:
1. Wi-Fi Direct Permissions (NEARBY_WIFI_DEVICES, CHANGE_WIFI_STATE)
2. Bluetooth Permissions (BLUETOOTH_SCAN, BLUETOOTH_CONNECT)
3. Location Permissions (required for discovery)
4. Network Permissions (INTERNET, multicast)
5. File Storage Permissions
6. Power Management (WAKE_LOCK)
7. Feature Declarations (optional)
8. Activity Definition with intent-filter
9. BroadcastReceiver Declarations:
   - Wi-Fi Direct state receiver
   - Bluetooth discovery receiver
   - Bluetooth device receiver
10. Service Declarations (commented for reference)
11. Provider Declarations (for file sharing)

BROADCAST INTENTS HANDLED:
Wi-Fi Direct:
- STATE_CHANGED: P2P capability enabled/disabled
- PEERS_CHANGED: Discovery results available
- CONNECTION_STATE_CHANGE: Group formed/closed
- THIS_DEVICE_CHANGED: Local device info updated

Bluetooth:
- DISCOVERY_STARTED/FINISHED: Scan lifecycle
- FOUND: Device discovered during scan
- BOND_STATE_CHANGED: Pairing state transitions
- PAIRING_REQUEST: User interaction needed


MODULE 6: test_p2p_modules.py (572 lines)
──────────────────────────────────────────────────────────────────

PURPOSE:
Comprehensive test suite for all modules with:
- Unit tests for each module
- Integration tests for workflows
- Thread safety validation
- Mock Android APIs for desktop testing

TEST CLASSES:
1. TestPermissionManager
   - Permission definitions completeness
   - API level constraints
   - Group assignments
   
2. TestWiFiDirectManager
   - WiFiPeer dataclass
   - State enum validation
   - Thread-safe peer access
   
3. TestBluetoothManager
   - BluetoothDevice dataclass
   - State enum validation
   - RFCOMM client initialization
   
4. TestP2PPlatformAdapter
   - P2PPeer unified representation
   - Channel state management
   - Peer discovery and management
   - Thread-safe operations
   
5. TestP2PIntegration
   - Complete discovery workflow
   - Peer deduplication across channels
   - Callback invocation

USAGE:
```bash
# Run all tests
python test_p2p_modules.py

# Run specific module tests
python test_p2p_modules.py --module wifi
python test_p2p_modules.py --module bluetooth
python test_p2p_modules.py --module adapter

# Verbose output
python test_p2p_modules.py -v
```
"""

# ============================================================================
# SECTION 3: INTEGRATION WITH EXISTING CODEBASE
# ============================================================================

"""
INTEGRATION POINTS WITH EXISTING GHOSTENGINE:

┌─────────────────────────────────────────────────────┐
│             Existing GhostEngine (network.py)        │
│  - UDP broadcast discovery (Port 37020)              │
│  - TCP messaging server (Port 37021)                 │
│  - Symmetric Fernet encryption                       │
│  - Peer management & timeouts                        │
│  - File transfer protocol                            │
└─────────────────────────────────────────────────────┘
            ↑                                  ↑
            │ TCP sockets                      │ Encrypted messages
            │                                  │
┌─────────────────────────────────────────────────────┐
│        P2P Platform Adapter (p2p_platform_adapter)   │
│  - Unified peer discovery across channels            │
│  - Deduplication & fallback                          │
│  - Connection management                             │
└─────────────────────────────────────────────────────┘
       ↑              ↑              ↑
       │              │              │
    WiFi Direct   Bluetooth      UDP/TCP
    (Native IP)   (RFCOMM)    (Existing)
    
  
CONNECTION FLOW:

1. WIFI DIRECT PATH:
   a) P2PPlatformAdapter.start_discovery()
   b) WiFiDirectManager discovers peers
   c) on_peer_discovered callback fires
   d) User selects peer → connect_to_peer()
   e) WiFiDirectManager.connect_to_peer()
   f) Group forms, GO IP resolved via _request_connection_info()
   g) Open TCP socket to GO:37021
   h) Hand over to GhostEngine for encrypted communication
   
2. BLUETOOTH PATH:
   a) P2PPlatformAdapter.start_discovery()
   b) BluetoothManager discovers devices
   c) on_peer_discovered callback fires
   d) User selects device → connect_to_peer()
   e) BluetoothManager.connect_to_device()
   f) RFCOMM socket established
   g) Receive data via BluetoothRFCOMMClient.on_data callback
   h) Frame data [4-byte length][message]
   i) Hand over to GhostEngine for decryption
   
3. UDP BROADCAST PATH (EXISTING):
   a) GhostEngine.start() already implemented
   b) Broadcasts beacon on port 37020
   c) Listens for peer beacons
   d) No changes needed to existing code


IMPLEMENTATION STEPS FOR INTEGRATION:

Step 1: Initialize in main.py on app start:

```python
from p2p_platform_adapter import P2PPlatformAdapter

class GhostApp(MDApp):
    def on_start(self):
        # Initialize P2P adapter
        self.p2p_adapter = P2PPlatformAdapter(
            on_peer_discovered=self.handle_peer_discovered,
            on_peer_connected=self.handle_peer_connected,
            on_channel_state_changed=self.handle_channel_state,
            on_error=self.handle_p2p_error
        )
        
        # Request permissions first
        self.p2p_adapter.request_required_permissions()
        
        # Initialize existing GhostEngine with TCP/UDP
        self.ghost_engine = GhostEngine(
            username=self.config_manager.get_username(),
            on_message_received=self.handle_message,
            on_peer_update=self.handle_peer_update,
            on_file_received=self.handle_file_received
        )
```

Step 2: Handle peer discovery:

```python
def handle_peer_discovered(self, peer_dict):
    logger.info(f"Peer discovered: {peer_dict['device_name']}")
    # Update UI peer list
    # Peer is on WIFI_DIRECT and/or BLUETOOTH channels
    
def handle_peer_connected(self, peer_id, channel):
    logger.info(f"Connected to {peer_id} via {channel.value}")
    # If Wi-Fi Direct: TCP socket now available to GhostEngine
    # If Bluetooth: RFCOMM data via callbacks
```

Step 3: Route Bluetooth data to GhostEngine:

```python
def setup_bluetooth_callbacks(self, bluetooth_manager):
    # When RFCOMM connection established:
    def on_bt_data(data):
        # Data arrives as [4-byte length][encrypted message]
        msg_len = struct.unpack('>I', data[:4])[0]
        encrypted_msg = data[4:4+msg_len]
        # Pass to GhostEngine for decryption
        self.ghost_engine.process_encrypted_message(encrypted_msg)
    
    bluetooth_manager.on_data = on_bt_data
```

Step 4: Shutdown sequence:

```python
def on_stop(self):
    self.ghost_engine.stop()
    self.p2p_adapter.shutdown()
```


PERMISSION REQUEST FLOW IN MAIN.PY:

```python
def request_p2p_permissions(self):
    # Checks API 33+ and requests Android permissions
    perm_available, denied_perms = self.p2p_adapter.check_critical_permissions()
    
    if not perm_available:
        self.show_permission_dialog(denied_perms)
    else:
        self.start_p2p_discovery()

def handle_permission_denied(self, permission_list):
    msg = "P2P features require: " + ", ".join(permission_list)
    self.show_dialog("Permissions Needed", msg,
                     on_grant=self.request_p2p_permissions)
```
"""

# ============================================================================
# SECTION 4: DEPLOYMENT & BUILD CONFIGURATION
# ============================================================================

"""
BUILDOZER.SPEC UPDATES:

[app]
requirements = python3,kivy==2.3.0,kivymd==1.2.0,asynckivy,asyncgui,
               pillow,cryptography==41.0.7,openssl,libffi,pyjnius

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,
    CHANGE_WIFI_MULTICAST_STATE,CHANGE_NETWORK_STATE,
    READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,WAKE_LOCK,
    NEARBY_WIFI_DEVICES,BLUETOOTH,BLUETOOTH_ADMIN,
    BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,
    ACCESS_COARSE_LOCATION,CHANGE_WIFI_STATE,LOCAL_MAC_ADDRESS

android.api = 33
android.minapi = 21
android.target_api = 33

android.enable_androidx = True

# Custom manifest (optional)
# android.manifest_custom_template = %(source.dir)s/AndroidManifest_P2P_Template.xml


BUILD STEPS:

1. Place modules in project root:
   - android_wifi_direct.py
   - android_bluetooth.py
   - android_permissions.py
   - p2p_platform_adapter.py
   - AndroidManifest_P2P_Template.xml (in .buildozer/android/src/main if used)

2. Build APK:
   buildozer android debug

3. Test on device:
   buildozer android debug deploy run

4. For production:
   buildozer android release
   # Sign and align APK


GRADLE CONFIGURATION (if needed):

android/build.gradle can include:
```gradle
dependencies {
    implementation 'androidx.core:core:1.6.0'  // For ActivityCompat
}

android {
    compileSdkVersion 33
    targetSdkVersion 33
    minSdkVersion 21
}
```
"""

# ============================================================================
# SECTION 5: TROUBLESHOOTING & COMMON ISSUES
# ============================================================================

"""
ISSUE 1: "WifiP2pManager not found" on startup
CAUSE: pyjnius not available or incorrect Android context
FIX:
- Ensure buildozer.spec includes pyjnius in requirements
- Verify running on actual Android device (not emulator without services)
- Check AndroidManifest has correct package name

ISSUE 2: Wi-Fi Direct discovery returns no peers
CAUSE: NEARBY_WIFI_DEVICES permission not granted at runtime
FIX:
- Call request_wifi_direct_permissions() before start_discovery()
- Ensure both devices have Wi-Fi Direct enabled
- Keep both devices within range
- Try resetting Wi-Fi on both devices

ISSUE 3: Bluetooth connection fails with "Connection refused"
CAUSE: Remote device not discoverable or RFCOMM port unavailable
FIX:
- Ensure both devices have Bluetooth enabled
- Make sure remote device is in pairing mode
- Try pairing manually first
- Check BLUETOOTH_CONNECT permission granted

ISSUE 4: High CPU usage during discovery
CAUSE: Discovery running continuously without stopping
FIX:
- Call stop_discovery() when not needed
- Set discovery timeout (default 30s)
- Increase discovery interval in config

ISSUE 5: File transfer stalls mid-transfer
CAUSE: Socket buffer full or connection interrupted
FIX:
- Implement send_file with smaller chunk sizes
- Add TCP_NODELAY socket option to reduce latency
- Implement sequence numbers for frame ordering
- Check connection quality (signal strength)

ISSUE 6: "Permission denied" after requesting permissions
CAUSE: User declined permission request
FIX:
- Show informative message about why permission needed
- Disable P2P features if permission critical
- Offer alternative communication channels
- Request permission again with context


THREAD SAFETY:

All managers use threading.RLock() acquisitions:
- WiFiDirectManager: lock on peers dict, state changes
- BluetoothManager: lock on discovered_devices, clients
- P2PPlatformAdapter: lock on peers, channel_states

Safe to call from multiple threads without external locking.


PERFORMANCE TIPS:

1. Disable unused channels:
   p2p_adapter.enabled_channels.discard(P2PChannel.BLUETOOTH)

2. Increase discovery timeout for slow networks:
   wifi_manager.DISCOVERY_TIMEOUT = 60

3. Reuse connections instead of reconnecting:
   peer_ip = p2p_adapter.get_peer(peer_id)['ip_addresses'][WIFI_DIRECT]
   # Keep socket open for multiple messages

4. Clean up stale peers:
   for peer_id, peer in list(p2p_adapter.peers.items()):
       if time.time() - peer.last_seen > 60:
           del p2p_adapter.peers[peer_id]
"""

# ============================================================================
# SECTION 6: API REFERENCE QUICK START
# ============================================================================

"""
QUICK START EXAMPLE:

from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel
from android_permissions import PermissionManager

# 1. Initialize
adapter = P2PPlatformAdapter(
    on_peer_discovered=print_peer,
    on_peer_connected=print_connected,
    on_error=print_error
)

# 2. Request permissions
adapter.request_required_permissions()

# 3. Start discovery
adapter.start_discovery()

# 4. Wait for peers (on_peer_discovered callback fires)

# 5. Connect to peer
adapter.connect_to_peer(peer_id="AA:BB:CC:DD:EE:FF",
                        preferred_channel=P2PChannel.WIFI_DIRECT)

# 6. Send data (via appropriate channel)
if adapter.get_channel_state(P2PChannel.WIFI_DIRECT) == P2PChannelState.CONNECTED:
    # Use existing GhostEngine for TCP
    ghost_engine.send_message(peer_ip, "Hello")
elif adapter.get_channel_state(P2PChannel.BLUETOOTH) == P2PChannelState.CONNECTED:
    # Use Bluetooth
    adapter.bluetooth_manager.send_to_device(peer_id, b"Hello")

# 7. Cleanup
adapter.shutdown()


CALLBACKS SIGNATURE:

on_peer_discovered(peer_dict):
    peer_dict = {
        'peer_id': 'AA:BB:CC:DD:EE:FF',
        'device_name': 'John\'s Phone',
        'channels': ['wifi_direct', 'bluetooth'],
        'ip_addresses': {'wifi_direct': '192.168.49.1'},
        'signal_strength': -50,
        'is_connected': False,
        'last_seen': 1700000000.0,
        'metadata': {}
    }

on_peer_connected(peer_id, channel):
    peer_id = 'AA:BB:CC:DD:EE:FF'
    channel = P2PChannel.WIFI_DIRECT

on_channel_state_changed(channel, state):
    channel = P2PChannel.WIFI_DIRECT
    state = P2PChannelState.CONNECTED

on_error(error_msg):
    # Handle error string
    pass
"""

# ============================================================================
# SECTION 7: TESTING
# ============================================================================

"""
RUN TESTS:

# All tests
python test_p2p_modules.py

# Specific module
python test_p2p_modules.py --module wifi
python test_p2p_modules.py --module bluetooth
python test_p2p_modules.py --module permissions
python test_p2p_modules.py --module adapter

# Verbose
python test_p2p_modules.py -v

# Expected output:
#   ✓ Permission definitions complete
#   ✓ WiFiPeer dataclass working
#   ✓ BluetoothDevice dataclass working
#   ✓ Peer deduplication working
#   etc.


MANUAL TESTING ON DEVICE:

Device 1 (Server):
1. Launch Ghost Net
2. Wait for permissions dialogs
3. Go to Discover tab
4. Start discovery (should see peers within ~10 seconds)

Device 2 (Peer):
1. Launch Ghost Net
2. Grant permissions
3. Should appear in Device 1's peer list
4. Try to connect via Wi-Fi Direct or Bluetooth

Verify:
- Both devices discover each other
- Connection succeeds without errors
- Messages transmit between devices
- File transfer works (if implemented in UI)
- No excessive battery drain or CPU usage
"""

# ============================================================================
# SECTION 8: FUTURE ENHANCEMENTS
# ============================================================================

"""
POTENTIAL IMPROVEMENTS:

1. Multi-hop Meshing:
   - Relay messages through intermediate peers
   - Extend range beyond single-hop P2P

2. Named Services:
   - Register Ghost Net service with zeroconf/mDNS
   - Easier peer identification on corporate networks

3. QoS Implementation:
   - Message acknowledgment/retransmission
   - Prioritize critical P2P messages

4. Bandwidth Management:
   - Rate limiting for large file transfers
   - Adaptive chunk sizing based on signal strength

5. Mobile Optimizations:
   - Reduce discovery interval on battery power
   - Pause P2P when screen off
   - Resume intelligently when screen on

6. Encrypted Tunnel:
   - TLS over Bluetooth RFCOMM
   - DTLS/IPSec for Wi-Fi Direct UDP

7. UI Enhancements:
   - Signal strength visualization
   - Channel selection UI
   - P2P discovery progress indicator

8. Testing:
   - Automated integration tests
   - Mock Android framework for CI/CD
   - Load testing with 100+ virtual peers

9. Documentation:
   - Video tutorials
   - Architecture diagrams
   - Troubleshooting guide
"""

# ============================================================================
# END OF COMPREHENSIVE IMPLEMENTATION GUIDE
# ============================================================================
