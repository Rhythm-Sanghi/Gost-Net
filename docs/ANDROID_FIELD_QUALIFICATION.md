# Gost-Net Android Physical Hardware Qualification Protocol

**Document Version:** 1.0.0  
**Target Release:** v1.0.0-rc1 -> v1.0.0 Gate  
**Scope:** Two-Device Physical Android Verification Protocol  
**Date:** 2026-10-02  

---

## 1. Objective & Authority

This document defines the strict physical hardware validation protocol required to qualify **Gost-Net** for general distribution. While the automated test suite validates cryptographic primitives, routing algorithms, serialization, and multi-process IPC on desktop operating systems, **physical RF characteristics, Android permission models, Linux kernel wakelocks, and OEM background execution killers can only be qualified on actual mobile devices**.

No release candidate may be promoted to `v1.0.0` until all tests in this protocol are executed on two real Android devices and signed off.

---

## 2. Equipment & Pre-Flight Configuration

### 2.1 Hardware Requirements
- **Device A (DUT 1):** Android smartphone running Android 13+ (Target API 33–36), arm64-v8a.
- **Device B (DUT 2):** Android smartphone running Android 10+ (API 29–34), arm64-v8a.
- **Test Workstation:** PC with Android Debug Bridge (`adb`) installed.
- **RF Test Environment:**
  - Air-gapped Wi-Fi Access Point (NO internet uplink).
  - Mobile Wi-Fi Hotspot mode (Device A hosting hotspot without cellular data).
  - Clean 2.4 GHz & 5 GHz RF environment for Bluetooth and Wi-Fi Direct tests.

### 2.2 Pre-Flight Installation Checklist
1. Connect Device A via USB:
   ```bash
   adb -s <DEVICE_A_SERIAL> install -r bin/GostNet-1.0.0-arm64-v8a-debug.apk
   ```
2. Connect Device B via USB:
   ```bash
   adb -s <DEVICE_B_SERIAL> install -r bin/GostNet-1.0.0-arm64-v8a-debug.apk
   ```
3. Verify App Sandbox Storage:
   ```bash
   adb -s <DEVICE_A_SERIAL> shell "run-as org.gostnet.ghostnet ls -la /data/data/org.gostnet.ghostnet/files"
   ```
4. Verify Battery Optimization Exemption:
   - Ensure the application prompts for or is configured with "Unrestricted Battery" under Android App Info -> Battery.

---

## 3. Test Cases & Execution Protocols

### TC-01: First Run, PIN Setup & Safety Number Verification
- **Purpose:** Validate secure onboarding, KDF v2 derivation, and determinism of out-of-band safety numbers.
- **Procedure:**
  1. Launch Gost-Net on Device A and Device B.
  2. Set Master PIN `849102` on Device A and `951753` on Device B.
  3. Ensure Duress PIN is configured with a distinct value.
  4. Note the displayed 12-digit Safety Number and SHA-256 fingerprint on both devices.
  5. Compare the safety numbers via out-of-band inspection.
- **Expected Outcome:**
  - Database is initialized with encrypted SQLite at rest.
  - PBKDF2-HMAC-SHA256 derivation completes smoothly (*measure latency on device*).
  - Safety numbers match symmetrically.

### TC-02: Local Wi-Fi Discovery & Encrypted Text Messaging
- **Purpose:** Validate UDP LAN discovery (Port 37020) and point-to-point encrypted TCP frames (Port 37021).
- **Procedure:**
  1. Connect Device A and Device B to the air-gapped Wi-Fi AP.
  2. Open Radar/Peers screen on both devices.
  3. Verify Device B appears in Device A's peer list within 5 seconds.
  4. Send text message `"Tactical check 01"` from Device A to Device B.
  5. Observe delivery status indicator and application-layer ACK.
- **Expected Outcome:**
  - Beacon is received and parsed without JSON errors.
  - TCP handshake completes and Double Ratchet session ratchets forward.
  - Double checkmark (ACK) appears within 500ms.

### TC-03: Resumable File Transfer with Physical Interruption
- **Purpose:** Validate 64KB chunking, `.part` staging, and SHA-256 integrity under network failure.
- **Procedure:**
  1. Select a 10MB test file on Device A and initiate transfer to Device B.
  2. At ~50% transfer progress, toggle Airplane Mode ON on Device B.
  3. Observe transfer suspension on Device A.
  4. Toggle Airplane Mode OFF on Device B and reconnect to Wi-Fi.
  5. Observe transfer resumption from the last verified chunk.
- **Expected Outcome:**
  - Device B retains existing `.part` chunks.
  - Transfer resumes automatically without re-transmitting from 0%.
  - Final SHA-256 hash matches the source file exactly.

### TC-04: Delay-Tolerant Networking (DTN) Epidemic Spooling
- **Purpose:** Validate store-and-forward spooling across disconnected partitions.
- **Procedure:**
  1. Disconnect Device B completely from the network.
  2. Device A sends message `"Store and forward test"` addressed to Device B.
  3. Observe message state on Device A is spooled (`[Spool] Message queued for peer`).
  4. Reconnect Device B to the network.
  5. Device A initiates beaconing and flushes the spool queue upon detecting Device B.
- **Expected Outcome:**
  - Message delivered to Device B as soon as connectivity resumes.
  - Spool file deleted from Device A's storage.

### TC-05: Push-to-Talk / Voice Note Recording & Playback
- **Purpose:** Validate hardware microphone access (RECORD_AUDIO), WAVE container formatting, and audio playback.
- **Procedure:**
  1. Press and hold Record Voice Note button on Device A.
  2. Speak for 5 seconds; release button to send.
  3. Verify message is delivered to Device B as an encrypted audio attachment.
  4. Press Play on Device B.
- **Expected Outcome:**
  - Audio plays clearly at 8 kHz mono without distortion or buffer underrun.
  - No temporary audio files left unencrypted in shared external storage.

### TC-06: Tactical Map & Waypoint Sharing
- **Purpose:** Validate offline raster/vector tile rendering and Cursor-on-Target (CoT) XML / GeoJSON data exchange.
- **Procedure:**
  1. Open Tactical Map screen on Device A.
  2. Verify offline MBTiles render correctly without internet access.
  3. Place a tactical Waypoint with label `"Checkpoint Alpha"`.
  4. Share waypoint with Device B.
- **Expected Outcome:**
  - Waypoint renders accurately on Device B's map.
  - CoT XML conforms to standard 2.0 schema.

### TC-07: Android Bluetooth RFCOMM Direct Transport
- **Purpose:** Validate off-grid Bluetooth transport when Wi-Fi is disabled.
- **Procedure:**
  1. Turn off Wi-Fi on both Device A and Device B; enable Bluetooth.
  2. Pair Device A and Device B via Android system Bluetooth settings.
  3. Select Bluetooth RFCOMM transport in Gost-Net settings.
  4. Send text message from Device A to Device B.
- **Expected Outcome:**
  - RFCOMM SPP socket connects over standard Gost-Net UUID.
  - Encrypted message frames transmit and ACK successfully over Bluetooth.

### TC-08: Android Wi-Fi Direct (P2P) Direct Link
- **Purpose:** Validate infrastructure-less Wi-Fi Direct peer discovery and group negotiation.
- **Procedure:**
  1. Disconnect both devices from any Wi-Fi AP.
  2. Enable Wi-Fi Direct mode in Gost-Net on both devices.
  3. Trigger discovery: Device A invites Device B.
  4. Accept invitation on Device B.
  5. Send text message across the established P2P group network.
- **Expected Outcome:**
  - Group Owner (GO) and Client roles negotiated automatically.
  - DHCP IP assigned; TCP messaging functions over the Wi-Fi P2P subnet.

### TC-09: Anti-Tamper Decoy Flip & Duress PIN Audit
- **Purpose:** Validate physical device defense against forced unlock and brute-force inspection.
- **Procedure:**
  1. Lock Gost-Net on Device A.
  2. Enter invalid PIN 5 consecutive times.
  3. Verify app automatically flips to Decoy Mode without crashing.
  4. Inspect database: verify master messages are hidden.
  5. Unlock using Duress PIN: verify immediate cryptographic key zeroization in RAM and decoy vault presentation.
- **Expected Outcome:**
  - Zero plaintext master keys in memory or SQLite storage.
  - Decoy vault displays convincing synthetic/empty conversation history.

---

## 4. Diagnostics & Log Collection

To capture real-time diagnostic telemetry during field tests:
```bash
# Filter python logs
adb -s <DEVICE_SERIAL> logcat -s python:D *:S

# Dump Gost-Net diagnostic database
adb -s <DEVICE_SERIAL> shell "run-as org.gostnet.ghostnet cat files/ghostnet_persistence.db" > dump_device.db
```

---

## 5. Qualification Sign-Off Sheet

| Test Case | Device A Model & OS | Device B Model & OS | Result (PASS/FAIL) | Engineer Signature | Date |
|---|---|---|---|---|---|
| TC-01 (Safety Numbers) | | | | | |
| TC-02 (Wi-Fi P2P Messaging) | | | | | |
| TC-03 (Resumable File Transfer) | | | | | |
| TC-04 (DTN Spooling) | | | | | |
| TC-05 (Voice Notes) | | | | | |
| TC-06 (Tactical Map) | | | | | |
| TC-07 (Bluetooth RFCOMM) | | | | | |
| TC-08 (Wi-Fi Direct) | | | | | |
| TC-09 (Duress & Anti-Tamper) | | | | | |
