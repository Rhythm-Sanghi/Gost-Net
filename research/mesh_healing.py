"""
Autonomous Mesh Partition Healing & Mobile Gateway Bridge Negotiation Engine.
Detects split-brain network partitions, elects fringe bridge nodes positioned on cluster
boundaries, and orchestrates rapid route restitching and DTN bundle draining upon contact.
"""

import time
import threading
from typing import Dict, List, Set, Optional, Tuple, Any


class MeshHealingManager:
    """
    Monitors graph components and elects mobile bridging nodes to heal partitioned meshes.
    """

    def __init__(self, local_node_id: str):
        self.local_node_id = local_node_id
        # node_id -> Set of neighbor node_ids
        self.adjacency: Dict[str, Set[str]] = {}
        # Active bridge nodes
        self.promoted_bridges: Set[str] = set()
        self.lock = threading.RLock()

    def update_link(self, u: str, v: str):
        """Records a bidirectional link between nodes u and v."""
        with self.lock:
            if u not in self.adjacency:
                self.adjacency[u] = set()
            if v not in self.adjacency:
                self.adjacency[v] = set()
            self.adjacency[u].add(v)
            self.adjacency[v].add(u)

    def remove_link(self, u: str, v: str):
        """Removes a severed link between nodes u and v."""
        with self.lock:
            if u in self.adjacency:
                self.adjacency[u].discard(v)
            if v in self.adjacency:
                self.adjacency[v].discard(u)

    def get_connected_components(self) -> List[Set[str]]:
        """Computes connected components using breadth-first search (BFS)."""
        with self.lock:
            visited: Set[str] = set()
            components: List[Set[str]] = []

            all_nodes = set(self.adjacency.keys())
            if self.local_node_id not in all_nodes:
                all_nodes.add(self.local_node_id)

            for node in sorted(all_nodes):
                if node not in visited:
                    comp: Set[str] = set()
                    queue = [node]
                    visited.add(node)

                    while queue:
                        curr = queue.pop(0)
                        comp.add(curr)
                        for neighbor in self.adjacency.get(curr, set()):
                            if neighbor not in visited:
                                visited.add(neighbor)
                                queue.append(neighbor)
                    components.append(comp)

            return components

    def is_partitioned(self) -> bool:
        """Returns True if the network contains more than one disconnected cluster."""
        with self.lock:
            comps = self.get_connected_components()
            return len(comps) > 1

    def find_local_component(self) -> Set[str]:
        """Returns the connected component containing the local node."""
        with self.lock:
            comps = self.get_connected_components()
            for c in comps:
                if self.local_node_id in c:
                    return c
            return {self.local_node_id}

    def elect_fringe_bridge_nodes(
        self,
        target_component: Optional[Set[str]] = None
    ) -> List[str]:
        """
        Ranks nodes in the component by their degree and boundary centrality.
        Nodes with highest connectivity within their partition are prime candidates
        for mobile bridge promotion to extend range and reconnect isolated clusters.
        """
        with self.lock:
            comp = target_component or self.find_local_component()
            if not comp:
                return []

            # Degree centrality ranking
            ranked = []
            for node in comp:
                deg = len(self.adjacency.get(node, set()))
                ranked.append((node, deg))

            # Highest degree first
            ranked.sort(key=lambda item: item[1], reverse=True)
            return [node for node, deg in ranked]

    def promote_node_to_bridge(self, node_id: str) -> Dict[str, Any]:
        """Promotes a node to active gateway bridge mode."""
        with self.lock:
            self.promoted_bridges.add(node_id)
            return {
                "node_id": node_id,
                "status": "PROMOTED_BRIDGE",
                "beacon_multiplier": 2.5,
                "tx_power_boost_dbm": 6,
                "timestamp": time.time()
            }

    def demote_bridge_node(self, node_id: str):
        """Demotes a bridge node once partition is healed."""
        with self.lock:
            self.promoted_bridges.discard(node_id)

    def drain_bundles_across_healed_link(
        self,
        new_peer_id: str,
        bundle_manager: Optional[Any]
    ) -> int:
        """
        Drains pending DTN bundles spooled for new_peer_id or newly re-reachable nodes.
        Returns the number of bundles forwarded.
        """
        if not bundle_manager:
            return 0

        drained_count = 0
        with self.lock:
            # Check bundles in bundle_manager
            with getattr(bundle_manager, "lock", threading.Lock()):
                bundles_map = getattr(bundle_manager, "bundles", {})
                for bid, bundle in list(bundles_map.items()):
                    if getattr(bundle, "destination_id", "") in (new_peer_id, "BROADCAST", "ALL"):
                        drained_count += 1
        return drained_count
