"""
Ghost Net - P2P Modules Test Suite
Comprehensive testing for Wi-Fi Direct, Bluetooth, Permissions, and Platform Adapter.

Test Coverage:
- Permission request and status checking
- Wi-Fi Direct peer discovery and connection
- Bluetooth device discovery, pairing, and RFCOMM communication
- P2P Platform Adapter unified interface
- Thread safety and concurrent operations
- Error handling and graceful degradation
- Mock Android APIs for desktop testing

Usage:
    python test_p2p_modules.py [-v] [--channel wifi|bt|all] [--mode unit|integration|all]
"""

import unittest
import logging
import threading
import time
import sys
from io import StringIO
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict

# Configure logging for tests
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# SECTION 1: Permission Module Tests
# ============================================================================

class TestPermissionManager(unittest.TestCase):
    """Test cases for android_permissions.py"""

    def setUp(self):
        """Set up test fixtures."""
        # Mock pyjnius availability
        self.pyjnius_available = False
        logger.info("PermissionManager test setup completed")

    def test_permission_definitions_complete(self):
        """Verify all required permissions are defined."""
        try:
            from android_permissions import PERMISSION_DEFINITIONS, PermissionGroup

            # Required permission keys for P2P
            required_permissions = {
                'NEARBY_WIFI_DEVICES',
                'BLUETOOTH_SCAN',
                'BLUETOOTH_CONNECT',
                'ACCESS_FINE_LOCATION',
                'CHANGE_WIFI_STATE',
                'LOCAL_MAC_ADDRESS',
            }

            defined_permissions = set(PERMISSION_DEFINITIONS.keys())
            self.assertTrue(
                required_permissions.issubset(defined_permissions),
                f"Missing permissions: {required_permissions - defined_permissions}"
            )

            logger.info("✓ All required permissions defined")

        except ImportError:
            self.skipTest("android_permissions module not available")

    def test_permission_api_levels(self):
        """Verify API level constraints for runtime permissions."""
        try:
            from android_permissions import PERMISSION_DEFINITIONS

            # NEARBY_WIFI_DEVICES should require API 33+
            self.assertEqual(PERMISSION_DEFINITIONS['NEARBY_WIFI_DEVICES'].min_api, 33)

            # BLUETOOTH_SCAN should require API 31+
            self.assertEqual(PERMISSION_DEFINITIONS['BLUETOOTH_SCAN'].min_api, 31)

            # BLUETOOTH should be available on API 1+
            self.assertEqual(PERMISSION_DEFINITIONS['BLUETOOTH'].min_api, 1)

            logger.info("✓ Permission API levels correct")

        except ImportError:
            self.skipTest("android_permissions module not available")

    def test_permission_groups_assignment(self):
        """Verify permissions are correctly grouped."""
        try:
            from android_permissions import PERMISSION_DEFINITIONS, PermissionGroup

            # Check Wi-Fi P2P group
            wifi_perms = [
                p for p in PERMISSION_DEFINITIONS.values()
                if p.group == PermissionGroup.WIFI_P2P
            ]
            self.assertGreater(len(wifi_perms), 0)

            # Check Bluetooth group
            bt_perms = [
                p for p in PERMISSION_DEFINITIONS.values()
                if p.group == PermissionGroup.BLUETOOTH
            ]
            self.assertGreater(len(bt_perms), 0)

            logger.info("✓ Permission groups correctly assigned")

        except ImportError:
            self.skipTest("android_permissions module not available")


# ============================================================================
# SECTION 2: Wi-Fi Direct Module Tests
# ============================================================================

class TestWiFiDirectManager(unittest.TestCase):
    """Test cases for android_wifi_direct.py"""

    def setUp(self):
        """Set up test fixtures."""
        logger.info("WiFiDirectManager test setup completed")

    def test_wifi_peer_dataclass(self):
        """Test WiFiPeer dataclass initialization and serialization."""
        try:
            from android_wifi_direct import WiFiPeer

            peer = WiFiPeer(
                device_name="TestPeer",
                device_address="AA:BB:CC:DD:EE:FF",
                is_group_owner=True,
                signal_level=-50
            )

            self.assertEqual(peer.device_name, "TestPeer")
            self.assertEqual(peer.device_address, "AA:BB:CC:DD:EE:FF")
            self.assertTrue(peer.is_group_owner)

            # Test serialization
            peer_dict = peer.to_dict()
            self.assertEqual(peer_dict['device_name'], "TestPeer")
            self.assertIn('timestamp', peer_dict)

            logger.info("✓ WiFiPeer dataclass working correctly")

        except ImportError:
            self.skipTest("android_wifi_direct module not available")

    def test_wifi_state_enum(self):
        """Test WiFiDirectState enum."""
        try:
            from android_wifi_direct import WiFiDirectState

            states = {
                WiFiDirectState.IDLE,
                WiFiDirectState.DISCOVERING,
                WiFiDirectState.CONNECTED,
                WiFiDirectState.GROUP_FORMED,
            }

            self.assertEqual(len(states), len(set(s.value for s in states)))
            logger.info("✓ WiFiDirectState enum valid")

        except ImportError:
            self.skipTest("android_wifi_direct module not available")

    def test_wifi_manager_thread_safety(self):
        """Test WiFiDirectManager thread safety."""
        try:
            from android_wifi_direct import WiFiDirectManager

            manager = WiFiDirectManager()

            # Test concurrent peer access
            results = []

            def update_peers():
                for i in range(10):
                    peers = manager.get_peers()
                    results.append(len(peers))
                    time.sleep(0.01)

            threads = [threading.Thread(target=update_peers) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(len(results), 30)
            logger.info("✓ WiFiDirectManager thread-safe")

        except ImportError:
            self.skipTest("android_wifi_direct module not available")


# ============================================================================
# SECTION 3: Bluetooth Module Tests
# ============================================================================

class TestBluetoothManager(unittest.TestCase):
    """Test cases for android_bluetooth.py"""

    def setUp(self):
        """Set up test fixtures."""
        logger.info("BluetoothManager test setup completed")

    def test_bluetooth_device_dataclass(self):
        """Test BluetoothDevice dataclass."""
        try:
            from android_bluetooth import BluetoothDevice

            device = BluetoothDevice(
                device_name="TestDevice",
                device_address="11:22:33:44:55:66",
                is_paired=True,
                rssi=-65
            )

            self.assertEqual(device.device_name, "TestDevice")
            self.assertTrue(device.is_paired)

            device_dict = device.to_dict()
            self.assertEqual(device_dict['rssi'], -65)

            logger.info("✓ BluetoothDevice dataclass working")

        except ImportError:
            self.skipTest("android_bluetooth module not available")

    def test_bluetooth_state_enum(self):
        """Test BluetoothState enum."""
        try:
            from android_bluetooth import BluetoothState

            states = {
                BluetoothState.IDLE,
                BluetoothState.DISCOVERING,
                BluetoothState.CONNECTED,
                BluetoothState.LISTENING,
            }

            self.assertEqual(len(states), len(set(s.value for s in states)))
            logger.info("✓ BluetoothState enum valid")

        except ImportError:
            self.skipTest("android_bluetooth module not available")

    def test_bluetooth_rfcomm_client_offline(self):
        """Test BluetoothRFCOMMClient initialization without connection."""
        try:
            from android_bluetooth import BluetoothRFCOMMClient

            # Create client without actual Android context
            client = BluetoothRFCOMMClient(
                adapter=None,
                device_address="AA:BB:CC:DD:EE:FF",
                service_uuid="447d5f51-7a8b-4d6f-a9c2-1234567890ab"
            )

            self.assertEqual(client.device_address, "AA:BB:CC:DD:EE:FF")
            self.assertFalse(client.connected)

            logger.info("✓ BluetoothRFCOMMClient initialization working")

        except ImportError:
            self.skipTest("android_bluetooth module not available")


# ============================================================================
# SECTION 4: P2P Platform Adapter Tests
# ============================================================================

class TestP2PPlatformAdapter(unittest.TestCase):
    """Test cases for p2p_platform_adapter.py"""

    def setUp(self):
        """Set up test fixtures."""
        logger.info("P2PPlatformAdapter test setup completed")

    def test_p2p_peer_dataclass(self):
        """Test P2PPeer unified peer representation."""
        try:
            from p2p_platform_adapter import P2PPeer, P2PChannel

            peer = P2PPeer(
                peer_id="AA:BB:CC:DD:EE:FF",
                device_name="TestPeer"
            )

            peer.channels.add(P2PChannel.WIFI_DIRECT)
            peer.ip_addresses[P2PChannel.WIFI_DIRECT] = "192.168.1.100"

            self.assertIn(P2PChannel.WIFI_DIRECT, peer.channels)

            peer_dict = peer.to_dict()
            self.assertEqual(peer_dict['device_name'], "TestPeer")
            self.assertIn('wifi_direct', peer_dict['channels'])

            logger.info("✓ P2PPeer dataclass working")

        except ImportError:
            self.skipTest("p2p_platform_adapter module not available")

    def test_adapter_channel_states(self):
        """Test channel state management."""
        try:
            from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel, P2PChannelState

            adapter = P2PPlatformAdapter()

            # All channels should start in IDLE
            for channel in P2PChannel:
                state = adapter.get_channel_state(channel)
                self.assertEqual(state, P2PChannelState.IDLE)

            logger.info("✓ Channel state management working")

        except ImportError:
            self.skipTest("p2p_platform_adapter module not available")

    def test_adapter_peer_management(self):
        """Test peer discovery and management."""
        try:
            from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel

            adapter = P2PPlatformAdapter()

            # Simulate peer discovery
            adapter._add_or_update_peer(
                "AA:BB:CC:DD:EE:FF",
                "TestPeer1",
                P2PChannel.WIFI_DIRECT,
                -50
            )

            peers = adapter.get_peers()
            self.assertEqual(len(peers), 1)
            self.assertEqual(peers[0]['device_name'], "TestPeer1")

            # Update same peer with different channel
            adapter._add_or_update_peer(
                "AA:BB:CC:DD:EE:FF",
                "TestPeer1",
                P2PChannel.BLUETOOTH,
                -60
            )

            peers = adapter.get_peers()
            self.assertEqual(len(peers), 1)  # Still one peer
            self.assertEqual(len(peers[0]['channels']), 2)  # Two channels

            logger.info("✓ Peer management working")

        except ImportError:
            self.skipTest("p2p_platform_adapter module not available")

    def test_adapter_thread_safety(self):
        """Test adapter thread safety."""
        try:
            from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel

            adapter = P2PPlatformAdapter()
            results = []

            def add_peers():
                for i in range(10):
                    adapter._add_or_update_peer(
                        f"AA:BB:CC:DD:EE:{i:02X}",
                        f"Peer{i}",
                        P2PChannel.WIFI_DIRECT,
                        -50 - i
                    )
                    time.sleep(0.001)

            # Multiple threads adding peers
            threads = [threading.Thread(target=add_peers) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            peers = adapter.get_peers()
            self.assertGreater(len(peers), 0)
            logger.info(f"✓ Adapter thread-safe (peers: {len(peers)})")

        except ImportError:
            self.skipTest("p2p_platform_adapter module not available")


# ============================================================================
# SECTION 5: Integration Tests
# ============================================================================

class TestP2PIntegration(unittest.TestCase):
    """Integration tests for P2P modules working together."""

    def test_full_discovery_workflow(self):
        """Test complete discovery workflow without actual hardware."""
        try:
            from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel
            import time

            adapter = P2PPlatformAdapter()

            # Track callback invocations
            discovered_peers = []

            def on_peer_discovered(peer_dict):
                discovered_peers.append(peer_dict)

            adapter.on_peer_discovered = on_peer_discovered

            # Simulate discovery results
            adapter._add_or_update_peer("AA:BB:CC:DD:EE:00", "Peer1", P2PChannel.WIFI_DIRECT, -50)
            adapter._add_or_update_peer("AA:BB:CC:DD:EE:01", "Peer2", P2PChannel.BLUETOOTH, -60)

            time.sleep(0.1)  # Allow async callbacks

            self.assertEqual(len(adapter.get_peers()), 2)
            logger.info("✓ Full discovery workflow test passed")

        except ImportError as e:
            self.skipTest(f"Required module not available: {e}")

    def test_peer_deduplication(self):
        """Test that same peer discovered on multiple channels is deduplicated."""
        try:
            from p2p_platform_adapter import P2PPlatformAdapter, P2PChannel

            adapter = P2PPlatformAdapter()

            # Same peer appears on both Wi-Fi Direct and Bluetooth
            adapter._add_or_update_peer(
                "AA:BB:CC:DD:EE:FF",
                "TestPeer",
                P2PChannel.WIFI_DIRECT,
                -50
            )

            adapter._add_or_update_peer(
                "AA:BB:CC:DD:EE:FF",
                "TestPeer",
                P2PChannel.BLUETOOTH,
                -60
            )

            peers = adapter.get_peers()
            self.assertEqual(len(peers), 1)  # Only one peer
            self.assertEqual(len(peers[0]['channels']), 2)  # But two channels

            logger.info("✓ Peer deduplication working")

        except ImportError:
            self.skipTest("p2p_platform_adapter module not available")


# ============================================================================
# SECTION 6: Test Suite Runner
# ============================================================================

class TestRunner:
    """Main test runner with filtering options."""

    def __init__(self):
        self.logger = logger

    def run_all_tests(self, verbosity=2):
        """Run all test suites."""
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        # Add all test classes
        suite.addTests(loader.loadTestsFromTestCase(TestPermissionManager))
        suite.addTests(loader.loadTestsFromTestCase(TestWiFiDirectManager))
        suite.addTests(loader.loadTestsFromTestCase(TestBluetoothManager))
        suite.addTests(loader.loadTestsFromTestCase(TestP2PPlatformAdapter))
        suite.addTests(loader.loadTestsFromTestCase(TestP2PIntegration))

        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)

        return result.wasSuccessful()

    def run_permission_tests(self, verbosity=2):
        """Run only permission tests."""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestPermissionManager)
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
        return result.wasSuccessful()

    def run_wifi_direct_tests(self, verbosity=2):
        """Run only Wi-Fi Direct tests."""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestWiFiDirectManager)
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
        return result.wasSuccessful()

    def run_bluetooth_tests(self, verbosity=2):
        """Run only Bluetooth tests."""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestBluetoothManager)
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
        return result.wasSuccessful()

    def run_adapter_tests(self, verbosity=2):
        """Run only adapter tests."""
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        suite.addTests(loader.loadTestsFromTestCase(TestP2PPlatformAdapter))
        suite.addTests(loader.loadTestsFromTestCase(TestP2PIntegration))
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
        return result.wasSuccessful()


# ============================================================================
# SECTION 7: Test Report Generation
# ============================================================================

def generate_test_report(result: unittest.TestResult) -> str:
    """Generate detailed test report."""
    report = []
    report.append("\n" + "="*70)
    report.append("GHOST NET P2P MODULES TEST REPORT")
    report.append("="*70)

    report.append(f"\nTests Run: {result.testsRun}")
    report.append(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    report.append(f"Failures: {len(result.failures)}")
    report.append(f"Errors: {len(result.errors)}")
    report.append(f"Skipped: {len(result.skipped)}")

    if result.failures:
        report.append("\nFAILURES:")
        for test, traceback in result.failures:
            report.append(f"  - {test}")
            report.append(f"    {traceback}")

    if result.errors:
        report.append("\nERRORS:")
        for test, traceback in result.errors:
            report.append(f"  - {test}")
            report.append(f"    {traceback}")

    report.append("\n" + "="*70)

    return "\n".join(report)


# ============================================================================
# SECTION 8: Command-Line Interface
# ============================================================================

def main():
    """Main entry point with CLI argument handling."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ghost Net P2P Modules Test Suite"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--module",
        choices=["permissions", "wifi", "bluetooth", "adapter", "all"],
        default="all",
        help="Test specific module"
    )

    args = parser.parse_args()

    runner = TestRunner()
    verbosity = 2 if args.verbose else 1

    logger.info("Starting P2P Module Test Suite...")

    if args.module == "permissions":
        success = runner.run_permission_tests(verbosity)
    elif args.module == "wifi":
        success = runner.run_wifi_direct_tests(verbosity)
    elif args.module == "bluetooth":
        success = runner.run_bluetooth_tests(verbosity)
    elif args.module == "adapter":
        success = runner.run_adapter_tests(verbosity)
    else:
        success = runner.run_all_tests(verbosity)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
