"""
Ghost Net - Test Suite for UI Layout and Network Detection Fixes
Tests keyboard handling, responsive layouts, and network switching functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import time
import sys
from pathlib import Path

# Add project directory to path
sys.path.insert(0, str(Path(__file__).parent))


class TestNetworkDetection(unittest.TestCase):
    """Test network detection and interface identification."""
    
    def setUp(self):
        """Set up test fixtures."""
        try:
            from network_utils import NetworkDetector, NetworkMonitor
            self.NetworkDetector = NetworkDetector
            self.NetworkMonitor = NetworkMonitor
        except ImportError:
            self.skipTest("network_utils not available")
    
    def test_network_detector_initialization(self):
        """Test NetworkDetector can be initialized."""
        detector = self.NetworkDetector()
        self.assertIsNotNone(detector)
    
    def test_detect_wifi_interface(self):
        """Test Wi-Fi interface detection."""
        detector = self.NetworkDetector()
        iface_type = detector._detect_interface_type('wlan0', '192.168.1.100')
        self.assertEqual(iface_type, 'wifi')
    
    def test_detect_hotspot_interface(self):
        """Test hotspot interface detection."""
        detector = self.NetworkDetector()
        
        # Test by name
        iface_type = detector._detect_interface_type('ap0', '192.168.43.1')
        self.assertEqual(iface_type, 'hotspot')
        
        # Test by IP range
        iface_type = detector._detect_interface_type_by_ip('192.168.43.100')
        self.assertEqual(iface_type, 'hotspot')
    
    def test_detect_cellular_interface(self):
        """Test cellular interface detection."""
        detector = self.NetworkDetector()
        iface_type = detector._detect_interface_type('rmnet0', '10.0.0.5')
        self.assertEqual(iface_type, 'cellular')
    
    def test_detect_ethernet_interface(self):
        """Test Ethernet interface detection."""
        detector = self.NetworkDetector()
        iface_type = detector._detect_interface_type('eth0', '192.168.1.50')
        self.assertEqual(iface_type, 'ethernet')
    
    def test_network_monitor_initialization(self):
        """Test NetworkMonitor can be initialized."""
        monitor = self.NetworkMonitor()
        self.assertIsNotNone(monitor)
    
    def test_network_monitor_status(self):
        """Test NetworkMonitor returns valid status."""
        monitor = self.NetworkMonitor()
        status = monitor.get_status()
        
        # Status should have required keys
        self.assertIn('ip', status)
        self.assertIn('type', status)
        self.assertIn('is_connected', status)
        self.assertIn('interfaces', status)
    
    def test_network_monitor_callback(self):
        """Test NetworkMonitor calls callback on network change."""
        callback_called = False
        callback_args = {}
        
        def on_network_changed(old_ip, new_ip, network_type):
            nonlocal callback_called, callback_args
            callback_called = True
            callback_args = {
                'old_ip': old_ip,
                'new_ip': new_ip,
                'network_type': network_type
            }
        
        monitor = self.NetworkMonitor(on_network_changed=on_network_changed)
        # Mock network change
        monitor.current_ip = '192.168.1.100'
        monitor.check_network_change()
        
        # Callback would be called if network actually changed
        # This is a simplified test


class TestGhostEngineNetworkSupport(unittest.TestCase):
    """Test GhostEngine network detection integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        try:
            from network import GhostEngine
            self.GhostEngine = GhostEngine
        except ImportError:
            self.skipTest("GhostEngine not available")
    
    def test_engine_initialization_with_network_detector(self):
        """Test GhostEngine initializes with network detection."""
        engine = self.GhostEngine(username="TestUser")
        self.assertIsNotNone(engine)
        self.assertEqual(engine.username, "TestUser")
    
    def test_engine_has_network_status_method(self):
        """Test GhostEngine has network status method."""
        engine = self.GhostEngine()
        self.assertTrue(hasattr(engine, 'get_network_status'))
        
        # Get network status
        status = engine.get_network_status()
        self.assertIsInstance(status, dict)
        self.assertIn('ip', status)
        self.assertIn('type', status)
    
    def test_engine_network_monitor_method(self):
        """Test GhostEngine has network monitor worker."""
        engine = self.GhostEngine()
        self.assertTrue(hasattr(engine, '_network_monitor_worker'))
    
    def test_engine_network_change_callback(self):
        """Test GhostEngine has network change callback."""
        engine = self.GhostEngine()
        self.assertTrue(hasattr(engine, '_on_network_changed'))


class TestChatScreenLayout(unittest.TestCase):
    """Test ChatScreen UI layout improvements."""
    
    @patch('main.MDApp')
    def test_chat_screen_has_keyboard_bindings(self, mock_app):
        """Test ChatScreen has keyboard event bindings."""
        try:
            from main import ChatScreen
            chat = ChatScreen()
            
            # Check for keyboard-related methods
            self.assertTrue(hasattr(chat, 'on_keyboard_height'))
            self.assertTrue(hasattr(chat, 'on_keyboard_event'))
            self.assertTrue(hasattr(chat, '_scroll_to_bottom'))
        except ImportError:
            self.skipTest("main.py not available")
    
    @patch('main.MDApp')
    def test_message_bubble_adaptive_height(self, mock_app):
        """Test MessageBubble uses adaptive height."""
        try:
            from main import MessageBubble
            bubble = MessageBubble("Test message", "12:00", is_sent=True)
            
            # Check adaptive height property
            self.assertTrue(bubble.adaptive_height)
            self.assertIsNotNone(bubble.minimum_height)
        except ImportError:
            self.skipTest("main.py not available")
    
    @patch('main.MDApp')
    def test_file_bubble_adaptive_height(self, mock_app):
        """Test FileBubble uses adaptive height."""
        try:
            from main import FileBubble
            bubble = FileBubble("test.txt", "/tmp/test.txt", "12:00", is_sent=False)
            
            # Check adaptive height property
            self.assertTrue(bubble.adaptive_height)
            self.assertIsNotNone(bubble.minimum_height)
        except ImportError:
            self.skipTest("main.py not available")
    
    @patch('main.MDApp')
    def test_radar_screen_network_badge(self, mock_app):
        """Test RadarScreen has network status badge."""
        try:
            from main import RadarScreen
            radar = RadarScreen()
            
            # Check for network badge
            self.assertTrue(hasattr(radar, 'network_badge'))
            self.assertTrue(hasattr(radar, 'update_network_status'))
        except ImportError:
            self.skipTest("main.py not available")


class TestResponsiveLayout(unittest.TestCase):
    """Test responsive layout on different screen sizes."""
    
    def test_small_screen_layout_480x800(self):
        """Test layout works on small screens (480x800)."""
        # This would require actual Kivy testing
        # Placeholder for integration testing
        pass
    
    def test_medium_screen_layout_720x1280(self):
        """Test layout works on medium screens (720x1280)."""
        # This would require actual Kivy testing
        # Placeholder for integration testing
        pass
    
    def test_large_screen_layout_1080x1920(self):
        """Test layout works on large screens (1080x1920)."""
        # This would require actual Kivy testing
        # Placeholder for integration testing
        pass


class TestNetworkSwitching(unittest.TestCase):
    """Test automatic network switching functionality."""
    
    def test_network_switch_wifi_to_hotspot(self):
        """Test switching from Wi-Fi to hotspot."""
        # This would require actual network setup
        # Placeholder for integration testing
        pass
    
    def test_network_switch_hotspot_to_cellular(self):
        """Test switching from hotspot to cellular."""
        # This would require actual network setup
        # Placeholder for integration testing
        pass
    
    def test_network_reconnection_on_change(self):
        """Test app reconnects when network changes."""
        # This would require actual network setup
        # Placeholder for integration testing
        pass


class TestBuildozerConfiguration(unittest.TestCase):
    """Test buildozer.spec configuration for Android."""
    
    def test_buildozer_spec_exists(self):
        """Test buildozer.spec file exists."""
        spec_path = Path('buildozer.spec')
        self.assertTrue(spec_path.exists(), "buildozer.spec not found")
    
    def test_buildozer_has_soft_input_mode(self):
        """Test buildozer.spec has soft input mode configured."""
        spec_path = Path('buildozer.spec')
        content = spec_path.read_text()
        
        # Check for soft input mode configuration
        self.assertIn('windowSoftInputMode', content)
        self.assertIn('adjustResize', content)
    
    def test_requirements_has_netifaces(self):
        """Test requirements.txt includes netifaces."""
        req_path = Path('requirements.txt')
        content = req_path.read_text()
        
        self.assertIn('netifaces', content)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestNetworkDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestGhostEngineNetworkSupport))
    suite.addTests(loader.loadTestsFromTestCase(TestChatScreenLayout))
    suite.addTests(loader.loadTestsFromTestCase(TestResponsiveLayout))
    suite.addTests(loader.loadTestsFromTestCase(TestNetworkSwitching))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildozerConfiguration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
