# Gost-Net Capabilities Matrix (Release Candidate v1.0.0-rc1)

**Last Updated:** 2026-10-02  
**Verification Baseline:** Core Test Suite (104/104 Passing), AST Clean Isolation Scan, Multi-Process Desktop Verification.  
**Classification Standard:**
- **IMPLEMENTED:** Complete production source code present in `src/`.
- **DESKTOP VERIFIED:** Multi-process functional test executed on real operating system sockets and encrypted SQLite storage.
- **SIMULATED:** Verified using mock sockets, memory loops, or headless simulated timing.
- **MOCKED:** Verified against mock platform wrappers (e.g. PyJNIus / Android API stubs).
- **PHYSICAL ANDROID VERIFIED:** Verified on physical Android hardware via ADB and RF interface.
- **NOT VERIFIED:** Not validated on real physical devices.

---

## 1. Subsystem Capability Matrix

| Feature / Capability | Implemented | Desktop Verified | Mobile Build Profile (Track A / B) | Physical Android Verified | Notes & Evidence |
|---|---|---|---|---|---|
| **Identity & Ed25519 Keys** | YES | YES | Included | SIMULATED | `tests/test_ghostnet.py::TestCryptoSubsystem` |
| **ECDH Shared Secret (X25519)** | YES | YES | Included | SIMULATED | `tests/test_ghostnet.py::TestCryptoSubsystem` |
| **Double Ratchet E2EE** | YES | YES | Included | SIMULATED | Forward secrecy & break-in recovery |
| **Out-of-Band Safety Numbers** | YES | YES | Included | SIMULATED | 12-digit numeric code + SHA-256 visual verification |
| **Master PIN & KDF v2** | YES | YES | Included | SIMULATED | PBKDF2-HMAC-SHA256 (200,000 iterations); *MOBILE PERFORMANCE NOT YET MEASURED* |
| **Duress PIN Protocol** | YES | YES | Included | SIMULATED | Instant zeroization, decoy vault activation |
| **Anti-Tamper Decoy Flip** | YES | YES | Included | SIMULATED | Automatic decoy mode on 5 consecutive invalid PIN attempts |
| **Dead Man's Switch** | YES | YES | Included | SIMULATED | Configurable local vault zeroization upon inactivity |
| **Encrypted SQLite at Rest** | YES | YES | Included | SIMULATED | Fernet KEK derived from PIN; 0 plaintext leaks |
| **In-RAM Ephemeral Mode** | YES | YES | Included | SIMULATED | Database writes suppressed; zero disk footprint |
| **Message TTL & Auto-Scrub** | YES | YES | Included | SIMULATED | Background sweep purges expired messages |
| **UDP LAN Peer Discovery** | YES | YES | Included | SIMULATED | Port 37020; adaptive 2s–30s beaconing |
| **Point-to-Point TCP Messaging** | YES | YES | Included | SIMULATED | Port 37021 / dynamic; encrypted frame transmission |
| **Application-Layer ACKs** | YES | YES | Included | SIMULATED | Positive delivery confirmation from recipient app |
| **Message Deduplication** | YES | YES | Included | SIMULATED | 2,000-message sliding window UUID cache |
| **Resumable File Transfer** | YES | YES | Included | SIMULATED | 64KB chunking, `.part` files, SHA-256 verification |
| **Path Traversal Protection** | YES | YES | Included | SIMULATED | Strict `os.path.basename` enforcement & folder sandboxing |
| **DTN Spooling & Relay** | YES | YES | Included | SIMULATED | Epidemic / store-and-forward bundle delivery across offline partitions |
| **Group Channels (Symmetric)** | YES | YES | Included | SIMULATED | Symmetric key derivation & multicast relay |
| **AODV Reactive Routing** | YES | YES | Included | SIMULATED | RREQ / RREP / RERR multi-hop path discovery |
| **Voice Notes (RIFF/WAVE)** | YES | SIMULATED | Included | NOT VERIFIED | Headless wav container creation; PyJNIus AudioRecord on mobile |
| **Offline Vector/Raster Maps** | YES | YES | Included | NOT VERIFIED | MBTiles raster tile parsing; zero external network requests |
| **Cursor-on-Target (CoT) XML** | YES | YES | Included | SIMULATED | ATAK / WinTAK interoperability format |
| **GeoJSON Spatial Import/Export** | YES | YES | Included | SIMULATED | Bounded geographic polygon / point features |
| **Android Bluetooth RFCOMM** | YES | MOCKED | Track A/B | NOT VERIFIED | Requires physical Android device pairing |
| **Android Wi-Fi Direct (P2P)** | YES | MOCKED | Track A/B | NOT VERIFIED | Requires physical Android device direct Wi-Fi |
| **Android Foreground Service** | YES | MOCKED | Track A/B | NOT VERIFIED | `service.py` background notification & wakelock |
| **Runtime Permission Manager** | YES | MOCKED | Track A/B | NOT VERIFIED | API 33+ granular runtime requests; `LOCAL_MAC_ADDRESS` removed |
| **Audio Steganography** | YES | SIMULATED | Excluded / Internal | NOT VERIFIED | Experimental LSB carrier embedding |
| **Acoustic Handshake** | YES | SIMULATED | Excluded / Internal | NOT VERIFIED | Ultrasonic / audible FSK modem |

---

## 2. Platform Distribution Profiles

### Profile Track A: Sideload / Direct Distribution
- **Target OS:** Android 5.0 (API 21) through Android 13 (API 33)
- **Artifact:** Universal APK (`.apk`)
- **NDK Toolchain:** NDK r25b
- **Permissions:** Sideload-optimized; no proprietary Google Play Services dependencies; internal app-private storage.

### Profile Track B: Google Play 2026 Target
- **Target OS:** Android 8.0 (API 26) through Android 16 (API 36)
- **Artifact:** Android App Bundle (`.aab`)
- **NDK Toolchain:** NDK r27b/r28 with 16 KB ELF page-alignment (`-Wl,-z,max-page-size=16384`)
- **Permissions:** Minimized; obsolete storage & privileged permissions removed; Scoped Storage compliant.

---

## 3. Physical Hardware Qualification Gate

Before promoting `v1.0.0-rc1` to final `v1.0.0`, all items marked **NOT VERIFIED** or **SIMULATED** must be executed against the standard test protocol defined in [ANDROID_FIELD_QUALIFICATION.md](file:///c:/Users/Test/Documents/Ghost%20net/docs/ANDROID_FIELD_QUALIFICATION.md).
