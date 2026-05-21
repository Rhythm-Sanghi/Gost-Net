import os
import ctypes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import threading
from typing import Dict, Optional, Tuple


class CryptoManager:

    def __init__(self):
        self.private_key = None
        self.public_key = None
        self.peer_keys: Dict[str, bytes] = {}
        self.peer_aes_keys: Dict[str, bytes] = {}
        self.keys_lock = threading.Lock()
        self._initialize_keys()

    def _initialize_keys(self):
        self.private_key = ec.generate_private_key(
            ec.SECP384R1(),
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()

    def get_public_key_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )

    def set_peer_public_key(self, peer_id: str, peer_public_key_bytes: bytes):
        with self.keys_lock:
            self.peer_keys[peer_id] = peer_public_key_bytes

    def derive_shared_secret(self, peer_id: str) -> Optional[bytes]:
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

            with self.keys_lock:
                self.peer_aes_keys[peer_id] = aes_key

            return aes_key
        except Exception as e:
            print(f"[CryptoManager] Error deriving AES key for {peer_id}: {e}")
            return None

    def get_peer_aes_key(self, peer_id: str) -> Optional[bytes]:
        with self.keys_lock:
            return self.peer_aes_keys.get(peer_id)

    def encrypt_message(self, peer_id: str, plaintext: bytes) -> Optional[Tuple[bytes, bytes]]:
        aes_key = self.get_peer_aes_key(peer_id)
        if not aes_key:
            return None

        try:
            nonce = os.urandom(12)
            cipher = AESGCM(aes_key)
            ciphertext = cipher.encrypt(nonce, plaintext, None)

            return (nonce, ciphertext)
        except Exception as e:
            print(f"[CryptoManager] Encryption error for {peer_id}: {e}")
            return None

    def decrypt_message(self, peer_id: str, nonce: bytes, ciphertext: bytes) -> Optional[bytes]:
        aes_key = self.get_peer_aes_key(peer_id)
        if not aes_key:
            return None

        try:
            cipher = AESGCM(aes_key)
            plaintext = cipher.decrypt(nonce, ciphertext, None)
            return plaintext
        except Exception as e:
            print(f"[CryptoManager] Decryption error for {peer_id}: {e}")
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
                    key_bytes = self.peer_keys[peer_id]
                    random_data = os.urandom(len(key_bytes))
                    ctypes_array = (ctypes.c_ubyte * len(key_bytes)).from_address(id(key_bytes))
                    for i in range(len(key_bytes)):
                        ctypes_array[i] = random_data[i]
                    del self.peer_keys[peer_id]

                for peer_id in list(self.peer_aes_keys.keys()):
                    key_bytes = self.peer_aes_keys[peer_id]
                    random_data = os.urandom(len(key_bytes))
                    ctypes_array = (ctypes.c_ubyte * len(key_bytes)).from_address(id(key_bytes))
                    for i in range(len(key_bytes)):
                        ctypes_array[i] = random_data[i]
                    del self.peer_aes_keys[peer_id]

                if self.private_key:
                    self.private_key = None
                if self.public_key:
                    self.public_key = None

                print("[CryptoManager] All keys shredded successfully")
            except Exception as e:
                print(f"[CryptoManager] Error shredding keys: {e}")
