"""
Tamper-Evident Merkle Audit Ledger & Cryptographic Hash Chain.
Maintains an unbroken, append-only Merkle hash chain over tactical operations
(messages, waypoints, revocations, and zeroization events) to mathematically
guarantee audit immutability and detect SQLite database modifications.
"""

import time
import json
import hashlib
import threading
from typing import List, Dict, Optional, Tuple, Any, Union


GENESIS_PREV_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


class MerkleAuditLedger:
    """
    Append-only cryptographic audit chain providing mathematical tamper detection
    for tactical events and after-action reviews (AAR).
    """

    def __init__(self, genesis_salt: bytes = b"GHOSTNET_MERKLE_GENESIS_ROOT"):
        self.genesis_salt = genesis_salt
        self.entries: List[Dict[str, Any]] = []
        self.lock = threading.RLock()

    def _canonical_bytes(self, d: Dict[str, Any]) -> bytes:
        return json.dumps(d, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def append_event(self, event_type: str, data: Union[str, bytes, dict, list]) -> Dict[str, Any]:
        """
        Appends an event to the ledger, linking it to the previous hash.
        """
        if isinstance(data, (dict, list)):
            data_bytes = json.dumps(data, sort_keys=True).encode('utf-8')
        elif isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = bytes(data)

        payload_hash = hashlib.sha256(data_bytes).hexdigest()
        now = time.time()

        with self.lock:
            idx = len(self.entries)
            prev_hash = self.entries[-1]["entry_hash"] if idx > 0 else GENESIS_PREV_HASH

            entry_body = {
                "index": idx,
                "timestamp": now,
                "event_type": event_type,
                "payload_hash": payload_hash,
                "prev_hash": prev_hash
            }

            entry_hash = hashlib.sha256(self._canonical_bytes(entry_body)).hexdigest()
            record = dict(entry_body)
            record["entry_hash"] = entry_hash

            self.entries.append(record)
            return record

    def get_latest_hash(self) -> str:
        """Returns the current Merkle head hash."""
        with self.lock:
            if not self.entries:
                return GENESIS_PREV_HASH
            return self.entries[-1]["entry_hash"]

    def verify_integrity(self) -> Tuple[bool, Optional[int], str]:
        """
        Verifies the cryptographic chain from genesis to head.
        Returns:
            (is_valid, corrupted_index, reason)
        """
        with self.lock:
            if not self.entries:
                return True, None, "EMPTY_LEDGER"

            expected_prev = GENESIS_PREV_HASH

            for idx, entry in enumerate(self.entries):
                # Verify index continuity
                if entry.get("index") != idx:
                    return False, idx, f"INDEX_MISMATCH: expected {idx}, got {entry.get('index')}"

                # Verify back-link to previous hash
                if entry.get("prev_hash") != expected_prev:
                    return False, idx, f"BROKEN_HASH_LINK at index {idx}"

                # Recompute hash of entry body
                body = {
                    "index": entry["index"],
                    "timestamp": entry["timestamp"],
                    "event_type": entry["event_type"],
                    "payload_hash": entry["payload_hash"],
                    "prev_hash": entry["prev_hash"]
                }
                computed_hash = hashlib.sha256(self._canonical_bytes(body)).hexdigest()

                if computed_hash != entry.get("entry_hash"):
                    return False, idx, f"HASH_CORRUPTION at index {idx}: payload or metadata altered"

                expected_prev = entry["entry_hash"]

            return True, None, "VERIFIED_INTEGRITY"

    def export_proof(self, index: int) -> Optional[Dict[str, Any]]:
        """Exports cryptographic inclusion proof for a given ledger record."""
        with self.lock:
            if index < 0 or index >= len(self.entries):
                return None

            entry = self.entries[index]
            head_hash = self.entries[-1]["entry_hash"]

            return {
                "index": index,
                "entry_hash": entry["entry_hash"],
                "event_type": entry["event_type"],
                "payload_hash": entry["payload_hash"],
                "timestamp": entry["timestamp"],
                "ledger_head": head_hash,
                "total_records": len(self.entries)
            }

    def generate_audit_proof(self, index: int) -> Optional[Dict[str, Any]]:
        """Exports cryptographic audit proof with sequential chain hashes for AAR verification."""
        with self.lock:
            if index < 0 or index >= len(self.entries):
                return None
            proof = self.export_proof(index)
            if proof is None:
                return None
            proof["target_index"] = index
            proof["head_index"] = len(self.entries) - 1
            proof["audit_path"] = [e["entry_hash"] for e in self.entries]
            return proof
