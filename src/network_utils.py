import socket
import platform
import threading
import time
from typing import Dict, List, Optional, Callable
from enum import Enum

try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False
    print("[NetworkUtils] netifaces not available - using fallback detection")


class DiscoveryMode(Enum):
    WIFI_LAN = "wifi_lan"
    WIFI_DIRECT = "wifi_direct"
    BLUETOOTH = "bluetooth"
    HYBRID = "hybrid"


class NetworkDetector:
    
    @staticmethod
    def get_all_interfaces() -> Dict[str, dict]:
        if NETIFACES_AVAILABLE:
            return NetworkDetector._get_interfaces_netifaces()
        else:
            return NetworkDetector._get_interfaces_fallback()
    
    @staticmethod
    def _get_interfaces_netifaces() -> Dict[str, dict]:
        interfaces = {}
        
        try:
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                
                if netifaces.AF_INET in addrs:
                    ip_info = addrs[netifaces.AF_INET][0]
                    ip = ip_info.get('addr')
                    
                    if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                        interfaces[iface] = {
                            'ip': ip,
                            'netmask': ip_info.get('netmask', '255.255.255.0'),
                            'type': NetworkDetector._detect_interface_type(iface, ip),
                            'is_active': True
                        }
        
        except Exception as e:
            print(f"[NetworkDetector] netifaces error: {e}")
        
        return interfaces
    
    @staticmethod
    def _get_interfaces_fallback() -> Dict[str, dict]:
        interfaces = {}
        
        try:
            dns_servers = [
                ('1.1.1.1', 80),
                ('8.8.8.8', 80),
                ('208.67.222.222', 80)
            ]
            
            for dns_ip, port in dns_servers:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.settimeout(2.0)
                    s.connect((dns_ip, port))
                    ip = s.getsockname()[0]
                    s.close()
                    
                    iface_type = NetworkDetector._detect_interface_type_by_ip(ip)
                    
                    interfaces['default'] = {
                        'ip': ip,
                        'netmask': '255.255.255.0',
                        'type': iface_type,
                        'is_active': True
                    }
                    return interfaces
                except (OSError, socket.error):
                    try:
                        s.close()
                    except Exception:
                        pass
                    continue
        
        except Exception as e:
            print(f"[NetworkDetector] Fallback detection error: {e}")
        
        return interfaces
    
    @staticmethod
    def _detect_interface_type(iface: str, ip: str) -> str:
        iface_lower = iface.lower()
        
        if any(x in iface_lower for x in ['ap', 'hotspot', 'tether', 'rndis', 'ncm']):
            return 'hotspot'
        
        if any(x in iface_lower for x in ['rmnet', 'ccmni', 'cellular', 'mobile', 'wwan']):
            return 'cellular'
        
        if any(x in iface_lower for x in ['eth', 'en0', 'en1', 'lan']):
            return 'ethernet'
        
        if any(x in iface_lower for x in ['wlan', 'wifi', 'wl', 'ath']):
            return 'wifi'
        
        return NetworkDetector._detect_interface_type_by_ip(ip)
    
    @staticmethod
    def _detect_interface_type_by_ip(ip: str) -> str:
        if ip.startswith('192.168.43.') or ip.startswith('192.168.137.'):
            return 'hotspot'
        
        if ip.startswith('192.168.1.') and 'cellular' in ip.lower():
            return 'cellular'
        
        if ip.startswith('10.') or ip.startswith('172.') or ip.startswith('192.168.'):
            return 'private'
        
        return 'unknown'
    
    @staticmethod
    def get_best_interface() -> Optional[str]:
        interfaces = NetworkDetector.get_all_interfaces()
        
        if not interfaces:
            return None
        
        priority = ['wifi', 'ethernet', 'private', 'hotspot', 'cellular', 'unknown']
        
        for conn_type in priority:
            for iface, info in interfaces.items():
                if info['type'] == conn_type and info.get('is_active', False):
                    return info['ip']
        
        for iface, info in interfaces.items():
            if info.get('is_active', False):
                return info['ip']
        
        return None
    
    @staticmethod
    def get_network_type(ip: Optional[str] = None) -> str:
        interfaces = NetworkDetector.get_all_interfaces()
        
        if not interfaces:
            return 'unknown'
        
        if ip:
            for iface, info in interfaces.items():
                if info['ip'] == ip:
                    return info['type']
        
        best_ip = NetworkDetector.get_best_interface()
        for iface, info in interfaces.items():
            if info['ip'] == best_ip:
                return info['type']
        
        return 'unknown'
    
    @staticmethod
    def get_interface_info(ip: str) -> Optional[dict]:
        interfaces = NetworkDetector.get_all_interfaces()
        
        for iface, info in interfaces.items():
            if info['ip'] == ip:
                return info
        
        return None
    
    @staticmethod
    def is_connected() -> bool:
        interfaces = NetworkDetector.get_all_interfaces()
        return len(interfaces) > 0


class P2PPeerDiscovery:
    
    def __init__(self, on_peers_discovered: Optional[Callable] = None):
        self.on_peers_discovered = on_peers_discovered
        self.discovered_peers: Dict[str, dict] = {}
        self.peers_lock = threading.Lock()
        self.discovery_mode = DiscoveryMode.WIFI_LAN
        self.running = False
    
    def add_lan_peer(self, ip: str, username: str, mac_address: Optional[str] = None):
        with self.peers_lock:
            self.discovered_peers[ip] = {
                'ip': ip,
                'username': username,
                'mac_address': mac_address,
                'discovery_type': 'wifi_lan',
                'last_seen': time.time(),
                'signal_strength': None
            }
    
    def add_wifi_direct_peer(self, mac_address: str, device_name: str, go_ip: Optional[str] = None):
        peer_id = f"wfd_{mac_address}"
        with self.peers_lock:
            self.discovered_peers[peer_id] = {
                'id': peer_id,
                'mac_address': mac_address,
                'device_name': device_name,
                'go_ip': go_ip,
                'discovery_type': 'wifi_direct',
                'last_seen': time.time(),
                'is_group_owner': False,
                'signal_strength': None
            }
    
    def add_bluetooth_peer(self, bluetooth_address: str, device_name: str, rssi: Optional[int] = None):
        peer_id = f"bt_{bluetooth_address}"
        with self.peers_lock:
            self.discovered_peers[peer_id] = {
                'id': peer_id,
                'bluetooth_address': bluetooth_address,
                'device_name': device_name,
                'discovery_type': 'bluetooth',
                'last_seen': time.time(),
                'rssi': rssi,
                'is_bonded': False
            }
    
    def remove_peer(self, peer_id: str):
        with self.peers_lock:
            if peer_id in self.discovered_peers:
                del self.discovered_peers[peer_id]
    
    def get_all_peers(self) -> Dict[str, dict]:
        with self.peers_lock:
            return dict(self.discovered_peers)
    
    def get_peers_by_type(self, discovery_type: str) -> Dict[str, dict]:
        with self.peers_lock:
            return {
                peer_id: peer for peer_id, peer in self.discovered_peers.items()
                if peer.get('discovery_type') == discovery_type
            }
    
    def prune_stale_peers(self, timeout_seconds: int = 30):
        current_time = time.time()
        stale_peers = []
        
        with self.peers_lock:
            for peer_id, peer in self.discovered_peers.items():
                last_seen = peer.get('last_seen', current_time)
                if current_time - last_seen > timeout_seconds:
                    stale_peers.append(peer_id)
        
        for peer_id in stale_peers:
            self.remove_peer(peer_id)
        
        return len(stale_peers)
    
    def on_peers_changed(self):
        if self.on_peers_discovered:
            try:
                self.on_peers_discovered(self.get_all_peers())
            except Exception as e:
                print(f"[P2PPeerDiscovery] Callback error: {e}")


class NetworkMonitor:
    
    def __init__(self, on_network_changed=None):
        self.current_ip = NetworkDetector.get_best_interface()
        self.current_type = NetworkDetector.get_network_type(self.current_ip)
        self.on_network_changed = on_network_changed
        self.peer_discovery = P2PPeerDiscovery()
    
    def check_network_change(self) -> bool:
        new_ip = NetworkDetector.get_best_interface()
        new_type = NetworkDetector.get_network_type(new_ip)
        
        if new_ip != self.current_ip or new_type != self.current_type:
            old_ip = self.current_ip
            old_type = self.current_type
            
            self.current_ip = new_ip
            self.current_type = new_type
            
            if self.on_network_changed:
                try:
                    self.on_network_changed(old_ip, new_ip, new_type)
                except Exception as e:
                    print(f"[NetworkMonitor] Callback error: {e}")
            
            return True
        
        return False
    
    def get_status(self) -> dict:
        return {
            'ip': self.current_ip,
            'type': self.current_type,
            'is_connected': self.current_ip is not None,
            'interfaces': NetworkDetector.get_all_interfaces(),
            'peers': self.peer_discovery.get_all_peers(),
            'discovery_mode': self.peer_discovery.discovery_mode.value
        }
    
    def get_peer_discovery(self) -> P2PPeerDiscovery:
        return self.peer_discovery


if __name__ == '__main__':
    print("[NetworkUtils] Testing network detection...\n")
    
    print("=== All Interfaces ===")
    interfaces = NetworkDetector.get_all_interfaces()
    for iface, info in interfaces.items():
        print(f"{iface}: {info['ip']} ({info['type']})")
    
    print("\n=== Best Interface ===")
    best_ip = NetworkDetector.get_best_interface()
    best_type = NetworkDetector.get_network_type(best_ip)
    print(f"IP: {best_ip}")
    print(f"Type: {best_type}")
    
    print("\n=== Network Monitor ===")
    monitor = NetworkMonitor()
    status = monitor.get_status()
    print(f"Status: {status}")
