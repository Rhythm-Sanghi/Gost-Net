"""
Dynamic Frequency Agility & Pseudo-Random Channel Hopping (FHSS) Coordinator.
Generates deterministic, time-synchronized channel hop sequences keyed by shared
mesh seed, navigates around jammed RF channels, and maintains rendezvous fallbacks.
"""

import time
import struct
import hmac
import hashlib
import threading
from typing import List, Dict, Optional, Tuple, Any


DEFAULT_LORA_CHANNELS_915 = [
    902.3, 902.5, 902.7, 902.9, 903.1, 903.3, 903.5, 903.7,
    903.9, 904.1, 904.3, 904.5, 904.7, 904.9, 905.1, 905.3
]


class FrequencyAgilityManager:
    """
    Coordinates synchronized pseudo-random frequency hopping (FHSS) across available
    radio channels to minimize probability of intercept and evade spot RF jamming.
    """

    def __init__(
        self,
        mesh_seed: bytes = b"GHOSTNET_FHSS_DEFAULT_SEED",
        channels: Optional[List[float]] = None,
        hop_interval_sec: float = 5.0,
        rendezvous_slot_interval: int = 10,
        clock_offset: float = 0.0
    ):
        self.mesh_seed = mesh_seed
        self.channels = channels or list(DEFAULT_LORA_CHANNELS_915)
        self.hop_interval_sec = hop_interval_sec
        self.rendezvous_slot_interval = rendezvous_slot_interval
        self.clock_offset = clock_offset

        self.blacklisted_channels: set = set()
        self.channel_metrics: Dict[int, Dict[str, float]] = {
            i: {"successes": 0, "failures": 0, "snr_avg": 0.0}
            for i in range(len(self.channels))
        }
        self.lock = threading.Lock()

    def set_clock_offset(self, offset: float):
        """Update synchronized mesh clock offset."""
        with self.lock:
            self.clock_offset = offset

    def get_current_slot(self, target_time: Optional[float] = None) -> int:
        """Computes monotonic hop slot number from synchronized mesh time."""
        now = (target_time if target_time is not None else time.time()) + self.clock_offset
        return int(now // self.hop_interval_sec)

    def is_rendezvous_slot(self, slot_num: Optional[int] = None) -> bool:
        """Determines if the given or current slot is a designated rendezvous slot."""
        if slot_num is None:
            slot_num = self.get_current_slot()
        return (slot_num % self.rendezvous_slot_interval) == 0

    def get_channel_for_slot(self, slot_num: int) -> Tuple[int, float]:
        """
        Derives channel index and frequency (MHz) for a given slot.
        Rendezvous slots always return channel 0 (rendezvous frequency).
        """
        with self.lock:
            if (slot_num % self.rendezvous_slot_interval) == 0:
                return 0, self.channels[0]

            # HMAC of slot number with mesh seed
            slot_bytes = struct.pack("!Q", slot_num)
            h = hmac.new(self.mesh_seed, slot_bytes, hashlib.sha256).digest()
            raw_val = int.from_bytes(h[:4], "big")

            available_indices = [
                i for i in range(len(self.channels))
                if i not in self.blacklisted_channels
            ]
            if not available_indices:
                # Fallback to all channels if all blacklisted
                available_indices = list(range(len(self.channels)))

            chosen_idx = available_indices[raw_val % len(available_indices)]
            return chosen_idx, self.channels[chosen_idx]

    def get_current_channel(self, target_time: Optional[float] = None) -> Tuple[int, float]:
        """Returns (channel_idx, frequency_mhz) for current synchronized time."""
        slot = self.get_current_slot(target_time)
        return self.get_channel_for_slot(slot)

    def get_adjacent_channels(self, target_time: Optional[float] = None) -> List[Tuple[int, float]]:
        """
        Returns channels for [slot - 1, slot, slot + 1] to allow receivers
        to tolerate slight clock jitter across hop window boundaries.
        """
        slot = self.get_current_slot(target_time)
        return [
            self.get_channel_for_slot(slot - 1),
            self.get_channel_for_slot(slot),
            self.get_channel_for_slot(slot + 1)
        ]

    def record_channel_result(self, channel_idx: int, success: bool, snr: float = 0.0):
        """Update link metrics for channel; automatically blacklists chronically jammed channels."""
        with self.lock:
            if channel_idx not in self.channel_metrics:
                return
            m = self.channel_metrics[channel_idx]
            if success:
                m["successes"] += 1
            else:
                m["failures"] += 1

            total = m["successes"] + m["failures"]
            if total >= 5 and (m["failures"] / total) >= 0.8:
                # Over 80% failure rate over 5+ attempts: mark as jammed/blacklisted
                if channel_idx != 0:  # Never blacklist rendezvous channel
                    self.blacklisted_channels.add(channel_idx)
                    print(f"[FHSS] Channel {channel_idx} ({self.channels[channel_idx]} MHz) blacklisted due to persistent RF interference")

    def unblacklist_channel(self, channel_idx: int):
        with self.lock:
            self.blacklisted_channels.discard(channel_idx)
            if channel_idx in self.channel_metrics:
                self.channel_metrics[channel_idx]["successes"] = 0
                self.channel_metrics[channel_idx]["failures"] = 0
