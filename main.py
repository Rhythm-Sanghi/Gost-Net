"""
Ghost Net - Main Application
Material Design P2P messaging app using KivyMD.
Offline-first, local network communication with file transfer support.
"""

# Safe imports with error handling for Android compatibility
try:
    from kivymd.app import MDApp
    from kivy.metrics import dp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.screenmanager import MDScreenManager
    from kivymd.uix.list import MDListItem, MDListItemHeadlineText, MDListItemSupportingText
    from kivymd.uix.button import MDButton, MDButtonText, MDIconButton, MDFabButton
    from kivymd.uix.textfield import MDTextField, MDTextFieldHintText, MDTextFieldHelperText
    from kivymd.uix.label import MDLabel
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.scrollview import MDScrollView
    from kivymd.uix.card import MDCard
    from kivymd.uix.filemanager import MDFileManager
    from kivymd.uix.slider import MDSlider
    from kivymd.uix.switch import MDSwitch
    from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogContentContainer, MDDialogButtonContainer
    from kivymd.uix.spinner import MDSpinner
    KIVYMD_AVAILABLE = True
except ImportError as e:
    print(f"[CRITICAL] KivyMD import failed: {e}")
    print("[CRITICAL] Please ensure KivyMD v1.1.1 is properly installed")
    print("[CRITICAL] Run: pip install kivymd==1.1.1")
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
from config import get_config


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


class RadarScreen(MDScreen):
    """Home screen showing discovered peers with radar animation."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'radar'
        
        # Main layout
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
            size_hint_x=0.8
        )
        
        settings_btn = MDIconButton(
            icon='cog',
            size_hint_x=0.2
        )
        settings_btn.bind(on_release=self.open_settings)
        
        header.add_widget(title)
        header.add_widget(settings_btn)
        layout.add_widget(header)
        
        # Radar animation
        self.radar = RadarWidget(size_hint=(1, 0.4))
        layout.add_widget(self.radar)
        
        # Status label
        self.status_label = MDLabel(
            text="Scanning for peers...",
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='large'
        )
        layout.add_widget(self.status_label)
        
        # Peers list
        peers_label = MDLabel(
            text="Discovered Peers",
            font_style='Title',
            role='large',
            padding=(dp(10), dp(10))
        )
        layout.add_widget(peers_label)
        
        # Scrollable list container
        self.peers_scroll = MDScrollView(size_hint=(1, 1))
        self.peers_list = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(5)
        )
        self.peers_scroll.add_widget(self.peers_list)
        layout.add_widget(self.peers_scroll)
        
        self.add_widget(layout)
    
    def update_peers(self, peers_dict):
        """Update the peers list (called from main thread via Clock)."""
        self.peers_list.clear_widgets()
        
        if not peers_dict:
            self.status_label.text = "No peers found. Waiting..."
            return
        
        self.status_label.text = f"Found {len(peers_dict)} peer(s)"
        
        for ip, info in peers_dict.items():
            username = info['username']
            
            # Create list item
            item = MDCard(
                style='elevated',
                padding=dp(10),
                size_hint_y=None,
                height=dp(60),
                md_bg_color=(0.1, 0.1, 0.15, 1)
            )
            
            item_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10))
            
            # Peer info
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
            
            # Chat button
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
    
    def open_settings(self, *args):
        """Navigate to settings screen."""
        app = MDApp.get_running_app()
        app.root.current = 'settings'


class MessageBubble(MDCard):
    """Custom message bubble widget for text messages."""
    
    def __init__(self, message, timestamp, is_sent=False, **kwargs):
        super().__init__(**kwargs)
        
        self.style = 'elevated'
        self.size_hint_y = None
        self.height = dp(60)
        self.padding = dp(10)
        
        # Color coding: sent (blue) vs received (grey)
        if is_sent:
            self.md_bg_color = (0.2, 0.4, 0.8, 1)
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.7
        else:
            self.md_bg_color = (0.3, 0.3, 0.3, 1)
            self.pos_hint = {'x': 0.05}
            self.size_hint_x = 0.7
        
        layout = MDBoxLayout(orientation='vertical', spacing=dp(5))
        
        msg_label = MDLabel(
            text=message,
            font_style='Body',
            role='large',
            theme_text_color='Primary'
        )
        
        time_label = MDLabel(
            text=timestamp,
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            halign='right'
        )
        
        layout.add_widget(msg_label)
        layout.add_widget(time_label)
        self.add_widget(layout)


class FileBubble(MDCard):
    """Custom file bubble widget for file transfers."""
    
    def __init__(self, filename, filepath, timestamp, is_sent=False, **kwargs):
        super().__init__(**kwargs)
        
        self.filename = filename
        self.filepath = filepath
        
        self.style = 'elevated'
        self.size_hint_y = None
        self.height = dp(80)
        self.padding = dp(10)
        
        # Color coding: sent (blue) vs received (grey)
        if is_sent:
            self.md_bg_color = (0.2, 0.4, 0.8, 1)
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.75
        else:
            self.md_bg_color = (0.3, 0.3, 0.3, 1)
            self.pos_hint = {'x': 0.05}
            self.size_hint_x = 0.75
        
        main_layout = MDBoxLayout(orientation='vertical', spacing=dp(5))
        
        # File info row
        file_row = MDBoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(40))
        
        # File icon
        icon = MDIconButton(
            icon=self._get_file_icon(filename),
            theme_icon_color='Custom',
            icon_color=(1, 1, 1, 1)
        )
        
        # File details
        file_info = MDBoxLayout(orientation='vertical', spacing=dp(2))
        
        name_label = MDLabel(
            text=filename,
            font_style='Body',
            role='large',
            theme_text_color='Primary'
        )
        
        # Get file size if available
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
        
        # Button row
        button_row = MDBoxLayout(orientation='horizontal', spacing=dp(5), size_hint_y=None, height=dp(30))
        
        # Open button (only for received files)
        if not is_sent and filepath and os.path.exists(filepath):
            open_btn = MDButton(style='text', size_hint_x=0.5)
            open_btn.add_widget(MDButtonText(text="Open"))
            open_btn.bind(on_release=lambda x: self.open_file())
            button_row.add_widget(open_btn)
        
        # Timestamp
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
        main_layout.add_widget(button_row)
        self.add_widget(main_layout)
    
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


class ChatScreen(MDScreen):
    """Chat interface for messaging with a specific peer."""
    
    peer_ip = StringProperty('')
    peer_name = StringProperty('Unknown')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'chat'
        self.file_manager = None
        
        # Main layout
        layout = MDBoxLayout(orientation='vertical', spacing=dp(10))
        
        # Header with back button
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
        
        header.add_widget(back_btn)
        header.add_widget(self.peer_label)
        layout.add_widget(header)
        
        # Messages area
        self.messages_scroll = MDScrollView(size_hint=(1, 1))
        self.messages_list = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(10),
            padding=dp(10)
        )
        self.messages_scroll.add_widget(self.messages_list)
        layout.add_widget(self.messages_scroll)
        
        # Input area
        input_layout = MDBoxLayout(
            size_hint_y=None,
            height=dp(60),
            padding=dp(10),
            spacing=dp(10)
        )
        
        # Attachment button
        attach_btn = MDIconButton(
            icon='paperclip',
            size_hint_x=None,
            width=dp(40)
        )
        attach_btn.bind(on_release=self.open_file_picker)
        
        self.message_input = MDTextField(
            mode='outlined',
            size_hint_x=0.7
        )
        self.message_input.add_widget(MDTextFieldHintText(text="Type a message..."))
        
        send_btn = MDButton(
            style='elevated',
            size_hint_x=0.2
        )
        send_btn.add_widget(MDButtonText(text="Send"))
        send_btn.bind(on_release=self.send_message)
        
        input_layout.add_widget(attach_btn)
        input_layout.add_widget(self.message_input)
        input_layout.add_widget(send_btn)
        layout.add_widget(input_layout)
        
        self.add_widget(layout)
    
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
        
        if not app or not app.engine or not app.engine.db_manager:
            print("[ChatScreen] No database manager available")
            return
        
        if not self.peer_ip:
            print("[ChatScreen] No peer IP set")
            return
        
        try:
            # Get history from database
            messages = app.engine.db_manager.get_history(self.peer_ip, limit=100)
            
            print(f"[ChatScreen] Loading {len(messages)} messages from history")
            
            # Add messages to UI
            for msg in messages:
                is_sent = (msg['sender'] == 'ME')
                
                # Format timestamp
                dt = datetime.fromtimestamp(msg['timestamp'])
                timestamp = dt.strftime("%H:%M:%S")
                
                if msg['message_type'] == 'TEXT':
                    # Text message bubble
                    bubble = MessageBubble(msg['content'], timestamp, is_sent=is_sent)
                    self.messages_list.add_widget(bubble)
                elif msg['message_type'] == 'FILE':
                    # File bubble
                    file_path = msg.get('file_path')
                    bubble = FileBubble(msg['content'], file_path, timestamp, is_sent=is_sent)
                    self.messages_list.add_widget(bubble)
            
            # Scroll to bottom
            Clock.schedule_once(lambda dt: setattr(
                self.messages_scroll, 'scroll_y', 0
            ), 0.1)
            
        except Exception as e:
            print(f"[ChatScreen] Error loading history: {e}")
    
    def send_message(self, *args):
        """Send a message to the current peer."""
        message_text = self.message_input.text.strip()
        
        if not message_text or not self.peer_ip:
            return
        
        app = MDApp.get_running_app()
        
        # Send via network engine
        if not app or not app.engine:
            print("[ChatScreen] Engine not available")
            return
        
        success = app.engine.send_message(self.peer_ip, message_text)
        
        if success:
            # Add to UI as sent message
            timestamp = datetime.now().strftime("%H:%M:%S")
            bubble = MessageBubble(message_text, timestamp, is_sent=True)
            self.messages_list.add_widget(bubble)
            
            # Clear input
            self.message_input.text = ''
            
            # Scroll to bottom
            Clock.schedule_once(lambda dt: setattr(
                self.messages_scroll, 'scroll_y', 0
            ), 0.1)
    
    def add_received_message(self, sender_ip, message_text, timestamp):
        """Add a received message to the chat (called from main thread)."""
        # Only add if we're chatting with this peer
        if sender_ip == self.peer_ip:
            bubble = MessageBubble(message_text, timestamp, is_sent=False)
            self.messages_list.add_widget(bubble)
            
            # Scroll to bottom
            Clock.schedule_once(lambda dt: setattr(
                self.messages_scroll, 'scroll_y', 0
            ), 0.1)
    
    def open_file_picker(self, *args):
        """Open file manager for file selection."""
        if not self.file_manager:
            self.file_manager = MDFileManager(
                exit_manager=self.exit_file_manager,
                select_path=self.select_file
            )
        
        # Start from user's home directory or storage - Bug #6 fix
        start_path = os.path.expanduser("~")  # Default to home
        
        if platform.system() == 'Android':
            # On Android, try common storage paths with fallback
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
                print(f"[ChatScreen] File manager failed even with home dir: {e2}")
    
    def exit_file_manager(self, *args):
        """Close the file manager."""
        if self.file_manager:
            self.file_manager.close()
    
    def select_file(self, path):
        """Handle file selection."""
        self.exit_file_manager()
        
        if not os.path.isfile(path):
            print(f"[ChatScreen] Not a file: {path}")
            return
        
        if not self.peer_ip:
            print(f"[ChatScreen] No peer selected")
            return
        
        # Get file info
        filename = os.path.basename(path)
        filesize = os.path.getsize(path)
        
        print(f"[ChatScreen] Sending file: {filename} ({filesize} bytes)")
        
        # Send file via network engine
        app = MDApp.get_running_app()
        if not app or not app.engine:
            print("[ChatScreen] Engine not available")
            return
        app.engine.send_file(self.peer_ip, path)
        
        # Add to UI as sent file bubble
        timestamp = datetime.now().strftime("%H:%M:%S")
        bubble = FileBubble(filename, path, timestamp, is_sent=True)
        self.messages_list.add_widget(bubble)
        
        # Scroll to bottom
        Clock.schedule_once(lambda dt: setattr(
            self.messages_scroll, 'scroll_y', 0
        ), 0.1)
    
    def add_received_file(self, sender_ip, filename, filepath, timestamp):
        """Add a received file to the chat (called from main thread)."""
        # Only add if we're chatting with this peer
        if sender_ip == self.peer_ip:
            bubble = FileBubble(filename, filepath, timestamp, is_sent=False)
            self.messages_list.add_widget(bubble)
            
            # Scroll to bottom
            Clock.schedule_once(lambda dt: setattr(
                self.messages_scroll, 'scroll_y', 0
            ), 0.1)
    
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
        
        # First confirmation
        dialog = MDDialog(
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
                    on_release=lambda x: dialog.dismiss()
                ),
                MDButton(
                    MDButtonText(text="Continue"),
                    style="elevated",
                    theme_bg_color='Custom',
                    md_bg_color=(0.8, 0.5, 0.2, 1),
                    on_release=lambda x: confirm_panic(dialog)
                ),
                spacing=dp(8)
            )
        )
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
            app.config.delete_config()
            print("[PANIC MODE] Config deleted")
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
    
    def build(self):
        """Build the app UI."""
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        
        # Create screen manager with all screens
        sm = MDScreenManager()
        sm.add_widget(BootScreen())
        sm.add_widget(RadarScreen())
        sm.add_widget(ChatScreen())
        sm.add_widget(SettingsScreen())
        
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
        
        # Start on boot screen
        try:
            self.root.current = 'boot'
        except Exception as e:
            print(f"[GhostNet] Error switching to boot screen: {e}")
        
        # Run startup checks in background
        threading.Thread(target=self.startup_checks, daemon=True).start()
    
    def startup_checks(self):
        """
        Perform startup initialization in background thread.
        Updates boot screen status and transitions to radar when complete.
        """
        # Safely get boot screen with error handling
        try:
            boot_screen = self.root.get_screen('boot')
            if not boot_screen:
                print("[GhostNet] Boot screen not available")
                return
        except Exception as e:
            print(f"[GhostNet] Error accessing boot screen: {e}")
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
            
            # Step 3: Initialize database
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Initializing database..."),
                0
            )
            time.sleep(0.5)
            
            # Step 4: Start network engine
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
                    enable_storage=True
                )
                
                # Start engine in background
                threading.Thread(target=self.engine.start, daemon=True).start()
                time.sleep(1.0)
            except Exception as e:
                print(f"[GhostNet] Engine initialization error: {e}")
                self.engine = None
                # Continue - app can work without networking
            
            # Step 5: Run privacy cleanup
            Clock.schedule_once(
                lambda dt: boot_screen.update_status("Cleaning old messages..."),
                0
            )
            
            # Check if config is available before using it (Bug #11)
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
            
            # Transition to radar screen
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
            # Always transition to radar screen even on error
            try:
                Clock.schedule_once(
                    lambda dt: setattr(self.root, 'current', 'radar'),
                    0
                )
            except Exception as e2:
                print(f"[GhostNet] Could not transition to radar: {e2}")
    
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
        
        # Run in background thread
        threading.Thread(target=_cleanup_worker, daemon=True).start()
    
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
        """Update radar screen with peer list (main thread)."""
        radar_screen = self.root.get_screen('radar')
        radar_screen.update_peers(peers_dict)
    
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
            username = self.engine.get_peer_username(sender_ip)
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
            username = self.engine.get_peer_username(sender_ip)
            print(f"[Notification] File received from {username}: {filename}")


if __name__ == '__main__':
    GhostNetApp().run()