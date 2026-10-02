import socket
import threading
import time
import os
import sys
import json
from datetime import datetime
from typing import Optional, Callable, Dict

# Add src/ to path so app modules (database, security, etc.) can be imported
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from kivy.utils import platform as kivy_platform

_is_android = (kivy_platform == 'android')  # kivy_platform is a string, not callable

if _is_android:
    from jnius import autoclass, cast
    from android.broadcast import BroadcastReceiver
    
    PythonService = autoclass('org.kivy.android.PythonService')
    service = PythonService.mService
    
    Context = autoclass('android.content.Context')
    PendingIntent = autoclass('android.app.PendingIntent')
    NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
    NotificationManager = autoclass('android.app.NotificationManager')
    
    Build = autoclass('android.os.Build')


class ServiceNotificationManager:
    
    def __init__(self):
        self.channel_id = "ghost_net_service"
        self.notification_id = 42
        self._setup_notification_channel()
    
    def _setup_notification_channel(self):
        if _is_android and Build.VERSION.SDK_INT >= 26:
            try:
                NotificationChannel = autoclass('android.app.NotificationChannel')
                Context = autoclass('android.content.Context')
                
                channel = NotificationChannel(
                    self.channel_id,
                    "Ghost Net Service",
                    NotificationManager.IMPORTANCE_DEFAULT
                )
                channel.setDescription("Ghost Net background service for P2P messaging")
                
                notification_service = service.getSystemService(Context.NOTIFICATION_SERVICE)
                notification_service.createNotificationChannel(channel)
                
                print("[ServiceNotification] Notification channel created for API 33+")
            except Exception as e:
                print(f"[ServiceNotification] Channel setup error: {e}")
    
    def show_foreground_notification(self):
        if not _is_android:
            print("[ServiceNotification] (Desktop mock) Foreground notification active")
            return True
        try:
            builder = NotificationCompat.Builder(service, self.channel_id)
            builder.setContentTitle("Ghost Net")
            builder.setContentText("Ghost Net is listening for peers.")
            builder.setSmallIcon(self._get_app_icon())
            builder.setPriority(NotificationCompat.PRIORITY_LOW)
            builder.setOngoing(True)
            
            notification = builder.build()
            
            # Formally transition service to foreground to comply with Android 8.0+ (API 26+)
            service.startForeground(self.notification_id, notification)
            
            print("[ServiceNotification] Foreground notification active (service.startForeground called)")
            return True
        except Exception as e:
            print(f"[ServiceNotification] Error showing notification: {e}")
            return False

    def stop_foreground_notification(self):
        if not _is_android:
            return True
        try:
            service.stopForeground(True)
            print("[ServiceNotification] Foreground notification removed")
            return True
        except Exception as e:
            print(f"[ServiceNotification] Error stopping foreground notification: {e}")
            return False
    
    def show_message_notification(self, sender_name: str, message_preview: str):
        if not _is_android:
            print(f"[ServiceNotification] (Desktop mock) Message notification from {sender_name}: {message_preview[:50]}")
            return True
        try:
            builder = NotificationCompat.Builder(service, self.channel_id)
            builder.setContentTitle(f"Message from {sender_name}")
            builder.setContentText(message_preview[:100])
            builder.setSmallIcon(self._get_app_icon())
            builder.setPriority(NotificationCompat.PRIORITY_HIGH)
            builder.setAutoCancel(True)
            
            notification = builder.build()
            
            notification_service = service.getSystemService(Context.NOTIFICATION_SERVICE)
            notification_id = hash(sender_name) % 10000
            notification_service.notify(notification_id, notification)
            
            print(f"[ServiceNotification] Message notification from {sender_name}")
            return True
        except Exception as e:
            print(f"[ServiceNotification] Error showing message notification: {e}")
            return False
    
    def _get_app_icon(self):
        if not _is_android:
            return 17301651
        try:
            app_context = service.getApplicationContext()
            app_info = app_context.getApplicationInfo()
            return app_info.icon
        except:
            return 17301651


class AndroidPowerManager:
    """Manages Partial WakeLock and Wi-Fi Lock to keep mesh listening active on Android."""
    def __init__(self):
        self.wake_lock = None
        self.wifi_lock = None
        self._init_locks()

    def _init_locks(self):
        if not _is_android:
            return
        try:
            PowerManager = autoclass('android.os.PowerManager')
            power_service = service.getSystemService(Context.POWER_SERVICE)
            self.wake_lock = power_service.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "GhostNet:MeshWakeLock")
            self.wake_lock.setReferenceCounted(False)

            WifiManager = autoclass('android.net.wifi.WifiManager')
            wifi_service = service.getSystemService(Context.WIFI_SERVICE)
            # Mode 3: WIFI_MODE_FULL_HIGH_PERF
            self.wifi_lock = wifi_service.createWifiLock(3, "GhostNet:MeshWifiLock")
            self.wifi_lock.setReferenceCounted(False)
            print("[AndroidPowerManager] WakeLock and Wi-Fi Lock initialized")
        except Exception as e:
            print(f"[AndroidPowerManager] Lock initialization failed: {e}")

    def acquire(self):
        if not _is_android:
            return
        try:
            if self.wake_lock and not self.wake_lock.isHeld():
                self.wake_lock.acquire()
                print("[AndroidPowerManager] Partial WakeLock acquired")
            if self.wifi_lock and not self.wifi_lock.isHeld():
                self.wifi_lock.acquire()
                print("[AndroidPowerManager] Wi-Fi Lock acquired")
        except Exception as e:
            print(f"[AndroidPowerManager] Failed to acquire locks: {e}")

    def release(self):
        if not _is_android:
            return
        try:
            if self.wake_lock and self.wake_lock.isHeld():
                self.wake_lock.release()
                print("[AndroidPowerManager] Partial WakeLock released")
            if self.wifi_lock and self.wifi_lock.isHeld():
                self.wifi_lock.release()
                print("[AndroidPowerManager] Wi-Fi Lock released")
        except Exception as e:
            print(f"[AndroidPowerManager] Failed to release locks: {e}")


class LightweightGhostEngine:
    
    UDP_PORT = 37020
    TCP_PORT = 37021
    BEACON_INTERVAL = 2
    PEER_TIMEOUT = 10
    BUFFER_SIZE = 4096
    CHUNK_SIZE = 8192
    HEADER_DELIMITER = b"<HEADER_END>"
    CHUNK_DELIMITER = b"<CHUNK_END>"
    
    def __init__(self, username: str = "GhostUser", 
                 on_message_received: Optional[Callable] = None,
                 persistence_db: Optional[object] = None,
                 notification_manager: Optional[object] = None):
        self.username = username
        self.running = False
        self.on_message_received = on_message_received
        self.persistence_db = persistence_db
        self.notification_manager = notification_manager
        self.power_manager = AndroidPowerManager()
        
        self.peers = {}
        self.peer_lock = threading.Lock()
        
        self.udp_socket = None
        self.tcp_socket = None
        self.tcp_threads = {}
        
        self._setup_encryption()
    
    def _setup_encryption(self):
        try:
            from security import CryptoManager
            self.crypto = CryptoManager()
            print("[LightweightEngine] Encryption initialized")
        except Exception as e:
            print(f"[LightweightEngine] Crypto setup failed: {e}")
            self.crypto = None
    
    def start(self):
        if self.running:
            return
        
        self.running = True
        self.power_manager.acquire()
        print(f"[LightweightEngine] Starting background service as '{self.username}'")
        
        threading.Thread(target=self._run_udp_listener, daemon=True).start()
        threading.Thread(target=self._run_tcp_listener, daemon=True).start()
        threading.Thread(target=self._broadcast_beacon, daemon=True).start()
        threading.Thread(target=self._scrubbing_worker, daemon=True).start()
    
    def stop(self):
        self.running = False
        self.power_manager.release()
        
        if self.notification_manager and hasattr(self.notification_manager, 'stop_foreground_notification'):
            try:
                self.notification_manager.stop_foreground_notification()
            except Exception:
                pass
        
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except:
                pass
        
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        
        for thread in self.tcp_threads.values():
            if thread and thread.is_alive():
                thread.join(timeout=1)
        
        print("[LightweightEngine] Background service stopped")
    
    def _run_udp_listener(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if hasattr(socket, 'SO_REUSEPORT'):
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            
            self.udp_socket.bind(('', self.UDP_PORT))
            self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
            self.udp_socket.settimeout(2.0)
            
            print(f"[LightweightEngine] UDP listener started on port {self.UDP_PORT}")
            
            while self.running:
                try:
                    data, addr = self.udp_socket.recvfrom(self.BUFFER_SIZE)
                    if data:
                        self._handle_beacon(data, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[LightweightEngine] UDP error: {e}")
        except Exception as e:
            print(f"[LightweightEngine] UDP listener error: {e}")
        finally:
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except:
                    pass
    
    def _run_tcp_listener(self):
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if hasattr(socket, 'SO_REUSEPORT'):
                self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            
            self.tcp_socket.bind(('', self.TCP_PORT))
            self.tcp_socket.listen(5)
            self.tcp_socket.settimeout(2.0)
            
            print(f"[LightweightEngine] TCP listener started on port {self.TCP_PORT}")
            
            while self.running:
                try:
                    client_socket, client_addr = self.tcp_socket.accept()
                    threading.Thread(
                        target=self._handle_client_connection,
                        args=(client_socket, client_addr),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[LightweightEngine] TCP error: {e}")
        except Exception as e:
            print(f"[LightweightEngine] TCP listener error: {e}")
        finally:
            if self.tcp_socket:
                try:
                    self.tcp_socket.close()
                except:
                    pass
    
    def _handle_beacon(self, data: bytes, addr):
        try:
            beacon_str = data.decode('utf-8', errors='ignore').strip()
            beacon_data = None
            if beacon_str.startswith('{'):
                try:
                    beacon_data = json.loads(beacon_str)
                except Exception:
                    beacon_data = None
            
            if isinstance(beacon_data, dict):
                peer_ip = addr[0]
                username = beacon_data.get('username', 'Unknown')
                
                with self.peer_lock:
                    self.peers[peer_ip] = {
                        'username': username,
                        'last_seen': time.time()
                    }
        except Exception as e:
            pass
    
    def _handle_client_connection(self, client_socket, client_addr):
        peer_ip = client_addr[0]
        
        try:
            client_socket.settimeout(30.0)
            
            received_data = b''
            while len(received_data) < 1024 and self.running:
                chunk = client_socket.recv(self.BUFFER_SIZE)
                if not chunk:
                    break
                received_data += chunk
                
                if self.HEADER_DELIMITER in received_data:
                    break
            
            if self.HEADER_DELIMITER in received_data:
                header_end = received_data.find(self.HEADER_DELIMITER)
                header_bytes = received_data[:header_end]
                payload = received_data[header_end + len(self.HEADER_DELIMITER):]
                
                try:
                    header_str = header_bytes.decode('utf-8', errors='ignore').strip()
                    try:
                        header = json.loads(header_str)
                    except Exception:
                        header = {}
                except:
                    header = {}
                
                message_type = header.get('type', '')
                
                if message_type == 'TEXT':
                    self._handle_text_message(header, payload, peer_ip)
                elif message_type == 'FILE':
                    self._handle_file_message(header, payload, peer_ip, client_socket)
        
        except Exception as e:
            print(f"[LightweightEngine] Client handling error from {peer_ip}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def _handle_text_message(self, header: dict, payload: bytes, peer_ip: str):
        try:
            message_content = payload.decode('utf-8', errors='ignore').rstrip('\x00')
            
            if self.crypto:
                try:
                    message_content = self.crypto.decrypt_message(message_content)
                except:
                    pass
            
            timestamp = time.time()
            
            if self.persistence_db:
                try:
                    peer_name = header.get('sender', 'Unknown')
                    self.persistence_db.save_message(
                        peer_id=peer_ip,
                        sender_type='peer',
                        content_type='text',
                        content=message_content,
                        timestamp=timestamp
                    )
                except Exception as e:
                    print(f"[LightweightEngine] DB save error: {e}")
            
            if self.on_message_received:
                try:
                    self.on_message_received(peer_ip, message_content, timestamp)
                except Exception as e:
                    print(f"[LightweightEngine] Callback error: {e}")
            
            print(f"[LightweightEngine] Text message from {peer_ip}: {message_content[:50]}")
        
        except Exception as e:
            print(f"[LightweightEngine] Text handling error: {e}")
    
    def _handle_file_message(self, header: dict, payload: bytes, peer_ip: str, client_socket):
        try:
            filename = header.get('filename', 'file')
            filesize = header.get('filesize', len(payload))
            
            downloads_dir = os.path.expanduser("~/.ghostnet/downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            filepath = os.path.join(downloads_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(payload)
            
            timestamp = time.time()
            
            if self.persistence_db:
                try:
                    self.persistence_db.save_message(
                        peer_id=peer_ip,
                        sender_type='peer',
                        content_type='file',
                        content=filename,
                        timestamp=timestamp
                    )
                except Exception as e:
                    print(f"[LightweightEngine] File DB save error: {e}")
            
            print(f"[LightweightEngine] File received from {peer_ip}: {filename}")
        
        except Exception as e:
            print(f"[LightweightEngine] File handling error: {e}")
    
    def _broadcast_beacon(self):
        try:
            beacon_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            beacon_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if hasattr(socket, 'SO_REUSEPORT'):
                beacon_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            
            beacon_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            beacon_socket.settimeout(2.0)
            
            while self.running:
                try:
                    beacon_data = {
                        'type': 'BEACON',
                        'username': self.username,
                        'timestamp': time.time()
                    }
                    beacon_bytes = json.dumps(beacon_data).encode('utf-8')
                    
                    beacon_socket.sendto(beacon_bytes, ('<broadcast>', self.UDP_PORT))
                    time.sleep(self.BEACON_INTERVAL)
                except Exception as e:
                    if self.running:
                        print(f"[LightweightEngine] Beacon error: {e}")
        except Exception as e:
            print(f"[LightweightEngine] Beacon setup error: {e}")
        finally:
            try:
                beacon_socket.close()
            except:
                pass
    
    def _scrubbing_worker(self):
        while self.running:
            try:
                if self.persistence_db:
                    deleted = self.persistence_db.scrub_expired_messages()
                time.sleep(10)
            except Exception as e:
                print(f"[LightweightEngine] Scrubbing error: {e}")
                time.sleep(10)


def main():
    username = "GhostUser"
    persistence_db = None
    
    try:
        from database import PersistenceDatabase
        persistence_db = PersistenceDatabase()
        print("[Service] Persistence database initialized")
    except Exception as e:
        print(f"[Service] Database initialization failed: {e}")
    
    notification_manager = None
    if _is_android:
        notification_manager = ServiceNotificationManager()
        try:
            notification_manager.show_foreground_notification()
        except Exception as e:
            print(f"[Service] Foreground notification error: {e}")
    
    def on_message_received_callback(peer_ip: str, message: str, timestamp: float):
        print(f"[Service] Message from {peer_ip}: {message}")
        
        if notification_manager and _is_android:
            try:
                notification_manager.show_message_notification(peer_ip, message)
            except Exception as e:
                print(f"[Service] Notification error: {e}")
    
    engine = LightweightGhostEngine(
        username=username,
        on_message_received=on_message_received_callback,
        persistence_db=persistence_db,
        notification_manager=notification_manager
    )
    
    engine.start()
    
    print("[Service] Background service running. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Service] Shutting down...")
        engine.stop()
        sys.exit(0)


if __name__ == '__main__':
    main()
