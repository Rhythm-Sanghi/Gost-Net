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
            icon_color=(0.65, 0.79, 0.92, 1)
        )
        back_btn.bind(on_release=self.go_back)
        
        title = MDLabel(
            text='Collaborative Notepad',
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            pos_hint={'center_y': 0.5}
        )
        
        sync_btn = MDIconButton(
            icon='sync',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1)
        )
        sync_btn.bind(on_release=self.sync_notes)
        
        header.add_widget(back_btn)
        header.add_widget(title)
        header.add_widget(Widget(size_hint_x=1))
        header.add_widget(sync_btn)
        layout.add_widget(header)
        
        self.status_label = MDLabel(
            text='Auto-saved locally. Press sync to broadcast to mesh peers.',
            font_style='Body',
            role='small',
            theme_text_color='Secondary',
            size_hint_y=None,
            height=dp(24)
        )
        layout.add_widget(self.status_label)
        
        # Text editor container
        editor_card = MDCard(
            style='outlined',
            padding=dp(8),
            size_hint=(1, 0.88),
            md_bg_color=(0.08, 0.10, 0.14, 0.95),
            line_color=(0.22, 0.28, 0.38, 0.6),
            radius=[dp(6), dp(6), dp(6), dp(6)]
        )
        
        # Multiline text editor for editing notes - borderless inside the card
        self.editor = TextInput(
            multiline=True,
            size_hint=(1, 1),
            background_color=(0, 0, 0, 0),
            foreground_color=(0.95, 0.96, 0.98, 1),
            cursor_color=(0.65, 0.79, 0.92, 1),
            font_size='16sp'
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
