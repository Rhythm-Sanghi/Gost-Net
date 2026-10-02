# Gost-Net Research & Experimental Prototypes

This directory contains standalone exploratory prototypes, tactical mesh algorithms, and research modules developed during earlier experimental phases.

## IMPORTANT STATUS NOTICE

1. **NOT IN PRODUCTION RUNTIME:** None of the modules in this directory are imported or executed during normal Gost-Net desktop or mobile application runtime.
2. **EXCLUDED FROM RELEASE BUILDS:** These files are explicitly excluded in `buildozer.spec` and do not enter release Android APK packages or desktop distributables.
3. **NOT HARDWARE VALIDATED:** The radio frequency, spread spectrum, acoustic modem, and electronic countermeasure models are mathematical simulations; they have not undergone physical radio hardware verification.
4. **NOT PART OF SECURITY CERTIFICATION:** Experimental cryptographic constructs (such as toy lattice KEMs, homomorphic aggregation, and zero-knowledge proofs) are educational/research prototypes and are NOT part of Gost-Net's supported security model.

## INVENTORY OF RESEARCH MODULES

- `adaptive_modulation.py`: Adaptive Modulation and Coding (AMC) simulation for RF links.
- `anti_jamming.py`: Energy detection and jamming defensive posture transitions.
- `anti_replay.py`: Experimental sliding window counter replay defense.
- `bearer_failover.py`: Dynamic multi-bearer failover controller.
- `bundle_protocol.py`: RFC 5050 bundle protocol framing variant.
- `chaos_fuzzer.py`: Protocol frame mutation fuzzer for negative testing.
- `cognitive_radio.py`: Energy detection spectrum sensing and channel ranking.
- `collaborative_ecm.py`: Simulated RF angle-of-arrival nulling and trilateration.
- `compact_framing.py`: Bit-packed binary framing for low-bandwidth links.
- `cot_geojson.py`: Cursor-on-Target (CoT) XML and GeoJSON translator.
- `covert_channel.py`: Inter-packet timing modulation covert channel.
- `dsss_modulation.py`: Gold code direct sequence spread spectrum simulator.
- `dtn_pubsub.py`: Topic-based publish/subscribe overlay with Bloom filter reconciliation.
- `duty_cycler.py`: Radio sleep/wake duty cycling controller.
- `ephemeral_handshake.py`: Pseudonym rotating beacon manager.
- `fec_engine.py`: Forward error correction (Reed-Solomon / erasure coding) prototype.
- `frequency_agility.py`: Pseudo-random fast frequency hopping simulator.
- `fuzzy_routing.py`: Multi-criteria fuzzy metric routing optimizer.
- `geocast.py`: Polygonal geofence coordinate router.
- `group_rekeying.py`: Logical Key Hierarchy (LKH) tree-based group rekeying.
- `homomorphic_aggregation.py`: Paillier homomorphic encrypted sensor aggregation.
- `link_budget.py`: Friis transmission path loss and link margin calculator.
- `memory_scrubber.py`: Multi-pass process memory zeroization routine.
- `merkle_vault.py`: Merkle audit tree for message event ledgers.
- `mesh_healing.py`: Network partition bridge promotion controller.
- `mesh_time_sync.py`: Cristian and Marzullo consensus wall-clock synchronization.
- `mesh_topology.py`: Topology graph and critical articulation point analyzer.
- `multipath_routing.py`: Disjoint multipath onion packet routing.
- `network_coding.py`: Random Linear Network Coding (RLNC) simulator.
- `post_quantum_kem.py`: Lattice Learning With Errors (LWE) key encapsulation prototype.
- `proximity_crypto.py`: Geohash zero-knowledge proximity verifier.
- `qos_shaper.py`: Token bucket traffic shaper.
- `quantum_resilient.py`: Pre-shared one-time pad (OTP) stream vault.
- `remote_wipe.py`: Cryptographic revocation token processor.
- `rf_signature.py`: RF emission advisor.
- `sovereign_identity.py`: Web-of-trust decentralized key endorsement.
- `spatial_privacy.py`: Laplace differential privacy coordinate perturber.
- `stego_transport.py`: Audio WAV LSB steganography and dead-drop deposit.
- `swarm_consensus.py`: Byzantine fault tolerant swarm consensus manager.
- `tactical_dht.py`: Kademlia XOR metric distributed hash table.
- `tactical_hud.py`: ASCII tactical terminal HUD renderer.
- `tak_bridge.py`: ATAK multicast socket bridge.
- `traffic_camouflage.py`: Poisson-distributed dummy traffic chaff generator.
- `transport_bearer.py`: Hardware serial UART packet fragmenter.
- `virtual_array.py`: Virtual antenna array beamforming simulator.
- `zkp_auth.py`: Schnorr zero-knowledge proof authentication protocol.
- `acoustic_handshake.py`: DTMF/acoustic frequency tone generator.

## EXECUTING RESEARCH TESTS

Research tests are isolated in `research/tests/` and can be run independently without affecting the core release test suite:

```bash
pytest research/tests/
```
