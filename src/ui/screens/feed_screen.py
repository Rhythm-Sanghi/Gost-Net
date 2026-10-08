"""
Ghost Net - Situation Feed Screen
Displays a clean, chronological event journal of what happened in the local coordination mesh.
Follows the Workshop Grid / Studio Utility design system:
flat functional surfaces, compact information density, thin dividers, restrained typography.
"""

import time
from datetime import datetime
from typing import Optional, List, Dict, Any

from kivy.metrics import dp
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDIconButton, MDButton, MDButtonText
from kivymd.app import MDApp

from ui.theme import WorkshopGridTokens, apply_workshop_background
from ui.navigation import get_navigation_controller


class FeedEventRow(MDBoxLayout):
    """
    Compact single-event row in the situation timeline.
    Layout: [ Timestamp ] [ Event Description & Detail ] [ Status / Transport Metadata ]
    """

    def __init__(self, event_data: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(56)
        self.padding = [dp(12), dp(6), dp(12), dp(6)]
        self.spacing = dp(8)

        ts = event_data.get("timestamp", time.time())
        try:
            dt = datetime.fromtimestamp(ts)
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            time_str = "--:--:--"

        # 1. Timestamp Column
        time_lbl = MDLabel(
            text=time_str,
            size_hint=(None, 1),
            width=dp(64),
            font_style='Body',
            role='small',
            theme_text_color='Custom',
            text_color=WorkshopGridTokens.DARK_TEXT_MUTED,
            halign='left',
            valign='center',
        )
        self.add_widget(time_lbl)

        # 2. Main Description Column
        desc_box = MDBoxLayout(
            orientation='vertical',
            size_hint=(1, 1),
            spacing=dp(2),
        )

        title_text = event_data.get("summary", "Event")
        detail_text = event_data.get("detail", "")

        title_lbl = MDLabel(
            text=title_text,
            size_hint=(1, None),
            height=dp(20),
            font_style='Body',
            role='medium',
            theme_text_color='Custom',
            text_color=WorkshopGridTokens.DARK_TEXT_PRIMARY,
            shorten=True,
            shorten_from='right',
        )
        desc_box.add_widget(title_lbl)

        if detail_text:
            detail_lbl = MDLabel(
                text=detail_text,
                size_hint=(1, None),
                height=dp(18),
                font_style='Body',
                role='small',
                theme_text_color='Custom',
                text_color=WorkshopGridTokens.DARK_TEXT_SECONDARY,
                shorten=True,
                shorten_from='right',
            )
            desc_box.add_widget(detail_lbl)

        self.add_widget(desc_box)

        # 3. Secondary Metadata / Provenance Column
        meta_text = event_data.get("metadata", "")
        if meta_text:
            meta_lbl = MDLabel(
                text=meta_text,
                size_hint=(None, 1),
                width=dp(90),
                font_style='Body',
                role='small',
                theme_text_color='Custom',
                text_color=WorkshopGridTokens.ACCENT,
                halign='right',
                valign='center',
                shorten=True,
            )
            self.add_widget(meta_lbl)

        # Bottom thin hairline divider
        with self.canvas.after:
            Color(*WorkshopGridTokens.DARK_BORDER)
            self._divider = Rectangle(pos=self.pos, size=(self.width, dp(1)))
        self.bind(pos=self._update_divider, size=self._update_divider)

    def _update_divider(self, *args):
        if hasattr(self, '_divider'):
            self._divider.pos = (self.x + dp(8), self.y)
            self._divider.size = (max(0, self.width - dp(16)), dp(1))


class FeedScreen(MDScreen):
    """
    Feed screen presenting the situation timeline for the active Space.
    Shows who joined, what waypoints were created, messages delivered, and network changes.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'feed'
        self.active_space_id = "spc_local_mesh"
        self._build_ui()

    def _build_ui(self):
        apply_workshop_background(self)

        layout = MDBoxLayout(
            orientation='vertical',
            padding=[dp(12), dp(12), dp(12), dp(12)],
            spacing=dp(8),
            size_hint=(1, 1),
        )

        # 1. Header Toolbar
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )

        back_btn = MDIconButton(
            icon='arrow-left',
            theme_icon_color='Custom',
            icon_color=WorkshopGridTokens.DARK_TEXT_PRIMARY,
            pos_hint={'center_y': 0.5},
        )
        back_btn.bind(on_release=lambda x: get_navigation_controller().go_back())
        header.add_widget(back_btn)

        title_box = MDBoxLayout(
            orientation='vertical',
            size_hint=(1, 1),
            pos_hint={'center_y': 0.5},
        )
        self.title_lbl = MDLabel(
            text="LOCAL FEED",
            font_style='Title',
            role='medium',
            theme_text_color='Custom',
            text_color=WorkshopGridTokens.DARK_TEXT_PRIMARY,
            size_hint=(1, None),
            height=dp(22),
        )
        self.subtitle_lbl = MDLabel(
            text="Local Coordination Mesh",
            font_style='Body',
            role='small',
            theme_text_color='Custom',
            text_color=WorkshopGridTokens.DARK_TEXT_MUTED,
            size_hint=(1, None),
            height=dp(18),
        )
        title_box.add_widget(self.title_lbl)
        title_box.add_widget(self.subtitle_lbl)
        header.add_widget(title_box)

        refresh_btn = MDIconButton(
            icon='refresh',
            theme_icon_color='Custom',
            icon_color=WorkshopGridTokens.DARK_TEXT_SECONDARY,
            pos_hint={'center_y': 0.5},
        )
        refresh_btn.bind(on_release=lambda x: self.refresh_feed())
        header.add_widget(refresh_btn)

        layout.add_widget(header)

        # 2. Scrollable Events Feed List
        scroll = MDScrollView(size_hint=(1, 1))
        self.events_container = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=dp(2),
        )
        self.events_container.bind(minimum_height=self.events_container.setter('height'))
        scroll.add_widget(self.events_container)
        layout.add_widget(scroll)

        # 3. Status Bar
        self.status_bar = MDLabel(
            text="Initialised · Local journal ready",
            font_style='Body',
            role='small',
            theme_text_color='Custom',
            text_color=WorkshopGridTokens.DARK_TEXT_MUTED,
            size_hint_y=None,
            height=dp(20),
            halign='left',
        )
        layout.add_widget(self.status_bar)

        self.add_widget(layout)

    def on_enter(self, *args):
        """Called when navigating to FeedScreen."""
        self.refresh_feed()

    def set_space(self, space_id: str, space_name: str = ""):
        """Sets the active Space being viewed."""
        self.active_space_id = space_id
        if space_name:
            self.subtitle_lbl.text = space_name
        self.refresh_feed()

    def refresh_feed(self):
        """Loads events from the local EventStore and updates UI."""
        app = MDApp.get_running_app()
        if not app or not getattr(app, 'persistence_db', None):
            self._render_empty("No persistence database available")
            return

        store = app.persistence_db.get_event_store()
        if not store:
            self._render_empty("Event store unavailable")
            return

        # Fetch events for the active space in deterministic total order
        events = store.get_events(self.active_space_id, limit=200)

        # Update space name in subtitle
        sp = store.get_space(self.active_space_id)
        if sp:
            self.subtitle_lbl.text = f"{sp.name} · {len(events)} events"

        self.events_container.clear_widgets()

        if not events:
            self._render_empty("No events in local feed yet.\nLocal mesh events will appear as peers interact.")
            self.status_bar.text = "0 events in local feed"
            return

        # Display latest events at top or in chronological order
        for ev in reversed(events):
            row_data = self._format_event_row(ev)
            row = FeedEventRow(row_data)
            self.events_container.add_widget(row)

        self.status_bar.text = f"{len(events)} events recorded · State digest: {sp.state_digest[:8] if sp and sp.state_digest else 'ready'}"

    def _render_empty(self, message: str):
        self.events_container.clear_widgets()
        empty_box = MDBoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(120),
            padding=[dp(16), dp(32), dp(16), dp(16)],
            spacing=dp(8),
        )
        empty_lbl = MDLabel(
            text=message,
            halign='center',
            font_style='Body',
            role='medium',
            theme_text_color='Custom',
            text_color=WorkshopGridTokens.DARK_TEXT_MUTED,
        )
        empty_box.add_widget(empty_lbl)
        self.events_container.add_widget(empty_box)

    @staticmethod
    def _format_event_row(ev) -> Dict[str, Any]:
        """Maps a SpaceEvent into human-readable situation row data."""
        etype = ev.event_type
        payload = ev.payload or {}
        author = ev.author_id

        summary = etype.replace('_', ' ').title()
        detail = ""
        meta = ""

        if etype in ("PEER_SEEN", "PEER_APPEARED"):
            p_name = payload.get("peer_id") or payload.get("username", author)
            summary = f"{p_name} became reachable"
            meta = payload.get("observed_transport") or payload.get("transport", "Direct")
        elif etype in ("PEER_LOST", "PEER_DISAPPEARED"):
            p_name = payload.get("peer_id") or payload.get("username", author)
            summary = f"{p_name} no longer reachable"
            meta = "Offline"
        elif etype in ("MESSAGE_CREATED", "MESSAGE_ADD"):
            recipient = payload.get("recipient_id") or payload.get("recipient", "mesh")
            summary = f"Message created for {recipient}"
            ctype = payload.get("content_type", "")
            size = payload.get("size_bytes")
            if size is not None:
                detail = f"{ctype.title() + ' ' if ctype else ''}({size} bytes)"
            else:
                detail = payload.get("text", "")
            meta = "Created"
        elif etype in ("MESSAGE_RECEIVED",):
            sender = payload.get("sender_id") or payload.get("sender", author)
            summary = f"Message received from {sender}"
            ctype = payload.get("content_type", "")
            size = payload.get("size_bytes")
            if size is not None:
                detail = f"{ctype.title() + ' ' if ctype else ''}({size} bytes)"
            else:
                detail = payload.get("text", "")
            meta = "Received"
        elif etype in ("MESSAGE_QUEUED",):
            recipient = payload.get("recipient_id") or payload.get("recipient", "peer")
            summary = f"Message queued for {recipient}"
            meta = "DTN Spool"
        elif etype in ("MESSAGE_DELIVERED",):
            recipient = payload.get("recipient_id") or payload.get("recipient")
            if recipient:
                summary = f"Message delivered to {recipient}"
            else:
                sender = payload.get("sender", author)
                summary = f"Message from {sender}"
            detail = payload.get("text", "")
            meta = payload.get("metadata") or "Delivered"
        elif etype in ("MESSAGE_RELAYED",):
            target = payload.get("target_peer_id", "peer")
            next_hop = payload.get("next_hop_id", "next hop")
            summary = f"Message relayed for {target}"
            detail = f"via {next_hop}"
            meta = "Relayed"
        elif etype in ("WAYPOINT_ADDED", "WAYPOINT_ADD"):
            title = payload.get("title", "Waypoint")
            summary = f"Waypoint added: {title}"
            detail = f"by {payload.get('created_by', author)}"
            meta = "Map"
        elif etype in ("WAYPOINT_UPDATED", "WAYPOINT_UPDATE"):
            title = payload.get("title", "Waypoint")
            summary = f"Waypoint updated: {title}"
            meta = "Map"
        elif etype in ("NOTE_CREATED", "NOTE_CREATE"):
            title = payload.get("title", "Note")
            summary = f"Note created: {title}"
            detail = payload.get("content", "")
            meta = f"by {author}"
        elif etype in ("SPACE_CREATED", "SPACE_CREATE"):
            name = payload.get("name", "Space")
            summary = f"Space created: {name}"
            meta = "Space"
        elif etype in ("SPACE_JOINED", "SPACE_JOIN"):
            p_name = payload.get("display_name", author)
            summary = f"{p_name} joined Space"
            meta = "Member"
        elif etype in ("DELIVERY_UPDATE",):
            summary = f"Delivery: {payload.get('status', 'Updated')}"
            meta = payload.get("status", "")

        return {
            "timestamp": ev.timestamp,
            "summary": summary,
            "detail": detail,
            "metadata": meta,
        }
