"""
Synchronized Low-Power Mesh Duty Cycling & Slotted Rendezvous Engine.
Coordinates slotted sleep/wake cycles to reduce radio transceiver power consumption by 5x-10x
while preserving mesh routing integrity through queued packet spooling.
"""

import enum
import time
import threading
from typing import List, Dict, Optional, Callable, Any


class PowerProfile(enum.Enum):
    CONTINUOUS = "continuous"            # 100% active, 0s sleep (Base Stations / Line Power)
    STANDARD_SAVER = "standard"          # 5s wake window every 30s (Default Handheld)
    AGGRESSIVE_SAVER = "aggressive"      # 2s wake window every 60s (Solar / Relay Nodes)
    ULTRA_LOW_POWER = "ultra_low_power"  # 1s wake window every 120s (Austere Emergency)


PROFILE_CONFIGS = {
    PowerProfile.CONTINUOUS: {"wake_duration": 0.0, "cycle_period": 0.0, "duty_ratio": 1.0},
    PowerProfile.STANDARD_SAVER: {"wake_duration": 5.0, "cycle_period": 30.0, "duty_ratio": 5.0 / 30.0},
    PowerProfile.AGGRESSIVE_SAVER: {"wake_duration": 2.0, "cycle_period": 60.0, "duty_ratio": 2.0 / 60.0},
    PowerProfile.ULTRA_LOW_POWER: {"wake_duration": 1.0, "cycle_period": 120.0, "duty_ratio": 1.0 / 120.0},
}


class DutyCycleManager:
    """
    Manages low-power slotted sleep/wake rendezvous for Gost-Net nodes.
    Buffers outgoing outbound transmissions while asleep and automatically flushes
    transmission queues upon window rendezvous.
    """

    def __init__(
        self,
        profile: PowerProfile = PowerProfile.STANDARD_SAVER,
        clock_offset: float = 0.0,
        max_spool_size: int = 100
    ):
        self.profile = profile
        self.clock_offset = clock_offset
        self.max_spool_size = max_spool_size

        self.wake_duration = PROFILE_CONFIGS[profile]["wake_duration"]
        self.cycle_period = PROFILE_CONFIGS[profile]["cycle_period"]

        self.spool_queue: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

        self.on_state_change: Optional[Callable[[bool], None]] = None
        self.on_spool_flush: Optional[Callable[[List[Dict[str, Any]]], None]] = None

        self._force_awake = False
        self._last_state: Optional[bool] = None  # True = Awake, False = Sleep

    def set_profile(self, profile: PowerProfile):
        """Update duty cycling power profile."""
        with self.lock:
            self.profile = profile
            self.wake_duration = PROFILE_CONFIGS[profile]["wake_duration"]
            self.cycle_period = PROFILE_CONFIGS[profile]["cycle_period"]

    def set_clock_offset(self, offset: float):
        """Update mesh time synchronization offset."""
        with self.lock:
            self.clock_offset = offset

    def is_awake(self, target_time: Optional[float] = None) -> bool:
        """
        Check if the node is currently in an active wake window.
        Uses synchronized mesh clock if offset is provided.
        """
        if self._force_awake or self.profile == PowerProfile.CONTINUOUS:
            return True

        if target_time is None:
            target_time = time.time()

        synced_time = target_time + self.clock_offset
        if self.cycle_period <= 0:
            return True

        cycle_pos = synced_time % self.cycle_period
        return cycle_pos < self.wake_duration

    def time_until_next_wake(self, target_time: Optional[float] = None) -> float:
        """
        Returns seconds remaining until the start of the next wake window.
        Returns 0.0 if already awake.
        """
        if self._force_awake or self.profile == PowerProfile.CONTINUOUS:
            return 0.0

        if target_time is None:
            target_time = time.time()

        synced_time = target_time + self.clock_offset
        if self.cycle_period <= 0:
            return 0.0

        cycle_pos = synced_time % self.cycle_period
        if cycle_pos < self.wake_duration:
            return 0.0
        return self.cycle_period - cycle_pos

    def queue_or_send(
        self,
        packet: bytes,
        target_peer: str,
        priority: int = 1,
        sender_func: Optional[Callable[[bytes, str], bool]] = None
    ) -> bool:
        """
        If currently awake, transmits immediately via sender_func.
        If sleeping, spools the packet into the transmission queue for next window flush,
        unless priority is critical (priority >= 9), which triggers emergency wake.
        """
        with self.lock:
            # Critical priority messages force immediate emergency wake
            if priority >= 9:
                self._force_awake = True
                if sender_func:
                    return sender_func(packet, target_peer)
                return True

            if self.is_awake():
                if sender_func:
                    return sender_func(packet, target_peer)
                return True

            # Node is sleeping, spool packet
            if len(self.spool_queue) >= self.max_spool_size:
                # Drop oldest lower-priority packet
                self.spool_queue.pop(0)

            self.spool_queue.append({
                "packet": packet,
                "target_peer": target_peer,
                "priority": priority,
                "enqueued_at": time.time(),
                "sender_func": sender_func
            })
            return True

    def flush_spool(self) -> int:
        """
        Flushes all spooled transmissions. Returns count of transmitted packets.
        """
        with self.lock:
            packets_to_send = list(self.spool_queue)
            self.spool_queue.clear()

        if not packets_to_send:
            return 0

        # Sort by priority descending
        packets_to_send.sort(key=lambda x: x["priority"], reverse=True)

        flushed_count = 0
        for item in packets_to_send:
            sender = item.get("sender_func")
            if sender:
                try:
                    if sender(item["packet"], item["target_peer"]):
                        flushed_count += 1
                except Exception as e:
                    print(f"[DutyCycleManager] Failed to flush queued packet to {item['target_peer']}: {e}")
            else:
                flushed_count += 1

        if self.on_spool_flush:
            self.on_spool_flush(packets_to_send)

        return flushed_count

    def force_wake(self, duration: float = 10.0):
        """Temporarily forces the transceiver awake for emergency activity."""
        self._force_awake = True
        self.flush_spool()
        # Reset force awake after duration
        if duration > 0:
            def _reset():
                time.sleep(duration)
                self._force_awake = False
            threading.Thread(target=_reset, daemon=True).start()

    def start(self):
        """Starts background duty cycle monitor thread."""
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self._thread = threading.Thread(target=self._run_loop, name="DutyCycleMonitor", daemon=True)
            self._thread.start()

    def stop(self):
        """Stops background monitor thread."""
        with self.lock:
            self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run_loop(self):
        while self.is_running:
            awake = self.is_awake()
            if awake != self._last_state:
                self._last_state = awake
                if awake:
                    # Just woke up: flush queued transmissions
                    self.flush_spool()
                if self.on_state_change:
                    try:
                        self.on_state_change(awake)
                    except Exception as e:
                        print(f"[DutyCycleManager] State change callback error: {e}")

            time.sleep(0.2)
