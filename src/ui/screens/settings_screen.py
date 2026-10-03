"""
Ghost Net UI - Settings Screen
Configuration center for cryptographic identity, retention periods, dark mode,
offline MBTiles maps, steganography carrier images, RAM-only ephemeral mode,
chaffing traffic generation, PIN management, and emergency wipe.
"""

import os
import sys
import time
import shutil
import platform
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDButton, MDIconButton
from kivymd.uix.slider import MDSlider

from ui.theme import (
    apply_premium_background,
    MDSwitch,
    MDButtonText,
    MDTextFieldHintText,
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from auth_manager import AuthenticationManager
from config import APP_VERSION


class SettingsScreen(MDScreen):
    """Settings screen for app configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'settings'
        apply_premium_background(self)
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
        
        back_btn = MDIconButton(
            icon='arrow-left',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1)
        )
        back_btn.bind(on_release=self.go_back)
        
        title = MDLabel(
            text="Settings",
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            pos_hint={'center_y': 0.5}
        )
        
        header.add_widget(back_btn)
        header.add_widget(title)
        layout.add_widget(header)
        
        # Scrollable settings content
        scroll = MDScrollView(
            size_hint=(1, 1),
            pos_hint={'center_x': 0.5}
        )
        settings_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(15),
            padding=dp(10)
        )
        
        # Unified settings card
        self.settings_card = MDCard(
            orientation='vertical',
            style='outlined',
            padding=dp(20),
            spacing=dp(20),
            size_hint_x=1,
            adaptive_height=True,
            md_bg_color=(0.1, 0.12, 0.18, 0.65),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        settings_content.add_widget(self.settings_card)
        
        def add_section(widget):
            if len(self.settings_card.children) > 0:
                self.settings_card.add_widget(self._create_divider())
            self.settings_card.add_widget(widget)
        
        # 1. Identity Section
        identity_card = self._create_section_card(
            "Identity",
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
        
        username_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(180),
            theme_bg_color='Custom',
            md_bg_color=(0.65, 0.79, 0.92, 1)
        )
        username_btn_text = MDButtonText(text="Update Username")
        username_btn_text.theme_text_color = 'Custom'
        username_btn_text.text_color = (0.05, 0.06, 0.1, 1)
        username_btn.add_widget(username_btn_text)
        username_btn.bind(on_release=self.update_username)
        
        identity_content.add_widget(self.username_field)
        identity_content.add_widget(username_btn)
        identity_card.add_widget(identity_content)
        add_section(identity_card)
        
        # 2. Privacy Section
        privacy_card = self._create_section_card(
            "Privacy",
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
        add_section(privacy_card)
        
        # 3. Appearance Section
        appearance_card = self._create_section_card(
            "Appearance",
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
        add_section(appearance_card)
        
        # 4. About Section
        about_card = self._create_section_card(
            "About",
            "App information and credits"
        )
        
        about_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        about_btn = MDButton(
            style='outlined',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(180),
            theme_bg_color='Custom',
            md_bg_color=(0.1, 0.12, 0.18, 0.3),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        about_btn_text = MDButtonText(text="View App Info")
        about_btn_text.theme_text_color = 'Custom'
        about_btn_text.text_color = (0.65, 0.79, 0.92, 1)
        about_btn.add_widget(about_btn_text)
        about_btn.bind(on_release=self.show_about_dialog)
        
        about_content.add_widget(about_btn)
        about_card.add_widget(about_content)
        add_section(about_card)
        
        # Map Settings Section
        map_card = self._create_section_card(
            "Map Settings",
            "Configure offline mapping database"
        )
        
        map_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        self.map_path_label = MDLabel(
            text="Offline Map: Not Selected",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(30)
        )
        
        map_select_btn = MDButton(
            style='outlined',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(180),
            theme_bg_color='Custom',
            md_bg_color=(0.1, 0.12, 0.18, 0.3),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        map_select_text = MDButtonText(text="Select .mbtiles File")
        map_select_text.theme_text_color = 'Custom'
        map_select_text.text_color = (0.65, 0.79, 0.92, 1)
        map_select_btn.add_widget(map_select_text)
        map_select_btn.bind(on_release=self.open_map_file_picker)
        
        map_content.add_widget(self.map_path_label)
        map_content.add_widget(map_select_btn)
        map_card.add_widget(map_content)
        add_section(map_card)
        
        # Steganography Settings Section
        stego_card = self._create_section_card(
            "Steganography Settings",
            "Hide messages inside carrier images"
        )
        
        stego_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        stego_switch_layout = MDBoxLayout(
            orientation='horizontal',
            adaptive_height=True,
            spacing=dp(10)
        )
        
        stego_switch_label = MDLabel(
            text="Enable Steganography",
            font_style='Body',
            role='large',
            size_hint_x=0.7
        )
        
        self.stego_switch = MDSwitch(
            size_hint_x=0.3,
            pos_hint={'center_y': 0.5}
        )
        self.stego_switch.bind(active=self.on_stego_changed)
        
        stego_switch_layout.add_widget(stego_switch_label)
        stego_switch_layout.add_widget(self.stego_switch)
        
        self.stego_path_label = MDLabel(
            text="Carrier Image: Default (Dynamic)",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(30)
        )
        
        stego_select_btn = MDButton(
            style='outlined',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(180),
            theme_bg_color='Custom',
            md_bg_color=(0.1, 0.12, 0.18, 0.3),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        stego_select_text = MDButtonText(text="Select Carrier PNG")
        stego_select_text.theme_text_color = 'Custom'
        stego_select_text.text_color = (0.65, 0.79, 0.92, 1)
        stego_select_btn.add_widget(stego_select_text)
        stego_select_btn.bind(on_release=self.open_carrier_file_picker)
        
        stego_content.add_widget(stego_switch_layout)
        stego_content.add_widget(self.stego_path_label)
        stego_content.add_widget(stego_select_btn)
        stego_card.add_widget(stego_content)
        add_section(stego_card)
        
        # Anonymity Section
        anonymity_card = self._create_section_card(
            "Advanced Anonymity",
            "Configure RAM-only chats & dummy traffic"
        )
        
        anonymity_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(15),
            padding=dp(10)
        )
        
        # Ephemeral Mode Switch
        ephemeral_layout = MDBoxLayout(
            orientation='horizontal',
            adaptive_height=True,
            spacing=dp(10),
            size_hint_y=None,
            height=dp(40)
        )
        ephemeral_label = MDLabel(
            text="Ephemeral Mode (RAM-only)",
            font_style='Body',
            role='large',
            size_hint_x=0.7
        )
        self.ephemeral_switch = MDSwitch(
            size_hint_x=0.3,
            pos_hint={'center_y': 0.5}
        )
        self.ephemeral_switch.bind(active=self.on_ephemeral_changed)
        ephemeral_layout.add_widget(ephemeral_label)
        ephemeral_layout.add_widget(self.ephemeral_switch)
        
        # Chaffing Switch
        chaffing_layout = MDBoxLayout(
            orientation='horizontal',
            adaptive_height=True,
            spacing=dp(10),
            size_hint_y=None,
            height=dp(40)
        )
        chaffing_label = MDLabel(
            text="Background Dummy Traffic (Chaffing)",
            font_style='Body',
            role='large',
            size_hint_x=0.7
        )
        self.chaffing_switch = MDSwitch(
            size_hint_x=0.3,
            pos_hint={'center_y': 0.5}
        )
        self.chaffing_switch.bind(active=self.on_chaffing_changed)
        chaffing_layout.add_widget(chaffing_label)
        chaffing_layout.add_widget(self.chaffing_switch)
        
        # Identity Fingerprint Label
        self.fingerprint_label = MDLabel(
            text="Fingerprint: Loading...",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(40)
        )
        
        anonymity_content.add_widget(ephemeral_layout)
        anonymity_content.add_widget(chaffing_layout)
        anonymity_content.add_widget(self.fingerprint_label)
        anonymity_card.add_widget(anonymity_content)
        add_section(anonymity_card)
        
        # Security Section (Change PINs)
        security_card = self._create_section_card(
            "Security Settings",
            "Update authentication PINs"
        )
        
        security_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        self.old_pin_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_y=None,
            height=dp(50)
        )
        self.old_pin_field.add_widget(MDTextFieldHintText(text="Current Master PIN"))
        
        self.new_master_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_y=None,
            height=dp(50)
        )
        self.new_master_field.add_widget(MDTextFieldHintText(text="New Master PIN"))
        
        self.new_duress_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_y=None,
            height=dp(50)
        )
        self.new_duress_field.add_widget(MDTextFieldHintText(text="New Duress PIN"))
        
        pin_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(180),
            theme_bg_color='Custom',
            md_bg_color=(0.65, 0.79, 0.92, 1)
        )
        pin_btn_text = MDButtonText(text="Change PINs")
        pin_btn_text.theme_text_color = 'Custom'
        pin_btn_text.text_color = (0.05, 0.06, 0.1, 1)
        pin_btn.add_widget(pin_btn_text)
        pin_btn.bind(on_release=self.change_pins_submit)
        
        security_content.add_widget(self.old_pin_field)
        security_content.add_widget(self.new_master_field)
        security_content.add_widget(self.new_duress_field)
        security_content.add_widget(pin_btn)
        
        security_card.add_widget(security_content)
        add_section(security_card)
        
        # Diagnostics & Telemetry Section
        diagnostics_card = self._create_section_card(
            "Diagnostics & Telemetry",
            "Real-time routing table, sockets & mission logs"
        )
        diag_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        diag_open_btn = MDButton(
            style='outlined',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(200),
            theme_bg_color='Custom',
            md_bg_color=(0.1, 0.12, 0.18, 0.3),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        diag_open_btn_text = MDButtonText(text="Open Diagnostics")
        diag_open_btn_text.theme_text_color = 'Custom'
        diag_open_btn_text.text_color = (0.65, 0.79, 0.92, 1)
        diag_open_btn.add_widget(diag_open_btn_text)
        diag_open_btn.bind(on_release=self.open_diagnostics)
        diag_content.add_widget(diag_open_btn)
        diagnostics_card.add_widget(diag_content)
        add_section(diagnostics_card)
        
        # 5. Emergency Data Wipe
        danger_card = self._create_section_card(
            "Emergency Data Wipe",
            "Cryptographic overwrite and local data removal",
            color=(0.85, 0.35, 0.35, 1)
        )
        
        danger_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        
        panic_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=None,
            width=dp(280),
            theme_bg_color='Custom',
            md_bg_color=(0.8, 0.2, 0.2, 1)
        )
        panic_text = MDButtonText(text="Emergency Data Wipe")
        panic_text.theme_text_color = 'Custom'
        panic_text.text_color = (1, 1, 1, 1)
        panic_btn.add_widget(panic_text)
        panic_btn.bind(on_release=self.show_panic_confirmation)
        
        danger_hint = MDLabel(
            text="Gost-Net attempts logical overwrite and deletion. Modern flash storage does not guarantee physical destruction.",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(20)
        )
        
        danger_content.add_widget(panic_btn)
        danger_content.add_widget(danger_hint)
        danger_card.add_widget(danger_content)
        add_section(danger_card)
        
        # 6. About / System Info Section
        about_card = self._create_section_card(
            "About Gost-Net",
            f"Gost-Net v{APP_VERSION}"
        )
        about_content = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(6),
            padding=dp(10)
        )
        version_label = MDLabel(
            text=f"Version {APP_VERSION}",
            font_style='Body',
            role='medium',
            theme_text_color='Secondary'
        )
        about_content.add_widget(version_label)
        about_card.add_widget(about_content)
        add_section(about_card)
        
        scroll.add_widget(settings_content)
        layout.add_widget(scroll)
        self.add_widget(layout)
    
    def _create_section_card(self, title, subtitle, color=None):
        """Creates a section container layout instead of a separate card, adding it to self.settings_card."""
        container = MDBoxLayout(
            orientation='vertical',
            spacing=dp(12),
            size_hint_y=None,
            adaptive_height=True
        )
        
        card_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(4),
            size_hint_y=None,
            height=dp(54)
        )
        
        title_label = MDLabel(
            text=title,
            font_style='Title',
            role='medium',
            theme_text_color='Primary',
            size_hint_y=None,
            height=dp(30)
        )
        if color:
            title_label.theme_text_color = 'Custom'
            title_label.text_color = color
            
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
        container.add_widget(card_layout)
        
        return container

    def _create_divider(self):
        """Creates a custom horizontal line separator."""
        divider = Widget(size_hint_y=None, height=dp(1))
        with divider.canvas.before:
            Color(0.2, 0.25, 0.35, 0.2)
            divider.rect = Rectangle(pos=divider.pos, size=(divider.width, 1))
        
        def _update_rect(instance, value):
            divider.rect.pos = divider.pos
            divider.rect.size = (divider.width, 1)
            
        divider.bind(pos=_update_rect, size=_update_rect)
        return divider
    
    def on_pre_enter(self):
        """Load current settings when entering the screen."""
        app = MDApp.get_running_app()
        
        if app and app.config:
            self.username_field.text = app.config.get_username()
            
            # Load retention hours
            retention_hours = app.config.get_retention_hours()
            self.retention_slider.value = retention_hours
            self.retention_label.text = f"Message Retention: {int(retention_hours)} hours"
            
            # Load dark mode
            self.dark_mode_switch.active = app.config.is_dark_mode()
            
            # Load mbtiles path
            mbtiles_path = app.config.get("mbtiles_path")
            if mbtiles_path:
                self.map_path_label.text = f"Offline Map: {os.path.basename(mbtiles_path)}"
            else:
                self.map_path_label.text = "Offline Map: Not Selected"
                
            # Load stego config
            self.stego_switch.active = app.config.get("steganography_enabled", False)
            carrier_path = app.config.get("carrier_image_path", "")
            if carrier_path:
                self.stego_path_label.text = f"Carrier Image: {os.path.basename(carrier_path)}"
            else:
                self.stego_path_label.text = "Carrier Image: Default (Dynamic)"
                
            # Load ephemeral config
            self.ephemeral_switch.active = app.config.get("ephemeral_mode", False)
            
            # Load chaffing config
            self.chaffing_switch.active = app.config.get("chaffing_enabled", False)
            
            # Load identity fingerprint
            fingerprint = app.get_identity_fingerprint()
            if fingerprint:
                self.fingerprint_label.text = f"Fingerprint: {fingerprint[:16]}...{fingerprint[-16:]}"
            else:
                self.fingerprint_label.text = "Fingerprint: Unavailable (Offline)"
        else:
            print("[SettingsScreen] Config not available, using defaults")
            self.username_field.text = "GhostUser"
            self.retention_slider.value = 24
            self.retention_label.text = "Message Retention: 24 hours"
            self.dark_mode_switch.active = True
            self.map_path_label.text = "Offline Map: Not Selected"
            self.stego_switch.active = False
            self.stego_path_label.text = "Carrier Image: Default (Dynamic)"
            self.ephemeral_switch.active = False
            self.chaffing_switch.active = False
            self.fingerprint_label.text = "Fingerprint: Unavailable (Offline)"
            
    def on_stego_changed(self, active):
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set("steganography_enabled", active)
            app.config.save()
            print(f"[Settings] Steganography mode: {active}")
            
    def open_carrier_file_picker(self, *args):
        try:
            from kivymd.uix.filemanager import MDFileManager
            
            def exit_manager(*args):
                self.carrier_file_manager.close()
                
            def select_path(path):
                self.carrier_file_manager.close()
                if path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    app = MDApp.get_running_app()
                    if app and app.config:
                        app.config.set("carrier_image_path", path)
                        app.config.save()
                        self.stego_path_label.text = f"Carrier Image: {os.path.basename(path)}"
                        print(f"[Settings] Selected carrier image path: {path}")
                else:
                    print("[Settings] Selected file must be a PNG or JPG file")
            
            self.carrier_file_manager = MDFileManager(
                exit_manager=exit_manager,
                select_path=select_path,
                preview=False
            )
            start_path = "/"
            if os.name == 'nt':
                start_path = "C:\\"
            self.carrier_file_manager.show(start_path)
        except Exception as e:
            print(f"[Settings] Carrier file picker error: {e}")
            
    def open_map_file_picker(self, *args):
        try:
            from kivymd.uix.filemanager import MDFileManager
            
            def exit_manager(*args):
                self.map_file_manager.close()
                
            def select_path(path):
                self.map_file_manager.close()
                if path.endswith('.mbtiles'):
                    app = MDApp.get_running_app()
                    if app and app.config:
                        app.config.set("mbtiles_path", path)
                        app.config.save()
                        self.map_path_label.text = f"Offline Map: {os.path.basename(path)}"
                        print(f"[Settings] Selected mbtiles path: {path}")
                else:
                    print("[Settings] Selected file must be an .mbtiles file")
            
            self.map_file_manager = MDFileManager(
                exit_manager=exit_manager,
                select_path=select_path,
                ext=['.mbtiles']
            )
            
            start_path = os.path.expanduser("~")
            if platform.system() == 'Android' or platform.system() == 'Linux':
                candidate_paths = [
                    '/storage/emulated/0/',
                    os.path.join(os.path.expanduser("~"), "Downloads"),
                    os.path.join(os.path.expanduser("~"), "Documents"),
                ]
                for p in candidate_paths:
                    if os.path.exists(p) and os.path.isdir(p):
                        start_path = p
                        break
            
            self.map_file_manager.show(start_path)
        except Exception as e:
            print(f"[Settings] Map file manager error: {e}")
    
    def update_username(self, *args):
        """Update the username in config."""
        new_username = self.username_field.text.strip()
        
        if not new_username:
            self.show_status_dialog("Error", "Username cannot be empty")
            return
        
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set_username(new_username)
            app.username = new_username
            self.show_status_dialog("Saved", f"Node callsign updated to '{new_username}'")
            print(f"[Settings] Username updated to '{new_username}'")
        else:
            self.show_status_dialog("Error", "Config not available, cannot update username")

    def open_diagnostics(self, *args):
        """Navigate to diagnostics screen."""
        app = MDApp.get_running_app()
        if app and app.root:
            app.root.current = 'diagnostics'
    
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
            
    def on_ephemeral_changed(self, instance, active):
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set("ephemeral_mode", active)
            app.config.save()
            print(f"[Settings] Ephemeral Mode changed to {active}")
            if app.persistence_db:
                app.persistence_db.ephemeral_mode = active
            if app.engine and app.engine.db_manager:
                app.engine.db_manager.ephemeral_mode = active
                
    def on_chaffing_changed(self, instance, active):
        app = MDApp.get_running_app()
        if app and app.config:
            app.config.set("chaffing_enabled", active)
            app.config.save()
            print(f"[Settings] Chaffing enabled changed to {active}")
            if app.engine:
                app.engine.chaffing_enabled = active
                
    def show_status_dialog(self, title, message):
        content = MDBoxLayout(
            orientation='vertical',
            padding=dp(20),
            adaptive_height=True
        )
        content.add_widget(MDLabel(
            text=message,
            font_style='Body',
            role='medium'
        ))
        
        dialog = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogContentContainer(content, orientation="vertical"),
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="OK"),
                    style="text",
                    on_release=lambda x: dialog.dismiss()
                )
            )
        )
        dialog.open()
        
    def change_pins_submit(self, *args):
        old_pin = self.old_pin_field.text.strip()
        new_master = self.new_master_field.text.strip()
        new_duress = self.new_duress_field.text.strip()
        
        if not old_pin or not new_master or not new_duress:
            self.show_status_dialog("Error", "All PIN fields must be filled")
            return
            
        auth_manager = AuthenticationManager()
        success, msg = auth_manager.change_pins(old_pin, new_master, new_duress)
        if success:
            self.show_status_dialog("Success", msg)
            self.old_pin_field.text = ""
            self.new_master_field.text = ""
            self.new_duress_field.text = ""
        else:
            self.show_status_dialog("Error", msg)
    
    def show_about_dialog(self, *args):
        """Show about dialog with app information."""
        if not self.about_dialog:
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
                ("GitHub", "github.com/Rhythm-Sanghi/Gost-Net")
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
        """Show double confirmation dialog for emergency data wipe."""
        app = MDApp.get_running_app()
        
        def confirm_panic(dialog):
            """Second confirmation dialog."""
            dialog.dismiss()
            
            second_dialog = MDDialog(
                MDDialogHeadlineText(text="CONFIRM EMERGENCY WIPE"),
                MDDialogContentContainer(
                    MDLabel(
                        text="This action cannot be undone!\n\nAll local messages, attachments, cryptographic ratchets, and configuration will be overwritten and removed from this node.\n\nNote: Physical wear-levelled flash memory (SSD/eMMC) may retain remnants beyond logical overwrite.\n\nAre you sure you want to proceed?",
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
                        MDButtonText(text="OVERWRITE & DELETE"),
                        style="elevated",
                        theme_bg_color='Custom',
                        md_bg_color=(0.8, 0.2, 0.2, 1),
                        on_release=lambda x: self.nuke_data(second_dialog)
                    ),
                    spacing=dp(8)
                )
            )
            second_dialog.open()
        
        dialog_holder = [None]

        def _make_first_dialog():
            d = MDDialog(
                MDDialogHeadlineText(text="Initiate Emergency Data Wipe?"),
                MDDialogContentContainer(
                    MDLabel(
                        text="This will overwrite and remove all local node data:\n• Stored messages and attachments\n• Double Ratchet cryptographic keys\n• Local application cache and config\n\nThe app will terminate immediately.",
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
        if app and getattr(app, 'engine', None):
            try:
                app.engine.stop()
            except Exception:
                pass
            time.sleep(0.5)
        
        # Close database connections
        try:
            if app and getattr(app, 'persistence_db', None):
                app.persistence_db.close()
            if app and getattr(app, 'db_manager', None):
                app.db_manager.close()
        except Exception as e:
            print(f"[PANIC MODE] Database close error: {e}")
        
        # Logical overwrite and deletion of databases
        try:
            from security import shred_file
            for db_name in ["ghostnet.db", "ghostnet_persistence.db", "ghostnet.db-wal", "ghostnet.db-shm"]:
                if os.path.exists(db_name):
                    shred_file(db_name)
                    print(f"[PANIC MODE] {db_name} logically overwritten and deleted")
        except Exception as e:
            print(f"[PANIC MODE] Database deletion error: {e}")
        
        # Delete encryption keys and secrets across working dir and storage_dir
        try:
            from security import shred_file
            storage_dir = getattr(app.auth_manager, 'storage_dir', '.') if (app and hasattr(app, 'auth_manager')) else '.'
            key_targets = ["secret.key", "secret.key.enc", ".db_salt", ".auth_secrets", "signing.key.enc", ".decoy_mode", ".failed_attempts", ".dead_man_switch"]
            for k in key_targets:
                if os.path.exists(k):
                    shred_file(k)
                if storage_dir and storage_dir != '.' and os.path.exists(os.path.join(storage_dir, k)):
                    shred_file(os.path.join(storage_dir, k))
            print("[PANIC MODE] Encryption keys and secrets logically overwritten and deleted")
        except Exception as e:
            print(f"[PANIC MODE] Key deletion error: {e}")
        
        # Delete downloads directories
        try:
            import shutil
            download_targets = ["downloads", os.path.expanduser("~/.ghostnet/downloads")]
            if app and getattr(app, 'downloads_path', None):
                download_targets.append(app.downloads_path)
            for d in download_targets:
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
            print("[PANIC MODE] Downloads cleared")
        except Exception as e:
            print(f"[PANIC MODE] Downloads deletion error: {e}")

        # Delete DTN spool directories
        try:
            import shutil
            spool_targets = ["spool", os.path.expanduser("~/.ghostnet/spool")]
            if app and getattr(app, 'engine', None) and getattr(app.engine, 'spool_dir', None):
                spool_targets.append(app.engine.spool_dir)
            for s in spool_targets:
                if os.path.exists(s):
                    shutil.rmtree(s, ignore_errors=True)
            print("[PANIC MODE] DTN spool directories cleared")
        except Exception as e:
            print(f"[PANIC MODE] Spool deletion error: {e}")

        # Clean audio cache, notes, and telemetry
        try:
            from security import shred_file
            if os.path.exists("notes.txt"):
                shred_file("notes.txt")
            try:
                from audio_manager import get_audio_manager
                get_audio_manager().shred_cache()
            except Exception:
                pass
            try:
                from telemetry_logger import get_telemetry_logger
                telemetry = get_telemetry_logger()
                with telemetry.buffer_lock:
                    telemetry.buffer.clear()
                shred_file(telemetry.get_log_path())
            except Exception:
                pass
            print("[PANIC MODE] Audio cache, notes, and telemetry cleared")
        except Exception as e:
            print(f"[PANIC MODE] Cache/telemetry wipe error: {e}")
        
        # Delete config
        try:
            if app and app.config:
                app.config.delete_config()
                print("[PANIC MODE] Config deleted")
            else:
                print("[PANIC MODE] Config not available to delete")
        except Exception as e:
            print(f"[PANIC MODE] Config deletion error: {e}")
        
        print("[PANIC MODE] All application data cleared. Exiting...")
        sys.exit(0)
    
    def go_back(self, *args):
        """Return to previous screen via NavigationController."""
        from ui.navigation import get_navigation_controller
        get_navigation_controller().go_back()
