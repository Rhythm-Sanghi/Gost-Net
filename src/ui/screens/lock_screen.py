"""
Ghost Net UI - Lock Screen
Master PIN unlock terminal with duress PIN detection, cryptographic key derivation,
and logical overwrite and key deletion on duress PIN entry.
"""

import os
import secrets
import threading
from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDButton

from ui.theme import (
    apply_premium_background,
    MDButtonText,
    MDTextFieldHintText,
    MDTextFieldHelperText,
)
from auth_manager import AuthenticationManager
from audio_manager import get_audio_manager


class LockScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'lock'
        apply_premium_background(self)
        self.auth_manager = AuthenticationManager()
        self.shredding_in_progress = False
        
        self.root_layout = MDFloatLayout(size_hint=(1, 1))
        self.build_ui()
        self.add_widget(self.root_layout)

    def build_ui(self):
        self.root_layout.clear_widgets()
        if not self.auth_manager.are_pins_initialized():
            self._build_setup_ui()
        else:
            self._build_unlock_ui()

    def _build_setup_ui(self):
        card = MDCard(
            orientation='vertical',
            style='outlined',
            size_hint=(None, None),
            size=(dp(340), dp(480)),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            padding=dp(20),
            spacing=dp(12),
            md_bg_color=(0.08, 0.10, 0.14, 0.95),
            line_color=(0.22, 0.28, 0.38, 0.6),
            radius=[dp(6), dp(6), dp(6), dp(6)]
        )
        
        brand_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(2),
            size_hint_y=None,
            height=dp(50)
        )
        title = MDLabel(
            text='Ghost Net Setup',
            font_style='Headline',
            role='small',
            theme_text_color='Primary',
            halign='center'
        )
        subtitle = MDLabel(
            text='Set up this device',
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            halign='center'
        )
        brand_layout.add_widget(title)
        brand_layout.add_widget(subtitle)
        card.add_widget(brand_layout)
        
        self.callsign_field = MDTextField(
            mode='outlined',
            size_hint_x=1,
            size_hint_y=None,
            height=dp(48),
            multiline=False
        )
        self.callsign_field.add_widget(MDTextFieldHintText(text="Callsign"))
        self.callsign_field.text = ""
        card.add_widget(self.callsign_field)
        
        self.setup_pin_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_x=1,
            size_hint_y=None,
            height=dp(48),
            multiline=False
        )
        self.setup_pin_field.add_widget(MDTextFieldHintText(text="Create Master PIN (min 4 chars)"))
        card.add_widget(self.setup_pin_field)
        
        self.setup_confirm_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_x=1,
            size_hint_y=None,
            height=dp(48),
            multiline=False
        )
        self.setup_confirm_field.add_widget(MDTextFieldHintText(text="Confirm Master PIN"))
        card.add_widget(self.setup_confirm_field)
        
        self.setup_duress_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_x=1,
            size_hint_y=None,
            height=dp(48),
            multiline=False
        )
        self.setup_duress_field.add_widget(MDTextFieldHintText(text="Duress PIN (optional emergency wipe)"))
        card.add_widget(self.setup_duress_field)
        
        submit_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=1,
            theme_bg_color='Custom',
            md_bg_color=(0.65, 0.79, 0.92, 1)
        )
        btn_text = MDButtonText(text='Create Account')
        btn_text.theme_text_color = 'Custom'
        btn_text.text_color = (0.05, 0.06, 0.1, 1)
        submit_btn.add_widget(btn_text)
        submit_btn.bind(on_release=self.on_setup_submit)
        card.add_widget(submit_btn)
        
        self.status_label = MDLabel(
            text='',
            theme_text_color='Secondary',
            halign='center',
            font_style='Body',
            role='small',
            size_hint_y=None,
            height=dp(24)
        )
        card.add_widget(self.status_label)
        self.root_layout.add_widget(card)

    def _build_unlock_ui(self):
        card = MDCard(
            orientation='vertical',
            style='outlined',
            size_hint=(None, None),
            size=(dp(340), dp(360)),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            padding=dp(24),
            spacing=dp(20),
            md_bg_color=(0.08, 0.10, 0.14, 0.95),
            line_color=(0.22, 0.28, 0.38, 0.6),
            radius=[dp(6), dp(6), dp(6), dp(6)]
        )
        
        brand_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(4),
            size_hint_y=None,
            height=dp(60)
        )
        title = MDLabel(
            text='Ghost Net',
            font_style='Headline',
            role='medium',
            theme_text_color='Primary',
            halign='center'
        )
        subtitle = MDLabel(
            text='Offline Mesh Communicator',
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            halign='center'
        )
        brand_layout.add_widget(title)
        brand_layout.add_widget(subtitle)
        card.add_widget(brand_layout)
        
        self.pin_field = MDTextField(
            mode='outlined',
            password=True,
            size_hint_x=1,
            size_hint_y=None,
            height=dp(56),
            multiline=False
        )
        self.pin_field.add_widget(MDTextFieldHintText(text="Enter PIN"))
        self.pin_field.add_widget(MDTextFieldHelperText(text="Enter Master or Duress PIN", mode="persistent"))
        self.pin_field.bind(on_text_validate=self.on_pin_submit)
        card.add_widget(self.pin_field)
        
        submit_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=1,
            theme_bg_color='Custom',
            md_bg_color=(0.65, 0.79, 0.92, 1)
        )
        btn_text = MDButtonText(text='Unlock')
        btn_text.theme_text_color = 'Custom'
        btn_text.text_color = (0.05, 0.06, 0.1, 1)
        submit_btn.add_widget(btn_text)
        submit_btn.bind(on_release=self.on_pin_submit)
        card.add_widget(submit_btn)
        
        self.status_label = MDLabel(
            text='',
            theme_text_color='Secondary',
            halign='center',
            font_style='Body',
            role='small',
            size_hint_y=None,
            height=dp(30)
        )
        card.add_widget(self.status_label)
        self.root_layout.add_widget(card)

    def on_setup_submit(self, *args):
        callsign = self.callsign_field.text.strip() if hasattr(self, 'callsign_field') else ''
        master_pin = self.setup_pin_field.text.strip() if hasattr(self, 'setup_pin_field') else ''
        confirm_pin = self.setup_confirm_field.text.strip() if hasattr(self, 'setup_confirm_field') else ''
        duress_pin = self.setup_duress_field.text.strip() if hasattr(self, 'setup_duress_field') else ''
        
        if not callsign:
            self.status_label.text = 'Callsign required'
            return
        if not master_pin or len(master_pin) < 4:
            self.status_label.text = 'Master PIN must be >= 4 chars'
            return
        if master_pin != confirm_pin:
            self.status_label.text = 'Master PINs do not match'
            return
        if duress_pin:
            if len(duress_pin) < 4:
                self.status_label.text = 'Duress PIN must be >= 4 chars'
                return
            if duress_pin == master_pin:
                self.status_label.text = 'Duress PIN cannot equal Master PIN'
                return
        else:
            duress_pin = secrets.token_hex(8)
            
        success = self.auth_manager.initialize_pins(master_pin, duress_pin)
        if not success:
            self.status_label.text = 'Failed to initialize credentials'
            return
            
        app = MDApp.get_running_app()
        if app and getattr(app, 'config', None):
            try:
                app.config.set_username(callsign)
            except Exception as e:
                print(f"[LockScreen] Config save username error: {e}")
                
        self.status_label.text = 'Initializing secure node...'
        if app:
            threading.Thread(target=app.post_unlock_startup, args=(master_pin,), daemon=True).start()

    def on_pin_submit(self, *args):
        pin = self.pin_field.text.strip()
        
        if not pin:
            self.status_label.text = 'Please enter a PIN'
            return
        
        pin_type = self.auth_manager.identify_pin(pin)
        
        if pin_type == 'master':
            self.status_label.text = 'Unlocking...'
            app = MDApp.get_running_app()
            # Start database decryption and network boot in background thread
            if app:
                threading.Thread(target=app.post_unlock_startup, args=(pin,), daemon=True).start()
        elif pin_type == 'duress':
            self.trigger_duress_protocol()
        else:
            remaining = max(0, self.auth_manager.max_failed_attempts - self.auth_manager.get_failed_attempts())
            self.status_label.text = f'Invalid PIN ({remaining} attempts remaining)'
            self.pin_field.text = ''
    
    def trigger_duress_protocol(self):
        if self.shredding_in_progress:
            return
        
        self.shredding_in_progress = True
        self.status_label.text = 'Unlocking...'
        self.pin_field.disabled = True
        
        app = MDApp.get_running_app()
        
        def shred_worker():
            try:
                if app:
                    app.decoy_mode = True
                
                import sqlite3
                from security import shred_file
                from database import PersistenceDatabase
                from storage import DatabaseManager
                
                # Activate persistent decoy mode in auth manager
                storage_dir = getattr(self.auth_manager, 'storage_dir', '.')
                if self.auth_manager:
                    self.auth_manager.activate_decoy_mode()
                
                # Securely shred key and config secrets across working dir and storage_dir
                for key_filename in ["secret.key.enc", "secret.key", "signing.key.enc", ".db_salt"]:
                    shred_file(key_filename)
                    if storage_dir and storage_dir != '.':
                        shred_file(os.path.join(storage_dir, key_filename))
                
                # Shred active DB or initialize decoy DB and shred it
                if app and app.persistence_db:
                    app.persistence_db.shred_everything()
                    app.persistence_db.recreate_and_populate_mock_data()
                else:
                    decoy_db = PersistenceDatabase()
                    decoy_db.shred_everything()
                    decoy_db.recreate_and_populate_mock_data()
                    if app:
                        app.persistence_db = decoy_db
                
                audio_manager = get_audio_manager()
                audio_manager.shred_cache()
                
                # Clear and shred telemetry logs
                from telemetry_logger import get_telemetry_logger
                telemetry = get_telemetry_logger()
                with telemetry.buffer_lock:
                    telemetry.buffer.clear()
                shred_file(telemetry.get_log_path())
                
                # Clean DTN spool directories and notes
                shred_file("notes.txt")
                import shutil
                for spool_candidate in ["spool", os.path.expanduser("~/.ghostnet/spool")]:
                    if os.path.exists(spool_candidate):
                        try:
                            shutil.rmtree(spool_candidate)
                        except Exception:
                            pass
                if app and getattr(app, 'engine', None) and getattr(app.engine, 'spool_dir', None):
                    if os.path.exists(app.engine.spool_dir):
                        try:
                            shutil.rmtree(app.engine.spool_dir)
                        except Exception:
                            pass
                
                if hasattr(app, 'crypto_manager') and app.crypto_manager:
                    app.crypto_manager.shred_all_keys()
                
                # Shred storage DB
                try:
                    if app and hasattr(app, 'db_manager') and app.db_manager:
                        app.db_manager.close()
                except:
                    pass
                shred_file("ghostnet.db")
                decoy_storage = DatabaseManager(db_path="ghostnet.db")
                if app:
                    app.db_manager = decoy_storage
                try:
                    decoy_storage.save_peer("192.168.0.100", "Alice")
                    decoy_storage.save_message("192.168.0.100", "PEER", "All quiet here. Stay safe.", "TEXT")
                except Exception as e:
                    print(f"[LockScreen] Decoy storage population error: {e}")
                
                if app:
                    app.start_decoy_simulator()
                Clock.schedule_once(lambda dt: self.show_decoy_radar(), 0)
            except Exception as e:
                print(f"[LockScreen] Shredding error: {e}")
                Clock.schedule_once(lambda dt: self.show_decoy_radar(), 0)
        
        shred_thread = threading.Thread(target=shred_worker, daemon=False)
        shred_thread.start()
    
    def show_decoy_radar(self):
        app = MDApp.get_running_app()
        if app and app.root:
            try:
                # Trigger a radar screen peer refresh with decoy mock data
                app.update_radar_peers({})
                app.root.current = 'radar'
            except Exception as e:
                print(f"[LockScreen] Decoy radar transition error: {e}")
                
    def show_empty_radar(self):
        self.show_decoy_radar()
