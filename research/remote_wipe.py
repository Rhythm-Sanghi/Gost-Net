"""
Over-The-Air (OTA) Cryptographic Detachment Zeroization Engine.
Generates, validates, and executes root-signed emergency burn tokens to remotely
quarantine or zeroize compromised nodes and unattended mesh repeaters.
"""

import os
import time
import json
import base64
from typing import Dict, Optional, Tuple, Any, Callable
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from src.security import shred_file


class RemoteWipeManager:
    """
    Manages generation, signature verification, and execution of Over-The-Air (OTA)
    emergency zeroization burn tokens.
    """

    def __init__(self, commander_public_key_bytes: Optional[bytes] = None, max_token_age: float = 300.0):
        self.commander_public_key_bytes = commander_public_key_bytes
        self.max_token_age = max_token_age
        self.seen_burn_nonces: Dict[str, float] = {}

    @staticmethod
    def generate_commander_keypair() -> Tuple[ed25519.Ed25519PrivateKey, bytes]:
        """
        Generate an Ed25519 commander keypair. Returns (private_key, public_key_bytes).
        """
        priv = ed25519.Ed25519PrivateKey.generate()
        pub_bytes = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return priv, pub_bytes

    def create_burn_token(
        self,
        commander_private_key: ed25519.Ed25519PrivateKey,
        commander_id: str,
        target_peer_id: str = "ALL",
        reason: str = "COMPROMISE_SUSPECTED"
    ) -> Dict[str, Any]:
        """
        Constructs and digitally signs an emergency burn token.
        """
        payload = {
            "action": "OTA_ZEROIZE",
            "commander_id": commander_id,
            "target_peer_id": target_peer_id,
            "reason": reason,
            "timestamp_ms": int(time.time() * 1000),
            "nonce": os.urandom(16).hex()
        }

        # Canonical bytes for signing
        canonical_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        signature = commander_private_key.sign(canonical_bytes)

        return {
            "payload": payload,
            "signature": base64.b64encode(signature).decode('utf-8')
        }

    def verify_burn_token(
        self,
        token: Dict[str, Any],
        local_peer_id: str,
        trusted_commander_pub_bytes: Optional[bytes] = None
    ) -> Tuple[bool, str]:
        """
        Verifies the authenticity, freshness, and recipient targeting of an OTA burn token.
        Returns (is_valid, reason).
        """
        pub_bytes = trusted_commander_pub_bytes or self.commander_public_key_bytes
        if not pub_bytes:
            return False, "NO_TRUSTED_COMMANDER_KEY"

        if "payload" not in token or "signature" not in token:
            return False, "MALFORMED_TOKEN"

        payload = token["payload"]
        sig_b64 = token["signature"]

        # Check target targeting
        target = payload.get("target_peer_id")
        if target != "ALL" and target != local_peer_id:
            return False, f"TARGET_MISMATCH: targeted to {target}, local is {local_peer_id}"

        # Check freshness and replay protection
        now_ms = time.time() * 1000
        token_ms = payload.get("timestamp_ms", 0)
        age_sec = (now_ms - token_ms) / 1000.0

        if age_sec > self.max_token_age:
            return False, f"TOKEN_EXPIRED: age {age_sec:.1f}s exceeds max {self.max_token_age}s"

        if age_sec < -60.0:
            return False, "TOKEN_FUTURE_TIMESTAMP"

        nonce = payload.get("nonce", "")
        if not nonce:
            return False, "MISSING_NONCE"

        # Check nonce replay
        now = time.time()
        # Clean expired nonces
        expired = [n for n, t in self.seen_burn_nonces.items() if now - t > self.max_token_age]
        for n in expired:
            del self.seen_burn_nonces[n]

        if nonce in self.seen_burn_nonces:
            return False, "NONCE_REPLAYED"

        # Verify Ed25519 digital signature
        try:
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = base64.b64decode(sig_b64)
            canonical_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
            pub_key.verify(sig_bytes, canonical_bytes)
        except Exception as e:
            return False, f"SIGNATURE_INVALID: {e}"

        # Nonce valid, register it
        self.seen_burn_nonces[nonce] = now
        return True, "VERIFIED"

    def execute_detachment_zeroize(
        self,
        db_path: Optional[str] = None,
        key_zeroize_callback: Optional[Callable[[], None]] = None,
        extra_files_to_shred: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Executes immediate detachment zeroization:
        - Memory key zeroization via key_zeroize_callback
        - Logical multi-pass overwrite and deletion of SQLite database, WAL files, and keys.
        NOTE: Logical file overwrite does not guarantee physical sanitization on wear-levelled
        flash storage (SSDs, eMMC, SD cards).
        """
        results = {
            "memory_zeroized": False,
            "files_shredded": [],
            "status": "COMPLETED"
        }

        # 1. Zeroize in-memory cryptographic state
        if key_zeroize_callback:
            try:
                key_zeroize_callback()
                results["memory_zeroized"] = True
            except Exception as e:
                print(f"[RemoteWipe] Key zeroization callback error: {e}")

        # 2. Shred SQLite database and associated journal/WAL files
        if db_path and os.path.exists(db_path):
            candidates = [db_path, f"{db_path}-wal", f"{db_path}-shm", f"{db_path}-journal"]
            for fpath in candidates:
                if os.path.exists(fpath):
                    shred_file(fpath)
                    results["files_shredded"].append(fpath)

        # 3. Shred any additional credential or key files
        if extra_files_to_shred:
            for fpath in extra_files_to_shred:
                if fpath and os.path.exists(fpath):
                    shred_file(fpath)
                    results["files_shredded"].append(fpath)

        print("[RemoteWipe] Detachment zeroization complete. Attempted logical overwrite of persistent credentials.")
        return results
