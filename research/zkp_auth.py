"""
Zero-Knowledge Peer Authentication (Schnorr Sigma-Protocol with Fiat-Shamir Heuristic).
Enables tactical operators to mathematically prove possession of private signing keys
and authorization to join mission channels without disclosing private keys or linkable identity tokens.
Uses RFC 3526 standardized MODP safe prime group.
"""

import hashlib
import secrets
from typing import Dict, Tuple, Any, Optional


# RFC 3526 1536-bit MODP Safe Prime Group
_P_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA237327FFFFFFFFFFFFFFFF"
)

P = int(_P_HEX, 16)
G = 2
Q = (P - 1) // 2


class SchnorrZKP:
    """
    Non-interactive Zero-Knowledge Proof (NIZK) of discrete logarithm knowledge.
    """

    @classmethod
    def generate_keypair(cls) -> Tuple[int, int]:
        """
        Generates a private secret x in [2, Q - 2] and public identity y = G^x mod P.
        Returns (private_key_x, public_key_y).
        """
        x = secrets.randbelow(Q - 4) + 2
        y = pow(G, x, P)
        return x, y

    @classmethod
    def create_proof(cls, private_x: int, public_y: int, context: str = "GostNet_ZKP_Auth") -> Dict[str, Any]:
        """
        Generates a non-interactive zero-knowledge proof of knowledge of private_x.
        """
        # Choose random commitment r in [2, Q - 2]
        r = secrets.randbelow(Q - 4) + 2
        commitment_R = pow(G, r, P)

        # Fiat-Shamir heuristic: compute non-interactive challenge c
        challenge_bytes = hashlib.sha256(f"{G}:{public_y}:{commitment_R}:{context}".encode('utf-8')).digest()
        c = int.from_bytes(challenge_bytes, byteorder='big') % Q

        # Response s = (r + c * x) mod Q
        s = (r + c * private_x) % Q

        return {
            "R": hex(commitment_R),
            "s": hex(s),
            "c": hex(c),
            "context": context
        }

    @classmethod
    def verify_proof(cls, public_y: int, proof: Dict[str, Any], context: Optional[str] = None) -> bool:
        """
        Verifies non-interactive zero-knowledge proof:
        Checks that G^s == R * (y^c) mod P.
        """
        try:
            R = int(proof["R"], 16)
            s = int(proof["s"], 16)
            c = int(proof["c"], 16)
            ctx = context if context is not None else proof.get("context", "GostNet_ZKP_Auth")

            # Validate range bounds
            if not (1 < R < P):
                return False
            if not (0 <= s < Q) or not (0 <= c < Q):
                return False

            # Recompute Fiat-Shamir challenge
            expected_c_bytes = hashlib.sha256(f"{G}:{public_y}:{R}:{ctx}".encode('utf-8')).digest()
            expected_c = int.from_bytes(expected_c_bytes, byteorder='big') % Q

            if c != expected_c:
                return False

            # Verify Schnorr verification equation: G^s == R * (y^c) mod P
            lhs = pow(G, s, P)
            rhs = (R * pow(public_y, c, P)) % P

            return lhs == rhs
        except Exception as e:
            print(f"[SchnorrZKP] Verification exception: {e}")
            return False
