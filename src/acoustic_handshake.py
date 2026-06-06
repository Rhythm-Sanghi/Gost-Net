import math
import struct
from typing import Optional

LOW_FREQS = [697, 770, 852, 941]
HIGH_FREQS = [1209, 1336, 1477, 1633]

# Mapping from hex digit (0-f) to (low_freq, high_freq)
HEX_TO_TONES = {}
TONES_TO_HEX = {}

for idx in range(16):
    char = hex(idx)[2:]
    low_freq = LOW_FREQS[idx // 4]
    high_freq = HIGH_FREQS[idx % 4]
    HEX_TO_TONES[char] = (low_freq, high_freq)
    TONES_TO_HEX[(low_freq, high_freq)] = char

def fingerprint_to_wav(fingerprint: str, sample_rate: int = 8000, tone_duration: float = 0.1, silence_duration: float = 0.05) -> bytes:
    """
    Encodes a hexadecimal fingerprint string into DTMF tones in WAV format.
    """
    clean_fp = "".join(c.lower() for c in fingerprint if c.lower() in "0123456789abcdef")
    
    tone_samples_len = int(sample_rate * tone_duration)
    silence_samples_len = int(sample_rate * silence_duration)
    
    audio_data = bytearray()
    
    for char in clean_fp:
        if char not in HEX_TO_TONES:
            continue
        low_f, high_f = HEX_TO_TONES[char]
        
        # Generate tone segment
        for i in range(tone_samples_len):
            t = i / sample_rate
            # Mix the two sine waves
            val = math.sin(2 * math.pi * low_f * t) * 0.5 + math.sin(2 * math.pi * high_f * t) * 0.5
            sample = int(32767 * 0.3 * val)  # scale and reduce volume
            audio_data.extend(struct.pack("<h", sample))
            
        # Generate silence segment
        for _ in range(silence_samples_len):
            audio_data.extend(struct.pack("<h", 0))
            
    data_size = len(audio_data)
    
    header = bytearray()
    header.extend(b'RIFF')
    header.extend((36 + data_size).to_bytes(4, 'little'))
    header.extend(b'WAVE')
    header.extend(b'fmt ')
    header.extend((16).to_bytes(4, 'little'))
    header.extend((1).to_bytes(2, 'little'))  # PCM
    header.extend((1).to_bytes(2, 'little'))  # Mono
    header.extend(sample_rate.to_bytes(4, 'little'))
    header.extend((sample_rate * 2).to_bytes(4, 'little'))  # Byte rate
    header.extend((2).to_bytes(2, 'little'))  # Block align
    header.extend((16).to_bytes(2, 'little'))  # 16-bit
    header.extend(b'data')
    header.extend(data_size.to_bytes(4, 'little'))
    
    return bytes(header + audio_data)

def _goertzel(samples: list, target_freq: float, sample_rate: int) -> float:
    num_samples = len(samples)
    if num_samples == 0:
        return 0.0
    k = int(0.5 + (num_samples * target_freq) / sample_rate)
    w = (2 * math.pi / num_samples) * k
    cosine = math.cos(w)
    coeff = 2 * cosine
    
    s_prev = 0.0
    s_prev2 = 0.0
    for x in samples:
        s = x + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
        
    power = s_prev2**2 + s_prev**2 - coeff * s_prev2 * s_prev
    return power

def wav_to_fingerprint(wav_data: bytes, sample_rate: int = 8000, tone_duration: float = 0.1, silence_duration: float = 0.05) -> str:
    """
    Decodes DTMF tones in WAV format back into a hexadecimal fingerprint string.
    """
    if len(wav_data) < 44:
        return ""
        
    # Read sample rate and size from header
    try:
        header_sample_rate = int.from_bytes(wav_data[24:28], 'little')
        # Skip header to get data
        # Search for 'data' chunk
        offset = 12
        limit = len(wav_data)
        data_offset = 44
        while offset + 8 <= limit:
            chunk_id = wav_data[offset:offset+4]
            chunk_size = int.from_bytes(wav_data[offset+4:offset+8], 'little')
            if chunk_id == b'data':
                data_offset = offset + 8
                break
            if chunk_size < 0 or offset + 8 + chunk_size > limit:
                break
            offset += 8 + chunk_size
            if chunk_size % 2 != 0:
                offset += 1
                
        raw_samples = wav_data[data_offset:]
    except Exception:
        header_sample_rate = sample_rate
        raw_samples = wav_data[44:]
        
    sample_rate = header_sample_rate
    
    # Read 16-bit mono PCM samples
    samples = []
    for i in range(0, len(raw_samples) - 1, 2):
        val = int.from_bytes(raw_samples[i:i+2], 'little', signed=True)
        samples.append(val)
        
    # Analyze window segments
    tone_samples_len = int(sample_rate * tone_duration)
    silence_samples_len = int(sample_rate * silence_duration)
    step = tone_samples_len + silence_samples_len
    
    fingerprint = []
    
    for start in range(0, len(samples), step):
        # Extract the tone segment (exclude silence segment)
        tone_window = samples[start:start + tone_samples_len]
        if len(tone_window) < tone_samples_len // 2:
            break
            
        # Detect low freq
        best_low = None
        max_low_power = -1.0
        for f in LOW_FREQS:
            power = _goertzel(tone_window, f, sample_rate)
            if power > max_low_power:
                max_low_power = power
                best_low = f
                
        # Detect high freq
        best_high = None
        max_high_power = -1.0
        for f in HIGH_FREQS:
            power = _goertzel(tone_window, f, sample_rate)
            if power > max_high_power:
                max_high_power = power
                best_high = f
                
        # Guard against pure noise/silence
        if max_low_power < 10000.0 or max_high_power < 10000.0:
            continue
            
        char = TONES_TO_HEX.get((best_low, best_high))
        if char:
            fingerprint.append(char)
            
    return "".join(fingerprint)
