"""
Ghost Net - Network Utilities
Handles multi-interface detection and network type identification.
Works across Wi-Fi, hotspot, cellular, Ethernet, and other connection types.
"""

import socket
import platform
from typing import Dict, List, Optional

# Try to import netifaces for better multi-interface support
try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False
    print("[NetworkUtils] netifaces not available - using fallback detection")


class NetworkDetector:
    """Detect and manage network interfaces across all connection types."""
    
    @staticmethod
    def get_all_interfaces() -> Dict[str, dict]:
        """
        Get all active network interfaces with details.
        
        Returns:
            {
                'interface_name': {
                    'ip': '192.168.1.5',
                    'netmask': '255.255.255.0',
                    'type': 'wifi|ethernet|cellular|hotspot|unknown',
                    'is_active': True
                }
            }
        """
        if NETIFACES_AVAILABLE:
            return NetworkDetector._get_interfaces_netifaces()
        else:
            return NetworkDetector._get_interfaces_fallback()
    
    @staticmethod
    def _get_interfaces_netifaces() -> Dict[str, dict]:
        """Get interfaces using netifaces module."""
        interfaces = {}
        
        try:
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                
                # Get IPv4 address
                if netifaces.AF_INET in addrs:
                    ip_info = addrs[netifaces.AF_INET][0]
                    ip = ip_info.get('addr')
                    
                    # Skip localhost and link-local
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
        """Fallback detection using socket operations."""
        interfaces = {}
        
        try:
            # Try to detect via socket connection
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2.0)
            
            # Try multiple DNS servers to find working interface
            dns_servers = [
                ('1.1.1.1', 80),      # Cloudflare
                ('8.8.8.8', 80),      # Google
                ('208.67.222.222', 80) # OpenDNS
            ]
            
            for dns_ip, port in dns_servers:
                try:
                    s.connect((dns_ip, port))
                    ip = s.getsockname()[0]
                    s.close()
                    
                    # Detect type based on IP range
                    iface_type = NetworkDetector._detect_interface_type_by_ip(ip)
                    
                    interfaces['default'] = {
                        'ip': ip,
                        'netmask': '255.255.255.0',
                        'type': iface_type,
                        'is_active': True
                    }
                    return interfaces
                except (OSError, socket.error):
                    continue
            
            s.close()
        
        except Exception as e:
            print(f"[NetworkDetector] Fallback detection error: {e}")
        
        return interfaces
    
    @staticmethod
    def _detect_interface_type(iface: str, ip: str) -> str:
        """Detect interface type based on name and IP."""
        iface_lower = iface.lower()
        
        # Hotspot/Tethering patterns
        if any(x in iface_lower for x in ['ap', 'hotspot', 'tether', 'rndis', 'ncm']):
            return 'hotspot'
        
        # Cellular/Mobile patterns
        if any(x in iface_lower for x in ['rmnet', 'ccmni', 'cellular', 'mobile', 'wwan']):
            return 'cellular'
        
        # Ethernet patterns
        if any(x in iface_lower for x in ['eth', 'en0', 'en1', 'lan']):
            return 'ethernet'
        
        # Wi-Fi patterns
        if any(x in iface_lower for x in ['wlan', 'wifi', 'wl', 'ath']):
            return 'wifi'
        
        # Check IP range patterns for better classification
        return NetworkDetector._detect_interface_type_by_ip(ip)
    
    @staticmethod
    def _detect_interface_type_by_ip(ip: str) -> str:
        """Detect interface type based on IP address patterns."""
        # Common hotspot AP IP ranges
        if ip.startswith('192.168.43.') or ip.startswith('192.168.137.'):
            return 'hotspot'
        
        # Common cellular tethering ranges
        if ip.startswith('192.168.1.') and 'cellular' in ip.lower():
            return 'cellular'
        
        # Private network (could be any type, default to unknown)
        if ip.startswith('10.') or ip.startswith('172.') or ip.startswith('192.168.'):
            return 'private'
        
        return 'unknown'
    
    @staticmethod
    def get_best_interface() -> Optional[str]:
        """
        Get the best interface IP for P2P communication.
        Priority: wifi > ethernet > hotspot > cellular > any
        """
        interfaces = NetworkDetector.get_all_interfaces()
        
        if not interfaces:
            return None
        
        # Priority order for connection types
        priority = ['wifi', 'ethernet', 'private', 'hotspot', 'cellular', 'unknown']
        
        # Find best interface by priority
        for conn_type in priority:
            for iface, info in interfaces.items():
                if info['type'] == conn_type and info.get('is_active', False):
                    return info['ip']
        
        # Return any available active interface
        for iface, info in interfaces.items():
            if info.get('is_active', False):
                return info['ip']
        
        return None
    
    @staticmethod
    def get_network_type(ip: Optional[str] = None) -> str:
        """Get the network type for a specific IP or the best interface."""
        interfaces = NetworkDetector.get_all_interfaces()
        
        if not interfaces:
            return 'unknown'
        
        # If IP specified, find its type
        if ip:
            for iface, info in interfaces.items():
                if info['ip'] == ip:
                    return info['type']
        
        # Otherwise get best interface type
        best_ip = NetworkDetector.get_best_interface()
        for iface, info in interfaces.items():
            if info['ip'] == best_ip:
                return info['type']
        
        return 'unknown'
    
    @staticmethod
    def get_interface_info(ip: str) -> Optional[dict]:
        """Get detailed info about a specific IP interface."""
        interfaces = NetworkDetector.get_all_interfaces()
        
        for iface, info in interfaces.items():
            if info['ip'] == ip:
                return info
        
        return None
    
    @staticmethod
    def is_connected() -> bool:
        """Check if device is connected to any network."""
        interfaces = NetworkDetector.get_all_interfaces()
        return len(interfaces) > 0


class NetworkMonitor:
    """Monitor network changes and provide callbacks."""
    
    def __init__(self, on_network_changed=None):
        """
        Initialize network monitor.
        
        Args:
            on_network_changed: Callback(old_ip, new_ip, network_type)
        """
        self.current_ip = NetworkDetector.get_best_interface()
        self.current_type = NetworkDetector.get_network_type(self.current_ip)
        self.on_network_changed = on_network_changed
    
    def check_network_change(self) -> bool:
        """
        Check if network has changed.
        
        Returns:
            True if network changed, False otherwise
        """
        new_ip = NetworkDetector.get_best_interface()
        new_type = NetworkDetector.get_network_type(new_ip)
        
        # Check if IP or type changed
        if new_ip != self.current_ip or new_type != self.current_type:
            old_ip = self.current_ip
            old_type = self.current_type
            
            self.current_ip = new_ip
            self.current_type = new_type
            
            # Notify callback
            if self.on_network_changed:
                try:
                    self.on_network_changed(old_ip, new_ip, new_type)
                except Exception as e:
                    print(f"[NetworkMonitor] Callback error: {e}")
            
            return True
        
        return False
    
    def get_status(self) -> dict:
        """Get current network status."""
        return {
            'ip': self.current_ip,
            'type': self.current_type,
            'is_connected': self.current_ip is not None,
            'interfaces': NetworkDetector.get_all_interfaces()
        }


# Test code
if __name__ == '__main__':
    print("[NetworkUtils] Testing network detection...\n")
    
    # Test interface detection
    print("=== All Interfaces ===")
    interfaces = NetworkDetector.get_all_interfaces()
    for iface, info in interfaces.items():
        print(f"{iface}: {info['ip']} ({info['type']})")
    
    # Test best interface
    print("\n=== Best Interface ===")
    best_ip = NetworkDetector.get_best_interface()
    best_type = NetworkDetector.get_network_type(best_ip)
    print(f"IP: {best_ip}")
    print(f"Type: {best_type}")
    
    # Test network monitor
    print("\n=== Network Monitor ===")
    monitor = NetworkMonitor()
    status = monitor.get_status()
    print(f"Status: {status}")
