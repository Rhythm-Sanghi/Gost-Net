"""
Covert Steganographic Media Carrier Injection & Dead-Drop Engine.
Embeds encrypted binary payloads into Least Significant Bits (LSB) of WAV audio
and image carriers with pseudo-random sample dispersion to provide plausible
deniability and covert asynchronous dead-drop communications under active SIGINT.
"""

import os
import struct
import zlib
import hashlib
from typing import Optional, List, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


STEGO_MAGIC = b'GSTG'
# Format: 4s (magic), I (payload_len), I (crc32)
STEGO_HEADER_FORMAT = "!4sII"
STEGO_HEADER_SIZE = struct.calcsize(STEGO_HEADER_FORMAT)


def _get_pseudo_random_indices(total_samples: int, count: int, key: bytes) -> List[int]:
    """Generates a deterministic, pseudo-random sequence of sample indices using PRNG keyed by secret."""
    if count > total_samples:
        raise ValueError(f"Payload requires {count} samples, carrier only has {total_samples}")

    indices = list(range(total_samples))
    # Fisher-Yates shuffle seeded with SHA256 of key and step counter
    for i in range(count):
        seed_hash = hashlib.sha256(key + struct.pack("!I", i)).digest()
        rand_idx = i + (int.from_bytes(seed_hash[:4], "big") % (total_samples - i))
        indices[i], indices[rand_idx] = indices[rand_idx], indices[i]

    return indices[:count]


def embed_payload_in_wav(wav_bytes: bytes, payload_bytes: bytes, secret_key: Optional[bytes] = None) -> bytes:
    """
    Embeds payload_bytes into the PCM audio samples of a standard RIFF/WAV file.
    If secret_key is supplied, payload is AES-GCM encrypted and samples are pseudo-randomly dispersed.
    """
    if len(wav_bytes) < 44 or wav_bytes[:4] != b'RIFF' or wav_bytes[8:12] != b'WAVE':
        raise ValueError("Provided bytes do not constitute a valid RIFF/WAVE container")

    # Locate 'data' chunk
    data_chunk_idx = wav_bytes.find(b'data')
    if data_chunk_idx == -1:
        # Fallback to standard 44-byte header
        data_chunk_idx = 36
    audio_data_start = data_chunk_idx + 8

    header_bytes = wav_bytes[:audio_data_start]
    samples = bytearray(wav_bytes[audio_data_start:])

    # Prepare payload with encryption if key provided
    processed_payload = payload_bytes
    if secret_key:
        aesgcm = AESGCM(secret_key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, payload_bytes, None)
        processed_payload = nonce + ct

    crc = zlib.crc32(processed_payload)
    packed_header = struct.pack(STEGO_HEADER_FORMAT, STEGO_MAGIC, len(processed_payload), crc)
    full_message = packed_header + processed_payload

    # Convert full_message bytes to bit array
    bits = []
    for b in full_message:
        for bit_pos in range(7, -1, -1):
            bits.append((b >> bit_pos) & 1)

    total_bits = len(bits)
    if total_bits > len(samples):
        raise ValueError(f"WAV carrier capacity ({len(samples)} bits) exceeded by payload ({total_bits} bits)")

    dispersion_key = secret_key or b'GHOSTNET_DEFAULT_STEGO_SEED_KEY'
    sample_indices = _get_pseudo_random_indices(len(samples), total_bits, dispersion_key)

    for bit_idx, sample_idx in enumerate(sample_indices):
        samples[sample_idx] = (samples[sample_idx] & 0xFE) | bits[bit_idx]

    return header_bytes + bytes(samples)


def extract_payload_from_wav(stego_wav_bytes: bytes, secret_key: Optional[bytes] = None) -> Optional[bytes]:
    """
    Extracts and verifies embedded payload from a steganographic WAV container.
    """
    if len(stego_wav_bytes) < 44 or stego_wav_bytes[:4] != b'RIFF':
        return None

    data_chunk_idx = stego_wav_bytes.find(b'data')
    if data_chunk_idx == -1:
        data_chunk_idx = 36
    audio_data_start = data_chunk_idx + 8

    samples = stego_wav_bytes[audio_data_start:]
    dispersion_key = secret_key or b'GHOSTNET_DEFAULT_STEGO_SEED_KEY'

    header_bits_needed = STEGO_HEADER_SIZE * 8
    if len(samples) < header_bits_needed:
        return None

    # Step 1: Extract header bits
    header_indices = _get_pseudo_random_indices(len(samples), header_bits_needed, dispersion_key)
    header_bits = [samples[idx] & 1 for idx in header_indices]

    header_bytes = bytearray()
    for byte_idx in range(STEGO_HEADER_SIZE):
        byte_val = 0
        for bit_offset in range(8):
            byte_val = (byte_val << 1) | header_bits[byte_idx * 8 + bit_offset]
        header_bytes.append(byte_val)

    try:
        magic, payload_len, expected_crc = struct.unpack(STEGO_HEADER_FORMAT, header_bytes)
        if magic != STEGO_MAGIC:
            return None
    except Exception:
        return None

    total_bits_needed = (STEGO_HEADER_SIZE + payload_len) * 8
    if len(samples) < total_bits_needed:
        return None

    # Step 2: Extract full bits
    all_indices = _get_pseudo_random_indices(len(samples), total_bits_needed, dispersion_key)
    payload_indices = all_indices[header_bits_needed:]
    payload_bits = [samples[idx] & 1 for idx in payload_indices]

    raw_payload = bytearray()
    for byte_idx in range(payload_len):
        byte_val = 0
        for bit_offset in range(8):
            byte_val = (byte_val << 1) | payload_bits[byte_idx * 8 + bit_offset]
        raw_payload.append(byte_val)

    # Checksum verification
    actual_crc = zlib.crc32(raw_payload)
    if actual_crc != expected_crc:
        return None

    # Decrypt if key provided
    if secret_key:
        try:
            if len(raw_payload) < 28:
                return None
            nonce = raw_payload[:12]
            ct = raw_payload[12:]
            aesgcm = AESGCM(secret_key)
            decrypted = aesgcm.decrypt(nonce, bytes(ct), None)
            return decrypted
        except Exception:
            return None

    return bytes(raw_payload)


class CovertDeadDropManager:
    """
    Manages asynchronous deposit and retrieval of steganographic media files.
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def deposit_dead_drop(
        self,
        base_wav_path: str,
        output_filename: str,
        payload_bytes: bytes,
        secret_key: Optional[bytes] = None
    ) -> Optional[str]:
        """Injects payload into carrier audio file and writes to dead-drop directory."""
        if not os.path.exists(base_wav_path):
            return None

        with open(base_wav_path, "rb") as f:
            carrier_bytes = f.read()

        try:
            stego_bytes = embed_payload_in_wav(carrier_bytes, payload_bytes, secret_key)
            out_path = os.path.join(self.storage_dir, output_filename)
            with open(out_path, "wb") as f:
                f.write(stego_bytes)
            return out_path
        except Exception as e:
            print(f"[CovertDeadDrop] Error depositing dead-drop: {e}")
            return None

    def scan_dead_drops(self, secret_key: Optional[bytes] = None) -> List[Tuple[str, bytes]]:
        """Scans drop directory and extracts valid stego payloads matching secret_key."""
        results = []
        if not os.path.exists(self.storage_dir):
            return results

        for fname in os.listdir(self.storage_dir):
            if not fname.lower().endswith(".wav"):
                continue
            fpath = os.path.join(self.storage_dir, fname)
            try:
                with open(fpath, "rb") as f:
                    content = f.read()
                extracted = extract_payload_from_wav(content, secret_key)
                if extracted:
                    results.append((fname, extracted))
            except Exception:
                pass

        return results
