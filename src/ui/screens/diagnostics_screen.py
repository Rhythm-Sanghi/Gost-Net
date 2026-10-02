"""
Ghost Net UI - Diagnostics Screen
Telemetry status dashboard, in-situ connection metrics, live mesh topology toggle,
and encrypted log export capabilities.
"""

import os
import threading
from datetime import datetime
from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDIconButton

from ui.theme import apply_premium_background, MDButtonText
from ui.components.radar_canvas import MeshTopologyWidget
from diagnostics import get_diagnostics, encrypt_telemetry_file, copy_to_downloads
from telemetry_logger import get_telemetry_logger
from config import APP_VERSION


class DiagnosticsScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'diagnostics'
        apply_premium_background(self)
        self.diagnostics = get_diagnostics()
        self.telemetry = get_telemetry_logger()
        self.update_scheduled = False
        self.export_status_label = None
        self.view_mode = 'list'
        
        root_layout = MDFloatLayout(size_hint=(1, 1))
        
        layout = MDBoxLayout(
            orientation='vertical',
            padding=dp(10),
            spacing=dp(10),
            size_hint=(None, 1),
            width=dp(600),
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
        back_btn.bind(on_release=self.close_diagnostics)
        
        title = MDLabel(
            text=f'Diagnostics (v{APP_VERSION})',
            font_style='Title',
            role='large',
            theme_text_color='Primary',
            pos_hint={'center_y': 0.5}
        )
        
        header.add_widget(back_btn)
        header.add_widget(title)
        layout.add_widget(header)
        
        buttons_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
            padding=dp(10)
        )
        
        export_btn = MDButton(
            style='filled',
            theme_width='Custom',
            size_hint_x=0.5,
            theme_bg_color='Custom',
            md_bg_color=(0.65, 0.79, 0.92, 1)
        )
        export_btn_text = MDButtonText(text='Export Mission Logs')
        export_btn_text.theme_text_color = 'Custom'
        export_btn_text.text_color = (0.05, 0.06, 0.1, 1)
        export_btn.add_widget(export_btn_text)
        export_btn.bind(on_release=self.export_mission_logs)
        
        clear_btn = MDButton(
            style='outlined',
            theme_width='Custom',
            size_hint_x=0.5,
            theme_bg_color='Custom',
            md_bg_color=(0.1, 0.12, 0.18, 0.3),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        clear_btn_text = MDButtonText(text='Clear Telemetry')
        clear_btn_text.theme_text_color = 'Custom'
        clear_btn_text.text_color = (0.65, 0.79, 0.92, 1)
        clear_btn.add_widget(clear_btn_text)
        clear_btn.bind(on_release=self.clear_telemetry)
        
        buttons_layout.add_widget(export_btn)
        buttons_layout.add_widget(clear_btn)
        layout.add_widget(buttons_layout)
        
        # View toggle layout
        toggle_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
            padding=dp(10)
        )
        self.toggle_btn = MDButton(
            style='outlined',
            theme_width='Custom',
            size_hint_x=1,
            theme_bg_color='Custom',
            md_bg_color=(0.1, 0.12, 0.18, 0.3),
            line_color=(0.25, 0.32, 0.45, 0.35)
        )
        self.toggle_btn_text = MDButtonText(text='View Mesh Graph')
        self.toggle_btn_text.theme_text_color = 'Custom'
        self.toggle_btn_text.text_color = (0.65, 0.79, 0.92, 1)
        self.toggle_btn.add_widget(self.toggle_btn_text)
        self.toggle_btn.bind(on_release=self.toggle_view)
        toggle_layout.add_widget(self.toggle_btn)
        layout.add_widget(toggle_layout)
        
        self.export_status_label = MDLabel(
            text='',
            halign='center',
            theme_text_color='Secondary',
            font_style='Body',
            role='small',
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(self.export_status_label)
        
        self.scroll = MDScrollView(size_hint=(1, 1))
        self.diag_box = MDBoxLayout(
            orientation='vertical',
            adaptive_height=True,
            spacing=dp(15),
            padding=dp(10)
        )
        self.scroll.add_widget(self.diag_box)
        layout.add_widget(self.scroll)
        
        self.mesh_graph = MeshTopologyWidget(size_hint=(1, 1))
        self.mesh_graph.opacity = 0
        self.mesh_graph.size_hint_y = None
        self.mesh_graph.height = 0
        layout.add_widget(self.mesh_graph)
        
        root_layout.add_widget(layout)
        self.add_widget(root_layout)
        
    def toggle_view(self, *args):
        if self.view_mode == 'list':
            self.view_mode = 'graph'
            self.toggle_btn_text.text = 'View Text Diagnostics'
            self.scroll.opacity = 0
            self.scroll.size_hint_y = None
            self.scroll.height = 0
            self.mesh_graph.opacity = 1
            self.mesh_graph.size_hint_y = 1
        else:
            self.view_mode = 'list'
            self.toggle_btn_text.text = 'View Mesh Graph'
            self.scroll.opacity = 1
            self.scroll.size_hint_y = 1
            self.mesh_graph.opacity = 0
            self.mesh_graph.size_hint_y = None
            self.mesh_graph.height = 0
        self.refresh_diagnostics()
    
    def on_enter(self):
        if not self.update_scheduled:
            Clock.schedule_interval(self.refresh_diagnostics, 1.0)
            self.update_scheduled = True
    
    def on_leave(self):
        if self.update_scheduled:
            Clock.unschedule(self.refresh_diagnostics)
            self.update_scheduled = False
    
    def refresh_diagnostics(self, dt=None):
        try:
            snapshot = self.diagnostics.get_diagnostics_snapshot()
            
            app = MDApp.get_running_app()
            if app and app.decoy_mode:
                snapshot['routing_table'] = {
                    "wfd_alice": {"next_hop": "wfd_alice", "metric": 1},
                    "bt_bob": {"next_hop": "bt_bob", "metric": 1},
                    "mesh_charlie": {"next_hop": "wfd_alice", "metric": 2}
                }
                snapshot['node_status'] = {
                    'local_ip': '192.168.43.10',
                    'local_mac': 'AA:BB:CC:DD:EE:FF',
                    'service_status': 'Running (Decoy)',
                    'uptime': '00h 42m 15s'
                }
            
            if self.view_mode == 'graph':
                self.mesh_graph.update_mesh(snapshot.get('routing_table', {}))
                
            # Initialize persistent widget structure once
            if not getattr(self, '_diag_initialized', False):
                self.diag_box.clear_widgets()
                
                # 1. Node Status Section
                node_section = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(4))
                node_section.add_widget(MDLabel(text='[b]NODE STATUS[/b]', markup=True, font_style='Body', role='large', theme_text_color='Hint'))
                self.lbl_node_ip = MDLabel(text='', font_style='Body', role='small')
                self.lbl_node_mac = MDLabel(text='', font_style='Body', role='small')
                self.lbl_node_service = MDLabel(text='', font_style='Body', role='small')
                self.lbl_node_uptime = MDLabel(text='', font_style='Body', role='small')
                node_section.add_widget(self.lbl_node_ip)
                node_section.add_widget(self.lbl_node_mac)
                node_section.add_widget(self.lbl_node_service)
                node_section.add_widget(self.lbl_node_uptime)
                self.diag_box.add_widget(node_section)
                
                # 2. Routing Table Section
                routing_section = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(3))
                routing_section.add_widget(MDLabel(text='[b]ROUTING TABLE[/b]', markup=True, font_style='Body', role='large', theme_text_color='Hint'))
                self.routing_entries_box = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(2))
                routing_section.add_widget(self.routing_entries_box)
                self.diag_box.add_widget(routing_section)
                
                # 3. Socket Health Section
                socket_section = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(3))
                socket_section.add_widget(MDLabel(text='[b]SOCKET HEALTH[/b]', markup=True, font_style='Body', role='large', theme_text_color='Hint'))
                self.lbl_socket_active = MDLabel(text='', font_style='Body', role='small')
                socket_section.add_widget(self.lbl_socket_active)
                self.socket_entries_box = MDBoxLayout(orientation='vertical', adaptive_height=True, spacing=dp(2))
                socket_section.add_widget(self.socket_entries_box)
                self.lbl_msg_queue = MDLabel(text='', font_style='Body', role='small', theme_text_color='Secondary')
                socket_section.add_widget(self.lbl_msg_queue)
                self.diag_box.add_widget(socket_section)
                
                self._diag_initialized = True
            
            # Update Node Status in-place
            node_status = snapshot['node_status']
            self.lbl_node_ip.text = f"IP: {node_status['local_ip']}"
            self.lbl_node_mac.text = f"MAC: {node_status['local_mac']}"
            self.lbl_node_service.text = f"Service: {node_status['service_status']}"
            self.lbl_node_uptime.text = f"Uptime: {node_status['uptime']}"
            
            # Update Routing Table entries
            routing_table = snapshot['routing_table']
            self.routing_entries_box.clear_widgets()
            if routing_table:
                for dest, route_info in routing_table.items():
                    if isinstance(route_info, dict):
                        next_hop = route_info.get('next_hop', 'N/A')
                        metric = route_info.get('metric', 'N/A')
                        route_text = f"→ {dest[:8]}... | {next_hop[:8]}... [{metric}]"
                    else:
                        route_text = f"→ {dest[:12]}... {route_info}"
                    self.routing_entries_box.add_widget(MDLabel(text=route_text, font_style='Body', role='small'))
            else:
                self.routing_entries_box.add_widget(MDLabel(text='No routes discovered', font_style='Body', role='small', theme_text_color='Secondary'))
            
            # Update Active Sockets
            active_sockets = snapshot['active_sockets']
            self.lbl_socket_active.text = f"Active Connections: {len(active_sockets)}"
            self.socket_entries_box.clear_widgets()
            for sock in active_sockets[:10]:
                if isinstance(sock, dict):
                    if 'error' in sock:
                        self.socket_entries_box.add_widget(MDLabel(text=f"Error: {sock['error'][:40]}", font_style='Body', role='small', theme_text_color='Error'))
                    else:
                        sock_type = sock.get('type', 'UNKNOWN')
                        remote = sock.get('remote', 'N/A')
                        self.socket_entries_box.add_widget(MDLabel(text=f"[{sock_type}] {remote[:20]}...", font_style='Body', role='small'))
            
            queue_size = snapshot['message_queue']
            self.lbl_msg_queue.text = f"Message Queue: {queue_size}"
        
        except Exception as e:
            self.diag_box.clear_widgets()
            self._diag_initialized = False
            self.diag_box.add_widget(MDLabel(
                text=f"Error: {str(e)[:100]}",
                font_style='Body',
                role='small',
                theme_text_color='Error'
            ))
    
    def export_mission_logs(self, instance=None):
        def export_worker():
            try:
                self.export_status_label.text = 'Exporting logs...'
                
                self.telemetry.flush()
                
                log_path = self.telemetry.get_log_path()
                if not os.path.exists(log_path):
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', 'No logs to export'), 0)
                    return
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                enc_filename = f'mission_telemetry_{timestamp}.enc'
                temp_enc_path = os.path.join(os.path.dirname(log_path), enc_filename)
                
                app = MDApp.get_running_app()
                db_mgr = getattr(app, 'engine', None) and getattr(app.engine, 'db_manager', None)
                cipher = getattr(db_mgr, 'cipher', None)
                if not encrypt_telemetry_file(log_path, temp_enc_path, cipher):
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', 'Encryption failed'), 0)
                    return
                
                final_path = copy_to_downloads(temp_enc_path, enc_filename)
                
                if final_path:
                    try:
                        from security import shred_file
                        shred_file(temp_enc_path)
                    except:
                        pass
                    
                    status_msg = f'✓ Exported to Downloads: {enc_filename}'
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', status_msg), 0)
                else:
                    Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', 'Export failed'), 0)
            
            except Exception as e:
                print(f"[DiagnosticsScreen] Export error: {e}")
                error_msg = f'Error: {str(e)[:40]}'
                Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', error_msg), 0)
        
        export_thread = threading.Thread(target=export_worker, daemon=True)
        export_thread.start()
    
    def clear_telemetry(self, instance=None):
        def clear_worker():
            try:
                self.telemetry.clear_logs()
                Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', '✓ Telemetry cleared'), 0)
            except Exception as e:
                print(f"[DiagnosticsScreen] Clear error: {e}")
                Clock.schedule_once(lambda dt: setattr(self.export_status_label, 'text', f'Clear error: {str(e)[:30]}'), 0)
        
        clear_thread = threading.Thread(target=clear_worker, daemon=True)
        clear_thread.start()
    
    def close_diagnostics(self, instance=None):
        app = MDApp.get_running_app()
        if app and app.root:
            app.root.current = 'radar'
