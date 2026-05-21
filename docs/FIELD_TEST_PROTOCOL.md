# Ghost Net Field Test Protocol - Phase 1 & Phase 2 Indore Deployment

## 1. Signal Threshold Performance Table

| RSSI Range (dBm) | Bluetooth Status | Wi-Fi Direct Status | Mesh Stability | Packet Loss | Latency | Radar Update | Action Required |
|---|---|---|---|---|---|---|---|
| -30 to -50 | Excellent | Excellent | Optimal | 0% | <10ms | Real-time | Continue operations |
| -60 to -70 | Good | Good | Stable | 0-2% | 10-50ms | 500ms update | Monitor for degradation |
| -80 to -90 | Marginal | Marginal | Churning | 5-15% | 50-200ms | 2-5s delay | Activate relay nodes |
| -100 | Critical | Disconnected | Failed | >30% | >500ms | Disappears | Reconnect or abort |
| Below -100 | Loss | Loss | Loss | 100% | Timeout | Offline | Out of range |

## 2. Three-Node Hop Test Procedure

### Pre-Test Setup

- [ ] All three devices charged to 100%
- [ ] Location app enabled on all nodes
- [ ] Mission telemetry logging enabled in settings
- [ ] Diagnostics screen accessible (press volume_up + power simultaneously 5 times)
- [ ] GPS fix acquired on all nodes (allow 60 seconds)
- [ ] Network stack initialized (verify "Ready" state in Radar)

### Node Positioning & Deployment

**Node A (Static Beacon)**
- [ ] Plant at test origin point (e.g., campus gate)
- [ ] Enable "Force Beacon" mode in diagnostics
- [ ] Verify transmitting status in Radar (green dot, pulsing)
- [ ] Record GPS coordinates

**Node B (50m Relay)**
- [ ] Position exactly 50m from Node A (measure with GPS or wheel)
- [ ] Ensure unobstructed line-of-sight to Node A
- [ ] Enable "Relay Mode" in diagnostics
- [ ] Set hop_limit to 2 (allows one bounce)
- [ ] Verify both upstream (to A) and downstream (to C) links establish

**Node C (100m Target)**
- [ ] Position 100m from Node A (or 50m from Node B at 90-degree angle)
- [ ] Partial obstruction acceptable (test LOS + NLOS variants)
- [ ] Enable passive telemetry collection
- [ ] Verify Radar shows both A and B as peers

### Multi-Hop Relay Verification

**Via Diagnostics Screen (Hidden Interface)**

1. Launch diagnostics overlay (vol_up + power x5)
2. Navigate to "Network Mesh" tab
3. Verify Node B shows:
   - `relay_mode: ACTIVE`
   - `upstream_peer: Node_A_MAC`
   - `downstream_peers: [Node_C_MAC]`
   - `hop_count_to_origin: 1`
   - `relay_latency: <150ms`

4. On Node C, verify:
   - `next_hop: Node_B_MAC`
   - `route_quality: ESTABLISHED`
   - `rssi_via_relay: -65 to -85 dBm (degraded from direct)`
   - `packet_retransmissions: <5%`

5. Initiate test sequence:
   - [ ] Send test message from A to C (should relay through B)
   - [ ] Verify delivery confirmation on C
   - [ ] Check Node B relay buffer (should show transit packet)
   - [ ] Verify latency increase (baseline + relay overhead ~50-100ms)

**Via Radar Display**

- [ ] Node A appears as origin (blue dot)
- [ ] Node B visible between A and C (yellow dot, relay indicator)
- [ ] Node C visible with dashed line to B (indicating relayed route)
- [ ] Signal strength bars decrease proportionally with distance

### Test Duration & Logging

- [ ] Run test for minimum 10 minutes
- [ ] Send 50 test packets minimum (trigger via PTT or chat)
- [ ] Record any disconnections or route flaps in manual log
- [ ] Monitor battery drain (should be <5% per 10 minutes)

## 3. Mission Telemetry Extraction Protocol

### Post-Test Data Retrieval

**Connect device via USB and execute:**

```
adb connect <device_ip>:5555
adb pull /data/data/com.ghostnet.app/files/mission_telemetry.csv ./telemetry_phase1.csv
```

**Alternative paths if primary path inaccessible:**

```
adb shell find /sdcard -name "mission_telemetry.csv" -type f
adb pull /sdcard/mission_telemetry.csv ./telemetry_backup.csv
```

**Verify extraction:**

```
adb shell wc -l /data/data/com.ghostnet.app/files/mission_telemetry.csv
```

### Data Analysis Pipeline

**Feed extracted CSV into mission_analyzer.py:**

```
python3 mission_analyzer.py --input telemetry_phase1.csv --output phase1_analysis.json --format verbose
```

**Generate visualizations:**

```
python3 mission_analyzer.py --input telemetry_phase1.csv --plot rssi_timeline --output phase1_rssi_chart.png
python3 mission_analyzer.py --input telemetry_phase1.csv --plot packet_loss_heatmap --output phase1_loss_map.png
python3 mission_analyzer.py --input telemetry_phase1.csv --plot latency_distribution --output phase1_latency.png
```

**Extract summary statistics:**

```
python3 mission_analyzer.py --input telemetry_phase1.csv --summary --format csv > phase1_summary.txt
```

### CSV Column Reference

- `timestamp`: Unix epoch (seconds)
- `event_type`: RSSI_SAMPLE, PACKET_SENT, PACKET_RECEIVED, HANDSHAKE_FAILED, RELAY_ACTIVATED, GPS_FIX, BATTERY_STATUS
- `source_mac`: Originating device MAC address
- `dest_mac`: Target device MAC address (for routing: next_hop_mac)
- `rssi_dbm`: Signal strength (-30 to -100 range)
- `packet_loss_percent`: 0-100 scale
- `latency_ms`: Milliseconds (includes relay overhead)
- `hop_distance`: Hops traversed (1=direct, 2+=relayed)
- `gps_lat` / `gps_lon`: Latitude/longitude
- `battery_percent`: Device charge level
- `interference_profile`: CLEAN, MODERATE, HIGH (detected 2.4GHz saturation)

## 4. Indore Urban Environment Notes

### High-Interference Zones (2.4GHz Saturation)

**Known Problematic Areas:**
- SVCE Campus: Heavy WiFi mesh (50+ SSID, dense AP deployment)
- Indore Market Area (indoor): Microwave ovens, abundant Bluetooth devices
- Near Telecom Towers: Power amplifiers may cause adjacent-channel interference
- Shopping Malls: Dense consumer WiFi, simultaneous video streaming

### Interference Mitigation Strategies

**Phase 1 (Line-of-Sight) Testing:**
- [ ] Conduct early morning (6-8 AM) for minimum ambient traffic
- [ ] Use frequency scan tool: `adb shell dumpsys wifi | grep -i frequency`
- [ ] If 2.4GHz saturated (>20 accessory devices), document as "HIGH_INTERFERENCE"
- [ ] Switch to 5GHz direct connection if available (Ghost Net auto-selects)

**Phase 2 (Urban Penetration) Testing:**
- [ ] Expect 10-20% higher packet loss in interference zones
- [ ] HANDSHAKE_FAILED events are normal (retry logic handles)
- [ ] Record interference profile in telemetry for correlation
- [ ] Use shielded locations (stairwells, basements) as control tests

### HANDSHAKE_FAILED Telemetry Interpretation

**High-Interference Environments:**

| Event Frequency | RSSI | Interpretation | Action |
|---|---|---|---|
| <5 per minute | -60 to -80 | Normal retry behavior in busy band | Continue test |
| 5-15 per minute | -70 to -90 | Moderate congestion, expect 5-10% loss | Relocate or wait |
| >15 per minute | <-90 | Severe interference or link failure | Abort test, relocate |

**Root Cause Analysis in mission_telemetry.csv:**

1. Extract HANDSHAKE_FAILED events:
```
grep "HANDSHAKE_FAILED" telemetry_phase1.csv > failed_handshakes.csv
```

2. Cross-reference with concurrent RSSI samples:
```
awk '{print $1}' failed_handshakes.csv | while read ts; do grep -B2 -A2 "^$ts" telemetry_phase1.csv | grep "RSSI_SAMPLE"; done
```

3. Correlate with interference_profile field:
   - If `interference_profile: HIGH` and `HANDSHAKE_FAILED`: Environmental (not device issue)
   - If `interference_profile: CLEAN` and `HANDSHAKE_FAILED`: May indicate firmware/hardware defect

### GPS Accuracy in Urban Canyon

**Expected GPS Performance:**
- Open space (SVCE grounds): ±5-10 meters (4-satellite minimum)
- Urban streets (sparse buildings): ±15-30 meters (3-4 satellites + multipath)
- Dense urban (near towers): ±30-50 meters (weak GNSS, IP-based fallback)

**Telemetry note:** GPS_FIX events with `dilution_of_precision > 5` indicate marginal accuracy; flag in analysis.

### Environmental Baseline Testing

**Before Phase 1 deployment, conduct 15-minute baseline:**

```
adb shell am start -n com.ghostnet.app/.DiagnosticsActivity
```

Record:
- Active WiFi SSIDs and signal strengths (wifi scan)
- Bluetooth device count in vicinity
- Cellular band and signal strength
- Ambient temperature and humidity (if sensor available)

Save as `baseline_indore_<date>.txt` for reference during data interpretation.

## 5. Emergency Procedures

### Node Disconnection / Link Loss

1. Verify RSSI reading (should be >-100 dBm)
2. Check GPS accuracy (dilution_of_precision <5)
3. If relaying: confirm relay node is powered and in range
4. Restart network stack: Settings → Network → Restart
5. If persistent: Power cycle entire mesh and re-establish

### Telemetry Extraction Failure

**If adb pull fails:**

```
adb shell su
cp /data/data/com.ghostnet.app/files/mission_telemetry.csv /sdcard/
exit
adb pull /sdcard/mission_telemetry.csv ./telemetry_recovery.csv
```

**If database locked:**

```
adb shell am force-stop com.ghostnet.app
adb shell sleep 3
adb pull /data/data/com.ghostnet.app/files/mission_telemetry.csv ./telemetry_force.csv
```

### Duress Data Shredder Activation

During high-risk zones (if authorized for testing):

```
adb shell am broadcast -a com.ghostnet.DURESS_TRIGGER
```

Verify secure erasure in telemetry (`SHRED_EVENT` entries), then reconstruct test from backup if needed.

## 6. Post-Test Checklist

- [ ] All three telemetry.csv files extracted and timestamped
- [ ] mission_analyzer.py analysis completed with output JSON
- [ ] Radar screenshots captured showing final topology
- [ ] Diagnostics logs exported (vol_up + power, export function)
- [ ] Manual notes transcribed (time, location, interference, anomalies)
- [ ] GPS track file saved (if available in app)
- [ ] Battery drain profile documented
- [ ] Phase 1/2 classification confirmed for each test segment
