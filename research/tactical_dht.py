"""
Tactical Kademlia Distributed Hash Table (DHT) for Off-Grid Asset Discovery.
Implements 160-bit XOR-metric decentralized key-value resource routing with k-buckets,
enabling reliable discovery of rendezvous points, emergency caches, and frequency plans.
"""

import time
import hashlib
import threading
from typing import Dict, List, Optional, Tuple, Any


def hash_key_160(key: str) -> int:
    """Hashes string key to 160-bit integer using SHA-1."""
    digest = hashlib.sha1(key.encode('utf-8')).digest()
    return int.from_bytes(digest, byteorder='big')


class KBucket:
    """
    Maintains a list of up to k nodes ordered by least-recently seen.
    """

    def __init__(self, k_size: int = 8):
        self.k_size = k_size
        # List of (node_id_int, node_info_dict)
        self.nodes: List[Tuple[int, Dict[str, Any]]] = []

    def update(self, node_id_int: int, node_info: Dict[str, Any]):
        for idx, (nid, _) in enumerate(self.nodes):
            if nid == node_id_int:
                # Move to end (most recently seen)
                self.nodes.pop(idx)
                self.nodes.append((node_id_int, node_info))
                return
        if len(self.nodes) < self.k_size:
            self.nodes.append((node_id_int, node_info))
        else:
            # Full bucket: discard or replace least recently seen (head)
            self.nodes.pop(0)
            self.nodes.append((node_id_int, node_info))

    def remove(self, node_id_int: int):
        self.nodes = [item for item in self.nodes if item[0] != node_id_int]


class TacticalDHT:
    """
    Decentralized Kademlia DHT node operating in ad-hoc mesh environments.
    """

    def __init__(self, local_node_id_str: str, k_size: int = 8):
        self.local_node_id_str = local_node_id_str
        self.local_id_int = hash_key_160(local_node_id_str)
        self.k_size = k_size

        # 160 k-buckets indexed 0 to 159
        self.buckets = [KBucket(k_size=k_size) for _ in range(160)]

        # Local storage: key_int -> (value, expiry_time)
        self.storage: Dict[int, Tuple[Any, float]] = {}
        self.lock = threading.RLock()

    def _get_bucket_index(self, target_id_int: int) -> int:
        """Determines bucket index based on leading zeros of distance."""
        dist = self.local_id_int ^ target_id_int
        if dist == 0:
            return 0
        # Bit length between 1 and 160
        length = dist.bit_length()
        return min(159, max(0, length - 1))

    def update_peer(self, peer_id_str: str, peer_info: Optional[Dict[str, Any]] = None):
        """Records or refreshes a peer in the routing table."""
        pid_int = hash_key_160(peer_id_str)
        if pid_int == self.local_id_int:
            return

        with self.lock:
            b_idx = self._get_bucket_index(pid_int)
            info = dict(peer_info) if peer_info else {"peer_id": peer_id_str}
            self.buckets[b_idx].update(pid_int, info)

    def find_closest_nodes(self, target_key_int: int, count: Optional[int] = None) -> List[Tuple[int, Dict[str, Any]]]:
        """Returns the count closest nodes to target_key_int based on XOR distance."""
        limit = count if count is not None else self.k_size
        with self.lock:
            all_nodes = []
            for b in self.buckets:
                all_nodes.extend(b.nodes)

            # Sort by XOR distance to target_key_int
            all_nodes.sort(key=lambda item: item[0] ^ target_key_int)
            return all_nodes[:limit]

    def store_value(self, key_str: str, value: Any, ttl_seconds: float = 3600.0) -> int:
        """Stores a key-value pair in local DHT memory."""
        k_int = hash_key_160(key_str)
        expiry = time.time() + ttl_seconds
        with self.lock:
            self.storage[k_int] = (value, expiry)
        return k_int

    def get_value(self, key_str: str) -> Optional[Any]:
        """Retrieves value if present and unexpired."""
        k_int = hash_key_160(key_str)
        with self.lock:
            if k_int in self.storage:
                val, expiry = self.storage[k_int]
                if time.time() <= expiry:
                    return val
                else:
                    del self.storage[k_int]
            return None
