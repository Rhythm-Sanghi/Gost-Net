"""
Ghost Net - Steganography Module
Implements LSB (Least Significant Bit) encoding/decoding to hide binary payloads
inside lossless PNG carrier images. Supports dynamic generation of default cover images.
"""

import io
import hashlib
from PIL import Image, ImageDraw
from typing import Optional, Union

def _calculate_png_seed(img: Image.Image) -> int:
    """
    Calculate a deterministic seed from the image's high bits (masking LSB to 0).
    This ensures both encoder and decoder arrive at the exact same seed.
    """
    pixels = list(img.convert('RGBA').getdata())
    hasher = hashlib.sha256()
    # Sample the first 10000 pixels to keep it fast
    sample_pixels = pixels[:10000]
    for r, g, b, a in sample_pixels:
        # Mask Least Significant Bit (LSB)
        r_masked = r & ~1
        g_masked = g & ~1
        b_masked = b & ~1
        hasher.update(bytes([r_masked, g_masked, b_masked]))
    return int(hasher.hexdigest()[:8], 16)

def _calculate_wav_seed(data: bytearray) -> int:
    """
    Calculate a deterministic seed from the audio's high bits (masking LSB to 0).
    """
    hasher = hashlib.sha256()
    # Sample the first 20000 bytes
    sample_bytes = data[:20000]
    masked_bytes = bytearray(b & ~1 for b in sample_bytes)
    hasher.update(masked_bytes)
    return int(hasher.hexdigest()[:8], 16)

def get_or_create_default_carrier() -> bytes:
    """
    Generates a unique procedural noise/pattern PNG image to use as a dynamic cover.
    """
    import random
    import math
    img = Image.new("RGBA", (512, 512))
    draw = ImageDraw.Draw(img)
    
    # Generate unique parameters for the noise pattern
    seed_r = random.uniform(1.0, 10.0)
    seed_g = random.uniform(1.0, 10.0)
    seed_b = random.uniform(1.0, 10.0)
    
    for y in range(512):
        # Mix sinusoidal wave values
        for x in range(0, 512, 2):
            r = int(128 + 127 * math.sin(x * 0.05 + seed_r) * math.cos(y * 0.05 + seed_r))
            g = int(128 + 127 * math.sin(x * 0.03 + seed_g) * math.sin(y * 0.03 + seed_g))
            b = int(128 + 127 * math.cos(x * 0.04 + seed_b) * math.cos(y * 0.04 + seed_b))
            # Draw a 2-pixel segment to speed up generation
            draw.line([(x, y), (x+1, y)], fill=(r, g, b, 255))
            
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()

def encode_lsb(carrier: Union[bytes, str], payload: bytes) -> bytes:
    """
    Encodes a payload byte string inside a PNG carrier (path or raw bytes) using LSB.
    Returns the encoded image as PNG bytes.
    """
    if isinstance(carrier, bytes):
        img = Image.open(io.BytesIO(carrier))
    else:
        img = Image.open(carrier)
        
    # Optimize: Downscale cover if it is too large to prevent GIL UI lag and memory exhaustion
    max_size = 1024
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
    img = img.convert('RGBA')
    pixels = list(img.getdata())
    
    # Format: [4 bytes length prefix] + payload
    full_payload = len(payload).to_bytes(4, 'big') + payload
    
    # Capacity verification
    max_bits = len(pixels) * 3  # R, G, B channels
    required_bits = len(full_payload) * 8
    if required_bits > max_bits:
        raise ValueError(f"Payload size ({len(payload)} bytes) exceeds cover capacity ({max_bits // 8} bytes).")
        
    # Build bit array
    bits = []
    for byte in full_payload:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
            
    # Deterministically select indices to embed the bits using dynamic seed
    import random
    seed = _calculate_png_seed(img)
    rng = random.Random(seed)
    used = set()
    indices = []
    while len(indices) < len(bits):
        idx = rng.randint(0, max_bits - 1)
        if idx not in used:
            used.add(idx)
            indices.append(idx)
            
    # Map indices to slots to write
    slots_to_write = {}
    for i, idx in enumerate(indices):
        slots_to_write[idx] = bits[i]
        
    new_pixels = []
    for pixel_idx, pixel in enumerate(pixels):
        r, g, b, a = pixel
        
        slot_r = pixel_idx * 3
        if slot_r in slots_to_write:
            r = (r & ~1) | slots_to_write[slot_r]
            
        slot_g = pixel_idx * 3 + 1
        if slot_g in slots_to_write:
            g = (g & ~1) | slots_to_write[slot_g]
            
        slot_b = pixel_idx * 3 + 2
        if slot_b in slots_to_write:
            b = (b & ~1) | slots_to_write[slot_b]
            
        new_pixels.append((r, g, b, a))
        
    new_img = Image.new('RGBA', img.size)
    new_img.putdata(new_pixels)
    
    out = io.BytesIO()
    new_img.save(out, format="PNG")
    return out.getvalue()

def _decode_lsb_with_seed(pixels: list, max_bits: int, seed: int) -> Optional[bytes]:
    import random
    rng = random.Random(seed)
    used = set()
    indices = []
    
    # 1. Read first 32 bits for length
    while len(indices) < 32:
        idx = rng.randint(0, max_bits - 1)
        if idx not in used:
            used.add(idx)
            indices.append(idx)
            
    length_bits = []
    for idx in indices:
        pixel_idx = idx // 3
        channel = idx % 3
        r, g, b, a = pixels[pixel_idx]
        val = r if channel == 0 else (g if channel == 1 else b)
        length_bits.append(val & 1)
        
    length_bytes = []
    for i in range(4):
        val = 0
        for j in range(8):
            val = (val << 1) | length_bits[i * 8 + j]
        length_bytes.append(val)
        
    length = int.from_bytes(bytes(length_bytes), 'big')
    
    if length <= 0 or length > 10 * 1024 * 1024 or (32 + length * 8) > max_bits:
        return None
        
    # 2. Read payload bits
    total_needed = 32 + length * 8
    while len(indices) < total_needed:
        idx = rng.randint(0, max_bits - 1)
        if idx not in used:
            used.add(idx)
            indices.append(idx)
            
    payload_bits = []
    for idx in indices[32:]:
        pixel_idx = idx // 3
        channel = idx % 3
        r, g, b, a = pixels[pixel_idx]
        val = r if channel == 0 else (g if channel == 1 else b)
        payload_bits.append(val & 1)
        
    payload = []
    for i in range(length):
        val = 0
        for j in range(8):
            val = (val << 1) | payload_bits[i * 8 + j]
        payload.append(val)
        
    return bytes(payload)

def decode_lsb(image: Union[bytes, str]) -> Optional[bytes]:
    """
    Decodes a payload byte string from a PNG image (path or raw bytes) using LSB.
    """
    try:
        if isinstance(image, bytes):
            img = Image.open(io.BytesIO(image))
        else:
            img = Image.open(image)
            
        img = img.convert('RGBA')
        pixels = list(img.getdata())
        
        max_bits = len(pixels) * 3
        if max_bits < 32:
            return None
            
        # Try dynamic seed first
        seed = _calculate_png_seed(img)
        res = _decode_lsb_with_seed(pixels, max_bits, seed)
        if res is not None:
            return res
            
        # Fallback to legacy seed 1337
        return _decode_lsb_with_seed(pixels, max_bits, 1337)
    except Exception as e:
        print(f"[Steganography] Decode failure: {e}")
        return None


def get_or_create_default_wav_carrier() -> bytes:
    """
    Generates a unique procedural noise/multi-tone PCM WAV file to use as a cover.
    """
    import random
    import math
    sample_rate = 44100
    duration = 1.0
    num_samples = int(sample_rate * duration)
    data_size = num_samples * 2  # 16-bit PCM (2 bytes per sample)
    
    header = bytearray()
    header.extend(b'RIFF')
    header.extend((36 + data_size).to_bytes(4, 'little'))
    header.extend(b'WAVE')
    header.extend(b'fmt ')
    header.extend((16).to_bytes(4, 'little'))
    header.extend((1).to_bytes(2, 'little'))  # Audio format (1 = PCM)
    header.extend((1).to_bytes(2, 'little'))  # Channels (1 = Mono)
    header.extend(sample_rate.to_bytes(4, 'little'))
    header.extend((sample_rate * 2).to_bytes(4, 'little'))  # Byte rate
    header.extend((2).to_bytes(2, 'little'))  # Block align
    header.extend((16).to_bytes(2, 'little'))  # Bits per sample
    header.extend(b'data')
    header.extend(data_size.to_bytes(4, 'little'))
    
    # Generate procedural audio data (multi-frequency synth + low amplitude white noise)
    audio_data = bytearray()
    freq1 = random.uniform(200.0, 800.0)
    freq2 = random.uniform(200.0, 800.0)
    
    for i in range(num_samples):
        val1 = math.sin(2 * math.pi * freq1 * (i / sample_rate))
        val2 = math.sin(2 * math.pi * freq2 * (i / sample_rate))
        noise = random.uniform(-0.1, 0.1)
        
        amplitude = 0.15  # Keep volume low
        sample = int(32767 * amplitude * (val1 * 0.4 + val2 * 0.4 + noise * 0.2))
        sample = max(-32768, min(32767, sample))
        
        audio_data.extend(sample.to_bytes(2, 'little', signed=True))
        
    return bytes(header + audio_data)


def _find_data_offset(carrier: bytes) -> int:
    """
    Parses RIFF chunks of the WAV file to dynamically locate the 'data' subchunk offset.
    Falls back to 44 if the format is not recognized or parsing fails.
    """
    if len(carrier) < 12:
        return 44
    if not (carrier.startswith(b'RIFF') and carrier[8:12] == b'WAVE'):
        return 44
    
    offset = 12
    limit = len(carrier)
    while offset + 8 <= limit:
        chunk_id = carrier[offset:offset+4]
        try:
            chunk_size = int.from_bytes(carrier[offset+4:offset+8], 'little')
        except Exception:
            return 44
        
        if chunk_id == b'data':
            return offset + 8
        
        # Advance to next chunk. Sane check chunk_size.
        if chunk_size < 0 or offset + 8 + chunk_size > limit:
            break
            
        offset += 8 + chunk_size
        # Align to 2-byte boundary if size is odd
        if chunk_size % 2 != 0:
            offset += 1
            
    return 44

def encode_wav_lsb(carrier: bytes, payload: bytes) -> bytes:
    """
    Encodes a payload byte string inside a WAV carrier using LSB.
    Returns the encoded WAV as bytes.
    """
    if not (carrier.startswith(b'RIFF') and b'WAVE' in carrier[8:12]):
        raise ValueError("Invalid WAV carrier file")
        
    data_offset = _find_data_offset(carrier)
    header = carrier[:data_offset]
    data = bytearray(carrier[data_offset:])
    
    # Format: [4 bytes length prefix] + payload
    full_payload = len(payload).to_bytes(4, 'big') + payload
    
    required_bits = len(full_payload) * 8
    max_bits = len(data)
    if required_bits > max_bits:
        raise ValueError(f"Payload size ({len(payload)} bytes) exceeds WAV capacity ({max_bits // 8} bytes).")
        
    # Build bit array
    bits = []
    for byte in full_payload:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
            
    # Deterministically select indices using dynamic seed
    import random
    seed = _calculate_wav_seed(data)
    rng = random.Random(seed)
    used = set()
    indices = []
    while len(indices) < len(bits):
        idx = rng.randint(0, max_bits - 1)
        if idx not in used:
            used.add(idx)
            indices.append(idx)
            
    # Embed bits
    for i, idx in enumerate(indices):
        data[idx] = (data[idx] & ~1) | bits[i]
        
    return header + bytes(data)


def _decode_wav_with_seed(data: bytes, max_bits: int, seed: int) -> Optional[bytes]:
    import random
    rng = random.Random(seed)
    used = set()
    indices = []
    
    # 1. Read first 32 bits for length
    while len(indices) < 32:
        idx = rng.randint(0, max_bits - 1)
        if idx not in used:
            used.add(idx)
            indices.append(idx)
            
    length_bits = [data[idx] & 1 for idx in indices]
    length_bytes = []
    for i in range(4):
        val = 0
        for j in range(8):
            val = (val << 1) | length_bits[i * 8 + j]
        length_bytes.append(val)
        
    length = int.from_bytes(bytes(length_bytes), 'big')
    
    if length <= 0 or length > 10 * 1024 * 1024 or (32 + length * 8) > max_bits:
        return None
        
    # 2. Read payload bits
    total_needed = 32 + length * 8
    while len(indices) < total_needed:
        idx = rng.randint(0, max_bits - 1)
        if idx not in used:
            used.add(idx)
            indices.append(idx)
            
    payload_bits = [data[idx] & 1 for idx in indices[32:]]
    
    payload = []
    for i in range(length):
        val = 0
        for j in range(8):
            val = (val << 1) | payload_bits[i * 8 + j]
        payload.append(val)
        
    return bytes(payload)

def decode_wav_lsb(carrier: bytes) -> Optional[bytes]:
    """
    Decodes a payload byte string from a WAV carrier using LSB.
    """
    try:
        if not (carrier.startswith(b'RIFF') and b'WAVE' in carrier[8:12]):
            return None
            
        data_offset = _find_data_offset(carrier)
        data = carrier[data_offset:]
        max_bits = len(data)
        if max_bits < 32:
            return None
            
        # Try dynamic seed first
        seed = _calculate_wav_seed(bytearray(data))
        res = _decode_wav_with_seed(data, max_bits, seed)
        if res is not None:
            return res
            
        # Fallback to legacy seed 1337
        return _decode_wav_with_seed(data, max_bits, 1337)
    except Exception as e:
        print(f"[Steganography] WAV decode failure: {e}")
        return None
