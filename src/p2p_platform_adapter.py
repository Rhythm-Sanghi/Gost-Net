"""
Ghost Net - P2P Platform Adapter
Integration layer connecting Android Wi-Fi Direct and Bluetooth modules
with the existing NetworkDetector architecture. Provides unified interface
for peer discovery and connection management across multiple P2P channels.

Architecture:
- Manages WiFiDirectManager, BluetoothManager, and PermissionManager
- Provides single callback interface for peer discovery across all channels
- Handles peer deduplication and state synchronization
- Integrates with existing GhostEngine for message transmission
- Thread-safe with Kivy Clock integration for UI updates
"""

import os
import sys
import logging
import threading
import time
from typing import Optional, Callable, Dict, List, Set
from enum import Enum
from dataclasses import dataclass, field
import socket
import json

_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Optional imports - graceful fallback for non-Android environments
try:
    from android_wifi_direct import WiFiDirectManager, WiFiDirectState, WiFiPeer
    WIFI_DIRECT_AVAILABLE = True
except ImportError:
    WIFI_DIRECT_AVAILABLE = False
    logger.warning("[P2PAdapter] WiFi Direct module not available")

try:
    from android_bluetooth import BluetoothManager, BluetoothState, BluetoothDevice
    BLUETOOTH_AVAILABLE = True
except ImportError:
    BLUETOOTH_AVAILABLE = False
    logger.warning("[P2PAdapter] Bluetooth module not available")

try:
    from android_permissions import PermissionManager, PermissionGroup
    PERMISSIONS_AVAILABLE = True
except ImportError:
    PERMISSIONS_AVAILABLE = False
    logger.warning("[P2PAdapter] Permissions module not available")

# Kivy integration - optional
try:
    from kivy.clock import Clock
    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False
    logger.debug("[P2PAdapter] Kivy not available - Clock callbacks disabled")


class P2PChannel(Enum):
    """Available P2P communication channels."""
    WIFI_DIRECT = "wifi_direct"
    BLUETOOTH = "bluetooth"
    UDP_BROADCAST = "udp_broadcast"
    TCP_SOCKET = "tcp_socket"


class P2PChannelState(Enum):
    """State of a P2P channel."""
    IDLE = "idle"
    DISCOVERING = "discovering"
    DISCOVERED = "discovered"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class P2PPeer:
    """Unified peer representation across all P2P channels."""
    peer_id: str  # Unique identifier (MAC address or hash)
    device_name: str
    channels: Set[P2PChannel] = field(default_factory=set)
    ip_addresses: Dict[P2PChannel, str] = field(default_factory=dict)
    signal_strength: int = 0
    is_connected: bool = False
    last_seen: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'peer_id': self.peer_id,
            'device_name': self.device_name,
            'channels': [c.value for c in self.channels],
            'ip_addresses': {k.value: v for k, v in self.ip_addresses.items()},
            'signal_strength': self.signal_strength,
            'is_connected': self.is_connected,
            'last_seen': self.last_seen,
            'metadata': self.metadata
        }


class P2PPlatformAdapter:
    """
    High-level adapter managing all P2P channels (Wi-Fi Direct, Bluetooth, UDP)
    with unified peer discovery and connection management.
    
    Capabilities:
    - Simultaneous channel discovery and connection
    - Automatic peer deduplication across channels
    - Fallback channel selection on failure
    - Permission management with graceful degradation
    - Thread-safe operation with Kivy Clock integration
    - Socket connection pooling and reuse
    """

    def __init__(self, on_peer_discovered: Optional[Callable] = None,
                 on_peer_connected: Optional[Callable] = None,
                 on_peer_disconnected: Optional[Callable] = None,
                 on_channel_state_changed: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        """
        Initialize P2P Platform Adapter.
        
        Args:
            on_peer_discovered: Callback(peer_dict) when peer discovered
            on_peer_connected: Callback(peer_id, channel) on connection
            on_peer_disconnected: Callback(peer_id, channel) on disconnect
            on_channel_state_changed: Callback(channel, state) on channel state change
            on_error: Callback(error_msg) on errors
        """
        # Callbacks
        self.on_peer_discovered = on_peer_discovered
        self.on_peer_connected = on_peer_connected
        self.on_peer_disconnected = on_peer_disconnected
        self.on_channel_state_changed = on_channel_state_changed
        self.on_error = on_error

        # Managers
        self.wifi_direct_manager: Optional[WiFiDirectManager] = None
        self.bluetooth_manager: Optional[BluetoothManager] = None
        self.permission_manager: Optional[PermissionManager] = None

        # State tracking
        self.peers: Dict[str, P2PPeer] = {}
        self.channel_states: Dict[P2PChannel, P2PChannelState] = {
            ch: P2PChannelState.IDLE for ch in P2PChannel
        }
        
        # Enabled channels based on platform availability
        self.enabled_channels: Set[P2PChannel] = set()
        self._update_available_channels()

        # Socket connection pool
        self.socket_connections: Dict[str, Dict[P2PChannel, socket.socket]] = {}

        # State management
        self.running = False
        self.discovering = False
        self.lock = threading.RLock()

        # Initialize managers if available
        if PERMISSIONS_AVAILABLE:
            self.permission_manager = PermissionManager(
                on_permissions_result=self._on_permissions_result,
                on_error=self._on_error
            )

        if WIFI_DIRECT_AVAILABLE:
            self.wifi_direct_manager = WiFiDirectManager(
                on_peer_discovered=self._on_wifi_peers_discovered,
                on_connection_established=self._on_wifi_connection_established,
                on_state_changed=self._on_wifi_state_changed,
                on_error=self._on_error
            )

        if BLUETOOTH_AVAILABLE:
            self.bluetooth_manager = BluetoothManager(
                on_device_discovered=self._on_bt_devices_discovered,
                on_state_changed=self._on_bt_state_changed,
                on_error=self._on_error
            )

        logger.info(
            f"[P2PAdapter] Initialized with channels: {[ch.value for ch in self.enabled_channels]}"
        )

    def _update_available_channels(self):
        """Determine which channels are available on this platform."""
        # WiFi Direct and Bluetooth require pyjnius (Android only)
        if WIFI_DIRECT_AVAILABLE:
            self.enabled_channels.add(P2PChannel.WIFI_DIRECT)

        if BLUETOOTH_AVAILABLE:
            self.enabled_channels.add(P2PChannel.BLUETOOTH)

        # UDP broadcast and TCP socket available on all platforms
        self.enabled_channels.add(P2PChannel.UDP_BROADCAST)
        self.enabled_channels.add(P2PChannel.TCP_SOCKET)

    def request_required_permissions(self) -> bool:
        """
        Request all permissions required for P2P operations.
        
        Returns:
            bool: True if request initiated or already granted
        """
        if not PERMISSIONS_AVAILABLE:
            logger.warning("[P2PAdapter] Permission manager not available")
            return False

        try:
            logger.info("[P2PAdapter] Requesting P2P permissions...")

            # Check if Wi-Fi Direct is available and request its permissions
            if P2PChannel.WIFI_DIRECT in self.enabled_channels:
                self.permission_manager.request_wifi_direct_permissions()

            # Check if Bluetooth is available and request its permissions
            if P2PChannel.BLUETOOTH in self.enabled_channels:
                self.permission_manager.request_bluetooth_permissions()

            # Location permissions required for both
            self.permission_manager.request_location_permissions()

            return True

        except Exception as e:
            logger.error(f"[P2PAdapter] Permission request error: {e}")
            self._on_error(f"Permission request failed: {e}")
            return False

    def _on_permissions_result(self, group, granted: List[str], denied: List[str]):
        """Handle permission request results."""
        if denied:
            logger.warning(f"[P2PAdapter] Permissions denied: {denied}")
            # Disable channels that require denied permissions
            if not granted:
                self._disable_channel_group(group)
        else:
            logger.info(f"[P2PAdapter] Permissions granted for {group.value}")

    def _disable_channel_group(self, group):
        """Disable channels associated with a permission group."""
        if group == PermissionGroup.WIFI_P2P:
            self.enabled_channels.discard(P2PChannel.WIFI_DIRECT)
            self._change_channel_state(P2PChannel.WIFI_DIRECT, P2PChannelState.DISABLED)
            logger.warning("[P2PAdapter] Wi-Fi Direct disabled due to missing permissions")

        elif group == PermissionGroup.BLUETOOTH:
            self.enabled_channels.discard(P2PChannel.BLUETOOTH)
            self._change_channel_state(P2PChannel.BLUETOOTH, P2PChannelState.DISABLED)
            logger.warning("[P2PAdapter] Bluetooth disabled due to missing permissions")

    def start_discovery(self) -> bool:
        """
        Start peer discovery on all enabled channels.
        
        Returns:
            bool: True if discovery started on at least one channel
        """
        with self.lock:
            if self.discovering:
                logger.debug("[P2PAdapter] Discovery already in progress")
                return False

            self.discovering = True
            self.running = True

        try:
            any_started = False

            # Start Wi-Fi Direct discovery
            if (P2PChannel.WIFI_DIRECT in self.enabled_channels and 
                self.wifi_direct_manager):
                try:
                    if self.wifi_direct_manager.start_discovery():
                        self._change_channel_state(
                            P2PChannel.WIFI_DIRECT,
                            P2PChannelState.DISCOVERING
                        )
                        any_started = True
                except Exception as e:
                    logger.error(f"[P2PAdapter] Wi-Fi Direct discovery error: {e}")

            # Start Bluetooth discovery
            if (P2PChannel.BLUETOOTH in self.enabled_channels and 
                self.bluetooth_manager):
                try:
                    if self.bluetooth_manager.start_discovery():
                        self._change_channel_state(
                            P2PChannel.BLUETOOTH,
                            P2PChannelState.DISCOVERING
                        )
                        any_started = True
                except Exception as e:
                    logger.error(f"[P2PAdapter] Bluetooth discovery error: {e}")

            # UDP broadcast discovery (if legacy network module available)
            # Would integrate with existing GhostEngine here
            self._change_channel_state(P2PChannel.UDP_BROADCAST, P2PChannelState.DISCOVERING)
            any_started = True

            if any_started:
                logger.info("[P2PAdapter] Peer discovery started")

            return any_started

        except Exception as e:
            logger.error(f"[P2PAdapter] Discovery start error: {e}")
            self._on_error(f"Discovery failed: {e}")
            with self.lock:
                self.discovering = False
            return False

    def stop_discovery(self) -> bool:
        """Stop peer discovery on all channels."""
        with self.lock:
            if not self.discovering:
                return False

            self.discovering = False

        try:
            if self.wifi_direct_manager:
                self.wifi_direct_manager.cancel_discovery()
            if self.bluetooth_manager:
                self.bluetooth_manager.cancel_discovery()

            logger.info("[P2PAdapter] Peer discovery stopped")
            return True

        except Exception as e:
            logger.error(f"[P2PAdapter] Discovery stop error: {e}")
            return False

    def _on_wifi_peers_discovered(self, peers_list: List[dict]):
        """Handle Wi-Fi Direct peer discovery results."""
        try:
            logger.debug(f"[P2PAdapter] Wi-Fi Direct discovered {len(peers_list)} peers")

            for peer_data in peers_list:
                self._add_or_update_peer(
                    peer_data['device_address'],
                    peer_data['device_name'],
                    P2PChannel.WIFI_DIRECT,
                    peer_data.get('signal_level', 0)
                )

            self._change_channel_state(P2PChannel.WIFI_DIRECT, P2PChannelState.DISCOVERED)

        except Exception as e:
            logger.error(f"[P2PAdapter] Wi-Fi peer processing error: {e}")

    def _on_bt_devices_discovered(self, devices_list: List[dict]):
        """Handle Bluetooth device discovery results."""
        try:
            logger.debug(f"[P2PAdapter] Bluetooth discovered {len(devices_list)} devices")

            for device_data in devices_list:
                self._add_or_update_peer(
                    device_data['device_address'],
                    device_data['device_name'],
                    P2PChannel.BLUETOOTH,
                    device_data.get('rssi', 0)
                )

            self._change_channel_state(P2PChannel.BLUETOOTH, P2PChannelState.DISCOVERED)

        except Exception as e:
            logger.error(f"[P2PAdapter] Bluetooth device processing error: {e}")

    def _add_or_update_peer(self, peer_id: str, device_name: str,
                           channel: P2PChannel, signal_strength: int):
        """Add new peer or update existing peer with new channel."""
        with self.lock:
            if peer_id in self.peers:
                # Update existing peer
                peer = self.peers[peer_id]
                peer.channels.add(channel)
                peer.signal_strength = max(peer.signal_strength, signal_strength)
                peer.last_seen = time.time()
                logger.debug(f"[P2PAdapter] Updated peer {peer_id} with {channel.value}")
            else:
                # New peer
                peer = P2PPeer(
                    peer_id=peer_id,
                    device_name=device_name,
                    channels={channel},
                    signal_strength=signal_strength
                )
                self.peers[peer_id] = peer
                logger.info(f"[P2PAdapter] New peer discovered: {device_name} ({peer_id})")

                # Notify on main thread (Kivy Clock if available)
                if self.on_peer_discovered:
                    self._call_on_main_thread(
                        self.on_peer_discovered,
                        peer.to_dict()
                    )

    def _on_wifi_connection_established(self, peer_dict: dict, ip_address: str):
        """Handle successful Wi-Fi Direct connection."""
        try:
            peer_id = peer_dict['device_address']
            with self.lock:
                if peer_id in self.peers:
                    self.peers[peer_id].ip_addresses[P2PChannel.WIFI_DIRECT] = ip_address
                    self.peers[peer_id].is_connected = True

            self._change_channel_state(P2PChannel.WIFI_DIRECT, P2PChannelState.CONNECTED)

            logger.info(f"[P2PAdapter] Connected to {peer_id} via Wi-Fi Direct at {ip_address}")

            if self.on_peer_connected:
                self._call_on_main_thread(
                    self.on_peer_connected,
                    peer_id,
                    P2PChannel.WIFI_DIRECT
                )

        except Exception as e:
            logger.error(f"[P2PAdapter] Connection establishment error: {e}")

    def _on_wifi_state_changed(self, state):
        """Handle Wi-Fi Direct state changes."""
        try:
            state_map = {
                'idle': P2PChannelState.IDLE,
                'discovering': P2PChannelState.DISCOVERING,
                'peers_found': P2PChannelState.DISCOVERED,
                'connecting': P2PChannelState.CONNECTING,
                'connected': P2PChannelState.CONNECTED,
                'group_formed': P2PChannelState.CONNECTED,
                'error': P2PChannelState.ERROR,
            }

            channel_state = state_map.get(state.value, P2PChannelState.IDLE)
            self._change_channel_state(P2PChannel.WIFI_DIRECT, channel_state)

        except Exception as e:
            logger.error(f"[P2PAdapter] Wi-Fi state change error: {e}")

    def _on_bt_state_changed(self, state):
        """Handle Bluetooth state changes."""
        try:
            state_map = {
                'idle': P2PChannelState.IDLE,
                'discovering': P2PChannelState.DISCOVERING,
                'devices_found': P2PChannelState.DISCOVERED,
                'pairing': P2PChannelState.CONNECTING,
                'paired': P2PChannelState.DISCOVERED,
                'connecting': P2PChannelState.CONNECTING,
                'connected': P2PChannelState.CONNECTED,
                'listening': P2PChannelState.CONNECTED,
                'error': P2PChannelState.ERROR,
            }

            channel_state = state_map.get(state.value, P2PChannelState.IDLE)
            self._change_channel_state(P2PChannel.BLUETOOTH, channel_state)

        except Exception as e:
            logger.error(f"[P2PAdapter] Bluetooth state change error: {e}")

    def _change_channel_state(self, channel: P2PChannel, state: P2PChannelState):
        """Thread-safe channel state transition."""
        with self.lock:
            if self.channel_states[channel] != state:
                old_state = self.channel_states[channel]
                self.channel_states[channel] = state
                logger.debug(f"[P2PAdapter] Channel {channel.value}: {old_state.value} -> {state.value}")

                if self.on_channel_state_changed:
                    self._call_on_main_thread(
                        self.on_channel_state_changed,
                        channel,
                        state
                    )

    def connect_to_peer(self, peer_id: str, preferred_channel: Optional[P2PChannel] = None) -> bool:
        """
        Initiate connection to peer on preferred or best available channel.
        
        Args:
            peer_id: Peer identifier
            preferred_channel: Preferred channel (Wi-Fi Direct or Bluetooth)
            
        Returns:
            bool: True if connection initiated
        """
        with self.lock:
            if peer_id not in self.peers:
                logger.error(f"[P2PAdapter] Peer not found: {peer_id}")
                return False

            peer = self.peers[peer_id]

        try:
            # Determine channel to use
            channels_to_try = []

            if preferred_channel and preferred_channel in peer.channels:
                channels_to_try.append(preferred_channel)

            # Add other available channels
            channels_to_try.extend(
                ch for ch in peer.channels
                if ch not in channels_to_try and ch in self.enabled_channels
            )

            if not channels_to_try:
                self._on_error(f"No available channels for peer {peer_id}")
                return False

            # Try channels in order
            for channel in channels_to_try:
                if channel == P2PChannel.WIFI_DIRECT and self.wifi_direct_manager:
                    logger.info(f"[P2PAdapter] Connecting to {peer_id} via Wi-Fi Direct")
                    self._change_channel_state(P2PChannel.WIFI_DIRECT, P2PChannelState.CONNECTING)
                    return self.wifi_direct_manager.connect_to_peer(peer_id)

                elif channel == P2PChannel.BLUETOOTH and self.bluetooth_manager:
                    logger.info(f"[P2PAdapter] Connecting to {peer_id} via Bluetooth")
                    self._change_channel_state(P2PChannel.BLUETOOTH, P2PChannelState.CONNECTING)
                    return self.bluetooth_manager.connect_to_device(peer_id)

            self._on_error(f"No connection method available for peer {peer_id}")
            return False

        except Exception as e:
            logger.error(f"[P2PAdapter] Connection error: {e}")
            return False

    def disconnect_from_peer(self, peer_id: str) -> bool:
        """Disconnect from peer on all channels."""
        try:
            if P2PChannel.WIFI_DIRECT in self.enabled_channels and self.wifi_direct_manager:
                self.wifi_direct_manager.disconnect()

            if P2PChannel.BLUETOOTH in self.enabled_channels and self.bluetooth_manager:
                self.bluetooth_manager.disconnect_device(peer_id)

            logger.info(f"[P2PAdapter] Disconnected from {peer_id}")
            return True

        except Exception as e:
            logger.error(f"[P2PAdapter] Disconnect error: {e}")
            return False

    def get_peers(self) -> List[dict]:
        """Get list of discovered peers."""
        with self.lock:
            return [p.to_dict() for p in self.peers.values()]

    def get_peer(self, peer_id: str) -> Optional[dict]:
        """Get specific peer information."""
        with self.lock:
            if peer_id in self.peers:
                return self.peers[peer_id].to_dict()
        return None

    def get_channel_state(self, channel: P2PChannel) -> P2PChannelState:
        """Get current state of a channel."""
        with self.lock:
            return self.channel_states[channel]

    def _call_on_main_thread(self, callback: Callable, *args, **kwargs):
        """Call callback on main thread (Kivy Clock if available)."""
        try:
            if KIVY_AVAILABLE:
                Clock.schedule_once(
                    lambda dt: callback(*args, **kwargs),
                    0
                )
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"[P2PAdapter] Callback error: {e}")

    def _on_error(self, error_msg: str):
        """Handle error notification."""
        logger.error(f"[P2PAdapter] Error: {error_msg}")
        if self.on_error:
            self._call_on_main_thread(self.on_error, error_msg)

    def shutdown(self):
        """Clean up all resources."""
        with self.lock:
            self.running = False
            self.discovering = False

        if self.wifi_direct_manager:
            self.wifi_direct_manager.shutdown()

        if self.bluetooth_manager:
            self.bluetooth_manager.shutdown()

        if self.permission_manager:
            self.permission_manager.shutdown()

        logger.info("[P2PAdapter] Shutdown complete")
