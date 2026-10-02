"""
Disruption-Tolerant Content-Centric Pub/Sub & Bloom Filter Cache Synchronization.
Enables topic-based publish/subscribe decoupled from host addresses, with compact
Bloom filter bit-vectors for bandwidth-optimal set reconciliation during opportunistic encounters.
"""

import time
import json
import struct
import hashlib
import fnmatch
import threading
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field


class BloomFilter:
    """
    Compact probabilistic set membership structure for cache reconciliation.
    Uses double-hashing (Kirsch-Mitzenmacher technique) over SHA-256.
    """

    def __init__(self, size_bits: int = 512, num_hashes: int = 4):
        self.size_bits = size_bits
        self.num_hashes = num_hashes
        self.bit_array = bytearray((size_bits + 7) // 8)

    def _get_hashes(self, item_id: str) -> List[int]:
        # Compute 2 32-bit hashes from SHA-256
        h = hashlib.sha256(item_id.encode('utf-8')).digest()
        h1 = struct.unpack("!I", h[:4])[0]
        h2 = struct.unpack("!I", h[4:8])[0]

        indices = []
        for i in range(self.num_hashes):
            idx = (h1 + i * h2) % self.size_bits
            indices.append(idx)
        return indices

    def add(self, item_id: str):
        for idx in self._get_hashes(item_id):
            byte_idx = idx // 8
            bit_idx = idx % 8
            self.bit_array[byte_idx] |= (1 << bit_idx)

    def contains(self, item_id: str) -> bool:
        for idx in self._get_hashes(item_id):
            byte_idx = idx // 8
            bit_idx = idx % 8
            if not (self.bit_array[byte_idx] & (1 << bit_idx)):
                return False
        return True

    def to_bytes(self) -> bytes:
        return bytes(self.bit_array)

    @classmethod
    def from_bytes(cls, data: bytes, size_bits: int = 512, num_hashes: int = 4) -> 'BloomFilter':
        bf = cls(size_bits=size_bits, num_hashes=num_hashes)
        bf.bit_array = bytearray(data)
        return bf


@dataclass
class TopicMessage:
    content_id: str
    topic: str
    payload: bytes
    publisher_id: str
    timestamp: float
    ttl_seconds: float = 86400.0

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.timestamp) > self.ttl_seconds


class DTNPubSubRouter:
    """
    Decoupled content router supporting wildcard topics and Bloom filter cache syncing.
    """

    def __init__(self, local_node_id: str, max_cache_entries: int = 1000):
        self.local_node_id = local_node_id
        self.max_cache_entries = max_cache_entries

        # topic_pattern -> list of callbacks
        self.subscriptions: Dict[str, List[Callable[[TopicMessage], None]]] = {}
        # content_id -> TopicMessage
        self.cache: Dict[str, TopicMessage] = {}
        self.lock = threading.RLock()

    @staticmethod
    def compute_content_id(topic: str, payload: bytes, timestamp: float) -> str:
        h = hashlib.sha256()
        h.update(topic.encode('utf-8'))
        h.update(payload)
        h.update(struct.pack("!d", timestamp))
        return h.hexdigest()[:24]

    def subscribe(self, topic_pattern: str, callback: Callable[[TopicMessage], None]):
        """
        Subscribes to topics matching topic_pattern (e.g., 'sitrep/*', 'intel/target/#').
        '#' is translated to '*' for multi-level matching.
        """
        pattern = topic_pattern.replace('#', '*')
        with self.lock:
            if pattern not in self.subscriptions:
                self.subscriptions[pattern] = []
            self.subscriptions[pattern].append(callback)

    def publish(
        self,
        topic: str,
        payload: bytes,
        ttl_seconds: float = 86400.0
    ) -> TopicMessage:
        """Publishes a new content-addressed message and delivers to matching local subscribers."""
        now = time.time()
        cid = self.compute_content_id(topic, payload, now)
        msg = TopicMessage(
            content_id=cid,
            topic=topic,
            payload=payload,
            publisher_id=self.local_node_id,
            timestamp=now,
            ttl_seconds=ttl_seconds
        )

        with self.lock:
            self._store_message(msg)
            self._dispatch_to_subscribers(msg)

        return msg

    def receive_message(self, msg: TopicMessage) -> bool:
        """Processes an incoming message from a mesh peer."""
        with self.lock:
            if msg.is_expired():
                return False
            if msg.content_id in self.cache:
                return False  # Already cached

            self._store_message(msg)
            self._dispatch_to_subscribers(msg)
            return True

    def generate_bloom_filter(self, size_bits: int = 512) -> BloomFilter:
        """Generates a compact Bloom filter containing all valid cached content IDs."""
        bf = BloomFilter(size_bits=size_bits)
        now = time.time()
        with self.lock:
            for cid, msg in self.cache.items():
                if not msg.is_expired(now):
                    bf.add(cid)
        return bf

    def reconcile_missing_items(self, peer_bloom_filter: BloomFilter) -> List[TopicMessage]:
        """
        Determines which locally cached items are missing from the peer's Bloom filter.
        Returns a list of messages to forward to the peer.
        """
        missing = []
        now = time.time()
        with self.lock:
            for cid, msg in self.cache.items():
                if msg.is_expired(now):
                    continue
                # If peer bloom filter doesn't have it, peer definitely needs it
                if not peer_bloom_filter.contains(cid):
                    missing.append(msg)
        return missing

    def _store_message(self, msg: TopicMessage):
        if len(self.cache) >= self.max_cache_entries:
            # Evict oldest entry
            oldest_cid = min(self.cache.keys(), key=lambda k: self.cache[k].timestamp)
            del self.cache[oldest_cid]
        self.cache[msg.content_id] = msg

    def _dispatch_to_subscribers(self, msg: TopicMessage):
        for pattern, callbacks in self.subscriptions.items():
            if fnmatch.fnmatch(msg.topic, pattern):
                for cb in callbacks:
                    try:
                        cb(msg)
                    except Exception as e:
                        print(f"[DTNPubSub] Subscriber error: {e}")
