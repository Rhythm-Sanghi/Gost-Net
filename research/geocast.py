"""
Geofenced Geographic Mesh Casting (GeoCast) Engine.
Enforces area-targeted transmission and delivery restricted to nodes physically
present within circular or polygonal GPS geofences, while allowing out-of-zone
nodes to act as encrypted DTN transport mules without operator display.
"""

import math
import time
import threading
from typing import Dict, List, Optional, Tuple, Any


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points in meters using Haversine formula.
    """
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def point_in_polygon(lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    Determine if a point (lat, lon) is inside a given polygon using ray-casting.
    Polygon is a list of (lat, lon) vertices.
    """
    if len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)
    p1_lat, p1_lon = polygon[0]

    for i in range(n + 1):
        p2_lat, p2_lon = polygon[i % n]
        if min(p1_lon, p2_lon) < lon <= max(p1_lon, p2_lon):
            if lat <= max(p1_lat, p2_lat):
                if p1_lon != p2_lon:
                    xinters = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                    if p1_lat == p2_lat or lat <= xinters:
                        inside = not inside
        p1_lat, p1_lon = p2_lat, p2_lon

    return inside


class GeoCastRouter:
    """
    Coordinates spatial packet evaluation, geofence validation, and selective delivery.
    """

    def __init__(self, dedup_ttl: float = 120.0):
        self.dedup_ttl = dedup_ttl
        self.seen_geocasts: Dict[str, float] = {}
        self.lock = threading.Lock()

    def is_in_geofence(
        self,
        lat: Optional[float],
        lon: Optional[float],
        geofence_type: str,
        geofence_params: Dict[str, Any]
    ) -> bool:
        """
        Evaluates whether coordinates (lat, lon) satisfy the specified geofence.
        If coordinates are unknown/None, returns False (fails closed).
        """
        if lat is None or lon is None:
            return False

        if geofence_type.upper() == "CIRCULAR":
            center_lat = geofence_params.get("center_lat", 0.0)
            center_lon = geofence_params.get("center_lon", 0.0)
            radius_m = geofence_params.get("radius_m", 1000.0)
            dist = haversine_distance_meters(lat, lon, center_lat, center_lon)
            return dist <= radius_m

        elif geofence_type.upper() == "POLYGONAL":
            vertices = geofence_params.get("vertices", [])
            # Vertices should be list of (lat, lon) or [lat, lon]
            poly = [(v[0], v[1]) for v in vertices if len(v) >= 2]
            return point_in_polygon(lat, lon, poly)

        return False

    def create_geocast_packet(
        self,
        geocast_id: str,
        sender_id: str,
        sender_name: str,
        message: str,
        geofence_type: str,
        geofence_params: Dict[str, Any],
        ttl: int = 8
    ) -> Dict[str, Any]:
        """
        Formats a GeoCast packet dictionary.
        """
        return {
            "type": "GEOCAST",
            "geocast_id": geocast_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "message": message,
            "geofence_type": geofence_type.upper(),
            "geofence_params": geofence_params,
            "timestamp": time.time(),
            "network_ttl": ttl,
            "visited_nodes": [sender_id]
        }

    def process_incoming_geocast(
        self,
        packet: Dict[str, Any],
        local_lat: Optional[float],
        local_lon: Optional[float]
    ) -> Dict[str, Any]:
        """
        Evaluates incoming GeoCast packet against local coordinates.
        Returns:
            {
                "should_deliver": bool,
                "should_forward": bool,
                "in_zone": bool,
                "reason": str
            }
        """
        geocast_id = packet.get("geocast_id", "")
        now = time.time()

        with self.lock:
            # Purge expired seen entries
            expired = [gid for gid, t in self.seen_geocasts.items() if now - t > self.dedup_ttl]
            for gid in expired:
                del self.seen_geocasts[gid]

            if geocast_id in self.seen_geocasts:
                return {
                    "should_deliver": False,
                    "should_forward": False,
                    "in_zone": False,
                    "reason": "DUPLICATE_PACKET"
                }
            self.seen_geocasts[geocast_id] = now

        ttl = int(packet.get("network_ttl", 0))
        should_forward = ttl > 1

        g_type = packet.get("geofence_type", "CIRCULAR")
        g_params = packet.get("geofence_params", {})

        in_zone = self.is_in_geofence(local_lat, local_lon, g_type, g_params)

        return {
            "should_deliver": in_zone,
            "should_forward": should_forward,
            "in_zone": in_zone,
            "reason": "IN_ZONE_DELIVER" if in_zone else "OUT_OF_ZONE_RELAY_ONLY"
        }
