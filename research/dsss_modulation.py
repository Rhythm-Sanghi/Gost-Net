"""
Direct Sequence Spread Spectrum (DSSS) LPI/LPD Soft Modulation Engine.
Spreads narrowband tactical frames across pseudo-random noise chips using LFSR Gold sequences,
enabling transmission below the channel thermal noise floor (Low Probability of Interception)
with matched-filter cross-correlation despreading.
"""

from typing import List, Tuple


class DSSSModulator:
    """
    Direct Sequence Spread Spectrum modulator/demodulator using 31-chip Gold sequences.
    """

    CHIP_LENGTH = 31

    @classmethod
    def generate_gold_sequence(cls, length: int = 31) -> List[int]:
        """
        Generates a 31-chip Gold sequence using dual 5-bit LFSRs:
        LFSR 1: x^5 + x^2 + 1
        LFSR 2: x^5 + x^4 + x^3 + x^2 + 1
        Returns sequence with values in {-1, 1}.
        """
        s1 = 0x1F
        s2 = 0x1F
        seq = []

        for _ in range(length):
            out1 = (s1 >> 4) & 1
            out2 = (s2 >> 4) & 1
            seq.append(1 if (out1 ^ out2) else -1)

            fb1 = ((s1 >> 4) ^ (s1 >> 1)) & 1
            s1 = ((s1 << 1) | fb1) & 0x1F

            fb2 = ((s2 >> 4) ^ (s2 >> 3) ^ (s2 >> 2) ^ (s2 >> 1)) & 1
            s2 = ((s2 << 1) | fb2) & 0x1F

        return seq

    @classmethod
    def spread(cls, data: bytes, gold_code: List[int]) -> List[float]:
        """
        Spreads data bytes into bipolar chips using gold_code.
        Each data bit maps to len(gold_code) chips.
        """
        chips: List[float] = []
        for byte_val in data:
            for b in range(8):
                bit = (byte_val >> (7 - b)) & 1
                polarity = 1.0 if bit == 1 else -1.0
                chips.extend([polarity * float(c) for c in gold_code])
        return chips

    @classmethod
    def despread(cls, received_chips: List[float], gold_code: List[int]) -> bytes:
        """
        Despreads received chips using matched-filter cross-correlation against gold_code.
        """
        code_len = len(gold_code)
        num_bits = len(received_chips) // code_len
        recovered_bits = []

        for bit_idx in range(num_bits):
            offset = bit_idx * code_len
            chunk = received_chips[offset:offset + code_len]
            # Cross correlation / inner product with reference gold code
            corr = sum(c * float(g) for c, g in zip(chunk, gold_code))
            recovered_bits.append(1 if corr >= 0.0 else 0)

        # Pack bits into bytes
        out = bytearray()
        for i in range(0, len(recovered_bits) - (len(recovered_bits) % 8), 8):
            val = 0
            for b in range(8):
                val = (val << 1) | recovered_bits[i + b]
            out.append(val)

        return bytes(out)
