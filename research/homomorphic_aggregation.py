"""
Privacy-Preserving Homomorphic Sensor & Swarm Telemetry Aggregation Engine.
Implements the Paillier additive homomorphic cryptosystem, allowing intermediate mesh mules
and relay nodes to sum detachment sensor telemetry (ammunition, casualties, battery health,
radiation levels) without decrypting individual operator data.
"""

import math
import secrets
from typing import Tuple, List, Dict, Any


def _is_probable_prime(n: int, k: int = 8) -> bool:
    """Miller-Rabin primality test."""
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0:
        return False
    r, d = 0, n - 1
    while d % 2 == 0:
        r += 1
        d //= 2
    for _ in range(k):
        a = secrets.randbelow(n - 4) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits: int = 128) -> int:
    """Generates a random probable prime of specified bit length."""
    while True:
        p = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(p):
            return p


class PaillierHomomorphicAggregator:
    """
    Additive homomorphic encryption engine for swarm telemetry.
    """

    @classmethod
    def generate_keypair(cls, key_bits: int = 128) -> Tuple[Dict[str, int], Dict[str, int]]:
        """
        Generates public key (n, g, n_sq) and private key (lam, mu, n).
        """
        p = _generate_prime(key_bits)
        q = _generate_prime(key_bits)
        while p == q:
            q = _generate_prime(key_bits)

        n = p * q
        n_sq = n * n
        lam = math.lcm(p - 1, q - 1)
        g = n + 1
        mu = pow(lam, -1, n)

        public_key = {"n": n, "g": g, "n_sq": n_sq}
        private_key = {"lam": lam, "mu": mu, "n": n}
        return public_key, private_key

    @classmethod
    def encrypt(cls, public_key: Dict[str, int], value: int) -> int:
        """
        Encrypts an integer telemetry reading: c = (g^m * r^n) mod n^2.
        """
        n = public_key["n"]
        g = public_key["g"]
        n_sq = public_key["n_sq"]

        m = int(value) % n
        r = secrets.randbelow(n - 4) + 2
        while math.gcd(r, n) != 1:
            r = secrets.randbelow(n - 4) + 2

        c = (pow(g, m, n_sq) * pow(r, n, n_sq)) % n_sq
        return c

    @classmethod
    def aggregate_ciphertexts(cls, public_key: Dict[str, int], ciphertexts: List[int]) -> int:
        """
        Performs homomorphic addition over encrypted ciphertexts:
        c_sum = prod(c_i) mod n^2.
        """
        if not ciphertexts:
            return 1
        n_sq = public_key["n_sq"]
        product = 1
        for c in ciphertexts:
            product = (product * (c % n_sq)) % n_sq
        return product

    @classmethod
    def decrypt(cls, private_key: Dict[str, int], public_key: Dict[str, int], ciphertext: int) -> int:
        """
        Decrypts an encrypted sum: m = L(c^lam mod n^2) * mu mod n.
        """
        lam = private_key["lam"]
        mu = private_key["mu"]
        n = private_key["n"]
        n_sq = public_key["n_sq"]

        u = pow(ciphertext, lam, n_sq)
        l_val = (u - 1) // n
        m = (l_val * mu) % n
        return m
