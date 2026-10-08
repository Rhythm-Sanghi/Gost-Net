"""
Ghost Net UI - Boot Screen
Startup loading sequence with animated spinner and status progression.
"""

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel

from ui.theme import apply_premium_background, MDSpinner


class BootScreen(MDScreen):
    """Initial boot screen with loading animation."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'boot'
        apply_premium_background(self)
        
        root_layout = MDFloatLayout(size_hint=(1, 1))
        
        # Modern centered layout container
        layout = MDBoxLayout(
            orientation='vertical',
            size_hint=(None, 1),
            width=dp(360),
            pos_hint={'center_x': 0.5},
            padding=dp(20),
            spacing=dp(20)
        )
        
        # Spacer
        layout.add_widget(Widget(size_hint_y=0.25))
        
        # Logo/Ghost animation area
        logo_area = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(300),
            spacing=dp(24)
        )
        
        # App name
        app_name = MDLabel(
            text="GOST-NET",
            halign='center',
            font_style='Headline',
            role='large',
            size_hint_y=None,
            height=dp(60)
        )
        
        # System description
        tagline = MDLabel(
            text="Offline Mesh Cryptographic Radio Terminal",
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='medium',
            size_hint_y=None,
            height=dp(30)
        )
        
        # Loading spinner
        self.spinner = MDSpinner(
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            pos_hint={'center_x': 0.5},
            active=True,
            color=(0.24, 0.44, 0.64, 1.0)
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
        layout.add_widget(Widget(size_hint_y=0.25))
        
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
        
        root_layout.add_widget(layout)
        self.add_widget(root_layout)
    
    def update_status(self, text):
        """Update the status label text."""
        self.status_label.text = text
