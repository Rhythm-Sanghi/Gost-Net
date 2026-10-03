"""
Ghost Net - Main Application
Material Design P2P messaging app using KivyMD.
Offline-first, local network communication with file transfer support.
"""

import os
import sys
import platform
import time
import threading
import random
from typing import Optional
from datetime import datetime

# Ensure src/ package is in sys.path
_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from kivy.utils import platform as _kivy_platform
    _is_android = (_kivy_platform == 'android')
except ImportError:
    _is_android = False

def _setup_crash_logging():
    import traceback

    def _handle_exception(exc_type, exc_val, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        try:
            sys.__stderr__.write(f"[FATAL_STARTUP_CRASH] {msg}\n")
            sys.__stderr__.flush()
            sys.__stdout__.write(f"[FATAL_STARTUP_CRASH] {msg}\n")
            sys.__stdout__.flush()
        except Exception:
            pass

        candidate_dirs = [
            os.path.dirname(os.path.abspath(__file__)),
            os.path.expanduser("~"),
            "/data/user/0/org.ghostnet.ghostnet/files/app",
            "."
        ]
        for cdir in candidate_dirs:
            try:
                log_file = os.path.join(cdir, "startup-crash.log")
                with open(log_file, "a") as f:
                    f.write(f"\n--- FATAL CRASH {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{msg}\n")
                break
            except Exception:
                continue

    sys.excepthook = _handle_exception
    if hasattr(threading, 'excepthook'):
        def _thread_hook(args):
            _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = _thread_hook

_setup_crash_logging()

# Qualify the cryptography native extension before anything imports it. On
# Android a Rust extension that fails to link against libpython is not caught by
# the page-size gate or by the desktop test suite -- it only surfaces when the
# device's dynamic loader opens it, which is why this runs first and why its
# result is written to disk where it can be read back after a crash.
try:
    from crypto_selftest import run as _run_crypto_selftest
    _CRYPTO_SELFTEST_OK, _CRYPTO_SELFTEST_DETAIL = _run_crypto_selftest()
except Exception as _exc:  # pragma: no cover - diagnostics must never block boot
    _CRYPTO_SELFTEST_OK, _CRYPTO_SELFTEST_DETAIL = False, repr(_exc)

# UI Components, Screens, and Framework shims (re-exported for backwards compatibility)
from ui import (
    apply_premium_background,
    KIVYMD_AVAILABLE,
    MDSpinner,
    MDButtonText,
    MDTextFieldHintText,
    MDTextFieldHelperText,
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
    MDSwitch,
    MDProgressBar,
    MDFloatingActionButton,
    MessageBubble,
    FileBubble,
    AudioBubble,
    RadarWidget,
    MeshTopologyWidget,
    LockScreen,
    BootScreen,
    RadarScreen,
    ChatScreen,
    MapScreen,
    GhostMapMarker,
    OfflineMBTilesMapSource,
    MAPVIEW_AVAILABLE,
    DiagnosticsScreen,
    SettingsScreen,
    NotesScreen,
)
from ui.theme import _safe_import

from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager
from kivy.clock import Clock
from kivy.core.window import Window

from network import GhostEngine
from database import PersistenceDatabase
from storage import DatabaseManager
from config import get_config
from android_mocks import get_file_picker, get_notification_manager
from audio_manager import get_audio_manager
from gps_manager import get_gps_manager
from auth_manager import AuthenticationManager
from diagnostics import get_diagnostics, encrypt_telemetry_file, copy_to_downloads
from telemetry_logger import get_telemetry_logger

# Configure soft input mode for Android keyboard handling
if _is_android:
    Window.keyboard_anim_args = {'d': 0.2, 't': 'in_out_cubic'}


class GhostNetApp(MDApp):
    """Main application class."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = None
        self.username = "GhostUser"
        self.service_running = False
        self.notification_manager = None
        self.decoy_mode = False
        self.auth_manager = AuthenticationManager()
        self.telemetry = get_telemetry_logger()
        
    @property
    def config(self):
        return get_config()
        
    @config.setter
    def config(self, value):
        pass
    
    def _start_android_service(self):
        if _is_android:
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                Intent = autoclass('android.content.Intent')
                BuildVersion = autoclass('android.os.Build$VERSION')
                
                service_classes = [
                    'org.ghostnet.ghostnet.ServiceGhostservice',
                    'org.ghostnet.ServiceGhostservice',
                    'org.kivy.android.PythonService'
                ]
                service_class = None
                for cls_name in service_classes:
                    try:
                        service_class = autoclass(cls_name)
                        break
                    except Exception:
                        continue
                
                if service_class and activity:
                    intent = Intent(activity, service_class)
                    if BuildVersion.SDK_INT >= 26:
                        activity.startForegroundService(intent)
                    else:
                        activity.startService(intent)
                    self.service_running = True
                    print("[GhostNetApp] Started Android background service")
                else:
                    print("[GhostNetApp] Could not resolve Android service class")
            except Exception as e:
                print(f"[GhostNetApp] Failed to start service: {e}")
        else:
            print("[GhostNetApp] Not on Android - skipping service startup")
    
    def build(self):
        """Build the app UI."""
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Indigo"
        
        sm = MDScreenManager()
        sm.add_widget(LockScreen())
        sm.add_widget(BootScreen())
        sm.add_widget(RadarScreen())
        sm.add_widget(DiagnosticsScreen())
        sm.add_widget(ChatScreen())
        sm.add_widget(SettingsScreen())
        sm.add_widget(NotesScreen())
        sm.add_widget(MapScreen())
        
        sm.current = 'lock'
        
        from ui.navigation import get_navigation_controller
        get_navigation_controller().setup_window_hooks()
        
        return sm
    
    def navigate_to(self, screen_name, direction='left'):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().navigate_to(screen_name, direction=direction)

    def go_back(self, direction='right'):
        from ui.navigation import get_navigation_controller
        return get_navigation_controller().go_back(direction=direction)
    
    def on_start(self):
        """Called when the app starts - now with async boot sequence."""
        self.downloads_path = None
        try:
            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads", "GhostNet")
            os.makedirs(downloads_path, exist_ok=True)
            self.downloads_path = downloads_path
            print(f"[GhostNet] Downloads directory: {downloads_path}")
        except Exception as e:
            print(f"[GhostNet] Primary downloads path failed: {e}")
            try:
                if _is_android:
                    downloads_path = os.path.join(os.path.expanduser("~"), ".ghostnet", "downloads")
                else:
                    downloads_path = os.path.join(os.path.expanduser("~"), ".ghostnet", "downloads")
                os.makedirs(downloads_path, exist_ok=True)
                self.downloads_path = downloads_path
                print(f"[GhostNet] Using fallback downloads directory: {downloads_path}")
            except Exception as e2:
                print(f"[GhostNet] WARNING: Could not create downloads directory: {e2}")
        
        self._start_android_service()
        
        threading.Thread(target=self.pre_unlock_startup, daemon=True).start()
    
    def pre_unlock_startup(self):
        """
        Perform basic startup configuration and permission checks before the app is unlocked.
        """
        try:
            def request_perms_ui():
                try:
                    self.request_permissions()
                except Exception as e:
                    print(f"[GhostNet] Permission request error: {e}")
            Clock.schedule_once(lambda dt: request_perms_ui(), 0)
            time.sleep(0.5)
            
            try:
                self.config = get_config()
            except Exception as e:
                print(f"[GhostNet] Config initialization error: {e}")
                self.config = None
            
            if self.config:
                try:
                    theme_style = "Dark" if self.config.is_dark_mode() else "Light"
                    Clock.schedule_once(
                        lambda dt: setattr(self.theme_cls, 'theme_style', theme_style),
                        0
                    )
                except Exception as e:
                    print(f"[GhostNet] Theme application error: {e}")
            
            def register_config_callback():
                if self.config:
                    try:
                        self.config.register_change_callback(self.on_config_changed)
                    except Exception as e:
                        print(f"[GhostNet] Config callback registration error: {e}")
            Clock.schedule_once(lambda dt: register_config_callback(), 0.5)
            
            if self.config:
                self.username = self.config.get_username()
            else:
                self.username = "GhostUser"
            
            print("[GhostNet] Pre-unlock startup finished. Waiting for PIN entry on LockScreen.")
            
        except Exception as e:
            print(f"[GhostNet] Pre-unlock startup error: {e}")
            
    def post_unlock_startup(self, pin: str):
        """
        Perform final database and network engine boot sequence once PIN is validated.
        Runs in a background thread.
        """
        def get_boot_screen():
            try:
                return self.root.get_screen('boot')
            except:
                return None
        
        Clock.schedule_once(lambda dt: setattr(self.root, 'current', 'boot'), 0)
        time.sleep(0.5)
        
        boot_screen = get_boot_screen()
        if boot_screen:
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Deriving Master Key..."),
                0
            )
            
        try:
            self.db_key = self.auth_manager.get_or_create_db_key(pin)
            if not self.db_key:
                print("[GhostNet] ERROR: Could not derive database key.")
                if boot_screen:
                    Clock.schedule_once(
                        lambda dt: boot_screen.update_status("Master Key Derivation Failed!"),
                        0
                    )
                return
                
            if boot_screen:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status("Initializing database..."),
                    0
                )
                
            self.persistence_db = None
            try:
                self.persistence_db = PersistenceDatabase(decrypted_key=self.db_key)
                if self.auth_manager and self.auth_manager.is_decoy_mode_active():
                    self.decoy_mode = True
                    print("[GhostNet] Persistent decoy mode active. Unlocking decoy vault.")
                    self.start_decoy_simulator()
                if self.config and self.config.get("ephemeral_mode", False):
                    self.persistence_db.ephemeral_mode = True
                    print("[GhostNet] Ephemeral Mode active in database")
                time.sleep(0.5)
            except Exception as e:
                print(f"[GhostNet] Persistence database error: {e}")
                self.persistence_db = None
            
            if boot_screen:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status("Starting P2P network..."),
                    0
                )
            
            try:
                db_mgr = DatabaseManager(decrypted_key=self.db_key)
                if getattr(self, 'telemetry', None) and getattr(db_mgr, 'cipher', None):
                    self.telemetry.set_cipher(db_mgr.cipher)
                if self.config and self.config.get("ephemeral_mode", False):
                    db_mgr.ephemeral_mode = True
                    print("[GhostNet] Ephemeral Mode active in storage database manager")
                    
                self.signing_key = self.auth_manager.get_or_create_signing_key(pin)
                self.engine = GhostEngine(
                    config_manager=self.config,
                    on_message_received=self.handle_message_received,
                    on_peer_update=self.handle_peer_update,
                    on_file_received=self.handle_file_received,
                    persistence_db=self.persistence_db,
                    db_manager=db_mgr,
                    enable_storage=True,
                    signing_private_key_bytes=self.signing_key
                )
                self.engine.on_sos_received = self.handle_sos_received
                self.engine.on_delivery_status = self.handle_delivery_status
                self.engine.on_location_update_received = self.handle_location_update_received
                self.engine.on_waypoint_received = self.handle_waypoint_received
                self.engine.on_peer_revoked = self.handle_peer_revoked
                self.engine.on_group_message_received = self.handle_group_message_received
                self.engine.on_peer_key_changed = self.handle_peer_key_changed
                
                if self.config and self.config.get("chaffing_enabled", False):
                    self.engine.chaffing_enabled = True
                    
                diag_mgr = get_diagnostics()
                diag_mgr.set_engine_reference(self.engine)
                
                gps_mgr = get_gps_manager()
                gps_mgr.start()
                
                threading.Thread(target=self.engine.start, daemon=True).start()
                time.sleep(1.0)
            except Exception as e:
                print(f"[GhostNet] Engine initialization error: {e}")
                self.engine = None
            
            if boot_screen:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status("Setting up background scrubbing..."),
                    0
                )
            Clock.schedule_interval(self.run_message_scrubbing, 10)
            time.sleep(0.5)
            
            if boot_screen:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status("Cleaning old messages..."),
                    0
                )
            if self.config and self.config.is_auto_cleanup_enabled():
                retention_hours = self.config.get_retention_hours()
                self.cleanup_old_messages(hours=retention_hours)
            time.sleep(0.5)
            
            if boot_screen:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status("Ready!"),
                    0
                )
            time.sleep(0.5)
            
            print(f"[GhostNet] App started as '{self.username}'")
            
            Clock.schedule_once(
                lambda dt: setattr(self.root, 'current', 'radar'),
                0
            )
            
        except Exception as e:
            print(f"[GhostNet] Post-unlock startup error: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status(f"Error: {str(e)[:30]}..."),
                    0
                )
            except:
                pass
            
            time.sleep(2)
            try:
                Clock.schedule_once(
                    lambda dt: setattr(self.root, 'current', 'lock'),
                    0
                )
            except Exception as e2:
                print(f"[GhostNet] Could not transition to lock: {e2}")
    
    def on_config_changed(self, key: str, old_value, new_value):
        """Handle configuration changes for hot-reloading."""
        try:
            print(f"[GhostNet] Config changed: {key} = {old_value} → {new_value}")
            
            if key == "dark_mode":
                if hasattr(self, 'theme_cls') and self.theme_cls:
                    self.theme_cls.theme_style = "Dark" if new_value else "Light"
                    print(f"[GhostNet] Theme changed to {'Dark' if new_value else 'Light'} mode")
            
            elif key == "username":
                self.username = new_value
                print(f"[GhostNet] Username updated to '{new_value}'")
        except Exception as e:
            print(f"[GhostNet] Config change handler error: {e}")
    
    def cleanup_old_messages(self, hours: int = 24):
        """
        Privacy feature: Delete messages older than specified hours.
        """
        if not self.engine or not self.engine.db_manager:
            return
        
        def _cleanup_worker():
            try:
                deleted = self.engine.db_manager.cleanup_old_messages(hours)
                if deleted > 0:
                    print(f"[Privacy] Deleted {deleted} messages older than {hours} hours")
            except Exception as e:
                print(f"[Privacy] Cleanup error: {e}")
        
        threading.Thread(target=_cleanup_worker, daemon=True).start()
    
    def run_message_scrubbing(self, dt=None):
        if not self.persistence_db:
            return
        
        def _scrub_worker():
            try:
                deleted = self.persistence_db.scrub_expired_messages()
            except Exception as e:
                print(f"[Scrubbing] Error: {e}")
        
        threading.Thread(target=_scrub_worker, daemon=True).start()
        
    def get_identity_fingerprint(self) -> Optional[str]:
        import hashlib
        if self.engine and self.engine.crypto_manager:
            try:
                pub_bytes = self.engine.crypto_manager.get_signing_public_key_bytes()
                return hashlib.sha256(pub_bytes).hexdigest()
            except Exception as e:
                print(f"[GhostNetApp] Error getting fingerprint: {e}")
        return None
    
    def request_permissions(self):
        """Request all required runtime permissions on Android with safe fallback."""
        if _is_android:
            try:
                try:
                    from android_permissions import PermissionManager
                    perm_mgr = PermissionManager()
                    if perm_mgr and hasattr(perm_mgr, 'request_all_permissions'):
                        perm_mgr.request_all_permissions()
                        print("[GhostNet] Requested permissions via PermissionManager")
                        return
                except Exception as pm_err:
                    print(f"[GhostNet] PermissionManager fallback to direct request: {pm_err}")

                from android.permissions import request_permissions, Permission
                
                all_permissions = [
                    'INTERNET',
                    'ACCESS_NETWORK_STATE',
                    'ACCESS_WIFI_STATE',
                    'CHANGE_WIFI_STATE',
                    'CHANGE_WIFI_MULTICAST_STATE',
                    'CHANGE_NETWORK_STATE',
                    'READ_EXTERNAL_STORAGE',
                    'WRITE_EXTERNAL_STORAGE',
                    'WAKE_LOCK',
                    'ACCESS_FINE_LOCATION',
                    'ACCESS_COARSE_LOCATION',
                    'RECORD_AUDIO',
                    'POST_NOTIFICATIONS',
                    'NEARBY_WIFI_DEVICES',
                    'BLUETOOTH',
                    'BLUETOOTH_ADMIN',
                    'BLUETOOTH_SCAN',
                    'BLUETOOTH_CONNECT',
                ]
                permissions_to_request = []
                for perm_name in all_permissions:
                    if hasattr(Permission, perm_name):
                        permissions_to_request.append(getattr(Permission, perm_name))
                
                if permissions_to_request:
                    request_permissions(permissions_to_request)
                    print(f"[GhostNet] Requested {len(permissions_to_request)} Android permissions")
                else:
                    print("[GhostNet] No permissions to request")
                    
            except ImportError as e:
                print(f"[GhostNet] Android permissions module not available: {e}")
            except AttributeError as e:
                print(f"[GhostNet] Permission attribute missing (API level issue): {e}")
            except Exception as e:
                print(f"[GhostNet] Permission request error: {e}")
        else:
            print("[GhostNet] Not on Android - permissions not needed")
    
    def on_pause(self):
        print("[GhostNet] App paused - handing off to background service")
        return True
    
    def on_resume(self):
        print("[GhostNet] App resumed - checking network & refreshing UI")
        try:
            if self.engine:
                if hasattr(self.engine, 'network_monitor') and self.engine.network_monitor:
                    self.engine.network_monitor.check_network_change()
                if hasattr(self.engine, 'get_all_peers_combined'):
                    self.handle_peer_update(self.engine.get_all_peers_combined())
            if self.persistence_db:
                chat_screen = self.root.get_screen('chat')
                if chat_screen and getattr(chat_screen, 'peer_ip', None):
                    chat_screen.load_history()
                    print("[GhostNet] Chat history refreshed")
        except Exception as e:
            print(f"[GhostNet] Resume refresh error: {e}")
    
    def on_stop(self):
        """Called when the app stops."""
        if self.engine:
            self.engine.stop()
    
    def handle_peer_update(self, peers_dict):
        """Handle peer list updates from network thread."""
        Clock.schedule_once(
            lambda dt: self.update_radar_peers(peers_dict),
            0
        )
    
    def update_radar_peers(self, peers_dict):
        """Update radar screen with peer list and network status (main thread)."""
        try:
            radar_screen = self.root.get_screen('radar')
            
            if self.decoy_mode:
                decoy_peers = {
                    "wfd_alice": {"username": "Alice (Base)", "peer_id": "wfd_alice", "visible_peers": []},
                    "bt_bob": {"username": "Bob (Mobile)", "peer_id": "bt_bob", "visible_peers": []},
                    "mesh_charlie": {"username": "Charlie (Relay)", "peer_id": "mesh_charlie", "visible_peers": ["wfd_alice"]}
                }
                radar_screen.update_peers(decoy_peers)
                decoy_net_status = {"type": "wifi", "ip": "192.168.43.10"}
                radar_screen.update_network_status(decoy_net_status)
                return
            
            radar_screen.update_peers(peers_dict)
            
            if self.engine:
                network_status = self.engine.get_network_status()
                radar_screen.update_network_status(network_status)
        except Exception as e:
            print(f"[GhostNetApp] Error updating radar: {e}")
    
    def handle_message_received(self, sender_ip, message_text, timestamp):
        """Handle incoming messages from network thread."""
        Clock.schedule_once(
            lambda dt: self.add_message_to_chat(sender_ip, message_text, timestamp),
            0
        )
    
    def add_message_to_chat(self, sender_ip, message_text, timestamp):
        """Add received message to chat screen (main thread)."""
        chat_screen = self.root.get_screen('chat')
        chat_screen.add_received_message(sender_ip, message_text, timestamp)
        
        if self.root.current != 'chat':
            username = self.engine.get_peer_username(sender_ip) if self.engine else sender_ip
            print(f"[Notification] New message from {username}")

    def handle_delivery_status(self, msg_id, target_ip, status):
        """Forward message delivery status updates to chat screen."""
        if not self.root:
            return
        def _update(dt):
            try:
                chat_screen = self.root.get_screen('chat')
                if chat_screen:
                    chat_screen.update_delivery_status(msg_id, status)
            except Exception as e:
                print(f"[GhostNetApp] Delivery status update error: {e}")
        Clock.schedule_once(_update, 0)

    def handle_peer_key_changed(self, peer_id, stored_key, new_key):
        """Handle peer cryptographic key mismatch detected by network engine."""
        if not self.root:
            return
        def _update(dt):
            try:
                if hasattr(self.root, 'get_screen'):
                    chat_screen = self.root.get_screen('chat')
                    if chat_screen and chat_screen.peer_ip == peer_id:
                        chat_screen.security_banner.opacity = 1
                        chat_screen.security_banner.disabled = False
                    radar_screen = self.root.get_screen('radar')
                    if radar_screen:
                        radar_screen.update_peer_list()
            except Exception as e:
                print(f"[GhostNetApp] Peer key changed handling error: {e}")
        Clock.schedule_once(_update, 0)

    def handle_location_update_received(self, payload: dict):
        """Update tactical map with peer's GPS telemetry."""
        if not self.root:
            return
        def _update(dt):
            try:
                if hasattr(self.root, 'get_screen'):
                    map_screen = self.root.get_screen('map')
                    if map_screen and hasattr(map_screen, 'plot_peer_marker'):
                        map_screen.plot_peer_marker(
                            peer_id=payload.get("peer_id", ""),
                            username=payload.get("username", "Peer"),
                            lat=payload.get("latitude", 0.0),
                            lon=payload.get("longitude", 0.0),
                            alt=payload.get("altitude", 0.0),
                            acc=payload.get("accuracy", 0.0)
                        )
            except Exception as e:
                print(f"[GhostNetApp] Location telemetry error: {e}")
        Clock.schedule_once(_update, 0)

    def handle_waypoint_received(self, waypoint_dict: dict):
        """Plot tactical waypoint received over mesh network."""
        if not self.root:
            return
        def _update(dt):
            try:
                if hasattr(self.root, 'get_screen'):
                    map_screen = self.root.get_screen('map')
                    if map_screen and hasattr(map_screen, 'plot_waypoint'):
                        map_screen.plot_waypoint(waypoint_dict)
            except Exception as e:
                print(f"[GhostNetApp] Waypoint received error: {e}")
        Clock.schedule_once(_update, 0)

    def handle_peer_revoked(self, peer_id: str, reason: str):
        """Handle peer blacklisting/revocation notification."""
        if not self.root:
            return
        def _update(dt):
            try:
                if self.engine:
                    self.update_radar_peers(self.engine.peers)
                chat_screen = self.root.get_screen('chat')
                if chat_screen and chat_screen.peer_ip == peer_id:
                    chat_screen.peer_label.text = f"[REVOKED] {chat_screen.peer_name}"
            except Exception as e:
                print(f"[GhostNetApp] Peer revocation handling error: {e}")
        Clock.schedule_once(_update, 0)

    def handle_group_message_received(self, channel_id: str, sender_id: str, sender_name: str, message: str, timestamp: float):
        """Handle incoming group message and update chat if active on that channel."""
        if not self.root:
            return
        def _update(dt):
            try:
                if hasattr(self.root, 'get_screen'):
                    chat_screen = self.root.get_screen('chat')
                    if chat_screen and getattr(chat_screen, 'current_channel_id', None) == channel_id:
                        chat_screen.add_message_bubble(
                            message=message,
                            is_own=False,
                            timestamp=timestamp,
                            sender_name=sender_name
                        )
            except Exception as e:
                print(f"[GhostNetApp] Group message update error: {e}")
        Clock.schedule_once(_update, 0)
    
    def handle_file_received(self, sender_ip, filename, filepath, timestamp):
        """Handle incoming file from network thread."""
        if filename == 'notes.txt':
            local_notes_file = "notes.txt"
            
            local_lines = []
            if os.path.exists(local_notes_file):
                try:
                    with open(local_notes_file, 'r', encoding='utf-8') as f:
                        local_lines = [line.rstrip('\r\n') for line in f]
                except Exception as e:
                    print(f"[GhostNetApp] Error reading local notes for merge: {e}")
            
            incoming_lines = []
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        incoming_lines = [line.rstrip('\r\n') for line in f]
                except Exception as e:
                    print(f"[GhostNetApp] Error reading incoming notes for merge: {e}")
            
            merged_lines = list(local_lines)
            local_set = set(local_lines)
            for line in incoming_lines:
                if line not in local_set:
                    merged_lines.append(line)
                    local_set.add(line)
            
            try:
                with open(local_notes_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(merged_lines))
                print(f"[GhostNetApp] Merged notes.txt with incoming lines from {sender_ip}")
            except Exception as e:
                print(f"[GhostNetApp] Error writing merged notes: {e}")
            
            def reload_editor_ui(dt):
                try:
                    notes_screen = self.root.get_screen('notes')
                    if notes_screen:
                        notes_screen.load_notes()
                except Exception as e:
                    print(f"[GhostNetApp] Error reloading notes screen UI: {e}")
            
            Clock.schedule_once(reload_editor_ui, 0)
            return

        Clock.schedule_once(
            lambda dt: self.add_file_to_chat(sender_ip, filename, filepath, timestamp),
            0
        )
    
    def add_file_to_chat(self, sender_ip, filename, filepath, timestamp):
        """Add received file to chat screen (main thread)."""
        chat_screen = self.root.get_screen('chat')
        chat_screen.add_received_file(sender_ip, filename, filepath, timestamp)
        
        if self.root.current != 'chat':
            username = self.engine.get_peer_username(sender_ip) if self.engine else sender_ip
            print(f"[Notification] File received from {username}: {filename}")
    
    def handle_sos_received(self, sender_name: str, latitude: float, longitude: float, message: str, sos_id: str):
        Clock.schedule_once(
            lambda dt: self.show_sos_alert_ui(sender_name, latitude, longitude, message, sos_id),
            0
        )
    
    def show_sos_alert_ui(self, sender_name: str, latitude: float, longitude: float, message: str, sos_id: str):
        try:
            radar_screen = self.root.get_screen('radar')
            radar_screen.show_sos_alert(sender_name, latitude, longitude, message, sos_id)
            
            if MAPVIEW_AVAILABLE:
                try:
                    map_screen = self.root.get_screen('map')
                    if map_screen and hasattr(map_screen, 'plot_sos_marker'):
                        map_screen.plot_sos_marker(latitude, longitude, sender_name, sos_id)
                except Exception as map_err:
                    print(f"[GhostNetApp] Map marker plot error: {map_err}")
        except Exception as e:
            print(f"[GhostNetApp] SOS alert UI error: {e}")
            
    def start_decoy_simulator(self):
        """Starts the background decoy conversation simulator worker."""
        if hasattr(self, '_decoy_simulator_started') and self._decoy_simulator_started:
            return
        self._decoy_simulator_started = True
        t = threading.Thread(target=self._decoy_simulator_worker, daemon=True)
        t.start()
        print("[GhostNet] Decoy simulator worker started.")

    def _decoy_simulator_worker(self):
        decoy_peers = ["wfd_alice", "bt_bob", "mesh_charlie"]
        
        decoy_messages = {
            "wfd_alice": [
                "Signals are stable on the backup channel.",
                "Moving to alternate frequency sector 4.",
                "Atmospheric conditions are causing slight delay.",
                "Let's schedule the next sync checkpoint.",
                "Status report: all base systems are nominal.",
                "No signs of activity on the perimeter."
            ],
            "bt_bob": [
                "Approaching rendezvous point Bravo.",
                "ETA to location is 15 minutes.",
                "Bringing the secondary communication terminal.",
                "Bob checking in. Signal strength is good.",
                "Relaying the latest geographic maps.",
                "Leaving sector 9 now."
            ],
            "mesh_charlie": [
                "Mesh relay node Charlie online.",
                "Routing path optimization completed.",
                "Dynamic beaconing interval set to low-power.",
                "Forwarded 12 diagnostic logs successfully.",
                "Relaying distress signal beacons.",
                "No packet loss detected on the 2.4GHz link."
            ]
        }
        
        while self.decoy_mode:
            is_testing = (
                "pytest" in sys.modules
                or "unittest" in sys.modules
                or any("test" in arg.lower() for arg in sys.argv)
                or os.environ.get("TESTING") == "1"
            )
            sleep_time = random.randint(1, 2) if is_testing else random.randint(30, 60)
            
            time.sleep(sleep_time)
            if not self.decoy_mode:
                break
                
            sender = random.choice(decoy_peers)
            msg = random.choice(decoy_messages[sender])
            
            self._inject_decoy_message(sender, msg)

    def _inject_decoy_message(self, sender_ip, message_text):
        if not self.decoy_mode:
            return
        
        timestamp_unix = time.time()
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        
        if self.persistence_db:
            self.persistence_db.save_message(sender_ip, "peer", "text", message_text, timestamp_unix)
            
        try:
            chat_screen = self.root.get_screen('chat')
            if chat_screen.peer_ip == sender_ip and self.root.current == 'chat':
                Clock.schedule_once(lambda dt: chat_screen.add_received_message(sender_ip, message_text, timestamp_str), 0)
            else:
                peer_names = {
                    "wfd_alice": "Alice (Base)",
                    "bt_bob": "Bob (Mobile)",
                    "mesh_charlie": "Charlie (Relay)"
                }
                username = peer_names.get(sender_ip, sender_ip)
                print(f"[Notification] New message from {username}: {message_text}")
        except Exception as e:
            pass


if __name__ == '__main__':
    try:
        print("[GhostNet] Initializing GhostNetApp...")
        GhostNetApp().run()
        print("[GhostNet] GhostNetApp main loop exited cleanly.")
    except BaseException as e:
        import traceback
        tb = traceback.format_exc()
        try:
            sys.__stderr__.write(f"[FATAL_STARTUP_CRASH] {tb}\n")
            sys.__stderr__.flush()
            sys.__stdout__.write(f"[FATAL_STARTUP_CRASH] {tb}\n")
            sys.__stdout__.flush()
        except Exception:
            pass
        for cdir in [
            os.path.dirname(os.path.abspath(__file__)),
            os.path.expanduser("~"),
            "/data/user/0/org.ghostnet.ghostnet/files/app",
            "."
        ]:
            try:
                log_file = os.path.join(cdir, "startup-crash.log")
                with open(log_file, "a") as f:
                    f.write(f"\n--- FATAL RUNTIME CRASH {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{tb}\n")
                break
            except Exception:
                continue
        raise