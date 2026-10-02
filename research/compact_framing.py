"""
Compact Binary Packet Framing and Adaptive Compression Engine for Gost-Net.
Provides low-bandwidth binary encapsulation for constrained RF, acoustic, and ad-hoc links.
"""

import struct
import zlib
import time
import json
from typing import Dict, Any, Optional, Tuple

# Header constants
MAGIC_BYTES = b'GN'  # 2 bytes: 'Gost-Net'
PROTOCOL_VERSION = 0x02  # 1 byte: Version 2.0

# 1-byte Packet Type Enumerations
PACKET_TYPES = {
    "TEXT": 0x01,
    "GROUP_TEXT": 0x02,
    "BEACON": 0x03,
    "ACK": 0x04,
    "RREQ": 0x05,
    "RREP": 0x06,
    "RERR": 0x07,
    "LOCATION_UPDATE": 0x08,
    "WAYPOINT": 0x09,
    "PEER_REVOCATION": 0x0A,
    "SOS": 0x0B,
    "FILE_CHUNK": 0x0C,
    "GENERIC_JSON": 0x0F
}

REVERSE_PACKET_TYPES = {v: k for k, v in PACKET_TYPES.items()}

# Bit flags
FLAG_COMPRESSED = 0x01
FLAG_PRIORITY = 0x02
FLAG_HAS_SIGNATURE = 0x04
FLAG_ENCRYPTED = 0x08

HEADER_STRUCT_FORMAT = "!2sBBIIQBH"
HEADER_SIZE = struct.calcsize(HEADER_STRUCT_FORMAT)
# ! = network (big-endian)
# 2s = magic (2 bytes, 'GN')
# B  = version (1 byte)
# B  = packet_type (1 byte)
# I  = sequence_id / crc (4 bytes)
# I  = flags (4 bytes)
# Q  = timestamp_ms (8 bytes, uint64)
# B  = ttl (1 byte)
# H  = payload_len (2 bytes, uint16, up to 65535 bytes)


def pack_compact_frame(
    packet_type: str,
    payload_data: bytes,
    seq_id: int = 0,
    timestamp_ms: Optional[int] = None,
    ttl: int = 15,
    is_priority: bool = False,
    is_encrypted: bool = False,
    auto_compress: bool = True
) -> bytes:
    """
    Pack payload bytes into a compact binary frame with optional zlib compression.
    """
    type_code = PACKET_TYPES.get(packet_type, PACKET_TYPES["GENERIC_JSON"])
    
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
        
    flags = 0
    if is_priority:
        flags |= FLAG_PRIORITY
    if is_encrypted:
        flags |= FLAG_ENCRYPTED
        
    final_payload = payload_data
    # Automatically apply zlib compression if payload > 128 bytes and compressible
    if auto_compress and len(payload_data) > 128:
        try:
            compressed = zlib.compress(payload_data, level=6)
            if len(compressed) < len(payload_data):
                final_payload = compressed
                flags |= FLAG_COMPRESSED
        except Exception:
            pass
            
    payload_len = len(final_payload)
    if payload_len > 65535:
        raise ValueError(f"Payload size {payload_len} exceeds max compact frame size (65535 bytes)")
        
    header = struct.pack(
        HEADER_STRUCT_FORMAT,
        MAGIC_BYTES,
        PROTOCOL_VERSION,
        type_code,
        seq_id & 0xFFFFFFFF,
        flags,
        timestamp_ms,
        ttl & 0xFF,
        payload_len
    )
    
    return header + final_payload


def unpack_compact_frame(frame_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Unpack and decompress a binary frame into its header fields and raw payload.
    """
    if len(frame_bytes) < HEADER_SIZE:
        return None
        
    try:
        magic, version, type_code, seq_id, flags, timestamp_ms, ttl, payload_len = struct.unpack(
            HEADER_STRUCT_FORMAT,
            frame_bytes[:HEADER_SIZE]
        )
        
        if magic != MAGIC_BYTES:
            return None
            
        payload = frame_bytes[HEADER_SIZE:HEADER_SIZE + payload_len]
        if len(payload) < payload_len:
            return None
            
        is_compressed = bool(flags & FLAG_COMPRESSED)
        is_priority = bool(flags & FLAG_PRIORITY)
        is_encrypted = bool(flags & FLAG_ENCRYPTED)
        
        if is_compressed:
            try:
                payload = zlib.decompress(payload)
            except Exception as e:
                print(f"[CompactFraming] Decompression error: {e}")
                return None
                
        packet_type = REVERSE_PACKET_TYPES.get(type_code, "GENERIC_JSON")
        
        return {
            "version": version,
            "packet_type": packet_type,
            "seq_id": seq_id,
            "flags": flags,
            "is_compressed": is_compressed,
            "is_priority": is_priority,
            "is_encrypted": is_encrypted,
            "timestamp_ms": timestamp_ms,
            "ttl": ttl,
            "payload": payload
        }
    except Exception as e:
        print(f"[CompactFraming] Unpack error: {e}")
        return None


def json_to_compact_frame(json_obj: Dict[str, Any], auto_compress: bool = True) -> bytes:
    """
    Serialize a standard Gost-Net dictionary to a compact binary frame.
    """
    packet_type = json_obj.get("type", "GENERIC_JSON")
    payload_bytes = json.dumps(json_obj).encode('utf-8')
    seq_id = zlib.crc32(payload_bytes)
    ttl = int(json_obj.get("network_ttl", 15))
    
    return pack_compact_frame(
        packet_type=packet_type,
        payload_data=payload_bytes,
        seq_id=seq_id,
        ttl=ttl,
        auto_compress=auto_compress
    )


def compact_frame_to_json(frame_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Deserialize a compact binary frame back into a standard dictionary.
    """
    unpacked = unpack_compact_frame(frame_bytes)
    if not unpacked:
        return None
        
    try:
        decoded_json = json.loads(unpacked["payload"].decode('utf-8'))
        return decoded_json
    except Exception:
        # Return structured metadata if raw binary payload
        return unpacked
