# Gost-Net Capability & Verification Matrix

**Version:** 1.0.0  
**Verification Date:** 2026-10-02  
**Validation Classification System:**
- **REAL DEVICE VERIFIED:** Executed on actual physical target hardware.
- **REAL DESKTOP PROCESS VERIFIED:** Executed using genuine application processes, real sockets, and SQLite database storage.
- **SIMULATED:** Executed using intentionally simulated environment behavior.
- **MOCKED:** Executed against mock adapters or components.
- **STATIC CODE INSPECTION:** Confirmed via static source code analysis.
- **NOT VERIFIED:** Not executed or verified on physical hardware.

---

## 1. Core Capability Support & Evidence Matrix

| Capability | Desktop Status | Android Status | Physical Hardware Verified | Notes |
|---|---|---|---|---|
| **UDP LAN Discovery** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Port 37020, adaptive 2s–30s beaconing |
| **Point-to-Point TCP Messaging** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Dynamic TCP port binding, encrypted |
| **Application-Layer ACKs** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Confirmed recipient application processing |
| **Message Deduplication** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | 2,000 message sliding window cache |
| **Resumable File Transfer** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Chunked `.part` files + SHA-256 integrity |
| **Path Traversal Protection** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Sanitizes filenames via `os.path.basename` |
| **Encryption at Rest** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | SQLite content encrypted with Fernet |
| **In-RAM Ephemeral Mode** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | 0 rows written to SQLite database |
| **Message Expiry (TTL)** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Periodic background sweep purges expired |
| **Master PIN Authentication** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | PBKDF2-HMAC-SHA256 (200k rounds v2); mobile timing unmeasured |
| **Anti-Tamper Decoy Flip** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Flips to decoy vault on 5 failed PIN attempts |
| **Duress Mode Key Purge** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Zeros memory keys, switches to decoy vault |
| **Dead Man's Switch** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Auto-wipes credentials upon timeout |
| **Out-of-Band Safety Number** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | 12-digit numeric code + SHA-256 fingerprint |
| **Identity Key Change Warning** | REAL DESKTOP PROCESS VERIFIED | REAL DESKTOP PROCESS VERIFIED | SIMULATED | Halts transmission on key mismatch |
| **Voice Notes (RIFF/WAVE)** | SIMULATED | SIMULATED | NOT VERIFIED | 8 kHz mono recording & local playback |
| **Offline MBTiles Maps** | STATIC CODE INSPECTION | STATIC CODE INSPECTION | NOT VERIFIED | Local raster tile sets; zero internet leaks |
| **Bluetooth RFCOMM** | MOCKED | IMPLEMENTED | NOT VERIFIED | Requires physical Android devices |
| **Wi-Fi Direct P2P** | MOCKED | IMPLEMENTED | NOT VERIFIED | Requires physical Android devices |
| **Foreground Service (Android)** | NOT APPLICABLE | IMPLEMENTED | NOT VERIFIED | Requires physical Android device testing |
| **System Notifications** | MOCKED | IMPLEMENTED | NOT VERIFIED | Requires physical Android device testing |
| **GPS Location Tracking** | MOCKED | IMPLEMENTED | NOT VERIFIED | Requires physical GPS hardware |
| **Audio Steganography** | SIMULATED | SIMULATED | NOT VERIFIED | Advanced/experimental utility |
| **Acoustic Handshake** | SIMULATED | SIMULATED | NOT VERIFIED | Advanced/experimental utility |

---

## 2. Platform Summary

### Desktop (Windows, Linux, macOS)
- **Primary Transport:** Local Area Network (Wi-Fi or Ethernet) via UDP discovery (37020) and TCP messaging (37021 / dynamic).
- **Storage:** Local user data directory with encrypted SQLite database.
- **UI:** Responsive KivyMD interface supporting keyboard shortcuts, window resizing, and mouse input.

### Android (API 33+, arm64-v8a)
- **Primary Transport:** Local Wi-Fi network, with implemented Android Bluetooth RFCOMM and Wi-Fi Direct adapters.
- **Storage:** App-private storage (`~/.ghostnet`).
- **UI:** Responsive touch interface with `adjustResize` soft-keyboard handling.
