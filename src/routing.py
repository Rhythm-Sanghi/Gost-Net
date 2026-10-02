import threading
import time
from typing import Dict, Optional, List, Set, Any

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RouteEntry:
    destination_peer_id: str
    next_hop_id: str
    metric: int
    last_updated: float
    hops: List[str] = field(default_factory=list)
    is_direct: bool = False
    battery_level: int = 100
    sequence_number: int = 1
    rtt_ms: float = 0.0
    pdr: float = 1.0  # Packet Delivery Ratio (0.0 to 1.0)
    route_status: str = "ACTIVE"  # "ACTIVE", "STALE", "BROKEN"


class RoutingTable:

    def __init__(self, max_route_age: float = 30.0):
        self.routes: Dict[str, RouteEntry] = {}
        self.peers_seen: Dict[str, Set[str]] = {}
        self.lock = threading.RLock()
        self.max_route_age = max_route_age
        self.table_version = 0
        self.local_sequence_number = 1
        self.broadcast_counter = 0
        self.seen_rreq_broadcasts: Dict[str, float] = {}
        self.link_metrics: Dict[str, Dict[str, float]] = {}

        
    def add_peer_observation(self, observer_id: str, observed_peer_ids: List[str]):
        with self.lock:
            if observer_id not in self.peers_seen:
                self.peers_seen[observer_id] = set()
            self.peers_seen[observer_id] = set(observed_peer_ids)
    
    def add_direct_route(self, peer_id: str, battery_level: int = 100):
        with self.lock:
            entry = RouteEntry(
                destination_peer_id=peer_id,
                next_hop_id=peer_id,
                metric=0,
                last_updated=time.time(),
                hops=[peer_id],
                is_direct=True,
                battery_level=battery_level
            )
            self.routes[peer_id] = entry
            self.table_version += 1
            return True
    
    def add_route(self, destination_id: str, next_hop_id: str, metric: int, hops: List[str], next_hop_battery: int = 100):
        adjusted_metric = metric
        if next_hop_battery < 20:
            adjusted_metric += 5
            
        if adjusted_metric > 15:
            return False
        
        with self.lock:
            if destination_id in self.routes:
                existing = self.routes[destination_id]
                if adjusted_metric < existing.metric or (existing.next_hop_id == next_hop_id and adjusted_metric != existing.metric) or (adjusted_metric == existing.metric and time.time() - existing.last_updated > 5):
                    self.routes[destination_id] = RouteEntry(
                        destination_peer_id=destination_id,
                        next_hop_id=next_hop_id,
                        metric=adjusted_metric,
                        last_updated=time.time(),
                        hops=hops,
                        is_direct=False,
                        battery_level=next_hop_battery
                    )
                    self.table_version += 1
                    return True
                return False
            else:
                self.routes[destination_id] = RouteEntry(
                    destination_peer_id=destination_id,
                    next_hop_id=next_hop_id,
                    metric=adjusted_metric,
                    last_updated=time.time(),
                    hops=hops,
                    is_direct=False,
                    battery_level=next_hop_battery
                )
                self.table_version += 1
                return True
    
    def get_route(self, destination_id: str) -> Optional[RouteEntry]:
        with self.lock:
            entry = self.routes.get(destination_id)
            if entry:
                if not entry.is_direct and time.time() - entry.last_updated > self.max_route_age:
                    del self.routes[destination_id]
                    self.table_version += 1
                    return None
                return entry
            return None
    
    def remove_stale_routes(self):
        with self.lock:
            current_time = time.time()
            stale_peers = []
            
            for peer_id, entry in list(self.routes.items()):
                if not entry.is_direct and current_time - entry.last_updated > self.max_route_age:
                    stale_peers.append(peer_id)
            
            for peer_id in stale_peers:
                del self.routes[peer_id]
                self.table_version += 1
            
            return stale_peers
    
    def get_all_routes(self) -> Dict[str, RouteEntry]:
        with self.lock:
            return {k: v for k, v in self.routes.items()}
    
    def get_direct_peers(self) -> List[str]:
        with self.lock:
            return [peer_id for peer_id, entry in self.routes.items() if entry.is_direct]
    
    def get_reachable_peers(self) -> List[str]:
        with self.lock:
            return list(self.routes.keys())
    
    def clear(self):
        with self.lock:
            self.routes.clear()
            self.peers_seen.clear()
            self.table_version += 1
    
    def compute_distance_vector(self, my_peer_id: str) -> Dict[str, int]:
        with self.lock:
            dv = {my_peer_id: 0}
            for peer_id, entry in self.routes.items():
                dv[peer_id] = entry.metric
            return dv
    
    def update_from_peer_advertisement(self, peer_id: str, advertised_distances: Dict[str, int]):
        with self.lock:
            for dest_id, announced_metric in advertised_distances.items():
                if dest_id == peer_id:
                    continue
                
                new_metric = announced_metric + 1
                current_route = self.routes.get(dest_id)
                
                if current_route is None or new_metric < current_route.metric:
                    hops = self._reconstruct_hops(peer_id, dest_id, new_metric)
                    self.add_route(dest_id, peer_id, new_metric, hops)
    
    def _reconstruct_hops(self, next_hop_id: str, destination_id: str, metric: int) -> List[str]:
        return [destination_id] + [next_hop_id]

    def update_link_metric(self, peer_id: str, rtt_ms: float, success: bool):
        """Update Exponential Moving Average (EMA) of RTT and Packet Delivery Ratio (PDR)."""
        with self.lock:
            if peer_id not in self.link_metrics:
                self.link_metrics[peer_id] = {
                    "rtt_ms": max(1.0, rtt_ms),
                    "pdr": 1.0 if success else 0.5,
                    "samples": 1
                }
            else:
                curr = self.link_metrics[peer_id]
                alpha = 0.25
                sample_pdr = 1.0 if success else 0.0
                curr["pdr"] = (1.0 - alpha) * curr["pdr"] + alpha * sample_pdr
                if success and rtt_ms > 0:
                    curr["rtt_ms"] = (1.0 - alpha) * curr["rtt_ms"] + alpha * rtt_ms
                curr["samples"] += 1

            # Update corresponding direct route if present
            if peer_id in self.routes:
                route = self.routes[peer_id]
                route.rtt_ms = self.link_metrics[peer_id]["rtt_ms"]
                route.pdr = self.link_metrics[peer_id]["pdr"]

    def get_link_metric(self, peer_id: str) -> Dict[str, float]:
        with self.lock:
            if peer_id in self.link_metrics:
                return dict(self.link_metrics[peer_id])
            return {"rtt_ms": 25.0, "pdr": 1.0, "samples": 0}


    def create_rreq(self, originator_id: str, destination_id: str) -> Dict[str, Any]:
        """Generate an AODV Route Request (RREQ) packet dictionary."""
        with self.lock:
            self.broadcast_counter += 1
            self.local_sequence_number += 1
            broadcast_id = self.broadcast_counter
            
            dest_route = self.routes.get(destination_id)
            dest_seq = dest_route.sequence_number if dest_route else 0
            
            # Record our own broadcast to avoid looping
            self.seen_rreq_broadcasts[f"{originator_id}_{broadcast_id}"] = time.time()
            
            return {
                "type": "RREQ",
                "originator_id": originator_id,
                "destination_id": destination_id,
                "broadcast_id": broadcast_id,
                "originator_seq": self.local_sequence_number,
                "dest_seq": dest_seq,
                "hop_count": 0,
                "hops": [originator_id],
                "timestamp": time.time()
            }

    def process_rreq(self, rreq: Dict[str, Any], local_peer_id: str) -> Optional[Dict[str, Any]]:
        """
        Process an incoming RREQ. If local node is destination or has a fresh route,
        generates an RREP. Otherwise records reverse path and returns None (for forwarding).
        """
        with self.lock:
            originator = rreq.get("originator_id")
            dest = rreq.get("destination_id")
            bcast_id = rreq.get("broadcast_id")
            orig_seq = rreq.get("originator_seq", 1)
            hop_count = rreq.get("hop_count", 0)
            hops = rreq.get("hops", [])
            
            key = f"{originator}_{bcast_id}"
            now = time.time()
            
            # Prune old broadcasts
            for k in list(self.seen_rreq_broadcasts.keys()):
                if now - self.seen_rreq_broadcasts[k] > 60.0:
                    del self.seen_rreq_broadcasts[k]
                    
            if key in self.seen_rreq_broadcasts:
                return None  # Drop duplicate RREQ
                
            self.seen_rreq_broadcasts[key] = now
            
            # Establish/update reverse route back to originator
            previous_hop = hops[-1] if hops else originator
            reverse_hops = list(reversed(hops)) if hops else [originator]
            self.add_route(
                destination_id=originator,
                next_hop_id=previous_hop,
                metric=hop_count + 1,
                hops=reverse_hops
            )
            if originator in self.routes:
                self.routes[originator].sequence_number = max(
                    self.routes[originator].sequence_number,
                    orig_seq
                )
                
            # If local node is the intended destination:
            if dest == local_peer_id:
                self.local_sequence_number += 1
                return {
                    "type": "RREP",
                    "originator_id": originator,
                    "destination_id": local_peer_id,
                    "dest_seq": self.local_sequence_number,
                    "hop_count": 0,
                    "hops": [local_peer_id],
                    "target_next_hop": previous_hop,
                    "timestamp": time.time()
                }
                
            # Intermediate node check: does this node have a valid route to destination?
            dest_route = self.routes.get(dest)
            if (dest_route and dest_route.route_status == "ACTIVE" 
                    and dest_route.sequence_number >= rreq.get("dest_seq", 0)
                    and now - dest_route.last_updated < self.max_route_age):
                return {
                    "type": "RREP",
                    "originator_id": originator,
                    "destination_id": dest,
                    "dest_seq": dest_route.sequence_number,
                    "hop_count": dest_route.metric,
                    "hops": [local_peer_id] + dest_route.hops,
                    "target_next_hop": previous_hop,
                    "timestamp": time.time()
                }
                
            return None

    def process_rrep(self, rrep: Dict[str, Any], local_peer_id: str) -> bool:
        """
        Process an incoming RREP, installing/updating forward route to destination.
        """
        with self.lock:
            dest = rrep.get("destination_id")
            dest_seq = rrep.get("dest_seq", 1)
            hop_count = rrep.get("hop_count", 0)
            hops = rrep.get("hops", [])
            previous_hop = hops[-1] if hops else dest
            
            existing = self.routes.get(dest)
            if (not existing or dest_seq > existing.sequence_number or 
                    (dest_seq == existing.sequence_number and hop_count + 1 < existing.metric)):
                self.add_route(
                    destination_id=dest,
                    next_hop_id=previous_hop,
                    metric=hop_count + 1,
                    hops=[dest] + hops
                )
                if dest in self.routes:
                    self.routes[dest].sequence_number = dest_seq
                    self.routes[dest].route_status = "ACTIVE"
                return True
            return False

    def create_rerr(self, unreachable_dest_id: str) -> Dict[str, Any]:
        """Generate an AODV Route Error (RERR) packet for broken links."""
        with self.lock:
            if unreachable_dest_id in self.routes:
                self.routes[unreachable_dest_id].route_status = "BROKEN"
            return {
                "type": "RERR",
                "unreachable_destinations": [unreachable_dest_id],
                "timestamp": time.time()
            }

    def process_rerr(self, rerr: Dict[str, Any]) -> List[str]:
        """Process RERR and invalidate affected routes."""
        with self.lock:
            invalidated = []
            unreachable = rerr.get("unreachable_destinations", [])
            for unreach in unreachable:
                for dest_id, route in list(self.routes.items()):
                    if dest_id == unreach or route.next_hop_id == unreach:
                        route.route_status = "BROKEN"
                        invalidated.append(dest_id)
            return invalidated

