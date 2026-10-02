"""
Lightweight Byzantine-Resilient Swarm Consensus Protocol for Tactical Meshes.
Enables decentralized threshold decision-making (leader election, team-wide zeroize,
channel migrations) across partitioned ad-hoc squads with cryptographic ballot verification.
"""

import time
import math
import json
import threading
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field, asdict

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    ED25519_AVAILABLE = True
except ImportError:
    ED25519_AVAILABLE = False


@dataclass
class ConsensusProposal:
    proposal_id: str
    epoch: int
    action_type: str
    params: Dict[str, Any]
    proposer_id: str
    created_at: float = field(default_factory=time.time)


@dataclass
class ConsensusBallot:
    proposal_id: str
    epoch: int
    voter_id: str
    vote: bool  # True = Approve, False = Reject
    signature_hex: str
    timestamp: float = field(default_factory=time.time)

    def canonical_bytes(self) -> bytes:
        d = {
            "proposal_id": self.proposal_id,
            "epoch": self.epoch,
            "voter_id": self.voter_id,
            "vote": self.vote
        }
        return json.dumps(d, sort_keys=True, separators=(',', ':')).encode('utf-8')


class SwarmConsensusManager:
    """
    Coordinates decentralized swarm consensus using threshold BFT quorums.
    Tolerates up to f < n/3 Byzantine or disconnected nodes.
    """

    def __init__(self, local_node_id: str, private_key: Optional[Any] = None):
        self.local_node_id = local_node_id
        self.private_key = private_key
        self.current_epoch: int = 1

        # proposal_id -> ConsensusProposal
        self.proposals: Dict[str, ConsensusProposal] = {}
        # proposal_id -> Dict[voter_id, ConsensusBallot]
        self.ballots: Dict[str, Dict[str, ConsensusBallot]] = {}
        # List of committed proposal dicts
        self.committed_log: List[Dict[str, Any]] = []

        self.lock = threading.RLock()

    def create_proposal(self, action_type: str, params: Dict[str, Any]) -> ConsensusProposal:
        """Initiates a new proposal for the current epoch."""
        with self.lock:
            import uuid
            prop_id = f"prop_{self.current_epoch}_{uuid.uuid4().hex[:8]}"
            proposal = ConsensusProposal(
                proposal_id=prop_id,
                epoch=self.current_epoch,
                action_type=action_type,
                params=params,
                proposer_id=self.local_node_id,
                created_at=time.time()
            )
            self.proposals[prop_id] = proposal
            self.ballots[prop_id] = {}
            return proposal

    def cast_ballot(self, proposal_id: str, vote: bool) -> Optional[ConsensusBallot]:
        """Signs and registers a local ballot for proposal_id."""
        with self.lock:
            if proposal_id not in self.proposals:
                return None
            proposal = self.proposals[proposal_id]
            if proposal.epoch < self.current_epoch:
                return None  # Stale proposal

            sig_hex = ""
            ballot = ConsensusBallot(
                proposal_id=proposal_id,
                epoch=proposal.epoch,
                voter_id=self.local_node_id,
                vote=vote,
                signature_hex="",
                timestamp=time.time()
            )

            if self.private_key and ED25519_AVAILABLE:
                try:
                    data = ballot.canonical_bytes()
                    raw_sig = self.private_key.sign(data)
                    sig_hex = raw_sig.hex()
                except Exception as e:
                    print(f"[Consensus] Signing error: {e}")

            ballot.signature_hex = sig_hex
            self.ballots[proposal_id][self.local_node_id] = ballot
            return ballot

    def process_incoming_ballot(
        self,
        ballot: ConsensusBallot,
        voter_public_key: Optional[Any] = None
    ) -> bool:
        """Validates and records an incoming ballot from a swarm peer."""
        with self.lock:
            if ballot.proposal_id not in self.proposals:
                return False

            proposal = self.proposals[ballot.proposal_id]
            if ballot.epoch != proposal.epoch or ballot.epoch < self.current_epoch:
                return False

            # Verify signature if public key provided
            if voter_public_key and ED25519_AVAILABLE and ballot.signature_hex:
                try:
                    sig_bytes = bytes.fromhex(ballot.signature_hex)
                    data = ballot.canonical_bytes()
                    voter_public_key.verify(sig_bytes, data)
                except Exception:
                    return False

            self.ballots[ballot.proposal_id][ballot.voter_id] = ballot
            return True

    def calculate_quorum_threshold(self, total_nodes: int) -> int:
        """
        BFT quorum threshold: requires ceil((2 * N + 1) / 3) votes.
        For N=3 -> 3, N=4 -> 3, N=5 -> 4, N=6 -> 5, N=7 -> 5.
        """
        if total_nodes <= 0:
            return 1
        return math.ceil((2.0 * total_nodes + 1.0) / 3.0)

    def evaluate_proposal(self, proposal_id: str, total_nodes: int) -> Dict[str, Any]:
        """
        Evaluates whether a proposal has achieved sufficient affirmative quorum.
        """
        with self.lock:
            if proposal_id not in self.proposals:
                return {"status": "UNKNOWN_PROPOSAL", "quorum_reached": False}

            proposal = self.proposals[proposal_id]
            ballots_map = self.ballots.get(proposal_id, {})

            affirmative_count = sum(1 for b in ballots_map.values() if b.vote)
            reject_count = sum(1 for b in ballots_map.values() if not b.vote)
            threshold = self.calculate_quorum_threshold(total_nodes)

            quorum_reached = affirmative_count >= threshold

            return {
                "proposal_id": proposal_id,
                "epoch": proposal.epoch,
                "action_type": proposal.action_type,
                "total_nodes": total_nodes,
                "threshold_needed": threshold,
                "affirmative_votes": affirmative_count,
                "reject_votes": reject_count,
                "quorum_reached": quorum_reached,
                "status": "APPROVED" if quorum_reached else "PENDING"
            }

    def commit_proposal(self, proposal_id: str, total_nodes: int) -> Optional[Dict[str, Any]]:
        """
        Commits an approved proposal, applies the action to local state,
        and increments the epoch counter.
        """
        with self.lock:
            eval_result = self.evaluate_proposal(proposal_id, total_nodes)
            if not eval_result.get("quorum_reached"):
                return None

            proposal = self.proposals[proposal_id]
            record = {
                "proposal_id": proposal.proposal_id,
                "epoch": proposal.epoch,
                "action_type": proposal.action_type,
                "params": proposal.params,
                "proposer_id": proposal.proposer_id,
                "committed_at": time.time(),
                "affirmative_voters": [
                    b.voter_id for b in self.ballots[proposal_id].values() if b.vote
                ]
            }

            self.committed_log.append(record)
            self.current_epoch += 1  # Epoch fences future proposals
            return record
