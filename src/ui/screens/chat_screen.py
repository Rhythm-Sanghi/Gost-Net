"""
Ghost Net UI - Chat Screen
End-to-end encrypted chat interface with adaptive message bubbles, file progress tracking,
voice messaging, out-of-band TOFU safety verification, and ephemeral TTL scheduling.
"""

import os
import time
import uuid
import threading
import platform
from datetime import datetime
from kivy.core.window import Window
from kivy.properties import StringProperty
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDButton, MDIconButton
from kivymd.uix.card import MDCard

from ui.theme import (
    apply_premium_background,
    MDButtonText,
    MDTextFieldHintText,
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from ui.components.bubbles import MessageBubble, FileBubble, AudioBubble
from audio_manager import get_audio_manager
from android_mocks import get_file_picker


class ChatScreen(MDScreen):
    """Chat interface for messaging with a specific peer with keyboard awareness."""
    
    peer_ip = StringProperty('')
    peer_name = StringProperty('Unknown')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'chat'
        apply_premium_background(self)
        self.file_manager = None
        self.keyboard_height = 0
        self.received_file_bubbles = {}
        self.active_bubbles = {}
        self.ttl_state = 0
        self.ttl_values = [None, 30, 300, 3600]
        self.ttl_labels = ["Off", "30s", "5m", "1h"]
        self.message_expiry_timers = {}
        self.is_recording = False
        self.audio_manager = get_audio_manager()
        self.mic_btn = None
        self.new_msg_badge = None
        self.pending_attachment = None
        
        # Main layout
        layout = MDBoxLayout(orientation='vertical', spacing=dp(10))
        
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(60),
            padding=dp(10),
            spacing=dp(10),
            md_bg_color=(0.1, 0.12, 0.18, 0.65)
        )
        
        back_btn = MDIconButton(
            icon='arrow-left',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1)
        )
        back_btn.bind(on_release=self.go_back)
        
        self.peer_label = MDLabel(
            text="Select a peer",
            font_style='Headline',
            role='small',
            theme_text_color='Primary',
            pos_hint={'center_y': 0.5}
        )
        
        self.ttl_label = MDLabel(
            text="TTL: Off",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_x=None,
            width=dp(64),
            pos_hint={'center_y': 0.5}
        )
        
        self.ttl_btn = MDIconButton(
            icon='clock-outline',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            pos_hint={'center_y': 0.5}
        )
        self.ttl_btn.bind(on_release=self.toggle_ttl)
        
        self.verify_btn = MDIconButton(
            icon='shield-outline',
            theme_icon_color='Custom',
            icon_color=(0.55, 0.7, 0.85, 1),
            pos_hint={'center_y': 0.5}
        )
        self.verify_btn.bind(on_release=self.show_safety_number_dialog)

        header.add_widget(back_btn)
        header.add_widget(self.peer_label)
        header.add_widget(self.verify_btn)
        header.add_widget(Widget(size_hint_x=1))
        header.add_widget(self.ttl_label)
        header.add_widget(self.ttl_btn)
        layout.add_widget(header)

        # Security warning banner for key change detection
        self.security_banner = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(36),
            padding=[dp(12), dp(4), dp(12), dp(4)],
            spacing=dp(6),
            md_bg_color=(0.35, 0.12, 0.12, 0.95),
            opacity=0,
            disabled=True
        )
        self.security_banner_label = MDLabel(
            text="⚠️ Key changed! Public fingerprint differs from saved identity.",
            font_style='Body',
            role='small',
            theme_text_color='Custom',
            text_color=(1, 0.75, 0.6, 1)
        )
        self.security_banner_btn = MDButton(style='text', size_hint_x=None, width=dp(80))
        self.security_banner_btn.add_widget(MDButtonText(text="Inspect"))
        self.security_banner_btn.bind(on_release=self.show_safety_number_dialog)
        self.security_banner.add_widget(self.security_banner_label)
        self.security_banner.add_widget(self.security_banner_btn)
        layout.add_widget(self.security_banner)
        
        # Centered chat container for minimal/modern feel
        self.chat_container = MDBoxLayout(
            orientation='vertical',
            size_hint=(None, 1),
            width=dp(600),
            pos_hint={'center_x': 0.5},
            spacing=dp(10)
        )
        
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
        self.chat_container.add_widget(self.messages_scroll)

        # Subtle "New messages ↓" floating indicator
        self.new_msg_badge = MDButton(
            style='elevated',
            theme_width='Custom',
            size_hint=(None, None),
            size=(dp(140), dp(32)),
            pos_hint={'center_x': 0.5},
            opacity=0,
            disabled=True,
            theme_bg_color='Custom',
            md_bg_color=(0.18, 0.26, 0.38, 0.95)
        )
        new_msg_text = MDButtonText(text="New messages ↓")
        new_msg_text.theme_text_color = 'Custom'
        new_msg_text.text_color = (0.65, 0.79, 0.92, 1)
        self.new_msg_badge.add_widget(new_msg_text)
        self.new_msg_badge.bind(on_release=lambda x: self._scroll_to_bottom())
        self.chat_container.add_widget(self.new_msg_badge)
        self.messages_scroll.bind(scroll_y=self._on_scroll_change)

        layout.add_widget(self.chat_container)
        
        # Input area with keyboard awareness
        self.input_layout = MDCard(
            orientation='horizontal',
            style='outlined',
            adaptive_height=True,
            minimum_height=dp(50),
            padding=[dp(12), dp(4), dp(12), dp(4)],
            spacing=dp(8),
            size_hint_y=None,
            md_bg_color=(0.08, 0.10, 0.14, 0.95),
            line_color=(0.22, 0.28, 0.38, 0.6),
            radius=[dp(6), dp(6), dp(6), dp(6)]
        )
        
        # Attachment button
        attach_btn = MDIconButton(
            icon='paperclip',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=None,
            width=dp(40),
            pos_hint={'center_y': 0.5}
        )
        attach_btn.bind(on_release=self.open_file_picker)
        
        self.message_input = MDTextField(
            mode='outlined',
            size_hint_x=0.55,
            size_hint_y=None,
            height=dp(36),
            pos_hint={'center_y': 0.5}
        )
        self.message_input.add_widget(MDTextFieldHintText(text="Type a message..."))
        self.message_input.bind(on_text_validate=self.send_message)
        
        self.mic_btn = MDIconButton(
            icon='microphone',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=None,
            width=dp(40),
            pos_hint={'center_y': 0.5}
        )
        self.mic_btn.bind(on_touch_down=self.on_mic_touch_down)
        self.mic_btn.bind(on_touch_up=self.on_mic_touch_up)
        
        send_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=0.2,
            size_hint_y=None,
            height=dp(36),
            pos_hint={'center_y': 0.5},
            theme_bg_color='Custom',
            md_bg_color=(0.65, 0.79, 0.92, 1)
        )
        send_text = MDButtonText(text="Send")
        send_text.theme_text_color = 'Custom'
        send_text.text_color = (0.05, 0.06, 0.1, 1)
        send_btn.add_widget(send_text)
        send_btn.bind(on_release=self.send_message)
        
        self.input_layout.add_widget(attach_btn)
        self.input_layout.add_widget(self.message_input)
        self.input_layout.add_widget(self.mic_btn)
        self.input_layout.add_widget(send_btn)

        # Composer container holding preview and input row
        self.composer_box = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(4),
            size_hint_y=None
        )

        # Attachment preview chip (revealed when file is picked)
        self.attachment_preview = MDCard(
            orientation='horizontal',
            style='outlined',
            adaptive_height=True,
            size_hint_y=None,
            height=0,
            opacity=0,
            disabled=True,
            padding=[dp(12), dp(4), dp(8), dp(4)],
            spacing=dp(8),
            md_bg_color=(0.14, 0.18, 0.26, 0.95),
            line_color=(0.3, 0.45, 0.65, 0.6),
            radius=[dp(6), dp(6), dp(6), dp(6)]
        )
        self.attachment_preview_label = MDLabel(
            text="",
            font_style='Body',
            role='small',
            theme_text_color='Custom',
            text_color=(0.75, 0.88, 1.0, 1),
            size_hint_x=0.9,
            pos_hint={'center_y': 0.5}
        )
        remove_attach_btn = MDIconButton(
            icon='close-circle',
            theme_icon_color='Custom',
            icon_color=(0.85, 0.45, 0.45, 1),
            size_hint_x=None,
            width=dp(32),
            pos_hint={'center_y': 0.5}
        )
        remove_attach_btn.bind(on_release=lambda x: self.clear_pending_attachment())
        self.attachment_preview.add_widget(self.attachment_preview_label)
        self.attachment_preview.add_widget(remove_attach_btn)

        self.composer_box.add_widget(self.attachment_preview)
        self.composer_box.add_widget(self.input_layout)
        self.chat_container.add_widget(self.composer_box)
        
        self.add_widget(layout)
        
        # Bind keyboard events for Android
        Window.bind(keyboard_height=self.on_keyboard_height)
        Window.bind(on_keyboard=self.on_keyboard_event)
    
    def on_keyboard_height(self, instance, height):
        """Handle keyboard height changes on Android."""
        self.keyboard_height = height
        if height > 0:
            Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)
    
    def on_keyboard_event(self, instance, key, scancode, codepoint, modifier):
        """Handle keyboard events across desktop (SDL2) and Android."""
        is_enter = (key == 13 or scancode in (40, 66, 88))
        if is_enter and self.message_input.focus:
            if modifier and 'shift' in modifier:
                self.message_input.insert_text('\n')
                return True
            self.send_message()
            return True
        return False
    
    def _on_scroll_change(self, instance, value):
        """Auto-hide the new message indicator if the user scrolls down to bottom."""
        if value <= 0.08 and self.new_msg_badge and self.new_msg_badge.opacity > 0:
            self.new_msg_badge.opacity = 0
            self.new_msg_badge.disabled = True

    def _show_new_message_badge(self):
        """Show subtle badge indicating unread messages below current scroll position."""
        if self.new_msg_badge:
            self.new_msg_badge.opacity = 1
            self.new_msg_badge.disabled = False

    def _scroll_to_bottom(self):
        """Scroll messages to the bottom."""
        try:
            self.messages_scroll.scroll_y = 0
            if self.new_msg_badge:
                self.new_msg_badge.opacity = 0
                self.new_msg_badge.disabled = True
        except Exception as e:
            print(f"[ChatScreen] Error scrolling: {e}")
    
    def set_peer(self, peer_ip, peer_name):
        """Set the current chat peer and load history."""
        self.peer_ip = peer_ip
        self.peer_name = peer_name
        self.clear_pending_attachment()
        
        # Check TOFU verification state
        app = MDApp.get_running_app()
        is_verified = False
        if app and hasattr(app, 'persistence_db') and app.persistence_db:
            try:
                peer_record = app.persistence_db.get_peer(peer_ip)
                if peer_record and peer_record.get('is_verified'):
                    is_verified = True
            except Exception:
                pass

        # Check key mismatch state
        key_mismatch = False
        if app and hasattr(app, 'engine') and app.engine:
            peer_info = app.engine.peers.get(peer_ip, {})
            if peer_info.get('key_mismatch'):
                key_mismatch = True

        if key_mismatch:
            self.security_banner.opacity = 1
            self.security_banner.disabled = False
        else:
            self.security_banner.opacity = 0
            self.security_banner.disabled = True
                
        if is_verified:
            self.peer_label.text = f"{peer_name} [Verified]"
            self.verify_btn.icon = 'shield-check'
            self.verify_btn.icon_color = (0.3, 0.85, 0.4, 1)
        else:
            self.peer_label.text = peer_name
            self.verify_btn.icon = 'shield-outline'
            self.verify_btn.icon_color = (0.55, 0.7, 0.85, 1)
        
        # Clear previous messages
        self.messages_list.clear_widgets()
        
        # Load chat history from database
        self.load_history()

    def show_safety_number_dialog(self, *args):
        """Display 12-digit safety number and key fingerprint for out-of-band identity verification."""
        app = MDApp.get_running_app()
        if not app:
            return

        peer_key = self.peer_ip
        peer_name = self.peer_name or "Unknown Peer"
        
        peer_record = None
        signing_key_bytes = None
        is_verified = False

        if hasattr(app, 'persistence_db') and app.persistence_db:
            try:
                peer_record = app.persistence_db.get_peer(peer_key)
                if peer_record:
                    is_verified = bool(peer_record.get('is_verified', 0))
                    key_b64 = peer_record.get('signing_key')
                    if key_b64:
                        import base64
                        signing_key_bytes = base64.b64decode(key_b64)
            except Exception as e:
                print(f"[ChatScreen] Error querying peer record: {e}")

        # Fallback to crypto_manager in engine
        if not signing_key_bytes and hasattr(app, 'engine') and app.engine and app.engine.crypto_manager:
            signing_key_bytes = app.engine.crypto_manager.get_peer_signing_key(peer_key)

        safety_num = "Key Exchange Pending"
        fingerprint = "No public key registered yet"

        if signing_key_bytes and hasattr(app, 'engine') and app.engine and app.engine.crypto_manager:
            safety_num = app.engine.crypto_manager.compute_safety_number(signing_key_bytes)
            fingerprint = app.engine.crypto_manager.compute_key_fingerprint(signing_key_bytes)

        # Check key mismatch
        peer_info = app.engine.peers.get(peer_key, {}) if (hasattr(app, 'engine') and app.engine) else {}
        is_mismatch = bool(peer_info.get('key_mismatch'))
        untrusted_key = peer_info.get('untrusted_signing_key')

        status_text = "[VERIFIED OUT-OF-BAND]" if is_verified else "[UNVERIFIED (TOFU)]"
        status_color = (0.3, 0.85, 0.4, 1) if is_verified else (0.95, 0.75, 0.25, 1)

        content = MDBoxLayout(orientation='vertical', spacing=dp(10), adaptive_height=True, padding=[dp(12), dp(8), dp(12), dp(8)])
        
        desc = MDLabel(
            text="Verify this 12-digit safety number in person or through an authenticated voice channel to defeat Man-In-The-Middle attacks:",
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            adaptive_height=True
        )
        content.add_widget(desc)

        safety_label = MDLabel(
            text=safety_num,
            font_style='Display',
            role='small',
            halign='center',
            theme_text_color='Custom',
            text_color=(0.3, 0.85, 0.95, 1),
            adaptive_height=True
        )
        content.add_widget(safety_label)

        fp_label = MDLabel(
            text=f"Stored Fingerprint: {fingerprint}",
            font_style='Label',
            role='small',
            theme_text_color='Secondary',
            halign='center',
            adaptive_height=True
        )
        content.add_widget(fp_label)

        if is_mismatch and untrusted_key and hasattr(app, 'engine') and app.engine.crypto_manager:
            untrusted_fp = app.engine.crypto_manager.compute_key_fingerprint(untrusted_key)
            warn_card = MDCard(
                orientation='vertical',
                adaptive_height=True,
                padding=[dp(8), dp(6), dp(8), dp(6)],
                md_bg_color=(0.35, 0.12, 0.12, 0.95),
                line_color=(0.85, 0.3, 0.3, 0.8),
                radius=[dp(4), dp(4), dp(4), dp(4)]
            )
            warn_label = MDLabel(
                text=f"⚠️ KEY MISMATCH DETECTED!\nIncoming beacon fingerprint:\n{untrusted_fp}\ndiffers from registered identity. If the peer re-initialized their identity, verify out-of-band before trusting.",
                font_style='Body',
                role='small',
                theme_text_color='Custom',
                text_color=(1, 0.85, 0.85, 1),
                adaptive_height=True
            )
            warn_card.add_widget(warn_label)
            content.add_widget(warn_card)

        st_label = MDLabel(
            text=f"Identity Status: {status_text}",
            font_style='Body',
            role='medium',
            theme_text_color='Custom',
            text_color=status_color,
            halign='center',
            adaptive_height=True
        )
        content.add_widget(st_label)

        dialog_holder = [None]

        def _toggle_verification(*_):
            new_state = not is_verified
            if hasattr(app, 'persistence_db') and app.persistence_db:
                app.persistence_db.set_peer_verified(peer_key, new_state)
            if new_state:
                self.peer_label.text = f"{peer_name} [Verified]"
                self.verify_btn.icon = 'shield-check'
                self.verify_btn.icon_color = (0.3, 0.85, 0.4, 1)
            else:
                self.peer_label.text = peer_name
                self.verify_btn.icon = 'shield-outline'
                self.verify_btn.icon_color = (0.55, 0.7, 0.85, 1)
            if dialog_holder[0]:
                dialog_holder[0].dismiss()

        def _accept_new_key(*_):
            if is_mismatch and untrusted_key and hasattr(app, 'engine') and app.engine.crypto_manager:
                app.engine.crypto_manager.force_update_peer_signing_key(peer_key, untrusted_key)
                import base64
                new_b64 = base64.b64encode(untrusted_key).decode('utf-8')
                if hasattr(app, 'persistence_db') and app.persistence_db:
                    app.persistence_db.save_peer(peer_key, peer_name, signing_key_b64=new_b64)
                peer_info['key_mismatch'] = False
                peer_info.pop('untrusted_signing_key', None)
                self.security_banner.opacity = 0
                self.security_banner.disabled = True
            if dialog_holder[0]:
                dialog_holder[0].dismiss()

        action_btn_text = "Revoke Verification" if is_verified else "Mark as Verified"
        action_btn_style = "tonal" if is_verified else "filled"

        btn_container = MDDialogButtonContainer(
            MDButton(
                MDButtonText(text="Close"),
                style="text",
                on_release=lambda x: dialog_holder[0].dismiss() if dialog_holder[0] else None
            ),
            MDButton(
                MDButtonText(text=action_btn_text),
                style=action_btn_style,
                on_release=_toggle_verification
            )
        )
        if is_mismatch and untrusted_key:
            trust_btn = MDButton(
                MDButtonText(text="Trust New Key"),
                style="filled",
                theme_bg_color="Custom",
                md_bg_color=(0.75, 0.25, 0.25, 1),
                on_release=_accept_new_key
            )
            btn_container.add_widget(trust_btn)

        dialog = MDDialog(
            MDDialogHeadlineText(text=f"Safety Number - {peer_name}"),
            MDDialogContentContainer(content, orientation="vertical"),
            btn_container
        )
        dialog_holder[0] = dialog
        dialog.open()
    
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
            empty_box = MDBoxLayout(
                orientation='vertical',
                adaptive_height=True,
                spacing=dp(6),
                padding=[dp(16), dp(32), dp(16), dp(16)],
                pos_hint={'center_x': 0.5}
            )
            empty_title = MDLabel(
                text="End-to-End Encrypted Session",
                font_style="Title",
                role="small",
                halign="center",
                theme_text_color="Primary"
            )
            empty_sub = MDLabel(
                text=f"Direct node: {self.peer_name}\nAddress: {self.peer_ip}\nDouble Ratchet cryptographic channel active.",
                font_style="Body",
                role="small",
                halign="center",
                theme_text_color="Secondary"
            )
            empty_box.add_widget(empty_title)
            empty_box.add_widget(empty_sub)
            self.empty_session_notice = empty_box
            self.messages_list.add_widget(empty_box)
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
    
    def clear_pending_attachment(self):
        """Clear currently queued attachment."""
        self.pending_attachment = None
        if hasattr(self, 'attachment_preview') and self.attachment_preview:
            self.attachment_preview.opacity = 0
            self.attachment_preview.height = 0
            self.attachment_preview.disabled = True

    def send_message(self, *args):
        """Send queued text or attachment to the current peer."""
        has_attachment = bool(self.pending_attachment)
        message_text = self.message_input.text.strip()
        
        if not has_attachment and not message_text:
            return
            
        if not self.peer_ip:
            print("[ChatScreen] No peer selected")
            return
            
        if has_attachment:
            file_to_send = self.pending_attachment
            self.clear_pending_attachment()
            self._dispatch_file_send(file_to_send)
            if message_text:
                self.message_input.text = ''
                self._dispatch_text_send(message_text)
        else:
            self.message_input.text = ''
            self._dispatch_text_send(message_text)

    def _dispatch_text_send(self, message_text):
        """Dispatch text message asynchronously without UI freeze."""
        app = MDApp.get_running_app()
        if not app:
            return
            
        if hasattr(self, 'empty_session_notice') and self.empty_session_notice:
            if self.empty_session_notice in self.messages_list.children:
                self.messages_list.remove_widget(self.empty_session_notice)
            self.empty_session_notice = None
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_id = uuid.uuid4().hex[:12]
        current_ttl = self.ttl_values[self.ttl_state]
        
        bubble = MessageBubble(
            message_text,
            timestamp,
            is_sent=True,
            msg_id=msg_id,
            status="Sending...",
            retry_callback=self.retry_message
        )
        self.messages_list.add_widget(bubble)
        self.active_bubbles[msg_id] = bubble
        
        if current_ttl:
            expires_at = time.time() + current_ttl
            self._schedule_bubble_expiry(bubble, expires_at)
            
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.1)

        if app.decoy_mode:
            if app.persistence_db:
                app.persistence_db.save_message(self.peer_ip, "me", "text", message_text)
            bubble.set_delivery_status("DELIVERED")
            self.trigger_decoy_reply(self.peer_ip, message_text)
            return

        if not app.engine:
            print("[ChatScreen] Engine not available")
            bubble.set_delivery_status("FAILED")
            return

        target_ip = self.peer_ip
        def send_worker():
            def on_status(mid, st):
                Clock.schedule_once(lambda dt: bubble.set_delivery_status(st), 0)
            try:
                res = app.engine.send_message(
                    target_ip,
                    message_text,
                    ttl=current_ttl,
                    msg_id=msg_id,
                    delivery_callback=on_status,
                    return_result=True
                )
                final_status = "DELIVERED" if getattr(res, 'status', None) == "DELIVERED" else ("SENT_TO_PEER" if res else "FAILED")
                Clock.schedule_once(lambda dt: bubble.set_delivery_status(final_status), 0)
            except Exception as e:
                print(f"[ChatScreen] Async send error: {e}")
                Clock.schedule_once(lambda dt: bubble.set_delivery_status("FAILED"), 0)

        threading.Thread(target=send_worker, daemon=True).start()

    def retry_message(self, msg_id, message_text):
        """Retry sending a previously failed message with the same msg_id."""
        app = MDApp.get_running_app()
        if not app or not app.engine or not self.peer_ip:
            return
            
        bubble = self.active_bubbles.get(msg_id)
        if bubble:
            bubble.set_delivery_status("SENDING")
            
        current_ttl = self.ttl_values[self.ttl_state]
        target_ip = self.peer_ip
        def retry_worker():
            def on_status(mid, st):
                if bubble:
                    Clock.schedule_once(lambda dt: bubble.set_delivery_status(st), 0)
            try:
                res = app.engine.send_message(
                    target_ip,
                    message_text,
                    ttl=current_ttl,
                    msg_id=msg_id,
                    delivery_callback=on_status,
                    return_result=True
                )
                final_status = "DELIVERED" if getattr(res, 'status', None) == "DELIVERED" else ("SENT_TO_PEER" if res else "FAILED")
                if bubble:
                    Clock.schedule_once(lambda dt: bubble.set_delivery_status(final_status), 0)
            except Exception as e:
                print(f"[ChatScreen] Retry send error: {e}")
                if bubble:
                    Clock.schedule_once(lambda dt: bubble.set_delivery_status("FAILED"), 0)

        threading.Thread(target=retry_worker, daemon=True).start()

    def update_delivery_status(self, msg_id, status):
        """Update delivery status on active message bubble."""
        bubble = self.active_bubbles.get(msg_id)
        if bubble:
            bubble.set_delivery_status(status)

    def trigger_decoy_reply(self, peer_ip, user_message):
        Clock.schedule_once(lambda dt: self._generate_decoy_reply(peer_ip, user_message), 1.5)

    def _generate_decoy_reply(self, peer_ip, user_message):
        app = MDApp.get_running_app()
        if not app or not app.decoy_mode:
            return
            
        responses = {
            "wfd_alice": [
                "Copy that. We are monitoring the frequencies.",
                "Understood. Maintain radio silence if possible.",
                "Got it. Update me if anything changes.",
                "Affirmative. Base is secure for now."
            ],
            "bt_bob": [
                "Understood. Moving to the rendezvous point now.",
                "Roger. See you at the coordinates.",
                "Acknowledged. Bringing the extra supplies.",
                "Copy. Bob out."
            ],
            "mesh_charlie": [
                "Understood. Mesh routing is stable.",
                "Roger, copying telemetry logs.",
                "Acknowledged. Relay node is fully operational.",
                "Copy that. Keeping packets flowing."
            ]
        }
        
        import random
        peer_responses = responses.get(peer_ip, [
            "Message received. Connection stable.",
            "Acknowledged. All systems green.",
            "Copy that. Understood."
        ])
        reply_text = random.choice(peer_responses)
        
        if app.persistence_db:
            app.persistence_db.save_message(peer_ip, "peer", "text", reply_text)
            
        if self.peer_ip == peer_ip:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.add_received_message(peer_ip, reply_text, timestamp)
    
    def add_received_message(self, sender_ip, message_text, timestamp, expires_at=None):
        if sender_ip == self.peer_ip:
            bubble = MessageBubble(message_text, timestamp, is_sent=False)
            self.messages_list.add_widget(bubble)
            
            if expires_at:
                self._schedule_bubble_expiry(bubble, expires_at)
            
            # Smart auto-scroll: if operator is reading backlog, show badge instead
            if self.messages_scroll.scroll_y <= 0.08:
                Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)
            else:
                self._show_new_message_badge()
    
    def open_file_picker(self, *args):
        """Open native file picker with fallback to MDFileManager."""
        try:
            file_picker = get_file_picker()
            
            if hasattr(file_picker, 'pick_file'):
                file_path = file_picker.pick_file()
                if file_path:
                    self.select_file(file_path)
                    return
            
            from kivymd.uix.filemanager import MDFileManager
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
        """Stage file attachment for inspection/captioning before sending."""
        self.exit_file_manager()
        
        if not path or not os.path.isfile(path):
            print(f"[ChatScreen] Not a valid file: {path}")
            return
            
        filesize = os.path.getsize(path)
        if filesize == 0:
            print("[ChatScreen] Cannot attach empty 0-byte file")
            return
            
        filename = os.path.basename(path)
        if filesize > 1024 * 1024:
            size_str = f"{filesize / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{filesize / 1024:.1f} KB"
            
        self.pending_attachment = path
        if hasattr(self, 'attachment_preview') and self.attachment_preview:
            self.attachment_preview_label.text = f"📎 {filename} ({size_str})"
            self.attachment_preview.height = dp(36)
            self.attachment_preview.opacity = 1
            self.attachment_preview.disabled = False

    def _dispatch_file_send(self, path):
        """Send file with progress bubble and async worker."""
        filename = os.path.basename(path)
        filesize = os.path.getsize(path)
        
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
        
        target_ip = self.peer_ip
        def file_worker():
            try:
                app.engine.send_file(target_ip, path, progress_callback=progress_callback)
            except Exception as e:
                print(f"[ChatScreen] Async send file error: {e}")
                
        threading.Thread(target=file_worker, daemon=True).start()
        
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.1)
    
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
            
        if hasattr(self, 'ttl_label') and self.ttl_label:
            self.ttl_label.text = f"TTL: {label}"
        
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
