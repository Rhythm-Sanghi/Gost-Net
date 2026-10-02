"""
Sovereign Multi-Key Web-of-Trust (WoT) Keyring & (k, n) Threshold Cryptographic Quorum.
Provides decentralized peer cross-certification with transitive confidence scoring,
and Shamir's Secret Sharing over GF(256) for multi-operator emergency command authorization.
"""

import os
import time
import json
import secrets
import threading
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, asdict

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    ED25519_AVAILABLE = True
except ImportError:
    ED25519_AVAILABLE = False


# ==============================================================================
# GF(256) Galois Field Arithmetic for Shamir's Secret Sharing
# Polynomial: x^8 + x^4 + x^3 + x^2 + 1 (0x11d)
# ==============================================================================

_EXP_TABLE = [0] * 512
_LOG_TABLE = [0] * 256

def _init_gf256():
    x = 1
    for i in range(255):
        _EXP_TABLE[i] = x
        _EXP_TABLE[i + 255] = x
        _LOG_TABLE[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11d

_init_gf256()

def _gf_add(a: int, b: int) -> int:
    return a ^ b

def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP_TABLE[_LOG_TABLE[a] + _LOG_TABLE[b]]

def _gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("GF(256) division by zero")
    if a == 0:
        return 0
    return _EXP_TABLE[(_LOG_TABLE[a] - _LOG_TABLE[b] + 255) % 255]


class ShamirThresholdCrypto:
    """
    (k, n) Threshold secret sharing over GF(256).
    Splits any arbitrary binary secret into n shares such that any k shares
    can reconstruct the secret, while <= k - 1 shares reveal nothing.
    """

    @classmethod
    def split_secret(cls, secret_bytes: bytes, threshold_k: int, total_shares_n: int) -> List[Tuple[int, bytes]]:
        """
        Splits secret_bytes into total_shares_n shares with threshold threshold_k.
        Returns a list of (x, share_bytes) where 1 <= x <= total_shares_n <= 255.
        """
        if threshold_k < 1 or threshold_k > total_shares_n:
            raise ValueError("Invalid threshold_k: must be 1 <= k <= n")
        if total_shares_n > 255:
            raise ValueError("total_shares_n cannot exceed 255 in GF(256)")

        shares_data = [bytearray(len(secret_bytes)) for _ in range(total_shares_n)]

        for byte_idx, s_byte in enumerate(secret_bytes):
            # Generate random polynomial coefficients: f(x) = s_byte + a_1*x + ... + a_{k-1}*x^{k-1}
            coeffs = [s_byte] + [secrets.randbelow(256) for _ in range(threshold_k - 1)]

            for i in range(total_shares_n):
                x = i + 1  # x in [1, total_shares_n]
                # Evaluate polynomial at x using Horner's method in GF(256)
                y = 0
                for c in reversed(coeffs):
                    y = _gf_add(_gf_mul(y, x), c)
                shares_data[i][byte_idx] = y

        return [(i + 1, bytes(shares_data[i])) for i in range(total_shares_n)]

    @classmethod
    def reconstruct_secret(cls, shares: List[Tuple[int, bytes]]) -> bytes:
        """
        Reconstructs the original secret from any k distinct shares via Lagrange interpolation at x=0.
        """
        if not shares:
            raise ValueError("Shares list cannot be empty")

        k = len(shares)
        length = len(shares[0][1])

        # Validate unique x coordinates and equal lengths
        x_vals = [s[0] for s in shares]
        if len(set(x_vals)) != k:
            raise ValueError("Duplicate share x coordinates detected")
        for x, s_bytes in shares:
            if len(s_bytes) != length:
                raise ValueError("Share lengths mismatch")

        secret = bytearray(length)

        # Lagrange basis polynomials evaluated at x=0:
        # l_j(0) = prod_{m != j} (x_m / (x_j ^ x_m))
        l_bases = []
        for j in range(k):
            xj = x_vals[j]
            basis = 1
            for m in range(k):
                if m == j:
                    continue
                xm = x_vals[m]
                numerator = xm
                denominator = _gf_add(xj, xm)
                basis = _gf_mul(basis, _gf_div(numerator, denominator))
            l_bases.append(basis)

        for byte_idx in range(length):
            v = 0
            for j in range(k):
                yj = shares[j][1][byte_idx]
                term = _gf_mul(yj, l_bases[j])
                v = _gf_add(v, term)
            secret[byte_idx] = v

        return bytes(secret)


# ==============================================================================
# Web of Trust (WoT) Keyring & Identity Certification
# ==============================================================================

class TrustLevel:
    DIRECT_VERIFICATION = 1.0  # In-person out-of-band verified
    RECOMMENDED_TRUST = 0.6    # Certified by trusted tactical leader
    MARGINAL_TRUST = 0.3       # Second-hand mesh endorsement
    UNTRUSTED = 0.0            # Uncertified / revoked


@dataclass
class KeyCertification:
    issuer_id: str
    subject_id: str
    subject_pubkey_hex: str
    trust_level: float
    timestamp: float
    signature_hex: str = ""

    def canonical_bytes(self) -> bytes:
        d = {
            "issuer_id": self.issuer_id,
            "subject_id": self.subject_id,
            "subject_pubkey_hex": self.subject_pubkey_hex,
            "trust_level": self.trust_level,
            "timestamp": self.timestamp
        }
        return json.dumps(d, sort_keys=True, separators=(',', ':')).encode('utf-8')


class WebOfTrustKeyring:
    """
    Decentralized cross-certification Web-of-Trust keyring for sovereign identity verification.
    """

    def __init__(self, local_node_id: str, private_key: Optional[Any] = None):
        self.local_node_id = local_node_id
        self.private_key = private_key

        # subject_id -> list of KeyCertification
        self.certifications: Dict[str, List[KeyCertification]] = {}
        # peer_id -> public_key_hex
        self.peer_public_keys: Dict[str, str] = {}
        self.lock = threading.RLock()

    def certify_peer(
        self,
        subject_id: str,
        subject_pubkey_hex: str,
        trust_level: float
    ) -> Optional[KeyCertification]:
        """Creates and digitally signs a certification endorsement for a peer."""
        now = time.time()
        cert = KeyCertification(
            issuer_id=self.local_node_id,
            subject_id=subject_id,
            subject_pubkey_hex=subject_pubkey_hex,
            trust_level=max(0.0, min(1.0, trust_level)),
            timestamp=now,
            signature_hex=""
        )

        if self.private_key and ED25519_AVAILABLE:
            try:
                sig_bytes = self.private_key.sign(cert.canonical_bytes())
                cert.signature_hex = sig_bytes.hex()
            except Exception as e:
                print(f"[WebOfTrust] Error signing certification: {e}")

        with self.lock:
            if subject_id not in self.certifications:
                self.certifications[subject_id] = []
            self.certifications[subject_id].append(cert)
            self.peer_public_keys[subject_id] = subject_pubkey_hex

        return cert

    def add_certification(
        self,
        cert: KeyCertification,
        issuer_pubkey: Optional[Any] = None
    ) -> bool:
        """Validates and imports a cross-certification issued by a mesh peer."""
        with self.lock:
            # Verify Ed25519 signature if issuer public key provided
            if issuer_pubkey and ED25519_AVAILABLE and cert.signature_hex:
                try:
                    sig = bytes.fromhex(cert.signature_hex)
                    issuer_pubkey.verify(sig, cert.canonical_bytes())
                except Exception:
                    return False

            if cert.subject_id not in self.certifications:
                self.certifications[cert.subject_id] = []
            self.certifications[cert.subject_id].append(cert)
            self.peer_public_keys[cert.subject_id] = cert.subject_pubkey_hex
            return True

    def compute_trust_score(self, subject_id: str, max_depth: int = 2) -> float:
        """
        Computes cumulative trust confidence for subject_id.
        Direct certification by local node yields immediate trust score.
        Indirect certifications are attenuated by transitive damping factor (0.7).
        """
        with self.lock:
            if subject_id == self.local_node_id:
                return 1.0

            certs = self.certifications.get(subject_id, [])
            if not certs:
                return 0.0

            # Check for direct certification from local node
            direct_certs = [c for c in certs if c.issuer_id == self.local_node_id]
            if direct_certs:
                # Highest direct trust level
                return max(c.trust_level for c in direct_certs)

            # Transitive trust calculation
            cumulative = 0.0
            weight_sum = 0.0

            for c in certs:
                # Get trust of the issuer
                issuer_trust = self.compute_trust_score(c.issuer_id, max_depth - 1) if max_depth > 1 else 0.0
                if issuer_trust > 0.1:
                    attenuated = c.trust_level * issuer_trust * 0.7
                    cumulative += attenuated
                    weight_sum += 1.0

            if weight_sum == 0.0:
                return 0.0
            return min(1.0, cumulative / weight_sum)

    def is_peer_trusted(self, subject_id: str, threshold: float = 0.5) -> bool:
        """Returns True if the peer's cumulative trust score meets or exceeds threshold."""
        return self.compute_trust_score(subject_id) >= threshold
