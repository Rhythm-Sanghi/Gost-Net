"""
Zero-Knowledge Spatial Proximity Verification Engine.
Enables tactical mesh nodes to cryptographically prove geographical proximity
(e.g., within 150m, 600m, or 2.4km sectors) using blinded Geohash HMAC commitments
with ZERO absolute latitude/longitude coordinate disclosure.
"""

import hmac
import hashlib
from typing import List, Dict, Optional, Tuple, Any

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode_geohash(lat: float, lon: float, precision: int = 6) -> str:
    """
    Encodes (latitude, longitude) into a standard base32 Geohash string of given precision.
    Precision 5: ~4.9km | Precision 6: ~1.2km x 0.6km | Precision 7: ~152m x 152m
    """
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]

    geohash = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True

    while len(geohash) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2.0
            if lon > mid:
                ch |= bits[bit]
                lon_interval[0] = mid
            else:
                lon_interval[1] = mid
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2.0
            if lat > mid:
                ch |= bits[bit]
                lat_interval[0] = mid
            else:
                lat_interval[1] = mid

        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(BASE32[ch])
            bit = 0
            ch = 0

    return "".join(geohash)


def get_adjacent_geohashes(lat: float, lon: float, precision: int = 6) -> List[str]:
    """
    Returns center geohash and its 8 neighboring boundary cells by perturbing
    coordinates by grid delta. Eliminates border edge effects.
    """
    # Approximate cell dimension in degrees for common precisions
    step_lat = 180.0 / (2 ** (precision * 5 // 2))
    step_lon = 360.0 / (2 ** (precision * 5 - precision * 5 // 2))

    neighbors = set()
    for d_lat in [-step_lat, 0.0, step_lat]:
        for d_lon in [-step_lon, 0.0, step_lon]:
            c_lat = max(-90.0, min(90.0, lat + d_lat))
            c_lon = max(-180.0, min(180.0, lon + d_lon))
            neighbors.add(encode_geohash(c_lat, c_lon, precision))

    return list(neighbors)


class ProximityVerifier:
    """
    Constructs and verifies blinded spatial commitments to validate physical
    co-location without revealing absolute position.
    """

    @staticmethod
    def create_proximity_token(
        lat: float,
        lon: float,
        shared_salt: bytes,
        precision: int = 6
    ) -> Dict[str, Any]:
        """
        Creates a blinded proximity token containing salted HMAC commitments for
        the local geohash cell and its adjacent boundary neighbors.
        """
        center_gh = encode_geohash(lat, lon, precision)
        all_cells = get_adjacent_geohashes(lat, lon, precision)

        def _blind(cell: str) -> str:
            h = hmac.new(shared_salt, cell.encode('utf-8'), hashlib.sha256)
            return h.hexdigest()[:24]

        center_commitment = _blind(center_gh)
        neighbor_commitments = [_blind(cell) for cell in all_cells if cell != center_gh]

        return {
            "precision": precision,
            "center_commitment": center_commitment,
            "neighbor_commitments": neighbor_commitments
        }

    @staticmethod
    def verify_proximity(token_a: Dict[str, Any], token_b: Dict[str, Any]) -> bool:
        """
        Verifies whether token A and token B originate from within the same spatial sector.
        Returns True if center cells match or center cell of either is within the other's adjacent neighbors.
        """
        if token_a.get("precision") != token_b.get("precision"):
            return False

        c_a = token_a.get("center_commitment")
        c_b = token_b.get("center_commitment")
        if not c_a or not c_b:
            return False

        # Direct cell match
        if c_a == c_b:
            return True

        # Boundary cell match (A inside B's neighborhood or B inside A's neighborhood)
        neighbors_a = set(token_a.get("neighbor_commitments", []))
        neighbors_b = set(token_b.get("neighbor_commitments", []))

        if c_b in neighbors_a or c_a in neighbors_b:
            return True

        return False
