"""
Random Linear Network Coding (RLNC) over GF(256).
Enables intermediate mesh relays to linearly combine packets on-the-fly, achieving
max-flow min-cut multicast capacity across lossy links without end-to-end retransmissions.
Decodes generations via Gaussian elimination over GF(256) with polynomial 0x11d.
"""

import secrets
from typing import List, Tuple, Optional


# ==============================================================================
# GF(256) Arithmetic with generator 2 and irreducible polynomial 0x11d
# ==============================================================================

_EXP = [0] * 512
_LOG = [0] * 256

def _init_tables():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _EXP[i + 255] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11d

_init_tables()

def _gf_add(a: int, b: int) -> int:
    return a ^ b

def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]

def _gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("Division by zero in GF(256)")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b] + 255) % 255]


class RLNCEncoder:
    """
    Encodes a generation of M packets into random linear combinations in GF(256).
    """

    def __init__(self, packets: List[bytes]):
        if not packets:
            raise ValueError("Packet list cannot be empty")
        self.num_packets = len(packets)
        self.packet_len = max(len(p) for p in packets)
        # Pad all packets to uniform length
        self.packets = [p.ljust(self.packet_len, b'\x00') for p in packets]

    def produce_coded_packet(self, coeffs: Optional[List[int]] = None) -> Tuple[List[int], bytes]:
        """
        Generates a coded packet: C = sum(alpha_i * P_i) over GF(256).
        Returns (coeffs, coded_bytes).
        """
        if coeffs is None:
            # Generate random non-zero coefficients
            coeffs = [secrets.randbelow(255) + 1 for _ in range(self.num_packets)]

        if len(coeffs) != self.num_packets:
            raise ValueError(f"Expected {self.num_packets} coefficients, got {len(coeffs)}")

        coded = bytearray(self.packet_len)
        for i, c in enumerate(coeffs):
            if c == 0:
                continue
            pkt = self.packets[i]
            for byte_idx in range(self.packet_len):
                coded[byte_idx] ^= _gf_mul(pkt[byte_idx], c)

        return coeffs, bytes(coded)


class RLNCDecoder:
    """
    Decodes an RLNC generation via incremental Gaussian elimination over GF(256).
    """

    def __init__(self, generation_size: int, packet_len: int):
        self.generation_size = generation_size
        self.packet_len = packet_len

        # Augmented matrix rows: each row is (coeffs_list, data_bytearray)
        # Maintained in row echelon form
        self.echelon_rows: List[Optional[Tuple[List[int], bytearray]]] = [None] * generation_size
        self.rank = 0

    def add_coded_packet(self, coeffs: List[int], data: bytes) -> bool:
        """
        Ingests a coded packet. Performs Gaussian elimination.
        Returns True if the packet was linearly independent (innovative), False if redundant.
        """
        if len(coeffs) != self.generation_size or len(data) != self.packet_len:
            return False

        c = list(coeffs)
        d = bytearray(data)

        # Eliminate against existing pivot rows
        for i in range(self.generation_size):
            if c[i] != 0:
                if self.echelon_rows[i] is None:
                    # New pivot found at column i!
                    # Normalize pivot row so pivot element is 1
                    pivot = c[i]
                    inv_pivot = _gf_div(1, pivot)

                    for col in range(i, self.generation_size):
                        c[col] = _gf_mul(c[col], inv_pivot)
                    for byte_idx in range(self.packet_len):
                        d[byte_idx] = _gf_mul(d[byte_idx], inv_pivot)

                    self.echelon_rows[i] = (c, d)
                    self.rank += 1
                    return True
                else:
                    # Eliminate leading term using existing pivot row
                    factor = c[i]
                    row_c, row_d = self.echelon_rows[i]
                    for col in range(i, self.generation_size):
                        c[col] ^= _gf_mul(row_c[col], factor)
                    for byte_idx in range(self.packet_len):
                        d[byte_idx] ^= _gf_mul(row_d[byte_idx], factor)

        return False  # Linearly dependent (redundant)

    def is_complete(self) -> bool:
        """Returns True if the matrix has full rank (generation is fully decodable)."""
        return self.rank == self.generation_size

    def decode(self) -> Optional[List[bytes]]:
        """
        Performs back-substitution to recover the original source packets.
        Returns None if rank is insufficient.
        """
        if not self.is_complete():
            return None

        # Copy data arrays for back substitution
        sol_data = [bytearray(self.echelon_rows[i][1]) for i in range(self.generation_size)]

        # Back substitution: eliminate upper triangle
        for i in range(self.generation_size - 1, -1, -1):
            row_c, _ = self.echelon_rows[i]
            for j in range(i - 1, -1, -1):
                factor = self.echelon_rows[j][0][i]
                if factor != 0:
                    for byte_idx in range(self.packet_len):
                        sol_data[j][byte_idx] ^= _gf_mul(sol_data[i][byte_idx], factor)

        return [bytes(s) for s in sol_data]
