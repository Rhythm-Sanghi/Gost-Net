"""
Ghost Net UI - Radar Screen
Home mesh radar display, peer discovery lists, active/saved peer tabs,
SOS emergency broadcast triggers, and direct chat launching.
"""

import os
import time
import threading
from datetime import datetime
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDIconButton

from ui.theme import (
    apply_premium_background,
    MDFloatingActionButton,
    MDButtonText,
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from ui.components.radar_canvas import RadarWidget
from gps_manager import get_gps_manager
from audio_manager import get_audio_manager

try:
    from ui.screens.map_screen import MAPVIEW_AVAILABLE
except ImportError:
    MAPVIEW_AVAILABLE = False


class RadarScreen(MDScreen):
    """Home screen showing discovered peers with radar animation and network info."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'radar'
        apply_premium_background(self)
        self.sos_long_press_time = 0
        self.sos_button = None
        self.gps_manager = get_gps_manager()
        self.alert_dialog = None
        self.title_tap_times = []
        self.title_widget = None
        
        # Root float layout to overlay floating buttons properly
        root_layout = MDFloatLayout(size_hint=(1, 1))
        
        layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint=(1, 1))
        
        # Responsive header with status and actions
        header = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(80),
            spacing=dp(4),
            padding=[dp(4), dp(4), dp(4), dp(4)]
        )
        
        top_row = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(36),
            spacing=dp(8)
        )
        
        title = MDLabel(
            text="Gost-Net",
            halign='left',
            font_style='Headline',
            role='medium',
            pos_hint={'center_y': 0.5}
        )
        title.bind(on_touch_down=self.on_title_tap)
        self.title_widget = title
        
        # Network status badge
        self.network_badge = MDLabel(
            text="Detecting...",
            halign='right',
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_x=None,
            width=dp(130),
            pos_hint={'center_y': 0.5}
        )
        
        top_row.add_widget(title)
        top_row.add_widget(self.network_badge)
        header.add_widget(top_row)
        
        action_row = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(40),
            spacing=dp(4)
        )
        
        map_btn = MDIconButton(
            icon='map',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=0.25,
            pos_hint={'center_y': 0.5}
        )
        map_btn.bind(on_release=self.open_map)
        
        notes_btn = MDIconButton(
            icon='note-text',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=0.25,
            pos_hint={'center_y': 0.5}
        )
        notes_btn.bind(on_release=self.open_notes)
        
        diag_btn = MDIconButton(
            icon='chart-timeline-variant',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=0.25,
            pos_hint={'center_y': 0.5}
        )
        diag_btn.bind(on_release=self.open_diagnostics)
        
        settings_btn = MDIconButton(
            icon='cog',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=0.25,
            pos_hint={'center_y': 0.5}
        )
        settings_btn.bind(on_release=self.open_settings)
        
        action_row.add_widget(map_btn)
        action_row.add_widget(notes_btn)
        action_row.add_widget(diag_btn)
        action_row.add_widget(settings_btn)
        header.add_widget(action_row)
        layout.add_widget(header)
        
        # Responsive body container
        body_container = MDBoxLayout(
            orientation='vertical',
            spacing=dp(8),
            size_hint=(1, 1),
            pos_hint={'center_x': 0.5}
        )
        
        self.radar = RadarWidget(size_hint=(1, 0.35))
        body_container.add_widget(self.radar)
        
        self.status_label = MDLabel(
            text="Scanning for peers...",
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='large',
            size_hint_y=None,
            height=dp(40)
        )
        body_container.add_widget(self.status_label)
        
        tabs_layout = MDBoxLayout(
            orientation='vertical',
            size_hint=(1, 1),
            spacing=dp(5)
        )
        self.tabs_layout = tabs_layout
        
        self.tab_buttons_layout = tab_buttons_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(5),
            padding=dp(5)
        )
        
        self.active_tab_btn = MDButton(
            style='text',
            theme_width='Custom',
            size_hint_x=0.5
        )
        act_text = MDButtonText(text="Active Peers")
        act_text.theme_text_color = 'Custom'
        act_text.text_color = (0.65, 0.79, 0.92, 1)
        self.active_tab_btn.add_widget(act_text)
        self.active_tab_btn.bind(on_release=self.show_active_peers)
        
        self.saved_tab_btn = MDButton(
            style='text',
            theme_width='Custom',
            size_hint_x=0.5
        )
        saved_text = MDButtonText(text="Saved Peers")
        saved_text.theme_text_color = 'Secondary'
        self.saved_tab_btn.add_widget(saved_text)
        self.saved_tab_btn.bind(on_release=self.show_saved_peers)
        
        # Bind tab buttons size/position changes to update underline indicator dynamically
        self.active_tab_btn.bind(pos=lambda *a: self.update_tab_buttons(), size=lambda *a: self.update_tab_buttons())
        self.saved_tab_btn.bind(pos=lambda *a: self.update_tab_buttons(), size=lambda *a: self.update_tab_buttons())
        
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
        self.peers_scroll.size_hint_y = 1
        self.saved_peers_scroll.opacity = 0
        self.saved_peers_scroll.size_hint_y = 0
        self.saved_peers_scroll.height = 0
        self.update_tab_buttons()
        
        tabs_layout.add_widget(self.peers_scroll)
        tabs_layout.add_widget(self.saved_peers_scroll)
        body_container.add_widget(tabs_layout)
        
        layout.add_widget(body_container)
        root_layout.add_widget(layout)
        
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
            root_layout.add_widget(self.sos_button)
            
        self.add_widget(root_layout)
    
    def open_diagnostics(self, *args):
        """Directly open the diagnostics screen from the header button."""
        self.unlock_diagnostics()

    def update_network_status(self, network_info):
        """Update network status badge with real interface and IP."""
        try:
            net_type = network_info.get('type', 'unknown')
            ip = network_info.get('ip', 'N/A')
            
            icons = {
                'wifi': 'WiFi',
                'hotspot': 'Hotspot',
                'cellular': 'Cellular',
                'ethernet': 'Ethernet',
                'private': 'Mesh',
                'unknown': 'Interface'
            }
            
            icon = icons.get(net_type, 'Node')
            if ip and ip != 'N/A':
                self.network_badge.text = f"{icon}: {ip}"
                self.network_badge.width = dp(160)
            else:
                self.network_badge.text = icon
        except Exception as e:
            print(f"[RadarScreen] Error updating network status: {e}")
            self.network_badge.text = "Offline"
    
    def update_peers(self, peers_dict):
        """Update the peers list (called from main thread via Clock)."""
        self.radar.update_peers(peers_dict)
        self.peers_list.clear_widgets()
        
        if not peers_dict:
            self.status_label.text = "Mesh listening: 0 direct peers"
            empty_item = MDBoxLayout(
                orientation='vertical',
                adaptive_height=True,
                spacing=dp(6),
                padding=[dp(16), dp(24), dp(16), dp(24)]
            )
            empty_lbl = MDLabel(
                text="No nearby peers discovered",
                font_style="Title",
                role="small",
                halign="center",
                theme_text_color="Primary"
            )
            empty_sub = MDLabel(
                text="Broadcast beaconing active on UDP port 37020 and BLE.\nNearby nodes will appear automatically once in range.",
                font_style="Body",
                role="small",
                halign="center",
                theme_text_color="Secondary"
            )
            empty_item.add_widget(empty_lbl)
            empty_item.add_widget(empty_sub)
            self.peers_list.add_widget(empty_item)
            return
        
        self.status_label.text = f"Active Mesh: {len(peers_dict)} peer(s)"
        
        for ip, info in peers_dict.items():
            username = info.get('username', 'Unknown')
            visible_peers = info.get('visible_peers', [])
            peer_id = info.get('peer_id', ip)
            battery = info.get('battery')
            if battery is not None:
                username = f"{username} ({battery}%)"
            
            # Transport resolution
            if ip.startswith('wfd_') or info.get('transport') == 'wfd':
                transport_label = "Wi-Fi Direct"
            elif ip.startswith('bt_') or info.get('transport') == 'bt':
                transport_label = "Bluetooth"
            else:
                transport_label = "TCP LAN"

            # TOFU Verification status
            app = MDApp.get_running_app()
            is_verified = False
            if app and hasattr(app, 'persistence_db') and app.persistence_db:
                try:
                    p_rec = app.persistence_db.get_peer(ip) or app.persistence_db.get_peer(peer_id)
                    if p_rec and p_rec.get('is_verified'):
                        is_verified = True
                except Exception:
                    pass
            key_mismatch = bool(info.get('key_mismatch'))
            if key_mismatch:
                verif_badge = "[⚠️ KEY MISMATCH]"
            elif is_verified:
                verif_badge = "[Verified]"
            else:
                verif_badge = "[TOFU]"

            # Last seen calculation
            last_seen_ts = info.get('last_seen', time.time())
            elapsed = max(0, int(time.time() - last_seen_ts))
            seen_str = "just now" if elapsed < 5 else f"{elapsed}s ago"

            route_text = None
            if visible_peers and len(visible_peers) > 0:
                if len(visible_peers) == 1:
                    route_text = f"Route: via {visible_peers[0][:8]}... (1 hop)"
                else:
                    route_text = f"Route: via {len(visible_peers)} peers"
            
            item = MDBoxLayout(
                orientation='horizontal',
                spacing=dp(10),
                size_hint_y=None,
                adaptive_height=True,
                padding=[dp(12), dp(10), dp(12), dp(10)]
            )
            
            with item.canvas.after:
                Color(0.2, 0.25, 0.35, 0.2)
                item.divider_line = Line(points=[item.x, item.y, item.x + item.width, item.y], width=1)
                
            def _update_div(inst, val):
                inst.divider_line.points = [inst.x, inst.y, inst.x + inst.width, inst.y]
            item.bind(pos=_update_div, size=_update_div)
            
            peer_info = MDBoxLayout(orientation='vertical', size_hint_x=0.74, spacing=dp(2), adaptive_height=True)
            peer_name = MDLabel(
                text=username,
                font_style='Title',
                role='medium',
                theme_text_color='Primary',
                adaptive_height=True
            )
            peer_badge = MDLabel(
                text=f"{verif_badge} • {transport_label}",
                font_style='Body',
                role='small',
                theme_text_color='Custom' if key_mismatch else 'Secondary',
                text_color=(1, 0.45, 0.45, 1) if key_mismatch else (0.65, 0.79, 0.92, 1),
                adaptive_height=True
            )
            peer_meta = MDLabel(
                text=f"{ip} • Seen {seen_str}",
                font_style='Body',
                role='small',
                theme_text_color='Secondary',
                adaptive_height=True
            )
            peer_info.add_widget(peer_name)
            peer_info.add_widget(peer_badge)
            peer_info.add_widget(peer_meta)
            
            if route_text:
                route_label = MDLabel(
                    text=route_text,
                    font_style='Body',
                    role='small',
                    theme_text_color='Secondary',
                    adaptive_height=True
                )
                peer_info.add_widget(route_label)
            
            chat_btn = MDButton(
                style='filled',
                size_hint_x=0.26,
                size_hint_y=None,
                height=dp(44),
                theme_bg_color='Custom',
                md_bg_color=(0.18, 0.24, 0.35, 0.9),
                pos_hint={'center_y': 0.5}
            )
            chat_btn_text = MDButtonText(text="Chat")
            chat_btn_text.theme_text_color = 'Custom'
            chat_btn_text.text_color = (0.65, 0.79, 0.92, 1)
            chat_btn.add_widget(chat_btn_text)
            chat_btn.bind(on_release=lambda x, p_ip=ip, p_name=username: self.open_chat(p_ip, p_name))
            
            item.add_widget(peer_info)
            item.add_widget(chat_btn)
            self.peers_list.add_widget(item)
    
    def on_enter(self, *args):
        """Resume radar animation and activate fast peer scanning when screen becomes visible."""
        if hasattr(self, 'radar') and self.radar:
            self.radar.start_animation()
        app = MDApp.get_running_app()
        if app and hasattr(app, 'engine') and app.engine:
            app.engine.reset_beacon_backoff()

    def on_leave(self, *args):
        """Pause radar animation when navigating away to conserve power."""
        if hasattr(self, 'radar') and self.radar:
            self.radar.stop_animation()

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
        from ui.navigation import get_navigation_controller
        get_navigation_controller().navigate_to('diagnostics')
    
    def open_diagnostics(self, *args):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().navigate_to('diagnostics')
    
    def open_settings(self, *args):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().navigate_to('settings')
    
    def open_map(self, *args):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().navigate_to('map')
            
    def open_notes(self, *args):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().navigate_to('notes')
    
    def handle_back(self) -> bool:
        """Handle screen-level Back key."""
        if self.current_tab == 'saved':
            self.show_active_peers()
            return True
        return False
        
    def show_exit_notice(self, text: str):
        """Show deliberate exit confirmation message on root screen."""
        original = self.status_label.text
        def reset(dt):
            if self.status_label.text == text:
                self.status_label.text = original
        self.status_label.text = text
        Clock.schedule_once(reset, 2.5)
    
    def show_active_peers(self, *args):
        """Switch to active peers tab."""
        if self.current_tab == 'active':
            return
        self.current_tab = 'active'
        self.peers_scroll.opacity = 1
        self.peers_scroll.size_hint_y = 1
        self.saved_peers_scroll.opacity = 0
        self.saved_peers_scroll.size_hint_y = 0
        self.saved_peers_scroll.height = 0
        self.update_tab_buttons()
     
    def show_saved_peers(self, *args):
        """Switch to saved peers tab and load from database."""
        if self.current_tab == 'saved':
            return
        self.current_tab = 'saved'
        self.peers_scroll.opacity = 0
        self.peers_scroll.size_hint_y = 0
        self.peers_scroll.height = 0
        self.saved_peers_scroll.opacity = 1
        self.saved_peers_scroll.size_hint_y = 1
        self.update_tab_buttons()
        self.load_saved_peers()

    def update_tab_buttons(self):
        if not hasattr(self, 'tab_buttons_layout'):
            return
        try:
            self.active_tab_btn.style = 'text'
            self.saved_tab_btn.style = 'text'
            
            if self.current_tab == 'active':
                for child in self.active_tab_btn.children:
                    if isinstance(child, MDButtonText):
                        child.theme_text_color = 'Custom'
                        child.text_color = (0.65, 0.79, 0.92, 1)
                for child in self.saved_tab_btn.children:
                    if isinstance(child, MDButtonText):
                        child.theme_text_color = 'Secondary'
            else:
                for child in self.active_tab_btn.children:
                    if isinstance(child, MDButtonText):
                        child.theme_text_color = 'Secondary'
                for child in self.saved_tab_btn.children:
                    if isinstance(child, MDButtonText):
                        child.theme_text_color = 'Custom'
                        child.text_color = (0.65, 0.79, 0.92, 1)
            
            # Redraw bottom underline on tab_buttons_layout canvas
            self.tab_buttons_layout.canvas.after.clear()
            with self.tab_buttons_layout.canvas.after:
                Color(0.65, 0.79, 0.92, 1) # Ice-Blue
                active_btn = self.active_tab_btn if self.current_tab == 'active' else self.saved_tab_btn
                Line(points=[active_btn.x, self.tab_buttons_layout.y, active_btn.x + active_btn.width, self.tab_buttons_layout.y], width=dp(2))
        except Exception as e:
            print(f"Tab button styling error: {e}")
    
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
                
                item = MDBoxLayout(
                    orientation='horizontal',
                    spacing=dp(10),
                    size_hint_y=None,
                    height=dp(70),
                    padding=[dp(12), dp(8), dp(12), dp(8)]
                )
                
                with item.canvas.after:
                    Color(0.2, 0.25, 0.35, 0.2)
                    item.divider_line = Line(points=[item.x, item.y, item.x + item.width, item.y], width=1)
                    
                def _update_div(inst, val):
                    inst.divider_line.points = [inst.x, inst.y, inst.x + inst.width, inst.y]
                item.bind(pos=_update_div, size=_update_div)
                
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
                chat_btn_text = MDButtonText(text="Connect")
                chat_btn_text.theme_text_color = 'Custom'
                chat_btn_text.text_color = (0.65, 0.79, 0.92, 1) # Ice-Blue
                chat_btn.add_widget(chat_btn_text)
                chat_btn.bind(on_release=lambda x, ip=peer_id, name=device_name: self.open_chat(ip, name))
                
                item.add_widget(peer_info)
                item.add_widget(chat_btn)
                
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
                text=f"EMERGENCY ALERT",
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
                MDDialogHeadlineText(text="SOS RECEIVED"),
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
