"""
Ephemeral Pre-Shared One-Time Pad (OTP) Keystream Vault.
Provides information-theoretically secure, quantum-resistant emergency messaging
for strategic command traffic. Enforces monotonic offset progression, strict
zero pad-reuse rejection, and immediate overwriting of consumed pad segments.
"""

import os
import time
import base64
import hmac
import hashlib
import threading
from typing import Optional, Dict, Any, Tuple


class OTPStreamVault:
    """
    Manages pre-shared one-time pad streams with strictly enforced monotonic offsets
    and zero pad reuse for quantum-resilient communications.
    """

    def __init__(self, pad_file_path: str, initial_pad_bytes: Optional[bytes] = None):
        self.pad_file_path = pad_file_path
        self.lock = threading.Lock()

        # Initialize pad file if supplied
        if initial_pad_bytes:
            with open(self.pad_file_path, "wb") as f:
                f.write(initial_pad_bytes)

        self.send_offset = 0
        self.recv_offset = 0

    @staticmethod
    def generate_random_pad(size_bytes: int = 65536) -> bytes:
        """Generate cryptographically secure random bytes for a shared pad."""
        return os.urandom(size_bytes)

    def remaining_pad_bytes(self) -> int:
        """Returns unconsumed pad bytes remaining in the vault."""
        with self.lock:
            if not os.path.exists(self.pad_file_path):
                return 0
            size = os.path.getsize(self.pad_file_path)
            return max(0, size - max(self.send_offset, self.recv_offset))

    def encrypt_otp(self, plaintext: bytes) -> Dict[str, Any]:
        """
        Encrypts plaintext using next unconsumed segment of the one-time pad.
        Immediately overwrites the consumed pad segment on disk to prevent reuse.
        """
        pt_len = len(plaintext)
        if pt_len == 0:
            raise ValueError("Plaintext cannot be empty")

        with self.lock:
            if not os.path.exists(self.pad_file_path):
                raise RuntimeError("OTP pad file does not exist")

            with open(self.pad_file_path, "r+b") as f:
                f.seek(self.send_offset)
                pad_segment = f.read(pt_len)
                if len(pad_segment) < pt_len:
                    raise RuntimeError("OTP pad exhausted: insufficient keystream remaining")

                # Information-theoretic encryption: P ^ K
                ciphertext = bytes(p ^ k for p, k in zip(plaintext, pad_segment))

                # Immediate secure overwrite of consumed segment in vault
                f.seek(self.send_offset)
                f.write(b'\x00' * pt_len)
                f.flush()
                os.fsync(f.fileno())

                used_offset = self.send_offset
                self.send_offset += pt_len

            # Authentication tag over (offset + ciphertext)
            tag = hmac.new(
                hashlib.sha256(pad_segment).digest(),
                used_offset.to_bytes(8, 'big') + ciphertext,
                hashlib.sha256
            ).hexdigest()

            return {
                "type": "OTP_FRAME",
                "pad_offset": used_offset,
                "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
                "tag": tag,
                "length": pt_len,
                "timestamp": time.time()
            }

    def decrypt_otp(self, otp_frame: Dict[str, Any], sender_pad_file_path: Optional[str] = None) -> Optional[bytes]:
        """
        Decrypts an OTP frame using recipient's corresponding pad stream.
        Enforces monotonic offset advancement and immediately zeros consumed pad data.
        """
        if not isinstance(otp_frame, dict) or otp_frame.get("type") != "OTP_FRAME":
            return None

        pad_path = sender_pad_file_path or self.pad_file_path
        offset = otp_frame.get("pad_offset", 0)
        ct_b64 = otp_frame.get("ciphertext", "")
        expected_tag = otp_frame.get("tag", "")
        length = otp_frame.get("length", 0)

        try:
            ciphertext = base64.b64decode(ct_b64)
        except Exception:
            return None

        if len(ciphertext) != length:
            return None

        with self.lock:
            # Replay and out-of-order reuse rejection
            if offset < self.recv_offset:
                print(f"[OTP] Rejected reused or out-of-sequence pad offset {offset} (current recv offset: {self.recv_offset})")
                return None

            if not os.path.exists(pad_path):
                return None

            with open(pad_path, "r+b") as f:
                f.seek(offset)
                pad_segment = f.read(length)
                if len(pad_segment) < length:
                    return None

                # Verify authentication tag
                computed_tag = hmac.new(
                    hashlib.sha256(pad_segment).digest(),
                    offset.to_bytes(8, 'big') + ciphertext,
                    hashlib.sha256
                ).hexdigest()

                if not hmac.compare_digest(computed_tag, expected_tag):
                    print("[OTP] Authentication tag mismatch on OTP frame")
                    return None

                # Decrypt: C ^ K
                plaintext = bytes(c ^ k for c, k in zip(ciphertext, pad_segment))

                # Immediately zeroize consumed segment
                f.seek(offset)
                f.write(b'\x00' * length)
                f.flush()
                os.fsync(f.fileno())

                self.recv_offset = offset + length

            return plaintext
