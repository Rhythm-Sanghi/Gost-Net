"""
Ghost Net UI - Message, File, and Audio Bubbles
Custom styled chat cards with responsive widths, delivery states, audio playback,
and interactive file progress indicators.
"""

import os
import sys
import platform
from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDIconButton

from ui.theme import MDButtonText, MDProgressBar
from audio_manager import get_audio_manager


class MessageBubble(MDCard):
    """Message bubble with text wrapping and delivery status lifecycle."""
    
    def __init__(self, message, timestamp, is_sent=False, status="", msg_id="", retry_callback=None, **kwargs):
        super().__init__(**kwargs)
        
        self.message = message
        self.timestamp = timestamp
        self.is_sent = is_sent
        self.msg_id = msg_id
        self.retry_callback = retry_callback
        
        self.style = 'outlined'
        self.adaptive_height = True
        self.size_hint_y = None
        self.minimum_height = dp(46)
        self.padding = [dp(12), dp(8), dp(12), dp(8)]
        self.spacing = dp(2)
        
        msg_len = len(message)
        if is_sent:
            self.md_bg_color = (0.16, 0.24, 0.36, 0.85)
            self.line_color = (0.28, 0.40, 0.56, 0.45)
            self.radius = [dp(10), dp(10), dp(2), dp(10)]
            self.pos_hint = {'right': 0.96}
        else:
            self.md_bg_color = (0.10, 0.12, 0.16, 0.85)
            self.line_color = (0.22, 0.26, 0.34, 0.45)
            self.radius = [dp(10), dp(10), dp(10), dp(2)]
            self.pos_hint = {'x': 0.04}

        if msg_len < 16:
            self.size_hint_x = None
            self.width = dp(max(130, msg_len * 9 + 60))
        elif msg_len < 40:
            self.size_hint_x = None
            self.width = dp(min(320, msg_len * 7.5 + 60))
        else:
            self.size_hint_x = 0.75
        
        layout = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(3),
            size_hint_y=None
        )
        
        self.msg_label = MDLabel(
            text=message,
            font_style='Body',
            role='medium',
            theme_text_color='Primary',
            adaptive_height=True,
            size_hint_y=None
        )
        # Enable word wrapping bounded by bubble width
        def _update_label_wrap(inst, width):
            inst.text_size = (max(width - dp(24), dp(80)), None)
        self.bind(width=_update_label_wrap)
        self.msg_label.bind(texture_size=self.msg_label.setter('size'))
        
        meta_row = MDBoxLayout(
            orientation='horizontal',
            adaptive_height=True,
            size_hint_y=None,
            height=dp(18),
            spacing=dp(6)
        )
        
        self.time_label = MDLabel(
            text=timestamp,
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            halign='right',
            size_hint_x=1
        )
        
        self.status_label = None
        self.retry_btn = None
        
        if is_sent:
            self.status_label = MDLabel(
                text=status or "Sent to peer",
                font_style='Body',
                role='small',
                theme_text_color='Custom',
                text_color=(0.65, 0.79, 0.92, 0.9),
                halign='right',
                size_hint_x=None,
                width=dp(90)
            )
            meta_row.add_widget(self.status_label)
            
        meta_row.add_widget(self.time_label)
        
        layout.add_widget(self.msg_label)
        layout.add_widget(meta_row)
        layout.bind(size=self.setter('height'))
        
        self.add_widget(layout)

    def set_delivery_status(self, status: str):
        if not self.is_sent or not self.status_label:
            return
        status_map = {
            "SENDING": ("Sending...", (0.7, 0.7, 0.7, 1)),
            "SENT_TO_PEER": ("Sent to peer", (0.65, 0.79, 0.92, 0.9)),
            "DELIVERED": ("Delivered", (0.35, 0.85, 0.55, 1)),
            "FAILED": ("Failed ↻", (0.95, 0.40, 0.40, 1)),
            "QUEUED": ("Queued", (0.85, 0.75, 0.35, 1))
        }
        text, color = status_map.get(status, (status, (0.65, 0.79, 0.92, 0.9)))
        self.status_label.text = text
        self.status_label.text_color = color
        if status == "FAILED" and self.retry_callback:
            self.status_label.bind(on_touch_down=self._on_status_tap)

    def _on_status_tap(self, instance, touch):
        if self.collide_point(*touch.pos) and self.retry_callback:
            self.set_delivery_status("SENDING")
            self.retry_callback(self.msg_id, self.message)
            return True
        return False


class FileBubble(MDCard):
    """Custom file bubble widget for file transfers with progress bar."""
    
    def __init__(self, filename, filepath, timestamp, is_sent=False, **kwargs):
        super().__init__(**kwargs)
        
        self.filename = filename
        self.filepath = filepath
        self.is_sent = is_sent
        self.progress = 0.0
        
        self.style = 'outlined'
        self.adaptive_height = True
        self.size_hint_y = None
        self.minimum_height = dp(110)
        self.padding = dp(12)
        
        if is_sent:
            self.md_bg_color = (0.18, 0.3, 0.5, 0.7)
            self.line_color = (0.3, 0.45, 0.6, 0.35)
            self.radius = [dp(16), dp(16), dp(2), dp(16)]
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.75
        else:
            self.md_bg_color = (0.08, 0.1, 0.14, 0.6)
            self.line_color = (0.2, 0.25, 0.35, 0.25)
            self.radius = [dp(16), dp(16), dp(16), dp(2)]
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
        self.state_label = MDLabel(
            text="Completed ✓" if (not is_sent or (filepath and os.path.exists(filepath))) else "Queued",
            font_style='Body',
            role='small',
            theme_text_color='Custom',
            text_color=(0.35, 0.85, 0.55, 1) if (not is_sent or (filepath and os.path.exists(filepath))) else (0.7, 0.7, 0.7, 1),
            size_hint_x=0.5
        )
        button_row.add_widget(self.state_label)
        button_row.add_widget(time_label)
        
        main_layout.add_widget(file_row)
        if self.progress_bar:
            main_layout.add_widget(self.progress_bar)
        main_layout.add_widget(button_row)
        main_layout.bind(size=self.setter('height'))
        
        self.add_widget(main_layout)
    
    def update_progress(self, bytes_sent, total_size):
        """Update progress bar and byte state label (thread-safe via Clock)."""
        if total_size <= 0:
            return
        
        progress_percent = min(100.0, (bytes_sent / total_size) * 100)
        sent_str = self._format_file_size(bytes_sent)
        total_str = self._format_file_size(total_size)
        
        def _update(dt):
            if self.progress_bar:
                self.progress_bar.value = progress_percent
            if hasattr(self, 'state_label') and self.state_label:
                if progress_percent >= 100:
                    self.state_label.text = f"Completed ✓ ({total_str})"
                    self.state_label.text_color = (0.35, 0.85, 0.55, 1)
                else:
                    self.state_label.text = f"{progress_percent:.0f}% ({sent_str}/{total_str})"
                    self.state_label.text_color = (0.65, 0.79, 0.92, 0.9)
        Clock.schedule_once(_update, 0)
    
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
        
        self.style = 'outlined'
        self.adaptive_height = True
        self.size_hint_y = None
        self.minimum_height = dp(90)
        self.padding = dp(12)
        
        if is_sent:
            self.md_bg_color = (0.18, 0.3, 0.5, 0.7)
            self.line_color = (0.3, 0.45, 0.6, 0.35)
            self.radius = [dp(16), dp(16), dp(2), dp(16)]
            self.pos_hint = {'right': 0.95}
            self.size_hint_x = 0.75
        else:
            self.md_bg_color = (0.08, 0.1, 0.14, 0.6)
            self.line_color = (0.2, 0.25, 0.35, 0.25)
            self.radius = [dp(16), dp(16), dp(16), dp(2)]
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
        self.play_btn_text = MDButtonText(text="Play")
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
            self.play_btn_text.text = "Play"
        else:
            if self.filepath and os.path.exists(self.filepath):
                success = self.audio_manager.play_audio(self.filepath)
                if success:
                    self.is_playing = True
                    self.play_btn_text.text = "Stop"
            else:
                print(f"[AudioBubble] File not found: {self.filepath}")
    
    def _update_progress(self, progress):
        self.playback_progress = progress
        if self.progress_bar:
            self.progress_bar.value = progress
    
    def _on_playback_complete(self):
        self.is_playing = False
        self.play_btn_text.text = "Play"
        if self.progress_bar:
            self.progress_bar.value = 0
