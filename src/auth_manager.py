import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple


class AuthenticationManager:

    def __init__(self, storage_dir: str = "."):
        self.storage_dir = storage_dir
        self.auth_file = os.path.join(storage_dir, ".auth_secrets")
        self.decoy_flag_file = os.path.join(storage_dir, ".decoy_mode")
        self.master_pin_hash = None
        self.duress_pin_hash = None
        self.pin_salt = None
        self._load_pin_hashes()
        if not self.are_pins_initialized():
            self.initialize_pins("1234", "9999")

    def is_decoy_mode_active(self) -> bool:
        return os.path.exists(self.decoy_flag_file)

    def activate_decoy_mode(self):
        try:
            with open(self.decoy_flag_file, 'w') as f:
                f.write("active")
            try:
                os.chmod(self.decoy_flag_file, 0o600)
            except:
                pass
            print("[AuthenticationManager] Persistent decoy mode activated")
        except Exception as e:
            print(f"[AuthenticationManager] Error activating decoy mode: {e}")

    def _load_pin_hashes(self):
        if os.path.exists(self.auth_file):
            try:
                with open(self.auth_file, 'rb') as f:
                    data = f.read()
                    if len(data) == 80:
                        self.pin_salt = data[:16]
                        self.master_pin_hash = data[16:48]
                        self.duress_pin_hash = data[48:80]
                    elif len(data) == 64:
                        self.pin_salt = b'ghostnet_pin_salt_v1'[:16]
                        self.master_pin_hash = data[:32]
                        self.duress_pin_hash = data[32:64]
            except Exception as e:
                print(f"[AuthenticationManager] Error loading PIN hashes: {e}")

    def _save_pin_hashes(self):
        try:
            os.makedirs(self.storage_dir, exist_ok=True)
            with open(self.auth_file, 'wb') as f:
                f.write(self.pin_salt + self.master_pin_hash + self.duress_pin_hash)
            os.chmod(self.auth_file, 0o600)
            print("[AuthenticationManager] PIN hashes saved securely")
        except Exception as e:
            print(f"[AuthenticationManager] Error saving PIN hashes: {e}")

    def _hash_pin(self, pin: str) -> bytes:
        salt = self.pin_salt if self.pin_salt else b'ghostnet_pin_salt_v1'
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
            self.pin_salt = os.urandom(16)
            self.master_pin_hash = self._hash_pin(master_pin)
            self.duress_pin_hash = self._hash_pin(duress_pin)
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
            
        if len(new_master) < 4 or len(new_duress) < 4:
            return False, "New PINs must be at least 4 characters long"
            
        if new_master == new_duress:
            return False, "Master PIN and Duress PIN cannot be identical"
            
        try:
            import base64
            from cryptography.fernet import Fernet
            
            # Load DB salt
            salt_path = os.path.join(self.storage_dir, ".db_salt")
            if os.path.exists(salt_path):
                with open(salt_path, 'rb') as f:
                    db_salt = f.read()
            else:
                db_salt = b'default_ghostnet_db_salt_v1'
            
            # Derive KEK from old PIN
            old_kek_bytes = self._derive_kek(old_pin, db_salt)
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
            
            # Generate new salt and save updated hashes (updates .auth_secrets)
            new_salt = os.urandom(16)
            self.pin_salt = new_salt
            self.master_pin_hash = self._hash_pin(new_master)
            self.duress_pin_hash = self._hash_pin(new_duress)
            self._save_pin_hashes()
            
            # Derive KEK from new PIN
            new_kek_bytes = self._derive_kek(new_master, db_salt)
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
            pin_hash = self._hash_pin(pin)
            return pin_hash == self.master_pin_hash
        except Exception as e:
            print(f"[AuthenticationManager] Error verifying master PIN: {e}")
            return False

    def verify_duress_pin(self, pin: str) -> bool:
        if self.is_decoy_mode_active():
            return False
        if self.duress_pin_hash is None:
            return False

        try:
            pin_hash = self._hash_pin(pin)
            return pin_hash == self.duress_pin_hash
        except Exception as e:
            print(f"[AuthenticationManager] Error verifying duress PIN: {e}")
            return False

    def identify_pin(self, pin: str) -> Optional[str]:
        if self.is_decoy_mode_active():
            return "master"
        if self.verify_master_pin(pin):
            return "master"
        elif self.verify_duress_pin(pin):
            return "duress"
        return None

    def _derive_kek(self, pin: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            'sha256',
            pin.encode('utf-8'),
            salt,
            100000,
            dklen=32
        )

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
        
        # Load or create salt
        if os.path.exists(salt_path):
            try:
                with open(salt_path, 'rb') as f:
                    salt = f.read()
            except Exception as e:
                print(f"[AuthenticationManager] Error loading salt: {e}")
                salt = b'default_ghostnet_db_salt_v1'
        else:
            salt = os.urandom(16)
            try:
                with open(salt_path, 'wb') as f:
                    f.write(salt)
                os.chmod(salt_path, 0o600)
            except Exception as e:
                print(f"[AuthenticationManager] Error saving salt: {e}")
                
        # Derive KEK
        kek = self._derive_kek(pin, salt)
        kek_b64 = base64.urlsafe_b64encode(kek)
        kek_cipher = Fernet(kek_b64)
        
        # Migrate plaintext key if present
        if not self.is_decoy_mode_active() and os.path.exists(plaintext_key_path) and not os.path.exists(enc_key_path):
            try:
                with open(plaintext_key_path, 'rb') as f:
                    db_key = f.read()
                # Encrypt it
                encrypted_data = kek_cipher.encrypt(db_key)
                with open(enc_key_path, 'wb') as f:
                    f.write(encrypted_data)
                os.chmod(enc_key_path, 0o600)
                # Securely shred the old plaintext file
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
        
        if os.path.exists(salt_path):
            try:
                with open(salt_path, 'rb') as f:
                    salt = f.read()
            except:
                salt = b'default_ghostnet_db_salt_v1'
        else:
            salt = b'default_ghostnet_db_salt_v1'
            
        kek = self._derive_kek(pin, salt)
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
