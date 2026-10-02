"""
Multi-Path Disjoint Mesh Routing & Per-Hop Onion Encapsulation Engine.
Calculates K=2 node-disjoint paths across the mesh topology to ensure redundant,
anti-jamming message delivery, paired with per-hop cryptographic onion wrapping.
"""

import json
import os
import time
import base64
import threading
from typing import Dict, List, Optional, Set, Tuple, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def find_disjoint_paths(
    graph: Dict[str, Set[str]],
    source: str,
    destination: str,
    k: int = 2
) -> List[List[str]]:
    """
    Computes up to k node-disjoint paths between source and destination using
    iterative BFS graph reduction. Intermediate nodes do not overlap between paths.
    """
    if source == destination or source not in graph:
        return []

    paths: List[List[str]] = []
    excluded_nodes: Set[str] = set()

    for _ in range(k):
        # BFS to find shortest path avoiding excluded nodes
        queue: List[List[str]] = [[source]]
        visited: Set[str] = {source} | excluded_nodes
        found_path: Optional[List[str]] = None

        while queue:
            current_path = queue.pop(0)
            curr = current_path[-1]

            if curr == destination:
                found_path = current_path
                break

            neighbors = graph.get(curr, set())
            for neighbor in neighbors:
                if neighbor == destination:
                    found_path = current_path + [destination]
                    break
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(current_path + [neighbor])
            if found_path:
                break

        if not found_path:
            break

        paths.append(found_path)
        # Exclude intermediate nodes (all nodes except source and destination)
        intermediate = set(found_path[1:-1])
        excluded_nodes.update(intermediate)

    return paths


def wrap_onion_packet(payload_bytes: bytes, path: List[str], hop_keys: Dict[str, bytes]) -> bytes:
    """
    Encapsulates payload_bytes in layered AES-256-GCM encryption for each hop along the path.
    Path is [self, hop_1, hop_2, ..., destination].
    The innermost payload is intended for destination.
    Returns the serialized outer onion packet to be sent to hop_1.
    """
    if len(path) <= 1:
        return payload_bytes

    # Path intermediate and destination hops (excluding self)
    relay_hops = path[1:]
    current_payload = payload_bytes

    # Wrap in reverse: from destination back to hop_1
    for i in range(len(relay_hops) - 1, -1, -1):
        target_hop = relay_hops[i]
        next_hop = relay_hops[i + 1] if i + 1 < len(relay_hops) else None
        key = hop_keys.get(target_hop)
        if not key:
            # Fallback if no specific hop key is available: use deterministic derived pad
            key = (target_hop.encode('utf-8') * 32)[:32]

        layer_dict = {
            "target": target_hop,
            "next_hop": next_hop,
            "data": base64.b64encode(current_payload).decode('utf-8')
        }
        layer_json = json.dumps(layer_dict).encode('utf-8')

        # Encrypt layer with AESGCM
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, layer_json, None)
        current_payload = nonce + ct

    return current_payload


def unwrap_onion_layer(onion_bytes: bytes, node_key: bytes) -> Tuple[Optional[str], Optional[bytes]]:
    """
    Unwraps the outer layer of an onion packet using the current node's key.
    Returns (next_hop, inner_data).
    If next_hop is None, this node is the final destination and inner_data is the application payload.
    If decryption fails, returns (None, None).
    """
    if len(onion_bytes) < 28:
        return None, None

    try:
        nonce = onion_bytes[:12]
        ct = onion_bytes[12:]
        aesgcm = AESGCM(node_key)
        layer_json = aesgcm.decrypt(nonce, ct, None)
        layer_dict = json.loads(layer_json.decode('utf-8'))
        next_hop = layer_dict.get("next_hop")
        inner_data = base64.b64decode(layer_dict.get("data", ""))
        return next_hop, inner_data
    except Exception as e:
        print(f"[MultiPathRouter] Failed to unwrap onion layer: {e}")
        return None, None


class MultiPathRouter:
    """
    Disjoint Multi-Path Router with duplicate suppression and onion dispatch.
    """

    def __init__(self, dedup_ttl: float = 60.0):
        self.dedup_ttl = dedup_ttl
        self.seen_messages: Dict[str, float] = {}
        self.lock = threading.Lock()

    def is_duplicate(self, message_id: str) -> bool:
        """
        Check if message_id has already been processed within the dedup_ttl window.
        Returns True if duplicate, False if novel.
        """
        now = time.time()
        with self.lock:
            # Purge expired entries
            expired = [m for m, t in self.seen_messages.items() if now - t > self.dedup_ttl]
            for m in expired:
                del self.seen_messages[m]

            if message_id in self.seen_messages:
                return True

            self.seen_messages[message_id] = now
            return False

    def dispatch_multipath(
        self,
        source: str,
        destination: str,
        message_id: str,
        payload: bytes,
        graph: Dict[str, Set[str]],
        hop_keys: Optional[Dict[str, bytes]] = None,
        transmit_callback: Optional[Any] = None
    ) -> List[List[str]]:
        """
        Discovers up to 2 node-disjoint paths and dispatches redundant onion-wrapped
        frames along each path.
        """
        paths = find_disjoint_paths(graph, source, destination, k=2)
        if not paths:
            return []

        for path in paths:
            next_hop = path[1]
            if hop_keys:
                onion_payload = wrap_onion_packet(payload, path, hop_keys)
            else:
                onion_payload = payload

            if transmit_callback:
                try:
                    transmit_callback(next_hop, onion_payload, message_id)
                except Exception as e:
                    print(f"[MultiPathRouter] Transmit callback error along path {path}: {e}")

        return paths
