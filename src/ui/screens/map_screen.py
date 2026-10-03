"""
Ghost Net UI - Field Map Screen
Offline GIS visualization with MBTiles offline tile providers,
GPS positioning, peer telemetry, waypoints, and SOS beacons.
"""

import os
import time
import sqlite3
from datetime import datetime
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDIconButton
from kivymd.uix.label import MDLabel

from ui.theme import (
    apply_premium_background,
    MDButtonText,
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from gps_manager import get_gps_manager

try:
    from kivy_garden.mapview import MapView, MapMarker, MapSource
    MAPVIEW_AVAILABLE = True
except ImportError:
    try:
        from kivy.garden.mapview import MapView, MapMarker, MapSource
        MAPVIEW_AVAILABLE = True
    except ImportError:
        MapView = None
        MapMarker = None
        MapSource = None
        MAPVIEW_AVAILABLE = False
        print("[MapScreen] MapView not available - map disabled")

if MAPVIEW_AVAILABLE and MapSource:
    class BlankOfflineMapSource(MapSource):
        """Offline-only blank map provider that suppresses external network requests."""
        def __init__(self, **kwargs):
            super().__init__(min_zoom=0, max_zoom=19, **kwargs)
            
        def fill_tile(self, tile):
            tile.state = "done"

    class OfflineMBTilesMapSource(MapSource):
        def __init__(self, mbtiles_path, **kwargs):
            self.mbtiles_path = mbtiles_path
            self.db = sqlite3.connect(mbtiles_path, check_same_thread=False)
            min_zoom = 0
            max_zoom = 19
            try:
                cursor = self.db.cursor()
                cursor.execute("SELECT value FROM metadata WHERE name='minzoom'")
                row = cursor.fetchone()
                if row:
                    min_zoom = int(row[0])
                cursor.execute("SELECT value FROM metadata WHERE name='maxzoom'")
                row = cursor.fetchone()
                if row:
                    max_zoom = int(row[0])
            except Exception as e:
                print(f"[OfflineMBTilesMapSource] Metadata fetch error: {e}")
            
            super().__init__(
                min_zoom=min_zoom,
                max_zoom=max_zoom,
                **kwargs
            )
            
        def fill_tile(self, tile):
            if tile.state == "done":
                return
            
            zoom = tile.zoom
            x = tile.tile_x
            y = tile.tile_y
            
            try:
                cursor = self.db.cursor()
                cursor.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                    (zoom, x, y)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    tile_data = row[0]
                    cache_fn = tile.cache_fn
                    os.makedirs(os.path.dirname(cache_fn), exist_ok=True)
                    with open(cache_fn, 'wb') as f:
                        f.write(tile_data)
                    
                    def _done(dt):
                        tile.set_source(cache_fn)
                    Clock.schedule_once(_done, 0)
                    return
            except Exception as e:
                print(f"[OfflineMBTilesMapSource] Error retrieving tile {zoom}/{x}/{y}: {e}")
                
            # Offline opsec enforcement: do NOT fallback to internet tile fetching
            tile.state = "done"
else:
    class BlankOfflineMapSource(object):
        def __init__(self, **kwargs):
            pass

    class OfflineMBTilesMapSource(object):
        def __init__(self, mbtiles_path, **kwargs):
            pass


class GhostMapMarker(MapMarker if MAPVIEW_AVAILABLE else object):
    def __init__(self, lat, lon, title, color=(1, 0, 0, 1), is_user=False, **kwargs):
        if MAPVIEW_AVAILABLE:
            super().__init__(lat=lat, lon=lon, **kwargs)
            self.title = title
            self.color = color
            self.is_user = is_user
            self.timestamp = None
            self.sender_name = None
            self.bind(on_release=self.on_marker_release)
    
    def on_marker_release(self, *args):
        app = MDApp.get_running_app()
        if app and hasattr(app.root, 'get_screen'):
            try:
                map_screen = app.root.get_screen('map')
                if map_screen and hasattr(map_screen, 'show_marker_details'):
                    map_screen.show_marker_details(self)
            except:
                pass


class MapScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'map'
        apply_premium_background(self)
        self.gps_manager = get_gps_manager()
        self.sos_markers = {}
        self.peer_markers = {}
        self.waypoint_markers = {}
        self.user_marker = None
        self.map_view = None
        self.selected_marker = None
        
        layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(60),
            spacing=dp(6)
        )
        
        back_btn = MDIconButton(
            icon='arrow-left',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1)
        )
        back_btn.bind(on_release=self.go_back)
        
        title = MDLabel(
            text='Field Map',
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            pos_hint={'center_y': 0.5}
        )
        
        share_btn = MDIconButton(
            icon='broadcast',
            theme_icon_color='Custom',
            icon_color=(0.3, 0.8, 0.9, 1),
            size_hint_x=None,
            width=dp(44),
            pos_hint={'center_y': 0.5}
        )
        share_btn.bind(on_release=self.share_location_beacon)

        waypoint_btn = MDIconButton(
            icon='map-marker-plus',
            theme_icon_color='Custom',
            icon_color=(0.9, 0.75, 0.3, 1),
            size_hint_x=None,
            width=dp(44),
            pos_hint={'center_y': 0.5}
        )
        waypoint_btn.bind(on_release=self.show_add_waypoint_dialog)

        locate_btn = MDIconButton(
            icon='crosshairs-gps',
            theme_icon_color='Custom',
            icon_color=(0.65, 0.79, 0.92, 1),
            size_hint_x=None,
            width=dp(44),
            pos_hint={'center_y': 0.5}
        )
        locate_btn.bind(on_release=self.recenter_on_user)
        
        header.add_widget(back_btn)
        header.add_widget(title)
        header.add_widget(Widget(size_hint_x=1))
        header.add_widget(share_btn)
        header.add_widget(waypoint_btn)
        header.add_widget(locate_btn)
        layout.add_widget(header)
        
        if MAPVIEW_AVAILABLE and MapView:
            self.map_view = MapView(
                zoom=14,
                lat=22.7196,
                lon=75.8577,
                size_hint=(1, 0.85)
            )
            if BlankOfflineMapSource:
                self.map_view.map_source = BlankOfflineMapSource()
            self.map_view.map_source.cache_size = 500
            self.map_view.map_source.cache = True
            
            self.init_user_marker()
            layout.add_widget(self.map_view)
        else:
            fallback_card = MDCard(
                orientation='vertical',
                style='outlined',
                padding=dp(20),
                spacing=dp(12),
                size_hint=(1, 0.85),
                pos_hint={'center_x': 0.5},
                md_bg_color=(0.10, 0.12, 0.18, 0.85),
                line_color=(0.25, 0.35, 0.50, 0.6)
            )
            fallback_title = MDLabel(
                text="Field Coordinates (Offline Sensor Mode)",
                font_style="Title",
                role="medium",
                theme_text_color="Primary",
                size_hint_y=None,
                height=dp(30)
            )
            self.fallback_coords_label = MDLabel(
                text="GPS Coordinates: Acquiring...",
                font_style="Headline",
                role="small",
                theme_text_color="Custom",
                text_color=(0.4, 0.8, 1.0, 1),
                size_hint_y=None,
                height=dp(40)
            )
            fallback_desc = MDLabel(
                text="Local coordinate tracking, SOS beacons, and waypoint broadcasts remain active.\nInteractive visual tile mapping requires kivy-garden.mapview and an offline MBTiles file configured in Settings.",
                font_style="Body",
                role="medium",
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(80)
            )
            fallback_card.add_widget(fallback_title)
            fallback_card.add_widget(self.fallback_coords_label)
            fallback_card.add_widget(fallback_desc)
            layout.add_widget(fallback_card)
        
        info_box = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(60),
            spacing=dp(5),
            padding=dp(10)
        )
        
        self.info_label = MDLabel(
            text='Your location: Loading...',
            font_style='Body',
            role='small',
            theme_text_color='Secondary'
        )
        
        self.markers_label = MDLabel(
            text='SOS Beacons: 0',
            font_style='Body',
            role='small',
            theme_text_color='Secondary'
        )
        
        info_box.add_widget(self.info_label)
        info_box.add_widget(self.markers_label)
        layout.add_widget(info_box)
        
        self.add_widget(layout)
        self._location_event = None

    def on_enter(self, *args):
        """Start periodic location updates when map is actively viewed."""
        self.load_offline_map()
        self.load_saved_waypoints()
        if not self._location_event:
            self._location_event = Clock.schedule_interval(self.update_user_location, 2.0)

    def on_leave(self, *args):
        """Pause location updates to conserve device power when not on map screen."""
        if self._location_event:
            self._location_event.cancel()
            self._location_event = None

    def load_offline_map(self):
        if not self.map_view:
            return
        app = MDApp.get_running_app()
        mbtiles_loaded = False
        if app and app.config:
            mbtiles_path = app.config.get("mbtiles_path")
            if mbtiles_path and os.path.exists(mbtiles_path):
                try:
                    print(f"[MapScreen] Setting map source to offline database: {mbtiles_path}")
                    offline_source = OfflineMBTilesMapSource(mbtiles_path)
                    self.map_view.map_source = offline_source
                    mbtiles_loaded = True
                except Exception as e:
                    print(f"[MapScreen] Failed to set offline map source: {e}")
        
        if not mbtiles_loaded:
            if BlankOfflineMapSource:
                self.map_view.map_source = BlankOfflineMapSource()
            if hasattr(self, 'info_label') and self.info_label:
                self.info_label.text = "GPS Active • Offline MBTiles not configured (select in Settings)"

    def init_user_marker(self):
        if not MAPVIEW_AVAILABLE or not self.map_view or not MapMarker:
            return
        
        lat, lon = self.gps_manager.get_coordinates()
        
        self.user_marker = GhostMapMarker(
            lat=lat,
            lon=lon,
            title='Your Location',
            color=(0.2, 0.8, 1, 1),
            is_user=True
        )
        
        self.map_view.add_widget(self.user_marker)
    
    def recenter_on_user(self, *args):
        """Center the map on the user's current GPS position."""
        if not self.map_view:
            return
        try:
            lat, lon = self.gps_manager.get_coordinates()
            self.map_view.center_on(lat, lon)
        except Exception as e:
            print(f"[MapScreen] Error re-centering on user: {e}")

    def update_user_location(self, dt):
        try:
            lat, lon = self.gps_manager.get_coordinates()
            if hasattr(self, 'info_label') and self.info_label:
                self.info_label.text = f'Your location: {lat:.4f}, {lon:.4f}'
            if hasattr(self, 'fallback_coords_label') and self.fallback_coords_label:
                self.fallback_coords_label.text = f'GPS Coordinates: {lat:.6f}, {lon:.6f}'
            
            if self.map_view and self.user_marker:
                self.user_marker.lat = lat
                self.user_marker.lon = lon
                
                # Center only once initially so user panning/zooming is not disrupted
                if not getattr(self, '_has_initially_centered', False):
                    self.map_view.center_on(lat, lon)
                    self._has_initially_centered = True
        except Exception as e:
            print(f'[MapScreen] Location update error: {e}')
    
    def plot_sos_marker(self, lat, lon, sender_name, sos_id=None):
        if not MAPVIEW_AVAILABLE or not self.map_view or not MapMarker:
            print('[MapScreen] MapView not available for SOS plotting')
            return
        
        marker_id = sos_id or sender_name
        
        if marker_id in self.sos_markers:
            old_marker = self.sos_markers[marker_id]
            self.map_view.remove_widget(old_marker)
        
        marker = GhostMapMarker(
            lat=lat,
            lon=lon,
            title=f'SOS: {sender_name}',
            color=(1, 0, 0, 1),
            is_user=False
        )
        marker.sender_name = sender_name
        marker.timestamp = datetime.now().strftime('%H:%M:%S')
        
        self.map_view.add_widget(marker)
        self.sos_markers[marker_id] = marker
        
        self.markers_label.text = f'SOS Beacons: {len(self.sos_markers)}'
        
        def pulse_animation():
            anim = Animation(opacity=0.5, duration=0.5) + Animation(opacity=1, duration=0.5)
            anim.repeat = True
            anim.start(marker)
        
        Clock.schedule_once(lambda dt: pulse_animation(), 0.1)
    
    def show_marker_details(self, marker):
        if not marker:
            return
        
        self.selected_marker = marker
        
        if marker.is_user:
            title_text = 'Your Location'
            details_text = f'Latitude: {marker.lat:.6f}\nLongitude: {marker.lon:.6f}'
        else:
            title_text = f'SOS: {marker.sender_name}'
            time_text = marker.timestamp or 'Unknown'
            details_text = f'From: {marker.sender_name}\nTime: {time_text}\nLat: {marker.lat:.6f}\nLon: {marker.lon:.6f}'
        
        content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(15),
            padding=dp(20),
            adaptive_height=True
        )
        
        title_label = MDLabel(
            text=title_text,
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            size_hint_y=None,
            height=dp(40)
        )
        
        details_label = MDLabel(
            text=details_text,
            font_style='Body',
            role='medium',
            size_hint_y=None,
            height=dp(80)
        )
        
        content.add_widget(title_label)
        content.add_widget(details_label)
        
        close_btn = MDButton(
            MDButtonText(text='Close'),
            style='elevated'
        )
        
        def dismiss_dialog(*args):
            if hasattr(self, '_marker_dialog') and self._marker_dialog:
                self._marker_dialog.dismiss()
        
        close_btn.bind(on_release=dismiss_dialog)
        content.add_widget(close_btn)
        
        self._marker_dialog = MDDialog(
            MDDialogHeadlineText(text='Marker Details'),
            MDDialogContentContainer(content, orientation='vertical'),
            MDDialogButtonContainer()
        )
        self._marker_dialog.open()

    def plot_peer_marker(self, peer_id, username, lat, lon, alt=0.0, acc=0.0):
        if not MAPVIEW_AVAILABLE or not self.map_view or not MapMarker:
            return

        if peer_id in self.peer_markers:
            old_marker = self.peer_markers[peer_id]
            self.map_view.remove_widget(old_marker)

        marker = GhostMapMarker(
            lat=lat,
            lon=lon,
            title=f"Peer: {username}",
            color=(0.2, 0.9, 0.6, 1),
            is_user=False
        )
        marker.sender_name = username
        marker.peer_id = peer_id
        marker.marker_type = "peer"
        marker.timestamp = datetime.now().strftime('%H:%M:%S')

        self.map_view.add_widget(marker)
        self.peer_markers[peer_id] = marker
        self._update_markers_label()

    def plot_waypoint(self, waypoint_dict):
        if not MAPVIEW_AVAILABLE or not self.map_view or not MapMarker:
            return

        wp_id = waypoint_dict.get("waypoint_id") or waypoint_dict.get("id") or str(time.time())
        if wp_id in self.waypoint_markers:
            old_marker = self.waypoint_markers[wp_id]
            self.map_view.remove_widget(old_marker)

        lat = float(waypoint_dict.get("latitude") or waypoint_dict.get("lat") or 0.0)
        lon = float(waypoint_dict.get("longitude") or waypoint_dict.get("lon") or 0.0)
        title = waypoint_dict.get("title", "Field Waypoint")
        wp_type = waypoint_dict.get("waypoint_type", "waypoint")

        type_colors = {
            "rally": (0.3, 0.7, 1.0, 1),
            "hazard": (1.0, 0.5, 0.0, 1),
            "cache": (0.9, 0.8, 0.2, 1),
            "checkpoint": (0.7, 0.3, 0.9, 1),
            "medical": (1.0, 0.2, 0.3, 1),
        }
        color = type_colors.get(str(wp_type).lower(), (0.65, 0.79, 0.92, 1))

        marker = GhostMapMarker(
            lat=lat,
            lon=lon,
            title=f"[{str(wp_type).upper()}] {title}",
            color=color,
            is_user=False
        )
        marker.sender_name = waypoint_dict.get("created_by", "Unknown")
        marker.waypoint_data = waypoint_dict
        marker.marker_type = wp_type
        marker.timestamp = datetime.now().strftime('%H:%M:%S')

        self.map_view.add_widget(marker)
        self.waypoint_markers[wp_id] = marker
        self._update_markers_label()

    def _update_markers_label(self):
        self.markers_label.text = f"Peers: {len(self.peer_markers)} • Waypoints: {len(self.waypoint_markers)} • SOS: {len(self.sos_markers)}"

    def load_saved_waypoints(self):
        app = MDApp.get_running_app()
        if app and hasattr(app, 'persistence_db') and app.persistence_db:
            try:
                saved = app.persistence_db.get_all_waypoints()
                for wp in saved:
                    self.plot_waypoint(wp)
            except Exception as e:
                print(f"[MapScreen] Error loading saved waypoints: {e}")

    def share_location_beacon(self, *args):
        app = MDApp.get_running_app()
        if not app or not app.engine:
            return
        lat, lon = self.gps_manager.get_coordinates()
        app.engine.send_location_beacon(lat, lon)
        self.info_label.text = f"Beacon broadcasted: ({lat:.4f}, {lon:.4f})"

    def show_add_waypoint_dialog(self, *args):
        lat, lon = self.gps_manager.get_coordinates()
        import uuid
        wp_data = {
            "waypoint_id": f"wp_{uuid.uuid4().hex[:8]}",
            "title": "Field Checkpoint",
            "description": "Standard rally point",
            "waypoint_type": "rally",
            "latitude": lat,
            "longitude": lon,
            "altitude": 0.0,
            "ttl": 86400
        }
        self.plot_waypoint(wp_data)
        app = MDApp.get_running_app()
        if app and app.engine:
            app.engine.send_waypoint(wp_data)
        self.info_label.text = f"Dropped waypoint at ({lat:.4f}, {lon:.4f})"

    def export_all_geojson(self) -> str:
        import json
        items = []
        lat, lon = self.gps_manager.get_coordinates()
        items.append({"title": "Own Position", "type": "user", "latitude": lat, "longitude": lon})
        for m in self.peer_markers.values():
            items.append({"title": getattr(m, 'sender_name', 'Peer'), "type": "peer", "latitude": m.lat, "longitude": m.lon})
        for m in self.waypoint_markers.values():
            wp = getattr(m, 'waypoint_data', {})
            items.append(wp if wp else {"title": m.title, "type": "waypoint", "latitude": m.lat, "longitude": m.lon})
        for m in self.sos_markers.values():
            items.append({"title": f"SOS: {getattr(m, 'sender_name', 'Unknown')}", "type": "sos", "latitude": m.lat, "longitude": m.lon})
        features = []
        for it in items:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [it.get("longitude", 0.0), it.get("latitude", 0.0)]
                },
                "properties": {
                    "title": it.get("title", ""),
                    "marker_type": it.get("type", "waypoint")
                }
            })
        return json.dumps({"type": "FeatureCollection", "features": features})

    def export_cot_for_marker(self, marker) -> str:
        # CoT XML is a research prototype; core Gost-Net returns empty string
        return ""

    def go_back(self, *args):
        from ui.navigation import get_navigation_controller
        get_navigation_controller().go_back()
