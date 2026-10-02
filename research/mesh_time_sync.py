"""
Sub-Millisecond Distributed Mesh Clock Synchronisation Engine.

Provides NTP-free, GPS-denied precision time synchronisation across a
tactical mesh using an implementation of Cristian's algorithm for
one-way round-trip offset estimation, combined with Marzullo's
intersection algorithm for fault-tolerant multi-source clock selection.

Key design goals:
  - No dependency on GPS, NTP, or external time authority.
  - Handles node join/leave during synchronisation rounds.
  - Tolerates up to f < n/3 faulty or Byzantine clock sources.
  - Achieves sub-millisecond convergence across ≤8-hop meshes under
    realistic LAN RTT conditions (~1–5 ms per hop).

Algorithm overview:
  1. Each node broadcasts a SYNC_REQUEST carrying its local timestamp T1.
  2. Responders reply with T1 (echoed), T2 (receive time), T3 (send time).
  3. Requester records T4 (receive time).
  4. Cristian offset estimate:
       RTT = (T4 - T1) - (T3 - T2)
       offset = ((T2 - T1) + (T3 - T4)) / 2
  5. Each offset gives an uncertainty interval [offset - RTT/2, offset + RTT/2].
  6. Marzullo's algorithm finds the tightest interval consistent with the
     largest sub-set of sources (tolerating Byzantine outliers).
  7. Local clock is adjusted by the interval midpoint.
"""

import time
import math
import hashlib
import struct
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
#  Data classes                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class SyncSample:
    """
    A single clock synchronisation measurement from one peer.

    Attributes
    ----------
    peer_id : str
        Identifier of the responding peer.
    offset_s : float
        Estimated clock offset in seconds (positive = local clock behind).
    uncertainty_s : float
        Half-width of the confidence interval (= RTT / 2).
    rtt_s : float
        Round-trip time in seconds.
    timestamp_local : float
        Local ``time.monotonic()`` when the sample was collected.
    """
    peer_id: str
    offset_s: float
    uncertainty_s: float
    rtt_s: float
    timestamp_local: float


@dataclass
class SyncState:
    """
    Current synchronisation state of the local node.

    Attributes
    ----------
    estimated_offset_s : float
        Best estimate of local clock offset from mesh consensus time.
    uncertainty_s : float
        Half-width of the Marzullo intersection interval.
    stratum : int
        Synchronisation stratum (0 = primary reference, increments per hop).
    peer_count : int
        Number of peer samples used in last synchronisation round.
    last_sync_monotonic : float
        Monotonic timestamp of last successful synchronisation.
    is_synchronised : bool
        True once at least one successful Marzullo intersection has been found.
    """
    estimated_offset_s: float = 0.0
    uncertainty_s: float = float("inf")
    stratum: int = 15   # unsynchronised
    peer_count: int = 0
    last_sync_monotonic: float = 0.0
    is_synchronised: bool = False


# --------------------------------------------------------------------------- #
#  Cristian's Algorithm helper                                                  #
# --------------------------------------------------------------------------- #

class CristiansEstimator:
    """
    Single-source Cristian's Algorithm clock offset estimator.

    Computes offset and RTT given the four NTP-style timestamps:
      T1 - request departure (local)
      T2 - request arrival (remote)
      T3 - response departure (remote)
      T4 - response arrival (local)
    """

    @staticmethod
    def compute_offset(
        t1: float, t2: float, t3: float, t4: float
    ) -> Tuple[float, float]:
        """
        Compute clock offset and RTT from four timestamps.

        Parameters
        ----------
        t1, t2, t3, t4 : float
            Timestamps in seconds.  T1 and T4 are in the local clock domain;
            T2 and T3 are in the remote (peer) clock domain.

        Returns
        -------
        (offset_s, rtt_s) : Tuple[float, float]
            Signed offset (positive = local clock is behind peer) and
            round-trip time, both in seconds.
        """
        rtt = (t4 - t1) - (t3 - t2)
        offset = ((t2 - t1) + (t3 - t4)) / 2.0
        return offset, max(0.0, rtt)

    @staticmethod
    def confidence_interval(
        offset_s: float, rtt_s: float
    ) -> Tuple[float, float]:
        """
        Return the [low, high] confidence interval for the offset.

        Interval half-width equals RTT/2, representing the maximum
        one-way transmission delay uncertainty.

        Returns
        -------
        (low, high) : Tuple[float, float]
        """
        half = rtt_s / 2.0
        return offset_s - half, offset_s + half


# --------------------------------------------------------------------------- #
#  Marzullo's Algorithm                                                         #
# --------------------------------------------------------------------------- #

class MarzulloAlgorithm:
    """
    Marzullo's fault-tolerant clock selection algorithm.

    Given a list of offset intervals from multiple sources, finds the
    smallest interval that is consistent with the largest subset of sources,
    tolerating up to f faulty sources.

    Reference: K. Marzullo, "Maintaining the Time in a Distributed System",
    ACM SIGOPS Operating Systems Review, 1984.
    """

    @staticmethod
    def find_intersection(
        intervals: List[Tuple[float, float]],
        max_faulty: int = 0,
    ) -> Optional[Tuple[float, float]]:
        """
        Find the tightest interval consistent with at least
        ``len(intervals) - max_faulty`` sources.

        Parameters
        ----------
        intervals : List[Tuple[float, float]]
            List of (low, high) offset confidence intervals in seconds.
        max_faulty : int
            Maximum number of faulty sources to tolerate.
            Set to 0 to require agreement from all sources.

        Returns
        -------
        Optional[Tuple[float, float]]
            The intersection interval (low, high), or None if no intersection
            is found even after tolerating max_faulty faults.
        """
        if not intervals:
            return None

        # Build endpoint list: +1 for interval start, -1 for interval end
        endpoints: List[Tuple[float, int]] = []
        for lo, hi in intervals:
            endpoints.append((lo, +1))
            endpoints.append((hi, -1))

        endpoints.sort(key=lambda x: (x[0], -x[1]))  # sort by value, starts before ends

        n = len(intervals)
        target = n - max_faulty
        if target <= 0:
            return None

        best: Optional[Tuple[float, float]] = None
        best_width = float("inf")
        count = 0
        start = None

        for value, kind in endpoints:
            count += kind
            if count >= target and start is None:
                start = value
            if count < target and start is not None:
                width = value - start
                if width < best_width:
                    best_width = width
                    best = (start, value)
                start = None

        return best


# --------------------------------------------------------------------------- #
#  Mesh Clock Synchroniser                                                     #
# --------------------------------------------------------------------------- #

class MeshTimeSynchroniser:
    """
    Distributed mesh clock synchronisation manager.

    Maintains a rolling buffer of ``SyncSample`` observations from mesh
    peers and periodically invokes Marzullo's algorithm to update the
    local ``SyncState``.

    Usage
    -----
    Instantiate with a node identifier.  Call ``record_sync_sample`` each
    time a peer responds to a sync request.  Call ``run_synchronisation_round``
    to recompute the consensus offset.  Use ``adjusted_time()`` to obtain the
    mesh-synchronised wall-clock time.
    """

    # Maximum age of a sample before it is discarded
    SAMPLE_MAX_AGE_S: float = 60.0

    # Maximum samples retained per peer
    MAX_SAMPLES_PER_PEER: int = 5

    def __init__(self, node_id: str, stratum: int = 1):
        """
        Parameters
        ----------
        node_id : str
            Identifier of this node.
        stratum : int
            Initial stratum level (1 = directly synchronized to reference).
        """
        self.node_id = node_id
        self.state = SyncState(stratum=stratum)
        self._samples: Dict[str, List[SyncSample]] = {}
        self._wall_clock_offset_s: float = 0.0  # added to time.time()

    # ------------------------------------------------------------------
    # Sample management
    # ------------------------------------------------------------------

    def record_sync_sample(
        self,
        peer_id: str,
        t1: float,
        t2: float,
        t3: float,
        t4: float,
    ) -> SyncSample:
        """
        Record a four-timestamp Cristian sync exchange and store the sample.

        Parameters
        ----------
        peer_id : str
            Identifier of the responding peer.
        t1, t2, t3, t4 : float
            Four NTP-style timestamps in seconds.

        Returns
        -------
        SyncSample
            The computed synchronisation sample.
        """
        offset, rtt = CristiansEstimator.compute_offset(t1, t2, t3, t4)
        uncertainty = rtt / 2.0

        sample = SyncSample(
            peer_id=peer_id,
            offset_s=offset,
            uncertainty_s=uncertainty,
            rtt_s=rtt,
            timestamp_local=time.monotonic(),
        )

        if peer_id not in self._samples:
            self._samples[peer_id] = []
        self._samples[peer_id].append(sample)

        # Trim to most recent N per peer
        if len(self._samples[peer_id]) > self.MAX_SAMPLES_PER_PEER:
            self._samples[peer_id] = self._samples[peer_id][-self.MAX_SAMPLES_PER_PEER :]

        return sample

    def run_synchronisation_round(self, max_faulty: int = 0) -> SyncState:
        """
        Recompute the consensus clock offset using Marzullo's algorithm.

        Discards stale samples, builds the interval list, and applies
        the intersection result to the local clock state.

        Parameters
        ----------
        max_faulty : int
            Maximum number of Byzantine/faulty peer sources to tolerate.

        Returns
        -------
        SyncState
            Updated synchronisation state.
        """
        now_mono = time.monotonic()

        # Collect fresh samples (one per peer: the most recent)
        intervals: List[Tuple[float, float]] = []
        active_peers: List[str] = []

        for peer_id, samples in self._samples.items():
            # Filter stale
            fresh = [
                s for s in samples
                if (now_mono - s.timestamp_local) <= self.SAMPLE_MAX_AGE_S
            ]
            if not fresh:
                continue
            best = min(fresh, key=lambda s: s.rtt_s)
            lo, hi = CristiansEstimator.confidence_interval(
                best.offset_s, best.rtt_s
            )
            intervals.append((lo, hi))
            active_peers.append(peer_id)

        if not intervals:
            return self.state

        intersection = MarzulloAlgorithm.find_intersection(intervals, max_faulty)

        if intersection is not None:
            lo, hi = intersection
            midpoint = (lo + hi) / 2.0
            uncertainty = (hi - lo) / 2.0

            self._wall_clock_offset_s += midpoint
            self.state.estimated_offset_s = self._wall_clock_offset_s
            self.state.uncertainty_s = uncertainty
            self.state.peer_count = len(active_peers)
            self.state.last_sync_monotonic = now_mono
            self.state.is_synchronised = True
            # Stratum reflects best peer stratum + 1 (simplified: use init value)

        return self.state

    def adjusted_time(self) -> float:
        """
        Return the current wall-clock time adjusted by the consensus offset.

        Returns
        -------
        float
            Mesh-synchronised POSIX timestamp (seconds since epoch).
        """
        return time.time() + self._wall_clock_offset_s

    def precision_ms(self) -> float:
        """
        Return the current clock uncertainty in milliseconds.

        Returns
        -------
        float
            Uncertainty half-width in milliseconds.
        """
        return self.state.uncertainty_s * 1000.0

    def all_samples(self) -> List[SyncSample]:
        """Return a flat list of all retained sync samples across all peers."""
        result: List[SyncSample] = []
        for samples in self._samples.values():
            result.extend(samples)
        return result
