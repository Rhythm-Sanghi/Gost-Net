# Gost-Net Operator Guide

**Version:** 1.0.0  
**Target:** Desktop & Android Offline Operation  

---

## 1. First-Run Setup

When Gost-Net is launched for the first time on a device, the setup screen guides you through initial credential creation:

1. **Callsign:** Enter your chosen display name (e.g., `NodeAlpha`, `FieldOperator`). This is how other nearby peers will identify your node in discovery lists.
2. **Master PIN:** Enter a secure PIN of at least 4 characters. This PIN encrypts your local database key and cryptographic identity keypair using PBKDF2-HMAC-SHA256 (200,000 iterations in v2; *mobile performance not yet measured*).
3. **Confirm Master PIN:** Re-enter the identical PIN to verify.
4. **(Optional) Duress PIN:** Enter an emergency duress PIN.
   - *Behavior:* If coerced into unlocking the device, entering the Duress PIN immediately activates Decoy Mode, zeroes operational in-memory keys, and displays a decoy environment with mock peer data.
   - *Important:* Never set the Duress PIN to match your Master PIN.
5. Tap **Create Account** to initialize the encrypted local vault and proceed.

---

## 2. Unlocking the Application

On subsequent launches, Gost-Net displays the lock screen:

1. Enter your **Master PIN**.
2. Tap **Unlock** (or press Enter on desktop).
3. Gost-Net derives the Key Encryption Key (KEK), decrypts your database key (`secret.key.enc`), loads your Ed25519 signing key (`signing.key.enc`), mounts the local SQLite database, and transitions to the nearby devices screen.

> [!WARNING]
> **Anti-Tamper Lockout:** 5 consecutive incorrect PIN attempts will automatically switch the device into Decoy Mode. Entering the authentic Master PIN recovers from Decoy Mode without data loss.

---

## 3. Nearby Devices (Radar View)

Upon unlocking, Gost-Net listens for local peers:

- **Local Discovery:** Gost-Net broadcasts and listens for UDP discovery beacons on port `37020` across your local Wi-Fi or ad-hoc network.
- **Adaptive Beaconing:** Discovery beacons automatically back off from 2-second intervals to 30-second intervals when the local environment is stable, conserving battery and network bandwidth.
- **Peer List:** Detected peers appear in the list with their callsign, peer ID, transport type (LAN UDP/TCP, Bluetooth, or Wi-Fi Direct), and connection state.
- **Opening a Conversation:** Tap on any discovered peer to open a direct chat session.

---

## 4. Identity Verification & Safety Numbers

Gost-Net operates on a **Trust On First Use (TOFU)** model:

1. **Unverified Status:** When a peer is first discovered, their cryptographic identity is marked as `Unverified` / `[TOFU]`.
2. **Safety Number Comparison:**
   - Tap the peer's name in the Chat header or view peer details.
   - A 12-digit safety number (`XXXX-XXXX-XXXX`) and full SHA-256 fingerprint will be displayed.
   - Compare this numeric code out-of-band (e.g., in person, via secure voice, or another verified channel) with the other operator.
   - If the numbers match exactly, tap **Verify Identity**.
3. **Identity Key Change Warning:**
   - If a peer's identity key changes (e.g., peer reinstalled the app or an attacker is spoofing their callsign), Gost-Net will display an **Identity Key Changed** warning.
   - Gost-Net **will never silently overwrite** an existing identity key. Verify the new key out-of-band before updating trust.

---

## 5. Messaging

- **Sending Messages:** Type your message in the text composer at the bottom of the chat window and press **Send** (or press `Enter` on desktop; `Shift+Enter` for newline).
- **Delivery Lifecycle States:**
  - `Queued`: Message is buffered locally awaiting socket connection.
  - `Sending...`: Active socket transmission in progress.
  - `Sent to peer`: Socket write completed and flushed to the network.
  - `Delivered`: The recipient device returned an application-layer ACK confirming processing.
  - `Failed`: Transmission timed out or connection was dropped. Tap the retry icon to retransmit.
- **Duplicate Suppression:** Gost-Net deduplicates messages by unique message ID. Retried messages will never be duplicated on the recipient's screen.

---

## 6. Attachments & File Transfer

1. Tap the attachment icon (clip) in the chat composer.
2. Select a file using the file chooser.
3. The attachment will be **staged visibly** in the composer showing the filename and size.
4. Tap **Send** to initiate the transfer.
5. **Transfer Engine:** Files are transferred in encrypted chunks with SHA-256 integrity verification. Incomplete transfers are saved as `.part` files and automatically support offset resumption if the connection drops.
6. Received files are saved securely under your app's `downloads` directory.

---

## 7. Voice Notes

1. Press and hold (or tap) the microphone button in the chat screen.
2. Speak clearly into the microphone. Voice notes are recorded in 8 kHz mono RIFF/WAVE format for intelligible, low-bandwidth transmission.
3. Tap **Stop** to review or send.
4. Voice notes play directly in the chat view with duration indicators and scrub controls.

---

## 8. Ephemeral Mode & Message Expiry (TTL)

- **Message Expiration (TTL):** In Chat Settings or via the TTL selector, configure message lifetimes:
  - `Off` (persists until manually deleted)
  - `30 seconds`
  - `5 minutes`
  - `1 hour`
  - `24 hours`
  Expired messages are automatically scrubbed from local storage during periodic maintenance sweeps.
- **Ephemeral (RAM-Only) Mode:** When enabled, messages exist only in working memory and are **never written to disk**. Exiting or locking the app discards all ephemeral messages immediately.

---

## 9. Offline Field Maps

1. Navigate to the **Map** tab from the bottom navigation bar.
2. Gost-Net renders maps exclusively from local offline raster MBTiles packages (`.mbtiles`).
3. **Zero Internet Leakage:** Gost-Net never queries external tile servers or internet map services.
4. **GPS Position:** Displays your device's current coordinates, speed, and heading. You can drop waypoints to share with nearby mesh peers.

---

## 10. Handling Network Interruptions

- If Wi-Fi or ad-hoc connections drop, Gost-Net transitions the connection state to `DEGRADED` or `RECONNECTING`.
- Unsent messages remain safely buffered in the local `Queued` state.
- Once connectivity is re-established, the network engine automatically resumes transmission and retries pending messages.

---

## 11. Security Warnings & Limitations

- **Flash Storage Realities:** When deleting data, Gost-Net performs logical overwriting and file deletion. However, modern flash memory (SSD, eMMC, UFS) uses wear-leveling controllers, meaning complete physical destruction cannot be guaranteed at the application layer.
- **Independent Cryptography:** The cryptographic architecture uses standard primitives (Ed25519, SECP384R1 ECDH, HKDF, AES-256-GCM), but has not undergone a formal third-party commercial security audit.
- **Radio Emission:** Any RF transmission (Wi-Fi, Bluetooth) can be detected by specialized radio-frequency monitoring equipment.

---

## 12. Diagnostics & Troubleshooting

1. Navigate to **Settings → Diagnostics**.
2. View real-time system metrics:
   - Network State and Local IP/Port
   - Active Peer Count
   - Persistent Queue Depth
   - Storage utilization
3. **Safe Export:** Diagnostic reports sanitize all keys, PINs, and message contents. Exported logs are completely safe to share for technical troubleshooting.
