"""
Gost-Net - Chaos Fuzzer & Protocol Robustness Verification Engine
Phase 16 Subsystem: Automated mutation-based stress testing and fault injection across
Gost-Net wire protocols. Mutates packet headers, injects bit flips, byte truncations,
integer boundary overflows, and malformed frames to prove parser containment and crash immunity.
"""

import os
import random
import json
import struct
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field


@dataclass
class FuzzResult:
    mutation_type: str
    original_size: int
    mutated_size: int
    parser_contained: bool
    exception_caught: Optional[str] = None
    output_rejected: bool = True


class ProtocolChaosFuzzer:
    """
    Mutation fuzzer targeting Gost-Net wire frames and packet handlers.
    Verifies that malformed or malicious network inputs never cause uncaught exceptions
    or daemon thread crashes.
    """

    MUTATION_STRATEGIES = [
        "BIT_FLIP",
        "BYTE_TRUNCATION",
        "HEADER_OVERFLOW",
        "MALFORMED_JSON",
        "CORRUPT_DELIMITER",
        "RANDOM_GARBAGE",
        "INTEGER_WRAP_AROUND"
    ]

    def __init__(self, seed: Optional[int] = 42):
        self.rng = random.Random(seed)

    def mutate_packet(self, packet_bytes: bytes, strategy: Optional[str] = None) -> Tuple[bytes, str]:
        """
        Applies a random or specified mutation strategy to an encoded packet.
        Returns:
            (mutated_bytes, strategy_used)
        """
        strat = strategy or self.rng.choice(self.MUTATION_STRATEGIES)
        raw = bytearray(packet_bytes)

        if strat == "BIT_FLIP" and len(raw) > 0:
            pos = self.rng.randint(0, len(raw) - 1)
            bit = 1 << self.rng.randint(0, 7)
            raw[pos] ^= bit
            return bytes(raw), strat

        elif strat == "BYTE_TRUNCATION" and len(raw) > 1:
            cut = self.rng.randint(1, len(raw) - 1)
            return bytes(raw[:cut]), strat

        elif strat == "HEADER_OVERFLOW":
            # Injects extremely long malicious strings into header fields
            overflow_header = {
                "type": "FUZZ_OVERFLOW_" + ("A" * 8192),
                "sender_peer_id": "X" * 4096,
                "payload": "B" * 16384
            }
            return json.dumps(overflow_header).encode('utf-8') + b"\n\n\n", strat

        elif strat == "MALFORMED_JSON":
            # Partially valid JSON missing closing braces or having trailing commas
            malformed = b'{"type": "CHAT", "sender": "ALICE", "corrupted": [1, 2, '
            return malformed + b"\n\n\n", strat

        elif strat == "CORRUPT_DELIMITER":
            # Replaces standard delimiter with corrupted bytes
            return bytes(raw).replace(b"\n\n\n", b"\x00\xff\x00"), strat

        elif strat == "INTEGER_WRAP_AROUND":
            # Injects 64-bit boundary integers into sequence or timestamp fields
            edge_header = {
                "type": "TIME_SYNC_REQUEST",
                "t1": 1.7976931348623157e+308,
                "seq_num": 0xFFFFFFFFFFFFFFFF,
                "epoch": -9223372036854775808
            }
            return json.dumps(edge_header).encode('utf-8') + b"\n\n\n", strat

        else:  # RANDOM_GARBAGE
            garbage_len = self.rng.randint(1, 1024)
            return os.urandom(garbage_len), "RANDOM_GARBAGE"

    def fuzz_parser(self, parser_fn: Callable[[bytes], Any], original_packet: bytes, iterations: int = 50) -> List[FuzzResult]:
        """
        Executes multiple fuzzing iterations against a packet parser function.
        Verifies that every mutation is either safely parsed or raises a handled rejection,
        without throwing unexpected fatal errors.
        """
        results: List[FuzzResult] = []
        for _ in range(iterations):
            mutated, strat = self.mutate_packet(original_packet)
            contained = True
            exc_str = None
            rejected = True

            try:
                res = parser_fn(mutated)
                # If it parsed without error, it accepted the mutated input
                rejected = (res is None or res is False)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError, struct.error) as e:
                # Handled protocol exceptions indicate successful input containment
                exc_str = type(e).__name__
                rejected = True
            except Exception as e:
                # Unexpected catastrophic exceptions
                contained = False
                exc_str = f"FATAL_{type(e).__name__}: {str(e)}"
                rejected = True

            results.append(FuzzResult(
                mutation_type=strat,
                original_size=len(original_packet),
                mutated_size=len(mutated),
                parser_contained=contained,
                exception_caught=exc_str,
                output_rejected=rejected
            ))

        return results
