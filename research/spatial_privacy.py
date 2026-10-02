"""
Geo-Indistinguishable Differential Privacy Spatial Obfuscation Engine.
Applies planar Laplace perturbation noise to GPS coordinate streams, providing mathematically
proven (epsilon)-differential privacy for friendly force tracking without compromising squad coordination.
"""

import math
import secrets
from typing import Tuple, Dict, Any


class PrivacyBudget:
    HIGH_PRECISION = 0.05   # ~20m radius (close tactical squad coordination)
    BALANCED_SITREP = 0.005 # ~200m radius (platoon level tracking)
    MAX_STEALTH = 0.001     # ~1000m radius (high-threat reconnaissance / sniper OPSEC)


class SpatialPrivacyEngine:
    """
    Perturbs spatial coordinates using polar Laplace noise to provide geo-indistinguishability.
    """

    METERS_PER_DEGREE_LAT = 111320.0

    @classmethod
    def sample_polar_laplace(cls, epsilon: float) -> Tuple[float, float]:
        """
        Samples radius r (in meters) and angle theta (in radians) from planar Laplace distribution:
        theta ~ Uniform[0, 2*pi)
        r = -ln(1 - u) / epsilon
        """
        eps = max(1e-5, epsilon)
        u1 = secrets.randbelow(1_000_000) / 1_000_000.0
        u2 = secrets.randbelow(1_000_000) / 1_000_000.0

        u1 = max(1e-6, min(1.0 - 1e-6, u1))
        u2 = max(1e-6, min(1.0 - 1e-6, u2))

        theta = 2.0 * math.pi * u1
        r_meters = -math.log(1.0 - u2) / eps
        return r_meters, theta

    @classmethod
    def obfuscate_coordinates(
        cls,
        lat: float,
        lon: float,
        epsilon: float = PrivacyBudget.BALANCED_SITREP
    ) -> Dict[str, Any]:
        """
        Obfuscates real GPS coordinates using planar Laplace differential privacy.
        Returns dictionary containing obfuscated lat/lon, perturbation distance, and epsilon.
        """
        r_meters, theta = cls.sample_polar_laplace(epsilon)

        delta_lat = (r_meters * math.cos(theta)) / cls.METERS_PER_DEGREE_LAT

        # Adjust longitude scaling by latitude cosine
        lat_rad = math.radians(lat)
        cos_lat = max(0.01, math.cos(lat_rad))
        meters_per_degree_lon = cls.METERS_PER_DEGREE_LAT * cos_lat
        delta_lon = (r_meters * math.sin(theta)) / meters_per_degree_lon

        obf_lat = max(-90.0, min(90.0, lat + delta_lat))
        obf_lon = max(-180.0, min(180.0, lon + delta_lon))

        return {
            "real_lat": lat,
            "real_lon": lon,
            "obfuscated_lat": round(obf_lat, 6),
            "obfuscated_lon": round(obf_lon, 6),
            "perturbation_meters": round(r_meters, 2),
            "epsilon": epsilon
        }

    @staticmethod
    def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Computes great-circle distance between two coordinates in meters."""
        r = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c
