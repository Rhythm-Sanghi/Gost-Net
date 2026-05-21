![Build Status](https://github.com/Rhythm-Sanghi/Gost-Net/actions/workflows/build.yml/badge.svg)

# 👻 Ghost Net v1.0

**An encrypted, decentralized, multi-hop mesh communication network for off-grid tactical operations.**

---

## Overview

Ghost Net is a production-grade mobile mesh network framework engineered for secure, resilient communication in austere and contested environments. Designed for tactical teams, humanitarian operations, and decentralized networks, Ghost Net provides authenticated encryption, multi-hop routing with blind relays, offline-first operational capability, and forensic countermeasures.

Built on Kivy for Android with cryptographic hardening, Ghost Net eliminates dependency on cellular infrastructure while maintaining operational security through end-to-end encryption and duress protection mechanisms.

---

## Core Capabilities

| Capability | Implementation | Status |
|---|---|---|
| **Encryption** | ECDH (SECP384R1) + AES-256-GCM authenticated encryption with forward secrecy | ✓ Production |
| **Mesh Networking** | Multi-hop blind relay routing protocol with dynamic peer discovery and topology adaptation | ✓ Production |
| **Stealth & OPSEC** | Duress PIN triggers, cryptographic data shredder, suppressed diagnostic telemetry, minimal logging footprint | ✓ Production |
| **Offline Operations** | Cached tactical maps via kivy_garden.mapview, GPS/SOS emergency broadcast flooding, PTT audio notes with local playback | ✓ Production |
| **Push-to-Talk** | Real-time voice streaming with adaptive codec selection and mesh-routed delivery | ✓ Production |
| **Mission Telemetry** | SQLite-backed flight data recorder with encrypted event logging and forensic extraction | ✓ Production |
| **Platform Abstraction** | Android P2P, WiFi Direct, Bluetooth LE with feature parity across platforms | ✓ Production |

---

## Architecture Subsystems

### End-to-End Encryption (E2EE)

- ECDH key exchange on SECP384R1 curve (384-bit ephemeral keys)
- AES-256-GCM authenticated encryption (16-byte nonce, 16-byte authentication tag)
- Per-session key derivation with HKDF-SHA256
- Forward secrecy: keys rotated per message batch

### Multi-Hop Mesh Routing

- Blind relay protocol: intermediate nodes forward without decryption
- Hop-limited flooding (TTL enforcement) to prevent loops
- Dynamic peer table with RSSI-weighted route selection
- Mesh healing: automatic alternate path discovery on link loss

### SQLite Persistence Layer

- Encrypted database schema with AES-256-GCM at rest
- Atomic transactions for mission-critical telemetry
- Journaled writes to prevent data corruption on power loss
- Rapid checkpoint cycles for low-latency logging

### Push-to-Talk Audio Manager

- Opus codec with 20ms frame rate and 48kHz sampling
- Adaptive bitrate (8-128 kbps) for bandwidth-constrained mesh links
- Mesh-routed delivery with per-hop jitter buffering
- Automatic gain control and voice activity detection

### Tactical Maps (Offline)

- Map tiles cached from OpenStreetMap during setup phase
- Offline rendering without internet dependency
- GPS waypoint overlay with SOS broadcast coordinates
- Map-view integration with Radar peer display

### GPS & SOS Flooding

- Continuous GPS sampling at 1Hz (configurable)
- Emergency broadcast protocol: beacons entire mesh on distress trigger
- Location telemetry stored locally with encryption
- Battery-aware sampling throttle for extended operations

### Mission Telemetry Logger

- Event-driven logging: handshake, packet loss, battery, GPS, duress events
- CSV export format for post-mission analysis
- Extraction via adb or local file transfer
- mission_analyzer.py tool for visualization and statistical analysis

### Duress Data Shredder

- PIN entry: hold power button and enter secret sequence
- Cryptographic overwrite: 7-pass DOD 5220.22-M standard
- Selectively whitelist core configs (map data, keys) or full wipe
- Triggers after 10-second countdown (cancellable)

### Fleet Deployment Script (deploy_fleet.sh)

- Automated APK signing and installation across multiple Android devices
- Over-the-air provisioning of mesh keys and roster
- Batch firmware updates and configuration rollout
- Health check and readiness verification post-deployment

---

## Hidden Diagnostics & Engineering Mode

Ghost Net includes a concealed diagnostics interface for advanced troubleshooting and operational monitoring. The interface is accessible via a multi-tap hardware trigger on the device.

**Access Method:**
Press the volume_up button and power button simultaneously 5 times in rapid succession. Upon successful activation, the diagnostics overlay will display.

**Diagnostics Capabilities:**
- Live network mesh topology with peer RSSI and hop counts
- Real-time relay activation and packet transit visualization
- Encrypted telemetry event stream with raw timestamps
- Battery drain profiling and thermal monitoring
- GPS accuracy metrics (dilution of precision, satellite count)
- Interference profile detection (ambient 2.4GHz saturation)
- Manual test packet injection for link quality assessment
- Emergency log export with USB debugging enabled

This interface is intentionally hidden to prevent accidental activation during field operations and to maintain operational security in contested environments.

---

## Field Testing & Mission Analysis

### Tactical Range Testing

Comprehensive field test procedures are documented in [`FIELD_TEST_PROTOCOL.md`](FIELD_TEST_PROTOCOL.md), covering:

- **Phase 1 (Line-of-Sight):** Direct peer-to-peer mesh evaluation with RSSI threshold mapping
- **Phase 2 (Urban Penetration):** Real-world obstruction and multi-hop relay performance under challenging RF conditions
- **Signal Degradation Reference:** RSSI performance table (-30 to -100 dBm) with expected packet loss and latency
- **3-Node Hop Procedure:** Methodology for testing blind relay activation and mesh routing integrity
- **Environment-Specific Notes:** Indore urban interference mitigation, GPS accuracy expectations, baseline RF profiling

### Mission Data Extraction & Analysis

Post-mission telemetry analysis workflow:

**1. Extract mission telemetry from device:**
```
adb pull /data/data/com.ghostnet.app/files/mission_telemetry.csv ./telemetry_phase1.csv
```

**2. Run mission analyzer for comprehensive breakdown:**
```
python3 mission_analyzer.py --input telemetry_phase1.csv --output phase1_analysis.json --format verbose
```

**3. Generate visualization plots:**
```
python3 mission_analyzer.py --input telemetry_phase1.csv --plot rssi_timeline --output phase1_rssi_chart.png
python3 mission_analyzer.py --input telemetry_phase1.csv --plot packet_loss_heatmap --output phase1_loss_map.png
python3 mission_analyzer.py --input telemetry_phase1.csv --plot latency_distribution --output phase1_latency.png
```

The [`mission_analyzer.py`](mission_analyzer.py) tool parses encrypted telemetry logs, validates event authenticity, and produces statistical summaries with geographic correlations.

---

## Installation

### Option 1: Download Pre-Built APK from GitHub Actions

Latest builds are available in the [Releases](https://github.com/Rhythm-Sanghi/Gost-Net/releases) page or via GitHub Actions artifacts:

1. Navigate to [Actions](https://github.com/Rhythm-Sanghi/Gost-Net/actions)
2. Select the latest successful build workflow run
3. Download the `ghost-net-release.apk` artifact
4. Transfer to Android device (7.0+) via USB
5. Install: `adb install ghost-net-release.apk`

### Option 2: Build Locally with Deploy Script

**Prerequisites:**
- Python 3.8+
- Buildozer 1.4+
- Android SDK (API 28+)
- Kivy 2.1+

**Build and Deploy:**
```
chmod +x deploy_fleet.sh
./deploy_fleet.sh --build --sign --install
```

For multi-device deployment:
```
./deploy_fleet.sh --build --sign --install --devices <device_serial_1> <device_serial_2>
```

**Offline Build (without GitHub Actions):**
```
buildozer android release
```

APK will be generated at `bin/ghost-net-<version>-release-unsigned.apk`.

---

## System Requirements

- **Android:** 7.0 (API 24) or higher
- **RAM:** Minimum 512 MB (2 GB recommended)
- **Storage:** 50 MB free space (plus map tile cache, ~100 MB per region)
- **Connectivity:** Bluetooth 4.0+, WiFi Direct support
- **GPS:** Hardware or network-based (for location telemetry)

---

## Documentation

- **[FIELD_TEST_PROTOCOL.md](FIELD_TEST_PROTOCOL.md)** - Tactical range testing procedures and environmental adaptation guide
- **[E2EE_IMPLEMENTATION_GUIDE.md](E2EE_IMPLEMENTATION_GUIDE.md)** - Cryptographic design and key derivation details
- **[MESH_NETWORK_IMPLEMENTATION.md](MESH_NETWORK_IMPLEMENTATION.md)** - Routing protocol, blind relay mechanics, and topology management
- **[PTT_VOICE_MESSAGING_IMPLEMENTATION.md](PTT_VOICE_MESSAGING_IMPLEMENTATION.md)** - Audio codec, streaming, and mesh delivery
- **[TACTICAL_MAP_IMPLEMENTATION.md](TACTICAL_MAP_IMPLEMENTATION.md)** - Offline map caching and GPS integration
- **[TELEMETRY_INTEGRATION.md](TELEMETRY_INTEGRATION.md)** - Event logging and mission data extraction
- **[PRODUCTION_RELEASE_BUILD_GUIDE.md](PRODUCTION_RELEASE_BUILD_GUIDE.md)** - Build pipeline, signing, and GitHub Actions configuration

---

## Security Considerations

Ghost Net is engineered for tactical deployments where security is paramount. Key design decisions:

- **Encryption at Rest:** SQLite database encrypted with AES-256-GCM
- **Encryption in Transit:** All mesh traffic authenticated with per-message encryption
- **Key Management:** ECDH ephemeral keys, HKDF key derivation, no plaintext key storage
- **Operational Security:** Duress shredder, log suppression, minimal persistent state
- **Forensic Hardening:** Cryptographic cache clearing, secure deletion standards (DOD 5220.22-M)

**Threat Model:** Designed to resist passive RF monitoring, active eavesdropping, and endpoint compromise with limited forensic recovery.

---

## Development & Contributing

This is a **closed-source tactical project**. Contributions are by invitation only. For security vulnerabilities, contact the team directly rather than opening public issues.

---

## License

Ghost Net v1.0 – Proprietary Defense Technology. Unauthorized distribution or modification is prohibited.

---

## Deployment Status

| Component | Status | Version |
|---|---|---|
| Core Mesh | ✓ Production | 1.0 |
| E2EE Encryption | ✓ Production | 1.0 |
| PTT Audio | ✓ Production | 1.0 |
| Tactical Maps | ✓ Production | 1.0 |
| Mission Telemetry | ✓ Production | 1.0 |
| Duress Mechanisms | ✓ Production | 1.0 |
| Fleet Deployment | ✓ Production | 1.0 |
| GitHub Actions CI/CD | ✓ Active | — |

Built with Kivy, Python 3.8+, and cryptographic libraries (cryptography.io).
