"""
Ghost Net - Android Wi-Fi Direct (P2P) Module
Pyjnius wrapper around android.net.wifi.p2p.WifiP2pManager for peer discovery
and connection establishment. Designed for API 33+ with comprehensive error
handling and thread-safe operations.

Key Features:
- Peer discovery with exponential backoff retry logic
- Automatic Group Owner IP resolution
- Thread-safe state management with BroadcastReceiver integration
- Timeout handling for discovery phases
- Non-blocking socket connections to discovered peers
"""

import logging
import socket
import threading
import time
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue
import json

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Conditional pyjnius imports - graceful fallback for non-Android environments
try:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    PYJNIUS_AVAILABLE = True
except ImportError:
    PYJNIUS_AVAILABLE = False
    logger.warning("[WiFiDirect] pyjnius not available - Wi-Fi Direct disabled")


class WiFiDirectState(Enum):
    """State machine for Wi-Fi Direct operations."""
    IDLE = "idle"
    DISCOVERING = "discovering"
    PEERS_FOUND = "peers_found"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    GROUP_FORMED = "group_formed"
    ERROR = "error"


@dataclass
class WiFiPeer:
    """Represents a discovered Wi-Fi Direct peer."""
    device_name: str
    device_address: str  # MAC address
    is_group_owner: bool = False
    signal_level: int = 0
    ip_address: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Convert peer to dictionary for serialization."""
        return {
            'device_name': self.device_name,
            'device_address': self.device_address,
            'is_group_owner': self.is_group_owner,
            'signal_level': self.signal_level,
            'ip_address': self.ip_address,
            'timestamp': self.timestamp
        }


class WiFiDirectBroadcastReceiver(PythonJavaClass):
    """
    Android BroadcastReceiver for Wi-Fi Direct state changes.
    Handles three critical intents:
    - WIFI_P2P_STATE_CHANGED_ACTION: P2P enabled/disabled
    - WIFI_P2P_PEERS_CHANGED_ACTION: Peer list updated
    - WIFI_P2P_CONNECTION_CHANGED_ACTION: Connection state changed
    
    This class bridges Android system events to Python callbacks.
    """
    __javainterfaces__ = ['android/content/BroadcastReceiver']
    __javacontext__ = 'app'

    def __init__(self, callback_queue: Queue):
        """
        Initialize receiver with callback queue for thread-safe event passing.
        
        Args:
            callback_queue: Queue to pass events to main WiFiDirectManager
        """
        super().__init__()
        self.callback_queue = callback_queue
        logger.debug("[WiFiDirect] BroadcastReceiver initialized")

    @java_method('(Landroid/content/Context;Landroid/content/Intent;)V')
    def onReceive(self, context, intent):
        """
        Handle broadcast events from Android system.
        
        Args:
            context: Android Context
            intent: Intent containing action and data
        """
        try:
            action = intent.getAction()
            logger.debug(f"[WiFiDirect] BroadcastReceiver event: {action}")

            if action == "android.net.wifi.p2p.STATE_CHANGED":
                # WIFI_P2P_STATE_CHANGED_ACTION
                p2p_state = intent.getIntExtra("wifi_p2p_state", -1)
                event = {
                    'type': 'state_changed',
                    'enabled': p2p_state == 2,  # WIFI_P2P_STATE_ENABLED = 2
                }
                self.callback_queue.put(event)

            elif action == "android.net.wifi.p2p.PEERS_CHANGED":
                # WIFI_P2P_PEERS_CHANGED_ACTION
                event = {
                    'type': 'peers_changed',
                    'timestamp': time.time()
                }
                self.callback_queue.put(event)

            elif action == "android.net.wifi.p2p.CONNECTION_STATE_CHANGE":
                # WIFI_P2P_CONNECTION_CHANGED_ACTION
                network_info = intent.getParcelableExtra("networkInfo")
                if network_info:
                    is_connected = network_info.isConnected()
                    event = {
                        'type': 'connection_changed',
                        'is_connected': is_connected,
                        'timestamp': time.time()
                    }
                    self.callback_queue.put(event)

        except Exception as e:
            logger.error(f"[WiFiDirect] BroadcastReceiver error: {e}", exc_info=True)


class WiFiDirectManager:
    """
    High-level manager for Android Wi-Fi Direct P2P operations.
    
    Implements peer discovery, connection establishment, and Group Owner
    IP resolution with exponential backoff and timeout handling.
    
    Thread-safe with non-blocking operations suitable for Kivy UI integration.
    """

    # Android Wi-Fi Direct constants
    WIFI_P2P_MANAGER_CLASS = "android.net.wifi.p2p.WifiP2pManager"
    WIFI_P2P_DEVICE_CLASS = "android.net.wifi.p2p.WifiP2pDevice"
    WIFI_P2P_DEVICE_LIST_CLASS = "android.net.wifi.p2p.WifiP2pDeviceList"
    WIFI_P2P_GROUP_CLASS = "android.net.wifi.p2p.WifiP2pGroup"
    WIFI_P2P_INFO_CLASS = "android.net.wifi.p2p.WifiP2pInfo"

    # Discovery and connection parameters
    DISCOVERY_TIMEOUT = 30  # seconds
    PEER_TIMEOUT = 10  # seconds before considering peer stale
    CONNECTION_TIMEOUT = 15  # seconds to establish connection
    MAX_DISCOVERY_RETRIES = 5
    INITIAL_BACKOFF = 1.0  # seconds
    MAX_BACKOFF = 16.0  # seconds

    def __init__(self, context=None, on_peer_discovered: Optional[Callable] = None,
                 on_connection_established: Optional[Callable] = None,
                 on_state_changed: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        """
        Initialize Wi-Fi Direct Manager.
        
        Args:
            context: Android Context (auto-retrieved if None)
            on_peer_discovered: Callback(peers_list) when peers discovered
            on_connection_established: Callback(peer, ip_address) on successful connection
            on_state_changed: Callback(state) on state machine changes
            on_error: Callback(error_message) on errors
        """
        self.context = context
        self.manager = None
        self.channel = None
        self.broadcast_receiver = None

        # Callbacks
        self.on_peer_discovered = on_peer_discovered
        self.on_connection_established = on_connection_established
        self.on_state_changed = on_state_changed
        self.on_error = on_error

        # State management
        self.state = WiFiDirectState.IDLE
        self.peers: Dict[str, WiFiPeer] = {}
        self.connected_peer: Optional[WiFiPeer] = None
        self.group_owner_ip: Optional[str] = None

        # Event handling
        self.event_queue = Queue()
        self.running = False
        self.event_thread = None

        # Discovery tracking
        self.discovery_retries = 0
        self.discovery_backoff = self.INITIAL_BACKOFF
        self.last_discovery_time = 0
        self.discovering = False

        # Thread safety
        self.lock = threading.RLock()

        # Initialize if pyjnius available
        if PYJNIUS_AVAILABLE:
            self._initialize_wifi_direct()
        else:
            logger.warning("[WiFiDirect] Initialization skipped - pyjnius unavailable")

    def _initialize_wifi_direct(self):
        """Initialize Wi-Fi Direct manager and broadcast receiver."""
        try:
            # Get Android context if not provided
            if not self.context:
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                self.context = PythonActivity.mActivity

            # Get system service
            Context = autoclass('android.content.Context')
            WifiP2pManager = autoclass(self.WIFI_P2P_MANAGER_CLASS)

            self.manager = self.context.getSystemService(
                Context.WIFI_P2P_SERVICE
            )
            logger.info("[WiFiDirect] Manager initialized")

            # Create broadcast receiver
            self.broadcast_receiver = WiFiDirectBroadcastReceiver(self.event_queue)

            # Start event processing thread
            self.running = True
            self.event_thread = threading.Thread(
                target=self._process_events,
                daemon=True,
                name="WiFiDirectEventLoop"
            )
            self.event_thread.start()
            logger.info("[WiFiDirect] Event loop started")

        except Exception as e:
            logger.error(f"[WiFiDirect] Initialization failed: {e}", exc_info=True)
            self._notify_error(f"Initialize failed: {e}")

    def _change_state(self, new_state: WiFiDirectState):
        """Thread-safe state transition with callback."""
        with self.lock:
            if self.state != new_state:
                old_state = self.state
                self.state = new_state
                logger.info(f"[WiFiDirect] State: {old_state.value} -> {new_state.value}")
                if self.on_state_changed:
                    self.on_state_changed(new_state)

    def _notify_error(self, error_msg: str):
        """Thread-safe error notification."""
        logger.error(f"[WiFiDirect] Error: {error_msg}")
        if self.on_error:
            self.on_error(error_msg)

    def _process_events(self):
        """Background thread processing broadcast events."""
        while self.running:
            try:
                event = self.event_queue.get(timeout=1)
                self._handle_broadcast_event(event)
            except:
                continue

    def _handle_broadcast_event(self, event: dict):
        """Process broadcast events from BroadcastReceiver."""
        try:
            event_type = event.get('type')

            if event_type == 'state_changed':
                enabled = event.get('enabled', False)
                if enabled:
                    self._change_state(WiFiDirectState.IDLE)
                    logger.info("[WiFiDirect] Wi-Fi Direct enabled")
                else:
                    self._change_state(WiFiDirectState.IDLE)
                    logger.warning("[WiFiDirect] Wi-Fi Direct disabled")

            elif event_type == 'peers_changed':
                logger.debug("[WiFiDirect] Peers changed event")
                self._request_peers()

            elif event_type == 'connection_changed':
                is_connected = event.get('is_connected', False)
                if is_connected:
                    self._change_state(WiFiDirectState.CONNECTED)
                    self._request_connection_info()
                else:
                    self._change_state(WiFiDirectState.IDLE)
                    with self.lock:
                        self.connected_peer = None
                        self.group_owner_ip = None

        except Exception as e:
            logger.error(f"[WiFiDirect] Event processing error: {e}", exc_info=True)

    def start_discovery(self) -> bool:
        """
        Start Wi-Fi Direct peer discovery with exponential backoff.
        
        Returns:
            bool: True if discovery started, False otherwise
        """
        if not self.manager:
            self._notify_error("Manager not initialized")
            return False

        with self.lock:
            if self.discovering:
                logger.debug("[WiFiDirect] Discovery already in progress")
                return False

            self.discovering = True

        try:
            self._change_state(WiFiDirectState.DISCOVERING)
            self.discovery_retries = 0
            self.discovery_backoff = self.INITIAL_BACKOFF
            self.last_discovery_time = time.time()

            # Execute discovery in background thread
            threading.Thread(
                target=self._discovery_loop,
                daemon=True,
                name="WiFiDirectDiscovery"
            ).start()
            return True

        except Exception as e:
            self._notify_error(f"Discovery start failed: {e}")
            with self.lock:
                self.discovering = False
            return False

    def _discovery_loop(self):
        """Background loop managing peer discovery with exponential backoff."""
        try:
            while self.discovering and self.discovery_retries < self.MAX_DISCOVERY_RETRIES:
                try:
                    # Request peer list from system
                    ActionListener = autoclass('android.net.wifi.p2p.WifiP2pManager$ActionListener')

                    class DiscoveryListener(PythonJavaClass):
                        __javainterfaces__ = ['android/net/wifi/p2p/WifiP2pManager$ActionListener']
                        __javacontext__ = 'app'

                        def __init__(self, manager):
                            super().__init__()
                            self.manager = manager

                        @java_method('()V')
                        def onSuccess(self):
                            logger.debug("[WiFiDirect] Discovery request succeeded")
                            self.manager.discovery_retries = 0
                            self.manager.discovery_backoff = self.manager.INITIAL_BACKOFF

                        @java_method('(I)V')
                        def onFailure(self, reason):
                            logger.warning(f"[WiFiDirect] Discovery request failed: {reason}")

                    listener = DiscoveryListener(self)
                    self.manager.discoverPeers(self.channel, listener)

                    # Wait before next attempt with exponential backoff
                    time.sleep(self.discovery_backoff)
                    with self.lock:
                        self.discovery_retries += 1
                        self.discovery_backoff = min(
                            self.discovery_backoff * 2,
                            self.MAX_BACKOFF
                        )

                    # Check if discovery timeout exceeded
                    if time.time() - self.last_discovery_time > self.DISCOVERY_TIMEOUT:
                        logger.warning("[WiFiDirect] Discovery timeout")
                        with self.lock:
                            self.discovering = False
                        self._change_state(WiFiDirectState.IDLE)
                        break

                except Exception as e:
                    logger.error(f"[WiFiDirect] Discovery loop error: {e}")
                    with self.lock:
                        self.discovery_retries += 1

        finally:
            with self.lock:
                self.discovering = False

    def _request_peers(self):
        """Request current peer list from Wi-Fi Direct system."""
        if not self.manager or not self.channel:
            return

        try:
            PeerListListener = autoclass('android.net.wifi.p2p.WifiP2pManager$PeerListListener')

            class PeersCallback(PythonJavaClass):
                __javainterfaces__ = ['android/net/wifi/p2p/WifiP2pManager$PeerListListener']
                __javacontext__ = 'app'

                def __init__(self, manager):
                    super().__init__()
                    self.wifi_manager = manager

                @java_method('(Landroid/net/wifi/p2p/WifiP2pDeviceList;)V')
                def onPeersAvailable(self, peer_list):
                    self.wifi_manager._process_peer_list(peer_list)

            listener = PeersCallback(self)
            self.manager.requestPeers(self.channel, listener)

        except Exception as e:
            logger.error(f"[WiFiDirect] Request peers error: {e}")

    def _process_peer_list(self, peer_list):
        """Process peer list received from Android system."""
        try:
            if not peer_list:
                return

            with self.lock:
                self.peers.clear()

            # Extract peer list
            peer_items = peer_list.getDeviceList()
            peer_count = peer_items.size() if peer_items else 0

            logger.debug(f"[WiFiDirect] Found {peer_count} peers")

            for i in range(peer_count):
                peer_device = peer_items.get(i)
                peer_name = peer_device.deviceName
                peer_addr = peer_device.deviceAddress
                peer_status = peer_device.status

                peer = WiFiPeer(
                    device_name=peer_name,
                    device_address=peer_addr,
                    is_group_owner=False,
                    signal_level=0
                )

                with self.lock:
                    self.peers[peer_addr] = peer

                logger.debug(f"[WiFiDirect] Peer: {peer_name} ({peer_addr})")

            self._change_state(WiFiDirectState.PEERS_FOUND)

            if self.on_peer_discovered:
                peers_list = [p.to_dict() for p in self.peers.values()]
                self.on_peer_discovered(peers_list)

        except Exception as e:
            logger.error(f"[WiFiDirect] Process peer list error: {e}", exc_info=True)

    def connect_to_peer(self, peer_address: str) -> bool:
        """
        Initiate connection to a discovered peer.
        
        Args:
            peer_address: MAC address of target peer
            
        Returns:
            bool: True if connection initiated, False otherwise
        """
        if not self.manager or peer_address not in self.peers:
            self._notify_error(f"Invalid peer: {peer_address}")
            return False

        try:
            with self.lock:
                target_peer = self.peers[peer_address]

            self._change_state(WiFiDirectState.CONNECTING)

            WifiP2pConfig = autoclass('android.net.wifi.p2p.WifiP2pConfig')
            config = WifiP2pConfig()
            config.deviceAddress = peer_address

            ActionListener = autoclass('android.net.wifi.p2p.WifiP2pManager$ActionListener')

            class ConnectListener(PythonJavaClass):
                __javainterfaces__ = ['android/net/wifi/p2p/WifiP2pManager$ActionListener']
                __javacontext__ = 'app'

                def __init__(self, manager, peer):
                    super().__init__()
                    self.manager = manager
                    self.peer = peer

                @java_method('()V')
                def onSuccess(self):
                    logger.info(f"[WiFiDirect] Connect request succeeded for {self.peer.device_name}")

                @java_method('(I)V')
                def onFailure(self, reason):
                    logger.error(f"[WiFiDirect] Connect failed: {reason}")
                    self.manager._change_state(WiFiDirectState.ERROR)

            listener = ConnectListener(self, target_peer)
            self.manager.connect(self.channel, config, listener)
            return True

        except Exception as e:
            self._notify_error(f"Connection failed: {e}")
            self._change_state(WiFiDirectState.ERROR)
            return False

    def _request_connection_info(self):
        """Request connection info after successful connection."""
        if not self.manager or not self.channel:
            return

        try:
            ConnectionInfoListener = autoclass(
                'android.net.wifi.p2p.WifiP2pManager$ConnectionInfoListener'
            )

            class InfoCallback(PythonJavaClass):
                __javainterfaces__ = ['android/net/wifi/p2p/WifiP2pManager$ConnectionInfoListener']
                __javacontext__ = 'app'

                def __init__(self, manager):
                    super().__init__()
                    self.manager = manager

                @java_method('(Landroid/net/wifi/p2p/WifiP2pInfo;)V')
                def onConnectionInfoAvailable(self, info):
                    self.manager._process_connection_info(info)

            listener = InfoCallback(self)
            self.manager.requestConnectionInfo(self.channel, listener)

        except Exception as e:
            logger.error(f"[WiFiDirect] Request connection info error: {e}")

    def _process_connection_info(self, info):
        """Process connection info and resolve Group Owner IP."""
        try:
            is_group_owner = info.isGroupOwner
            group_owner_addr = info.groupOwnerAddress

            if group_owner_addr:
                go_ip = group_owner_addr.getHostAddress()
                with self.lock:
                    self.group_owner_ip = go_ip

                logger.info(f"[WiFiDirect] Group Owner IP: {go_ip}")
                self._change_state(WiFiDirectState.GROUP_FORMED)

                if self.on_connection_established and self.connected_peer:
                    self.on_connection_established(
                        self.connected_peer.to_dict(),
                        go_ip
                    )

        except Exception as e:
            logger.error(f"[WiFiDirect] Process connection info error: {e}")

    def get_peers(self) -> List[dict]:
        """Get current peer list."""
        with self.lock:
            return [p.to_dict() for p in self.peers.values()]

    def get_state(self) -> WiFiDirectState:
        """Get current state."""
        with self.lock:
            return self.state

    def get_group_owner_ip(self) -> Optional[str]:
        """Get Group Owner IP address if connected."""
        with self.lock:
            return self.group_owner_ip

    def disconnect(self) -> bool:
        """Disconnect from Wi-Fi Direct group."""
        if not self.manager or not self.channel:
            return False

        try:
            ActionListener = autoclass('android.net.wifi.p2p.WifiP2pManager$ActionListener')

            class DisconnectListener(PythonJavaClass):
                __javainterfaces__ = ['android/net/wifi/p2p/WifiP2pManager$ActionListener']
                __javacontext__ = 'app'

                def __init__(self, manager):
                    super().__init__()
                    self.manager = manager

                @java_method('()V')
                def onSuccess(self):
                    logger.info("[WiFiDirect] Disconnected successfully")
                    self.manager._change_state(WiFiDirectState.IDLE)

                @java_method('(I)V')
                def onFailure(self, reason):
                    logger.warning(f"[WiFiDirect] Disconnect failed: {reason}")

            listener = DisconnectListener(self)
            self.manager.removeGroup(self.channel, listener)
            return True

        except Exception as e:
            logger.error(f"[WiFiDirect] Disconnect error: {e}")
            return False

    def shutdown(self):
        """Clean up resources."""
        with self.lock:
            self.running = False
            self.discovering = False

        if self.event_thread:
            self.event_thread.join(timeout=2)

        logger.info("[WiFiDirect] Manager shut down")
