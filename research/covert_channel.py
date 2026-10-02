"""
Covert Timing Channel & Inter-Packet Delay (IPD) Steganography Engine.

Encodes secret bit streams into the statistical distribution of packet
inter-arrival intervals, enabling covert data exfiltration across observed
network links without altering packet content or payload lengths.

Decoding reconstructs the hidden bitstream from the same IPD observations
using a shared keyed encoding map, achieving a covert channel below the
statistical detection threshold of naive traffic analysers.

Technical basis:
  - Modulation alphabet: N timing buckets uniformly spanning [T_min, T_max] ms.
  - Bits per symbol: floor(log2(N)).
  - Symbol embedding: delay(k) = T_min + (k + 0.5) * bucket_width  (bucket centre).
  - Decode quantisation: floor((delay - T_min) / bucket_width), clamped.
  - Noise tolerance: symmetric ±(bucket_width / 2) around each bucket centre.
  - Detection resistance: optional Gaussian jitter added from os.urandom bytes.
"""

import math
import hashlib
import struct
import os
from typing import List, Tuple


class CovertTimingChannel:
    """
    Inter-Packet Delay (IPD) steganographic covert channel.

    Encodes bit groups into quantised inter-packet delay values so that
    the transmitted message is hidden in the *timing* of packets rather
    than their content.

    Each symbol is transmitted at the **centre** of its bucket so that
    channel noise of up to ±(bucket_width / 2) cannot cross the quantisation
    boundary, providing maximum noise resilience.

    Parameters
    ----------
    t_min_ms : float
        Minimum inter-packet delay in milliseconds (floor of timing alphabet).
    t_max_ms : float
        Maximum inter-packet delay in milliseconds (ceiling of timing alphabet).
    num_buckets : int
        Number of uniformly-spaced timing buckets.  Must be a power of two
        so that floor(log2(num_buckets)) whole bits map cleanly per symbol.
    sigma_jitter_ms : float
        Standard deviation of additive Gaussian jitter noise in milliseconds,
        simulating realistic channel timing variance.
    """

    def __init__(
        self,
        t_min_ms: float = 10.0,
        t_max_ms: float = 250.0,
        num_buckets: int = 16,
        sigma_jitter_ms: float = 2.0,
    ):
        if t_max_ms <= t_min_ms:
            raise ValueError("t_max_ms must be greater than t_min_ms")
        if num_buckets < 2:
            raise ValueError("num_buckets must be >= 2")

        self.t_min_ms = t_min_ms
        self.t_max_ms = t_max_ms
        self.num_buckets = num_buckets
        self.sigma_jitter_ms = sigma_jitter_ms

        # Bits per inter-packet interval symbol
        self.bits_per_symbol: int = int(math.log2(num_buckets))
        if 2 ** self.bits_per_symbol != num_buckets:
            # Truncate to nearest power-of-two worth of bits
            self.bits_per_symbol = int(math.floor(math.log2(num_buckets)))
            effective_buckets = 2 ** self.bits_per_symbol
        else:
            effective_buckets = num_buckets

        self._effective_buckets = effective_buckets
        self._bucket_width_ms = (t_max_ms - t_min_ms) / effective_buckets

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, payload: bytes) -> List[float]:
        """
        Encode *payload* into a sequence of inter-packet delay values (ms).

        Each group of ``bits_per_symbol`` bits from the payload is mapped to
        one delay value placed at the *centre* of its timing bucket.  A 2-byte
        length prefix is prepended so the decoder can strip any trailing padding
        symbols.

        Parameters
        ----------
        payload : bytes
            Secret message to hide in the timing channel.

        Returns
        -------
        List[float]
            Sequence of inter-packet delay values in milliseconds.
            Feed these as sleep intervals between successive packet transmissions.
        """
        # Prepend 2-byte length so decoder knows exact payload boundary
        length_prefix = struct.pack(">H", len(payload))
        data = length_prefix + payload

        bits = self._bytes_to_bits(data)

        # Pad bits to multiple of bits_per_symbol
        remainder = len(bits) % self.bits_per_symbol
        if remainder:
            bits += [0] * (self.bits_per_symbol - remainder)

        delays: List[float] = []
        for i in range(0, len(bits), self.bits_per_symbol):
            chunk = bits[i : i + self.bits_per_symbol]
            symbol_index = self._bits_to_int(chunk)
            # Place ideal delay at the bucket centre for symmetric noise tolerance:
            # centre_k = t_min + (k + 0.5) * bucket_width
            ideal_delay = self.t_min_ms + (symbol_index + 0.5) * self._bucket_width_ms
            # Add jitter noise
            jitter = self._gaussian_jitter()
            delay = max(self.t_min_ms, min(self.t_max_ms, ideal_delay + jitter))
            delays.append(delay)

        return delays

    def decode(self, delays: List[float]) -> bytes:
        """
        Decode inter-packet delay observations back to the hidden payload.

        Quantises each delay to the nearest bucket index using floor division,
        which is equivalent to round-to-nearest when the ideal delays are at
        bucket centres.

        Parameters
        ----------
        delays : List[float]
            Sequence of inter-packet delay values in milliseconds as observed
            by the receiver (may include channel jitter noise).

        Returns
        -------
        bytes
            Reconstructed secret payload.
        """
        bits: List[int] = []
        for delay in delays:
            # Clamp to valid range, then floor-divide to get bucket index.
            # Because ideal delays are at bucket centres, floor(offset/width)
            # correctly maps any noise within ±width/2 to the right bucket.
            clamped = max(self.t_min_ms, min(self.t_max_ms - 1e-9, delay))
            symbol_index = int((clamped - self.t_min_ms) / self._bucket_width_ms)
            symbol_index = max(0, min(self._effective_buckets - 1, symbol_index))
            symbol_bits = self._int_to_bits(symbol_index, self.bits_per_symbol)
            bits.extend(symbol_bits)

        # Recover byte stream
        raw_bytes = self._bits_to_bytes(bits)

        # Extract 2-byte length prefix
        if len(raw_bytes) < 2:
            return b""
        payload_len = struct.unpack(">H", raw_bytes[:2])[0]
        payload = raw_bytes[2 : 2 + payload_len]
        return payload

    def channel_capacity_bps(self, mean_ipd_ms: float) -> float:
        """
        Theoretical Shannon channel capacity in bits per second.

        Approximates the covert channel as an AWGN channel where the
        quantisation SNR determines the effective alphabet size.

        Parameters
        ----------
        mean_ipd_ms : float
            Expected mean inter-packet delay in milliseconds.

        Returns
        -------
        float
            Achievable covert bit-rate in bits per second.
        """
        if mean_ipd_ms <= 0:
            return 0.0
        symbols_per_second = 1000.0 / mean_ipd_ms
        return self.bits_per_symbol * symbols_per_second

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bytes_to_bits(data: bytes) -> List[int]:
        """Convert bytes to list of bits (MSB first)."""
        bits: List[int] = []
        for byte_val in data:
            for b in range(7, -1, -1):
                bits.append((byte_val >> b) & 1)
        return bits

    @staticmethod
    def _bits_to_bytes(bits: List[int]) -> bytes:
        """Convert list of bits (MSB first) back to bytes."""
        # Pad to byte boundary
        remainder = len(bits) % 8
        if remainder:
            bits = bits + [0] * (8 - remainder)
        result = bytearray()
        for i in range(0, len(bits), 8):
            byte_val = 0
            for j in range(8):
                byte_val = (byte_val << 1) | bits[i + j]
            result.append(byte_val)
        return bytes(result)

    @staticmethod
    def _bits_to_int(bits: List[int]) -> int:
        """Interpret a list of bits (MSB first) as an unsigned integer."""
        val = 0
        for b in bits:
            val = (val << 1) | b
        return val

    @staticmethod
    def _int_to_bits(val: int, width: int) -> List[int]:
        """Convert integer to a fixed-width bit list (MSB first)."""
        return [(val >> (width - 1 - i)) & 1 for i in range(width)]

    def _gaussian_jitter(self) -> float:
        """
        Generate a Gaussian-distributed jitter sample.

        Uses the Box-Muller transform on os.urandom bytes to avoid
        depending on random.gauss (which uses the Mersenne Twister state).
        """
        if self.sigma_jitter_ms == 0.0:
            return 0.0
        # Box-Muller: two uniform samples -> standard normal
        u1_bytes = os.urandom(4)
        u2_bytes = os.urandom(4)
        u1 = (struct.unpack(">I", u1_bytes)[0] + 1) / (2**32 + 1)
        u2 = (struct.unpack(">I", u2_bytes)[0] + 1) / (2**32 + 1)
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return z * self.sigma_jitter_ms


class KeyedTimingChannel(CovertTimingChannel):
    """
    Keyed variant of CovertTimingChannel.

    Derives a per-session timing permutation from a shared secret key so
    that the bucket-to-symbol mapping is pseudo-random and not easily
    reverse-engineered by an adversary without the key.
    """

    def __init__(self, key: bytes, **kwargs):
        """
        Parameters
        ----------
        key : bytes
            Shared secret key used to derive the bucket permutation.
        **kwargs
            Forwarded to CovertTimingChannel.__init__.
        """
        super().__init__(**kwargs)
        self._permutation, self._inverse_permutation = self._derive_permutation(key)

    def _derive_permutation(self, key: bytes) -> Tuple[List[int], List[int]]:
        """
        Derive a deterministic bucket permutation from *key* using HMAC-SHA256
        seeded Fisher-Yates shuffle.
        """
        n = self._effective_buckets
        perm = list(range(n))

        # Generate enough pseudo-random bytes: n * 4 bytes
        prng_bytes = b""
        counter = 0
        while len(prng_bytes) < n * 4:
            digest = hashlib.sha256(key + struct.pack(">I", counter)).digest()
            prng_bytes += digest
            counter += 1

        # Fisher-Yates shuffle
        for i in range(n - 1, 0, -1):
            rand_val = struct.unpack(">I", prng_bytes[i * 4 : i * 4 + 4])[0]
            j = rand_val % (i + 1)
            perm[i], perm[j] = perm[j], perm[i]

        inverse = [0] * n
        for idx, val in enumerate(perm):
            inverse[val] = idx

        return perm, inverse

    def encode(self, payload: bytes) -> List[float]:
        """
        Encode payload with keyed bucket permutation applied before delay mapping.
        """
        length_prefix = struct.pack(">H", len(payload))
        data = length_prefix + payload

        bits = self._bytes_to_bits(data)
        remainder = len(bits) % self.bits_per_symbol
        if remainder:
            bits += [0] * (self.bits_per_symbol - remainder)

        delays: List[float] = []
        for i in range(0, len(bits), self.bits_per_symbol):
            chunk = bits[i : i + self.bits_per_symbol]
            symbol_index = self._bits_to_int(chunk)
            # Apply keyed permutation
            permuted_index = self._permutation[symbol_index]
            # Place at bucket centre
            ideal_delay = self.t_min_ms + (permuted_index + 0.5) * self._bucket_width_ms
            jitter = self._gaussian_jitter()
            delay = max(self.t_min_ms, min(self.t_max_ms, ideal_delay + jitter))
            delays.append(delay)

        return delays

    def decode(self, delays: List[float]) -> bytes:
        """
        Decode delays with inverse keyed bucket permutation applied after quantisation.
        """
        bits: List[int] = []
        for delay in delays:
            clamped = max(self.t_min_ms, min(self.t_max_ms - 1e-9, delay))
            permuted_index = int((clamped - self.t_min_ms) / self._bucket_width_ms)
            permuted_index = max(0, min(self._effective_buckets - 1, permuted_index))
            # Apply inverse permutation
            symbol_index = self._inverse_permutation[permuted_index]
            symbol_bits = self._int_to_bits(symbol_index, self.bits_per_symbol)
            bits.extend(symbol_bits)

        raw_bytes = self._bits_to_bytes(bits)
        if len(raw_bytes) < 2:
            return b""
        payload_len = struct.unpack(">H", raw_bytes[:2])[0]
        return raw_bytes[2 : 2 + payload_len]
