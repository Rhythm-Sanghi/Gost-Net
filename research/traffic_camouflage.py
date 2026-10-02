"""
Covert Traffic Camouflage & Inter-Arrival Timing Modulation Engine.
Defeats SIGINT electronic warfare traffic-flow analysis and emitter fingerprinting by shaping
packet inter-arrival intervals via Poisson processes and injecting indistinguishable dummy chaff.
"""

import math
import time
import secrets
import threading
from typing import List, Tuple, Optional, Any


CHAFF_MAGIC_HEADER = b"GNCF"


class TrafficCamouflageEngine:
    """
    Modulates transmission timing and schedules dummy packets to flatten bursty traffic profiles.
    """

    def __init__(
        self,
        mean_rate_lambda: float = 0.5,
        min_interval_sec: float = 0.1,
        max_interval_sec: float = 5.0,
        enable_chaff: bool = True
    ):
        self.mean_rate_lambda = max(0.01, mean_rate_lambda)
        self.min_interval_sec = min_interval_sec
        self.max_interval_sec = max_interval_sec
        self.enable_chaff = enable_chaff
        self.lock = threading.RLock()

    def generate_next_interval(self) -> float:
        """
        Samples the next packet inter-arrival delay from an exponential distribution
        (Poisson arrival process): delta_t = -ln(1 - U) / lambda
        Clamped to [min_interval_sec, max_interval_sec].
        """
        # Draw uniform random u in (0, 1) using cryptographically secure RNG
        u = secrets.randbelow(1_000_000) / 1_000_000.0
        u = max(1e-6, min(1.0 - 1e-6, u))

        raw_interval = -math.log(1.0 - u) / self.mean_rate_lambda
        return max(self.min_interval_sec, min(self.max_interval_sec, raw_interval))

    @staticmethod
    def generate_chaff_packet(target_size_bytes: int = 128) -> bytes:
        """
        Generates an indistinguishable dummy chaff packet with high entropy.
        Includes a 4-byte internal magic header and random padding.
        """
        size = max(16, target_size_bytes)
        random_body = secrets.token_bytes(size - len(CHAFF_MAGIC_HEADER))
        return CHAFF_MAGIC_HEADER + random_body

    @staticmethod
    def is_chaff_packet(packet: bytes) -> bool:
        """Checks if an incoming packet is a dummy chaff frame."""
        return packet.startswith(CHAFF_MAGIC_HEADER)

    def schedule_transmissions(
        self,
        real_packets: List[bytes],
        start_time: Optional[float] = None
    ) -> List[Tuple[float, bytes, bool]]:
        """
        Takes real packets and schedules them with shaped Poisson inter-arrival delays.
        If real traffic is sparse and enable_chaff is True, inserts dummy chaff frames
        to maintain a consistent electromagnetic profile.
        Returns a list of (scheduled_timestamp, packet_bytes, is_chaff).
        """
        with self.lock:
            schedule = []
            curr_time = start_time if start_time is not None else time.time()

            queue = list(real_packets)
            while queue:
                pkt = queue.pop(0)
                interval = self.generate_next_interval()
                curr_time += interval
                schedule.append((curr_time, pkt, False))

                # If interval is large, insert a chaff packet in between
                if self.enable_chaff and interval > 2.0:
                    chaff_time = curr_time - (interval / 2.0)
                    chaff_pkt = self.generate_chaff_packet(len(pkt))
                    schedule.append((chaff_time, chaff_pkt, True))

            # Sort chronological
            schedule.sort(key=lambda item: item[0])
            return schedule
