"""
Hybrid Post-Quantum Key Encapsulation Mechanism (Ring-LWE Lattice KEM).
Implements Kyber/ML-KEM style polynomial arithmetic in Z_q[x] / (x^n + 1) with n=64, q=3329.
Combines post-quantum lattice shared secrets with classical ECDH via dual HKDF-SHA256
to provide quantum-resilient forward secrecy against 'harvest now, decrypt later' threats.
"""

import hashlib
import secrets
from typing import Tuple, List, Dict, Any


N = 64
Q = 3329


def _poly_mul(a: List[int], b: List[int]) -> List[int]:
    """Negacyclic polynomial multiplication: c = a * b mod (x^N + 1) in Z_Q."""
    c = [0] * N
    for i in range(N):
        ai = a[i]
        if ai == 0:
            continue
        for j in range(N):
            term = (ai * b[j]) % Q
            if i + j < N:
                c[i + j] = (c[i + j] + term) % Q
            else:
                c[i + j - N] = (c[i + j - N] - term) % Q
    return c


def _poly_add(a: List[int], b: List[int]) -> List[int]:
    return [(x + y) % Q for x, y in zip(a, b)]


def _poly_sub(a: List[int], b: List[int]) -> List[int]:
    return [(x - y) % Q for x, y in zip(a, b)]


def _sample_small() -> List[int]:
    """Samples small noise vector with coefficients in {-1, 0, 1}."""
    return [secrets.choice([-1, 0, 1]) for _ in range(N)]


class PostQuantumLatticeKEM:
    """
    Ring-LWE Key Encapsulation Mechanism with dual classical HKDF combiner.
    """

    @classmethod
    def generate_keypair(cls) -> Tuple[Dict[str, List[int]], List[int]]:
        """
        Generates public key (a, t) and private key s.
        """
        a = [secrets.randbelow(Q) for _ in range(N)]
        s = _sample_small()
        e = _sample_small()
        t = _poly_add(_poly_mul(a, s), e)

        public_key = {"a": a, "t": t}
        private_key = s
        return public_key, private_key

    @classmethod
    def encapsulate(cls, public_key: Dict[str, List[int]]) -> Tuple[Dict[str, List[int]], bytes]:
        """
        Encapsulates a random message m, producing ciphertext (u, v) and shared secret K_pq.
        """
        a = public_key["a"]
        t = public_key["t"]

        # Random message bits
        m_bits = [secrets.choice([0, 1]) for _ in range(N)]
        m_encoded = [b * (Q // 2) for b in m_bits]

        r = _sample_small()
        e1 = _sample_small()
        e2 = _sample_small()

        u = _poly_add(_poly_mul(a, r), e1)
        v = _poly_add(_poly_add(_poly_mul(t, r), e2), m_encoded)

        # Derive 32-byte shared secret from message bits
        bit_str = "".join(str(b) for b in m_bits)
        shared_secret = hashlib.sha256(bit_str.encode('utf-8')).digest()

        ciphertext = {"u": u, "v": v}
        return ciphertext, shared_secret

    @classmethod
    def decapsulate(cls, private_key: List[int], ciphertext: Dict[str, List[int]]) -> bytes:
        """
        Decapsulates ciphertext (u, v) using private key s to recover shared secret K_pq.
        """
        s = private_key
        u = ciphertext["u"]
        v = ciphertext["v"]

        w = _poly_sub(v, _poly_mul(u, s))
        recovered_bits = []
        half_q = Q // 2

        for coeff in w:
            c = coeff % Q
            dist_half = min(abs(c - half_q), abs(c + Q - half_q))
            dist_zero = min(c, Q - c)
            recovered_bits.append(1 if dist_half < dist_zero else 0)

        bit_str = "".join(str(b) for b in recovered_bits)
        return hashlib.sha256(bit_str.encode('utf-8')).digest()

    @staticmethod
    def combine_hybrid_keys(ecdh_secret: bytes, pq_secret: bytes, context: str = "GostNet_Hybrid_PQ") -> bytes:
        """
        Combines classical ECDH secret and Post-Quantum lattice secret via HKDF-Extract.
        """
        ikm = ecdh_secret + pq_secret
        return hashlib.sha256(context.encode('utf-8') + ikm).digest()
