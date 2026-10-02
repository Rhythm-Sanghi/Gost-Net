"""
Dynamic Mesh Topology Graph & RF Health Telemetry Engine.
Analyzes peer observations, link quality (PDR/RTT), and multi-hop paths to construct
live graph states, calculate network diameter and bridge centrality, and export
topological models in standard JSON and Graphviz DOT formats.
"""

import json
import time
import threading
from typing import Dict, List, Set, Tuple, Optional, Any


class TopologyGraphManager:
    """
    Maintains the live mesh topology graph, evaluates network health, and exports
    topological structures for tactical GIS and diagnostics overlays.
    """

    def __init__(self, local_node_id: str):
        self.local_node_id = local_node_id
        # Adjacency map: node_id -> {neighbor_id: {"pdr": float, "rtt_ms": float, "last_seen": float}}
        self.adjacency: Dict[str, Dict[str, Dict[str, float]]] = {}
        self.node_metadata: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()

    def update_node(self, node_id: str, username: str, battery: int = 100, role: str = "PEER"):
        """Update metadata for a mesh node."""
        with self.lock:
            self.node_metadata[node_id] = {
                "username": username,
                "battery": battery,
                "role": role,
                "updated_at": time.time()
            }
            if node_id not in self.adjacency:
                self.adjacency[node_id] = {}

    def update_edge(self, u: str, v: str, pdr: float = 1.0, rtt_ms: float = 10.0, bidirectional: bool = True):
        """Add or update an RF link edge between u and v."""
        with self.lock:
            now = time.time()
            if u not in self.adjacency:
                self.adjacency[u] = {}
            self.adjacency[u][v] = {"pdr": float(pdr), "rtt_ms": float(rtt_ms), "last_seen": now}

            if bidirectional:
                if v not in self.adjacency:
                    self.adjacency[v] = {}
                self.adjacency[v][u] = {"pdr": float(pdr), "rtt_ms": float(rtt_ms), "last_seen": now}

    def remove_stale_edges(self, max_age_seconds: float = 60.0):
        """Purges edges that haven't been observed recently."""
        now = time.time()
        with self.lock:
            for u in list(self.adjacency.keys()):
                for v in list(self.adjacency[u].keys()):
                    if now - self.adjacency[u][v]["last_seen"] > max_age_seconds:
                        del self.adjacency[u][v]

    def get_connected_components(self) -> List[Set[str]]:
        """Identifies isolated mesh partitions using BFS."""
        with self.lock:
            nodes = set(self.adjacency.keys()) | set(self.node_metadata.keys())
            visited = set()
            components = []

            for n in nodes:
                if n not in visited:
                    comp = set()
                    queue = [n]
                    visited.add(n)
                    while queue:
                        curr = queue.pop(0)
                        comp.add(curr)
                        for neighbor in self.adjacency.get(curr, {}).keys():
                            if neighbor not in visited:
                                visited.add(neighbor)
                                queue.append(neighbor)
                    components.append(comp)

            return components

    def calculate_network_diameter(self) -> int:
        """Calculates the maximum shortest path length (diameter) across connected nodes."""
        with self.lock:
            nodes = list(self.adjacency.keys())
            if len(nodes) <= 1:
                return 0

            max_dist = 0
            for src in nodes:
                distances = {src: 0}
                queue = [src]
                while queue:
                    curr = queue.pop(0)
                    curr_dist = distances[curr]
                    for neighbor in self.adjacency.get(curr, {}).keys():
                        if neighbor not in distances:
                            distances[neighbor] = curr_dist + 1
                            queue.append(neighbor)
                            if distances[neighbor] > max_dist:
                                max_dist = distances[neighbor]

            return max_dist

    def find_critical_bridge_nodes(self) -> List[str]:
        """
        Identifies critical single-point-of-failure bridge nodes (articulation points)
        whose removal increases the number of connected components.
        """
        with self.lock:
            base_comps = len(self.get_connected_components())
            all_nodes = list(self.adjacency.keys())
            critical_nodes = []

            for candidate in all_nodes:
                if candidate == self.local_node_id:
                    continue  # Don't evaluate local node removal

                # Simulate removal of candidate node
                remaining_nodes = [n for n in all_nodes if n != candidate]
                visited = set()
                sub_comps = 0

                for n in remaining_nodes:
                    if n not in visited:
                        sub_comps += 1
                        queue = [n]
                        visited.add(n)
                        while queue:
                            curr = queue.pop(0)
                            for neighbor in self.adjacency.get(curr, {}).keys():
                                if neighbor != candidate and neighbor not in visited:
                                    visited.add(neighbor)
                                    queue.append(neighbor)

                if sub_comps > base_comps:
                    critical_nodes.append(candidate)

            return critical_nodes

    def export_json(self) -> str:
        """Exports complete topology as JSON."""
        with self.lock:
            nodes = []
            for nid, meta in self.node_metadata.items():
                nodes.append({
                    "id": nid,
                    "username": meta.get("username", nid),
                    "battery": meta.get("battery", 100),
                    "role": meta.get("role", "PEER")
                })

            edges = []
            seen_pairs = set()
            for u, neighbors in self.adjacency.items():
                for v, metrics in neighbors.items():
                    pair = tuple(sorted([u, v]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        edges.append({
                            "source": u,
                            "target": v,
                            "pdr": metrics.get("pdr", 1.0),
                            "rtt_ms": metrics.get("rtt_ms", 0.0)
                        })

            diameter = self.calculate_network_diameter()
            critical_bridges = self.find_critical_bridge_nodes()

            data = {
                "timestamp": time.time(),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "network_diameter": diameter,
                "critical_bridges": critical_bridges,
                "nodes": nodes,
                "edges": edges
            }
            return json.dumps(data, indent=2)

    def export_dot(self) -> str:
        """Exports graph in Graphviz DOT format."""
        with self.lock:
            lines = ["graph MeshTopology {", "  node [shape=box, style=filled, fillcolor=\"#1A2332\", fontcolor=white];", "  edge [color=\"#4CAF50\"];"]

            for nid, meta in self.node_metadata.items():
                label = f"{meta.get('username', nid)}\\n({meta.get('battery', 100)}%)"
                lines.append(f'  "{nid}" [label="{label}"];')

            seen_edges = set()
            for u, neighbors in self.adjacency.items():
                for v, metrics in neighbors.items():
                    pair = tuple(sorted([u, v]))
                    if pair not in seen_edges:
                        seen_edges.add(pair)
                        pdr = metrics.get("pdr", 1.0)
                        rtt = metrics.get("rtt_ms", 0.0)
                        label = f"PDR: {pdr:.2f}\\n{rtt:.0f}ms"
                        lines.append(f'  "{u}" -- "{v}" [label="{label}"];')

            lines.append("}")
            return "\n".join(lines)
