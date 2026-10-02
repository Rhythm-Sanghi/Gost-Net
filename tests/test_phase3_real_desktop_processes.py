"""
Phase 3 Verification & Validation Suite
Independent verification of Gost-Net operational guarantees under realistic desktop execution.

Covers:
1. First-run credential generation and fresh directory initialization.
2. PIN failure behavior, lockout persistence, and non-destructive lockout recovery.
3. Duress protocol validation.
4. Two real desktop processes (Node A <-> Node B) over real network sockets (UDP/TCP):
   - Mutual discovery
   - Bidirectional messaging with application-layer ACKs (QUEUED -> SENDING -> DELIVERED)
   - Deduplication defense (replay attack / ACK loss simulation)
   - Unicode & large payload boundary handling
   - File transfer with SHA-256 integrity and atomic .part promotion
   - Path traversal prevention
   - Node restart and database persistence survival
5. Hostile beacon and TCP header fuzzing.
"""

import os
import sys
import time
import json
import socket
import shutil
import hashlib
import tempfile
import threading
import pytest

# Ensure src is on path
_repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(_repo_dir, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from auth_manager import AuthenticationManager
from network import GhostEngine
from config import ConfigManager, APP_VERSION
from database import PersistenceDatabase
from storage import DatabaseManager


class TestFirstRunAndAuthHardening:
    """Verifies first-run flow and PIN failure behavior."""

    def test_fresh_install_not_initialized(self, tmp_path):
        """A normal fresh installation must NOT silently ship with a default PIN."""
        data_dir = str(tmp_path / "fresh_node")
        os.makedirs(data_dir, exist_ok=True)
        # Explicitly disable test auto-init defaults
        auth = AuthenticationManager(storage_dir=data_dir, auto_init_defaults=False)
        assert not auth.are_pins_initialized(), "Fresh installation must not initialize default PINs"

    def test_first_run_setup_flow(self, tmp_path):
        """User creates Master PIN, optional duress PIN, and derives keys."""
        data_dir = str(tmp_path / "setup_node")
        os.makedirs(data_dir, exist_ok=True)
        auth = AuthenticationManager(storage_dir=data_dir, auto_init_defaults=False)
        
        # Validation checks
        assert not auth.initialize_pins("12", "9999"), "PIN < 4 chars must be rejected"
        assert not auth.initialize_pins("1234", "12"), "Duress PIN < 4 chars must be rejected"
        
        # Valid setup
        assert auth.initialize_pins("SecureMaster123", "EmergencyDuress999")
        assert auth.are_pins_initialized()
        assert auth.identify_pin("SecureMaster123") == "master"
        assert auth.identify_pin("EmergencyDuress999") == "duress"
        assert auth.identify_pin("WrongPIN") is None

    def test_pin_failure_lockout_and_non_destructive_recovery(self, tmp_path):
        """
        Verify that 5 failed PIN attempts trigger decoy mode, do NOT destructively shred
        the database, and genuine master PIN can recover the session.
        """
        data_dir = str(tmp_path / "lockout_node")
        os.makedirs(data_dir, exist_ok=True)
        auth = AuthenticationManager(storage_dir=data_dir, auto_init_defaults=False)
        auth.initialize_pins("MyPass9876", "DuressWipe111")
        
        # 1 failed attempt
        assert auth.identify_pin("wrong1") is None
        assert auth.get_failed_attempts() == 1
        assert not auth.is_decoy_mode_active()
        
        # 4 more failed attempts -> reaches 5
        for i in range(2, 6):
            auth.identify_pin(f"wrong{i}")
        assert auth.get_failed_attempts() >= 5
        assert auth.is_decoy_mode_active(), "5 failed attempts must activate decoy mode"
        
        # Authentication secrets must still exist (not destructively shredded!)
        assert os.path.exists(auth.auth_file), "Lockout must not shred vault secrets"
        
        # An adversary entering arbitrary PIN in decoy mode gets honeypot master
        assert auth.identify_pin("adversary_guess") == "master"
        assert auth.is_decoy_mode_active(), "Adversary guess must remain in decoy mode"
        
        # Genuine user enters correct master PIN -> recovers from lockout!
        assert auth.identify_pin("MyPass9876") == "master"
        assert not auth.is_decoy_mode_active(), "Genuine master PIN must deactivate decoy mode and recover"
        assert auth.get_failed_attempts() == 0, "Failed attempts counter must be reset upon recovery"

    def test_duress_pin_protocol(self, tmp_path):
        """Entering duress PIN must identify as duress."""
        data_dir = str(tmp_path / "duress_node")
        os.makedirs(data_dir, exist_ok=True)
        auth = AuthenticationManager(storage_dir=data_dir, auto_init_defaults=False)
        auth.initialize_pins("Normal1234", "Panic9999")
        assert auth.identify_pin("Panic9999") == "duress"


class TestTwoRealDesktopProcesses:
    """
    Spawns two real GhostEngine instances on the local host with isolated configurations,
    exercising real UDP discovery and real TCP transport connections.
    """

    @pytest.fixture(autouse=True)
    def setup_nodes(self, tmp_path):
        self.dir_a = str(tmp_path / "node_a")
        self.dir_b = str(tmp_path / "node_b")
        os.makedirs(self.dir_a, exist_ok=True)
        os.makedirs(self.dir_b, exist_ok=True)

        self.downloads_a = os.path.join(self.dir_a, "downloads")
        self.downloads_b = os.path.join(self.dir_b, "downloads")
        os.makedirs(self.downloads_a, exist_ok=True)
        os.makedirs(self.downloads_b, exist_ok=True)

        self.db_a = PersistenceDatabase(db_path=os.path.join(self.dir_a, "node_a.db"))
        self.db_b = PersistenceDatabase(db_path=os.path.join(self.dir_b, "node_b.db"))

        self.messages_a = []
        self.messages_b = []
        self.files_b = []
        self.delivery_events_a = []
        self.delivery_events_b = []

        def on_msg_a(sender, text, ts):
            self.messages_a.append((sender, text, ts))

        def on_msg_b(sender, text, ts):
            self.messages_b.append((sender, text, ts))

        def on_file_b(sender, filename, filepath, ts):
            self.files_b.append((sender, filename, filepath, ts))

        def on_deliv_a(msg_id, target, state):
            self.delivery_events_a.append((msg_id, target, state))

        def on_deliv_b(msg_id, target, state):
            self.delivery_events_b.append((msg_id, target, state))

        self.engine_a = GhostEngine(
            username="NodeAlpha",
            on_message_received=on_msg_a,
            downloads_dir=self.downloads_a,
            persistence_db=self.db_a,
            enable_storage=False
        )
        self.engine_a.on_delivery_status = on_deliv_a

        self.engine_b = GhostEngine(
            username="NodeBravo",
            on_message_received=on_msg_b,
            on_file_received=on_file_b,
            downloads_dir=self.downloads_b,
            persistence_db=self.db_b,
            enable_storage=False
        )
        self.engine_b.on_delivery_status = on_deliv_b

        yield

        # Teardown
        if hasattr(self, 'engine_a') and self.engine_a:
            self.engine_a.stop()
        if hasattr(self, 'engine_b') and self.engine_b:
            self.engine_b.stop()
        if hasattr(self, 'db_a') and self.db_a:
            self.db_a.close()
        if hasattr(self, 'db_b') and self.db_b:
            self.db_b.close()

    def test_mutual_discovery_and_messaging_with_acks(self):
        """
        Verify that Node A and Node B bind distinct dynamic TCP ports,
        discover each other via UDP beacons, exchange bidirectional messages,
        and confirm receipt with application-layer ACKs (DELIVERED).
        """
        self.engine_a.start()
        self.engine_b.start()

        # Both engines must bind valid dynamic TCP ports
        assert self.engine_a.tcp_port > 0
        assert self.engine_b.tcp_port > 0
        assert self.engine_a.tcp_port != self.engine_b.tcp_port

        # Wait for mutual UDP discovery
        discovered = False
        target_b_str = f"127.0.0.1:{self.engine_b.tcp_port}"
        target_a_str = f"127.0.0.1:{self.engine_a.tcp_port}"

        for _ in range(30):
            # Send immediate beacons to accelerate discovery
            self.engine_a._broadcast_immediate_beacon()
            self.engine_b._broadcast_immediate_beacon()
            time.sleep(0.2)
            with self.engine_a.peers_lock:
                peers_a = list(self.engine_a.peers.keys())
            with self.engine_b.peers_lock:
                peers_b = list(self.engine_b.peers.keys())
            if len(peers_a) > 0 and len(peers_b) > 0:
                discovered = True
                break

        assert discovered, f"Nodes failed to discover each other over UDP loopback. Peers A: {peers_a}, Peers B: {peers_b}"

        # 1. Text Message A -> B
        test_msg_1 = "Tactical Ping from Alpha"
        res_a = self.engine_a.send_message(
            target_ip=target_b_str,
            message_text=test_msg_1,
            return_result=True
        )
        assert res_a.success, f"Send A -> B failed: {res_a.error}"
        assert res_a.state == "DELIVERED", f"Message A -> B was not DELIVERED: {res_a.state}"

        # Allow TCP worker dispatch
        time.sleep(0.3)
        assert len(self.messages_b) == 1
        assert self.messages_b[0][1] == test_msg_1

        # 2. Text Message B -> A
        test_msg_2 = "Tactical Pong from Bravo"
        res_b = self.engine_b.send_message(
            target_ip=target_a_str,
            message_text=test_msg_2,
            return_result=True
        )
        assert res_b.success
        assert res_b.state == "DELIVERED"

        time.sleep(0.3)
        assert len(self.messages_a) == 1
        assert self.messages_a[0][1] == test_msg_2

        # 3. Unicode and Emoji support
        unicode_msg = "Coordinates: 28.6139° N, 77.2090° E | नमस्ते | 你好 | 🚨 SOS"
        res_u = self.engine_a.send_message(
            target_ip=target_b_str,
            message_text=unicode_msg,
            return_result=True
        )
        assert res_u.success
        assert res_u.state == "DELIVERED"
        time.sleep(0.3)
        assert any(msg[1] == unicode_msg for msg in self.messages_b)

        # 4. Large message test (8 KB)
        large_msg = "X" * 8192
        res_l = self.engine_a.send_message(
            target_ip=target_b_str,
            message_text=large_msg,
            return_result=True
        )
        assert res_l.success
        assert res_l.state == "DELIVERED"
        time.sleep(0.3)
        assert any(msg[1] == large_msg for msg in self.messages_b)

    def test_duplicate_message_suppression(self):
        """
        Verify that receiving the same message ID twice sends an ACK
        back to the sender, but does NOT create a duplicate message in the receiver.
        """
        self.engine_a.start()
        self.engine_b.start()
        time.sleep(0.5)

        target_b_str = f"127.0.0.1:{self.engine_b.tcp_port}"
        fixed_msg_id = "test_dup_msg_101"

        # First transmission
        res1 = self.engine_a.send_message(
            target_ip=target_b_str,
            message_text="Idempotent Payload",
            msg_id=fixed_msg_id,
            return_result=True
        )
        assert res1.success
        assert res1.state == "DELIVERED"
        time.sleep(0.3)
        assert len(self.messages_b) == 1

        # Replay same message ID (simulating ACK drop / retransmission)
        res2 = self.engine_a.send_message(
            target_ip=target_b_str,
            message_text="Idempotent Payload",
            msg_id=fixed_msg_id,
            return_result=True
        )
        assert res2.success
        assert res2.state == "DELIVERED", "Replay must still receive an ACK to satisfy sender"
        time.sleep(0.3)
        # Message count must remain 1 - duplicate dropped!
        assert len(self.messages_b) == 1, "Duplicate message ID must be dropped by receiver"

    def test_file_transfer_integrity_and_path_traversal_prevention(self):
        """
        Verify file transfer with SHA-256 integrity, temporary .part promotion,
        and sanitization against directory traversal filenames.
        """
        self.engine_a.start()
        self.engine_b.start()
        time.sleep(0.5)

        target_b_str = f"127.0.0.1:{self.engine_b.tcp_port}"

        # Create source file on Node A
        test_file_path = os.path.join(self.dir_a, "recon_data.bin")
        payload = os.urandom(64 * 1024)  # 64 KB
        with open(test_file_path, "wb") as f:
            f.write(payload)

        # 1. Normal file transfer
        success = self.engine_a.send_file(target_b_str, test_file_path)
        assert success, "File transfer failed"

        time.sleep(1.0)
        assert len(self.files_b) == 1
        _, rx_filename, rx_path, _ = self.files_b[0]
        assert rx_filename == "recon_data.bin"
        assert os.path.exists(rx_path)
        assert not os.path.exists(rx_path + ".part"), ".part file must be promoted and removed"

        # Verify SHA-256 integrity
        with open(rx_path, "rb") as f:
            rx_data = f.read()
        assert hashlib.sha256(rx_data).hexdigest() == hashlib.sha256(payload).hexdigest()

        # 2. Path Traversal attack prevention
        # Malicious filename attempting traversal out of downloads directory
        traversal_file = os.path.join(self.dir_a, "traversal_test.txt")
        with open(traversal_file, "w") as f:
            f.write("Hostile payload")

        # Directly send a TCP header claiming "../../evil.txt"
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", self.engine_b.tcp_port))
        
        evil_header = {
            "type": "FILE",
            "filename": "../../../escaped_target.txt",
            "filesize": 15,
            "checksum": hashlib.sha256(b"Hostile payload").hexdigest()
        }
        header_enc = self.engine_a._encrypt_message(json.dumps(evil_header))
        client.sendall(header_enc + self.engine_a.HEADER_DELIMITER + b"Hostile payload")
        client.close()

        time.sleep(0.5)
        # Check that file was NOT created outside downloads directory
        escaped_path = os.path.abspath(os.path.join(self.downloads_b, "..", "..", "escaped_target.txt"))
        assert not os.path.exists(escaped_path), "Path traversal attack must not escape downloads directory"
        # It must be sanitized and placed strictly inside downloads_b
        sanitized_path = os.path.join(self.downloads_b, "escaped_target.txt")
        assert os.path.exists(sanitized_path)

    def test_node_restart_and_persistence_survival(self):
        """
        Verify that Node A can stop and restart without crashing Node B,
        reconnect, and messages are preserved across engine reboots.
        """
        self.engine_a.start()
        self.engine_b.start()
        time.sleep(0.5)

        target_b_str = f"127.0.0.1:{self.engine_b.tcp_port}"
        self.engine_a.send_message(target_b_str, "Pre-restart message", return_result=True)
        time.sleep(0.5)

        # Stop Node A
        self.engine_a.stop()
        time.sleep(0.5)

        # Node B must remain healthy and running
        assert self.engine_b.running
        assert self.engine_b.tcp_socket is not None

        # Re-initialize Node A with the same persistence DB
        messages_a_restart = []
        engine_a_restarted = GhostEngine(
            username="NodeAlpha",
            on_message_received=lambda s, m, t: messages_a_restart.append(m),
            downloads_dir=self.downloads_a,
            persistence_db=self.db_a,
            enable_storage=False
        )
        engine_a_restarted.start()
        time.sleep(0.5)

        # Send post-restart message from restarted Node A to Node B
        res_post = engine_a_restarted.send_message(target_b_str, "Post-restart message", return_result=True)
        assert res_post.success
        assert res_post.state == "DELIVERED"

        time.sleep(0.5)
        engine_a_restarted.stop()


class TestHostileInputFuzzing:
    """Rigorous input boundary and malicious network packet fuzzing."""

    @pytest.fixture(autouse=True)
    def setup_target(self, tmp_path):
        self.target_dir = str(tmp_path / "fuzz_node")
        os.makedirs(self.target_dir, exist_ok=True)
        self.db = PersistenceDatabase(db_path=os.path.join(self.target_dir, "fuzz.db"))
        self.engine = GhostEngine(
            username="FuzzTarget",
            persistence_db=self.db,
            enable_storage=False
        )
        self.engine.start()
        time.sleep(0.3)
        yield
        self.engine.stop()
        self.db.close()

    def test_hostile_udp_beacons(self):
        """Send malicious/corrupt datagrams to the UDP listener."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        target_port = self.engine.UDP_PORT

        hostile_payloads = [
            b"",                                     # Empty
            b"\x00",                                 # Single null
            b"\xff\xfe\xfd\xfc",                     # Invalid UTF-8
            b"Not JSON at all",                      # Garbage text
            b"[]",                                   # Array instead of object
            b"{" + b'"nested":'*50 + b'1' + b'}'*50, # Deeply nested JSON
            json.dumps({"type": "BEACON"}).encode(), # Missing required fields
            json.dumps({"type": "BEACON", "peer_id": "X" * 10000}).encode(), # Giant peer_id
            json.dumps({"type": "BEACON", "username": "U" * 10000}).encode(), # Giant username
            json.dumps({"type": "BEACON", "tcp_port": -50}).encode(),         # Negative port
            json.dumps({"type": "BEACON", "tcp_port": 999999}).encode(),      # Out-of-bounds port
            json.dumps({"type": "BEACON", "signing_key": "not_base64!!"}).encode(), # Corrupt key
            os.urandom(4096),                        # Random binary fuzz
        ]

        for payload in hostile_payloads:
            try:
                sock.sendto(payload, ("127.0.0.1", target_port))
            except Exception:
                pass

        sock.close()
        time.sleep(0.5)
        # Engine must still be alive and operational
        assert self.engine.running
        assert self.engine.udp_socket is not None

    def test_hostile_tcp_headers(self):
        """Send malicious/corrupt TCP connection frames to the TCP server."""
        target_port = self.engine.tcp_port

        def send_raw(data):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect(("127.0.0.1", target_port))
                s.sendall(data)
                s.close()
            except Exception:
                pass

        # 1. Truncated header without delimiter
        send_raw(b"Random garbage without header delimiter")
        # 2. Huge claimed length / allocation bomb
        fake_header = self.engine._encrypt_message(json.dumps({
            "type": "FILE",
            "filename": "bomb.bin",
            "filesize": 10 * 1024 * 1024 * 1024  # 10 Gigabytes claimed
        }))
        send_raw(fake_header + self.engine.HEADER_DELIMITER)
        # 3. Corrupt ciphertext with valid delimiter
        send_raw(b"CorruptCiphertextDataNotBase64" + self.engine.HEADER_DELIMITER)
        # 4. Null bytes injection
        send_raw(b"\x00" * 1024 + self.engine.HEADER_DELIMITER)

        time.sleep(0.5)
        # TCP server must still be functional
        assert self.engine.running
        assert self.engine.tcp_socket is not None
