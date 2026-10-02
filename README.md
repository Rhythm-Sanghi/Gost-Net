# Gost-Net: Offline Peer-to-Peer Messaging and DTN Mesh Utility

[![Tests](https://img.shields.io/badge/tests-294%20passing-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-Android%20%7C%20Desktop-lightgrey.svg)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)]()

**Gost-Net** is an offline-first peer-to-peer messaging and delay-tolerant networking (DTN) utility engineered for unreliable, off-grid communication environments. It enables local communication across Android and Desktop platforms without reliance on cellular infrastructure, centralized servers, or active internet connectivity.

Designed with the functional pragmatism of field instruments and radio consoles, Gost-Net emphasizes deterministic state handling, delivery verifiability, and graceful degradation during network disruption.

---

## System Architecture

```
                       +---------------------------------------+
                       |           Field UI (KivyMD)           |
                       |  Lock / Radar / Chat / Map / Diagnostics
                       +-------------------+-------------------+
                                           |
                                +----------v----------+
                                |     GhostEngine     |
                                +----------+----------+
                                           |
         +------------------+--------------+-------------+--------------------+
         |                  |                            |                    |
+-------v-------+  +-------v--------+           +-------v--------+   +-------v--------+
| Cryptography  |  | Network Engine |           | DTN Spool      |   | Local Storage  |
| - ED25519 Sign|  | - State Machine|           | - Double Env   |   | - SQLite (WAL) |
| - Double      |  | - UDP Discovery|           | - Route Pruning|   | - At-Rest      |
|   Ratchet     |  | - Direct TCP   |           | - Store & Fwd  |   |   Encryption   |
| - ECDH 384    |  | - App-layer ACK|           | - TTL Cleanup  |   | - Logical      |
| - Safety Num  |  | - Multi-Hop Rel|           | - Metric Path  |   |   Overwrite    |
| - TOFU Store  |  | - Atomic .part |           | - Loop Prevent |   | - Custody Trans|
| - Key Zeroize |  | - Flow Resumpt |           | - CoT / GeoJSON|   | - Waypoints DB |
| - Revocation  |  | - Voice Audio  |           | - Ingress Drop |   | - Revoked DB   |
| - Channel Key |  | - AODV Routing |           | - Link Quality |   | - Group DB     |
| - Dead Man Sw |  | - Compact Frame|           | - Multicast Rel|   | - Decoy Vault  |
+---------------+  +----------------+           +----------------+   +----------------+
```

### 1. Networking, Transport & Resumption
- **Adaptive Discovery:** Dynamic UDP broadcast beacons with exponential backoff (2s up to 30s) when topology is static, minimizing battery draw and RF signature. Instant scan reset occurs upon peer activity or manual operator interaction.
- **State Machine:** Clear internal operational states (`OFFLINE`, `DISCOVERING`, `AVAILABLE`, `CONNECTING`, `SESSION_READY`, `DEGRADED`, `RECONNECTING`) surfaced cleanly in the UI.
- **Delivery Lifecycle:** Messages progress through deterministic stages:
  - `Queued` (persisted or pending dispatch)
  - `Sending...` (TCP transmission in progress)
  - `Sent to peer` (socket write completed)
  - `Delivered` (confirmed via application-layer ACK from recipient)
  - `Failed ↻` (transmission or handshake failed; one-tap idempotent retry)
- **Resumable Chunked Transfers & Flow Control:** Streamed file attachments utilize `.part` temporary files with byte-offset resumption. Pacing delay (`0.002s`) between chunks prevents buffer bloat and packet drops on congested ad-hoc links. Transfers are verified against SHA-256 integrity checksums before atomic promotion (`os.replace`).
- **Low-Bandwidth Voice Notes:** Audio messaging records into standard RIFF/WAVE 8kHz mono containers for maximum intelligibility at minimal payload sizes, with cross-platform playback monitoring and fallback simulation.

### 2. Situational Awareness & Geospatial Interoperability
- **Peer Location Sharing:** Real-time peer position telemetry broadcast with configurable accuracy, altitude (HAE), and timestamp indicators.
- **Tactical Waypoints:** Drop, share, and track tactical waypoints (rally points, hazards, supply caches, checkpoints, medical stations) with automated TTL expiration.
- **CoT 2.0 XML & RFC 7946 GeoJSON:** Full bidirectional export and import compatibility for external situational awareness suites such as ATAK, WinTAK, and QGIS. Coordinate boundary validation enforces strict geospatial bounds (`-90 <= lat <= 90`, `-180 <= lon <= 180`).

### 3. Delay-Tolerant Networking (DTN) & Multi-Hop Relay
- **Multi-Hop Mesh Forwarding:** Automatic routing across intermediate nodes ($A \to B \to C$) when direct radio links are obstructed, with custody transfer confirmation.
- **Anti-Loop Vector Tracking:** Headers track `visited_nodes` and decrement `network_ttl` on every hop to eliminate routing loops and packet storms.
- **Store-and-Forward Spooling:** When destination nodes are unreachable, encrypted message bundles are spooled locally in a persistent queue.
- **Dynamic Routing:** Route selection evaluates path hop counts and node battery levels, penalizing routing paths through nodes with battery below 20%.
- **TTL Expiry:** Ephemeral messages expire deterministically based on sender-assigned lifetimes (`30s`, `5m`, `1h`, `24h`) and are removed during background database maintenance sweeps.

### 4. Cryptographic Implementation, Revocation & OpSec
- **Session Ratchet:** Session key negotiation implements a Double Ratchet construction using SECP384R1 ECDH and HKDF key derivation with AES-256-GCM message encryption.
- **Digital Signatures:** ED25519 keypairs sign outbound payload headers to verify origin authenticity.
- **Cryptographic Revocation & Blacklisting:** Signed revocation broadcasts (`PEER_REVOCATION`) allow operators to digitally blacklist compromised nodes. Revoked peers are permanently blocked at the ingress transport boundary.
- **In-Memory Key Zeroization:** Rapid zeroization routine (`zeroize_ephemeral_keys`) overwrites private keys, derived AES keys, and shared secrets in memory with zeroes to mitigate physical memory inspection.
- **Out-of-Band Safety Numbers:** Operators can verify peer public keys via symmetric 12-digit safety numbers (`XXXX-XXXX-XXXX`) and SHA-256 fingerprints to eliminate Man-In-The-Middle (MITM) risks inherent in unauthenticated Trust-On-First-Use (TOFU).
- **TOFU Status Badges:** Peers display clear verification badges in Radar and Chat headers (`[TOFU]` unverified vs. `[Verified]` out-of-band).

### 5. Multi-Party Group Channels, AODV Routing & Hardware OpSec
- **Encrypted Group Channels:** Named tactical channels (e.g. `ALL_CALL`, `RECON_TEAM`) with symmetric keys derived via HKDF-SHA256 from shared passphrases. Intermediate mesh nodes forward multicast packets across the mesh without possessing decryption capability.
- **AODV Reactive Route Discovery:** On-demand Route Request (`RREQ`), Route Reply (`RREP`), and Route Error (`RERR`) protocol actively discovers multi-hop routes to unseen nodes and purges broken links.
- **Link Quality Estimation:** Exponential Moving Average (EMA) of Round-Trip Time (RTT) and Packet Delivery Ratio (PDR) weights route selection.
- **Ultra-Compact Binary Framing:** Low-overhead binary protocol (`GN` magic header, packed struct fields, and adaptive zlib compression saving 40–70% bandwidth on constrained links).
- **Anti-Tamper Lockout & Dead Man's Switch:** 5 failed PIN attempts trigger automatic Decoy Vault switch. Inactivity past configurable Dead Man's Switch timeout automatically triggers cryptographic purge and disk sanitization.

### 6. Cross-Bearer Gateway, Mesh Duty Cycling, Multi-Path & Remote Zeroize
- **Modular Multi-Bearer Gateway (`src/transport_bearer.py`):** Unified `TransportBearer` abstraction enabling Gost-Net to communicate across heterogeneous physical media (TCP/IP, Serial/UART LoRa transceivers like SX1262 / Meshtastic, Bluetooth RFCOMM).
- **Packet Segmentation & Reassembly (SAR):** Slices high-bandwidth payloads into MTU-bounded frames with 16-byte `FRAG` headers, reassembling packets upon receipt with CRC32 integrity verification and timeout purging.
- **Synchronized Slotted Mesh Duty Cycling (`src/duty_cycler.py`):** Coordinated sleep/wake scheduling (5s active window every 30s) aligned with mesh median clock convergence. Spools outbound transmissions during sleep cycles and flushes prioritized queues upon window rendezvous.
- **K=2 Disjoint Multi-Path Routing (`src/multipath_routing.py`):** Dispatches critical packets across 2 node-disjoint mesh paths simultaneously to defeat jamming and physical obstruction, with duplicate suppression at destination.
- **Per-Hop Cryptographic Onion Encapsulation:** Forwarded packets are wrapped in layered AES-256-GCM encryption, ensuring intermediate relay nodes only know previous and next hops, hiding true originators and endpoints.
- **Over-The-Air (OTA) Cryptographic Burn Token (`src/remote_wipe.py`):** Authorized commanders broadcast Ed25519-signed emergency burn tokens to remotely zeroize compromised nodes or repeaters, purging in-memory session keys and logically overwriting persistent SQLite databases.

### 7. Forward Error Correction, GeoCast, Covert Stego & Topology Telemetry
- **MDS Erasure Coding / Forward Error Correction (`src/fec_engine.py`):** Reed-Solomon style Cauchy erasure coding over $GF(2^8)$. Slices payloads into $K$ data blocks and generates $M$ parity blocks ($N = K + M$), allowing bit-exact payload recovery from any $K$ received blocks without round-trip retransmissions on high-loss RF channels.
- **Geofenced Geographic Mesh Casting (GeoCast) (`src/geocast.py`):** Spatial routing engine enforcing circular and polygonal GPS geofencing. Messages are displayed only when recipient devices reside physically inside the target operational zone; out-of-zone nodes act strictly as encrypted DTN mules.
- **Covert Audio Steganography & Dead-Drops (`src/stego_transport.py`):** Injects encrypted binary payloads into Least Significant Bits (LSB) of RIFF/WAVE PCM audio files with keyed pseudo-random sample dispersion to withstand statistical steganalysis and enable plausible deniability.
- **Real-Time Mesh Topology Graph & Health Telemetry (`src/mesh_topology.py`):** Live directed graph state analyzing network diameter, articulation point bridges (single points of failure), connected components, and link quality metrics (PDR/RTT). Exports topological state in standard JSON and Graphviz DOT formats for integration with ATAK, WinTAK, and QGIS.

### 8. Frequency Agility (FHSS), Zero-Knowledge Proximity, OTP Vault & EW Countermeasures
- **Synchronized Frequency Hopping (FHSS) (`src/frequency_agility.py`):** Pseudo-random channel agility keyed by shared mesh seed and epoch slot times across configurable sub-GHz channel plans (e.g. 915 MHz channels 0–15). Implements periodic static rendezvous slots and automatic dynamic blacklisting of chronically jammed channels.
- **Zero-Knowledge Proximity Verification (`src/proximity_crypto.py`):** Hierarchical Geohash spatial commitments with salted HMAC verification. Enables operators to cryptographically prove geographical co-location (e.g. within 150m, 600m, or 2.4km bounding cells) with **zero disclosure of absolute GPS coordinates**.
- **Ephemeral Pre-Shared One-Time Pad (OTP) Vault (`src/quantum_resilient.py`):** Information-theoretically secure keystream manager for strategic command and zeroization traffic. Enforces strictly monotonic offset progression, zero pad-reuse rejection, and immediate overwriting of consumed keystream segments on disk.
- **EW Jamming Detection & Autonomous Recovery (`src/anti_jamming.py`):** Monitors multi-neighbor link quality collapse and channel contention to distinguish deliberate RF jamming from natural distance attenuation. Autonomously shifts the network into defensive posture, upgrading FEC parity to maximum resilience ($K=2, M=4$) and rerouting priority traffic.

### 9. DTN Bundle Custody, Ephemeral Beacons, ATAK CoT Streaming & Merkle Vault
- **RFC-Aligned DTN Bundle Custody Transfer (`src/bundle_protocol.py`):** Priority-tiered DTN bundle queues (`EXPEDITED=0`, `STANDARD=1`, `BULK=2`) with explicit Custody Acceptance Signals (CAS). Ensures guaranteed custodial handoffs across intermittent multi-hop routes while preventing buffer exhaustion via TTL-bounded lifetime reclamation and lowest-priority unheld eviction.
- **Rotating Ephemeral Beacon Anonymization (`src/ephemeral_handshake.py`):** Eliminates static call signs and radio fingerprints in discovery beacons by generating rotating, time-windowed pseudo-random tokens via HMAC-SHA256 from a pre-shared group secret. Prevents SIGINT emitter correlation and RF tracking while allowing authenticated team members to de-anonymize friendly peers across clock-skew-tolerant epoch windows.
- **Real-Time ATAK / WinTAK Cursor-on-Target (CoT) Multicast Streaming (`src/tak_bridge.py`):** Bi-directional UDP streaming on standard ATAK multicast channel (`239.2.3.1:6969`) and unicast port `4242`. Translates Gost-Net peer positions and tactical waypoints to CoT 2.0 XML in real time, delivering seamless situational awareness integration with field tactical assault kits.
- **Tamper-Evident Merkle Audit Ledger & Cryptographic Hash Chain (`src/merkle_vault.py`):** Unbroken append-only cryptographic SHA-256 hash chains over mission-critical tactical actions (messages, waypoints, revocations, and zeroization events). Detects database tampering down to the exact corrupt record index and generates standalone cryptographic inclusion proofs for after-action reviews (AAR).

### 10. Cognitive Radio Spectrum Sensing, Swarm Consensus, DTN Pub/Sub & Sovereign Identity
- **Cognitive Radio Spectrum Sensing & Dynamic Energy Detection (`src/cognitive_radio.py`):** Radiometric energy detection over sampled power spectra with adaptive noise floor estimation, signal-to-noise ratio (SNR) calculation, and spectral flatness (Wiener entropy) metrics to distinguish wideband noise from narrowband interference and rank vacant sub-GHz channels.
- **Byzantine-Resilient Swarm Consensus Protocol (`src/swarm_consensus.py`):** Decentralized threshold BFT voting enabling autonomous edge squad decisions (detachment leader election, dynamic frequency plan migration, collective emergency zeroization) with cryptographic ballot verification, epoch fencing, and tolerance of up to $f < n/3$ faulty or disconnected nodes.
- **Disruption-Tolerant Content-Centric Pub/Sub & Bloom Filter Cache Synchronization (`src/dtn_pubsub.py`):** Topic-based pub/sub decoupled from host network addresses featuring wildcard pattern matching (`sitrep/*`, `intel/#`). Synchronizes caches during brief opportunistic radio encounters using compact Bloom filter set reconciliation to transmit only missing content items.
- **Sovereign Multi-Key Web-of-Trust (WoT) Keyring & (k, n) Threshold Cryptographic Quorum (`src/sovereign_identity.py`):** Decentralized PGP-style peer cross-certification keyring computing transitive confidence scores without centralized authorities. Pairs with a $(k, n)$ Shamir's Secret Sharing scheme over $GF(256)$ with primitive polynomial $0x11d$ for multi-operator emergency command authorization.

### 11. Autonomous Swarm Self-Healing, Covert Timing Camouflage, Tactical DHT & Spatial Privacy
- **Autonomous Mesh Partition Healing & Gateway Bridge Negotiation (`src/mesh_healing.py`):** Automatically detects split-brain partitioned network components using breadth-first cluster analysis. Autonomously elects and promotes fringe boundary nodes to gateway bridge mode with transmission power boosts to bridge isolated components and drain spooled DTN bundles upon contact.
- **Covert Traffic Camouflage & Inter-Arrival Timing Modulation (`src/traffic_camouflage.py`):** Defeats adversary electronic warfare (EW) traffic-flow analysis and radio emitter fingerprinting by shaping packet inter-arrival intervals via exponential Poisson processes and injecting indistinguishable dummy chaff frames when traffic is sparse.
- **Tactical Kademlia Distributed Hash Table (DHT) (`src/tactical_dht.py`):** Decentralized 160-bit XOR-metric ($d(x, y) = x \oplus y$) key-value resource routing with $k$-buckets and iterative lookups, enabling ad-hoc discovery of rendezvous points, emergency medical caches, and frequency plans without central infrastructure.
- **Geo-Indistinguishable Differential Privacy Spatial Obfuscation (`src/spatial_privacy.py`):** Applies planar polar Laplace perturbation noise to GPS coordinate streams, providing mathematically proven $(\epsilon)$-differential privacy for friendly force tracking to disguise sniper nests and command tents while preserving squad-level situational awareness.

### 12. Collaborative ECM, Random Linear Network Coding, Token-Bucket QoS & Zero-Knowledge Auth
- **Collaborative Electronic Countermeasures (ECM) & Jammer Triangulation (`src/collaborative_ecm.py`):** Coordinates distributed RF signal power observations across multiple nodes to calculate jammer positions via log-distance path-loss multilateration. Computes forward azimuth nulling vectors to guide directional antennas and time-slotted spatial nulling schedules.
- **Random Linear Network Coding (RLNC) over $GF(256)$ (`src/network_coding.py`):** Enables intermediate mesh relay nodes to synthesize random linear combinations of incoming generation packets on-the-fly, achieving theoretical max-flow min-cut multicast capacity across lossy ad-hoc links without retransmission overhead. Solved via incremental Gaussian elimination and back-substitution.
- **Dynamic Token-Bucket QoS & Tactical Bandwidth Shaper (`src/qos_shaper.py`):** Multi-tier rate-limiting scheduler enforcing strict priority queuing (`CRITICAL`, `TACTICAL`, `BULK`). Automatically suppresses background bulk transfers when link delivery ratios drop below $0.70$, guaranteeing zero contention and immediate transmission for emergency SOS alerts and situational awareness telemetry.
- **Zero-Knowledge Peer Authentication (Schnorr $\Sigma$-Protocol) (`src/zkp_auth.py`):** Non-interactive zero-knowledge proofs of discrete logarithm knowledge over RFC 3526 1536-bit MODP safe prime groups with Fiat-Shamir heuristics. Allows tactical operators to prove possession of authorization keys without disclosing private keys or transmitting linkable identity tokens.

### 13. Post-Quantum KEM, Homomorphic Aggregation, DSSS Spread Spectrum & Virtual Antenna Arrays
- **Lattice-Based Post-Quantum KEM (`src/post_quantum_kem.py`):** Ring Learning with Errors (Ring-LWE) key encapsulation mechanism over polynomial ring $\mathbb{Z}_q[x]/(x^N + 1)$ with $N=64, Q=3329$. Generates quantum-resistant public/private keypairs, encrypts ephemeral 32-byte session secrets with error perturbation, and decapsulates with negacyclic polynomial reduction. Combined with classical ECDH via dual-HKDF to provide hybrid security (safe if either classical or PQ primitive remains unbroken).
- **Additive Homomorphic Telemetry Aggregation (`src/homomorphic_aggregation.py`):** Additive Paillier cryptosystem enabling intermediate DTN mules and tactical repeaters to aggregate confidential swarm telemetry (ammunition levels, casualty counts, battery reserves) directly on ciphertexts ($c_1 \cdot c_2 \pmod{n^2} = \text{Enc}(m_1 + m_2 \pmod n)$) without decrypting individual operator reports or exposing node identities.
- **Direct Sequence Spread Spectrum (DSSS) LPI/LPD Modulation (`src/dsss_modulation.py`):** Low Probability of Interception / Low Probability of Detection (LPI/LPD) physical framing engine. Modulates tactical payloads across 31-chip bipolar Gold sequences generated by dual degree-5 LFSR preferred polynomials ($x^5 + x^2 + 1$ and $x^5 + x^4 + x^3 + x^2 + 1$). Matched-filter cross-correlation despreading enables payload recovery even below channel noise floor ($E_b/N_0$).
- **Distributed Virtual Antenna Array & Coordinated Beamforming (`src/virtual_array.py`):** Coordinates multi-node distributed beamforming across tactical squads. Calculates carrier phase shifts and microsecond time delays for each node based on spatial coordinates relative to target azimuth and elevation. Computes theoretical constructive power gain ($20\log_{10} N\,\text{dB}$) and array factor directivity to punch through adversary jamming or reach distant satellite relays.

### 14. Covert Timing Channel, Tactical RF Link Budget, Mesh Clock Sync & RF Signature Advisor
- **Inter-Packet Delay (IPD) Covert Timing Channel (`src/covert_channel.py`):** Encodes secret bit-streams into the statistical distribution of packet inter-arrival intervals (timing steganography). Each symbol maps to the centre of a quantised timing bucket spanning $[T_{min}, T_{max}]$ ms, providing symmetric $\pm\,(B_w/2)$ noise tolerance and achieving covert channel capacity of $\lfloor\log_2 N\rfloor \cdot (1000/\overline{T})$ bits/second. `KeyedTimingChannel` applies a Fisher-Yates bucket permutation derived from HMAC-SHA256 over a shared secret, defeating passive traffic analysts without the key.
- **Tactical RF Link Budget Calculator (`src/link_budget.py`):** Friis-based end-to-end link margin computation incorporating free-space path loss (FSPL), receiver thermal noise floor ($N = -174 + 10\log_{10} B + NF$), ITU-R P.838 rain attenuation ($\gamma_R = k R^\alpha$ dB/km), COST 235 foliage excess loss, and obstacle diffraction loss. Binary-searches maximum viable communication range (m) and outputs per-link BER estimates under BPSK modulation via Abramowitz & Stegun erfc approximation.
- **NTP-Free Distributed Mesh Clock Synchronisation (`src/mesh_time_sync.py`):** GPS-denied sub-millisecond clock alignment using Cristian's algorithm for per-exchange offset and RTT estimation (four-timestamp model: $T_1, T_2, T_3, T_4$) combined with Marzullo's fault-tolerant intersection algorithm across multiple peer sources. Tolerates up to $f < n/3$ Byzantine faulty clocks. Maintains rolling sample buffers and provides `adjusted_time()` for mesh-synchronised POSIX timestamps.
- **RF Emission Signature Minimisation Advisor (`src/rf_signature.py`):** Models a node's electromagnetic footprint by computing EIRP ($P_{tx} + G_{ant} - L_{cable}$), passive intercept range (Friis inversion against adversary MDS), and a duty-cycle-weighted emission threat score in $[0, 1]$. Issues scheduling recommendations — minimum transmit power, reduced duty cycle, and burst duration limits — to restrict coherent integration gain available to an adversary correlator. Ranks candidate operating frequencies by ascending intercept range for frequency selection guidance.

### 15. Adaptive Modulation & Coding (AMC), LKH Group Rekeying, Fuzzy Route Optimization & Anti-Replay
- **Adaptive Modulation & Coding (AMC) Link Adaptation (`src/adaptive_modulation.py`):** Dynamic physical/link-layer rate adaptation based on Channel State Information (CSI), Signal-to-Interference-plus-Noise Ratio (SINR / SNR), and packet error rate. Transitions across LoRa modes (SF12, SF10, SF7) and narrowband digital modulations (BPSK 1/2, BPSK 3/4, QPSK 1/2, QPSK 3/4, 16-QAM 1/2, 16-QAM 3/4, 64-QAM 2/3, 64-QAM 5/6). Enforces an upward hysteresis margin (1.5 dB) to prevent rapid ping-pong oscillation under channel fading, computes Shannon-Hartley channel capacity, and provides closed-loop Channel Quality Indicator (CQI) telemetry.
- **Logical Key Hierarchy (LKH) Scalable Squad Rekeying (`src/group_rekeying.py`):** Scalable group key management for dynamic tactical squads and detachments operating in hostile, off-grid environments. Maintains a balanced binary key tree where leaves represent individual squad members and the root holds the Group Session Key. Executes $O(\log_2 N)$ join and compromise eviction rekeying protocols, enforcing strict forward secrecy (evicted nodes cannot decipher future traffic) and backward secrecy (newly joined nodes cannot decipher past operational logs).
- **Multi-Criteria Fuzzy Logic / AHP Tactical Route Optimization (`src/fuzzy_routing.py`):** Advanced composite tactical route cost estimation combining non-linear physical parameters: residual battery level, RF signal strength (RSSI/SNR), Packet Delivery Ratio (PDR), latency/jitter (RTT), and hop count. Features triangular/trapezoidal fuzzy membership functions, Analytic Hierarchy Process (AHP) weight vectors with mission presets (`STANDARD`, `EMERGENCY`, `LOW_POWER`), battery starvation avoidance, link failure pruning, and Pareto-optimal multi-hop candidate path ranking.
- **Anti-Replay Sliding Window & Cryptographic Sequence Vector Engine (`src/anti_replay.py`):** High-performance, denial-of-service resilient anti-replay verification tailored for out-of-order, multi-path, delay-tolerant mesh packets (RFC 4303 / RFC 6479 aligned). Employs a configurable bitmask sliding window (default 128 bits) with per-peer epoch isolation to accept legitimate out-of-order arrivals while rejecting replays and aged packets.

### 16. Protocol Chaos Fuzzing, Unified Tactical HUD, Multi-Bearer Failover & In-Memory Panic Scrubbing
- **Protocol Chaos Fuzzing & Crash Immunity Engine (`src/chaos_fuzzer.py`):** Mutation-based fuzzing and fault injection across Gost-Net wire protocols. Applies 7 automated mutation strategies (bit flips, byte truncations, header overflows, malformed JSON, delimiter corruptions, integer wrap-arounds, and random garbage) to prove exception containment and zero-daemon-crash resilience under adversarial network inputs.
- **Unified Tactical HUD & Diagnostic Dashboard Controller (`src/tactical_hud.py`):** Centralized C4ISR situational awareness aggregator synthesizing physical-layer AMC constellations, link margins, EIRP threat scores, mesh graph topology metrics, LKH group key versions, jammer triangulation, sliding-window replay statistics, and Merkle audit ledgers into a cohesive operational state. Provides structured JSON telemetry and an ASCII terminal dashboard for field operators.
- **Multi-Bearer Autonomous Failover & Redundancy Controller (`src/bearer_failover.py`):** Coordinates heterogeneous physical network bearers (LAN TCP/IP, Wi-Fi Direct, Bluetooth RFCOMM, LoRa Serial/UART). Computes dynamic link health scores from heartbeats, latency, and delivery success, executing seamless autonomous failover and hysteresis recovery without dropping spooled DTN bundles.
- **In-Memory Multi-Pass Panic Zeroization & Memory Scrubber (`src/memory_scrubber.py`):** Hardware-level anti-forensic memory sanitization. Executes in-place 4-pass cryptographic overwriting (`0x00`, `0xFF`, pseudo-random bytes, `0x00`) across all registered private keys, session secrets, and PIN buffers in RAM, defeating cold-boot retention, DMA probing, and physical forensic flash dumps.

---

## Security Model & Engineering Boundaries

Gost-Net implements layered defensive controls, but operators must understand technical limitations and assumptions:

1. **Cryptographic Review:**
   - Gost-Net uses standard, audited cryptographic primitives (via the Python `cryptography` library), including AES-256-GCM, HKDF, ECDH SECP384R1, and ED25519.
   - However, the custom protocol framing and Double Ratchet implementation have not undergone formal third-party cryptographic verification. It should not be treated as a formally verified protocol like the Signal Protocol or Matrix Olm.

2. **Trust-On-First-Use (TOFU):**
   - The initial public key exchange occurs over the local broadcast channel. TOFU models are vulnerable to active Man-In-The-Middle (MITM) attacks during the very first packet exchange. Key verification out-of-band (e.g., verifying fingerprints in person) is recommended for high-assurance links.

3. **Storage & Data Deletion Realities:**
   - Local message stores are encrypted at rest using keys derived via PBKDF2.
   - The application performs multi-pass logical overwrites before deleting files. **However**, on modern solid-state media (NAND flash, eMMC, UFS, and SSDs), underlying controller wear-levelling algorithms, bad block remapping, and copy-on-write filesystems mean logical overwrites cannot physically guarantee complete forensic erasure of all flash blocks.

4. **Duress Protocol:**
   - A dual-PIN entry mechanism enables unlocking a separate decoy database to mitigate immediate casual inspection or coercion. It is a procedural mitigation, not proof against in-depth forensic flash inspection.

---

## Getting Started

### Prerequisites
- Python 3.10 or 3.11
- Microsoft Visual C++ Build Tools (Windows, for Kivy dependencies) or standard C build tools (Linux/macOS)

### Installation
```bash
# Clone repository
git clone https://github.com/Rhythm-Sanghi/Gost-Net.git
cd "Ghost net"

# Install dependencies
pip install -r requirements.txt
```

### Running on Desktop
```bash
python main.py
```

#### Authentication
- **Default Master PIN:** `1234` (Loads primary operational database and conversation history)
- **Default Duress PIN:** `9999` (Loads isolated decoy storage)
- *PINs can be updated from the in-app Settings screen.*

---

## Verification & Automated Tests

### 1. Headless Unit & Protocol Tests
Run the comprehensive test suite (284 passing tests across 16 test suites) covering hostile inputs, file transfer atomicity, application ACKs, raw disk encryption inspection, 3-node multi-hop mesh routing, anti-loop vector tracking, safety numbers, Cursor-on-Target 2.0 XML / GeoJSON translation, tactical waypoints, signed revocation, memory zeroization, audio RIFF/WAVE verification, chunked transfer resumption, compact binary framing & compression, encrypted group channels, reactive AODV discovery, link quality scoring, anti-tamper brute-force lockout, Dead Man's Switch expiration, MTU packet fragmentation/reassembly (SAR), Serial/LoRa radio bearer adapters, slotted low-power mesh duty cycling, K=2 disjoint multi-path discovery, per-hop onion wrapping, Ed25519 root-signed emergency detachment zeroization, Reed-Solomon MDS erasure coding / FEC over GF(2^8), circular and polygonal GPS GeoCast routing, covert audio WAV steganography & dead-drops, dynamic network topology graph telemetry, synchronized pseudo-random frequency hopping (FHSS), zero-knowledge Geohash spatial commitments, pre-shared OTP stream vaults, electronic warfare (EW) jamming detection, RFC-aligned DTN bundle custody transfer queues & CAS signals, rotating HMAC ephemeral beacon anonymization, ATAK / WinTAK CoT multicast streaming, tamper-evident Merkle audit ledgers, cognitive radio spectrum energy sensing, Byzantine-resilient swarm consensus voting, disruption-tolerant Bloom filter pub/sub, Web-of-Trust (WoT) Shamir threshold keyrings, autonomous mesh partition healing, covert Poisson traffic camouflage & chaffing, tactical 160-bit Kademlia DHT asset routing, planar Laplace differential privacy spatial obfuscation, collaborative ECM jammer triangulation, Random Linear Network Coding (RLNC) over GF(256), token-bucket QoS priority queuing, zero-knowledge Schnorr identity verification, Ring-LWE post-quantum key encapsulation (KEM), hybrid classical/quantum key combiner, Paillier additive homomorphic telemetry aggregation, 31-chip Gold sequence DSSS LPI/LPD modulation and despreading, distributed virtual antenna array beamforming, inter-packet delay (IPD) covert timing channel steganography, keyed bucket-permutation timing channels, Friis RF link budget with ITU-R P.838 rain and foliage attenuation, GPS-denied Cristian/Marzullo distributed mesh clock synchronisation, RF emission signature scoring with EIRP and passive intercept range advisory, dynamic adaptive modulation and coding (AMC) rate adaptation, upward SNR hysteresis filtering, Shannon capacity estimation, closed-loop CQI telemetry, Logical Key Hierarchy (LKH) O(log N) squad rekeying trees, forward and backward multicast secrecy, multi-criteria fuzzy logic and AHP composite routing, battery starvation avoidance, link failure pruning, RFC 4303/6479 sliding window anti-replay verification, out-of-order packet acceptance, duplicate sequence rejection, epoch rollover isolation, protocol chaos mutation fuzzing with bit flips and byte truncations, parser crash containment, unified C4ISR tactical HUD compilation and ASCII dashboard rendering, autonomous multi-bearer link health tracking and seamless failover, in-place multi-pass cryptographic memory panic zeroization, asynchronous persistence worker queues, zero-byte file transfer rejection, TOFU key mismatch detection and defense, in-memory zero-disk ephemeral message verification, and two-node direct localhost TCP socket communication:
```bash
python -m pytest -v tests/
```



### 2. Integration & Feature Verification
Run the 40-step end-to-end integration harness:
```bash
python scratch/test_new_features.py
```

### 3. Syntax & Bytecode Compilation
```bash
python -c "import compileall; assert compileall.compile_dir('.', force=False, quiet=1)"
```

---

## Two-Device Physical Field Test Plan

To validate Gost-Net under realistic conditions using two physical Android devices (or one Android device and one Desktop laptop):

### Setup
1. **Network Environment:**
   - Turn off mobile data / cellular connection on both devices.
   - Connect both devices to the same local Wi-Fi router (with WAN/internet disconnected) OR enable a Portable Wi-Fi Hotspot on Device A and connect Device B to it.
2. **App Launch & Permissions:**
   - Launch Gost-Net on both devices. Grant Local Network, Location (required by Android for Wi-Fi scanning), and Storage permissions when prompted.
   - Enter PIN `1234` on both devices to unlock.

### Verification Steps
1. **Peer Discovery (Radar Screen):**
   - Navigate to the **Radar** screen on both devices.
   - Confirm that each device discovers the other within 5–10 seconds.
   - Verify the displayed row: Call sign, active transport (`LAN` / `Wi-Fi Direct`), and identity status (`[TOFU]` or `[Verified]`).
   - Leave the screen to confirm radar scanning animations pause to conserve battery.

2. **Session Establishment & Message Lifecycle (Chat Screen):**
   - On Device A, tap the discovered peer from the Radar list to open Chat.
   - Send a test message: `"Grid check 01"`.
   - Observe message delivery badge transitions:
     - Immediate local bubble render: `Sending...`
     - TCP transmission complete: `Sent to peer`
     - Remote node application-layer reception: `Delivered`
   - Verify Device B displays the incoming message and automatically scrolls to bottom.

3. **Desktop Keyboard & Composer Verification:**
   - On Desktop, verify pressing `Enter` sends the message, while `Shift+Enter` inserts a newline.
   - Verify empty or whitespace-only messages cannot be submitted.
   - Rapidly double-tap the send button; verify message is not duplicated.

4. **Network Interruption & Retry:**
   - Switch Device B into Airplane Mode.
   - On Device A, attempt to send a message.
   - Verify the message status displays `Failed ↻`.
   - Turn Airplane Mode OFF on Device B. Wait for peer beacon reacquisition.
   - Tap `↻` on the failed message bubble on Device A; verify the message dispatches and updates to `Delivered`.

5. **Attachment & Integrity Verification:**
   - On Device A, tap the attachment icon and select a test image or document.
   - Send the file. Verify that Device B receives the file with matching name and size.
   - Check Device B's download folder to verify no orphaned `.part` files remain and the file hash matches Device A's source.

6. **Lifecycle & Persistence Check:**
   - On Device B, switch apps to background Gost-Net for 30 seconds, then return to foreground.
   - Verify no background thread crashes or duplicate socket errors occur.
   - Close Gost-Net completely on both devices and relaunch.
   - Enter PIN `1234` and verify conversation history is intact.

7. **Emergency Data Wipe:**
   - In Settings, select **Emergency Data Wipe**.
   - Confirm prompt. Verify that the local database and caches are cleared, and the application returns to the initial setup/lock state.

---

## License
MIT License. See [LICENSE](LICENSE) for details.
