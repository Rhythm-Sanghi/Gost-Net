"""
Ghost Net - Android Bluetooth RFCOMM Module
Pyjnius wrapper for android.bluetooth package implementing peer discovery,
pairing workflows, and bidirectional socket communication. Supports both
server (listenUsingInsecureRfcomm) and client (createInsecureRfcommSocket)
operations designed for API 33+ with runtime permission support.

Key Features:
- Device discovery with filtering (Bluetooth classic only)
- Automatic pairing and unpair workflows
- RFCOMM socket server for listening connections
- RFCOMM socket client for initiating connections
- Bidirectional text and binary message framing
- Automatic reconnection on disconnection
- Thread-safe operation for Kivy integration
- File transmission support with chunked transfers
"""

import logging
import socket
import threading
import time
from typing import Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import struct
import uuid as uuid_module

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Conditional pyjnius imports
try:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    PYJNIUS_AVAILABLE = True
except ImportError:
    PYJNIUS_AVAILABLE = False
    autoclass = None
    cast = None
    class PythonJavaClass:
        pass
    def java_method(signature):
        def decorator(f):
            return f
        return decorator
    logger.warning("[Bluetooth] pyjnius not available - Bluetooth disabled")


class BluetoothState(Enum):
    """State machine for Bluetooth operations."""
    IDLE = "idle"
    DISCOVERING = "discovering"
    DEVICES_FOUND = "devices_found"
    PAIRING = "pairing"
    PAIRED = "paired"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LISTENING = "listening"
    ERROR = "error"


@dataclass
class BluetoothDevice:
    """Represents a discovered Bluetooth device."""
    device_name: str
    device_address: str  # MAC address
    device_class: int = 0
    is_paired: bool = False
    rssi: int = 0  # Signal strength
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Convert device to dictionary for serialization."""
        return {
            'device_name': self.device_name,
            'device_address': self.device_address,
            'device_class': self.device_class,
            'is_paired': self.is_paired,
            'rssi': self.rssi,
            'timestamp': self.timestamp
        }


class BluetoothBroadcastReceiver(PythonJavaClass):
    """
    Android BroadcastReceiver for Bluetooth state changes.
    Handles discovery results, pairing state changes, and connection events.
    
    Intents:
    - ACTION_DISCOVERY_STARTED
    - ACTION_DISCOVERY_FINISHED
    - ACTION_FOUND (device discovered)
    - ACTION_BOND_STATE_CHANGED (pairing state)
    - ACTION_PAIRING_REQUEST
    """
    __javainterfaces__ = ['android/content/BroadcastReceiver']
    __javacontext__ = 'app'

    def __init__(self, callback_queue):
        """Initialize receiver with event queue."""
        super().__init__()
        self.callback_queue = callback_queue
        logger.debug("[Bluetooth] BroadcastReceiver initialized")

    @java_method('(Landroid/content/Context;Landroid/content/Intent;)V')
    def onReceive(self, context, intent):
        """Handle Bluetooth broadcast events."""
        try:
            action = intent.getAction()
            logger.debug(f"[Bluetooth] BroadcastReceiver event: {action}")

            if action == "android.bluetooth.adapter.action.DISCOVERY_STARTED":
                event = {'type': 'discovery_started'}
                self.callback_queue.put(event)

            elif action == "android.bluetooth.adapter.action.DISCOVERY_FINISHED":
                event = {'type': 'discovery_finished'}
                self.callback_queue.put(event)

            elif action == "android.bluetooth.device.action.FOUND":
                device = intent.getParcelableExtra("android.bluetooth.device.extra.DEVICE")
                rssi = intent.getShortExtra("android.bluetooth.device.extra.RSSI", 0)
                if device:
                    event = {
                        'type': 'device_found',
                        'device': device,
                        'rssi': rssi
                    }
                    self.callback_queue.put(event)

            elif action == "android.bluetooth.device.action.BOND_STATE_CHANGED":
                device = intent.getParcelableExtra("android.bluetooth.device.extra.DEVICE")
                bond_state = intent.getIntExtra("android.bluetooth.device.extra.BOND_STATE", -1)
                if device:
                    event = {
                        'type': 'bond_state_changed',
                        'device': device,
                        'bond_state': bond_state
                    }
                    self.callback_queue.put(event)

            elif action == "android.bluetooth.device.action.PAIRING_REQUEST":
                event = {'type': 'pairing_request'}
                self.callback_queue.put(event)

        except Exception as e:
            logger.error(f"[Bluetooth] BroadcastReceiver error: {e}", exc_info=True)


if PYJNIUS_AVAILABLE:
    class BLEAdvertiseCallback(PythonJavaClass):
        __javainterfaces__ = ['android/bluetooth/le/AdvertiseCallback']
        __javacontext__ = 'app'

        def __init__(self):
            super().__init__()

        @java_method('(Landroid/bluetooth/le/AdvertiseSettings;)V')
        def onStartSuccess(self, settingsInEffect):
            logger.info("[BLE] Advertise started successfully")

        @java_method('(I)V')
        def onStartFailure(self, errorCode):
            logger.error(f"[BLE] Advertise failed: {errorCode}")

    class BLEScanCallback(PythonJavaClass):
        __javainterfaces__ = ['android/bluetooth/le/ScanCallback']
        __javacontext__ = 'app'

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(ILandroid/bluetooth/le/ScanResult;)V')
        def onScanResult(self, callbackType, result):
            try:
                device = result.getDevice()
                rssi = result.getRssi()
                name = device.getName()
                if not name and result.getScanRecord():
                    name = result.getScanRecord().getDeviceName()
                self.callback(device, rssi, name)
            except Exception as e:
                logger.error(f"[BLE] onScanResult error: {e}")

        @java_method('(Ljava/util/List;)V')
        def onBatchScanResults(self, results):
            pass

        @java_method('(I)V')
        def onScanFailed(self, errorCode):
            logger.error(f"[BLE] Scan failed: {errorCode}")


class BluetoothRFCOMMServer(threading.Thread):
    """
    Bluetooth RFCOMM server listening for incoming connections.
    Runs in background thread and accepts connections from remote devices.
    
    Uses listenUsingInsecureRfcommWithServiceRecord for insecure
    (non-encrypted) connections suitable for local P2P scenarios.
    """

    def __init__(self, adapter, service_name: str, service_uuid: str,
                 on_connection: Optional[Callable] = None,
                 on_data: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        """
        Initialize RFCOMM server.
        
        Args:
            adapter: Android BluetoothAdapter instance
            service_name: Service name for service record
            service_uuid: UUID string for service identification
            on_connection: Callback(device_info) on new connection
            on_data: Callback(device_address, data) on data received
            on_error: Callback(error_msg) on errors
        """
        super().__init__(daemon=True, name="BluetoothRFCOMMServer")

        self.adapter = adapter
        self.service_name = service_name
        self.service_uuid = service_uuid
        self.on_connection = on_connection
        self.on_data = on_data
        self.on_error = on_error

        self.running = False
        self.server_socket = None
        self.client_sockets: Dict[str, socket.socket] = {}
        self.lock = threading.RLock()

    def run(self):
        """Background thread main loop."""
        if not PYJNIUS_AVAILABLE:
            return

        try:
            self._initialize_server()
            self._accept_connections()
        except Exception as e:
            logger.error(f"[Bluetooth] Server thread error: {e}", exc_info=True)
            if self.on_error:
                self.on_error(f"Server error: {e}")
        finally:
            self._cleanup()

    def _initialize_server(self):
        """Initialize RFCOMM server socket."""
        try:
            UUID = autoclass('java.util.UUID')
            ParcelUuid = autoclass('android.os.ParcelUuid')

            # Convert UUID string to Java UUID
            java_uuid = UUID.fromString(self.service_uuid)
            parcel_uuid = ParcelUuid(java_uuid)

            # Create server socket
            self.server_socket = self.adapter.listenUsingInsecureRfcommWithServiceRecord(
                self.service_name,
                java_uuid
            )

            self.running = True
            logger.info(f"[Bluetooth] Server listening on {self.service_name}")

        except Exception as e:
            logger.error(f"[Bluetooth] Server initialization failed: {e}", exc_info=True)
            if self.on_error:
                self.on_error(f"Server init failed: {e}")
            raise

    def _accept_connections(self):
        """Accept incoming RFCOMM connections."""
        while self.running:
            try:
                # Accept connection (blocking)
                client_sock = self.server_socket.accept()
                if client_sock:
                    # Get remote device address
                    remote_device = client_sock.getRemoteDevice()
                    device_addr = remote_device.getAddress()

                    logger.info(f"[Bluetooth] Client connected: {device_addr}")

                    with self.lock:
                        self.client_sockets[device_addr] = client_sock

                    # Notify connection
                    if self.on_connection:
                        device_dict = {
                            'device_name': remote_device.getName(),
                            'device_address': device_addr
                        }
                        self.on_connection(device_dict)

                    # Start data reception thread
                    threading.Thread(
                        target=self._handle_client_data,
                        args=(device_addr, client_sock),
                        daemon=True,
                        name=f"BluetoothClientHandler-{device_addr}"
                    ).start()

            except Exception as e:
                if self.running:
                    logger.error(f"[Bluetooth] Accept connection error: {e}")

    def _handle_client_data(self, device_addr: str, client_sock):
        """Handle data from connected client."""
        try:
            while self.running:
                # Read frame header (4 bytes for length)
                header = client_sock.getInputStream().read(4)
                if not header or len(header) < 4:
                    break

                # Unpack message length
                msg_len = struct.unpack('>I', header)[0]
                if msg_len > 1024 * 1024:  # Max 1MB per message
                    logger.warning(f"[Bluetooth] Message too large: {msg_len}")
                    break

                # Read message body
                body = b''
                while len(body) < msg_len:
                    chunk = client_sock.getInputStream().read(msg_len - len(body))
                    if not chunk:
                        break
                    body += chunk

                if self.on_data:
                    self.on_data(device_addr, body)

        except Exception as e:
            logger.debug(f"[Bluetooth] Client data error: {e}")
        finally:
            with self.lock:
                if device_addr in self.client_sockets:
                    try:
                        self.client_sockets[device_addr].close()
                    except:
                        pass
                    del self.client_sockets[device_addr]

    def send_data(self, device_addr: str, data: bytes) -> bool:
        """
        Send data to connected client with frame format.
        
        Frame format: [4-byte length][data...]
        
        Args:
            device_addr: Device MAC address
            data: Bytes to send
            
        Returns:
            bool: True if sent, False otherwise
        """
        with self.lock:
            if device_addr not in self.client_sockets:
                return False

            try:
                sock = self.client_sockets[device_addr]
                frame = struct.pack('>I', len(data)) + data
                sock.getOutputStream().write(frame)
                sock.getOutputStream().flush()
                return True
            except Exception as e:
                logger.error(f"[Bluetooth] Send error: {e}")
                return False

    def disconnect_client(self, device_addr: str):
        """Disconnect specific client."""
        with self.lock:
            if device_addr in self.client_sockets:
                try:
                    self.client_sockets[device_addr].close()
                except:
                    pass
                del self.client_sockets[device_addr]
                logger.info(f"[Bluetooth] Client disconnected: {device_addr}")

    def _cleanup(self):
        """Clean up server resources."""
        self.running = False

        with self.lock:
            for sock in self.client_sockets.values():
                try:
                    sock.close()
                except:
                    pass
            self.client_sockets.clear()

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        logger.info("[Bluetooth] Server cleanup complete")


class BluetoothRFCOMMClient:
    """
    Bluetooth RFCOMM client for connecting to remote devices.
    Uses createInsecureRfcommSocketToServiceRecord for non-encrypted
    connections and handles automatic reconnection.
    """

    def __init__(self, adapter, device_address: str, service_uuid: str,
                 on_connected: Optional[Callable] = None,
                 on_data: Optional[Callable] = None,
                 on_disconnected: Optional[Callable] = None,
                 on_error: Optional[Callable] = None,
                 auto_reconnect: bool = True):
        """
        Initialize RFCOMM client.
        
        Args:
            adapter: Android BluetoothAdapter instance
            device_address: Remote device MAC address
            service_uuid: UUID string matching remote service
            on_connected: Callback() on successful connection
            on_data: Callback(data_bytes) on data received
            on_disconnected: Callback() on disconnection
            on_error: Callback(error_msg) on errors
            auto_reconnect: Enable automatic reconnection (default: True)
        """
        self.adapter = adapter
        self.device_address = device_address
        self.service_uuid = service_uuid
        self.on_connected = on_connected
        self.on_data = on_data
        self.on_disconnected = on_disconnected
        self.on_error = on_error
        self.auto_reconnect = auto_reconnect

        self.socket = None
        self.connected = False
        self.reading_thread = None
        self.lock = threading.RLock()

        # Reconnection parameters
        self.reconnect_attempts = 0
        self.reconnect_backoff = 1.0
        self.max_reconnects = 10
        self.max_backoff = 32.0

    def connect(self) -> bool:
        """
        Establish RFCOMM connection to remote device.
        
        Returns:
            bool: True if connection started, False otherwise
        """
        if not PYJNIUS_AVAILABLE:
            self._notify_error("pyjnius not available")
            return False

        if self.connected:
            logger.debug("[Bluetooth] Already connected")
            return True

        try:
            UUID = autoclass('java.util.UUID')

            # Get remote device
            remote_device = self.adapter.getRemoteDevice(self.device_address)

            # Create socket
            java_uuid = UUID.fromString(self.service_uuid)
            self.socket = remote_device.createInsecureRfcommSocketToServiceRecord(java_uuid)

            # Connect (blocking)
            self.socket.connect()

            with self.lock:
                self.connected = True
                self.reconnect_attempts = 0
                self.reconnect_backoff = 1.0

            logger.info(f"[Bluetooth] Connected to {self.device_address}")

            # Start data reception thread
            self.reading_thread = threading.Thread(
                target=self._read_loop,
                daemon=True,
                name=f"BluetoothClientRead-{self.device_address}"
            )
            self.reading_thread.start()

            if self.on_connected:
                self.on_connected()

            return True

        except Exception as e:
            logger.error(f"[Bluetooth] Connection failed: {e}")
            self._notify_error(f"Connection failed: {e}")
            self._handle_disconnection()
            return False

    def _read_loop(self):
        """Background loop reading data from socket."""
        try:
            while self.connected and self.socket:
                try:
                    # Read frame header
                    header = self.socket.getInputStream().read(4)
                    if not header or len(header) < 4:
                        break

                    # Unpack message length
                    msg_len = struct.unpack('>I', header)[0]
                    if msg_len > 1024 * 1024:  # Max 1MB
                        logger.warning(f"[Bluetooth] Message too large: {msg_len}")
                        break

                    # Read body
                    body = b''
                    while len(body) < msg_len:
                        chunk = self.socket.getInputStream().read(msg_len - len(body))
                        if not chunk:
                            break
                        body += chunk

                    if self.on_data:
                        self.on_data(body)

                except Exception as e:
                    logger.debug(f"[Bluetooth] Read error: {e}")
                    break

        finally:
            self._handle_disconnection()

    def send_data(self, data: bytes) -> bool:
        """
        Send data to remote device with frame format.
        
        Args:
            data: Bytes to send
            
        Returns:
            bool: True if sent, False otherwise
        """
        with self.lock:
            if not self.connected or not self.socket:
                return False

            try:
                frame = struct.pack('>I', len(data)) + data
                self.socket.getOutputStream().write(frame)
                self.socket.getOutputStream().flush()
                return True
            except Exception as e:
                logger.error(f"[Bluetooth] Send error: {e}")
                self._handle_disconnection()
                return False

    def send_text(self, text: str) -> bool:
        """Send text message to remote device."""
        try:
            return self.send_data(text.encode('utf-8'))
        except Exception as e:
            logger.error(f"[Bluetooth] Send text error: {e}")
            return False

    def send_file(self, file_path: str, chunk_size: int = 4096) -> bool:
        """
        Send file to remote device with progress tracking.
        
        Args:
            file_path: Path to file to send
            chunk_size: Bytes per transmission chunk
            
        Returns:
            bool: True if transfer started, False otherwise
        """
        try:
            import os
            if not os.path.isfile(file_path):
                self._notify_error(f"File not found: {file_path}")
                return False

            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)

            # Send file header: [4-byte name length][name][8-byte file size]
            name_bytes = file_name.encode('utf-8')
            header = struct.pack('>I', len(name_bytes)) + name_bytes + struct.pack('>Q', file_size)

            if not self.send_data(header):
                return False

            # Send file in chunks
            with open(file_path, 'rb') as f:
                bytes_sent = 0
                while bytes_sent < file_size:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    if not self.send_data(chunk):
                        return False

                    bytes_sent += len(chunk)
                    progress = (bytes_sent / file_size) * 100
                    logger.debug(f"[Bluetooth] File transfer progress: {progress:.1f}%")

            logger.info(f"[Bluetooth] File sent: {file_name}")
            return True

        except Exception as e:
            logger.error(f"[Bluetooth] File send error: {e}")
            return False

    def _handle_disconnection(self):
        """Handle connection closure and attempt reconnection."""
        with self.lock:
            if not self.connected:
                return

            self.connected = False

            try:
                if self.socket:
                    self.socket.close()
                    self.socket = None
            except:
                pass

        logger.warning(f"[Bluetooth] Disconnected from {self.device_address}")

        if self.on_disconnected:
            self.on_disconnected()

        # Attempt reconnection
        if self.auto_reconnect and self.reconnect_attempts < self.max_reconnects:
            threading.Thread(
                target=self._reconnect_loop,
                daemon=True,
                name=f"BluetoothClientReconnect-{self.device_address}"
            ).start()

    def _reconnect_loop(self):
        """Background loop for automatic reconnection with exponential backoff."""
        while self.reconnect_attempts < self.max_reconnects and not self.connected:
            try:
                self.reconnect_attempts += 1
                logger.info(f"[Bluetooth] Reconnect attempt {self.reconnect_attempts}")

                time.sleep(self.reconnect_backoff)

                if self.connect():
                    return

                self.reconnect_backoff = min(
                    self.reconnect_backoff * 2,
                    self.max_backoff
                )

            except Exception as e:
                logger.error(f"[Bluetooth] Reconnect error: {e}")

    def disconnect(self):
        """Close connection gracefully."""
        with self.lock:
            self.connected = False

            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

        if self.reading_thread:
            self.reading_thread.join(timeout=2)

        logger.info(f"[Bluetooth] Closed connection to {self.device_address}")

    def _notify_error(self, error_msg: str):
        """Thread-safe error notification."""
        logger.error(f"[Bluetooth] Error: {error_msg}")
        if self.on_error:
            self.on_error(error_msg)


class BluetoothManager:
    """
    High-level manager for Bluetooth P2P operations.
    Integrates device discovery, pairing, RFCOMM server, and client connectivity.
    """

    # Standard service UUID for Ghost Net
    GHOST_NET_SERVICE_UUID = "447d5f51-7a8b-4d6f-a9c2-1234567890ab"

    def __init__(self, on_device_discovered: Optional[Callable] = None,
                 on_state_changed: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        """
        Initialize Bluetooth Manager.
        
        Args:
            on_device_discovered: Callback(devices_list) on device discovery
            on_state_changed: Callback(state) on state changes
            on_error: Callback(error_msg) on errors
        """
        self.adapter = None
        self.context = None

        self.on_device_discovered = on_device_discovered
        self.on_state_changed = on_state_changed
        self.on_error = on_error

        self.state = BluetoothState.IDLE
        self.discovered_devices: Dict[str, BluetoothDevice] = {}
        self.broadcast_receiver = None

        self.server: Optional[BluetoothRFCOMMServer] = None
        self.clients: Dict[str, BluetoothRFCOMMClient] = {}

        self.event_queue = None
        self.event_loop_thread = None
        self.running = False

        self.ble_advertiser = None
        self.ble_scanner = None
        self.ble_advertise_callback = None
        self.ble_scan_callback = None
        self.ble_on_device_discovered = None

        self.lock = threading.RLock()

        # Initialize if pyjnius available
        if PYJNIUS_AVAILABLE:
            self._initialize_bluetooth()
        else:
            logger.warning("[Bluetooth] Initialization skipped - pyjnius unavailable")

    def _initialize_bluetooth(self):
        """Initialize Bluetooth adapter and broadcast receiver."""
        try:
            # Get context
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.context = PythonActivity.mActivity

            # Get Bluetooth adapter
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            self.adapter = BluetoothAdapter.getDefaultAdapter()

            if not self.adapter:
                self._notify_error("Bluetooth adapter not available")
                return

            try:
                self.ble_advertiser = self.adapter.getBluetoothLeAdvertiser()
                self.ble_scanner = self.adapter.getBluetoothLeScanner()
            except Exception as e:
                logger.warning(f"[Bluetooth] BLE components not available: {e}")

            if not self.adapter:
                self._notify_error("Bluetooth adapter not available")
                return

            # Check if Bluetooth is enabled
            if not self.adapter.isEnabled():
                logger.warning("[Bluetooth] Bluetooth is not enabled")

            # Initialize event queue and loop
            from queue import Queue
            self.event_queue = Queue()
            self.running = True

            self.event_loop_thread = threading.Thread(
                target=self._event_loop,
                daemon=True,
                name="BluetoothEventLoop"
            )
            self.event_loop_thread.start()

            # Register broadcast receiver
            self.broadcast_receiver = BluetoothBroadcastReceiver(self.event_queue)
            logger.info("[Bluetooth] Manager initialized")

        except Exception as e:
            logger.error(f"[Bluetooth] Initialization failed: {e}", exc_info=True)
            self._notify_error(f"Init failed: {e}")

    def _change_state(self, new_state: BluetoothState):
        """Thread-safe state transition."""
        with self.lock:
            if self.state != new_state:
                old_state = self.state
                self.state = new_state
                logger.info(f"[Bluetooth] State: {old_state.value} -> {new_state.value}")
                if self.on_state_changed:
                    self.on_state_changed(new_state)

    def _notify_error(self, error_msg: str):
        """Thread-safe error notification."""
        logger.error(f"[Bluetooth] Error: {error_msg}")
        if self.on_error:
            self.on_error(error_msg)

    def _event_loop(self):
        """Background event processing loop."""
        while self.running:
            try:
                if self.event_queue:
                    event = self.event_queue.get(timeout=1)
                    self._handle_broadcast_event(event)
            except:
                continue

    def _handle_broadcast_event(self, event: dict):
        """Process broadcast events."""
        try:
            event_type = event.get('type')

            if event_type == 'discovery_started':
                self._change_state(BluetoothState.DISCOVERING)
                with self.lock:
                    self.discovered_devices.clear()

            elif event_type == 'discovery_finished':
                self._change_state(BluetoothState.DEVICES_FOUND)
                if self.on_device_discovered:
                    devices = [d.to_dict() for d in self.discovered_devices.values()]
                    self.on_device_discovered(devices)

            elif event_type == 'device_found':
                device = event.get('device')
                rssi = event.get('rssi', 0)
                if device:
                    self._process_discovered_device(device, rssi)

            elif event_type == 'bond_state_changed':
                device = event.get('device')
                bond_state = event.get('bond_state')
                if device:
                    self._process_bond_state(device, bond_state)

        except Exception as e:
            logger.error(f"[Bluetooth] Event handling error: {e}", exc_info=True)

    def _process_discovered_device(self, device, rssi: int):
        """Process discovered device from broadcast."""
        try:
            address = device.getAddress()
            name = device.getName() or f"Unknown ({address})"
            device_class = device.getDeviceClass()

            dev = BluetoothDevice(
                device_name=name,
                device_address=address,
                device_class=device_class,
                rssi=rssi
            )

            with self.lock:
                self.discovered_devices[address] = dev

            logger.debug(f"[Bluetooth] Device found: {name} ({address})")

        except Exception as e:
            logger.error(f"[Bluetooth] Process device error: {e}")

    def _process_bond_state(self, device, bond_state: int):
        """Process bond state change."""
        try:
            address = device.getAddress()
            # Bond states: BOND_NONE=10, BOND_BONDING=11, BOND_BONDED=12
            is_paired = bond_state == 12  # BOND_BONDED

            with self.lock:
                if address in self.discovered_devices:
                    self.discovered_devices[address].is_paired = is_paired

            logger.info(f"[Bluetooth] Device {address} paired={is_paired}")

        except Exception as e:
            logger.error(f"[Bluetooth] Process bond state error: {e}")

    def start_discovery(self) -> bool:
        """
        Start Bluetooth device discovery.
        
        Returns:
            bool: True if discovery started, False otherwise
        """
        if not self.adapter:
            self._notify_error("Adapter not initialized")
            return False

        try:
            if self.adapter.isDiscovering():
                logger.debug("[Bluetooth] Discovery already in progress")
                return False

            success = self.adapter.startDiscovery()
            if success:
                self._change_state(BluetoothState.DISCOVERING)
                logger.info("[Bluetooth] Discovery started")
            else:
                self._notify_error("Failed to start discovery")

            return success

        except Exception as e:
            self._notify_error(f"Discovery failed: {e}")
            return False

    def cancel_discovery(self) -> bool:
        """Cancel ongoing discovery."""
        if not self.adapter:
            return False

        try:
            success = self.adapter.cancelDiscovery()
            if success:
                self._change_state(BluetoothState.IDLE)
            return success
        except Exception as e:
            logger.error(f"[Bluetooth] Cancel discovery error: {e}")
            return False

    def pair_device(self, device_address: str) -> bool:
        """
        Initiate pairing with a device.
        
        Args:
            device_address: Device MAC address
            
        Returns:
            bool: True if pairing initiated, False otherwise
        """
        if not self.adapter:
            return False

        try:
            self._change_state(BluetoothState.PAIRING)
            device = self.adapter.getRemoteDevice(device_address)

            # Create bond (pairing)
            result = device.createBond()
            logger.info(f"[Bluetooth] Pairing initiated with {device_address}")
            return result

        except Exception as e:
            logger.error(f"[Bluetooth] Pairing error: {e}")
            self._change_state(BluetoothState.ERROR)
            return False

    def unpair_device(self, device_address: str) -> bool:
        """
        Unpair a device.
        
        Args:
            device_address: Device MAC address
            
        Returns:
            bool: True if unpair successful, False otherwise
        """
        if not self.adapter:
            return False

        try:
            device = self.adapter.getRemoteDevice(device_address)
            result = device.removeBond()
            logger.info(f"[Bluetooth] Unpaired {device_address}")
            return result
        except Exception as e:
            logger.error(f"[Bluetooth] Unpair error: {e}")
            return False

    def start_server(self, on_connection: Optional[Callable] = None,
                    on_data: Optional[Callable] = None) -> bool:
        """
        Start RFCOMM server for accepting connections.
        
        Args:
            on_connection: Callback(device_info) on client connection
            on_data: Callback(device_address, data) on data received
            
        Returns:
            bool: True if server started, False otherwise
        """
        if not self.adapter:
            self._notify_error("Adapter not initialized")
            return False

        try:
            if self.server:
                logger.debug("[Bluetooth] Server already running")
                return False

            self.server = BluetoothRFCOMMServer(
                self.adapter,
                service_name="GhostNet",
                service_uuid=self.GHOST_NET_SERVICE_UUID,
                on_connection=on_connection,
                on_data=on_data,
                on_error=self._notify_error
            )
            self.server.start()
            self._change_state(BluetoothState.LISTENING)
            logger.info("[Bluetooth] Server started")
            return True

        except Exception as e:
            self._notify_error(f"Server start failed: {e}")
            return False

    def connect_to_device(self, device_address: str,
                         on_connected: Optional[Callable] = None,
                         on_data: Optional[Callable] = None) -> bool:
        """
        Connect to remote device.
        
        Args:
            device_address: Device MAC address
            on_connected: Connection callback
            on_data: Data reception callback
            
        Returns:
            bool: True if connection initiated, False otherwise
        """
        if not self.adapter:
            self._notify_error("Adapter not initialized")
            return False

        try:
            if device_address in self.clients:
                logger.debug(f"[Bluetooth] Already connecting to {device_address}")
                return False

            client = BluetoothRFCOMMClient(
                self.adapter,
                device_address,
                self.GHOST_NET_SERVICE_UUID,
                on_connected=on_connected,
                on_data=on_data,
                on_error=self._notify_error
            )

            with self.lock:
                self.clients[device_address] = client

            # Connect in background thread
            threading.Thread(
                target=client.connect,
                daemon=True,
                name=f"BluetoothConnect-{device_address}"
            ).start()

            return True

        except Exception as e:
            self._notify_error(f"Connect failed: {e}")
            return False

    def send_to_device(self, device_address: str, data: bytes) -> bool:
        """Send data to connected device."""
        with self.lock:
            if device_address in self.clients:
                return self.clients[device_address].send_data(data)
        return False

    def disconnect_device(self, device_address: str):
        """Disconnect from device."""
        with self.lock:
            if device_address in self.clients:
                self.clients[device_address].disconnect()
                del self.clients[device_address]

    def get_discovered_devices(self) -> List[dict]:
        """Get list of discovered devices."""
        with self.lock:
            return [d.to_dict() for d in self.discovered_devices.values()]

    def get_paired_devices(self) -> List[dict]:
        """Get list of paired devices from system."""
        if not self.adapter:
            return []

        try:
            paired = self.adapter.getBondedDevices()
            devices = []
            for device in paired:
                devices.append({
                    'device_name': device.getName(),
                    'device_address': device.getAddress(),
                    'is_paired': True
                })
            return devices
        except Exception as e:
            logger.error(f"[Bluetooth] Get paired devices error: {e}")
            return []

    def start_ble_advertising(self, service_uuid: str, device_name: str) -> bool:
        if not PYJNIUS_AVAILABLE or not self.ble_advertiser:
            logger.warning("[BLE] Advertising not supported or advertiser unavailable")
            return False
            
        try:
            if self.ble_advertise_callback:
                logger.debug("[BLE] Advertising already active")
                return True
                
            UUID = autoclass('java.util.UUID')
            ParcelUuid = autoclass('android.os.ParcelUuid')
            AdvertiseSettings = autoclass('android.bluetooth.le.AdvertiseSettings')
            AdvertiseSettingsBuilder = autoclass('android.bluetooth.le.AdvertiseSettings$Builder')
            AdvertiseData = autoclass('android.bluetooth.le.AdvertiseData')
            AdvertiseDataBuilder = autoclass('android.bluetooth.le.AdvertiseData$Builder')
            
            settings_builder = AdvertiseSettingsBuilder()
            settings_builder.setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            settings_builder.setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            settings_builder.setConnectable(True)
            settings = settings_builder.build()
            
            data_builder = AdvertiseDataBuilder()
            java_uuid = UUID.fromString(service_uuid)
            parcel_uuid = ParcelUuid(java_uuid)
            data_builder.addServiceUuid(parcel_uuid)
            data_builder.setIncludeDeviceName(True)
            data = data_builder.build()
            
            self.ble_advertise_callback = BLEAdvertiseCallback()
            self.ble_advertiser.startAdvertising(settings, data, self.ble_advertise_callback)
            logger.info(f"[BLE] Started advertising service UUID: {service_uuid}")
            return True
        except Exception as e:
            logger.error(f"[BLE] Start advertising failed: {e}")
            self.ble_advertise_callback = None
            return False

    def stop_ble_advertising(self) -> bool:
        if not PYJNIUS_AVAILABLE or not self.ble_advertiser or not self.ble_advertise_callback:
            return False
        try:
            self.ble_advertiser.stopAdvertising(self.ble_advertise_callback)
            self.ble_advertise_callback = None
            logger.info("[BLE] Stopped advertising")
            return True
        except Exception as e:
            logger.error(f"[BLE] Stop advertising failed: {e}")
            return False

    def start_ble_scanning(self, service_uuid: str, on_device_found: Callable) -> bool:
        if not PYJNIUS_AVAILABLE or not self.ble_scanner:
            logger.warning("[BLE] Scanning not supported or scanner unavailable")
            return False
        try:
            if self.ble_scan_callback:
                logger.debug("[BLE] Scan already active")
                return True
                
            UUID = autoclass('java.util.UUID')
            ParcelUuid = autoclass('android.os.ParcelUuid')
            ScanFilterBuilder = autoclass('android.bluetooth.le.ScanFilter$Builder')
            ScanSettingsBuilder = autoclass('android.bluetooth.le.ScanSettings$Builder')
            ScanSettings = autoclass('android.bluetooth.le.ScanSettings')
            ArrayList = autoclass('java.util.ArrayList')
            
            java_uuid = UUID.fromString(service_uuid)
            parcel_uuid = ParcelUuid(java_uuid)
            
            filter_builder = ScanFilterBuilder()
            filter_builder.setServiceUuid(parcel_uuid)
            scan_filter = filter_builder.build()
            
            filters = ArrayList()
            filters.add(scan_filter)
            
            settings_builder = ScanSettingsBuilder()
            settings_builder.setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            scan_settings = settings_builder.build()
            
            def scan_result_callback(device, rssi, name):
                address = device.getAddress()
                on_device_found(address, name or f"BLE_Node_{address[-5:]}", rssi)
                
            self.ble_scan_callback = BLEScanCallback(scan_result_callback)
            self.ble_scanner.startScan(filters, scan_settings, self.ble_scan_callback)
            logger.info(f"[BLE] Started scanning for service UUID: {service_uuid}")
            return True
        except Exception as e:
            logger.error(f"[BLE] Start scanning failed: {e}")
            self.ble_scan_callback = None
            return False

    def stop_ble_scanning(self) -> bool:
        if not PYJNIUS_AVAILABLE or not self.ble_scanner or not self.ble_scan_callback:
            return False
        try:
            self.ble_scanner.stopScan(self.ble_scan_callback)
            self.ble_scan_callback = None
            logger.info("[BLE] Stopped scanning")
            return True
        except Exception as e:
            logger.error(f"[BLE] Stop scanning failed: {e}")
            return False

    def shutdown(self):
        """Clean up resources."""
        with self.lock:
            self.running = False

            # Stop BLE
            try:
                self.stop_ble_advertising()
            except:
                pass
            try:
                self.stop_ble_scanning()
            except:
                pass

            # Disconnect all clients
            for client in self.clients.values():
                try:
                    client.disconnect()
                except:
                    pass
            self.clients.clear()

            # Stop server
            if self.server:
                try:
                    self.server.running = False
                except:
                    pass
                self.server = None

        if self.event_loop_thread:
            self.event_loop_thread.join(timeout=2)

        logger.info("[Bluetooth] Manager shut down")
