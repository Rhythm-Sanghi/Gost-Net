"""
Forward Error Correction (FEC) & Erasure Coding Engine.
Provides Maximum Distance Separable (MDS) erasure coding over GF(2^8) for high-loss RF channels.
Enables full payload reconstruction from any K out of N (K data + M parity) received blocks,
eliminating retransmission storms on lossy ad-hoc radio links.
"""

import struct
from typing import List, Optional, Tuple, Dict

# Field generator polynomial for GF(2^8) (0x11d = x^8 + x^4 + x^3 + x^2 + 1)
GF_POLY = 0x11D

# Precomputed GF(2^8) exp and log lookup tables
GF_EXP = [0] * 512
GF_LOG = [0] * 256

def _init_gf_tables():
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_EXP[i + 255] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= GF_POLY
    GF_LOG[0] = 0

_init_gf_tables()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def gf_div(a: int, b: int) -> int:
    if a == 0:
        return 0
    if b == 0:
        raise ZeroDivisionError("GF(2^8) division by zero")
    diff = GF_LOG[a] - GF_LOG[b]
    if diff < 0:
        diff += 255
    return GF_EXP[diff]


def gf_inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("GF(2^8) inversion of zero")
    return GF_EXP[255 - GF_LOG[a]]


def invert_matrix(matrix: List[List[int]]) -> Optional[List[List[int]]]:
    """Inverts an n x n matrix over GF(2^8) using Gauss-Jordan elimination."""
    n = len(matrix)
    aug = [row[:] + [1 if i == j else 0 for j in range(n)] for i, row in enumerate(matrix)]

    for col in range(n):
        # Find pivot
        pivot_row = None
        for r in range(col, n):
            if aug[r][col] != 0:
                pivot_row = r
                break
        if pivot_row is None:
            return None  # Singular matrix

        if pivot_row != col:
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

        pivot_inv = gf_inv(aug[col][col])
        for c in range(2 * n):
            aug[col][c] = gf_mul(aug[col][c], pivot_inv)

        for r in range(n):
            if r != col and aug[r][col] != 0:
                factor = aug[r][col]
                for c in range(2 * n):
                    aug[r][c] ^= gf_mul(aug[col][c], factor)

    inv = [row[n:] for row in aug]
    return inv


FEC_MAGIC = b'FECC'
# Format: 4s (magic), H (block_idx), H (total_k), H (total_n), I (orig_len)
FEC_HEADER_FORMAT = "!4sHHHI"
FEC_HEADER_SIZE = struct.calcsize(FEC_HEADER_FORMAT)


class FECEngine:
    """
    Reed-Solomon style MDS Erasure Code Engine.
    Encodes K data blocks into N = K + M blocks. Any K received blocks suffice to reconstruct.
    """

    def __init__(self, default_k: int = 4, default_m: int = 2):
        self.default_k = default_k
        self.default_m = default_m

    def _generate_cauchy_matrix(self, k: int, m: int) -> List[List[int]]:
        """
        Constructs an (k + m) x k generator matrix where top k x k is identity,
        and bottom m x k is a Cauchy matrix: C[i][j] = 1 / (X[i] ^ Y[j]).
        """
        # X: [0..m-1] mapped to disjoint elements from Y
        x_vals = [i for i in range(m)]
        y_vals = [m + j for j in range(k)]

        matrix = []
        # Top k rows: Identity
        for i in range(k):
            row = [0] * k
            row[i] = 1
            matrix.append(row)

        # Bottom m rows: Cauchy
        for i in range(m):
            row = []
            for j in range(k):
                diff = x_vals[i] ^ y_vals[j]
                row.append(gf_inv(diff))
            matrix.append(row)

        return matrix

    def encode(self, data: bytes, k: Optional[int] = None, m: Optional[int] = None) -> List[bytes]:
        """
        Encodes arbitrary binary data into N = (k + m) FEC blocks.
        """
        k = k or self.default_k
        m = m or self.default_m
        n = k + m

        orig_len = len(data)
        block_size = (orig_len + k - 1) // k
        if block_size == 0:
            block_size = 1

        # Pad data so each of the k data blocks has equal length
        padded_data = data.ljust(k * block_size, b'\x00')
        data_blocks = [
            list(padded_data[i * block_size:(i + 1) * block_size])
            for i in range(k)
        ]

        generator = self._generate_cauchy_matrix(k, m)
        encoded_blocks: List[bytes] = []

        for row_idx in range(n):
            coeff_row = generator[row_idx]
            out_bytes = bytearray(block_size)
            for byte_pos in range(block_size):
                val = 0
                for col_idx in range(k):
                    coeff = coeff_row[col_idx]
                    if coeff != 0:
                        val ^= gf_mul(data_blocks[col_idx][byte_pos], coeff)
                out_bytes[byte_pos] = val

            header = struct.pack(FEC_HEADER_FORMAT, FEC_MAGIC, row_idx, k, n, orig_len)
            encoded_blocks.append(header + bytes(out_bytes))

        return encoded_blocks

    def decode(self, received_blocks: List[bytes]) -> Optional[bytes]:
        """
        Reconstructs the original data from any K valid received blocks out of N.
        """
        if not received_blocks:
            return None

        valid_blocks: Dict[int, Tuple[int, int, int, bytes]] = {}

        for raw in received_blocks:
            if len(raw) < FEC_HEADER_SIZE:
                continue
            magic, block_idx, k, n, orig_len = struct.unpack(
                FEC_HEADER_FORMAT,
                raw[:FEC_HEADER_SIZE]
            )
            if magic != FEC_MAGIC:
                continue
            payload = raw[FEC_HEADER_SIZE:]
            if block_idx not in valid_blocks:
                valid_blocks[block_idx] = (k, n, orig_len, payload)

        if not valid_blocks:
            return None

        # Sample first block parameters
        first = next(iter(valid_blocks.values()))
        k, n, orig_len, _ = first

        if len(valid_blocks) < k:
            # Insufficient blocks for reconstruction
            return None

        # Pick exactly k blocks
        selected_indices = sorted(list(valid_blocks.keys()))[:k]
        block_size = len(valid_blocks[selected_indices[0]][3])

        # If all k data blocks (0..k-1) are present, directly reconstruct without matrix inversion
        if selected_indices == list(range(k)):
            reconstructed = bytearray()
            for idx in selected_indices:
                reconstructed.extend(valid_blocks[idx][3])
            return bytes(reconstructed[:orig_len])

        # Generate Cauchy matrix for the full code
        m = n - k
        full_matrix = self._generate_cauchy_matrix(k, m)

        # Submatrix corresponding to the k received row indices
        submatrix = [full_matrix[idx] for idx in selected_indices]
        inv_submatrix = invert_matrix(submatrix)
        if inv_submatrix is None:
            return None

        # Multiply inv_submatrix by received block vectors to retrieve original k data blocks
        recv_data = [list(valid_blocks[idx][3]) for idx in selected_indices]
        orig_data_blocks = []

        for row_idx in range(k):
            coeffs = inv_submatrix[row_idx]
            out_bytes = bytearray(block_size)
            for byte_pos in range(block_size):
                val = 0
                for col_idx in range(k):
                    c = coeffs[col_idx]
                    if c != 0:
                        val ^= gf_mul(recv_data[col_idx][byte_pos], c)
                out_bytes[byte_pos] = val
            orig_data_blocks.append(bytes(out_bytes))

        full_payload = b"".join(orig_data_blocks)
        return full_payload[:orig_len]
