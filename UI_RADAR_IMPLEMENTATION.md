# Ghost Net - P2P Radar UI Implementation

Complete guide to the updated RadarScreen displaying WiFi LAN, WiFi Direct, and Bluetooth peers with filtering and dynamic secondary text.

---

## Overview

The RadarScreen now displays three types of peers simultaneously with distinct visual indicators, filtering controls, and context-aware secondary information.

---

## UI Components

### 1. Filter Bar

Four filter buttons at the top of the peer list:

```
[All] [WiFi LAN] [WiFi Direct] [Bluetooth]
```

- **All** — Shows all discovered peers (default)
- **WiFi LAN** — Shows only UDP broadcast peers (IP-based)
- **WiFi Direct** — Shows only WiFi P2P peers (MAC-based)
- **Bluetooth** — Shows only Bluetooth devices (BT address-based)

Active filter button has `style='elevated'`, inactive have `style='outlined'`.

### 2. Peer List Items

Each peer is displayed in an MDCard with:
- **Icon** — Distinct icon per discovery type
- **Primary Text** — Peer name (username or device_name)
- **Secondary Text** — Context-aware technical data
- **Chat Button** — Navigate to chat (WiFi LAN only)

---

## Visual Indicators

### WiFi LAN Peers
```
Icon: wifi (green 📶)
Color: (0.2, 0.8, 0.3, 1)
Secondary: IP: 192.168.1.10
Button: Enabled (Chat available)
```

### WiFi Direct Peers
```
Icon: cellphone-link (blue 📡)
Color: (0.2, 0.6, 1.0, 1)
Secondary: MAC: aa:bb:cc:dd:ee:ff (GO: 192.168.49.1)
Button: Disabled (P2P not yet implemented)
```

### Bluetooth Peers
```
Icon: bluetooth (orange 🔵)
Color: (0.9, 0.5, 0.2, 1)
Secondary: BT: bb:cc:dd:ee:ff:11 (Signal: -45 dBm)
Button: Disabled (BT not yet implemented)
```

---

## Data Flow

```
GhostEngine.start()
    ↓
Peer discovery threads (LAN, WiFi Direct, Bluetooth)
    ↓
on_peer_update callback (from network engine)
    ↓
RadarScreen.update_peers(peers_dict)
    ↓
Store in self.all_peers
    ↓
_render_filtered_peers()
    ↓
Filter by active_filter
    ↓
Generate peer list items with icons/colors/secondary text
    ↓
Display in peers_scroll
```

---

## Implementation Details

### Filter Storage
```python
self.active_filter = 'all'
self.all_peers = {}
```

### Filter Buttons
```python
self.filter_buttons = {}
for filter_type, label in zip(['all', 'lan', 'p2p', 'bluetooth'], 
                               ['All', 'WiFi LAN', 'WiFi Direct', 'Bluetooth']):
    btn = MDButton(...)
    btn.bind(on_release=lambda x, f=filter_type: self.set_filter(f))
    self.filter_buttons[filter_type] = btn
```

### Set Filter Method
```python
def set_filter(self, filter_type):
    self.active_filter = filter_type
    
    for f_type, btn in self.filter_buttons.items():
        btn.style = 'elevated' if f_type == filter_type else 'outlined'
    
    self._render_filtered_peers()
```

### Icon & Color Mapping
```python
def _get_icon_and_color_for_peer(self, discovery_type):
    icon_map = {
        'wifi_lan': ('wifi', (0.2, 0.8, 0.3, 1)),
        'wifi_direct': ('cellphone-link', (0.2, 0.6, 1.0, 1)),
        'bluetooth': ('bluetooth', (0.9, 0.5, 0.2, 1))
    }
    return icon_map.get(discovery_type, ('help-circle', (0.5, 0.5, 0.5, 1)))
```

### Secondary Text Generation
```python
def _get_secondary_text(self, peer_info):
    discovery_type = peer_info.get('discovery_type', 'unknown')
    
    if discovery_type == 'wifi_lan':
        return f"IP: {peer_info.get('ip', 'N/A')}"
    elif discovery_type == 'wifi_direct':
        mac = peer_info.get('mac_address', 'Unknown')
        go_ip = peer_info.get('go_ip')
        if go_ip:
            return f"MAC: {mac} (GO: {go_ip})"
        return f"MAC: {mac}"
    elif discovery_type == 'bluetooth':
        bt_addr = peer_info.get('bluetooth_address', 'Unknown')
        rssi = peer_info.get('rssi')
        if rssi:
            return f"BT: {bt_addr} (Signal: {rssi} dBm)"
        return f"BT: {bt_addr}"
    
    return "Unknown peer type"
```

### Rendering Filtered Peers
```python
def _render_filtered_peers(self):
    self.peers_list.clear_widgets()
    
    if not self.all_peers:
        self.status_label.text = "No peers found. Waiting..."
        return
    
    filtered_peers = {}
    
    if self.active_filter == 'all':
        filtered_peers = self.all_peers
    elif self.active_filter == 'lan':
        filtered_peers = {k: v for k, v in self.all_peers.items() 
                         if v.get('discovery_type') == 'wifi_lan'}
    elif self.active_filter == 'p2p':
        filtered_peers = {k: v for k, v in self.all_peers.items() 
                         if v.get('discovery_type') == 'wifi_direct'}
    elif self.active_filter == 'bluetooth':
        filtered_peers = {k: v for k, v in self.all_peers.items() 
                         if v.get('discovery_type') == 'bluetooth'}
    
    self.status_label.text = f"Found {len(filtered_peers)} peer(s) ({len(self.all_peers)} total)"
    
    for peer_id, peer_info in filtered_peers.items():
        discovery_type = peer_info.get('discovery_type', 'unknown')
        icon_name, icon_color = self._get_icon_and_color_for_peer(discovery_type)
        
        peer_name = peer_info.get('username') or peer_info.get('device_name', 'Unknown')
        secondary_text = self._get_secondary_text(peer_info)
        
        item = MDCard(...)
        item_layout = MDBoxLayout(orientation='horizontal', spacing=dp(12), padding=dp(5))
        
        icon_widget = MDIconButton(
            icon=icon_name,
            theme_icon_color='Custom',
            icon_color=icon_color,
            icon_size="32sp",
            size_hint_x=None,
            width=dp(48)
        )
        
        peer_content = MDBoxLayout(orientation='vertical', size_hint_x=0.65, spacing=dp(3))
        
        peer_label = MDLabel(text=peer_name, ...)
        secondary_label = MDLabel(text=secondary_text, ...)
        
        peer_content.add_widget(peer_label)
        peer_content.add_widget(secondary_label)
        
        chat_btn = MDButton(style='text', size_hint_x=0.35)
        chat_btn.add_widget(MDButtonText(text="Chat"))
        
        if discovery_type == 'wifi_lan':
            peer_ip = peer_info.get('ip')
            chat_btn.bind(on_release=lambda x, ip=peer_ip, name=peer_name: self.open_chat(ip, name))
        else:
            chat_btn.disabled = True
            chat_btn.opacity = 0.5
        
        item_layout.add_widget(icon_widget)
        item_layout.add_widget(peer_content)
        item_layout.add_widget(chat_btn)
        
        item.add_widget(item_layout)
        self.peers_list.add_widget(item)
```

### Update Peers Method
```python
def update_peers(self, peers_dict):
    if not peers_dict:
        self.all_peers = {}
        self.status_label.text = "No peers found. Waiting..."
        self.peers_list.clear_widgets()
        return
    
    self.all_peers = peers_dict.copy()
    self._render_filtered_peers()
```

---

## Layout Structure

```
┌─────────────────────────────────────┐
│ Header (Title + Badge + Settings)   │  height=60dp
├─────────────────────────────────────┤
│ Radar Animation                     │  height=35% of screen
├─────────────────────────────────────┤
│ Status Label                        │  height=30dp
│ (Found X peer(s) (Y total))         │
├─────────────────────────────────────┤
│ [All] [LAN] [P2P] [Bluetooth]       │  height=50dp
├─────────────────────────────────────┤
│ Discovered Peers Label              │  height=40dp
├─────────────────────────────────────┤
│ Peer List (Scrollable)              │  height=remaining
│                                     │
│ ┌──────────────────────────────────┐│
│ │ 📶 Alice                         ││  height=70dp
│ │    IP: 192.168.1.10              ││
│ │                    [Chat] ▶      ││
│ ├──────────────────────────────────┤│
│ │ 📡 Samsung_Phone                 ││  height=70dp
│ │    MAC: aa:bb:cc:dd:ee:ff        ││
│ │                    [Chat] ▶      ││
│ ├──────────────────────────────────┤│
│ │ 🔵 Google_Pixel                  ││  height=70dp
│ │    BT: bb:cc:dd:ee:ff (RSSI -45) ││
│ │                    [Chat] ▶      ││
│ └──────────────────────────────────┘│
└─────────────────────────────────────┘
```

---

## Testing

### Desktop Testing
```bash
python main.py
```

Expected behavior:
1. Boot screen shows "Initializing..."
2. Transitions to radar screen
3. Mock APIs log "Discovering peers (mock)"
4. No actual peers appear (expected on desktop)
5. Filter buttons available but no peers to filter

### Phone Testing
```bash
buildozer android debug deploy run logcat
```

Expected behavior:
1. App launches with radar animation
2. Status shows "Found X peer(s) (Y total)"
3. LAN peers appear (if on same network)
4. WiFi Direct peers appear (if device nearby)
5. Bluetooth peers appear (if devices paired)
6. Click filters to show/hide peer types
7. Click "Chat" button on LAN peers to open chat

---

## Interactive Features

### Filter Switching
- Click any filter button
- Active button becomes `elevated`, others become `outlined`
- Peer list instantly updates to show only selected type
- Status label updates with filtered count

### Peer Selection
- Click "Chat" button on WiFi LAN peer
- Navigates to ChatScreen with that peer
- P2P and Bluetooth peers show disabled button (not yet implemented)

### Dynamic Status
- Shows "Found X peer(s) (Y total)"
- X = number of peers in active filter
- Y = total peers across all types

---

## Responsive Design

All components use KivyMD adaptive sizing:
- `size_hint_x` for horizontal distribution
- `size_hint_y` for vertical distribution
- `adaptive_height=True` for content-based sizing
- `size_hint_y=None, height=dp()` for fixed heights
- Widget spacing controlled with `spacing=dp()`

---

## Color Scheme

- WiFi LAN: Green (0.2, 0.8, 0.3, 1) — Trusted local network
- WiFi Direct: Blue (0.2, 0.6, 1.0, 1) — Direct P2P connection
- Bluetooth: Orange (0.9, 0.5, 0.2, 1) — Short-range wireless
- Card background: (0.08, 0.08, 0.12, 1) — Dark theme consistency

---

## Future Enhancements

1. WiFi Direct peer connection UI
2. Bluetooth RFCOMM connection UI
3. Peer signal strength visualization (RSSI bars)
4. Peer online/offline status indicators
5. Peer filtering by signal strength
6. Peer discovery statistics/history
7. Peer blocking/favorite functionality
8. Custom peer icons/emojis

---

## API Integration

RadarScreen expects the network engine to call:
```python
radar_screen.update_peers(peers_dict)
```

With `peers_dict` containing:
```python
{
    'peer_id': {
        'discovery_type': 'wifi_lan|wifi_direct|bluetooth',
        'username': 'Alice',                    # LAN only
        'device_name': 'Samsung_Phone',         # P2P/BT
        'ip': '192.168.1.10',                   # LAN only
        'mac_address': 'aa:bb:cc:dd:ee:ff',    # P2P only
        'go_ip': '192.168.49.1',                # P2P optional
        'bluetooth_address': 'bb:cc:dd:ee:ff',  # BT only
        'rssi': -45,                            # BT optional
        'last_seen': 1234567890.123
    }
}
```

---

## Code Statistics

- **File**: main.py (RadarScreen class)
- **Lines Added**: ~200 (new filtering + rendering methods)
- **No Comments**: Python code as requested
- **Syntax**: All files pass `python -m py_compile`
- **KivyMD Compatibility**: Full Material Design 3 support

---

## Verification

✅ RadarScreen updated with filtering UI
✅ Icon mapping for all peer types
✅ Dynamic secondary text per type
✅ Filter state management
✅ Responsive layout maintained
✅ No comments in code
✅ All files compile without errors
✅ Integrates with network engine
