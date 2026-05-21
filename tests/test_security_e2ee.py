import os
import sys
import unittest
from security import CryptoManager


class TestCryptoManager(unittest.TestCase):

    def setUp(self):
        self.crypto1 = CryptoManager()
        self.crypto2 = CryptoManager()
        self.peer_id = "test_peer_001"

    def test_public_key_generation(self):
        pub_key_bytes = self.crypto1.get_public_key_bytes()
        self.assertIsNotNone(pub_key_bytes)
        self.assertEqual(len(pub_key_bytes), 97)

    def test_peer_public_key_storage(self):
        pub_key = self.crypto2.get_public_key_bytes()
        self.crypto1.set_peer_public_key(self.peer_id, pub_key)

        stored_key = self.crypto1.peer_keys.get(self.peer_id)
        self.assertEqual(stored_key, pub_key)

    def test_shared_secret_derivation(self):
        pub_key_1 = self.crypto1.get_public_key_bytes()
        pub_key_2 = self.crypto2.get_public_key_bytes()

        self.crypto1.set_peer_public_key(self.peer_id, pub_key_2)
        self.crypto2.set_peer_public_key(self.peer_id, pub_key_1)

        shared_secret_1 = self.crypto1.derive_shared_secret(self.peer_id)
        shared_secret_2 = self.crypto2.derive_shared_secret(self.peer_id)

        self.assertIsNotNone(shared_secret_1)
        self.assertIsNotNone(shared_secret_2)
        self.assertEqual(shared_secret_1, shared_secret_2)
        self.assertEqual(len(shared_secret_1), 48)

    def test_aes_key_derivation(self):
        pub_key_1 = self.crypto1.get_public_key_bytes()
        pub_key_2 = self.crypto2.get_public_key_bytes()

        self.crypto1.set_peer_public_key(self.peer_id, pub_key_2)
        self.crypto2.set_peer_public_key(self.peer_id, pub_key_1)

        shared_secret_1 = self.crypto1.derive_shared_secret(self.peer_id)
        shared_secret_2 = self.crypto2.derive_shared_secret(self.peer_id)

        aes_key_1 = self.crypto1.derive_aes_key(self.peer_id, shared_secret_1)
        aes_key_2 = self.crypto2.derive_aes_key(self.peer_id, shared_secret_2)

        self.assertIsNotNone(aes_key_1)
        self.assertIsNotNone(aes_key_2)
        self.assertEqual(aes_key_1, aes_key_2)
        self.assertEqual(len(aes_key_1), 32)

    def test_message_encryption_decryption(self):
        pub_key_1 = self.crypto1.get_public_key_bytes()
        pub_key_2 = self.crypto2.get_public_key_bytes()

        self.crypto1.set_peer_public_key(self.peer_id, pub_key_2)
        self.crypto2.set_peer_public_key(self.peer_id, pub_key_1)

        shared_secret_1 = self.crypto1.derive_shared_secret(self.peer_id)
        shared_secret_2 = self.crypto2.derive_shared_secret(self.peer_id)

        self.crypto1.derive_aes_key(self.peer_id, shared_secret_1)
        self.crypto2.derive_aes_key(self.peer_id, shared_secret_2)

        plaintext = b"Hello, Ghost Net! This is a secret message."
        encryption_result = self.crypto1.encrypt_message(self.peer_id, plaintext)

        self.assertIsNotNone(encryption_result)
        nonce, ciphertext = encryption_result

        self.assertEqual(len(nonce), 12)
        self.assertNotEqual(ciphertext, plaintext)

        decrypted = self.crypto2.decrypt_message(self.peer_id, nonce, ciphertext)
        self.assertEqual(decrypted, plaintext)

    def test_encryption_with_unique_nonce(self):
        pub_key_1 = self.crypto1.get_public_key_bytes()
        pub_key_2 = self.crypto2.get_public_key_bytes()

        self.crypto1.set_peer_public_key(self.peer_id, pub_key_2)
        self.crypto2.set_peer_public_key(self.peer_id, pub_key_1)

        shared_secret_1 = self.crypto1.derive_shared_secret(self.peer_id)
        shared_secret_2 = self.crypto2.derive_shared_secret(self.peer_id)

        self.crypto1.derive_aes_key(self.peer_id, shared_secret_1)
        self.crypto2.derive_aes_key(self.peer_id, shared_secret_2)

        plaintext = b"Testing unique nonces"

        result1 = self.crypto1.encrypt_message(self.peer_id, plaintext)
        result2 = self.crypto1.encrypt_message(self.peer_id, plaintext)

        nonce1, cipher1 = result1
        nonce2, cipher2 = result2

        self.assertNotEqual(nonce1, nonce2)
        self.assertNotEqual(cipher1, cipher2)

        decrypted1 = self.crypto2.decrypt_message(self.peer_id, nonce1, cipher1)
        decrypted2 = self.crypto2.decrypt_message(self.peer_id, nonce2, cipher2)

        self.assertEqual(decrypted1, plaintext)
        self.assertEqual(decrypted2, plaintext)

    def test_tampered_ciphertext_detection(self):
        pub_key_1 = self.crypto1.get_public_key_bytes()
        pub_key_2 = self.crypto2.get_public_key_bytes()

        self.crypto1.set_peer_public_key(self.peer_id, pub_key_2)
        self.crypto2.set_peer_public_key(self.peer_id, pub_key_1)

        shared_secret_1 = self.crypto1.derive_shared_secret(self.peer_id)
        shared_secret_2 = self.crypto2.derive_shared_secret(self.peer_id)

        self.crypto1.derive_aes_key(self.peer_id, shared_secret_1)
        self.crypto2.derive_aes_key(self.peer_id, shared_secret_2)

        plaintext = b"Verify authentication"
        nonce, ciphertext = self.crypto1.encrypt_message(self.peer_id, plaintext)

        tampered_ciphertext = bytearray(ciphertext)
        tampered_ciphertext[0] ^= 0xFF
        tampered_ciphertext = bytes(tampered_ciphertext)

        decrypted = self.crypto2.decrypt_message(self.peer_id, nonce, tampered_ciphertext)
        self.assertIsNone(decrypted)

    def test_file_chunk_encryption_decryption(self):
        pub_key_1 = self.crypto1.get_public_key_bytes()
        pub_key_2 = self.crypto2.get_public_key_bytes()

        self.crypto1.set_peer_public_key(self.peer_id, pub_key_2)
        self.crypto2.set_peer_public_key(self.peer_id, pub_key_1)

        shared_secret_1 = self.crypto1.derive_shared_secret(self.peer_id)
        shared_secret_2 = self.crypto2.derive_shared_secret(self.peer_id)

        self.crypto1.derive_aes_key(self.peer_id, shared_secret_1)
        self.crypto2.derive_aes_key(self.peer_id, shared_secret_2)

        file_chunk = os.urandom(4096)

        result = self.crypto1.encrypt_file_chunk(self.peer_id, file_chunk)
        self.assertIsNotNone(result)

        nonce, encrypted_chunk = result
        decrypted_chunk = self.crypto2.decrypt_file_chunk(self.peer_id, nonce, encrypted_chunk)

        self.assertEqual(decrypted_chunk, file_chunk)

    def test_missing_peer_key(self):
        plaintext = b"Test message"
        result = self.crypto1.encrypt_message("nonexistent_peer", plaintext)
        self.assertIsNone(result)

    def test_peer_key_cleanup(self):
        pub_key = self.crypto2.get_public_key_bytes()
        self.crypto1.set_peer_public_key(self.peer_id, pub_key)

        self.assertIn(self.peer_id, self.crypto1.peer_keys)

        self.crypto1.clear_peer_keys(self.peer_id)

        self.assertNotIn(self.peer_id, self.crypto1.peer_keys)
        self.assertNotIn(self.peer_id, self.crypto1.peer_aes_keys)

    def test_multiple_peer_management(self):
        peer_ids = ["peer_001", "peer_002", "peer_003"]
        pub_key = self.crypto2.get_public_key_bytes()

        for peer_id in peer_ids:
            self.crypto1.set_peer_public_key(peer_id, pub_key)

        all_peers = self.crypto1.get_all_peer_ids()
        self.assertEqual(len(all_peers), 0)

        for peer_id in peer_ids:
            shared_secret = self.crypto1.derive_shared_secret(peer_id)
            if shared_secret:
                self.crypto1.derive_aes_key(peer_id, shared_secret)

        all_peers = self.crypto1.get_all_peer_ids()
        self.assertEqual(len(all_peers), len(peer_ids))


class TestECDHHandshakeSimulation(unittest.TestCase):

    def test_complete_ecdh_workflow(self):
        alice = CryptoManager()
        bob = CryptoManager()

        shared_peer_id = "shared_connection"

        alice_pub = alice.get_public_key_bytes()
        bob_pub = bob.get_public_key_bytes()

        alice.set_peer_public_key(shared_peer_id, bob_pub)
        bob.set_peer_public_key(shared_peer_id, alice_pub)

        alice_shared = alice.derive_shared_secret(shared_peer_id)
        bob_shared = bob.derive_shared_secret(shared_peer_id)

        self.assertEqual(alice_shared, bob_shared)

        alice.derive_aes_key(shared_peer_id, alice_shared)
        bob.derive_aes_key(shared_peer_id, bob_shared)

        message = b"Secure communication established!"

        nonce, ciphertext = alice.encrypt_message(shared_peer_id, message)
        decrypted = bob.decrypt_message(shared_peer_id, nonce, ciphertext)

        self.assertEqual(decrypted, message)


if __name__ == '__main__':
    unittest.main()
