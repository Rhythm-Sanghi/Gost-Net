"""
Tests for Phase 10: Cognitive Radio Spectrum Sensing, Swarm Consensus Protocol,
Content-Centric DTN Pub/Sub with Bloom Filter Sync, and Sovereign Identity (WoT & Shamir).
"""

import os
import sys
import time
import math
import shutil
import tempfile
import pytest

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from cognitive_radio import SpectrumSensingEngine
from swarm_consensus import SwarmConsensusManager, ConsensusProposal, ConsensusBallot
from dtn_pubsub import DTNPubSubRouter, BloomFilter, TopicMessage
from sovereign_identity import WebOfTrustKeyring, TrustLevel, ShamirThresholdCrypto
from network import GhostEngine


def test_cognitive_radio_energy_detection_and_ranking():
    """Verify radiometric energy detection, Wiener spectral flatness, and dynamic vacancy ranking."""
    engine = SpectrumSensingEngine(noise_floor_window=20, default_detection_threshold_margin=1.5)
    
    # 1. Energy Calculation Validation: [1, 2, 3, 4] -> sum(sq)=30, mean=7.5
    samples = [1.0, 2.0, 3.0, 4.0]
    assert abs(engine.compute_energy(samples) - 7.5) < 1e-6
    
    # 2. Spectral Flatness Validation (Wiener Entropy)
    # White noise (flat spectrum bins) -> flatness ~ 1.0
    flat_bins = [10.0, 10.0, 10.0, 10.0, 10.0]
    assert abs(engine.compute_spectral_flatness(flat_bins) - 1.0) < 1e-4
    
    # Strong single narrowband tone -> flatness near 0.0
    tone_bins = [0.001, 0.001, 1000.0, 0.001, 0.001]
    assert engine.compute_spectral_flatness(tone_bins) < 0.1
    
    # 3. Dynamic Channel Energy & Occupancy Detection
    quiet_samples = [0.05, 0.04, 0.06, 0.05, 0.03]
    jammed_samples = [4.2, 5.8, 6.1, 4.9, 5.5]
    
    # Calibrate baselines for channels 1, 2, 3
    for _ in range(6):
        engine.update_channel_observation(channel_id=1, samples=quiet_samples)
        engine.update_channel_observation(channel_id=2, samples=quiet_samples)
        engine.update_channel_observation(channel_id=3, samples=quiet_samples)
        
    # Inject heavy transmission/jamming into channel 2
    obs2 = engine.update_channel_observation(channel_id=2, samples=jammed_samples)
    obs1 = engine.update_channel_observation(channel_id=1, samples=quiet_samples)
    
    assert obs2["is_occupied"] is True
    assert obs2["energy"] > 20.0
    assert obs1["is_occupied"] is False
    
    # 4. Vacancy Ranking
    ranked = engine.rank_vacant_channels([1, 2, 3])
    # Best vacant channels first, jammed channel 2 ranked last
    assert len(ranked) == 3
    ranked_channels = [r[0] for r in ranked]
    assert ranked_channels[-1] == 2
    assert ranked_channels[0] in (1, 3)


def test_swarm_consensus_bft_quorum_and_commit():
    """Verify Byzantine fault-tolerant threshold quorum calculation, ballot voting, and epoch fencing."""
    mgr = SwarmConsensusManager(local_node_id="NODE_ALFA")
    
    # Quorum threshold verification for N=4 nodes: ceil((2*4 + 1)/3) = 3
    total_nodes = 4
    threshold = mgr.calculate_quorum_threshold(total_nodes)
    assert threshold == 3
    
    # Create proposal for tactical frequency migration
    prop = mgr.create_proposal(action_type="MIGRATE_RADIO_CHANNEL", params={"channel": 7})
    assert prop.epoch == 1
    assert prop.proposal_id in mgr.proposals
    
    # Proposer Alfa casts affirmative vote
    ballot_alfa = mgr.cast_ballot(prop.proposal_id, vote=True)
    assert ballot_alfa is not None
    
    # Check evaluation with 1 vote: pending
    res1 = mgr.evaluate_proposal(prop.proposal_id, total_nodes)
    assert res1["affirmative_votes"] == 1
    assert res1["quorum_reached"] is False
    assert res1["status"] == "PENDING"
    
    # Peer Bravo casts affirmative ballot
    ballot_bravo = ConsensusBallot(
        proposal_id=prop.proposal_id,
        epoch=1,
        voter_id="NODE_BRAVO",
        vote=True,
        signature_hex=""
    )
    mgr.process_incoming_ballot(ballot_bravo)
    
    # Check evaluation with 2 votes: still pending (needs 3)
    res2 = mgr.evaluate_proposal(prop.proposal_id, total_nodes)
    assert res2["affirmative_votes"] == 2
    assert res2["quorum_reached"] is False
    
    # Peer Charlie casts affirmative ballot -> achieves quorum (3/4)
    ballot_charlie = ConsensusBallot(
        proposal_id=prop.proposal_id,
        epoch=1,
        voter_id="NODE_CHARLIE",
        vote=True,
        signature_hex=""
    )
    mgr.process_incoming_ballot(ballot_charlie)
    
    res3 = mgr.evaluate_proposal(prop.proposal_id, total_nodes)
    assert res3["affirmative_votes"] == 3
    assert res3["quorum_reached"] is True
    assert res3["status"] == "APPROVED"
    
    # Commit proposal
    committed = mgr.commit_proposal(prop.proposal_id, total_nodes)
    assert committed is not None
    assert committed["action_type"] == "MIGRATE_RADIO_CHANNEL"
    assert committed["params"]["channel"] == 7
    assert len(mgr.committed_log) == 1
    
    # Epoch fencing: current_epoch advanced to 2; ballots for epoch 1 are rejected
    assert mgr.current_epoch == 2
    late_ballot = ConsensusBallot(
        proposal_id=prop.proposal_id,
        epoch=1,
        voter_id="NODE_DELTA",
        vote=True,
        signature_hex=""
    )
    assert mgr.process_incoming_ballot(late_ballot) is False


def test_dtn_pubsub_wildcard_matching_and_bloom_reconciliation():
    """Verify topic-based publish/subscribe with globbing wildcards and compact Bloom filter cache sync."""
    router_a = DTNPubSubRouter(local_node_id="NODE_A")
    router_b = DTNPubSubRouter(local_node_id="NODE_B")
    
    received_a_messages = []
    
    # Router A subscribes with wildcard glob patterns
    router_a.subscribe("intel/target/*", lambda m: received_a_messages.append((m.topic, m.payload)))
    router_a.subscribe("sitrep/#", lambda m: received_a_messages.append((m.topic, m.payload)))
    
    # Publish messages
    m1 = router_a.publish("intel/target/alpha", b"TARGET_RADAR_CONFIRMED")
    m2 = router_a.publish("sitrep/sector9/north", b"PERIMETER_CLEAR")
    m3 = router_a.publish("logistics/supplies", b"FUEL_NOMINAL")  # Unsubscribed
    
    assert len(received_a_messages) == 2
    topics = [item[0] for item in received_a_messages]
    assert "intel/target/alpha" in topics
    assert "sitrep/sector9/north" in topics
    assert "logistics/supplies" not in topics
    
    # 2. Bloom Filter Set Reconciliation
    # Router B is freshly initialized (empty cache)
    bf_b_empty = router_b.generate_bloom_filter(size_bits=512)
    
    # Router A reconciles against Router B's empty Bloom filter
    missing_for_b = router_a.reconcile_missing_items(bf_b_empty)
    assert len(missing_for_b) == 3
    missing_cids = {m.content_id for m in missing_for_b}
    assert m1.content_id in missing_cids
    assert m2.content_id in missing_cids
    assert m3.content_id in missing_cids
    
    # Router B ingests all missing items
    for item in missing_for_b:
        router_b.receive_message(item)
        
    assert len(router_b.cache) == 3
    
    # Router B generates updated Bloom filter
    bf_b_synced = router_b.generate_bloom_filter(size_bits=512)
    
    # Router A reconciles again -> 0 missing items!
    missing_after_sync = router_a.reconcile_missing_items(bf_b_synced)
    assert len(missing_after_sync) == 0


def test_sovereign_identity_wot_transitive_trust():
    """Verify decentralized Web-of-Trust keyring, transitive trust propagation, and signature verification."""
    wot = WebOfTrustKeyring(local_node_id="ALICE")
    
    # Alice directly verifies Bob with trust 1.0 (in-person out-of-band key verification)
    wot.certify_peer(
        subject_id="BOB",
        subject_pubkey_hex="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        trust_level=TrustLevel.DIRECT_VERIFICATION
    )
    
    # Bob certifies Charlie with RECOMMENDED_TRUST (0.6)
    charlie_cert = wot.certify_peer.__wrapped__(
        wot,
        subject_id="CHARLIE",
        subject_pubkey_hex="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        trust_level=TrustLevel.RECOMMENDED_TRUST
    ) if hasattr(wot.certify_peer, '__wrapped__') else None
    
    # Simulate Bob issuing certification for Charlie
    from sovereign_identity import KeyCertification
    cert_bob_to_charlie = KeyCertification(
        issuer_id="BOB",
        subject_id="CHARLIE",
        subject_pubkey_hex="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        trust_level=TrustLevel.RECOMMENDED_TRUST,
        timestamp=time.time()
    )
    wot.add_certification(cert_bob_to_charlie)
    
    # Alice computes trust scores
    bob_trust = wot.compute_trust_score("BOB")
    assert bob_trust == 1.0
    assert wot.is_peer_trusted("BOB", threshold=0.5) is True
    
    # Charlie trust is transitively attenuated: direct Bob (1.0) * Bob->Charlie (0.6) * damping (0.7) = 0.42
    charlie_trust = wot.compute_trust_score("CHARLIE", max_depth=2)
    assert abs(charlie_trust - 0.42) < 1e-4
    assert wot.is_peer_trusted("CHARLIE", threshold=0.4) is True
    assert wot.is_peer_trusted("CHARLIE", threshold=0.8) is False
    
    # Unknown/Uncertified peer Eve yields 0.0 trust
    assert wot.compute_trust_score("EVE") == 0.0
    assert wot.is_peer_trusted("EVE") is False


def test_shamir_secret_sharing_gf256_reconstruction():
    """Verify (k, n) threshold secret sharing over GF(256) polynomial interpolation for multi-operator emergency auth."""
    secret_command = b"EMERGENCY_DESTRUCT_KEY_DELTA_4492"
    threshold_k = 3
    total_shares_n = 5
    
    # 1. Split secret into 5 shares
    shares = ShamirThresholdCrypto.split_secret(
        secret_bytes=secret_command,
        threshold_k=threshold_k,
        total_shares_n=total_shares_n
    )
    assert len(shares) == 5
    for x, share_bytes in shares:
        assert 1 <= x <= 5
        assert len(share_bytes) == len(secret_command)
        
    # 2. Perfect reconstruction using any k (3) distinct shares
    # Combination A: shares [0, 2, 4] (x=1, x=3, x=5)
    subset_a = [shares[0], shares[2], shares[4]]
    reconstructed_a = ShamirThresholdCrypto.reconstruct_secret(subset_a)
    assert reconstructed_a == secret_command
    
    # Combination B: shares [1, 3, 4] (x=2, x=4, x=5)
    subset_b = [shares[1], shares[3], shares[4]]
    reconstructed_b = ShamirThresholdCrypto.reconstruct_secret(subset_b)
    assert reconstructed_b == secret_command
    
    # Combination C: all 5 shares
    reconstructed_all = ShamirThresholdCrypto.reconstruct_secret(shares)
    assert reconstructed_all == secret_command
    
    # 3. Inadequate quorum: <= k - 1 shares (only 2 shares) fails to reconstruct secret
    subset_insufficient = [shares[0], shares[1]]
    reconstructed_bad = ShamirThresholdCrypto.reconstruct_secret(subset_insufficient)
    assert reconstructed_bad != secret_command


def test_phase10_live_engine_swarm_and_pubsub_dispatch():
    """Verify end-to-end TCP socket transmission of Pub/Sub topics, Swarm proposals, and Merkle audit trails between GhostEngine nodes."""
    dir_alice = tempfile.mkdtemp(prefix="ghostnet_phase10_alice_")
    dir_bob = tempfile.mkdtemp(prefix="ghostnet_phase10_bob_")
    
    alice = GhostEngine(username="AliceP10", downloads_dir=dir_alice, enable_storage=False)
    bob = GhostEngine(username="BobP10", downloads_dir=dir_bob, enable_storage=False)
    
    alice.start()
    bob.start()
    time.sleep(0.5)
    
    # Setup Pub/Sub subscriber on Bob
    bob_pubsub_received = []
    bob.subscribe_topic("tactical/orders/*", lambda msg: bob_pubsub_received.append((msg.topic, msg.payload)))
    
    # Setup Consensus proposal listener on Bob
    bob_proposals_received = []
    bob.on_consensus_proposal = lambda p: bob_proposals_received.append(p)
    
    # 1. Alice publishes a PubSub topic directly to Bob's port
    target_addr = f"127.0.0.1:{bob.tcp_port}"
    pub_msg = alice.publish_topic("tactical/orders/extract", b"EXTRACTION_WINDOW_OPEN_0900", broadcast=False)
    assert pub_msg is not None
    
    # Alice sends topic message to Bob over socket
    import base64
    import socket
    import json
    
    pub_header = {
        "type": "PUBSUB_PUBLISH",
        "content_id": pub_msg.content_id,
        "topic": pub_msg.topic,
        "payload_b64": base64.b64encode(pub_msg.payload).decode('utf-8'),
        "publisher_id": pub_msg.publisher_id,
        "timestamp": pub_msg.timestamp,
        "ttl_seconds": pub_msg.ttl_seconds,
        "sender_peer_id": alice.peer_id,
        "sender_tcp_port": alice.tcp_port
    }
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        s.connect(("127.0.0.1", bob.tcp_port))
        s.sendall(json.dumps(pub_header).encode('utf-8') + alice.HEADER_DELIMITER)
        
    time.sleep(0.8)
    
    # Verify Bob received the topic message
    assert len(bob_pubsub_received) == 1
    assert bob_pubsub_received[0][0] == "tactical/orders/extract"
    assert bob_pubsub_received[0][1] == b"EXTRACTION_WINDOW_OPEN_0900"
    
    # 2. Swarm Proposal socket dispatch
    proposal = alice.propose_swarm_action("TACTICAL_HALT", {"reason": "PERIMETER_PROBE"}, target_peers=[target_addr])
    assert proposal is not None
    
    time.sleep(0.8)
    
    # Verify Bob received the proposal
    assert len(bob_proposals_received) == 1
    assert bob_proposals_received[0].action_type == "TACTICAL_HALT"
    
    # 3. Merkle audit ledger integrity check
    alice_valid, _, _ = alice.verify_audit_ledger()
    bob_valid, _, _ = bob.verify_audit_ledger()
    assert alice_valid is True
    assert bob_valid is True
    
    alice_events = [e["event_type"] for e in alice.merkle_ledger.entries]
    bob_events = [e["event_type"] for e in bob.merkle_ledger.entries]
    assert "PUBSUB_PUBLISHED" in alice_events
    assert "SWARM_PROPOSAL_CREATED" in alice_events
    assert "PUBSUB_INGRESS" in bob_events
    assert "SWARM_PROPOSAL_RECEIVED" in bob_events
    
    alice.stop()
    bob.stop()
    shutil.rmtree(dir_alice, ignore_errors=True)
    shutil.rmtree(dir_bob, ignore_errors=True)
