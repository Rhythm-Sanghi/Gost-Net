# Gost-Net Cryptographic Specification for External Review

**Document Purpose:** Independent Technical Cryptographic Review  
**Application:** Gost-Net v1.0.0  
**Library Dependency:** `cryptography >= 41.0.0` (hazmat layer)  

---

## 1. Cryptographic Primitive Selection Rationale

### 1.1 Digital Signatures (Ed25519)
- **Standard:** RFC 8032 (Ed25519)
- **Rationale:** High signature generation speed, small key sizes (32 bytes public, 64 bytes signature), immune to side-channel timing attacks on software multiplication, and absence of fragile random nonce generation during signing (deterministic EdDSA).
- **Usage:** Long-term node identity signing of discovery beacons, message headers, revocation tokens, and custody receipts.

### 1.2 Asymmetric Key Agreement (SECP384R1 ECDH)
- **Standard:** NIST SP 800-56A Rev. 3 / FIPS 186-4
- **Rationale:** 192-bit security level providing strong margin against cryptanalytic advancement. Standard curve support in Python's cryptography hazmat primitives.
- **Usage:** Point-to-point session secret negotiation prior to Double Ratchet initialization.

### 1.3 Symmetric Key Encapsulation & Message Encryption (AES-256-GCM)
- **Standard:** NIST SP 800-38D
- **Rationale:** Authenticated Encryption with Associated Data (AEAD). Provides confidentiality and integrity verification in a single pass.
- **Parameters:**
  - Key size: 256 bits (32 bytes)
  - Nonce size: 96 bits (12 bytes), generated via `os.urandom()` per frame
  - Tag size: 128 bits (16 bytes)
  - Associated Data ($AD$): Serialized frame metadata (`sender_id || recipient_id || msg_id || timestamp`)

---

## 2. Key Derivation Hierarchy

```
                          [User Master PIN]
                                  │
                   PBKDF2-HMAC-SHA256 (200k rounds, salt - v2)
                   [Note: MOBILE PERFORMANCE NOT YET MEASURED]
                                  │
                                  ▼
                     Key Encryption Key (KEK, 32B)
                      │                         │
     Fernet.decrypt(secret.key.enc)    Fernet.decrypt(signing.key.enc)
                      │                         │
                      ▼                         ▼
            Database Key (32B)         Ed25519 Private Key (32B)
```

```
     [Node A Ephemeral Priv]               [Node B Ephemeral Pub]
                 │                                   │
                 └───────────────┬───────────────────┘
                                 │
                            ECDH.exchange()
                                 │
                                 ▼
                         Shared Secret (48B)
                                 │
                     HKDF-SHA256(salt=b'ghostnet_aes_key')
                                 │
                                 ▼
                     Session Root Key ($RK$, 32B)
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
         Sending Chain Key ($CK_s$)    Receiving Chain Key ($CK_r$)
```

---

## 3. Double Ratchet Implementation Transitions

### 3.1 Symmetric-Key Ratchet
For each message sent or received:
$$\text{Message Key } MK = \text{HMAC-SHA256}(CK, \text{b"\x01"})$$
$$\text{Next Chain Key } CK' = \text{HMAC-SHA256}(CK, \text{b"\x02"})$$
- The message key $MK$ is zeroized immediately after encrypting or decrypting the single message payload.
- Previous chain keys cannot be derived from subsequent chain keys (one-way property of HMAC).

### 3.2 Diffie-Hellman Ratchet
When a new ephemeral public key is received from the peer:
$$RK', CK_r = \text{HKDF}(RK, \text{ECDH}(DH_{local}, DH_{remote}))$$
$$DH_{local}' = \text{GenerateNewKeyPair}()$$
$$RK'', CK_s = \text{HKDF}(RK', \text{ECDH}(DH_{local}', DH_{remote}))$$

---

## 4. Nonce Handling & Collision Mitigation

- AES-256-GCM nonces are strictly 12 bytes generated via CSPRNG `os.urandom(12)`.
- For $N$ messages encrypted under a single ephemeral message key, $N = 1$ (each message key is single-use under the ratchet).
- Therefore, catastrophic AES-GCM nonce reuse under the same key is prevented by design.

---

## 5. Areas Requesting Focused Independent Audit

1. **Ratchet Deserialization Boundary:** Validation of state transitions during out-of-order bundle arrival in DTN store-and-forward mode (`src/security.py`).
2. **Key Erasure / Zeroization Consistency:** Evaluation of Python garbage collection and runtime memory management guarantees when zeroizing bytearrays (`src/security.py:zeroize_ephemeral_keys`).
3. **Decoy Mode Storage Separation:** Verification of SQLite handle isolation between legitimate database and decoy database upon duress trigger (`src/auth_manager.py`).
