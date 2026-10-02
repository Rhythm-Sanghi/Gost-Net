"""
Gost-Net - Anti-Replay Sliding Window & Cryptographic Sequence Vector Engine
Phase 15 Subsystem: High-performance, denial-of-service resilient anti-replay verification
tailored for out-of-order, multi-path, delay-tolerant mesh packets (RFC 4303 / RFC 6479 inspired).
Employs a configurable bitmask sliding window (default 128 or 256 bits) with per-peer epoch
isolation to accept legitimate out-of-order arrivals while rejecting replays and aged packets.
"""

from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class AntiReplayStats:
    total_packets_checked: int = 0
    valid_in_order: int = 0
    valid_out_of_order: int = 0
    replays_rejected: int = 0
    aged_expired_rejected: int = 0
    epoch_mismatches: int = 0


class SlidingWindow:
    """
    Sliding window bitmask for anti-replay verification against sequence numbers.
    Window size W determines maximum allowable out-of-order delay (e.g. 128 or 256 packets).
    """

    def __init__(self, window_size: int = 128):
        if window_size <= 0 or (window_size & (window_size - 1)) != 0:
            # Enforce power of 2 for clean bit operations, default 128
            window_size = 128
        self.window_size = window_size
        self.max_seq: int = 0
        self.bitmap: int = 0  # integer bitmask representing window_size bits
        self.initialized: bool = False

    def check_and_update(self, seq_num: int) -> Tuple[bool, str]:
        """
        Validates whether seq_num is acceptable and updates the sliding window state.
        Returns:
            (is_valid: bool, reason: str)
            reason in {"OK_IN_ORDER", "OK_OUT_OF_ORDER", "REPLAY_DUPLICATE", "TOO_OLD"}
        """
        if seq_num < 0:
            return (False, "TOO_OLD")

        if not self.initialized:
            self.max_seq = seq_num
            self.bitmap = 1
            self.initialized = True
            return (True, "OK_IN_ORDER")

        diff = seq_num - self.max_seq

        if diff > 0:
            # Case 1: Newer packet advancing the window
            if diff >= self.window_size:
                # Advanced by more than full window size; reset bitmap
                self.bitmap = 1
            else:
                self.bitmap = ((self.bitmap << diff) | 1) & ((1 << self.window_size) - 1)
            self.max_seq = seq_num
            return (True, "OK_IN_ORDER")

        diff = -diff  # distance behind max_seq

        if diff >= self.window_size:
            # Case 2: Packet is too old (outside window horizon)
            return (False, "TOO_OLD")

        # Case 3: Packet is within sliding window
        mask = 1 << diff
        if self.bitmap & mask:
            # Bit is already set -> Replay attack / duplicate packet
            return (False, "REPLAY_DUPLICATE")

        # Bit is not set -> Valid out-of-order packet
        self.bitmap |= mask
        return (True, "OK_OUT_OF_ORDER")

    def is_seen(self, seq_num: int) -> bool:
        """Query if a sequence number is marked seen without mutating state."""
        if not self.initialized:
            return False
        diff = self.max_seq - seq_num
        if diff < 0:
            return False
        if diff >= self.window_size:
            return True  # Past horizon, treated as seen/expired
        return bool(self.bitmap & (1 << diff))


class AntiReplayManager:
    """
    Manages per-peer sliding windows and epoch tracking across the mesh network.
    """

    def __init__(self, window_size: int = 128):
        self.window_size = window_size
        self.peer_windows: Dict[str, SlidingWindow] = {}
        self.peer_epochs: Dict[str, int] = {}
        self.stats = AntiReplayStats()

    def verify_and_accept(self, peer_id: str, seq_num: int, epoch: int = 1) -> Tuple[bool, str]:
        """
        Validates an incoming packet's sequence number and epoch from a given peer.
        Enforces epoch isolation to prevent replays across key rotation or system restart.
        """
        self.stats.total_packets_checked += 1

        # Check or initialize peer epoch
        if peer_id not in self.peer_epochs:
            self.peer_epochs[peer_id] = epoch
            self.peer_windows[peer_id] = SlidingWindow(self.window_size)
        elif epoch > self.peer_epochs[peer_id]:
            # Peer advanced to a newer epoch (e.g. session rekey or rollover)
            self.peer_epochs[peer_id] = epoch
            self.peer_windows[peer_id] = SlidingWindow(self.window_size)
        elif epoch < self.peer_epochs[peer_id]:
            # Stale epoch from older session
            self.stats.epoch_mismatches += 1
            return (False, "STALE_EPOCH")

        window = self.peer_windows[peer_id]
        is_valid, reason = window.check_and_update(seq_num)

        if reason == "OK_IN_ORDER":
            self.stats.valid_in_order += 1
        elif reason == "OK_OUT_OF_ORDER":
            self.stats.valid_out_of_order += 1
        elif reason == "REPLAY_DUPLICATE":
            self.stats.replays_rejected += 1
        elif reason == "TOO_OLD":
            self.stats.aged_expired_rejected += 1

        return (is_valid, reason)

    def get_peer_state(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Returns diagnostic telemetry for a specific peer's anti-replay window."""
        if peer_id not in self.peer_windows:
            return None
        win = self.peer_windows[peer_id]
        return {
            "peer_id": peer_id,
            "epoch": self.peer_epochs.get(peer_id, 1),
            "max_seq": win.max_seq,
            "window_size": win.window_size,
            "initialized": win.initialized
        }

    def reset_peer(self, peer_id: str):
        """Resets sliding window state for a peer (e.g. upon fresh handshake)."""
        self.peer_windows.pop(peer_id, None)
        self.peer_epochs.pop(peer_id, None)
