"""
RFC-Aligned Delay-Tolerant Networking (DTN) Bundle Protocol & Custody Transfer Engine.
Provides priority-tiered bundle queues (EXPEDITED, STANDARD, BULK), explicit Custody
Acceptance Signals (CAS), and automated lifetime reclamation for austere multi-hop missions.
"""

import time
import json
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict


class BundlePriority:
    EXPEDITED = 0  # SOS, Detachment zeroization, medical emergencies
    STANDARD = 1   # Text messaging, waypoints, tactical telemetry
    BULK = 2       # Large file transfers, raster maps, survival manuals


@dataclass
class Bundle:
    bundle_id: str
    source_id: str
    destination_id: str
    creation_time: float
    lifetime_sec: float
    priority: int = BundlePriority.STANDARD
    payload: bytes = b""
    custody_requested: bool = False
    current_custodian_id: str = ""
    replicated_nodes: List[str] = field(default_factory=list)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.creation_time) > self.lifetime_sec

    def to_dict(self) -> Dict[str, Any]:
        import base64
        d = asdict(self)
        d["payload"] = base64.b64encode(self.payload).decode('utf-8')
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Bundle':
        import base64
        d = dict(data)
        if isinstance(d.get("payload"), str):
            d["payload"] = base64.b64decode(d["payload"])
        return cls(**d)


@dataclass
class CustodyAcceptanceSignal:
    bundle_id: str
    custodian_id: str
    timestamp: float
    reason: str = "CUSTODY_ACCEPTED"


class BundleProtocolManager:
    """
    Manages persistent DTN bundle queues with strict priority scheduling and
    custody transfer handoffs.
    """

    def __init__(self, local_node_id: str, max_queue_size: int = 500):
        self.local_node_id = local_node_id
        self.max_queue_size = max_queue_size

        # bundle_id -> Bundle
        self.bundles: Dict[str, Bundle] = {}
        # bundle_ids where this node is currently the accountable custodian
        self.held_custodies: set = set()
        self.lock = threading.Lock()

    def store_bundle(self, bundle: Bundle) -> bool:
        """Stores a bundle into the local DTN buffer."""
        with self.lock:
            if bundle.is_expired():
                return False

            if len(self.bundles) >= self.max_queue_size:
                # Evict oldest expired or lowest priority (BULK) bundle
                purged = self._evict_one_bundle()
                if not purged:
                    return False

            self.bundles[bundle.bundle_id] = bundle
            if bundle.current_custodian_id == self.local_node_id:
                self.held_custodies.add(bundle.bundle_id)
            return True

    def accept_custody(self, bundle_id: str) -> Optional[CustodyAcceptanceSignal]:
        """
        Accepts custody for a bundle, sending a CAS and assuming forwarding responsibility.
        """
        with self.lock:
            if bundle_id not in self.bundles:
                return None
            bundle = self.bundles[bundle_id]
            bundle.current_custodian_id = self.local_node_id
            self.held_custodies.add(bundle_id)

            return CustodyAcceptanceSignal(
                bundle_id=bundle_id,
                custodian_id=self.local_node_id,
                timestamp=time.time()
            )

    def process_cas(self, cas: CustodyAcceptanceSignal) -> bool:
        """
        Processes incoming Custody Acceptance Signal from downstream node.
        Releases local custody responsibility since downstream peer assumed custody.
        """
        with self.lock:
            bundle_id = cas.bundle_id
            if bundle_id in self.held_custodies:
                self.held_custodies.discard(bundle_id)
                if bundle_id in self.bundles:
                    self.bundles[bundle_id].current_custodian_id = cas.custodian_id
                print(f"[BundleProtocol] Custody transferred for bundle {bundle_id} to {cas.custodian_id}")
                return True
            return False

    def get_next_bundle_to_transmit(self, destination: Optional[str] = None) -> Optional[Bundle]:
        """
        Retrieves highest-priority bundle ready for transmission.
        Strict priority order: EXPEDITED (0) > STANDARD (1) > BULK (2).
        """
        with self.lock:
            now = time.time()
            candidates = [
                b for b in self.bundles.values()
                if not b.is_expired(now) and (destination is None or b.destination_id in (destination, "BROADCAST", "ALL"))
            ]
            if not candidates:
                return None

            # Sort by priority ascending (0 is highest), then creation time ascending (FIFO)
            candidates.sort(key=lambda b: (b.priority, b.creation_time))
            return candidates[0]

    def remove_bundle(self, bundle_id: str) -> bool:
        with self.lock:
            if bundle_id in self.bundles:
                del self.bundles[bundle_id]
                self.held_custodies.discard(bundle_id)
                return True
            return False

    def purge_expired_bundles(self) -> int:
        """Purges all expired bundles from buffer."""
        now = time.time()
        with self.lock:
            expired_ids = [bid for bid, b in self.bundles.items() if b.is_expired(now)]
            for bid in expired_ids:
                del self.bundles[bid]
                self.held_custodies.discard(bid)
            return len(expired_ids)

    def _evict_one_bundle(self) -> bool:
        """Helper to evict a low-priority or unheld bundle when queue is full."""
        now = time.time()
        # First priority: any expired bundle
        for bid, b in list(self.bundles.items()):
            if b.is_expired(now):
                del self.bundles[bid]
                self.held_custodies.discard(bid)
                return True

        # Second priority: non-custodial bulk bundle
        for bid, b in list(self.bundles.items()):
            if bid not in self.held_custodies and b.priority == BundlePriority.BULK:
                del self.bundles[bid]
                return True

        # Third priority: non-custodial standard bundle
        for bid, b in list(self.bundles.items()):
            if bid not in self.held_custodies and b.priority == BundlePriority.STANDARD:
                del self.bundles[bid]
                return True

        return False
