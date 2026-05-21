import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple


class AuthenticationManager:

    def __init__(self, storage_dir: str = "."):
        self.storage_dir = storage_dir
        self.auth_file = os.path.join(storage_dir, ".auth_secrets")
        self.master_pin_hash = None
        self.duress_pin_hash = None
        self._load_pin_hashes()

    def _load_pin_hashes(self):
        if os.path.exists(self.auth_file):
            try:
                with open(self.auth_file, 'rb') as f:
                    data = f.read()
                    if len(data) >= 64:
                        self.master_pin_hash = data[:32]
                        self.duress_pin_hash = data[32:64]
            except Exception as e:
                print(f"[AuthenticationManager] Error loading PIN hashes: {e}")

    def _save_pin_hashes(self):
        try:
            os.makedirs(self.storage_dir, exist_ok=True)
            with open(self.auth_file, 'wb') as f:
                f.write(self.master_pin_hash + self.duress_pin_hash)
            os.chmod(self.auth_file, 0o600)
            print("[AuthenticationManager] PIN hashes saved securely")
        except Exception as e:
            print(f"[AuthenticationManager] Error saving PIN hashes: {e}")

    def _hash_pin(self, pin: str) -> bytes:
        salt = b'ghostnet_pin_salt_v1'
        return hashlib.pbkdf2_hmac(
            'sha256',
            pin.encode('utf-8'),
            salt,
            65536,
            dklen=32
        )

    def are_pins_initialized(self) -> bool:
        return self.master_pin_hash is not None and self.duress_pin_hash is not None

    def initialize_pins(self, master_pin: str, duress_pin: str) -> bool:
        if self.are_pins_initialized():
            print("[AuthenticationManager] PINs already initialized")
            return False

        if len(master_pin) < 4 or len(duress_pin) < 4:
            print("[AuthenticationManager] PINs must be at least 4 characters")
            return False

        try:
            self.master_pin_hash = self._hash_pin(master_pin)
            self.duress_pin_hash = self._hash_pin(duress_pin)
            self._save_pin_hashes()
            return True
        except Exception as e:
            print(f"[AuthenticationManager] Error initializing PINs: {e}")
            self.master_pin_hash = None
            self.duress_pin_hash = None
            return False

    def verify_master_pin(self, pin: str) -> bool:
        if self.master_pin_hash is None:
            return False

        try:
            pin_hash = self._hash_pin(pin)
            return pin_hash == self.master_pin_hash
        except Exception as e:
            print(f"[AuthenticationManager] Error verifying master PIN: {e}")
            return False

    def verify_duress_pin(self, pin: str) -> bool:
        if self.duress_pin_hash is None:
            return False

        try:
            pin_hash = self._hash_pin(pin)
            return pin_hash == self.duress_pin_hash
        except Exception as e:
            print(f"[AuthenticationManager] Error verifying duress PIN: {e}")
            return False

    def identify_pin(self, pin: str) -> Optional[str]:
        if self.verify_master_pin(pin):
            return "master"
        elif self.verify_duress_pin(pin):
            return "duress"
        return None
