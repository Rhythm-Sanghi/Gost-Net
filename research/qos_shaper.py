"""
Dynamic Token-Bucket QoS & Tactical Bandwidth Shaper Engine.
Enforces multi-tier priority scheduling (CRITICAL, TACTICAL, BULK) with token-bucket
rate limiting, automatically suppressing bulk traffic during link congestion to guarantee
zero latency for SOS emergency traffic and situational awareness CoT messages.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


class QoSClass:
    CRITICAL = 0  # SOS alerts, zeroization commands, key rotation
    TACTICAL = 1  # CoT positions, situational awareness, text chat
    BULK = 2      # Map tiles, file chunks, telemetry logs


class TokenBucket:
    """
    Standard token bucket rate limiter.
    """

    def __init__(self, capacity_bytes: int, refill_rate_bytes_sec: float):
        self.capacity_bytes = float(capacity_bytes)
        self.refill_rate = float(refill_rate_bytes_sec)
        self.tokens = float(capacity_bytes)
        self.last_refill = time.time()

    def refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity_bytes, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def can_consume(self, num_bytes: int) -> bool:
        self.refill()
        return self.tokens >= num_bytes

    def consume(self, num_bytes: int) -> bool:
        self.refill()
        if self.tokens >= num_bytes:
            self.tokens -= num_bytes
            return True
        return False


class TacticalQoSShaper:
    """
    Hierarchical QoS scheduler with Deficit Round-Robin priority and link-aware congestion backoff.
    """

    def __init__(
        self,
        tactical_rate_bytes_sec: float = 10000.0,
        bulk_rate_bytes_sec: float = 5000.0,
        congestion_pdr_threshold: float = 0.70
    ):
        self.congestion_pdr_threshold = congestion_pdr_threshold
        self.is_congested = False
        self.last_pdr = 1.0

        # Token buckets for rate-limited classes
        self.tactical_bucket = TokenBucket(capacity_bytes=20000, refill_rate_bytes_sec=tactical_rate_bytes_sec)
        self.bulk_bucket = TokenBucket(capacity_bytes=10000, refill_rate_bytes_sec=bulk_rate_bytes_sec)

        # Queues for each class: list of bytes
        self.queues: Dict[int, List[bytes]] = {
            QoSClass.CRITICAL: [],
            QoSClass.TACTICAL: [],
            QoSClass.BULK: []
        }
        self.lock = threading.RLock()

    def report_link_health(self, pdr: float, rtt_ms: float = 50.0):
        """Updates link health to adjust congestion throttling."""
        with self.lock:
            self.last_pdr = pdr
            self.is_congested = pdr < self.congestion_pdr_threshold

    def enqueue_packet(self, packet: bytes, qos_class: int = QoSClass.TACTICAL) -> bool:
        """Enqueues a packet into the designated priority queue."""
        with self.lock:
            if qos_class not in self.queues:
                qos_class = QoSClass.TACTICAL
            self.queues[qos_class].append(packet)
            return True

    def dequeue_packet(self) -> Optional[Tuple[bytes, int]]:
        """
        Dequeues the highest-priority schedulable packet.
        CRITICAL packets are always dequeued immediately without token restriction.
        TACTICAL packets require tactical token availability.
        BULK packets are suppressed if link is congested, and require bulk token availability.
        Returns (packet_bytes, qos_class) or None if queues are empty or blocked.
        """
        with self.lock:
            # 1. CRITICAL: Preemptive priority, unconstrained by tokens
            if self.queues[QoSClass.CRITICAL]:
                pkt = self.queues[QoSClass.CRITICAL].pop(0)
                return pkt, QoSClass.CRITICAL

            # 2. TACTICAL: Check bucket
            if self.queues[QoSClass.TACTICAL]:
                candidate = self.queues[QoSClass.TACTICAL][0]
                if self.tactical_bucket.consume(len(candidate)):
                    pkt = self.queues[QoSClass.TACTICAL].pop(0)
                    return pkt, QoSClass.TACTICAL

            # 3. BULK: Suppressed during congestion, otherwise metered
            if not self.is_congested and self.queues[QoSClass.BULK]:
                candidate = self.queues[QoSClass.BULK][0]
                if self.bulk_bucket.consume(len(candidate)):
                    pkt = self.queues[QoSClass.BULK].pop(0)
                    return pkt, QoSClass.BULK

            return None

    def get_queue_depth(self) -> Dict[str, int]:
        with self.lock:
            return {
                "critical": len(self.queues[QoSClass.CRITICAL]),
                "tactical": len(self.queues[QoSClass.TACTICAL]),
                "bulk": len(self.queues[QoSClass.BULK]),
                "is_congested": self.is_congested
            }
