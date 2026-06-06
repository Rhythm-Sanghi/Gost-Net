import socket
import json
import threading
import time
from typing import Dict, List, Optional, Callable
from enum import Enum

from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth


class DiscoveryMode(Enum):
    WIFI_LAN = "wifi_lan"
    WIFI_DIRECT = "wifi_direct"
    BLUETOOTH = "bluetooth"
    HYBRID = "hybrid"


class P2PPeerTracker:
    
    def __init__(self):
        self.wifi_direct_peers: Dict[str, dict] = {}
        self.bluetooth_peers: Dict[str, dict] = {}
        self.lan_peers: Dict[str, dict] = {}
        self.peers_lock = threading.Lock()
        self.current_mode = DiscoveryMode.HYBRID
    
    def add_lan_peer(self, ip: str, username: str):
        with self.peers_lock:
            self.lan_peers[ip] = {
                'ip': ip,
                'username': username,
                'discovery_type': 'wifi_lan',
                'last_seen': time.time()
            }
    
    def add_wifi_direct_peer(self, mac_address: str, device_name: str, go_ip: Optional[str] = None):
        peer_id = f"wfd_{mac_address}"
        with self.peers_lock:
            self.wifi_direct_peers[peer_id] = {
                'id': peer_id,
                'mac_address': mac_address,
                'device_name': device_name,
                'go_ip': go_ip,
                'discovery_type': 'wifi_direct',
                'last_seen': time.time()
            }
    
    def add_bluetooth_peer(self, bt_address: str, device_name: str, rssi: Optional[int] = None):
        peer_id = f"bt_{bt_address}"
        with self.peers_lock:
            self.bluetooth_peers[peer_id] = {
                'id': peer_id,
                'bluetooth_address': bt_address,
                'device_name': device_name,
                'discovery_type': 'bluetooth',
                'last_seen': time.time(),
                'rssi': rssi
            }
    
    def get_all_peers(self) -> Dict[str, dict]:
        with self.peers_lock:
            all_peers = {}
            all_peers.update(self.lan_peers)
            all_peers.update(self.wifi_direct_peers)
            all_peers.update(self.bluetooth_peers)
            return all_peers
    
    def get_lan_peers(self) -> Dict[str, dict]:
        with self.peers_lock:
            return dict(self.lan_peers)
    
    def get_wifi_direct_peers(self) -> Dict[str, dict]:
        with self.peers_lock:
            return dict(self.wifi_direct_peers)
    
    def get_bluetooth_peers(self) -> Dict[str, dict]:
        with self.peers_lock:
            return dict(self.bluetooth_peers)
    
    def remove_peer(self, peer_id: str):
        with self.peers_lock:
            self.lan_peers.pop(peer_id, None)
            self.wifi_direct_peers.pop(peer_id, None)
            self.bluetooth_peers.pop(peer_id, None)
    
    def prune_stale_peers(self, timeout_seconds: int = 30):
        current_time = time.time()
        stale_peers = []
        
        with self.peers_lock:
            for peers_dict in [self.lan_peers, self.wifi_direct_peers, self.bluetooth_peers]:
                for peer_id, peer in list(peers_dict.items()):
                    last_seen = peer.get('last_seen', current_time)
                    if current_time - last_seen > timeout_seconds:
                        stale_peers.append((peer_id, peers_dict))
        
        for peer_id, peers_dict in stale_peers:
            with self.peers_lock:
                peers_dict.pop(peer_id, None)
        
        return len(stale_peers)


class OffGridPeerDiscovery:
    
    def __init__(self, wifi_direct=None, bluetooth=None):
        self.wifi_direct = wifi_direct or get_android_wifi_direct()
        self.bluetooth = bluetooth or get_android_bluetooth()
        self.peer_tracker = P2PPeerTracker()
        self.running = False
        self.is_android = is_android()
    
    def start(self):
        self.running = True
        
        if self.is_android:
            print("[OffGridDiscovery] Starting on Android with real APIs")
        else:
            print("[OffGridDiscovery] Starting on desktop (mocking APIs)")
        
        self._start_wifi_direct_discovery()
        self._start_bluetooth_discovery()
    
    def _start_wifi_direct_discovery(self):
        try:
            self.wifi_direct.enable()
            print("[WiFiDirectDiscovery] Enabled")
            
            def _wifi_worker():
                while self.running:
                    try:
                        peers = self.wifi_direct.discover_peers()
                        for peer in peers:
                            mac = peer.get('mac_address', '')
                            name = peer.get('device_name', 'Unknown')
                            go_ip = peer.get('go_ip')
                            self.peer_tracker.add_wifi_direct_peer(mac, name, go_ip)
                        
                        if peers:
                            print(f"[WiFiDirectDiscovery] Found {len(peers)} peers")
                        
                        time.sleep(5)
                    except Exception as e:
                        print(f"[WiFiDirectDiscovery] Error: {e}")
                        time.sleep(5)
            
            threading.Thread(target=_wifi_worker, daemon=True).start()
        except Exception as e:
            print(f"[WiFiDirectDiscovery] Init error: {e}")
    
    def _start_bluetooth_discovery(self):
        try:
            self.bluetooth.enable()
            print("[BluetoothDiscovery] Enabled")
            
            # Start BLE Advertising and Scanning
            service_uuid = "447d5f51-7a8b-4d6f-a9c2-1234567890ab"
            try:
                self.bluetooth.start_ble_advertising(service_uuid, "GhostNode")
                print("[BluetoothDiscovery] BLE advertising started")
            except Exception as e:
                print(f"[BluetoothDiscovery] BLE advertising failed: {e}")
                
            try:
                def on_ble_device_found(device, rssi, name):
                    # device can be a real android BluetoothDevice or dummy device, getAddress() returns address
                    addr = device.getAddress()
                    self.peer_tracker.add_bluetooth_peer(addr, name, rssi)
                    
                self.bluetooth.start_ble_scanning(service_uuid, on_ble_device_found)
                print("[BluetoothDiscovery] BLE scanning started")
            except Exception as e:
                print(f"[BluetoothDiscovery] BLE scanning failed: {e}")
            
            def _bt_worker():
                while self.running:
                    try:
                        devices = self.bluetooth.scan_devices()
                        for device in devices:
                            bt_addr = device.get('address', '')
                            name = device.get('name', 'Unknown')
                            rssi = device.get('rssi')
                            self.peer_tracker.add_bluetooth_peer(bt_addr, name, rssi)
                        
                        if devices:
                            print(f"[BluetoothDiscovery] Found {len(devices)} devices")
                        
                        time.sleep(10)
                    except Exception as e:
                        print(f"[BluetoothDiscovery] Error: {e}")
                        time.sleep(10)
            
            threading.Thread(target=_bt_worker, daemon=True).start()
        except Exception as e:
            print(f"[BluetoothDiscovery] Init error: {e}")
    
    def stop(self):
        self.running = False
        try:
            self.bluetooth.stop_ble_advertising()
        except:
            pass
        try:
            self.bluetooth.stop_ble_scanning()
        except:
            pass
        print("[OffGridDiscovery] Stopped")
    
    def get_all_peers(self) -> Dict[str, dict]:
        return self.peer_tracker.get_all_peers()
    
    def get_wifi_direct_peers(self) -> Dict[str, dict]:
        return self.peer_tracker.get_wifi_direct_peers()
    
    def get_bluetooth_peers(self) -> Dict[str, dict]:
        return self.peer_tracker.get_bluetooth_peers()
    
    def get_lan_peers(self) -> Dict[str, dict]:
        return self.peer_tracker.get_lan_peers()
    
    def add_lan_peer(self, ip: str, username: str):
        self.peer_tracker.add_lan_peer(ip, username)
    
    def get_peer_summary(self) -> Dict[str, int]:
        return {
            'lan_peers': len(self.peer_tracker.get_lan_peers()),
            'wifi_direct_peers': len(self.peer_tracker.get_wifi_direct_peers()),
            'bluetooth_peers': len(self.peer_tracker.get_bluetooth_peers()),
            'total_peers': len(self.peer_tracker.get_all_peers())
        }


if __name__ == '__main__':
    print("[OffGridPeerDiscovery] Testing...\n")
    
    discovery = OffGridPeerDiscovery()
    discovery.start()
    
    print("\n[Test] Simulating peer discovery...")
    discovery.add_lan_peer("192.168.1.10", "Alice")
    discovery.add_lan_peer("192.168.1.11", "Bob")
    
    print("[Test] Manually adding test peers...")
    discovery.peer_tracker.add_wifi_direct_peer("aa:bb:cc:dd:ee:01", "WiFiDirect_Peer1", "192.168.49.1")
    discovery.peer_tracker.add_bluetooth_peer("bb:cc:dd:ee:ff:01", "BT_Device1", rssi=-50)
    
    summary = discovery.get_peer_summary()
    print(f"\n[Summary] {summary}")
    
    print(f"\n[All Peers] {discovery.get_all_peers()}")
    
    time.sleep(2)
    discovery.stop()
