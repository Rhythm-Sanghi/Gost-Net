"""
Ghost Net UI - Radar and Mesh Canvas Components
High-fidelity sonar sweep canvas and dynamic 2D graph mesh topology visualization.
"""

import math
import hashlib
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.graphics import Color, Line, Ellipse, Rectangle


class RadarWidget(Widget):
    """Animated radar visualization for the home screen with high-fidelity effects."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.angle = 0
        self.pulse_val = 0.0
        self.peers = {}
        self._sweep_event = None
        self._pulse_event = None
        self.bind(pos=self.redraw, size=self.redraw)
        self.start_animation()

    def start_animation(self):
        """Start animation loops if not already active."""
        if not self._sweep_event:
            self._sweep_event = Clock.schedule_interval(self.animate_sweep, 0.03)
        if not self._pulse_event:
            self._pulse_event = Clock.schedule_interval(self.animate_pulse, 0.05)

    def stop_animation(self):
        """Stop animation loops to conserve CPU/battery when screen is not visible."""
        if self._sweep_event:
            self._sweep_event.cancel()
            self._sweep_event = None
        if self._pulse_event:
            self._pulse_event.cancel()
            self._pulse_event = None
        
    def update_peers(self, peers):
        self.peers = peers
        self.redraw()
        
    def redraw(self, *args):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        radius = min(self.width, self.height) * 0.45
        if radius <= 0:
            return
            
        with self.canvas:
            # Draw concentric background grid rings
            for i in range(1, 4):
                r = radius * (i / 3)
                Color(0.65, 0.79, 0.92, 0.06 * i)
                Line(circle=(cx, cy, r), width=1, dash_length=4, dash_offset=2)
                
            # Draw crosshairs (subtle grid axes)
            Color(0.65, 0.79, 0.92, 0.08)
            Line(points=[cx - radius, cy, cx + radius, cy], width=1)
            Line(points=[cx, cy - radius, cx, cy + radius], width=1)
            
            # Draw the rotating sweep trail (multiple lines with decaying alpha)
            for i in range(12):
                alpha = 0.8 * (1 - i / 12)
                trail_angle = (self.angle - i * 2.2) % 360
                rad = math.radians(trail_angle)
                tx = cx + radius * math.cos(rad)
                ty = cy + radius * math.sin(rad)
                
                Color(0.65, 0.79, 0.92, alpha)
                Line(points=[cx, cy, tx, ty], width=1.5 if i == 0 else 0.8)
            
            # Draw remote peer blips deterministically plotted on radar
            for ip, info in self.peers.items():
                h = int(hashlib.md5(ip.encode()).hexdigest(), 16)
                peer_angle = h % 360
                peer_dist_ratio = 0.3 + (h % 50) / 100.0
                
                p_rad = math.radians(peer_angle)
                px = cx + radius * peer_dist_ratio * math.cos(p_rad)
                py = cy + radius * peer_dist_ratio * math.sin(p_rad)
                
                # Draw pulsing blip halo
                pulse_r = 6 + self.pulse_val * 10
                pulse_alpha = 0.45 * (1.0 - self.pulse_val)
                Color(0.65, 0.79, 0.92, pulse_alpha)
                Line(circle=(px, py, pulse_r), width=1)
                
                # Outer circle
                Color(0.65, 0.79, 0.92, 0.35)
                Line(circle=(px, py, 6), width=1)
                
                # Solid inner node
                Color(0.65, 0.79, 0.92, 1.0)
                Ellipse(pos=(px - 3, py - 3), size=(6, 6))
            
            # Central local node with pulsing ring
            pulse_r = 10 + self.pulse_val * 25
            pulse_alpha = 0.5 * (1.0 - self.pulse_val)
            Color(0.65, 0.79, 0.92, pulse_alpha)
            Line(circle=(cx, cy, pulse_r), width=1)
            
            # Central ice-blue solid node
            Color(0.65, 0.79, 0.92, 1.0)
            Ellipse(pos=(cx - 5, cy - 5), size=(10, 10))
            
    def animate_sweep(self, dt):
        """Animate the sweep angle."""
        self.angle = (self.angle + 2) % 360
        self.redraw()
        
    def animate_pulse(self, dt):
        """Animate the sonar pulse."""
        self.pulse_val = (self.pulse_val + 0.02) % 1.0
        self.redraw()


class MeshTopologyWidget(Widget):
    """Visual network graph showing the local node, discovered peers, and mesh routes."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.routing_table = {}
        self.pulse_val = 0.0
        self.bind(pos=self.redraw, size=self.redraw)
        Clock.schedule_interval(self.animate_pulse, 0.05)
        
    def update_mesh(self, routing_table):
        self.routing_table = routing_table
        self.redraw()
        
    def animate_pulse(self, dt):
        self.pulse_val = (self.pulse_val + 0.02) % 1.0
        self.redraw()
        
    def redraw(self, *args):
        self.canvas.clear()
        self.clear_widgets()
        
        # Calculate center coordinates
        center_x = self.x + self.width / 2
        center_y = self.y + self.height / 2
        
        # Draw dark styling background matching matte obsidian
        with self.canvas:
            Color(0.04, 0.04, 0.05, 1)
            Rectangle(pos=self.pos, size=self.size)
            
        if not self.routing_table:
            # Draw local node only
            with self.canvas:
                # Pulsing halo
                pulse_r = 14 + self.pulse_val * 12
                pulse_alpha = 0.4 * (1.0 - self.pulse_val)
                Color(0.65, 0.79, 0.92, pulse_alpha)
                Line(circle=(center_x, center_y, pulse_r), width=1)
                
                Color(0.65, 0.79, 0.92, 0.3)
                Line(circle=(center_x, center_y, 18), width=1.5)
                Color(0.65, 0.79, 0.92, 1) # Ice-Blue
                Ellipse(pos=(center_x - 10, center_y - 10), size=(20, 20))
            
            # Local node label
            lbl = Label(text="ME (Local)", font_size='12sp', color=(0.65, 0.79, 0.92, 1))
            lbl.pos = (center_x - 50, center_y - 35)
            lbl.size = (100, 20)
            self.add_widget(lbl)
            return
            
        # Extract unique nodes
        nodes = set()
        for dest, route in self.routing_table.items():
            if dest == 'error':
                continue
            nodes.add(dest)
            if isinstance(route, dict):
                next_hop = route.get('next_hop')
                if next_hop and next_hop != 'N/A' and next_hop != dest:
                    nodes.add(next_hop)
                    
        nodes_list = sorted(list(nodes))
        num_nodes = len(nodes_list)
        
        if num_nodes == 0:
            with self.canvas:
                # Pulsing halo
                pulse_r = 14 + self.pulse_val * 12
                pulse_alpha = 0.4 * (1.0 - self.pulse_val)
                Color(0.65, 0.79, 0.92, pulse_alpha)
                Line(circle=(center_x, center_y, pulse_r), width=1)
                
                Color(0.65, 0.79, 0.92, 0.3)
                Line(circle=(center_x, center_y, 18), width=1.5)
                Color(0.65, 0.79, 0.92, 1)
                Ellipse(pos=(center_x - 10, center_y - 10), size=(20, 20))
            lbl = Label(text="ME (Local)", font_size='12sp', color=(0.65, 0.79, 0.92, 1))
            lbl.pos = (center_x - 50, center_y - 35)
            lbl.size = (100, 20)
            self.add_widget(lbl)
            return
            
        # Distribute remote nodes on a circle
        radius = min(self.width, self.height) * 0.35
        node_coords = {}
        
        for i, node_id in enumerate(nodes_list):
            angle = 2 * math.pi * i / num_nodes
            nx = center_x + radius * math.cos(angle)
            ny = center_y + radius * math.sin(angle)
            node_coords[node_id] = (nx, ny)
            
        with self.canvas:
            # Draw route connections
            for dest, route in self.routing_table.items():
                if dest not in node_coords:
                    continue
                
                dest_coords = node_coords[dest]
                next_hop = None
                if isinstance(route, dict):
                    next_hop = route.get('next_hop')
                    
                if not next_hop or next_hop == dest or next_hop == 'N/A':
                    # Direct route (ice-blue)
                    Color(0.65, 0.79, 0.92, 0.8)
                    Line(points=[center_x, center_y, dest_coords[0], dest_coords[1]], width=1.5)
                else:
                    # Indirect route via next_hop (dashed grey-indigo)
                    if next_hop in node_coords:
                        hop_coords = node_coords[next_hop]
                        # Draw local to next hop (ice-blue translucent)
                        Color(0.65, 0.79, 0.92, 0.4)
                        Line(points=[center_x, center_y, hop_coords[0], hop_coords[1]], width=1.5)
                        # Draw next hop to destination (dashed grey-indigo)
                        Color(0.25, 0.32, 0.45, 0.6)
                        Line(points=[hop_coords[0], hop_coords[1], dest_coords[0], dest_coords[1]], width=1.5, dash_length=4, dash_offset=2)
                        
            # Draw local node with pulsing outer glow ring
            pulse_r = 14 + self.pulse_val * 12
            pulse_alpha = 0.4 * (1.0 - self.pulse_val)
            Color(0.65, 0.79, 0.92, pulse_alpha)
            Line(circle=(center_x, center_y, pulse_r), width=1)
            
            Color(0.65, 0.79, 0.92, 0.3)
            Line(circle=(center_x, center_y, 18), width=1.5)
            Color(0.65, 0.79, 0.92, 1) # Ice-Blue
            Ellipse(pos=(center_x - 10, center_y - 10), size=(20, 20))
            
            # Draw remote nodes with pulsing outer glow ring
            for node_id, coords in node_coords.items():
                pulse_rem_r = 10 + self.pulse_val * 10
                pulse_rem_alpha = 0.4 * (1.0 - self.pulse_val)
                Color(0.18, 0.36, 0.68, pulse_rem_alpha)
                Line(circle=(coords[0], coords[1], pulse_rem_r), width=1)
                
                Color(0.18, 0.36, 0.68, 0.3)
                Line(circle=(coords[0], coords[1], 14), width=1.5)
                Color(0.18, 0.36, 0.68, 0.85) # Indigo
                Ellipse(pos=(coords[0] - 8, coords[1] - 8), size=(16, 16))
                
        # Draw labels
        lbl = Label(text="ME (Local)", font_size='12sp', color=(0.65, 0.79, 0.92, 1))
        lbl.pos = (center_x - 50, center_y - 35)
        lbl.size = (100, 20)
        self.add_widget(lbl)
        
        for node_id, coords in node_coords.items():
            label_text = node_id[:8] + "..." if len(node_id) > 8 else node_id
            lbl = Label(text=label_text, font_size='11sp', color=(0.8, 0.8, 0.8, 1))
            lbl.pos = (coords[0] - 50, coords[1] - 25)
            lbl.size = (100, 15)
            self.add_widget(lbl)
