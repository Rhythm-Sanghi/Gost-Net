"""
Electronic Warfare (EW) Jamming Detection & Autonomous Recovery Engine.
Distinguishes intentional RF jamming from natural distance attenuation by analyzing
multi-neighbor Link Quality Indicators (PDR) and channel contention metrics,
triggering automated defensive postures and channel agility.
"""

import time
import threading
from typing import Dict, List, Optional, Any, Callable


class DefensivePosture:
    NORMAL = "NORMAL"
    ELEVATED_INTERFERENCE = "ELEVATED_INTERFERENCE"
    EW_JAMMING_ACTIVE = "EW_JAMMING_ACTIVE"


class JammingDetector:
    """
    Monitors aggregate mesh link health to identify electronic warfare jamming signatures
    and orchestrate defensive counter-jamming responses.
    """

    def __init__(
        self,
        pdr_threshold: float = 0.25,
        min_affected_neighbors: int = 2,
        observation_window_sec: float = 30.0
    ):
        self.pdr_threshold = pdr_threshold
        self.min_affected_neighbors = min_affected_neighbors
        self.observation_window_sec = observation_window_sec

        # peer_id -> {"pdr": float, "cca_busy": float, "timestamp": float}
        self.observations: Dict[str, Dict[str, float]] = {}
        self.current_posture = DefensivePosture.NORMAL
        self.lock = threading.Lock()

        self.on_posture_changed: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def record_link_observation(self, peer_id: str, pdr: float, cca_busy: float = 0.0):
        """Record latest observed link metrics for a direct mesh neighbor."""
        with self.lock:
            self.observations[peer_id] = {
                "pdr": float(pdr),
                "cca_busy": float(cca_busy),
                "timestamp": time.time()
            }

    def evaluate_jamming_status(self) -> Dict[str, Any]:
        """
        Evaluates current link observations.
        If multiple direct neighbors exhibit simultaneous PDR collapse below threshold,
        a jamming signature is detected.
        """
        now = time.time()
        with self.lock:
            # Purge stale observations
            active_obs = {
                pid: obs for pid, obs in self.observations.items()
                if now - obs["timestamp"] <= self.observation_window_sec
            }
            self.observations = active_obs

            total_peers = len(active_obs)
            if total_peers == 0:
                return {
                    "jamming_detected": False,
                    "confidence": 0.0,
                    "affected_peers": 0,
                    "total_peers": 0,
                    "posture": DefensivePosture.NORMAL
                }

            degraded_peers = [
                pid for pid, obs in active_obs.items()
                if obs["pdr"] <= self.pdr_threshold
            ]
            degraded_count = len(degraded_peers)

            # High channel contention average
            avg_cca = sum(obs["cca_busy"] for obs in active_obs.values()) / total_peers

            jamming_detected = False
            confidence = 0.0
            new_posture = DefensivePosture.NORMAL

            if degraded_count >= self.min_affected_neighbors or (total_peers == 1 and degraded_count == 1 and avg_cca > 0.7):
                jamming_detected = True
                confidence = min(1.0, (degraded_count / max(1, total_peers)) * 0.7 + avg_cca * 0.3)
                new_posture = DefensivePosture.EW_JAMMING_ACTIVE
            elif degraded_count > 0 or avg_cca > 0.5:
                confidence = 0.4
                new_posture = DefensivePosture.ELEVATED_INTERFERENCE

            old_posture = self.current_posture
            self.current_posture = new_posture

        if old_posture != new_posture and self.on_posture_changed:
            try:
                self.on_posture_changed(new_posture, {
                    "degraded_peers": degraded_peers,
                    "confidence": confidence,
                    "avg_cca": avg_cca
                })
            except Exception as e:
                print(f"[JammingDetector] Posture callback error: {e}")

        return {
            "jamming_detected": jamming_detected,
            "confidence": confidence,
            "affected_peers": degraded_count,
            "total_peers": total_peers,
            "posture": new_posture
        }

    def reset(self):
        """Reset observations and posture to NORMAL."""
        with self.lock:
            self.observations.clear()
            self.current_posture = DefensivePosture.NORMAL
