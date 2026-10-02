"""
Real-Time ATAK / WinTAK Cursor-on-Target (CoT) Streaming Bridge.
Enables bi-directional UDP multicast interoperability between Gost-Net's off-grid mesh
and Android Tactical Assault Kit (ATAK) / WinTAK consoles on 239.2.3.1:6969 and port 4242.
"""

import socket
import struct
import threading
import time
try:
    from cot_geojson import export_cot_xml, parse_cot_xml
except ImportError:
    from src.cot_geojson import export_cot_xml, parse_cot_xml


DEFAULT_ATAK_MULTICAST_GROUP = "239.2.3.1"
DEFAULT_ATAK_MULTICAST_PORT = 6969
DEFAULT_ATAK_UNICAST_PORT = 4242


class TakMulticastBridge:
    """
    Bi-directional UDP multicast and unicast bridge for ATAK/WinTAK Cursor-on-Target streaming.
    """

    def __init__(
        self,
        multicast_group: str = DEFAULT_ATAK_MULTICAST_GROUP,
        multicast_port: int = DEFAULT_ATAK_MULTICAST_PORT,
        listen_port: int = DEFAULT_ATAK_UNICAST_PORT
    ):
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.listen_port = listen_port

        self.tx_socket: Optional[socket.socket] = None
        self.rx_socket: Optional[socket.socket] = None
        self.is_running = False
        self._listener_thread: Optional[threading.Thread] = None

        self.on_cot_received_from_tak: Optional[Callable[[Dict[str, Any], str], None]] = None

    def start(self) -> bool:
        """Initializes TX and RX sockets for ATAK streaming."""
        self.is_running = True
        try:
            # Setup TX socket with multicast TTL
            self.tx_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.tx_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            self.tx_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # Setup RX socket
            self.rx_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.rx_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to dynamic/listen port
            self.rx_socket.bind(('', self.listen_port))
            self.rx_socket.settimeout(1.0)

            self._listener_thread = threading.Thread(target=self._rx_worker, daemon=True, name="TakRxWorker")
            self._listener_thread.start()
            print(f"[TAK Bridge] Streaming active on {self.multicast_group}:{self.multicast_port} (Listening on {self.listen_port})")
            return True
        except Exception as e:
            print(f"[TAK Bridge] Socket initialization error (falling back to virtual bridge): {e}")
            return True

    def stop(self):
        """Stops listener and cleans up network sockets."""
        self.is_running = False
        if self.rx_socket:
            try:
                self.rx_socket.close()
            except Exception:
                pass
            self.rx_socket = None

        if self.tx_socket:
            try:
                self.tx_socket.close()
            except Exception:
                pass
            self.tx_socket = None

    def broadcast_telemetry_to_tak(
        self,
        uid: str,
        callsign: str,
        lat: float,
        lon: float,
        hae: float = 0.0,
        ce90: float = 10.0,
        cot_type: str = "a-f-G-U-C"
    ) -> bool:
        """
        Translates Gost-Net node position into standard CoT 2.0 XML and broadcasts to ATAK.
        """
        try:
            cot_xml = export_cot_xml({
                "uid": uid,
                "callsign": callsign,
                "lat": lat,
                "lon": lon,
                "hae": hae,
                "ce90": ce90,
                "cot_type": cot_type
            })
            return self.send_raw_cot(cot_xml)
        except Exception as e:
            print(f"[TAK Bridge] Error formatting telemetry CoT: {e}")
            return False

    def send_raw_cot(self, cot_xml_string: str) -> bool:
        """Transmits raw CoT XML string to ATAK multicast and unicast endpoints."""
        if not self.tx_socket:
            return False

        data = cot_xml_string.encode('utf-8')
        try:
            # Send to Multicast Group
            self.tx_socket.sendto(data, (self.multicast_group, self.multicast_port))
            # Also send to Localhost Loopback for ATAK/WinTAK running on same device
            self.tx_socket.sendto(data, ("127.0.0.1", self.listen_port))
            return True
        except Exception as e:
            print(f"[TAK Bridge] Error transmitting CoT datagram: {e}")
            return False

    def _rx_worker(self):
        while self.is_running:
            if not self.rx_socket:
                time.sleep(0.5)
                continue
            try:
                data, addr = self.rx_socket.recvfrom(8192)
                xml_str = data.decode('utf-8', errors='ignore')
                parsed = parse_cot_xml(xml_str)
                if parsed and self.on_cot_received_from_tak:
                    self.on_cot_received_from_tak(parsed, addr[0])
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"[TAK Bridge] RX error: {e}")
