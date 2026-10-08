"""
Ghost Net UI - Notes Screen
Collaborative distributed offline markdown/text notepad with CRDT line-merge sync.
"""

import os
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDIconButton

from ui.theme import apply_premium_background


class NotesScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'notes'
        apply_premium_background(self)
        self.notes_file = "notes.txt"
        
        root_layout = MDFloatLayout(size_hint=(1, 1))
        
        layout = MDBoxLayout(
            orientation='vertical',
            padding=dp(20),
            spacing=dp(10),
            size_hint=(1, 1),
            pos_hint={'center_x': 0.5}
        )
        
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(60),
            spacing=dp(10)
        )
        
        back_btn = MDIconButton(
            icon='arrow-left',
            theme_icon_color='Custom',
            icon_color=(0.627, 0.631, 0.604, 1)
        )
        back_btn.bind(on_release=self.go_back)
        
        title = MDLabel(
            text='03 / FIELD NOTEPAD',
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            pos_hint={'center_y': 0.5}
        )
        
        sync_btn = MDIconButton(
            icon='sync',
            theme_icon_color='Custom',
            icon_color=(0.24, 0.44, 0.64, 1.0)
        )
        sync_btn.bind(on_release=self.sync_notes)
        
        header.add_widget(back_btn)
        header.add_widget(title)
        header.add_widget(Widget(size_hint_x=1))
        header.add_widget(sync_btn)
        layout.add_widget(header)
        
        self.status_label = MDLabel(
            text='Saved to local encrypted storage. Tap sync to distribute to peers.',
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(24)
        )
        layout.add_widget(self.status_label)
        
        # Text editor container with Workshop Grid surface and restrained border
        editor_card = MDCard(
            style='outlined',
            padding=dp(10),
            size_hint=(1, 0.88),
            md_bg_color=(0.090, 0.094, 0.086, 0.98),
            line_color=(0.188, 0.192, 0.176, 1.0),
            radius=[dp(4), dp(4), dp(4), dp(4)]
        )
        
        # Multiline text editor for editing notes - monospace technical font
        self.editor = TextInput(
            multiline=True,
            size_hint=(1, 1),
            background_color=(0, 0, 0, 0),
            foreground_color=(0.910, 0.914, 0.894, 1.0),
            cursor_color=(0.24, 0.44, 0.64, 1.0),
            font_name='RobotoMono-Regular' if os.path.exists('RobotoMono-Regular.ttf') else 'monospace',
            font_size='15sp'
        )
        self.editor.bind(text=self.on_text_change)
        editor_card.add_widget(self.editor)
        layout.add_widget(editor_card)
        
        root_layout.add_widget(layout)
        self.add_widget(root_layout)
        
    def on_pre_enter(self):
        self.load_notes()
        
    def load_notes(self):
        if os.path.exists(self.notes_file):
            try:
                with open(self.notes_file, 'r', encoding='utf-8') as f:
                    self.editor.text = f.read()
            except Exception as e:
                print(f"[NotesScreen] Error loading notes: {e}")
        else:
            self.editor.text = ""
            
    def on_text_change(self, instance, value):
        try:
            with open(self.notes_file, 'w', encoding='utf-8') as f:
                f.write(value)
        except Exception as e:
            print(f"[NotesScreen] Error saving notes: {e}")
            
    def sync_notes(self, *args):
        app = MDApp.get_running_app()
        if not app or not app.engine:
            self.status_label.text = "Mesh network engine is offline."
            return
            
        if not os.path.exists(self.notes_file):
            with open(self.notes_file, 'w', encoding='utf-8') as f:
                f.write("")
                
        direct_peers = []
        if app.engine.routing_table:
            direct_peers = app.engine.routing_table.get_direct_peers()
            
        if not direct_peers:
            self.status_label.text = "No direct mesh peers online to sync with."
            return
            
        synced_count = 0
        for peer in direct_peers:
            for ip, peer_info in app.engine.peers.items():
                if peer_info.get('peer_id') == peer:
                    app.engine.send_file(ip, self.notes_file)
                    synced_count += 1
                    
        self.status_label.text = f"Synced notes with {synced_count} direct peer(s)."
                    
    def go_back(self, *args):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().go_back()
