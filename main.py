"""
Ghost Net - Main Application
Material Design P2P messaging app using KivyMD.
Offline-first, local network communication with file transfer support.
"""

import os
import platform as _platform_check
if _platform_check.system() == 'Android':
    try:
        from logger import activate_opsec
        activate_opsec()
    except:
        pass

def _safe_import(module_path, name, fallback_class=None):
    try:
        parts = module_path.rsplit('.', 1)
        module = __import__(module_path, fromlist=[name])
        return getattr(module, name)
    except (ImportError, AttributeError):
        if fallback_class:
            return fallback_class
        raise

try:
    from kivymd.app import MDApp
    from kivy.metrics import dp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.screenmanager import MDScreenManager
    from kivymd.uix.button import MDButton, MDIconButton
    try:
        from kivymd.uix.button import MDFloatingActionButton
    except ImportError:
        MDFloatingActionButton = None
    from kivymd.uix.textfield import MDTextField
    from kivymd.uix.label import MDLabel
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.scrollview import MDScrollView
    from kivymd.uix.card import MDCard
    from kivymd.uix.filemanager import MDFileManager
    from kivymd.uix.slider import MDSlider
    
    # Create fallback classes for optional components
    from kivy.uix.widget import Widget as KivyWidget
    from kivy.properties import BooleanProperty
    
    class _DummySpinner(KivyWidget):
        """Fallback spinner for KivyMD versions without MDSpinner."""
        active = BooleanProperty(True)
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
    
    class _DummyDialog(KivyWidget):
        """Fallback dialog for KivyMD versions without MDDialog."""
        def __init__(self, *args, **kwargs):
            super().__init__(**kwargs)
        def open(self, *args): pass
        def dismiss(self, *args): pass
    
    class _DummySwitch(KivyWidget):
        """Fallback switch for KivyMD versions without MDSwitch."""
        active = BooleanProperty(False)
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
    
    # Import optional components with fallbacks
    try:
        # Try KivyMD 2.0+ first (MDCircularProgressIndicator)
        from kivymd.uix.progressindicator import MDCircularProgressIndicator as MDSpinner
    except ImportError:
        try:
            # Fall back to older MDSpinner
            from kivymd.uix.spinner import MDSpinner
        except ImportError:
            MDSpinner = _DummySpinner
    
    try:
        from kivymd.uix.button import MDButtonText
        from kivymd.uix.textfield import MDTextFieldHintText, MDTextFieldHelperText
    except ImportError:
        MDButtonText = MDLabel
        # Use a deferred lambda that accesses Widget only at call time (Widget is imported later)
        MDTextFieldHintText = lambda **kwargs: KivyWidget(**{k: v for k, v in kwargs.items() if k != 'text'})
        MDTextFieldHelperText = lambda **kwargs: KivyWidget(**{k: v for k, v in kwargs.items() if k != 'text'})
    
    try:
        from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogContentContainer, MDDialogButtonContainer
    except ImportError:
        MDDialog = _DummyDialog
        MDDialogHeadlineText = MDLabel
        MDDialogContentContainer = MDBoxLayout
        MDDialogButtonContainer = MDBoxLayout
    
    try:
        from kivymd.uix.switch import MDSwitch
    except ImportError:
        MDSwitch = _DummySwitch
    
    try:
        from kivymd.uix.progressbar import MDProgressBar
    except ImportError:
        MDProgressBar = None
    
    KIVYMD_AVAILABLE = True
except ImportError as e:
    print(f"[CRITICAL] KivyMD import failed: {e}")
    print("[CRITICAL] Please ensure KivyMD is properly installed")
    import sys
    sys.exit(1)
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import StringProperty, ListProperty, NumericProperty
from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line
from kivy.uix.widget import Widget
from datetime import datetime
import threading
import os
import platform
import sys
import time

from network import GhostEngine
from database import PersistenceDatabase
from config import get_config
from android_mocks import get_file_picker, get_notification_manager
from audio_manager import get_audio_manager
from gps_manager import get_gps_manager
from auth_manager import AuthenticationManager
from diagnostics import get_diagnostics, encrypt_telemetry_file, copy_to_downloads
from telemetry_logger import get_telemetry_logger

try:
    from kivy_garden.mapview import MapView, MapMarker
    MAPVIEW_AVAILABLE = True
except ImportError:
    MapView = None
    MapMarker = None
    MAPVIEW_AVAILABLE = False
    print("[MapScreen] MapView not available - tactical map disabled")

# Configure soft input mode for Android keyboard handling
if platform.system() == 'Android':
    from kivy.core.window import Window
    Window.keyboard_anim_args = {'d': 0.2, 't': 'in_out_cubic'}


class LockScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'lock'
        self.auth_manager = AuthenticationManager()
        self.shredding_in_progress = False
        
        layout = MDBoxLayout(
            orientation='vertical',
            padding=dp(20),
            spacing=dp(20),
            size_hint=(1, 1)
        )
        
        title = MDLabel(
            text='🔐 Ghost Net',
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            halign='center',
            size_hint_y=None,
            height=dp(80)
        )
        layout.add_widget(title)
        
        spacer1 = MDLabel(size_hint_y=0.2)
        layout.add_widget(spacer1)
        
        self.pin_field = MDTextField(
            mode='rectangle',
            hint_text='Enter PIN',
            password=True,
            size_hint_x=1,
            size_hint_y=None,
            height=dp(56),
            multiline=False
        )
        layout.add_widget(self.pin_field)
        
        button_layout = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(10),
            size_hint_y=None,
            height=dp(50)
        )
        
        submit_btn = MDButton(MDButtonText(text='Unlock'))
        submit_btn.bind(on_release=self.on_pin_submit)
        button_layout.add_widget(submit_btn)
        
        layout.add_widget(button_layout)
        
        spacer2 = MDLabel(size_hint_y=None, height=dp(20))
        layout.add_widget(spacer2)
        
        self.status_label = MDLabel(
            text='',
            theme_text_color='Secondary',
            halign='center',
            size_hint_y=None,
            height=dp(40)
        )
        layout.add_widget(self.status_label)
        
        self.add_widget(layout)
    
    def on_pin_submit(self, *args):
        pin = self.pin_field.text.strip()
        
        if not pin:
            self.status_label.text = 'Please enter a PIN'
            return
        
        pin_type = self.auth_manager.identify_pin(pin)
        
        if pin_type == 'master':
            self.transition_to_radar()
        elif pin_type == 'duress':
            self.trigger_duress_protocol()
        else:
            self.status_label.text = 'Invalid PIN'
            self.pin_field.text = ''
    
    def transition_to_radar(self):
        app = MDApp.get_running_app()
        if app and app.root:
            try:
                app.root.current = 'radar'
            except Exception as e:
                self.status_label.text = f'Error: {str(e)}'
                print(f"[LockScreen] Transition error: {e}")
    
    def trigger_duress_protocol(self):
        if self.shredding_in_progress:
            return
        
        self.shredding_in_progress = True
        self.status_label.text = 'Initiating secure wipe...'
        self.pin_field.disabled = True
        
        app = MDApp.get_running_app()
        
        def shred_worker():
            try:
                if app and app.persistence_db:
                    app.persistence_db.shred_everything()
                
                audio_manager = get_audio_manager()
                audio_manager.shred_cache()
                
                if hasattr(app, 'crypto_manager') and app.crypto_manager:
                    app.crypto_manager.shred_all_keys()
                
                Clock.schedule_once(lambda dt: self.show_empty_radar(), 0)
            except Exception as e:
                print(f"[LockScreen] Shredding error: {e}")
                Clock.schedule_once(lambda dt: self.show_empty_radar(), 0)
        
        shred_thread = threading.Thread(target=shred_worker, daemon=False)
        shred_thread.start()
    
    def show_empty_radar(self):
        app = MDApp.get_running_app()
        if app and app.root:
            try:
                radar_screen = app.root.get_screen('radar')
                if hasattr(radar_screen, 'peers'):
                    radar_screen.peers = []
                if hasattr(radar_screen, 'update_peers_display'):
                    radar_screen.update_peers_display()
                app.root.current = 'radar'
            except Exception as e:
                print(f"[LockScreen] Radar transition error: {e}")


class MapMarkerPopup(MapMarker if MAPVIEW_AVAILABLE else object):
    def __init__(self, lat, lon, title, color=(1, 0, 0, 1), is_user=False, **kwargs):
        if MAPVIEW_AVAILABLE:
            super().__init__(lat=lat, lon=lon, **kwargs)
            self.title = title
            self.color = color
            self.is_user = is_user
            self.timestamp = None
            self.sender_name = None
            
            from kivy.garden.mapview import MapSource
            self.source = MapSource.cache
            
            self.bind(on_release=self.on_marker_release)
    
    def on_marker_release(self, *args):
        app = MDApp.get_running_app()
        if app and hasattr(app.root, 'get_screen'):
            try:
                map_screen = app.root.get_screen('map')
                if map_screen and hasattr(map_screen, 'show_marker_details'):
                    map_screen.show_marker_details(self)
            except:
                pass


class MapScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'map'
        self.gps_manager = get_gps_manager()
        self.sos_markers = {}
        self.user_marker = None
        self.map_view = None
        self.selected_marker = None
        
        layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(60),
            spacing=dp(10)
        )
        
        back_btn = MDIconButton(icon='arrow-left')
        back_btn.bind(on_release=self.go_back)
        
        title = MDLabel(
            text='🗺️ Tactical Map',
            font_style='Title',
            role='large',
            theme_text_color='Primary'
        )
        
        header.add_widget(back_btn)
        header.add_widget(title)
        layout.add_widget(header)
        
        if MAPVIEW_AVAILABLE and MapView:
            self.map_view = MapView(
                zoom=14,
                lat=22.7196,
                lon=75.8577,
                size_hint=(1, 0.85)
            )
            
            self.map_view.map_source.cache_size = 500
            self.map_view.map_source.cache = True
            
            self.init_user_marker()
            
            layout.add_widget(self.map_view)
        else:
            fallback_label = MDLabel(
                text='MapView unavailable - install kivy_garden.mapview',
                halign='center',
                theme_text_color='Secondary'
            )
            layout.add_widget(fallback_label)
        
        info_box = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(60),
            spacing=dp(5),
            padding=dp(10)
        )
        
        self.info_label = MDLabel(
            text='Your location: Loading...',
            font_style='Body',
            role='small',
            theme_text_color='Secondary'
        )
        
        self.markers_label = MDLabel(
            text='SOS Beacons: 0',
            font_style='Body',
            role='small',
            theme_text_color='Secondary'
        )
        
        info_box.add_widget(self.info_label)
        info_box.add_widget(self.markers_label)
        layout.add_widget(info_box)
        
        self.add_widget(layout)
        
        Clock.schedule_interval(self.update_user_location, 2.0)
    
    def init_user_marker(self):
        if not MAPVIEW_AVAILABLE or not self.map_view or not MapMarker:
            return
        
        lat, lon = self.gps_manager.get_coordinates()
        
        self.user_marker = MapMarkerPopup(
            lat=lat,
            lon=lon,
            title='Your Location',
            color=(0.2, 0.8, 1, 1),
            is_user=True
        )
        
        self.map_view.add_widget(self.user_marker)
    
    def update_user_location(self, dt):
        if not self.map_view or not self.user_marker:
            return
        
        try:
            lat, lon = self.gps_manager.get_coordinates()
            
            self.user_marker.lat = lat
            self.user_marker.lon = lon
            
            self.map_view.center_on(lat, lon)
            
            self.info_label.text = f'Your location: {lat:.4f}, {lon:.4f}'
        except Exception as e:
            print(f'[MapScreen] Location update error: {e}')
    
    def plot_sos_marker(self, lat, lon, sender_name, sos_id=None):
        if not MAPVIEW_AVAILABLE or not self.map_view or not MapMarker:
            print('[MapScreen] MapView not available for SOS plotting')
            return
        
        from kivy.clock import Clock
        from kivy.animation import Animation
        
        marker_id = sos_id or sender_name
        
        if marker_id in self.sos_markers:
            old_marker = self.sos_markers[marker_id]
            self.map_view.remove_widget(old_marker)
        
        marker = MapMarkerPopup(
            lat=lat,
            lon=lon,
            title=f'SOS: {sender_name}',
            color=(1, 0, 0, 1),
            is_user=False
        )
        marker.sender_name = sender_name
        marker.timestamp = datetime.now().strftime('%H:%M:%S')
        
        self.map_view.add_widget(marker)
        self.sos_markers[marker_id] = marker
        
        self.markers_label.text = f'SOS Beacons: {len(self.sos_markers)}'
        
        def pulse_animation():
            anim = Animation(opacity=0.5, duration=0.5) + Animation(opacity=1, duration=0.5)
            anim.repeat = True
            anim.start(marker)
        
        Clock.schedule_once(lambda dt: pulse_animation(), 0.1)
    
    def show_marker_details(self, marker):
        if not marker:
            return
        
        self.selected_marker = marker
        
        if marker.is_user:
            title_text = '📍 Your Location'
            details_text = f'Latitude: {marker.lat:.6f}\nLongitude: {marker.lon:.6f}'
        else:
            title_text = f'🚨 SOS: {marker.sender_name}'
            time_text = marker.timestamp or 'Unknown'
            details_text = f'From: {marker.sender_name}\nTime: {time_text}\nLat: {marker.lat:.6f}\nLon: {marker.lon:.6f}'
        
        content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(15),
            padding=dp(20),
            adaptive_height=True
        )
        
        title_label = MDLabel(
            text=title_text,
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            size_hint_y=None,
            height=dp(40)
        )
        
        details_label = MDLabel(
            text=details_text,
            font_style='Body',
            role='medium',
            size_hint_y=None,
            height=dp(80)
        )
        
        content.add_widget(title_label)
        content.add_widget(details_label)
        
        close_btn = MDButton(
            MDButtonText(text='Close'),
            style='elevated'
        )
        
        def dismiss_dialog(*args):
            if hasattr(self, '_marker_dialog') and self._marker_dialog:
                self._marker_dialog.dismiss()
        
        close_btn.bind(on_release=dismiss_dialog)
        content.add_widget(close_btn)
        
        self._marker_dialog = MDDialog(
            MDDialogHeadlineText(text='Marker Details'),
            MDDialogContentContainer(content, orientation='vertical'),
            MDDialogButtonContainer()
        )
        self._marker_dialog.open()
    
    def go_back(self, *args):
        app = MDApp.get_running_app()
        app.root.current = 'radar'


class BootScreen(MDScreen):
    """Initial boot screen with loading animation."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'boot'
        
        # Main layout
        layout = MDBoxLayout(orientation='vertical', padding=dp(20))
        
        # Spacer
        layout.add_widget(Widget(size_hint_y=0.3))
        
        # Logo/Ghost animation area
        logo_area = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(300),
            spacing=dp(20)
        )
        
        # App name
        app_name = MDLabel(
            text="👻 Ghost Net",
            halign='center',
            font_style='Display',
            role='large',
            size_hint_y=None,
            height=dp(80)
        )
        
        # Tagline
        tagline = MDLabel(
            text="Secure • Offline • Free",
            halign='center',
            theme_text_color='Secondary',
            font_style='Title',
            role='medium',
            size_hint_y=None,
            height=dp(40)
        )
        
        # Loading spinner
        self.spinner = MDSpinner(
            size_hint=(None, None),
            size=(dp(46), dp(46)),
            pos_hint={'center_x': 0.5},
            active=True
        )
        
        # Status label
        self.status_label = MDLabel(
            text="Initializing...",
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='large',
            size_hint_y=None,
            height=dp(30)
        )
        
        logo_area.add_widget(app_name)
        logo_area.add_widget(tagline)
        logo_area.add_widget(self.spinner)
        logo_area.add_widget(self.status_label)
        
        layout.add_widget(logo_area)
        
        # Spacer
        layout.add_widget(Widget(size_hint_y=0.3))
        
        # Version info at bottom
        version_label = MDLabel(
            text="v1.0.0",
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='small',
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(version_label)
        
        self.add_widget(layout)
    
    def update_status(self, text):
        """Update the status label text."""
        self.status_label.text = text


class RadarWidget(Widget):
    """Animated radar visualization for the home screen."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.angle = 0
        
        with self.canvas:
            # Draw radar circles
            Color(0.2, 0.6, 0.8, 0.3)
            self.circle1 = Ellipse(size=(dp(200), dp(200)))
            Color(0.2, 0.6, 0.8, 0.2)
            self.circle2 = Ellipse(size=(dp(150), dp(150)))
            Color(0.2, 0.6, 0.8, 0.1)
            self.circle3 = Ellipse(size=(dp(100), dp(100)))
            
            # Radar sweep line
            Color(0.3, 0.8, 1.0, 0.8)
            self.sweep = Line(points=[], width=2)
        
        self.bind(pos=self.update_radar, size=self.update_radar)
        Clock.schedule_interval(self.animate_sweep, 0.05)
    
    def update_radar(self, *args):
        """Update radar position and size."""
        cx, cy = self.center_x, self.center_y
        
        self.circle1.pos = (cx - dp(100), cy - dp(100))
        self.circle2.pos = (cx - dp(75), cy - dp(75))
        self.circle3.pos = (cx - dp(50), cy - dp(50))
    
    def animate_sweep(self, dt):
        """Animate the radar sweep line."""
        import math
        self.angle = (self.angle + 3) % 360
        rad = math.radians(self.angle)
        
        cx, cy = self.center_x, self.center_y
        end_x = cx + dp(100) * math.cos(rad)
        end_y = cy + dp(100) * math.sin(rad)
        
        self.sweep.points = [cx, cy, end_x, end_y]


class DiagnosticsScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'diagnostics'
        self.diagnostics = get_diagnostics()
        self.telemetry = get_telemetry_logger()
        self.update_scheduled = False
        self.export_status_label = None
        
        layout = MDBoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(50),
            spacing=dp(10)
        )
        
        title = MDLabel(
            text='⚙️ DIAGNOSTICS',
            font_style='Title',
            role='large',
            size_hint_x=0.6
        )
        
        close_btn = MDButton(style='text', size_hint_x=0.2)
        close_btn.add_widget(MDButtonText(text='Close'))
        close_btn.bind(on_release=self.close_diagnostics)
        
        header.add_widget(title)
        header.add_widget(close_btn)
        layout.add_widget(header)
        
        buttons_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
            padding=dp(10)
        )
        
        export_btn = MDButton(style='elevated', size_hint_x=0.5)
        export_btn.add_widget(MDButtonText(text='Export Mission Logs'))
        export_btn.bind(on_release=self.export_mission_logs)
        
        clear_btn = MDButton(style='elevated', size_hint_x=0.5)
        clear_btn.add_widget(MDButtonText(text='Clear Telemetry'))
        clear_btn.bind(on_release=self.clear_telemetry)
        
        buttons_layout.add_widget(export_btn)
        buttons_layout.add_widget(clear_btn)
        layout.add_widget(buttons_layout)
        
        self.export_status_label = MDLabel(
            text='',
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='small',
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(self.export_status_label)
        
        scroll = MDScrollView(size_hint=(1, 1))
        self.diag_box = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(15),
            padding=dp(10)
        )
        scroll.add_widget(self.diag_box)
        layout.add_widget(scroll)
        
        self.add_widget(layout)
    
    def on_enter(self):
        if not self.update_scheduled:
            Clock.schedule_interval(self.refresh_diagnostics, 1.0)
            self.update_scheduled = True
    
    def on_leave(self):
        if self.update_scheduled:
            Clock.unschedule(self.refresh_diagnostics)
            self.update_scheduled = False
    
    def refresh_diagnostics(self, dt=None):
        try:
            snapshot = self.diagnostics.get_diagnostics_snapshot()
            self.diag_box.clear_widgets()
            
            node_status = snapshot['node_status']
            node_section = MDBoxLayout(
                orientation='vertical',
                adaptive_height=True,
                spacing=dp(5)
            )
            node_section.add_widget(MDLabel(
                text='[b]NODE STATUS[/b]',
                markup=True,
                font_style='Body',
                role='large',
                theme_text_color='Hint'
            ))
            node_section.add_widget(MDLabel(
                text=f"IP: {node_status['local_ip']}",
                font_style='Body',
                role='small'
            ))
            node_section.add_widget(MDLabel(
                text=f"MAC: {node_status['local_mac']}",
                font_style='Body',
                role='small'
            ))
            node_section.add_widget(MDLabel(
                text=f"Service: {node_status['service_status']}",
                font_style='Body',
                role='small'
            ))
            node_section.add_widget(MDLabel(
                text=f"Uptime: {node_status['uptime']}",
                font_style='Body',
                role='small'
            ))
            self.diag_box.add_widget(node_section)
            
            routing_table = snapshot['routing_table']
            routing_section = MDBoxLayout(
                orientation='vertical',
                adaptive_height=True,
                spacing=dp(3)
            )
            routing_section.add_widget(MDLabel(
                text='[b]ROUTING TABLE[/b]',
                markup=True,
                font_style='Body',
                role='large',
                theme_text_color='Hint'
            ))
            
            if routing_table:
                for dest, route_info in routing_table.items():
                    if isinstance(route_info, dict):
                        next_hop = route_info.get('next_hop', 'N/A')
                        metric = route_info.get('metric', 'N/A')
                        route_text = f"→ {dest[:8]}... | {next_hop[:8]}... [{metric}]"
                    else:
                        route_text = f"→ {dest[:12]}... {route_info}"
                    
                    routing_section.add_widget(MDLabel(
                        text=route_text,
                        font_style='Body',
                        role='small'
                    ))
            else:
                routing_section.add_widget(MDLabel(
                    text='No routes discovered',
                    font_style='Body',
                    role='small',
                    theme_text_color='Secondary'
                ))
            self.diag_box.add_widget(routing_section)
            
            active_sockets = snapshot['active_sockets']
            socket_section = MDBoxLayout(
                orientation='vertical',
                adaptive_height=True,
                spacing=dp(3)
            )
            socket_section.add_widget(MDLabel(
                text='[b]SOCKET HEALTH[/b]',
                markup=True,
                font_style='Body',
                role='large',
                theme_text_color='Hint'
            ))
            socket_section.add_widget(MDLabel(
                text=f"Active Connections: {len(active_sockets)}",
                font_style='Body',
                role='small'
            ))
            
            for sock in active_sockets[:10]:
                if isinstance(sock, dict):
                    if 'error' in sock:
                        socket_section.add_widget(MDLabel(
                            text=f"Error: {sock['error'][:40]}",
                            font_style='Body',
                            role='small',
                            theme_text_color='Error'
                        ))
                    else:
                        sock_type = sock.get('type', 'UNKNOWN')
                        remote = sock.get('remote', 'N/A')
                        socket_section.add_widget(MDLabel(
                            text=f"[{sock_type}] {remote[:20]}...",
                            font_style='Body',
                            role='small'
                        ))
            
            queue_size = snapshot['message_queue']
            socket_section.add_widget(MDLabel(
                text=f"Message Queue: {queue_size}",
                font_style='Body',
                role='small',
                theme_text_color='Secondary'
            ))
            self.diag_box.add_widget(socket_section)
        
        except Exception as e:
            self.diag_box.clear_widgets()
            self.diag_box.add_widget(MDLabel(
                text=f"Error: {str(e)[:100]}",
                font_style='Body',
                role='small',
                theme_text_color='Error'
            ))
    
    def export_mission_logs(self, instance=None):
        def export_worker():
            try:
                self.export_status_label.text = 'Exporting logs...'
                
                self.telemetry.flush()
                
                log_path = self.telemetry.get_log_path()
                if not os.path.exists(log_path):
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', 'No logs to export'), 0)
                    return
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                enc_filename = f'mission_telemetry_{timestamp}.enc'
                temp_enc_path = os.path.join(os.path.dirname(log_path), enc_filename)
                
                if not encrypt_telemetry_file(log_path, temp_enc_path):
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', 'Encryption failed'), 0)
                    return
                
                final_path = copy_to_downloads(temp_enc_path, enc_filename)
                
                if final_path:
                    try:
                        os.remove(temp_enc_path)
                    except:
                        pass
                    
                    status_msg = f'✓ Exported to Downloads: {enc_filename}'
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', status_msg), 0)
                else:
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', 'Export failed'), 0)
            
            except Exception as e:
                print(f"[DiagnosticsScreen] Export error: {e}")
                error_msg = f'Error: {str(e)[:40]}'
                Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', error_msg), 0)
        
        export_thread = threading.Thread(target=export_worker, daemon=True)
        export_thread.start()
    
    def clear_telemetry(self, instance=None):
        def clear_worker():
            try:
                self.telemetry.clear_logs()
                Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', '✓ Telemetry cleared'), 0)
            except Exception as e:
                print(f"[DiagnosticsScreen] Clear error: {e}")
                Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', f'Clear error: {str(e)[:30]}'), 0)
        
        clear_thread = threading.Thread(target=clear_worker, daemon=True)
        clear_thread.start()
    
    def close_diagnostics(self, instance=None):
        app = MDApp.get_running_app()
        if app and app.root:
            app.root.current = 'radar'


class RadarScreen(MDScreen):
    """Home screen showing discovered peers with radar animation and network info."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'radar'
        self.sos_long_press_time = 0
        self.sos_button = None
        self.gps_manager = get_gps_manager()
        self.alert_dialog = None
        self.title_tap_times = []
        self.title_widget = None
        
        layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))
        
        # Header with title and settings button
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(60),
            spacing=dp(10)
        )
        
        title = MDLabel(
            text="👻 Ghost Net",
            halign='center',
            font_style='Display',
            role='small',
            size_hint_x=0.6
        )
        title.bind(on_touch_down=self.on_title_tap)
        self.title_widget = title
        
        # Network status badge
        self.network_badge = MDLabel(
            text="📶 Detecting...",
            halign='right',
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_x=0.2
        )
        
        settings_btn = MDIconButton(
            icon='cog',
            size_hint_x=0.1
        )
        settings_btn.bind(on_release=self.open_settings)
        
        map_btn = MDIconButton(
            icon='map',
            size_hint_x=0.1
        )
        map_btn.bind(on_release=self.open_map)
        
        header.add_widget(title)
        header.add_widget(self.network_badge)
        header.add_widget(map_btn)
        header.add_widget(settings_btn)
        layout.add_widget(header)
        
        self.radar = RadarWidget(size_hint=(1, 0.4))
        layout.add_widget(self.radar)
        
        self.status_label = MDLabel(
            text="Scanning for peers...",
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='large'
        )
        layout.add_widget(self.status_label)
        
        tabs_layout = MDBoxLayout(
            orientation='vertical',
            size_hint=(1, 1),
            spacing=dp(5)
        )
        
        tab_buttons_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(5),
            padding=dp(5)
        )
        
        self.active_tab_btn = MDButton(
            style='elevated',
            size_hint_x=0.5
        )
        self.active_tab_btn.add_widget(MDButtonText(text="Active Peers"))
        self.active_tab_btn.bind(on_release=self.show_active_peers)
        
        self.saved_tab_btn = MDButton(
            style='text',
            size_hint_x=0.5
        )
        self.saved_tab_btn.add_widget(MDButtonText(text="Saved Peers"))
        self.saved_tab_btn.bind(on_release=self.show_saved_peers)
        
        tab_buttons_layout.add_widget(self.active_tab_btn)
        tab_buttons_layout.add_widget(self.saved_tab_btn)
        tabs_layout.add_widget(tab_buttons_layout)
        
        self.peers_scroll = MDScrollView(size_hint=(1, 1))
        self.peers_list = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(5)
        )
        self.peers_scroll.add_widget(self.peers_list)
        
        self.saved_peers_scroll = MDScrollView(size_hint=(1, 1))
        self.saved_peers_list = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(5)
        )
        self.saved_peers_scroll.add_widget(self.saved_peers_list)
        
        self.current_tab = 'active'
        self.peers_scroll.opacity = 1
        self.saved_peers_scroll.opacity = 0
        
        tabs_layout.add_widget(self.peers_scroll)
        tabs_layout.add_widget(self.saved_peers_scroll)
        
        layout.add_widget(tabs_layout)
        
        if MDFloatingActionButton:
            self.sos_button = MDFloatingActionButton(
                icon='alert-circle',
                theme_bg_color='Custom',
                md_bg_color=(1.0, 0.2, 0.2, 1),
                size_hint=(None, None),
                size=(dp(64), dp(64)),
                pos_hint={'right': 0.98, 'top': 0.98}
            )
            self.sos_button.bind(on_touch_down=self.on_sos_touch_down)
            self.sos_button.bind(on_touch_up=self.on_sos_touch_up)
            layout.add_widget(self.sos_button)
        
        self.add_widget(layout)
    
    def update_network_status(self, network_info):
        """Update network status badge."""
        try:
            net_type = network_info.get('type', 'unknown')
            ip = network_info.get('ip', 'N/A')
            
            # Icon mapping
            icons = {
                'wifi': '📶',
                'hotspot': '📡',
                'cellular': '📱',
                'ethernet': '🔌',
                'private': '🔒',
                'unknown': '❓'
            }
            
            icon = icons.get(net_type, '❓')
            self.network_badge.text = f"{icon} {net_type.capitalize()}"
        except Exception as e:
            print(f"[RadarScreen] Error updating network status: {e}")
            self.network_badge.text = "❓ Unknown"
    
    def update_peers(self, peers_dict):
        """Update the peers list (called from main thread via Clock)."""
        self.peers_list.clear_widgets()
        
        if not peers_dict:
            self.status_label.text = "No peers found. Waiting..."
            return
        
        self.status_label.text = f"Found {len(peers_dict)} peer(s)"
        
        for ip, info in peers_dict.items():
            username = info['username']
            visible_peers = info.get('visible_peers', [])
            peer_id = info.get('peer_id', ip)
            
            item_height = dp(60)
            route_text = None
            
            if visible_peers and len(visible_peers) > 0:
                item_height = dp(80)
                if len(visible_peers) == 1:
                    route_text = f"Route: via {visible_peers[0][:8]}... (1 hop)"
                else:
                    route_text = f"Route: via {len(visible_peers)} peers"
            
            item = MDCard(
                style='elevated',
                padding=dp(10),
                size_hint_y=None,
                height=item_height,
                md_bg_color=(0.1, 0.1, 0.15, 1)
            )
            
            item_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10))
            
            peer_info = MDBoxLayout(orientation='vertical', size_hint_x=0.8)
            peer_name = MDLabel(
                text=username,
                font_style='Title',
                role='medium',
                theme_text_color='Primary'
            )
            peer_ip = MDLabel(
                text=ip,
                font_style='Body',
                role='small',
                theme_text_color='Secondary'
            )
            peer_info.add_widget(peer_name)
            peer_info.add_widget(peer_ip)
            
            if route_text:
                route_label = MDLabel(
                    text=route_text,
                    font_style='Body',
                    role='small',
                    theme_text_color='Secondary'
                )
                peer_info.add_widget(route_label)
            
            chat_btn = MDButton(
                style='text',
                size_hint_x=0.2
            )
            chat_btn.add_widget(MDButtonText(text="Chat"))
            chat_btn.bind(on_release=lambda x, ip=ip, name=username: self.open_chat(ip, name))
            
            item_layout.add_widget(peer_info)
            item_layout.add_widget(chat_btn)
            item.add_widget(item_layout)
            
            self.peers_list.add_widget(item)
    
    def open_chat(self, peer_ip, peer_name):
        """Navigate to chat screen with selected peer."""
        app = MDApp.get_running_app()
        chat_screen = app.root.get_screen('chat')
        chat_screen.set_peer(peer_ip, peer_name)
        app.root.current = 'chat'
    
    def on_title_tap(self, instance, touch):
        if not self.collide_point(*touch.pos):
            return
        
        current_time = time.time()
        self.title_tap_times = [t for t in self.title_tap_times if current_time - t < 3.0]
        self.title_tap_times.append(current_time)
        
        if len(self.title_tap_times) >= 7:
            self.title_tap_times = []
            self.unlock_diagnostics()
    
    def unlock_diagnostics(self):
        app = MDApp.get_running_app()
        if app and app.root:
            try:
                diag_screen = app.root.get_screen('diagnostics')
            except:
                diag_screen = None
            
            if not diag_screen:
                diag_screen = DiagnosticsScreen()
                app.root.add_widget(diag_screen)
            
            app.root.current = 'diagnostics'
    
    def open_settings(self, *args):
        app = MDApp.get_running_app()
        app.root.current = 'settings'
    
    def open_map(self, *args):
        """Navigate to tactical map screen."""
        app = MDApp.get_running_app()
        if MAPVIEW_AVAILABLE:
            app.root.current = 'map'
        else:
            print("[RadarScreen] MapView not available")
    
    def show_active_peers(self, *args):
        """Switch to active peers tab."""
        self.current_tab = 'active'
        self.peers_scroll.opacity = 1
        self.saved_peers_scroll.opacity = 0
        
        try:
            self.active_tab_btn.style = 'elevated'
            self.saved_tab_btn.style = 'text'
        except:
            pass
    
    def show_saved_peers(self, *args):
        """Switch to saved peers tab and load from database."""
        self.current_tab = 'saved'
        self.peers_scroll.opacity = 0
        self.saved_peers_scroll.opacity = 1
        
        try:
            self.active_tab_btn.style = 'text'
            self.saved_tab_btn.style = 'elevated'
        except:
            pass
        
        self.load_saved_peers()
    
    def load_saved_peers(self):
        """Load and display saved peers from persistence database."""
        app = MDApp.get_running_app()
        
        if not app or not hasattr(app, 'persistence_db') or not app.persistence_db:
            self.saved_peers_list.clear_widgets()
            no_peers_label = MDLabel(
                text="No saved peers database",
                halign='center',
                theme_text_color='Secondary'
            )
            self.saved_peers_list.add_widget(no_peers_label)
            return
        
        try:
            saved_peers = app.persistence_db.get_all_peers()
            
            self.saved_peers_list.clear_widgets()
            
            if not saved_peers:
                no_peers_label = MDLabel(
                    text="No saved peers yet. Chat with someone to save them!",
                    halign='center',
                    theme_text_color='Secondary',
                    size_hint_y=None,
                    height=dp(40)
                )
                self.saved_peers_list.add_widget(no_peers_label)
                return
            
            for peer in saved_peers:
                peer_id = peer['peer_id']
                device_name = peer['device_name']
                discovery_type = peer.get('discovery_type', 'unknown')
                last_seen_ts = peer['last_seen']
                
                last_seen_dt = datetime.fromtimestamp(last_seen_ts)
                last_seen_str = last_seen_dt.strftime("%a %H:%M")
                
                item = MDCard(
                    style='elevated',
                    padding=dp(10),
                    size_hint_y=None,
                    height=dp(70),
                    md_bg_color=(0.1, 0.1, 0.15, 1)
                )
                
                item_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10))
                
                peer_info = MDBoxLayout(orientation='vertical', size_hint_x=0.75)
                peer_name = MDLabel(
                    text=f"{device_name}",
                    font_style='Title',
                    role='medium',
                    theme_text_color='Primary'
                )
                peer_meta = MDLabel(
                    text=f"{peer_id} • {discovery_type}",
                    font_style='Body',
                    role='small',
                    theme_text_color='Secondary'
                )
                peer_time = MDLabel(
                    text=f"Last: {last_seen_str}",
                    font_style='Body',
                    role='small',
                    theme_text_color='Secondary'
                )
                peer_info.add_widget(peer_name)
                peer_info.add_widget(peer_meta)
                peer_info.add_widget(peer_time)
                
                chat_btn = MDButton(
                    style='text',
                    size_hint_x=0.25
                )
                chat_btn.add_widget(MDButtonText(text="Connect"))
                chat_btn.bind(on_release=lambda x, ip=peer_id, name=device_name: self.open_chat(ip, name))
                
                item_layout.add_widget(peer_info)
                item_layout.add_widget(chat_btn)
                item.add_widget(item_layout)
                
                self.saved_peers_list.add_widget(item)
        
        except Exception as e:
            print(f"[RadarScreen] Error loading saved peers: {e}")
            self.saved_peers_list.clear_widgets()
            error_label = MDLabel(
                text=f"Error loading saved peers: {str(e)[:40]}",
                halign='center',
                theme_text_color='Secondary',
                size_hint_y=None,
                height=dp(40)
            )
            self.saved_peers_list.add_widget(error_label)
    
    def on_sos_touch_down(self, widget, touch):
        if not widget.collide_point(*touch.pos):
            return False
        self.sos_long_press_time = time.time()
        return True
    
    def on_sos_touch_up(self, widget, touch):
        if not self.sos_long_press_time:
            return False
        
        press_duration = time.time() - self.sos_long_press_time
        self.sos_long_press_time = 0
        
        if press_duration >= 1.5:
            self.trigger_sos()
        
        return True
    
    def trigger_sos(self):
        app = MDApp.get_running_app()
        if not app or not app.engine:
            print("[RadarScreen] Engine not available for SOS")
            return
        
        lat, lon = self.gps_manager.get_coordinates()
        
        def broadcast_worker():
            app.engine.broadcast_sos(lat, lon, "EMERGENCY SOS")
        
        threading.Thread(target=broadcast_worker, daemon=True).start()
    
    def show_sos_alert(self, sender_name: str, latitude: float, longitude: float, message: str, sos_id: str):
        try:
            app = MDApp.get_running_app()
            audio_mgr = get_audio_manager()
            
            audio_mgr.on_playback_complete = lambda: None
            threading.Thread(
                target=lambda: self._play_alert_tone(audio_mgr),
                daemon=True
            ).start()
            
            content = MDBoxLayout(
                orientation='vertical',
                spacing=dp(15),
                padding=dp(20),
                adaptive_height=True
            )
            
            title_label = MDLabel(
                text=f"🚨 EMERGENCY ALERT",
                font_style='Title',
                role='large',
                theme_text_color='Error',
                size_hint_y=None,
                height=dp(40)
            )
            
            sender_label = MDLabel(
                text=f"From: {sender_name}",
                font_style='Body',
                role='large',
                size_hint_y=None,
                height=dp(30)
            )
            
            message_label = MDLabel(
                text=message,
                font_style='Body',
                role='medium',
                size_hint_y=None,
                height=dp(30)
            )
            
            coords_label = MDLabel(
                text=f"Location: {latitude:.4f}, {longitude:.4f}",
                font_style='Body',
                role='small',
                theme_text_color='Secondary',
                size_hint_y=None,
                height=dp(30)
            )
            
            content.add_widget(title_label)
            content.add_widget(sender_label)
            content.add_widget(message_label)
            content.add_widget(coords_label)
            
            close_btn = MDButton(
                MDButtonText(text="Dismiss"),
                style='elevated',
                theme_bg_color='Custom',
                md_bg_color=(1.0, 0.2, 0.2, 1)
            )
            
            def on_dismiss(*args):
                audio_mgr.stop_playback()
                if self.alert_dialog:
                    self.alert_dialog.dismiss()
            
            close_btn.bind(on_release=on_dismiss)
            content.add_widget(close_btn)
            
            self.alert_dialog = MDDialog(
                MDDialogHeadlineText(text="⚠️ SOS RECEIVED"),
                MDDialogContentContainer(content, orientation="vertical"),
                MDDialogButtonContainer()
            )
            self.alert_dialog.open()
        
        except Exception as e:
            print(f"[RadarScreen] SOS alert error: {e}")
    
    def _play_alert_tone(self, audio_mgr):
        try:
            for i in range(10):
                if not hasattr(self, 'alert_dialog') or not self.alert_dialog:
                    break
                
                import tempfile
                alert_dir = self.gps_manager.recording_dir if hasattr(self.gps_manager, 'recording_dir') else tempfile.gettempdir()
                alert_file = os.path.join(alert_dir, 'alert_tone.wav')
                with open(alert_file, 'wb') as f:
                    f.write(b'ALERT_TONE_DATA')
                
                audio_mgr.play_audio(alert_file)
                time.sleep(0.5)
        except Exception as e:
            print(f"[RadarScreen] Alert tone error: {e}")


class MessageBubble(MDCard):
    """Custom message bubble widget for text messages with adaptive height."""
    
    def __init__(self, message, timestamp, is_sent=False, **kwargs):
        super().__init__(**kwargs)
        
        self.style = 'elevated'
        self.adaptive_height = True  # ✅ Adapt to content
        self.size_hint_y = None
        self.minimum_height = dp(60)  # Minimum height for small messages
        self.padding = dp(10)
        self.spacing = dp(5)
        
        # Color coding: sent (blue) vs received (grey)
        if is_sent:
            self.md_bg_color = (0.2, 0.4, 0.8, 1)
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.75  # Slightly wider for better text flow
        else:
            self.md_bg_color = (0.3, 0.3, 0.3, 1)
            self.pos_hint = {'x': 0.05}
            self.size_hint_x = 0.75
        
        layout = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(5),
            size_hint_y=None
        )
        
        msg_label = MDLabel(
            text=message,
            font_style='Body',
            role='large',
            theme_text_color='Primary',
            adaptive_height=True,  # ✅ Multi-line support
            size_hint_y=None
        )
        # Bind text size to label height for multi-line text
        msg_label.bind(texture_size=msg_label.setter('size'))
        
        time_label = MDLabel(
            text=timestamp,
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            halign='right',
            size_hint_y=None,
            height=dp(20)
        )
        
        layout.add_widget(msg_label)
        layout.add_widget(time_label)
        layout.bind(size=self.setter('height'))  # Bind layout height to card height
        
        self.add_widget(layout)


class FileBubble(MDCard):
    """Custom file bubble widget for file transfers with progress bar."""
    
    def __init__(self, filename, filepath, timestamp, is_sent=False, **kwargs):
        super().__init__(**kwargs)
        
        self.filename = filename
        self.filepath = filepath
        self.is_sent = is_sent
        self.progress = 0.0
        
        self.style = 'elevated'
        self.adaptive_height = True
        self.size_hint_y = None
        self.minimum_height = dp(120)
        self.padding = dp(10)
        
        if is_sent:
            self.md_bg_color = (0.2, 0.4, 0.8, 1)
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.75
        else:
            self.md_bg_color = (0.3, 0.3, 0.3, 1)
            self.pos_hint = {'x': 0.05}
            self.size_hint_x = 0.75
        
        main_layout = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(5),
            size_hint_y=None
        )
        
        file_row = MDBoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(40))
        
        icon = MDIconButton(
            icon=self._get_file_icon(filename),
            theme_icon_color='Custom',
            icon_color=(1, 1, 1, 1)
        )
        
        file_info = MDBoxLayout(orientation='vertical', spacing=dp(2))
        
        name_label = MDLabel(
            text=filename,
            font_style='Body',
            role='large',
            theme_text_color='Primary'
        )
        
        size_text = ""
        if filepath and os.path.exists(filepath):
            size_bytes = os.path.getsize(filepath)
            size_text = self._format_file_size(size_bytes)
        
        size_label = MDLabel(
            text=size_text,
            font_style='Body',
            role='small',
            theme_text_color='Secondary'
        )
        
        file_info.add_widget(name_label)
        file_info.add_widget(size_label)
        
        file_row.add_widget(icon)
        file_row.add_widget(file_info)
        
        self.progress_bar = None
        if MDProgressBar:
            self.progress_bar = MDProgressBar(
                value=0,
                size_hint_y=None,
                height=dp(4)
            )
        
        button_row = MDBoxLayout(orientation='horizontal', spacing=dp(5), size_hint_y=None, height=dp(30))
        
        if not is_sent and filepath and os.path.exists(filepath):
            open_btn = MDButton(style='text', size_hint_x=0.5)
            open_btn.add_widget(MDButtonText(text="Open"))
            open_btn.bind(on_release=lambda x: self.open_file())
            button_row.add_widget(open_btn)
        
        time_label = MDLabel(
            text=timestamp,
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            halign='right',
            size_hint_x=0.5
        )
        button_row.add_widget(time_label)
        
        main_layout.add_widget(file_row)
        if self.progress_bar:
            main_layout.add_widget(self.progress_bar)
        main_layout.add_widget(button_row)
        main_layout.bind(size=self.setter('height'))
        
        self.add_widget(main_layout)
    
    def update_progress(self, bytes_sent, total_size):
        """Update progress bar (thread-safe via Clock)."""
        if not self.progress_bar or total_size == 0:
            return
        
        progress_percent = (bytes_sent / total_size) * 100
        Clock.schedule_once(
            lambda dt: setattr(self.progress_bar, 'value', progress_percent),
            0
        )
    
    def _get_file_icon(self, filename):
        """Get appropriate icon based on file extension."""
        ext = os.path.splitext(filename)[1].lower()
        
        icon_map = {
            '.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.gif': 'image',
            '.pdf': 'file-pdf-box', '.doc': 'file-word', '.docx': 'file-word',
            '.mp4': 'video', '.avi': 'video', '.mov': 'video',
            '.mp3': 'music', '.wav': 'music',
            '.zip': 'folder-zip', '.rar': 'folder-zip',
        }
        
        return icon_map.get(ext, 'file')
    
    def _format_file_size(self, bytes):
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.1f} TB"
    
    def open_file(self):
        """Open the file with default system application."""
        if not self.filepath or not os.path.exists(self.filepath):
            print(f"[FileBubble] File not found: {self.filepath}")
            return
        
        try:
            if platform.system() == 'Windows':
                os.startfile(self.filepath)
            elif platform.system() == 'Darwin':  # macOS
                os.system(f'open "{self.filepath}"')
            else:  # Linux and Android
                os.system(f'xdg-open "{self.filepath}"')
            print(f"[FileBubble] Opened file: {self.filepath}")
        except Exception as e:
            print(f"[FileBubble] Error opening file: {e}")


class AudioBubble(MDCard):
    def __init__(self, filename, filepath, timestamp, is_sent=False, **kwargs):
        super().__init__(**kwargs)
        
        self.filename = filename
        self.filepath = filepath
        self.is_sent = is_sent
        self.is_playing = False
        self.playback_progress = 0.0
        
        self.style = 'elevated'
        self.adaptive_height = True
        self.size_hint_y = None
        self.minimum_height = dp(100)
        self.padding = dp(10)
        
        if is_sent:
            self.md_bg_color = (0.2, 0.4, 0.8, 1)
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.75
        else:
            self.md_bg_color = (0.3, 0.3, 0.3, 1)
            self.pos_hint = {'x': 0.05}
            self.size_hint_x = 0.75
        
        main_layout = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(5),
            size_hint_y=None
        )
        
        header_row = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(10),
            size_hint_y=None,
            height=dp(50)
        )
        
        audio_icon = MDIconButton(
            icon='microphone',
            theme_icon_color='Custom',
            icon_color=(1, 1, 1, 1),
            size_hint_x=None,
            width=dp(48)
        )
        
        info_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(2),
            size_hint_x=0.7
        )
        
        name_label = MDLabel(
            text=filename,
            font_style='Body',
            role='large',
            theme_text_color='Primary'
        )
        
        time_label = MDLabel(
            text=timestamp,
            font_style='Body',
            role='small',
            theme_text_color='Secondary'
        )
        
        info_layout.add_widget(name_label)
        info_layout.add_widget(time_label)
        
        header_row.add_widget(audio_icon)
        header_row.add_widget(info_layout)
        
        play_btn = MDButton(
            style='text',
            size_hint_x=0.3
        )
        self.play_btn_text = MDButtonText(text="▶ Play")
        play_btn.add_widget(self.play_btn_text)
        play_btn.bind(on_release=self.toggle_playback)
        
        header_row.add_widget(play_btn)
        
        self.progress_bar = None
        if MDProgressBar:
            self.progress_bar = MDProgressBar(
                value=0,
                size_hint_y=None,
                height=dp(4)
            )
        
        main_layout.add_widget(header_row)
        if self.progress_bar:
            main_layout.add_widget(self.progress_bar)
        
        main_layout.bind(size=self.setter('height'))
        
        self.add_widget(main_layout)
        
        self.audio_manager = get_audio_manager()
        self.audio_manager.on_playback_progress = self._update_progress
        self.audio_manager.on_playback_complete = self._on_playback_complete
    
    def toggle_playback(self, *args):
        if self.is_playing:
            self.audio_manager.stop_playback()
            self.is_playing = False
            self.play_btn_text.text = "▶ Play"
        else:
            if self.filepath and os.path.exists(self.filepath):
                success = self.audio_manager.play_audio(self.filepath)
                if success:
                    self.is_playing = True
                    self.play_btn_text.text = "⏸ Stop"
            else:
                print(f"[AudioBubble] File not found: {self.filepath}")
    
    def _update_progress(self, progress):
        self.playback_progress = progress
        if self.progress_bar:
            self.progress_bar.value = progress
    
    def _on_playback_complete(self):
        self.is_playing = False
        self.play_btn_text.text = "▶ Play"
        if self.progress_bar:
            self.progress_bar.value = 0


class ChatScreen(MDScreen):
    """Chat interface for messaging with a specific peer with keyboard awareness."""
    
    peer_ip = StringProperty('')
    peer_name = StringProperty('Unknown')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'chat'
        self.file_manager = None
        self.keyboard_height = 0
        self.received_file_bubbles = {}
        self.ttl_state = 0
        self.ttl_values = [None, 30, 300, 3600]
        self.ttl_labels = ["Off", "30s", "5m", "1h"]
        self.message_expiry_timers = {}
        self.is_recording = False
        self.audio_manager = get_audio_manager()
        self.mic_btn = None
        
        # Main layout
        layout = MDBoxLayout(orientation='vertical', spacing=dp(10))
        
        header = MDBoxLayout(
            size_hint_y=None,
            height=dp(60),
            padding=dp(10),
            spacing=dp(10),
            md_bg_color=(0.1, 0.1, 0.2, 1)
        )
        
        back_btn = MDIconButton(icon='arrow-left')
        back_btn.bind(on_release=self.go_back)
        
        self.peer_label = MDLabel(
            text="Select a peer",
            font_style='Title',
            role='large',
            theme_text_color='Primary'
        )
        
        self.ttl_btn = MDIconButton(
            icon='clock-outline',
            theme_icon_color='Custom',
            icon_color=(0.5, 0.5, 0.5, 1)
        )
        self.ttl_btn.bind(on_release=self.toggle_ttl)
        
        header.add_widget(back_btn)
        header.add_widget(self.peer_label)
        header.add_widget(self.ttl_btn)
        layout.add_widget(header)
        
        # Messages area with improved scrolling
        self.messages_scroll = MDScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width=dp(10),
            scroll_type=['bars', 'content']
        )
        self.messages_list = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10),
            size_hint_y=None
        )
        self.messages_list.bind(minimum_height=self.messages_list.setter('height'))
        self.messages_scroll.add_widget(self.messages_list)
        layout.add_widget(self.messages_scroll)
        
        # Input area with keyboard awareness
        self.input_layout = MDBoxLayout(
            orientation='horizontal',
            adaptive_height=True,
            minimum_height=dp(60),
            padding=dp(10),
            spacing=dp(10),
            size_hint_y=None,
            pos_hint={'x': 0, 'bottom': 0}
        )
        
        # Attachment button
        attach_btn = MDIconButton(
            icon='paperclip',
            size_hint_x=None,
            width=dp(48)
        )
        attach_btn.bind(on_release=self.open_file_picker)
        
        self.message_input = MDTextField(
            mode='outlined',
            size_hint_x=0.55,
            size_hint_y=None,
            height=dp(50)
        )
        self.message_input.add_widget(MDTextFieldHintText(text="Type a message..."))
        
        self.mic_btn = MDIconButton(
            icon='microphone',
            theme_icon_color='Custom',
            icon_color=(0.5, 0.5, 0.5, 1),
            size_hint_x=None,
            width=dp(48)
        )
        self.mic_btn.bind(on_touch_down=self.on_mic_touch_down)
        self.mic_btn.bind(on_touch_up=self.on_mic_touch_up)
        
        send_btn = MDButton(
            style='elevated',
            size_hint_x=0.2,
            size_hint_y=None,
            height=dp(50)
        )
        send_btn.add_widget(MDButtonText(text="Send"))
        send_btn.bind(on_release=self.send_message)
        
        self.input_layout.add_widget(attach_btn)
        self.input_layout.add_widget(self.message_input)
        self.input_layout.add_widget(self.mic_btn)
        self.input_layout.add_widget(send_btn)
        layout.add_widget(self.input_layout)
        
        self.add_widget(layout)
        
        # Bind keyboard events for Android
        Window.bind(keyboard_height=self.on_keyboard_height)
        Window.bind(on_keyboard=self.on_keyboard_event)
    
    def on_keyboard_height(self, instance, height):
        """Handle keyboard height changes on Android."""
        self.keyboard_height = height
        
        if height > 0:
            # Keyboard is visible - scroll to bottom to show input
            Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)
        else:
            # Keyboard is hidden
            pass
    
    def on_keyboard_event(self, instance, key, scancode, codepoint, modifier):
        """Handle keyboard events."""
        if scancode == 66:  # Enter key
            # Only send if in message input
            if self.message_input.focus:
                self.send_message()
                return True
        return False
    
    def _scroll_to_bottom(self):
        """Scroll messages to the bottom."""
        try:
            self.messages_scroll.scroll_y = 0
        except Exception as e:
            print(f"[ChatScreen] Error scrolling: {e}")
    
    def set_peer(self, peer_ip, peer_name):
        """Set the current chat peer and load history."""
        self.peer_ip = peer_ip
        self.peer_name = peer_name
        self.peer_label.text = f"💬 {peer_name}"
        
        # Clear previous messages
        self.messages_list.clear_widgets()
        
        # Load chat history from database
        self.load_history()
    
    def load_history(self):
        """Load chat history from database."""
        app = MDApp.get_running_app()
        
        if not self.peer_ip:
            print("[ChatScreen] No peer IP set")
            return
        
        messages = []
        if app and hasattr(app, 'persistence_db') and app.persistence_db:
            try:
                messages = app.persistence_db.get_messages_for_peer(self.peer_ip, limit=100)
            except Exception as e:
                print(f"[ChatScreen] Error loading from persistence DB: {e}")
        
        if not messages and app and app.engine and app.engine.db_manager:
            try:
                messages = app.engine.db_manager.get_history(self.peer_ip, limit=100)
            except Exception as e:
                print(f"[ChatScreen] Error loading from storage DB: {e}")
        
        if not messages:
            print(f"[ChatScreen] No message history found for {self.peer_ip}")
            return
        
        print(f"[ChatScreen] Loading {len(messages)} messages from history")
        
        try:
            for msg in messages:
                if 'sender_type' in msg:
                    is_sent = (msg['sender_type'] == 'me')
                else:
                    is_sent = (msg.get('sender') == 'ME')
                
                dt = datetime.fromtimestamp(msg['timestamp'])
                timestamp = dt.strftime("%H:%M:%S")
                
                if msg.get('content_type') == 'text' or msg.get('message_type') == 'TEXT':
                    bubble = MessageBubble(msg['content'], timestamp, is_sent=is_sent)
                    self.messages_list.add_widget(bubble)
                elif msg.get('content_type') == 'file' or msg.get('message_type') == 'FILE':
                    filename = msg['content']
                    # DatabaseManager uses 'file_path'; PersistenceDatabase has no filepath
                    filepath = msg.get('file_path') or msg.get('filepath')
                    
                    audio_exts = ['.m4a', '.amr', '.wav', '.mp3', '.ogg', '.aac']
                    is_audio = any(filename.lower().endswith(ext) for ext in audio_exts)
                    
                    if is_audio:
                        bubble = AudioBubble(filename, filepath, timestamp, is_sent=is_sent)
                    else:
                        bubble = FileBubble(filename, filepath, timestamp, is_sent=is_sent)
                    
                    self.messages_list.add_widget(bubble)
            
            Clock.schedule_once(lambda dt: setattr(
                self.messages_scroll, 'scroll_y', 0
            ), 0.1)
            
        except Exception as e:
            print(f"[ChatScreen] Error rendering history: {e}")
    
    def send_message(self, *args):
        """Send a message to the current peer."""
        message_text = self.message_input.text.strip()
        
        if not message_text or not self.peer_ip:
            return
        
        app = MDApp.get_running_app()
        
        if not app or not app.engine:
            print("[ChatScreen] Engine not available")
            return
        
        current_ttl = self.ttl_values[self.ttl_state]
        success = app.engine.send_message(self.peer_ip, message_text, ttl=current_ttl)
        
        if success:
            timestamp = datetime.now().strftime("%H:%M:%S")
            bubble = MessageBubble(message_text, timestamp, is_sent=True)
            self.messages_list.add_widget(bubble)
            
            if current_ttl:
                expires_at = time.time() + current_ttl
                self._schedule_bubble_expiry(bubble, expires_at)
            
            self.message_input.text = ''
            
            Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)
    
    def add_received_message(self, sender_ip, message_text, timestamp, expires_at=None):
        if sender_ip == self.peer_ip:
            bubble = MessageBubble(message_text, timestamp, is_sent=False)
            self.messages_list.add_widget(bubble)
            
            if expires_at:
                self._schedule_bubble_expiry(bubble, expires_at)
            
            Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)
    
    def open_file_picker(self, *args):
        """Open native file picker with fallback to MDFileManager."""
        try:
            file_picker = get_file_picker()
            
            if platform.system() == 'Android' and hasattr(file_picker, 'pick_file'):
                file_path = file_picker.pick_file()
                if file_path:
                    self.select_file(file_path)
            else:
                if not self.file_manager:
                    self.file_manager = MDFileManager(
                        exit_manager=self.exit_file_manager,
                        select_path=self.select_file
                    )
                
                start_path = os.path.expanduser("~")
                
                if platform.system() == 'Android':
                    candidate_paths = [
                        '/storage/emulated/0/',
                        os.path.join(os.path.expanduser("~"), "Documents"),
                        os.path.join(os.path.expanduser("~"), "Downloads"),
                        os.path.expanduser("~"),
                    ]
                    
                    for path in candidate_paths:
                        if os.path.exists(path) and os.path.isdir(path):
                            start_path = path
                            break
                
                try:
                    self.file_manager.show(start_path)
                except Exception as e:
                    print(f"[ChatScreen] File manager error: {e}, trying home directory")
                    try:
                        self.file_manager.show(os.path.expanduser("~"))
                    except Exception as e2:
                        print(f"[ChatScreen] File manager failed: {e2}")
        except Exception as e:
            print(f"[ChatScreen] File picker error: {e}")
    
    def exit_file_manager(self, *args):
        """Close the file manager."""
        if self.file_manager:
            self.file_manager.close()
    
    def select_file(self, path):
        """Handle file selection with progress tracking."""
        self.exit_file_manager()
        
        if not os.path.isfile(path):
            print(f"[ChatScreen] Not a file: {path}")
            return
        
        if not self.peer_ip:
            print(f"[ChatScreen] No peer selected")
            return
        
        filename = os.path.basename(path)
        filesize = os.path.getsize(path)
        
        print(f"[ChatScreen] Sending file: {filename} ({filesize} bytes)")
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        bubble = FileBubble(filename, path, timestamp, is_sent=True)
        self.messages_list.add_widget(bubble)
        
        def progress_callback(bytes_sent, total_size):
            if bubble and hasattr(bubble, 'update_progress'):
                bubble.update_progress(bytes_sent, total_size)
        
        app = MDApp.get_running_app()
        if not app or not app.engine:
            print("[ChatScreen] Engine not available")
            return
        
        app.engine.send_file(self.peer_ip, path, progress_callback=progress_callback)
        
        Clock.schedule_once(lambda dt: setattr(
            self.messages_scroll, 'scroll_y', 0
        ), 0.1)
    
    def add_received_file(self, sender_ip, filename, filepath, timestamp):
        """Add a received file to the chat (called from main thread)."""
        if sender_ip == self.peer_ip:
            audio_exts = ['.m4a', '.amr', '.wav', '.mp3', '.ogg', '.aac']
            is_audio = any(filename.lower().endswith(ext) for ext in audio_exts)
            
            if is_audio:
                bubble = AudioBubble(filename, filepath, timestamp, is_sent=False)
            else:
                bubble = FileBubble(filename, filepath, timestamp, is_sent=False)
            
            self.received_file_bubbles[filepath] = bubble
            self.messages_list.add_widget(bubble)
            
            Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)
    
    def update_received_file_progress(self, filepath, bytes_received, total_size):
        """Update progress for incoming file (called from background thread)."""
        if filepath in self.received_file_bubbles:
            bubble = self.received_file_bubbles[filepath]
            if bubble and hasattr(bubble, 'update_progress'):
                bubble.update_progress(bytes_received, total_size)
    
    def toggle_ttl(self, *args):
        self.ttl_state = (self.ttl_state + 1) % len(self.ttl_values)
        label = self.ttl_labels[self.ttl_state]
        
        if self.ttl_state == 0:
            self.ttl_btn.icon_color = (0.5, 0.5, 0.5, 1)
        else:
            self.ttl_btn.icon_color = (1.0, 0.84, 0.0, 1)
        
        print(f"[ChatScreen] TTL set to {label}")
    
    def _schedule_bubble_expiry(self, bubble, expires_at):
        current_time = time.time()
        time_until_expiry = expires_at - current_time
        
        if time_until_expiry > 0:
            def remove_bubble():
                try:
                    if bubble in self.messages_list.children:
                        self.messages_list.remove_widget(bubble)
                        print("[ChatScreen] Expired message removed from UI")
                except:
                    pass
            
            Clock.schedule_once(lambda dt: remove_bubble(), time_until_expiry)
    
    def on_mic_touch_down(self, widget, touch):
        if not widget.collide_point(*touch.pos):
            return False
        
        if self.is_recording:
            return False
        
        success = self.audio_manager.start_recording()
        if success:
            self.is_recording = True
            self.mic_btn.icon_color = (1.0, 0.2, 0.2, 1)
            self.audio_manager.on_recording_complete = self.on_recording_complete
        
        return True
    
    def on_mic_touch_up(self, widget, touch):
        if not self.is_recording:
            return False
        
        recording_path = self.audio_manager.stop_recording()
        self.is_recording = False
        self.mic_btn.icon_color = (0.5, 0.5, 0.5, 1)
        
        return True
    
    def on_recording_complete(self, recording_path):
        if not recording_path or not os.path.exists(recording_path):
            print("[ChatScreen] Recording file not found or invalid")
            return
        
        if not self.peer_ip:
            print("[ChatScreen] No peer selected")
            return
        
        filename = os.path.basename(recording_path)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        bubble = AudioBubble(filename, recording_path, timestamp, is_sent=True)
        self.messages_list.add_widget(bubble)
        
        app = MDApp.get_running_app()
        if app and app.engine:
            def progress_callback(bytes_sent, total_size):
                if bubble and hasattr(bubble, 'update_progress'):
                    bubble.update_progress(bytes_sent, total_size)
            
            app.engine.send_file(self.peer_ip, recording_path, progress_callback=progress_callback)
        
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.1)
    
    def go_back(self, *args):
        """Return to radar screen."""
        app = MDApp.get_running_app()
        app.root.current = 'radar'


class SettingsScreen(MDScreen):
    """Settings screen for app configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'settings'
        self.about_dialog = None
        
        # Main layout
        layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))
        
        # Header with back button
        header = MDBoxLayout(
            size_hint_y=None,
            height=dp(60),
            padding=dp(10),
            spacing=dp(10)
        )
        
        back_btn = MDIconButton(icon='arrow-left')
        back_btn.bind(on_release=self.go_back)
        
        title = MDLabel(
            text="⚙️ Settings",
            font_style='Title',
            role='large',
            theme_text_color='Primary'
        )
        
        header.add_widget(back_btn)
        header.add_widget(title)
        layout.add_widget(header)
        
        # Scrollable settings content
        scroll = MDScrollView(size_hint=(1, 1))
        settings_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(15),
            padding=dp(10)
        )
        
        # 1. Identity Section
        identity_card = self._create_section_card(
            "🪪 Identity",
            "Manage your display name"
        )
        
        identity_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        self.username_field = MDTextField(
            mode='outlined',
            size_hint_y=None,
            height=dp(50)
        )
        self.username_field.add_widget(MDTextFieldHintText(text="Username"))
        
        username_btn = MDButton(style='elevated')
        username_btn.add_widget(MDButtonText(text="Update Username"))
        username_btn.bind(on_release=self.update_username)
        
        identity_content.add_widget(self.username_field)
        identity_content.add_widget(username_btn)
        identity_card.add_widget(identity_content)
        settings_content.add_widget(identity_card)
        
        # 2. Privacy Section
        privacy_card = self._create_section_card(
            "🔒 Privacy",
            "Control data retention and cleanup"
        )
        
        privacy_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(15),
            padding=dp(10)
        )
        
        # Retention hours slider
        retention_label = MDLabel(
            text="Message Retention: 24 hours",
            font_style='Body',
            role='large',
            size_hint_y=None,
            height=dp(30)
        )
        
        self.retention_slider = MDSlider(
            min=1,
            max=168,
            value=24,
            step=1,
            size_hint_y=None,
            height=dp(40)
        )
        self.retention_slider.bind(value=lambda x, v: self.on_retention_changed(v))
        
        retention_hint = MDLabel(
            text="Messages older than this will be auto-deleted",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(20)
        )
        
        self.retention_label = retention_label
        privacy_content.add_widget(retention_label)
        privacy_content.add_widget(self.retention_slider)
        privacy_content.add_widget(retention_hint)
        privacy_card.add_widget(privacy_content)
        settings_content.add_widget(privacy_card)
        
        # 3. Appearance Section
        appearance_card = self._create_section_card(
            "🎨 Appearance",
            "Customize the app look and feel"
        )
        
        appearance_content = MDBoxLayout(
            orientation='horizontal',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10),
            size_hint_y=None,
            height=dp(50)
        )
        
        dark_mode_label = MDLabel(
            text="Dark Mode",
            font_style='Body',
            role='large',
            size_hint_x=0.7
        )
        
        self.dark_mode_switch = MDSwitch(
            size_hint_x=0.3,
            pos_hint={'center_y': 0.5}
        )
        self.dark_mode_switch.bind(active=self.on_dark_mode_changed)
        
        appearance_content.add_widget(dark_mode_label)
        appearance_content.add_widget(self.dark_mode_switch)
        appearance_card.add_widget(appearance_content)
        settings_content.add_widget(appearance_card)
        
        # 4. About Section
        about_card = self._create_section_card(
            "ℹ️ About",
            "App information and credits"
        )
        
        about_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        about_btn = MDButton(style='text')
        about_btn.add_widget(MDButtonText(text="View App Info"))
        about_btn.bind(on_release=self.show_about_dialog)
        
        about_content.add_widget(about_btn)
        about_card.add_widget(about_content)
        settings_content.add_widget(about_card)
        
        # 5. Danger Zone
        danger_card = self._create_section_card(
            "⚠️ Danger Zone",
            "Irreversible actions",
            color=(0.8, 0.2, 0.2, 1)
        )
        
        danger_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        panic_btn = MDButton(
            style='elevated',
            theme_bg_color='Custom',
            md_bg_color=(0.8, 0.2, 0.2, 1)
        )
        panic_btn.add_widget(MDButtonText(text="🔥 PANIC MODE - Delete All Data"))
        panic_btn.bind(on_release=self.show_panic_confirmation)
        
        danger_hint = MDLabel(
            text="This will permanently delete all messages, files, and keys",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(20)
        )
        
        danger_content.add_widget(panic_btn)
        danger_content.add_widget(danger_hint)
        danger_card.add_widget(danger_content)
        settings_content.add_widget(danger_card)
        
        scroll.add_widget(settings_content)
        layout.add_widget(scroll)
        self.add_widget(layout)
    
    def _create_section_card(self, title, subtitle, color=None):
        """Create a section card with title and subtitle."""
        card = MDCard(
            style='elevated',
            padding=dp(15),
            size_hint_y=None,
            height=dp(80),
            md_bg_color=color if color else (0.1, 0.1, 0.15, 1)
        )
        
        card_layout = MDBoxLayout(orientation='vertical', spacing=dp(5))
        
        title_label = MDLabel(
            text=title,
            font_style='Title',
            role='medium',
            theme_text_color='Primary',
            size_hint_y=None,
            height=dp(30)
        )
        
        subtitle_label = MDLabel(
            text=subtitle,
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(20)
        )
        
        card_layout.add_widget(title_label)
        card_layout.add_widget(subtitle_label)
        card.add_widget(card_layout)
        
        return card
    
    def on_pre_enter(self):
        """Load current settings when entering the screen."""
        app = MDApp.get_running_app()
        
        # Load username (with null check for Bug #9)
        if app and app.config:
            self.username_field.text = app.config.get_username()
            
            # Load retention hours
            retention_hours = app.config.get_retention_hours()
            self.retention_slider.value = retention_hours
            self.retention_label.text = f"Message Retention: {int(retention_hours)} hours"
            
            # Load dark mode
            self.dark_mode_switch.active = app.config.is_dark_mode()
        else:
            print("[SettingsScreen] Config not available, using defaults")
            self.username_field.text = "GhostUser"
            self.retention_slider.value = 24
            self.retention_label.text = "Message Retention: 24 hours"
            self.dark_mode_switch.active = True
    
    def update_username(self, *args):
        """Update the username in config."""
        new_username = self.username_field.text.strip()
        
        if not new_username:
            print("[Settings] Username cannot be empty")
            return
        
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set_username(new_username)
            print(f"[Settings] Username updated to '{new_username}'")
        else:
            print("[Settings] Config not available, cannot update username")
    
    def on_retention_changed(self, value):
        """Handle retention slider changes."""
        hours = int(value)
        self.retention_label.text = f"Message Retention: {hours} hours"
        
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set_retention_hours(hours)
            print(f"[Settings] Retention hours updated to {hours}")
        else:
            print("[Settings] Config not available, cannot update retention")
    
    def on_dark_mode_changed(self, switch, value):
        """Handle dark mode toggle."""
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set_dark_mode(value)
            print(f"[Settings] Dark mode {'enabled' if value else 'disabled'}")
        else:
            print("[Settings] Config not available, cannot update dark mode")
    
    def show_about_dialog(self, *args):
        """Show about dialog with app information."""
        if not self.about_dialog:
            # Create dialog content
            content = MDBoxLayout(
                orientation='vertical',
                spacing=dp(10),
                padding=dp(20),
                adaptive_height=True
            )
            
            info_items = [
                ("Version", "1.0.0"),
                ("Build", "Production"),
                ("Framework", "KivyMD + Python"),
                ("License", "Open Source"),
                ("GitHub", "github.com/yourusername/ghostnet")
            ]
            
            for label, value in info_items:
                item_layout = MDBoxLayout(
                    orientation='horizontal',
                    spacing=dp(10),
                    size_hint_y=None,
                    height=dp(30)
                )
                
                label_widget = MDLabel(
                    text=f"{label}:",
                    font_style='Body',
                    role='medium',
                    size_hint_x=0.4
                )
                
                value_widget = MDLabel(
                    text=value,
                    font_style='Body',
                    role='medium',
                    theme_text_color='Secondary',
                    size_hint_x=0.6
                )
                
                item_layout.add_widget(label_widget)
                item_layout.add_widget(value_widget)
                content.add_widget(item_layout)
            
            # Create dialog
            self.about_dialog = MDDialog(
                MDDialogHeadlineText(text="About Ghost Net"),
                MDDialogContentContainer(content, orientation="vertical"),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(
                        MDButtonText(text="Close"),
                        style="text",
                        on_release=lambda x: self.about_dialog.dismiss()
                    ),
                    spacing=dp(8)
                )
            )
        
        self.about_dialog.open()
    
    def show_panic_confirmation(self, *args):
        """Show double confirmation dialog for panic mode."""
        app = MDApp.get_running_app()
        
        def confirm_panic(dialog):
            """Second confirmation dialog."""
            dialog.dismiss()
            
            second_dialog = MDDialog(
                MDDialogHeadlineText(text="⚠️ FINAL WARNING"),
                MDDialogContentContainer(
                    MDLabel(
                        text="This action is IRREVERSIBLE!\n\nAll messages, files, encryption keys, and config will be permanently deleted.\n\nAre you ABSOLUTELY sure?",
                        halign='center',
                        font_style='Body',
                        role='large'
                    ),
                    orientation="vertical"
                ),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="Cancel"),
                        style="text",
                        on_release=lambda x: second_dialog.dismiss()
                    ),
                    MDButton(
                        MDButtonText(text="DELETE EVERYTHING"),
                        style="elevated",
                        theme_bg_color='Custom',
                        md_bg_color=(0.8, 0.2, 0.2, 1),
                        on_release=lambda x: self.nuke_data(second_dialog)
                    ),
                    spacing=dp(8)
                )
            )
            second_dialog.open()
        
        # First confirmation — use a list to hold the dialog reference so the
        # Cancel lambda can capture it before the variable is fully assigned
        # (avoids the "referenced before assignment" forward-reference bug)
        dialog_holder = [None]

        def _make_first_dialog():
            d = MDDialog(
                MDDialogHeadlineText(text="⚠️ Activate Panic Mode?"),
                MDDialogContentContainer(
                    MDLabel(
                        text="This will delete ALL data:\n• All messages\n• All files\n• Encryption keys\n• App configuration\n\nThe app will exit immediately.",
                        halign='center',
                        font_style='Body',
                        role='large'
                    ),
                    orientation="vertical"
                ),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="Cancel"),
                        style="text",
                        on_release=lambda x: dialog_holder[0].dismiss()
                    ),
                    MDButton(
                        MDButtonText(text="Continue"),
                        style="elevated",
                        theme_bg_color='Custom',
                        md_bg_color=(0.8, 0.5, 0.2, 1),
                        on_release=lambda x: confirm_panic(dialog_holder[0])
                    ),
                    spacing=dp(8)
                )
            )
            dialog_holder[0] = d
            return d

        dialog = _make_first_dialog()
        dialog.open()
    
    def nuke_data(self, dialog):
        """Execute panic mode - delete all data and exit."""
        dialog.dismiss()
        app = MDApp.get_running_app()
        
        print("[PANIC MODE] Initiating data destruction...")
        
        # Stop engine first
        if app.engine:
            app.engine.stop()
            time.sleep(1)  # Wait for threads to close file handles
        
        # Delete database
        try:
            if os.path.exists("ghostnet.db"):
                os.remove("ghostnet.db")
                print("[PANIC MODE] Database deleted")
        except Exception as e:
            print(f"[PANIC MODE] Database deletion error: {e}")
        
        # Delete encryption key
        try:
            if os.path.exists("secret.key"):
                os.remove("secret.key")
                print("[PANIC MODE] Encryption key deleted")
        except Exception as e:
            print(f"[PANIC MODE] Key deletion error: {e}")
        
        # Delete downloads directory
        try:
            import shutil
            if os.path.exists("downloads"):
                shutil.rmtree("downloads")
                print("[PANIC MODE] Downloads deleted")
        except Exception as e:
            print(f"[PANIC MODE] Downloads deletion error: {e}")
        
        # Delete config
        try:
            if app and app.config:
                app.config.delete_config()
                print("[PANIC MODE] Config deleted")
            else:
                print("[PANIC MODE] Config not available to delete")
        except Exception as e:
            print(f"[PANIC MODE] Config deletion error: {e}")
        
        print("[PANIC MODE] All data destroyed. Exiting...")
        sys.exit(0)
    
    def go_back(self, *args):
        """Return to radar screen."""
        app = MDApp.get_running_app()
        app.root.current = 'radar'


class GhostNetApp(MDApp):
    """Main application class."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = None
        self.username = "GhostUser"
        self.service_running = False
        self.notification_manager = None
    
    def _start_android_service(self):
        if platform.system() == 'Android':
            try:
                from jnius import autoclass
                PythonService = autoclass('org.kivy.android.PythonService')
                service = PythonService.mService
                
                Intent = autoclass('android.content.Intent')
                intent = Intent(service, autoclass('service.GhostService'))
                service.startService(intent)
                
                self.service_running = True
                print("[GhostNetApp] Started Android background service")
            except Exception as e:
                print(f"[GhostNetApp] Failed to start service: {e}")
        else:
            print("[GhostNetApp] Not on Android - skipping service startup")
    
    def build(self):
        """Build the app UI."""
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        
        sm = MDScreenManager()
        sm.add_widget(LockScreen())
        sm.add_widget(BootScreen())
        sm.add_widget(RadarScreen())
        sm.add_widget(DiagnosticsScreen())
        sm.add_widget(ChatScreen())
        sm.add_widget(SettingsScreen())
        if MAPVIEW_AVAILABLE:
            sm.add_widget(MapScreen())
        
        sm.current = 'lock'
        
        return sm
    
    def on_start(self):
        """Called when the app starts - now with async boot sequence."""
        # Create required directories (only user-writable ones) - Bug #2 fix
        self.downloads_path = None
        try:
            # Try primary path first: ~/Downloads/GhostNet
            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads", "GhostNet")
            os.makedirs(downloads_path, exist_ok=True)
            self.downloads_path = downloads_path
            print(f"[GhostNet] Downloads directory: {downloads_path}")
        except Exception as e:
            print(f"[GhostNet] Primary downloads path failed: {e}")
            # Fallback to app-specific directory
            try:
                import platform
                if platform.system() == 'Android':
                    downloads_path = os.path.join(os.path.expanduser("~"), ".ghostnet", "downloads")
                else:
                    downloads_path = os.path.join(os.path.expanduser("~"), ".ghostnet", "downloads")
                os.makedirs(downloads_path, exist_ok=True)
                self.downloads_path = downloads_path
                print(f"[GhostNet] Using fallback downloads directory: {downloads_path}")
            except Exception as e2:
                print(f"[GhostNet] WARNING: Could not create downloads directory: {e2}")
                # Continue without downloads directory - app can still function
        
        self._start_android_service()
        
        threading.Thread(target=self.startup_checks, daemon=True).start()
    
    def startup_checks(self):
        """
        Perform startup initialization in background thread.
        Updates boot screen status and transitions to boot when complete.
        """
        def get_boot_screen():
            try:
                return self.root.get_screen('boot')
            except:
                return None
        
        boot_screen = get_boot_screen()
        if not boot_screen:
            print("[GhostNet] Boot screen not available")
            return
        
        try:
            # Step 1: Request permissions (move to UI thread to avoid threading issues)
            # Bug #5 fix: Store boot_screen in self to avoid scope issues
            def request_perms_ui():
                try:
                    if self.root and self.root.get_screen('boot'):
                        self.root.get_screen('boot').update_status("Requesting permissions...")
                    self.request_permissions()
                except Exception as e:
                    print(f"[GhostNet] Permission request error: {e}")
            
            Clock.schedule_once(lambda dt: request_perms_ui(), 0)
            time.sleep(0.5)
            
            # Step 2: Load configuration with error handling
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Loading configuration..."),
                0
            )
            
            try:
                self.config = get_config()
            except Exception as e:
                print(f"[GhostNet] Config initialization error: {e}")
                self.config = None
                # Continue with defaults
            
            if self.config:
                try:
                    # Apply theme from config
                    theme_style = "Dark" if self.config.is_dark_mode() else "Light"
                    Clock.schedule_once(
                        lambda dt: setattr(self.theme_cls, 'theme_style', theme_style),
                        0
                    )
                except Exception as e:
                    print(f"[GhostNet] Theme application error: {e}")
            
            # Defer callback registration until UI is fully initialized
            def register_config_callback():
                if self.config:
                    try:
                        self.config.register_change_callback(self.on_config_changed)
                    except Exception as e:
                        print(f"[GhostNet] Config callback registration error: {e}")
            
            Clock.schedule_once(lambda dt: register_config_callback(), 0.5)
            
            # Get username from config (with null check)
            if self.config:
                self.username = self.config.get_username()
            else:
                print("[GhostNet] Config unavailable, using default username")
                self.username = "GhostUser"
            time.sleep(0.5)
            
            self.persistence_db = None
            try:
                Clock.schedule_once(
                    lambda dt: boot_screen.update_status("Initializing database..."),
                    0
                )
                self.persistence_db = PersistenceDatabase()
                time.sleep(0.5)
            except Exception as e:
                print(f"[GhostNet] Persistence database error: {e}")
                self.persistence_db = None
            
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Starting P2P network..."),
                0
            )
            
            try:
                self.engine = GhostEngine(
                    config_manager=self.config,
                    on_message_received=self.handle_message_received,
                    on_peer_update=self.handle_peer_update,
                    on_file_received=self.handle_file_received,
                    persistence_db=self.persistence_db,
                    enable_storage=True
                )
                self.engine.on_sos_received = self.handle_sos_received
                
                diag_mgr = get_diagnostics()
                diag_mgr.set_engine_reference(self.engine)
                
                gps_mgr = get_gps_manager()
                gps_mgr.start()
                
                threading.Thread(target=self.engine.start, daemon=True).start()
                time.sleep(1.0)
            except Exception as e:
                print(f"[GhostNet] Engine initialization error: {e}")
                self.engine = None
                # Continue - app can work without networking
            
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Setting up background scrubbing..."),
                0
            )
            
            Clock.schedule_interval(self.run_message_scrubbing, 10)
            time.sleep(0.5)
            
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Cleaning old messages..."),
                0
            )
            
            if self.config and self.config.is_auto_cleanup_enabled():
                retention_hours = self.config.get_retention_hours()
                self.cleanup_old_messages(hours=retention_hours)
            time.sleep(0.5)
            
            # Step 6: Complete
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Ready!"),
                0
            )
            time.sleep(0.5)
            
            print(f"[GhostNet] App started as '{self.username}'")
            
            # Transition to radar (main screen) after successful boot
            Clock.schedule_once(
                lambda dt: setattr(self.root, 'current', 'radar'),
                0
            )
            
        except Exception as e:
            print(f"[GhostNet] Startup error: {e}")
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
                    lambda dt: setattr(self.root, 'current', 'boot'),
                    0
                )
            except Exception as e2:
                print(f"[GhostNet] Could not transition to boot: {e2}")
    
    def on_config_changed(self, key: str, old_value, new_value):
        """Handle configuration changes for hot-reloading."""
        try:
            print(f"[GhostNet] Config changed: {key} = {old_value} → {new_value}")
            
            if key == "dark_mode":
                # Hot-reload theme (check theme_cls exists)
                if hasattr(self, 'theme_cls') and self.theme_cls:
                    self.theme_cls.theme_style = "Dark" if new_value else "Light"
                    print(f"[GhostNet] Theme changed to {'Dark' if new_value else 'Light'} mode")
            
            elif key == "username":
                # Update local username reference
                self.username = new_value
                print(f"[GhostNet] Username updated to '{new_value}'")
        except Exception as e:
            print(f"[GhostNet] Config change handler error: {e}")
    
    def cleanup_old_messages(self, hours: int = 24):
        """
        Privacy feature: Delete messages older than specified hours.
        
        Args:
            hours: Age threshold in hours (default 24)
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
    
    def request_permissions(self):
        """Request storage permissions on Android with safe error handling."""
        if platform.system() == 'Android':
            try:
                from android.permissions import request_permissions, Permission
                
                # For Android API 33+, handle scoped storage
                permissions_to_request = []
                
                # Check if permissions exist before requesting
                if hasattr(Permission, 'INTERNET'):
                    permissions_to_request.append(Permission.INTERNET)
                if hasattr(Permission, 'ACCESS_NETWORK_STATE'):
                    permissions_to_request.append(Permission.ACCESS_NETWORK_STATE)
                if hasattr(Permission, 'ACCESS_WIFI_STATE'):
                    permissions_to_request.append(Permission.ACCESS_WIFI_STATE)
                
                # Storage permissions - handle API level differences
                if hasattr(Permission, 'READ_EXTERNAL_STORAGE'):
                    permissions_to_request.append(Permission.READ_EXTERNAL_STORAGE)
                if hasattr(Permission, 'WRITE_EXTERNAL_STORAGE'):
                    permissions_to_request.append(Permission.WRITE_EXTERNAL_STORAGE)
                
                if permissions_to_request:
                    request_permissions(permissions_to_request)
                    print(f"[GhostNet] Requested {len(permissions_to_request)} Android permissions")
                else:
                    print("[GhostNet] No permissions to request")
                    
            except ImportError as e:
                print(f"[GhostNet] Android permissions module not available: {e}")
                # Continue without permissions on non-Android or if module missing
            except AttributeError as e:
                print(f"[GhostNet] Permission attribute missing (API level issue): {e}")
                # Continue - may be running on newer Android API
            except Exception as e:
                print(f"[GhostNet] Permission request error: {e}")
                # Don't crash - continue app execution
        else:
            print("[GhostNet] Not on Android - permissions not needed")
    
    def on_pause(self):
        print("[GhostNet] App paused - handing off to background service")
        return True
    
    def on_resume(self):
        print("[GhostNet] App resumed - refreshing UI from database")
        try:
            if self.persistence_db:
                chat_screen = self.root.get_screen('chat')
                if chat_screen and chat_screen.peer_ip:
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
        # Schedule UI update on main thread
        Clock.schedule_once(
            lambda dt: self.update_radar_peers(peers_dict),
            0
        )
    
    def update_radar_peers(self, peers_dict):
        """Update radar screen with peer list and network status (main thread)."""
        try:
            radar_screen = self.root.get_screen('radar')
            radar_screen.update_peers(peers_dict)
            
            # Also update network status
            if self.engine:
                network_status = self.engine.get_network_status()
                radar_screen.update_network_status(network_status)
        except Exception as e:
            print(f"[GhostNetApp] Error updating radar: {e}")
    
    def handle_message_received(self, sender_ip, message_text, timestamp):
        """Handle incoming messages from network thread."""
        # Schedule UI update on main thread
        Clock.schedule_once(
            lambda dt: self.add_message_to_chat(sender_ip, message_text, timestamp),
            0
        )
    
    def add_message_to_chat(self, sender_ip, message_text, timestamp):
        """Add received message to chat screen (main thread)."""
        chat_screen = self.root.get_screen('chat')
        chat_screen.add_received_message(sender_ip, message_text, timestamp)
        
        # Show notification if not on chat screen
        if self.root.current != 'chat':
            username = self.engine.get_peer_username(sender_ip) if self.engine else sender_ip
            print(f"[Notification] New message from {username}")
    
    def handle_file_received(self, sender_ip, filename, filepath, timestamp):
        """Handle incoming file from network thread."""
        # Schedule UI update on main thread
        Clock.schedule_once(
            lambda dt: self.add_file_to_chat(sender_ip, filename, filepath, timestamp),
            0
        )
    
    def add_file_to_chat(self, sender_ip, filename, filepath, timestamp):
        """Add received file to chat screen (main thread)."""
        chat_screen = self.root.get_screen('chat')
        chat_screen.add_received_file(sender_ip, filename, filepath, timestamp)
        
        # Show notification if not on chat screen
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


if __name__ == '__main__':
    GhostNetApp().run()