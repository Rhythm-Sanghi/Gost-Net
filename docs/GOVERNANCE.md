# Gost-Net Feature Governance Principles

**Context:** Phase 79 — Future Feature Governance  
**Purpose:** Ensure Gost-Net remains a focused, coherent, offline-first peer-to-peer communication utility rather than a sprawling collection of disconnected experimental features.

---

## 1. Core Product Identity

Gost-Net is:
> **An offline-first, peer-to-peer communication tool designed to operate reliably when disconnected from centralized internet and cellular infrastructure.**

Gost-Net is **not**:
- A centralized cloud SaaS messenger.
- A social media platform.
- A theatrical "cyberpunk hacker terminal."
- An untestable cryptographic playground.

---

## 2. Gatekeeper Questions for Any Proposed Feature

Before any new capability, dependency, or protocol extension is merged into Gost-Net, maintainers must answer the following 6 gatekeeper questions:

### 1. Does this improve the core offline communication workflow?
- Does it make local discovery faster or more reliable?
- Does it improve message delivery under intermittent connectivity?
- Does it make connection status or identity trust more understandable to a non-technical user?
*If No:* Reject or isolate to an optional plugin.

### 2. Does it introduce an external or cloud dependency?
- Does it require a public STUN/TURN server, internet DNS, cloud API key, or centralized telemetry service?
*If Yes:* Reject immediately. Gost-Net must function with zero internet connectivity.

### 3. Does it undermine user privacy or increase attack surface?
- Does it log message contents, private keys, or PINs?
- Does it accept unbounded or unauthenticated network inputs?
- Does it transmit unencrypted identifiers over broadcast media?
*If Yes:* Reject.

### 4. Does it make the user interface more confusing or AI-generated?
- Does it introduce decorative glowing elements, meaningless progress bars, or nested card grids?
- Does it create redundant screens or dead buttons?
*If Yes:* Redesign to prioritize clear information hierarchy and functional utility.

### 5. Does it create substantial maintenance or performance overhead?
- Does it require heavy native C/C++ libraries that complicate Android cross-compilation?
- Does it run CPU-intensive polling loops that degrade mobile battery life?
*If Yes:* Reject or optimize before consideration.

### 6. Can it be independently tested and validated?
- Can it be tested in automated pytest suites without physical external hardware?
- If hardware-dependent, can it be isolated behind a clear adapter interface with mock fallback?
*If No:* Require test harnesses before acceptance.

---

## 3. Deprecation and Experimental Subsystems

- Experimental algorithms (e.g., lattice post-quantum KEMs, audio steganography, cognitive radio sensing) must remain modularized under `src/` and disabled by default in the standard user UI until they meet stability and testing bars.
- Subsystems with no active callers or test coverage will be flagged for deprecation and removed to protect code health.
