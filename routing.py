import threading
import time
from typing import Dict, Optional, List, Set
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


class RoutingTable:

    def __init__(self, max_route_age: float = 30.0):
        self.routes: Dict[str, RouteEntry] = {}
        self.peers_seen: Dict[str, Set[str]] = {}
        self.lock = threading.RLock()
        self.max_route_age = max_route_age
        self.table_version = 0
        
    def add_peer_observation(self, observer_id: str, observed_peer_ids: List[str]):
        with self.lock:
            if observer_id not in self.peers_seen:
                self.peers_seen[observer_id] = set()
            self.peers_seen[observer_id] = set(observed_peer_ids)
    
    def add_direct_route(self, peer_id: str):
        with self.lock:
            entry = RouteEntry(
                destination_peer_id=peer_id,
                next_hop_id=peer_id,
                metric=0,
                last_updated=time.time(),
                hops=[peer_id],
                is_direct=True
            )
            self.routes[peer_id] = entry
            self.table_version += 1
            return True
    
    def add_route(self, destination_id: str, next_hop_id: str, metric: int, hops: List[str]):
        if metric > 15:
            return False
        
        with self.lock:
            if destination_id in self.routes:
                existing = self.routes[destination_id]
                if metric < existing.metric or (metric == existing.metric and time.time() - existing.last_updated > 5):
                    self.routes[destination_id] = RouteEntry(
                        destination_peer_id=destination_id,
                        next_hop_id=next_hop_id,
                        metric=metric,
                        last_updated=time.time(),
                        hops=hops,
                        is_direct=False
                    )
                    self.table_version += 1
                    return True
                return False
            else:
                self.routes[destination_id] = RouteEntry(
                    destination_peer_id=destination_id,
                    next_hop_id=next_hop_id,
                    metric=metric,
                    last_updated=time.time(),
                    hops=hops,
                    is_direct=False
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
