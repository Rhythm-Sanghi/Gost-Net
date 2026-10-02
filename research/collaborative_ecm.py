"""
Autonomous Collaborative Electronic Countermeasures (ECM) & Jammer Triangulation Engine.
Aggregates multi-node distributed RF power observations to calculate jammer positions via
log-distance path-loss multilateration, and advises friendly beam-nulling azimuths.
"""

import math
import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class JammerObservation:
    observer_id: str
    lat: float
    lon: float
    rssi_dbm: float
    timestamp: float


class CollaborativeECMManager:
    """
    Coordinates distributed sensing to locate and mitigate adversarial electronic warfare emitters.
    """

    def __init__(self, local_node_id: str, observation_ttl_sec: float = 60.0):
        self.local_node_id = local_node_id
        self.observation_ttl_sec = observation_ttl_sec
        # observer_id -> JammerObservation
        self.observations: Dict[str, JammerObservation] = {}
        self.lock = threading.RLock()

    def record_observation(self, observer_id: str, lat: float, lon: float, rssi_dbm: float):
        """Records an RF jamming power measurement from an observer node."""
        with self.lock:
            self.observations[observer_id] = JammerObservation(
                observer_id=observer_id,
                lat=lat,
                lon=lon,
                rssi_dbm=rssi_dbm,
                timestamp=time.time()
            )

    def prune_stale_observations(self):
        now = time.time()
        with self.lock:
            stale_keys = [
                oid for oid, obs in self.observations.items()
                if (now - obs.timestamp) > self.observation_ttl_sec
            ]
            for k in stale_keys:
                del self.observations[k]

    def estimate_distance_from_rssi(
        self,
        rssi_dbm: float,
        p0_dbm: float = -30.0,
        path_loss_exp: float = 2.5
    ) -> float:
        """
        Calculates estimated distance in meters using log-distance path loss:
        d = 10 ** ((P0 - RSSI) / (10 * n))
        """
        delta = (p0_dbm - rssi_dbm) / (10.0 * max(1.0, path_loss_exp))
        return max(1.0, 10.0 ** delta)

    def triangulate_jammer(
        self,
        p0_dbm: float = -30.0,
        path_loss_exp: float = 2.5
    ) -> Optional[Dict[str, Any]]:
        """
        Performs weighted centroid trilateration from multi-node observations.
        Requires at least 3 distinct observations.
        """
        with self.lock:
            self.prune_stale_observations()
            if len(self.observations) < 3:
                return None

            obs_list = list(self.observations.values())
            weights = []
            coords = []

            for obs in obs_list:
                dist = self.estimate_distance_from_rssi(obs.rssi_dbm, p0_dbm, path_loss_exp)
                # Weight inversely proportional to distance (stronger signal = closer observer)
                w = 1.0 / max(1.0, dist)
                weights.append(w)
                coords.append((obs.lat, obs.lon))

            total_weight = sum(weights)
            if total_weight <= 0:
                return None

            est_lat = sum(c[0] * w for c, w in zip(coords, weights)) / total_weight
            est_lon = sum(c[1] * w for c, w in zip(coords, weights)) / total_weight

            return {
                "estimated_lat": round(est_lat, 6),
                "estimated_lon": round(est_lon, 6),
                "contributing_nodes": [o.observer_id for o in obs_list],
                "confidence_score": min(1.0, len(obs_list) / 5.0),
                "timestamp": time.time()
            }

    @staticmethod
    def calculate_nulling_bearing(
        friendly_lat: float,
        friendly_lon: float,
        jammer_lat: float,
        jammer_lon: float
    ) -> float:
        """
        Calculates forward azimuth (bearing) from friendly location toward jammer in degrees [0, 360).
        """
        lat1 = math.radians(friendly_lat)
        lat2 = math.radians(jammer_lat)
        diff_lon = math.radians(jammer_lon - friendly_lon)

        x = math.sin(diff_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(diff_lon))

        initial_bearing = math.atan2(x, y)
        deg = math.degrees(initial_bearing)
        return (deg + 360.0) % 360.0
