import os
import ctypes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import threading
from typing import Dict, Optional, Tuple


import json
import base64
import hmac
import hashlib

class DoubleRatchetSession:
    def __init__(self, peer_id, shared_secret=None, is_initiator=False):
        self.peer_id = peer_id
        
        # Keys and ratchets
        self.root_key = None
        self.sending_chain_key = None
        self.receiving_chain_key = None
        
        # DH Ratchet
        self.dhr_private_key = None
        self.dhr_public_key = None
        self.dhr_peer_public_key = None
        
        # Message numbers
        self.Ns = 0
        self.Nr = 0
        self.Pn = 0
        
        # Skipped keys: map (peer_dh_pub_bytes, msg_num) -> message_key_bytes
        self.skipped_message_keys = {}
        
        if shared_secret:
            self.initialize(shared_secret, is_initiator)
            
    def initialize(self, shared_secret, is_initiator):
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=b'ghostnet_double_ratchet_salt',
            info=b'ghostnet_double_ratchet_init',
            backend=default_backend()
        )
        derived = hkdf.derive(shared_secret)
        self.root_key = derived[:32]
        
        if is_initiator:
            self._generate_dh_keypair()
            self.sending_chain_key = derived[32:]
            self.receiving_chain_key = None
        else:
            self.sending_chain_key = None
            self.receiving_chain_key = derived[32:]
            
    def _generate_dh_keypair(self):
        self.dhr_private_key = ec.generate_private_key(ec.SECP384R1(), backend=default_backend())
        self.dhr_public_key = self.dhr_private_key.public_key()
        
    def get_public_key_bytes(self):
        if not self.dhr_public_key:
            self._generate_dh_keypair()
        return self.dhr_public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
    def _kdf_rk(self, rk, dh_out):
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=rk,
            info=b'ghostnet_double_ratchet_rk',
            backend=default_backend()
        )
        res = hkdf.derive(dh_out)
        return res[:32], res[32:]
        
    def _kdf_ck(self, ck):
        mk = hmac.new(ck, b'\x01', hashlib.sha256).digest()
        ck_new = hmac.new(ck, b'\x02', hashlib.sha256).digest()
        return ck_new, mk
        
    def encrypt(self, plaintext):
        if not self.sending_chain_key:
            if not self.dhr_private_key:
                self._generate_dh_keypair()
            if self.dhr_peer_public_key:
                shared = self.dhr_private_key.exchange(ec.ECDH(), self.dhr_peer_public_key)
                self.root_key, self.sending_chain_key = self._kdf_rk(self.root_key, shared)
            else:
                self.sending_chain_key = self.root_key
                
        self.sending_chain_key, mk = self._kdf_ck(self.sending_chain_key)
        
        cipher = AESGCM(mk)
        nonce = os.urandom(12)
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        
        dh_pub_bytes = self.get_public_key_bytes()
        header = dh_pub_bytes + self.Ns.to_bytes(4, 'big') + self.Pn.to_bytes(4, 'big')
        
        self.Ns += 1
        return nonce, header + ciphertext
        
    def decrypt(self, header_and_ciphertext, nonce):
        if len(header_and_ciphertext) < 105:
            return None
            
        peer_dh_bytes = header_and_ciphertext[:97]
        n = int.from_bytes(header_and_ciphertext[97:101], 'big')
        pn = int.from_bytes(header_and_ciphertext[101:105], 'big')
        ciphertext = header_and_ciphertext[105:]
        
        peer_dh_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP384R1(), peer_dh_bytes)
        
        self._skip_message_keys(peer_dh_bytes, n)
        
        if (peer_dh_bytes, n) in self.skipped_message_keys:
            mk = self.skipped_message_keys.pop((peer_dh_bytes, n))
            cipher = AESGCM(mk)
            return cipher.decrypt(nonce, ciphertext, None)
            
        if self.dhr_peer_public_key is None or peer_dh_bytes != self.dhr_peer_public_key_bytes():
            self.Pn = self.Ns
            self.Ns = 0
            self.Nr = 0
            
            self.dhr_peer_public_key = peer_dh_key
            self.dhr_peer_pub_bytes = peer_dh_bytes
            
            if self.dhr_private_key:
                shared = self.dhr_private_key.exchange(ec.ECDH(), self.dhr_peer_public_key)
                self.root_key, self.receiving_chain_key = self._kdf_rk(self.root_key, shared)
                
            self._generate_dh_keypair()
            shared = self.dhr_private_key.exchange(ec.ECDH(), self.dhr_peer_public_key)
            self.root_key, self.sending_chain_key = self._kdf_rk(self.root_key, shared)
            
        self.receiving_chain_key, mk = self._kdf_ck(self.receiving_chain_key)
        self.Nr += 1
        
        cipher = AESGCM(mk)
        return cipher.decrypt(nonce, ciphertext, None)
        
    def dhr_peer_public_key_bytes(self):
        if not self.dhr_peer_public_key:
            return b''
        return self.dhr_peer_public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
    def _skip_message_keys(self, peer_dh_bytes, until_n):
        if len(self.skipped_message_keys) > 100:
            return
            
        if self.Nr + 100 < until_n:
            return
            
        while self.Nr < until_n:
            if not self.receiving_chain_key:
                break
            self.receiving_chain_key, mk = self._kdf_ck(self.receiving_chain_key)
            self.skipped_message_keys[(peer_dh_bytes, self.Nr)] = mk
            self.Nr += 1
            
    def serialize(self):
        priv_pem = ''
        if self.dhr_private_key:
            priv_pem = base64.b64encode(self.dhr_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )).decode()
            
        peer_pub_b64 = ''
        if self.dhr_peer_public_key:
            peer_pub_b64 = base64.b64encode(self.dhr_peer_public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )).decode()
            
        skipped_serialized = {}
        for (dh_bytes, n), mk in self.skipped_message_keys.items():
            key_str = f"{base64.b64encode(dh_bytes).decode()}:{n}"
            skipped_serialized[key_str] = base64.b64encode(mk).decode()
            
        state = {
            "root_key": base64.b64encode(self.root_key).decode() if self.root_key else '',
            "sending_chain_key": base64.b64encode(self.sending_chain_key).decode() if self.sending_chain_key else '',
            "receiving_chain_key": base64.b64encode(self.receiving_chain_key).decode() if self.receiving_chain_key else '',
            "priv_pem": priv_pem,
            "peer_pub_b64": peer_pub_b64,
            "Ns": self.Ns,
            "Nr": self.Nr,
            "Pn": self.Pn,
            "skipped_keys": skipped_serialized
        }
        return json.dumps(state)
        
    @classmethod
    def deserialize(cls, peer_id, json_str):
        state = json.loads(json_str)
        session = cls(peer_id)
        
        session.root_key = base64.b64decode(state["root_key"]) if state["root_key"] else None
        session.sending_chain_key = base64.b64decode(state["sending_chain_key"]) if state["sending_chain_key"] else None
        session.receiving_chain_key = base64.b64decode(state["receiving_chain_key"]) if state["receiving_chain_key"] else None
        
        if state["priv_pem"]:
            session.dhr_private_key = serialization.load_pem_private_key(
                base64.b64decode(state["priv_pem"]),
                password=None,
                backend=default_backend()
            )
            session.dhr_public_key = session.dhr_private_key.public_key()
            
        if state["peer_pub_b64"]:
            session.dhr_peer_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP384R1(),
                base64.b64decode(state["peer_pub_b64"])
            )
            
        session.Ns = state["Ns"]
        session.Nr = state["Nr"]
        session.Pn = state["Pn"]
        
        for key_str, mk_b64 in state.get("skipped_keys", {}).items():
            parts = key_str.split(':')
            dh_bytes = base64.b64decode(parts[0])
            n = int(parts[1])
            mk = base64.b64decode(mk_b64)
            session.skipped_message_keys[(dh_bytes, n)] = mk
            
        return session


class CryptoManager:

    def __init__(self, signing_private_key_bytes: Optional[bytes] = None):
        self.private_key = None
        self.public_key = None
        self.signing_private_key = None
        self.signing_public_key = None
        self.peer_keys: Dict[str, bytes] = {}
        self.peer_aes_keys: Dict[str, bytes] = {}
        self.keys_lock = threading.Lock()
        self._initialize_keys(signing_private_key_bytes)

    def _initialize_keys(self, signing_private_key_bytes: Optional[bytes] = None):
        from datetime import datetime
        self._key_date = datetime.now().strftime("%Y-%m-%d")
        self.private_key = ec.generate_private_key(
            ec.SECP384R1(),
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()
        
        if signing_private_key_bytes:
            try:
                self.signing_private_key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_private_key_bytes)
                self.signing_public_key = self.signing_private_key.public_key()
            except Exception as e:
                print(f"[CryptoManager] Failed to load signing private key: {e}")
                self.signing_private_key = ed25519.Ed25519PrivateKey.generate()
                self.signing_public_key = self.signing_private_key.public_key()
        else:
            self.signing_private_key = ed25519.Ed25519PrivateKey.generate()
            self.signing_public_key = self.signing_private_key.public_key()

    def _check_daily_key_rotation(self):
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        if not hasattr(self, '_key_date') or self._key_date != current_date:
            self._key_date = current_date
            self.private_key = ec.generate_private_key(
                ec.SECP384R1(),
                backend=default_backend()
            )
            self.public_key = self.private_key.public_key()
            with self.keys_lock:
                self.peer_aes_keys.clear()
            print("[CryptoManager] Daily ECDH keypair rotated successfully")

    def get_public_key_bytes(self) -> bytes:
        self._check_daily_key_rotation()
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )

    def get_signing_public_key_bytes(self) -> bytes:
        return self.signing_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    def sign_data(self, data: bytes) -> bytes:
        if not self.signing_private_key:
            raise ValueError("Signing key not initialized")
        return self.signing_private_key.sign(data)

    def verify_signature(self, signature: bytes, data: bytes, public_key_bytes: bytes) -> bool:
        try:
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            pub_key.verify(signature, data)
            return True
        except Exception as e:
            print(f"[CryptoManager] Signature verification failed: {e}")
            return False

    def set_peer_public_key(self, peer_id: str, peer_public_key_bytes: bytes):
        mlock_bytes(peer_public_key_bytes)
        with self.keys_lock:
            self.peer_keys[peer_id] = peer_public_key_bytes

    def derive_shared_secret(self, peer_id: str) -> Optional[bytes]:
        self._check_daily_key_rotation()
        with self.keys_lock:
            if peer_id not in self.peer_keys:
                return None

            peer_public_key_bytes = self.peer_keys[peer_id]

        try:
            peer_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP384R1(),
                peer_public_key_bytes
            )

            shared_key = self.private_key.exchange(
                ec.ECDH(),
                peer_public_key
            )

            return shared_key
        except Exception as e:
            print(f"[CryptoManager] Error deriving shared secret for {peer_id}: {e}")
            return None

    def derive_aes_key(self, peer_id: str, shared_secret: bytes) -> Optional[bytes]:
        try:
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'ghostnet_aes_key',
                info=peer_id.encode() if isinstance(peer_id, str) else peer_id,
                backend=default_backend()
            )

            aes_key = hkdf.derive(shared_secret)
            mlock_bytes(aes_key)

            with self.keys_lock:
                self.peer_aes_keys[peer_id] = aes_key

            return aes_key
        except Exception as e:
            print(f"[CryptoManager] Error deriving AES key for {peer_id}: {e}")
            return None

    def get_peer_aes_key(self, peer_id: str) -> Optional[bytes]:
        with self.keys_lock:
            return self.peer_aes_keys.get(peer_id)

    def _get_db(self):
        try:
            from kivymd.app import MDApp
            app = MDApp.get_running_app()
            if app and hasattr(app, 'persistence_db'):
                return app.persistence_db
        except:
            pass
        return None

    def _get_or_create_session(self, peer_id: str, is_initiator=True) -> Optional[DoubleRatchetSession]:
        db = self._get_db()
        if db:
            session_data = db.get_ratchet_session(peer_id)
            if session_data:
                try:
                    return DoubleRatchetSession.deserialize(peer_id, session_data)
                except Exception as e:
                    print(f"[CryptoManager] Error deserializing session for {peer_id}: {e}")
                    
        shared_secret = self.derive_shared_secret(peer_id)
        if shared_secret:
            try:
                session = DoubleRatchetSession(peer_id, shared_secret, is_initiator)
                self._save_session(peer_id, session)
                return session
            except Exception as e:
                print(f"[CryptoManager] Error bootstrapping Double Ratchet for {peer_id}: {e}")
        return None

    def _save_session(self, peer_id: str, session: DoubleRatchetSession):
        db = self._get_db()
        if db:
            try:
                session_data = session.serialize()
                db.save_ratchet_session(peer_id, session_data)
            except Exception as e:
                print(f"[CryptoManager] Error saving session to DB: {e}")

    def _fallback_encrypt(self, peer_id: str, plaintext: bytes) -> Optional[Tuple[bytes, bytes]]:
        aes_key = self.get_peer_aes_key(peer_id)
        if not aes_key:
            return None
        try:
            nonce = os.urandom(12)
            cipher = AESGCM(aes_key)
            ciphertext = cipher.encrypt(nonce, plaintext, None)
            return (nonce, ciphertext)
        except Exception as e:
            print(f"[CryptoManager] Fallback encryption error for {peer_id}: {e}")
            return None

    def encrypt_message(self, peer_id: str, plaintext: bytes) -> Optional[Tuple[bytes, bytes]]:
        session = self._get_or_create_session(peer_id, is_initiator=True)
        if not session:
            return self._fallback_encrypt(peer_id, plaintext)
            
        try:
            nonce, header_and_ciphertext = session.encrypt(plaintext)
            self._save_session(peer_id, session)
            return nonce, header_and_ciphertext
        except Exception as e:
            print(f"[CryptoManager] Double Ratchet encryption error: {e}")
            return self._fallback_encrypt(peer_id, plaintext)

    def decrypt_message(self, peer_id: str, nonce: bytes, ciphertext: bytes) -> Optional[bytes]:
        if len(ciphertext) >= 105:
            session = self._get_or_create_session(peer_id, is_initiator=False)
            if session:
                try:
                    plaintext = session.decrypt(ciphertext, nonce)
                    self._save_session(peer_id, session)
                    return plaintext
                except Exception as e:
                    print(f"[CryptoManager] Double Ratchet decryption failed for {peer_id}: {e}. Trying fallback.")
                    
        aes_key = self.get_peer_aes_key(peer_id)
        if not aes_key:
            return None
        try:
            cipher = AESGCM(aes_key)
            plaintext = cipher.decrypt(nonce, ciphertext, None)
            return plaintext
        except Exception as e:
            print(f"[CryptoManager] Fallback decryption error for {peer_id}: {e}")
            return None

    def encrypt_file_chunk(self, peer_id: str, chunk: bytes) -> Optional[Tuple[bytes, bytes]]:
        return self.encrypt_message(peer_id, chunk)

    def decrypt_file_chunk(self, peer_id: str, nonce: bytes, chunk: bytes) -> Optional[bytes]:
        return self.decrypt_message(peer_id, nonce, chunk)

    def clear_peer_keys(self, peer_id: str):
        with self.keys_lock:
            self.peer_keys.pop(peer_id, None)
            self.peer_aes_keys.pop(peer_id, None)

    def get_all_peer_ids(self) -> list:
        with self.keys_lock:
            return list(self.peer_aes_keys.keys())

    def shred_all_keys(self):
        with self.keys_lock:
            try:
                for peer_id in list(self.peer_keys.keys()):
                    shred_bytes(self.peer_keys[peer_id])
                    del self.peer_keys[peer_id]

                for peer_id in list(self.peer_aes_keys.keys()):
                    shred_bytes(self.peer_aes_keys[peer_id])
                    del self.peer_aes_keys[peer_id]

                if self.private_key:
                    self.private_key = None
                if self.public_key:
                    self.public_key = None

                print("[CryptoManager] All keys shredded successfully")
            except Exception as e:
                print(f"[CryptoManager] Error shredding keys: {e}")

def shred_bytes(b: bytes):
    if not isinstance(b, bytes):
        return
    munlock_bytes(b)
    import sys
    size = len(b)
    if size > 0:
        try:
            offset = 32 if sys.maxsize > 2**32 else 16
            addr = id(b) + offset
            ctypes_array = (ctypes.c_ubyte * size).from_address(addr)
            random_data = os.urandom(size)
            for i in range(size):
                ctypes_array[i] = random_data[i]
            for i in range(size):
                ctypes_array[i] = 0
        except Exception as e:
            print(f"[CryptoManager] Memory shredding warning: {e}")

def mlock_bytes(b: bytes):
    if not isinstance(b, bytes):
        return
    import sys
    if sys.platform.startswith('linux') or sys.platform == 'android':
        try:
            import ctypes
            libc = ctypes.CDLL(None)
            size = len(b)
            if size > 0:
                offset = 32 if sys.maxsize > 2**32 else 16
                addr = id(b) + offset
                res = libc.mlock(addr, size)
                if res != 0:
                    print(f"[Security] mlock returned status code {res}")
        except Exception as e:
            print(f"[Security] mlock error: {e}")

def munlock_bytes(b: bytes):
    if not isinstance(b, bytes):
        return
    import sys
    if sys.platform.startswith('linux') or sys.platform == 'android':
        try:
            import ctypes
            libc = ctypes.CDLL(None)
            size = len(b)
            if size > 0:
                offset = 32 if sys.maxsize > 2**32 else 16
                addr = id(b) + offset
                res = libc.munlock(addr, size)
                if res != 0:
                    print(f"[Security] munlock returned status code {res}")
        except Exception as e:
            print(f"[Security] munlock error: {e}")

def shred_file(filepath: str):
    """
    Securely shred a file by overwriting it with random bytes and zeros before deleting.
    """
    if not os.path.exists(filepath):
        return
    try:
        size = os.path.getsize(filepath)
        if size > 0:
            with open(filepath, "r+b") as f:
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())
                f.seek(0)
                f.write(b'\x00' * size)
                f.flush()
                os.fsync(f.fileno())
        os.remove(filepath)
        print(f"[Anti-Forensics] Securely shredded file: {filepath}")
    except Exception as e:
        print(f"[Anti-Forensics] Error shredding file {filepath}: {e}")
        try:
            os.remove(filepath)
        except:
            pass
