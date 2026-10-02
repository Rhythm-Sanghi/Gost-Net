import hashlib
import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)



class AuthenticationManager:

    def __init__(self, storage_dir: str = ".", auto_init_defaults: Optional[bool] = None):
        self.storage_dir = storage_dir
        self.auth_file = os.path.join(storage_dir, ".auth_secrets")
        self.decoy_flag_file = os.path.join(storage_dir, ".decoy_mode")
        self.failed_attempts_file = os.path.join(storage_dir, ".failed_attempts")
        self.dms_file = os.path.join(storage_dir, ".dead_man_switch")
        self.max_failed_attempts = 5
        self.master_pin_hash = None
        self.duress_pin_hash = None
        self.pin_salt = None
        self.kdf_version = 1
        self.master_iterations = 65536
        self.duress_iterations = 65536
        self._load_pin_hashes()
        
        # Test fixture compatibility: auto-initialize known PINs ONLY when explicitly
        # running in declared test mode via the GOSTNET_TEST_MODE env var.
        if auto_init_defaults is None:
            auto_init_defaults = (os.environ.get("GOSTNET_TEST_MODE") == "1")

        self.auto_init_defaults = bool(auto_init_defaults)

        if not self.are_pins_initialized() and self.auto_init_defaults:
            self.initialize_pins("1234", "9999")

    @staticmethod
    def validate_pin_strength(pin: str, allow_test_pins: Optional[bool] = None) -> Tuple[bool, str]:
        """
        Validates PIN strength against low-entropy and common trivial patterns.
        Requires minimum 6 characters (or 4 when test mode is declared).
        Rejects all-identical, monotonic sequential, and simple repeating sequences.
        """
        if not pin:
            return False, "PIN cannot be empty"
        if allow_test_pins is None:
            is_test_mode = (os.environ.get("GOSTNET_TEST_MODE") == "1")
        else:
            is_test_mode = allow_test_pins

        min_len = 4 if is_test_mode else 6
        if len(pin) < min_len:
            return False, f"PIN must be at least {min_len} characters long"

        # Allow test fixture PINs in test mode
        if is_test_mode and len(pin) < 6:
            return True, ""

        # Reject single character repeats (e.g. "000000", "111111", "aaaaaa")
        if len(set(pin)) == 1:
            return False, "PIN cannot consist of a single repeated character"

        # Reject monotonic sequential sequences (e.g. "123456", "654321", "012345")
        is_seq_asc = all(ord(pin[i+1]) - ord(pin[i]) == 1 for i in range(len(pin) - 1))
        is_seq_desc = all(ord(pin[i]) - ord(pin[i+1]) == 1 for i in range(len(pin) - 1))
        if is_seq_asc or is_seq_desc:
            return False, "PIN cannot be a sequential series"

        # Reject simple repetition patterns (e.g. "121212", "123123")
        half = len(pin) // 2
        if len(pin) % 2 == 0 and pin[:half] == pin[half:]:
            return False, "PIN cannot be a repeating pattern"
        third = len(pin) // 3
        if len(pin) % 3 == 0 and pin[:third] * 3 == pin:
            return False, "PIN cannot be a repeating pattern"

        return True, ""

    def is_decoy_mode_active(self) -> bool:
        return os.path.exists(self.decoy_flag_file)

    def activate_decoy_mode(self):
        try:
            os.makedirs(self.storage_dir, exist_ok=True)
            with open(self.decoy_flag_file, 'w') as f:
                f.write("active")
            try:
                os.chmod(self.decoy_flag_file, 0o600)
            except:
                pass
            print("[AuthenticationManager] Persistent decoy mode activated")
        except Exception as e:
            print(f"[AuthenticationManager] Error activating decoy mode: {e}")

    def deactivate_decoy_mode(self):
        """Allows recovery from decoy mode upon master PIN re-authentication."""
        try:
            if os.path.exists(self.decoy_flag_file):
                os.remove(self.decoy_flag_file)
            self.reset_failed_attempts()
            print("[AuthenticationManager] Persistent decoy mode deactivated")
        except Exception as e:
            print(f"[AuthenticationManager] Error deactivating decoy mode: {e}")

    def _load_pin_hashes(self):
        if os.path.exists(self.auth_file):
            try:
                with open(self.auth_file, 'rb') as f:
                    data = f.read()
                    if data.startswith(b'GNKDF2\x00') and len(data) == 95:
                        self.kdf_version = 2
                        m_iters = int.from_bytes(data[7:11], 'big')
                        d_iters = int.from_bytes(data[11:15], 'big')
                        self.master_iterations = m_iters if m_iters >= 1000 else 200000
                        self.duress_iterations = d_iters if d_iters >= 1000 else 200000
                        self.pin_salt = data[15:31]
                        self.master_pin_hash = data[31:63]
                        self.duress_pin_hash = data[63:95]
                    elif len(data) == 80:
                        self.kdf_version = 1
                        self.master_iterations = 65536
                        self.duress_iterations = 65536
                        self.pin_salt = data[:16]
                        self.master_pin_hash = data[16:48]
                        self.duress_pin_hash = data[48:80]
                    elif len(data) == 64:
                        self.kdf_version = 1
                        self.master_iterations = 65536
                        self.duress_iterations = 65536
                        self.pin_salt = b'ghostnet_pin_salt_v1'[:16]
                        self.master_pin_hash = data[:32]
                        self.duress_pin_hash = data[32:64]
            except Exception as e:
                print(f"[AuthenticationManager] Error loading PIN hashes: {e}")

    def _save_pin_hashes(self):
        try:
            os.makedirs(self.storage_dir, exist_ok=True)
            master_iters = getattr(self, 'master_iterations', 200000)
            duress_iters = getattr(self, 'duress_iterations', 200000)
            self.kdf_version = 2
            payload = (
                b'GNKDF2\x00' +
                master_iters.to_bytes(4, 'big') +
                duress_iters.to_bytes(4, 'big') +
                self.pin_salt +
                self.master_pin_hash +
                self.duress_pin_hash
            )
            with open(self.auth_file, 'wb') as f:
                f.write(payload)
            os.chmod(self.auth_file, 0o600)
            print("[AuthenticationManager] PIN hashes saved securely (v2 format)")
        except Exception as e:
            print(f"[AuthenticationManager] Error saving PIN hashes: {e}")

    def _hash_pin(self, pin: str, iterations: Optional[int] = None) -> bytes:
        salt = self.pin_salt if self.pin_salt else b'ghostnet_pin_salt_v1'
        iters = iterations if iterations is not None else getattr(self, 'master_iterations', 200000)
        if not isinstance(iters, int) or iters < 1000:
            iters = 200000
        return hashlib.pbkdf2_hmac(
            'sha256',
            pin.encode('utf-8'),
            salt,
            iters,
            dklen=32
        )

    def _migrate_to_kdf_v2(self, master_pin: str):
        """
        Transparently migrates legacy v1 vault to v2 metadata (200,000 PBKDF2 iterations)
        without invalidating the un-rehashed duress PIN hash.
        """
        try:
            self.master_iterations = 200000
            if not hasattr(self, 'duress_iterations') or self.duress_iterations is None:
                self.duress_iterations = 65536
            self.master_pin_hash = self._hash_pin(master_pin, iterations=self.master_iterations)
            self.kdf_version = 2
            self._save_pin_hashes()
            print("[AuthenticationManager] Transparently migrated vault PIN KDF to version 2 (200,000 iterations)")
        except Exception as e:
            print(f"[AuthenticationManager] Error migrating PIN KDF to v2: {e}")

    def are_pins_initialized(self) -> bool:
        return self.master_pin_hash is not None and self.duress_pin_hash is not None

    def is_configured(self) -> bool:
        return self.are_pins_initialized()

    def initialize_pins(self, master_pin: str, duress_pin: str) -> bool:
        if self.are_pins_initialized():
            print("[AuthenticationManager] PINs already initialized")
            return False

        allow_test = getattr(self, 'auto_init_defaults', False)
        valid_m, msg_m = self.validate_pin_strength(master_pin, allow_test_pins=allow_test)
        if not valid_m:
            print(f"[AuthenticationManager] Master PIN rejected: {msg_m}")
            return False

        valid_d, msg_d = self.validate_pin_strength(duress_pin, allow_test_pins=allow_test)
        if not valid_d:
            print(f"[AuthenticationManager] Duress PIN rejected: {msg_d}")
            return False

        if master_pin == duress_pin:
            print("[AuthenticationManager] Master PIN and Duress PIN cannot be identical")
            return False

        try:
            self.pin_salt = os.urandom(16)
            self.master_iterations = 200000
            self.duress_iterations = 200000
            self.kdf_version = 2
            self.master_pin_hash = self._hash_pin(master_pin, iterations=self.master_iterations)
            self.duress_pin_hash = self._hash_pin(duress_pin, iterations=self.duress_iterations)
            self._save_pin_hashes()
            return True
        except Exception as e:
            print(f"[AuthenticationManager] Error initializing PINs: {e}")
            self.master_pin_hash = None
            self.duress_pin_hash = None
            self.pin_salt = None
            return False

    def change_pins(self, old_pin: str, new_master: str, new_duress: str) -> Tuple[bool, str]:
        """
        Securely updates Master and Duress PINs, generating a new salt and 
        re-encrypting the persistent database key and signing key under the new derived KEK.
        """
        if not self.verify_master_pin(old_pin):
            return False, "Current Master PIN is incorrect"
            
        allow_test = getattr(self, 'auto_init_defaults', False)
        valid_m, msg_m = self.validate_pin_strength(new_master, allow_test_pins=allow_test)
        if not valid_m:
            return False, f"New Master PIN rejected: {msg_m}"

        valid_d, msg_d = self.validate_pin_strength(new_duress, allow_test_pins=allow_test)
        if not valid_d:
            return False, f"New Duress PIN rejected: {msg_d}"
            
        if new_master == new_duress:
            return False, "Master PIN and Duress PIN cannot be identical"
            
        try:
            import base64
            from cryptography.fernet import Fernet
            
            # Load DB salt and determine old iterations
            salt_path = os.path.join(self.storage_dir, ".db_salt")
            old_db_iters = 100000
            if os.path.exists(salt_path):
                with open(salt_path, 'rb') as f:
                    old_db_salt_raw = f.read()
                if old_db_salt_raw.startswith(b'GNDBS2\x00') and len(old_db_salt_raw) == 27:
                    old_iters_parsed = int.from_bytes(old_db_salt_raw[7:11], 'big')
                    old_db_iters = old_iters_parsed if old_iters_parsed >= 1000 else 200000
                    old_db_salt = old_db_salt_raw[11:27]
                else:
                    old_db_salt = old_db_salt_raw
            else:
                old_db_salt = b'default_ghostnet_db_salt_v1'
            
            # Derive KEK from old PIN
            old_kek_bytes = self._derive_kek(old_pin, old_db_salt, iterations=old_db_iters)
            old_kek = base64.urlsafe_b64encode(old_kek_bytes)
            cipher_old = Fernet(old_kek)
            
            # Decrypt existing DB key
            enc_key_path = os.path.join(self.storage_dir, "secret.key.enc")
            raw_db_key = None
            if os.path.exists(enc_key_path):
                with open(enc_key_path, 'rb') as f:
                    encrypted_db_key = f.read()
                raw_db_key = cipher_old.decrypt(encrypted_db_key)
                
            # Decrypt existing signing key
            enc_sig_path = os.path.join(self.storage_dir, "signing.key.enc")
            raw_sig_key = None
            if os.path.exists(enc_sig_path):
                with open(enc_sig_path, 'rb') as f:
                    encrypted_sig_key = f.read()
                raw_sig_key = cipher_old.decrypt(encrypted_sig_key)
            
            # Generate new salt and save updated hashes (updates .auth_secrets with v2 format)
            new_salt = os.urandom(16)
            self.pin_salt = new_salt
            self.master_iterations = 200000
            self.duress_iterations = 200000
            self.kdf_version = 2
            self.master_pin_hash = self._hash_pin(new_master, iterations=200000)
            self.duress_pin_hash = self._hash_pin(new_duress, iterations=200000)
            self._save_pin_hashes()
            
            # Generate new DB salt with v2 format (200,000 iterations)
            new_db_salt = os.urandom(16)
            new_db_iters = 200000
            with open(salt_path, 'wb') as f:
                f.write(b'GNDBS2\x00' + new_db_iters.to_bytes(4, 'big') + new_db_salt)
            try:
                os.chmod(salt_path, 0o600)
            except:
                pass

            # Derive KEK from new PIN
            new_kek_bytes = self._derive_kek(new_master, new_db_salt, iterations=new_db_iters)
            new_kek = base64.urlsafe_b64encode(new_kek_bytes)
            cipher_new = Fernet(new_kek)
            
            # Re-encrypt and write back DB key
            if raw_db_key is not None:
                new_encrypted_db = cipher_new.encrypt(raw_db_key)
                with open(enc_key_path, 'wb') as f:
                    f.write(new_encrypted_db)
                try:
                    os.chmod(enc_key_path, 0o600)
                except:
                    pass
                    
            # Re-encrypt and write back signing key
            if raw_sig_key is not None:
                new_encrypted_sig = cipher_new.encrypt(raw_sig_key)
                with open(enc_sig_path, 'wb') as f:
                    f.write(new_encrypted_sig)
                try:
                    os.chmod(enc_sig_path, 0o600)
                except:
                    pass
                
            return True, "PINs updated successfully"
        except Exception as e:
            print(f"[AuthenticationManager] Error updating PINs: {e}")
            return False, f"Encryption update error: {str(e)}"

    def verify_master_pin(self, pin: str) -> bool:
        if self.is_decoy_mode_active():
            return True
        if self.master_pin_hash is None:
            return False

        try:
            iters = getattr(self, 'master_iterations', 200000)
            pin_hash = self._hash_pin(pin, iterations=iters)
            matched = (pin_hash == self.master_pin_hash)
            if matched and getattr(self, 'kdf_version', 1) < 2:
                self._migrate_to_kdf_v2(pin)
            return matched
        except Exception as e:
            print(f"[AuthenticationManager] Error verifying master PIN: {e}")
            return False

    def verify_duress_pin(self, pin: str) -> bool:
        if self.is_decoy_mode_active():
            return False
        if self.duress_pin_hash is None:
            return False

        try:
            iters = getattr(self, 'duress_iterations', 200000)
            pin_hash = self._hash_pin(pin, iterations=iters)
            return pin_hash == self.duress_pin_hash
        except Exception as e:
            print(f"[AuthenticationManager] Error verifying duress PIN: {e}")
            return False
            print(f"[AuthenticationManager] Error verifying duress PIN: {e}")
            return False

    def get_failed_attempts(self) -> int:
        if os.path.exists(self.failed_attempts_file):
            try:
                with open(self.failed_attempts_file, 'r') as f:
                    return int(f.read().strip())
            except Exception:
                return 0
        return 0

    def record_failed_attempt(self) -> int:
        count = self.get_failed_attempts() + 1
        try:
            with open(self.failed_attempts_file, 'w') as f:
                f.write(str(count))
            os.chmod(self.failed_attempts_file, 0o600)
        except Exception:
            pass
        return count

    def reset_failed_attempts(self):
        try:
            if os.path.exists(self.failed_attempts_file):
                os.remove(self.failed_attempts_file)
        except Exception:
            pass

    def record_authentication_heartbeat(self):
        try:
            status = self.get_dead_man_switch_status()
            status["last_heartbeat"] = time.time()
            with open(self.dms_file, 'w') as f:
                json.dump(status, f)
            os.chmod(self.dms_file, 0o600)
        except Exception:
            pass

    def set_dead_man_switch(self, enabled: bool, interval_hours: float = 24.0) -> bool:
        try:
            status = {
                "enabled": enabled,
                "interval_hours": max(0.01, float(interval_hours)),
                "last_heartbeat": time.time()
            }
            with open(self.dms_file, 'w') as f:
                json.dump(status, f)
            os.chmod(self.dms_file, 0o600)
            return True
        except Exception as e:
            print(f"[AuthenticationManager] Error setting Dead Man's Switch: {e}")
            return False

    def get_dead_man_switch_status(self) -> Dict[str, Any]:
        if os.path.exists(self.dms_file):
            try:
                with open(self.dms_file, 'r') as f:
                    data = json.load(f)
                    return data
            except Exception:
                pass
        return {
            "enabled": False,
            "interval_hours": 24.0,
            "last_heartbeat": time.time()
        }

    def check_dead_man_switch(self) -> bool:
        """
        Check if Dead Man's Switch is enabled and has expired.
        If expired, triggers physical wipe and returns True.
        """
        status = self.get_dead_man_switch_status()
        if not status.get("enabled"):
            return False
        last_hb = status.get("last_heartbeat", time.time())
        interval_sec = status.get("interval_hours", 24.0) * 3600.0
        if time.time() - last_hb > interval_sec:
            print("[AuthenticationManager] DEAD MAN'S SWITCH EXPIRED! Triggering emergency wipe...")
            self.trigger_dead_man_wipe()
            return True
        return False

    def trigger_dead_man_wipe(self):
        """Execute physical wipe of credentials and operational keys."""
        try:
            try:
                from src.security import shred_file
            except ImportError:
                from security import shred_file
                
            targets = [
                self.auth_file,
                self.decoy_flag_file,
                self.failed_attempts_file,
                self.dms_file,
                os.path.join(self.storage_dir, ".db_salt"),
                os.path.join(self.storage_dir, "secret.key.enc"),
                os.path.join(self.storage_dir, "signing.key.enc"),
                os.path.join(self.storage_dir, "ghostnet.db"),
                os.path.join(self.storage_dir, "ghostnet.db-wal"),
                os.path.join(self.storage_dir, "ghostnet.db-shm")
            ]
            for target in targets:
                if os.path.exists(target):
                    shred_file(target)
            print("[AuthenticationManager] Dead Man's Switch wipe complete.")
        except Exception as e:
            print(f"[AuthenticationManager] Error during Dead Man's Switch wipe: {e}")

    def _verify_master_hash(self, pin: str) -> bool:
        if self.master_pin_hash is None:
            return False
        try:
            iters = getattr(self, 'master_iterations', 200000)
            pin_hash = self._hash_pin(pin, iterations=iters)
            matched = (pin_hash == self.master_pin_hash)
            if matched and getattr(self, 'kdf_version', 1) < 2:
                self._migrate_to_kdf_v2(pin)
            return matched
        except Exception:
            return False

    def identify_pin(self, pin: str) -> Optional[str]:
        if self.check_dead_man_switch():
            return None

        if self.is_decoy_mode_active():
            # If genuine master PIN is entered, recover from decoy mode
            if self._verify_master_hash(pin):
                self.deactivate_decoy_mode()
                self.record_authentication_heartbeat()
                return "master"
            if len(pin) >= 4:
                self.record_authentication_heartbeat()
                return "master"
            return None

        if self.verify_master_pin(pin):
            self.reset_failed_attempts()
            self.record_authentication_heartbeat()
            return "master"
        elif self.verify_duress_pin(pin):
            self.reset_failed_attempts()
            self.record_authentication_heartbeat()
            return "duress"
        else:
            fails = self.record_failed_attempt()
            print(f"[AuthenticationManager] Invalid PIN attempt ({fails}/{self.max_failed_attempts})")
            if fails >= self.max_failed_attempts:
                print(f"[AuthenticationManager] Failed attempts exceeded threshold ({fails}). Flipping to decoy mode.")
                self.activate_decoy_mode()
            return None

    def _derive_kek(self, pin: str, salt: bytes, iterations: int = 200000) -> bytes:
        if not isinstance(iterations, int) or iterations < 1000:
            iterations = 200000
        return hashlib.pbkdf2_hmac(
            'sha256',
            pin.encode('utf-8'),
            salt,
            iterations,
            dklen=32
        )

    def _migrate_db_kek_v2(self, pin: str, salt: bytes, db_key: bytes, old_kek_cipher):
        """
        Transparently migrates database and signing key files from legacy 100,000 iterations
        to hardened 200,000 iterations (v2) and writes versioned salt header.
        """
        try:
            import base64
            from cryptography.fernet import Fernet
            new_iters = 200000
            new_kek_bytes = self._derive_kek(pin, salt, iterations=new_iters)
            new_kek_cipher = Fernet(base64.urlsafe_b64encode(new_kek_bytes))

            # Re-encrypt secret.key.enc
            enc_key_path = os.path.join(self.storage_dir, "secret.key.enc")
            new_enc = new_kek_cipher.encrypt(db_key)
            with open(enc_key_path, 'wb') as f:
                f.write(new_enc)
            try:
                os.chmod(enc_key_path, 0o600)
            except:
                pass

            # Re-encrypt signing.key.enc if present
            enc_sig_path = os.path.join(self.storage_dir, "signing.key.enc")
            if os.path.exists(enc_sig_path):
                with open(enc_sig_path, 'rb') as f:
                    old_sig_enc = f.read()
                raw_sig = old_kek_cipher.decrypt(old_sig_enc)
                new_sig_enc = new_kek_cipher.encrypt(raw_sig)
                with open(enc_sig_path, 'wb') as f:
                    f.write(new_sig_enc)
                try:
                    os.chmod(enc_sig_path, 0o600)
                except:
                    pass

            # Write versioned .db_salt file
            salt_path = os.path.join(self.storage_dir, ".db_salt")
            with open(salt_path, 'wb') as f:
                f.write(b'GNDBS2\x00' + new_iters.to_bytes(4, 'big') + salt)
            try:
                os.chmod(salt_path, 0o600)
            except:
                pass
            print("[AuthenticationManager] Transparently migrated database & signing key KEK to 200,000 iterations (v2)")
        except Exception as e:
            print(f"[AuthenticationManager] Error migrating DB KEK to v2: {e}")

    def get_or_create_db_key(self, pin: str) -> Optional[bytes]:
        """
        Derives KEK from the PIN, and decrypts the encrypted database key file (secret.key.enc).
        If the file does not exist, generates a new database key, encrypts it using the KEK, and saves it.
        Handles migration of any existing plaintext secret.key file.
        """
        import base64
        from cryptography.fernet import Fernet
        
        if self.is_decoy_mode_active():
            enc_key_path = os.path.join(self.storage_dir, "secret_decoy.key.enc")
        else:
            enc_key_path = os.path.join(self.storage_dir, "secret.key.enc")
            
        plaintext_key_path = os.path.join(self.storage_dir, "secret.key")
        salt_path = os.path.join(self.storage_dir, ".db_salt")
        
        # Load or create salt with version check
        db_salt_version = 1
        db_iters = 100000
        if os.path.exists(salt_path):
            try:
                with open(salt_path, 'rb') as f:
                    raw_salt = f.read()
                if raw_salt.startswith(b'GNDBS2\x00') and len(raw_salt) == 27:
                    raw_iters = int.from_bytes(raw_salt[7:11], 'big')
                    db_iters = raw_iters if raw_iters >= 1000 else 200000
                    salt = raw_salt[11:27]
                    db_salt_version = 2
                else:
                    salt = raw_salt
                    db_iters = 100000
                    db_salt_version = 1
            except Exception as e:
                print(f"[AuthenticationManager] Error loading salt: {e}")
                salt = b'default_ghostnet_db_salt_v1'
        else:
            salt = os.urandom(16)
            db_iters = 200000
            db_salt_version = 2
            try:
                with open(salt_path, 'wb') as f:
                    f.write(b'GNDBS2\x00' + db_iters.to_bytes(4, 'big') + salt)
                os.chmod(salt_path, 0o600)
            except Exception as e:
                print(f"[AuthenticationManager] Error saving salt: {e}")
                
        # Derive KEK
        kek = self._derive_kek(pin, salt, iterations=db_iters)
        kek_b64 = base64.urlsafe_b64encode(kek)
        kek_cipher = Fernet(kek_b64)
        
        # Migrate plaintext key if present
        if not self.is_decoy_mode_active() and os.path.exists(plaintext_key_path) and not os.path.exists(enc_key_path):
            try:
                with open(plaintext_key_path, 'rb') as f:
                    db_key = f.read()
                encrypted_data = kek_cipher.encrypt(db_key)
                with open(enc_key_path, 'wb') as f:
                    f.write(encrypted_data)
                os.chmod(enc_key_path, 0o600)
                try:
                    from src.security import shred_file
                except ImportError:
                    from security import shred_file
                shred_file(plaintext_key_path)
                print("[AuthenticationManager] Migrated database key to encrypted secret.key.enc")
                return db_key
            except Exception as e:
                print(f"[AuthenticationManager] Error migrating database key: {e}")
        
        if os.path.exists(enc_key_path):
            try:
                with open(enc_key_path, 'rb') as f:
                    encrypted_data = f.read()
                db_key = kek_cipher.decrypt(encrypted_data)

                # Upgrade legacy DB KEK (100k iters) to v2 (200k iters)
                if db_salt_version == 1 and not self.is_decoy_mode_active():
                    self._migrate_db_kek_v2(pin, salt, db_key, kek_cipher)

                return db_key
            except Exception as e:
                print(f"[AuthenticationManager] Error decrypting database key: {e}")
                if self.is_decoy_mode_active():
                    return Fernet.generate_key()
                return None
        else:
            # Generate new database key
            db_key = Fernet.generate_key()
            try:
                encrypted_data = kek_cipher.encrypt(db_key)
                with open(enc_key_path, 'wb') as f:
                    f.write(encrypted_data)
                os.chmod(enc_key_path, 0o600)
                print("[AuthenticationManager] Generated and encrypted new database key")
                return db_key
            except Exception as e:
                print(f"[AuthenticationManager] Error saving encrypted database key: {e}")
                return db_key
        return None

    def get_or_create_signing_key(self, pin: str) -> Optional[bytes]:
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.asymmetric import ed25519
        
        if self.is_decoy_mode_active():
            enc_sig_path = os.path.join(self.storage_dir, "signing_decoy.key.enc")
        else:
            enc_sig_path = os.path.join(self.storage_dir, "signing.key.enc")
            
        salt_path = os.path.join(self.storage_dir, ".db_salt")
        db_iters = 100000
        
        if os.path.exists(salt_path):
            try:
                with open(salt_path, 'rb') as f:
                    raw_salt = f.read()
                if raw_salt.startswith(b'GNDBS2\x00') and len(raw_salt) == 27:
                    raw_iters = int.from_bytes(raw_salt[7:11], 'big')
                    db_iters = raw_iters if raw_iters >= 1000 else 200000
                    salt = raw_salt[11:27]
                else:
                    salt = raw_salt
                    db_iters = 100000
            except:
                salt = b'default_ghostnet_db_salt_v1'
        else:
            salt = b'default_ghostnet_db_salt_v1'
            
        kek = self._derive_kek(pin, salt, iterations=db_iters)
        kek_b64 = base64.urlsafe_b64encode(kek)
        kek_cipher = Fernet(kek_b64)
        
        if os.path.exists(enc_sig_path):
            try:
                with open(enc_sig_path, 'rb') as f:
                    encrypted_data = f.read()
                sig_key = kek_cipher.decrypt(encrypted_data)
                return sig_key
            except Exception as e:
                print(f"[AuthenticationManager] Error decrypting signing key: {e}")
                if self.is_decoy_mode_active():
                    private_key = ed25519.Ed25519PrivateKey.generate()
                    from cryptography.hazmat.primitives import serialization
                    return private_key.private_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PrivateFormat.Raw,
                        encryption_algorithm=serialization.NoEncryption()
                    )
                return None
        else:
            # Generate new Ed25519 private key
            private_key = ed25519.Ed25519PrivateKey.generate()
            from cryptography.hazmat.primitives import serialization
            sig_key = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            try:
                encrypted_data = kek_cipher.encrypt(sig_key)
                with open(enc_sig_path, 'wb') as f:
                    f.write(encrypted_data)
                os.chmod(enc_sig_path, 0o600)
                print("[AuthenticationManager] Generated and encrypted new signing key")
                return sig_key
            except Exception as e:
                print(f"[AuthenticationManager] Error saving encrypted signing key: {e}")
                return sig_key
