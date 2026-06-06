from kivy.utils import platform as kivy_platform
from kivy.clock import Clock
import asyncio
import time
import threading

_platform = kivy_platform  # kivy.utils.platform is a string, not a callable
_is_android = (_platform == 'android')

class MockWiFiDirect:
    def __init__(self):
        self.enabled = False
        self.peers = {}
        self.connected_peers = {}
    
    def enable(self):
        if not _is_android:
            print("[MockWiFiDirect] Wi-Fi Direct mock: enabled")
        self.enabled = True
    
    def discover_peers(self):
        if not _is_android:
            print("[MockWiFiDirect] Discovering peers (mock)")
        return list(self.peers.values())
    
    def connect(self, peer_address):
        if not _is_android:
            print(f"[MockWiFiDirect] Connecting to {peer_address} (mock)")
        
        if _is_android:
            return True
        
        self.connected_peers[peer_address] = {
            'connected_at': time.time(),
            'go_ip': '192.168.49.1'
        }
        return True
    
    def get_go_ip_for_peer(self, peer_address):
        if not _is_android:
            print(f"[MockWiFiDirect] Resolving GO IP for {peer_address} (mock)")
        
        if peer_address in self.connected_peers:
            return self.connected_peers[peer_address].get('go_ip')
        
        return '192.168.49.1'
    
    def disconnect(self):
        if not _is_android:
            print("[MockWiFiDirect] Disconnected (mock)")
        self.connected_peers.clear()
        return True

class MockBluetooth:
    def __init__(self):
        self.enabled = False
        self.paired_devices = {}
        self.rfcomm_sockets = {}
        self.server_thread = None
        self.server_running = False
        self.ble_advertising = False
        self.ble_scanning = False
        self.ble_scan_thread = None
    
    def enable(self):
        if not _is_android:
            print("[MockBluetooth] Bluetooth mock: enabled")
        self.enabled = True
    
    def scan_devices(self):
        if not _is_android:
            print("[MockBluetooth] Scanning for devices (mock)")
        return list(self.paired_devices.values())
    
    def connect(self, device_address):
        if not _is_android:
            print(f"[MockBluetooth] Connecting to {device_address} (mock)")
        
        if _is_android:
            return True
        
        self.rfcomm_sockets[device_address] = MockRFCOMMSocket(device_address)
        return True
    
    def create_rfcomm_socket(self, device_address):
        if not _is_android:
            print(f"[MockBluetooth] Creating RFCOMM socket for {device_address} (mock)")
        
        if device_address in self.rfcomm_sockets:
            return self.rfcomm_sockets[device_address]
        
        socket = MockRFCOMMSocket(device_address)
        self.rfcomm_sockets[device_address] = socket
        return socket
    
    def listen_rfcomm(self):
        if not _is_android:
            print("[MockBluetooth] Listening for RFCOMM connections (mock)")
        
        return None
        
    def start_ble_advertising(self, service_uuid: str, device_name: str) -> bool:
        if not _is_android:
            print(f"[MockBluetooth] BLE advertising started for UUID: {service_uuid}")
        self.ble_advertising = True
        return True

    def stop_ble_advertising(self) -> bool:
        if not _is_android:
            print("[MockBluetooth] BLE advertising stopped")
        self.ble_advertising = False
        return True

    def start_ble_scanning(self, service_uuid: str, on_device_found) -> bool:
        if not _is_android:
            print(f"[MockBluetooth] BLE scan started for UUID: {service_uuid}")
        self.ble_scanning = True
        
        def _ble_scan_mock_worker():
            mock_nodes = [
                ("aa:bb:cc:dd:ee:f1", "BLE_MeshNode_A", -62),
                ("aa:bb:cc:dd:ee:f2", "BLE_MeshNode_B", -75)
            ]
            while self.ble_scanning:
                time.sleep(5)
                for addr, name, rssi in mock_nodes:
                    if not self.ble_scanning:
                        break
                    try:
                        # Call on_device_found
                        # To mock device object, we pass a dummy object that implements getAddress()
                        class DummyDevice:
                            def __init__(self, address):
                                self.address = address
                            def getAddress(self):
                                return self.address
                        on_device_found(DummyDevice(addr), rssi, name)
                    except Exception as e:
                        print(f"[MockBluetooth] BLE scan callback error: {e}")
                        
        self.ble_scan_thread = threading.Thread(target=_ble_scan_mock_worker, daemon=True)
        self.ble_scan_thread.start()
        return True

    def stop_ble_scanning(self) -> bool:
        if not _is_android:
            print("[MockBluetooth] BLE scan stopped")
        self.ble_scanning = False
        return True
    
    def disconnect(self):
        if not _is_android:
            print("[MockBluetooth] Disconnected (mock)")
        self.rfcomm_sockets.clear()
        self.stop_ble_scanning()
        self.stop_ble_advertising()
        return True

class MockRFCOMMSocket:
    def __init__(self, device_address):
        self.device_address = device_address
        self.buffer = b''
        self.closed = False
        self.recv_buffer = b''
    
    def send(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.buffer += data
        return len(data)
    
    def recv(self, bufsize):
        if self.closed:
            return b''
        
        if len(self.recv_buffer) == 0:
            self.recv_buffer = self.buffer
            self.buffer = b''
        
        data = self.recv_buffer[:bufsize]
        self.recv_buffer = self.recv_buffer[bufsize:]
        return data
    
    def sendall(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.buffer += data
    
    def settimeout(self, timeout):
        pass
    
    def getpeername(self):
        return (self.device_address, 0)
    
    def close(self):
        self.closed = True

class MockAndroidPermissions:
    @staticmethod
    def request_permissions(permissions):
        if not _is_android:
            print(f"[MockAndroidPermissions] Requesting {len(permissions)} permissions (mock)")
        return True
    
    @staticmethod
    def check_permission(permission):
        if not _is_android:
            print(f"[MockAndroidPermissions] Checking {permission} (mock)")
        return True

class MockFilePicker:
    @staticmethod
    def pick_file(filters=None):
        if not _is_android:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                filetypes = [("All Files", "*.*")]
                if filters:
                    filetypes = filters
                file_path = filedialog.askopenfilename(filetypes=filetypes)
                root.destroy()
                return file_path if file_path else None
            except Exception as e:
                print(f"[MockFilePicker] Desktop picker error: {e}")
                return None
        return None
    
    @staticmethod
    def pick_multiple_files(filters=None):
        if not _is_android:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                filetypes = [("All Files", "*.*")]
                if filters:
                    filetypes = filters
                files = filedialog.askopenfilenames(filetypes=filetypes)
                root.destroy()
                return list(files) if files else []
            except Exception as e:
                print(f"[MockFilePicker] Desktop multi-picker error: {e}")
                return []
        return []

def get_android_wifi_direct():
    if _is_android:
        try:
            from android_wifi_direct import AndroidWiFiDirect
            return AndroidWiFiDirect()
        except ImportError:
            print("[WARNING] Android Wi-Fi Direct module not available")
            return MockWiFiDirect()
    return MockWiFiDirect()

def get_android_bluetooth():
    if _is_android:
        try:
            from android_bluetooth import AndroidBluetooth
            return AndroidBluetooth()
        except ImportError:
            print("[WARNING] Android Bluetooth module not available")
            return MockBluetooth()
    return MockBluetooth()

def conditional_import(module_name, class_name, fallback_class=None):
    if _is_android:
        try:
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            print(f"[WARNING] Failed to import {module_name}.{class_name}: {e}")
            if fallback_class:
                return fallback_class
            return None
    else:
        if fallback_class:
            return fallback_class
        return None

def is_android():
    return _is_android

def get_file_picker():
     if _is_android:
         try:
             from plyer import filechooser
             return filechooser
         except ImportError:
             print("[WARNING] Plyer not available for file picker")
             return MockFilePicker()
     return MockFilePicker()

class MockNotificationManager:
     def __init__(self):
         self.channel_id = "ghost_net_service"
         self.notification_id = 42
     
     def show_foreground_notification(self):
         if not _is_android:
             print("[MockNotificationManager] Foreground notification: Ghost Net is listening for peers.")
         return True
     
     def show_message_notification(self, sender_name: str, message_preview: str):
         if not _is_android:
             print(f"[MockNotificationManager] Message notification from {sender_name}: {message_preview[:100]}")
         return True

def get_notification_manager():
     if _is_android:
         try:
             from service import ServiceNotificationManager
             return ServiceNotificationManager()
         except ImportError:
             print("[WARNING] Service notification manager not available")
             return MockNotificationManager()
     return MockNotificationManager()
