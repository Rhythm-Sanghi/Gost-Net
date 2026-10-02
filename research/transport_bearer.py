"""
Modular Multi-Bearer Tactical Radio Gateway and MTU Fragmentation Engine.
Enables Gost-Net to communicate across heterogeneous physical bearers (TCP, Serial, LoRa, Acoustic).
"""

import abc
import struct
import time
import zlib
import threading
from typing import Dict, List, Optional, Tuple, Callable, Any

# 4-byte Magic header for fragments
FRAG_MAGIC = b'FRAG'
# Header format: 4s (magic), I (frag_id uint32), H (frag_idx uint16), H (frag_total uint16), I (crc32)
FRAG_HEADER_FORMAT = "!4sIHHI"
FRAG_HEADER_SIZE = struct.calcsize(FRAG_HEADER_FORMAT)


class PacketFragmenter:
    """
    Segmentation and Reassembly (SAR) Engine for low-MTU tactical radio links.
    Slices large packets into MTU-sized frames and reassembles them with checksum verification.
    """

    def __init__(self, reassembly_timeout: float = 15.0):
        self.reassembly_timeout = reassembly_timeout
        self.fragment_buffers: Dict[int, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.frag_counter = 0

    def fragment_packet(self, packet_bytes: bytes, mtu: int) -> List[bytes]:
        """
        Slice a packet into fragments that fit within the specified bearer MTU.
        """
        if mtu <= FRAG_HEADER_SIZE:
            raise ValueError(f"Bearer MTU ({mtu}) is too small to accommodate fragment headers ({FRAG_HEADER_SIZE})")

        max_payload_per_frag = mtu - FRAG_HEADER_SIZE
        total_len = len(packet_bytes)

        if total_len <= max_payload_per_frag:
            # Single fragment
            with self.lock:
                self.frag_counter = (self.frag_counter + 1) & 0xFFFFFFFF
                frag_id = self.frag_counter
            crc = zlib.crc32(packet_bytes)
            header = struct.pack(FRAG_HEADER_FORMAT, FRAG_MAGIC, frag_id, 0, 1, crc)
            return [header + packet_bytes]

        # Multi-fragment slicing
        with self.lock:
            self.frag_counter = (self.frag_counter + 1) & 0xFFFFFFFF
            frag_id = self.frag_counter

        crc = zlib.crc32(packet_bytes)
        chunks = [
            packet_bytes[i:i + max_payload_per_frag]
            for i in range(0, total_len, max_payload_per_frag)
        ]
        total_frags = len(chunks)

        fragments = []
        for idx, chunk in enumerate(chunks):
            header = struct.pack(FRAG_HEADER_FORMAT, FRAG_MAGIC, frag_id, idx, total_frags, crc)
            fragments.append(header + chunk)

        return fragments

    def reassemble_fragment(self, frame_bytes: bytes) -> Optional[bytes]:
        """
        Process an incoming fragment. If all fragments for the sequence have arrived,
        reassembles and returns the verified full packet payload.
        """
        if len(frame_bytes) < FRAG_HEADER_SIZE:
            return None

        try:
            magic, frag_id, frag_idx, frag_total, expected_crc = struct.unpack(
                FRAG_HEADER_FORMAT,
                frame_bytes[:FRAG_HEADER_SIZE]
            )
            if magic != FRAG_MAGIC:
                return None

            payload_chunk = frame_bytes[FRAG_HEADER_SIZE:]
            now = time.time()

            with self.lock:
                # Cleanup expired incomplete fragment sets
                expired_keys = [
                    k for k, v in self.fragment_buffers.items()
                    if now - v["timestamp"] > self.reassembly_timeout
                ]
                for k in expired_keys:
                    del self.fragment_buffers[k]

                if frag_id not in self.fragment_buffers:
                    self.fragment_buffers[frag_id] = {
                        "total": frag_total,
                        "expected_crc": expected_crc,
                        "timestamp": now,
                        "chunks": {}
                    }

                buf = self.fragment_buffers[frag_id]
                buf["chunks"][frag_idx] = payload_chunk
                buf["timestamp"] = now

                # Check if all fragments are collected
                if len(buf["chunks"]) == buf["total"]:
                    full_payload = b"".join(
                        buf["chunks"][i] for i in range(buf["total"])
                    )
                    del self.fragment_buffers[frag_id]

                    actual_crc = zlib.crc32(full_payload)
                    if actual_crc == expected_crc:
                        return full_payload
                    else:
                        print(f"[PacketFragmenter] Checksum mismatch! Expected {expected_crc}, got {actual_crc}")
                        return None
        except Exception as e:
            print(f"[PacketFragmenter] Error reassembling fragment: {e}")
            return None

        return None


class TransportBearer(abc.ABC):
    """
    Abstract base class for all physical and virtual transport bearers.
    """

    def __init__(self, bearer_name: str, mtu: int):
        self.bearer_name = bearer_name
        self.mtu = mtu
        self.is_running = False
        self.on_data_received: Optional[Callable[[bytes, str], None]] = None

    @abc.abstractmethod
    def start(self) -> bool:
        pass

    @abc.abstractmethod
    def stop(self):
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        pass

    @abc.abstractmethod
    def send(self, data: bytes, target_address: Optional[str] = None) -> bool:
        pass


class SerialRadioBearer(TransportBearer):
    """
    Serial / UART Radio Bearer for external LoRa modules (e.g. SX1262, Meshtastic serial bridge).
    Includes loopback/mock fallback for systems without physical USB-UART transceivers attached.
    """

    def __init__(self, port: str = "COM1", baudrate: int = 115200, mtu: int = 220):
        super().__init__(bearer_name=f"LoRa-Serial({port})", mtu=mtu)
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.use_mock = False
        self.mock_rx_buffer: List[bytes] = []
        self.mock_lock = threading.Lock()

    def start(self) -> bool:
        try:
            import serial
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1.0)
            self.is_running = True
            print(f"[SerialRadioBearer] Opened hardware radio serial port {self.port}")
            return True
        except Exception:
            # Fallback to simulated/virtual serial transceiver
            self.use_mock = True
            self.is_running = True
            print(f"[SerialRadioBearer] Hardware serial unavailable; operating in loopback/simulated radio mode on {self.port}")
            return True

    def stop(self):
        self.is_running = False
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

    def is_available(self) -> bool:
        return self.is_running

    def send(self, data: bytes, target_address: Optional[str] = None) -> bool:
        if not self.is_running:
            return False

        if self.serial_conn and not self.use_mock:
            try:
                self.serial_conn.write(data)
                self.serial_conn.flush()
                return True
            except Exception as e:
                print(f"[SerialRadioBearer] Serial transmission error: {e}")
                return False
        else:
            # Mock transmission
            with self.mock_lock:
                self.mock_rx_buffer.append(data)
            return True

    def inject_mock_rx(self, data: bytes, sender: str = "LORA_REMOTE"):
        """Simulate receipt of radio frame over RF."""
        if self.on_data_received:
            self.on_data_received(data, sender)


class BearerManager:
    """
    Manages multiple active physical bearers, handles MTU adaptation, and transparent SAR.
    """

    def __init__(self):
        self.bearers: Dict[str, TransportBearer] = {}
        self.fragmenter = PacketFragmenter()
        self.on_packet_received: Optional[Callable[[bytes, str, str], None]] = None
        self.lock = threading.Lock()

    def register_bearer(self, bearer: TransportBearer):
        with self.lock:
            self.bearers[bearer.bearer_name] = bearer
            bearer.on_data_received = lambda data, sender: self._handle_raw_bearer_data(data, sender, bearer.bearer_name)
            print(f"[BearerManager] Registered transport bearer: {bearer.bearer_name} (MTU: {bearer.mtu})")

    def unregister_bearer(self, bearer_name: str):
        with self.lock:
            if bearer_name in self.bearers:
                self.bearers[bearer_name].stop()
                del self.bearers[bearer_name]

    def _handle_raw_bearer_data(self, raw_data: bytes, sender: str, bearer_name: str):
        """Process incoming raw bearer frame, reassembling if fragmented."""
        reassembled = self.fragmenter.reassemble_fragment(raw_data)
        if reassembled:
            if self.on_packet_received:
                self.on_packet_received(reassembled, sender, bearer_name)

    def send_packet(self, packet_bytes: bytes, preferred_bearer: Optional[str] = None, target_address: Optional[str] = None) -> bool:
        """
        Send a packet over the specified or highest-MTU available bearer, fragmenting if necessary.
        """
        with self.lock:
            selected_bearer = None
            if preferred_bearer and preferred_bearer in self.bearers:
                selected_bearer = self.bearers[preferred_bearer]
            else:
                # Select available bearer
                available = [b for b in self.bearers.values() if b.is_available()]
                if available:
                    selected_bearer = available[0]

            if not selected_bearer:
                return False

            fragments = self.fragmenter.fragment_packet(packet_bytes, selected_bearer.mtu)
            for frag in fragments:
                success = selected_bearer.send(frag, target_address)
                if not success:
                    return False

            return True
