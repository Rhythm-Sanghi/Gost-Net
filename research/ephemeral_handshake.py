"""
Rotating Ephemeral Beacon Anonymization & Anti-RF Tracking Engine.
Replaces static call signs and peer identifiers in discovery beacons with
time-windowed pseudo-random tokens derived via HMAC from a shared group secret,
preventing SIGINT emitter correlation while allowing authenticated peers to de-anonymize.
"""

import time
import struct
import hmac
import hashlib
from typing import Dict, List, Optional, Set


class EphemeralBeaconManager:
    """
    Manages generation and resolution of rotating, un-correlatable beacon identifiers.
    """

    def __init__(
        self,
        group_secret: bytes = b"GHOSTNET_ANONYMIZED_BEACON_KEY",
        rotation_interval_sec: float = 600.0,
        clock_offset: float = 0.0
    ):
        self.group_secret = group_secret
        self.rotation_interval_sec = rotation_interval_sec
        self.clock_offset = clock_offset

    def set_clock_offset(self, offset: float):
        self.clock_offset = offset

    def _get_epoch_slot(self, target_time: Optional[float] = None) -> int:
        now = (target_time if target_time is not None else time.time()) + self.clock_offset
        return int(now // self.rotation_interval_sec)

    def generate_ephemeral_token(self, real_peer_id: str, target_time: Optional[float] = None) -> str:
        """
        Generates an ephemeral pseudonym token for real_peer_id for the current rotation window.
        """
        slot = self._get_epoch_slot(target_time)
        slot_bytes = struct.pack("!q", slot)
        h = hmac.new(self.group_secret, slot_bytes + real_peer_id.encode('utf-8'), hashlib.sha256)
        return h.hexdigest()[:24]

    def resolve_ephemeral_token(
        self,
        token: str,
        known_peer_ids: List[str],
        target_time: Optional[float] = None
    ) -> Optional[str]:
        """
        Resolves an incoming ephemeral token against a list of known team member peer IDs.
        Checks current slot as well as adjacent slots (slot - 1, slot + 1) to tolerate clock skew.
        Returns the matching real_peer_id, or None if unknown/unauthenticated.
        """
        center_slot = self._get_epoch_slot(target_time)
        candidate_slots = [center_slot, center_slot - 1, center_slot + 1]

        for pid in known_peer_ids:
            pid_bytes = pid.encode('utf-8')
            for slot in candidate_slots:
                slot_bytes = struct.pack("!q", slot)
                candidate_token = hmac.new(self.group_secret, slot_bytes + pid_bytes, hashlib.sha256).hexdigest()[:24]
                if hmac.compare_digest(candidate_token, token):
                    return pid

        return None
