# Gost-Net Security Architecture & Threat Model

**Status:** Ready for External Review  
**Specification Version:** 1.0.0  
**Notice:** This software utilizes standard cryptographic primitives implemented via the Python `cryptography` library. It has not received formal third-party commercial verification or certification. Security properties described herein represent engineering specifications and implementation guarantees, not formal proofs.

---

## 1. System Threat Model

### Adversary Capabilities Considered
1. **Passive LAN Observer:** Can capture all broadcast UDP discovery packets and unencrypted TCP traffic on the local ad-hoc network.
2. **Active LAN Adversary:** Can inject forged UDP discovery beacons, replay old messages, alter transit packets, or attempt to connect to arbitrary open TCP ports.
3. **Malicious Peer:** An authorized peer who participates in the network but attempts to transmit path-traversal file paths, malformed JSON, or oversized payloads to crash other nodes.
4. **Physical Device Seizure:** An adversary gains physical possession of a powered-off or locked device and inspects flash memory (SQLite database files, key files).
5. **Coerced Unlock:** An operator is compelled under duress to unlock the device.

### Non-Goals & Out of Scope
1. **Hardware-level Side-Channel Attacks:** DPA (differential power analysis) or EM radiation analysis on physical host silicon.
2. **Kernel/OS Compromise:** Rootkits, malicious OS modifications, or memory inspection via debugging tools on a compromised operating system.
3. **Physical RF Triangulation:** Gost-Net cannot prevent RF physical direction-finding by adversaries monitoring 2.4 GHz / 5 GHz electromagnetic emissions.
4. **Physical Flash Memory Wear-Leveling:** Flash controllers may leave remnant physical bits outside the logical file system after file deletion.

---

## 2. Identity and Trust Model

### Long-Term Identity
- Each node generates an **Ed25519 signing keypair** upon initial setup.
- The node ID is defined as the first 16 hexadecimal characters of `SHA-256(Callsign)`.
- The Ed25519 public key is serialized as 32 raw bytes (or standard Base64 representation in JSON headers).
- Changing an operator callsign updates the local display name but **does not** silently regenerate the cryptographic identity keypair.

### Trust on First Use (TOFU)
- When a peer is first encountered via UDP discovery or direct connection, their Ed25519 public key is stored locally in the peer table and marked `is_verified = 0` (`[TOFU]`).
- Out-of-band identity verification is performed by comparing a 12-digit numeric safety number formatted as `XXXX-XXXX-XXXX` derived from `SHA-256(min(key_A, key_B) || max(key_A, key_B))`.
- Upon successful out-of-band verification, the record is updated to `is_verified = 1`.

### Key Replacement Defense
- If a peer broadcasts or initiates a session with a public key that differs from the stored public key associated with that peer's identity, the network engine sets the peer state to `KEY_CHANGED`.
- Outbound messages to this peer are halted.
- The user is alerted with the previous fingerprint and the new candidate fingerprint.
- The stored key is never replaced without explicit, deliberate operator confirmation.

---

## 3. Cryptographic Primitives & Parameters

| Operation | Primitive / Standard | Parameters / Key Sizes |
|---|---|---|
| **Identity Signatures** | Ed25519 (PureEdDSA) | 256-bit elliptic curve over Curve25519 |
| **Ephemeral Key Exchange** | ECDH over NIST curve | SECP384R1 (384-bit prime field) |
| **Key Derivation Function** | HKDF (RFC 5869) | SHA-256 hash, info strings per context |
| **Symmetric Encryption** | AES-256-GCM | 256-bit key, 96-bit random nonce, 128-bit auth tag |
| **Storage Encryption** | Fernet (cryptography) | AES-128-CBC + HMAC-SHA256 authenticated envelope |
| **PIN Key Derivation** | PBKDF2-HMAC-SHA256 | 16-byte random salt, 200,000 rounds (v2), 32-byte KEK (*MOBILE PERFORMANCE NOT YET MEASURED*) |
| **Integrity Hashing** | SHA-256 | 256-bit digest |

---

## 4. Key Storage at Rest

1. **Database Key:** A 32-byte random key generated via `Fernet.generate_key()`. It is encrypted using the derived KEK (AES-128-CBC + HMAC-SHA256) and saved as `secret.key.enc` with permissions `0600`.
2. **Signing Private Key:** The raw 32-byte Ed25519 private seed is encrypted with the derived KEK and saved as `signing.key.enc` with permissions `0600`.
3. **Database Salt:** A 16-byte random salt stored in `.db_salt`.
4. **PIN Hashes:** Stored in `.auth_secrets` as `salt (16B) || master_hash (32B) || duress_hash (32B)`.

---

## 5. Session Ratchet Architecture

For point-to-point sessions, Gost-Net implements a Double Ratchet mechanism:
1. **Root Key ($RK$):** Initialized from the ECDH shared secret derived via SECP384R1 and HKDF-SHA256.
2. **Sending & Receiving Chains:** Two symmetric chains producing ephemeral message keys ($CK_{send}$, $CK_{recv}$).
3. **Diffie-Hellman Ratchet:** Periodically advances when new ephemeral public keys are exchanged, providing backward secrecy (compromise of current keys does not expose past sessions) and forward secrecy (future messages re-establish security).

---

## 6. Authentication and Integrity Coverage

- **Outbound Frames:** Every outbound frame header contains:
  - `sender_peer_id`: Originating node identity.
  - `timestamp`: Monotonic POSIX timestamp.
  - `msg_id`: Cryptographically random message UUID.
  - `signature`: Ed25519 signature computed over `msg_id || timestamp || payload_hash`.
- **Inbound Verification:** Incoming packets with missing or invalid Ed25519 signatures are rejected at the transport boundary before parsing.

---

## 7. Replay Protection & Deduplication

1. **Sliding Window Cache:** Each node maintains a bounded set of the last 2,000 processed `msg_id`s in memory.
2. **Replay Rejection:** If an incoming message contains an already-seen `msg_id`, an ACK is immediately returned (to terminate the sender's retry loop), but the payload is discarded without decryption or persistence.
3. **Timestamp Window:** Messages with timestamps deviating by more than 300 seconds from the local clock (adjusted for mesh clock skew) are flagged.

---

## 8. Data Deletion and Emergency Duress Protocol

### Logical Deletion
- When messages or keys are deleted, Gost-Net performs a logical multi-pass zeroization on the file before calling `os.remove()`.
- **Limitation Notice:** Due to hardware wear-leveling on modern SSDs, eMMC, and UFS flash, operating systems cannot guarantee physical block overwrite. The UI explicitly discloses this reality.

### Duress Protocol Execution
Upon entering the configured Duress PIN:
1. In-memory session keys and ephemeral keys are immediately overwritten with zeroes via `mlock`/`ctypes` zeroization.
2. Local key files (`secret.key.enc`, `signing.key.enc`, `.auth_secrets`, `.db_salt`) are logically overwritten and unlinked.
3. Decoy Mode is activated, populating a clean SQLite database with synthetic contacts and benign messages.
4. Outward application behavior appears completely normal.
