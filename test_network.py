"""
Ghost Net - Network Engine Test Suite
Tests UDP discovery, TCP messaging, and encryption without UI.
"""

import time
import sys
from network import GhostEngine


class NetworkTester:
    """Test harness for Ghost Net network engine."""
    
    def __init__(self):
        self.messages_received = []
        self.peer_updates = []
        self.test_results = {}
    
    def on_message_callback(self, sender_ip, message, timestamp):
        """Callback for received messages."""
        print(f"\n✉️  [{timestamp}] Message from {sender_ip}: {message}")
        self.messages_received.append({
            'sender': sender_ip,
            'message': message,
            'timestamp': timestamp
        })
    
    def on_peer_callback(self, peers):
        """Callback for peer updates."""
        print(f"\n👥 Peer update: {len(peers)} active peer(s)")
        for ip, info in peers.items():
            print(f"   - {info['username']} @ {ip}")
        self.peer_updates.append(peers.copy())
    
    def test_engine_initialization(self, username="TestUser"):
        """Test 1: Engine initialization."""
        print("\n" + "="*60)
        print("TEST 1: Engine Initialization")
        print("="*60)
        
        try:
            engine = GhostEngine(
                username=username,
                on_message_received=self.on_message_callback,
                on_peer_update=self.on_peer_callback
            )
            
            print(f"✅ Engine created for user: {username}")
            print(f"✅ Local IP detected: {engine.local_ip}")
            print(f"✅ Cipher initialized: {type(engine.cipher).__name__}")
            
            self.test_results['initialization'] = 'PASS'
            return engine
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            self.test_results['initialization'] = 'FAIL'
            return None
    
    def test_engine_start(self, engine):
        """Test 2: Engine start and thread spawning."""
        print("\n" + "="*60)
        print("TEST 2: Engine Start & Threading")
        print("="*60)
        
        try:
            engine.start()
            time.sleep(2)  # Give threads time to start
            
            # Check if threads are alive
            threads_alive = []
            if engine.beacon_thread and engine.beacon_thread.is_alive():
                threads_alive.append("Beacon")
            if engine.listener_thread and engine.listener_thread.is_alive():
                threads_alive.append("Listener")
            if engine.tcp_server_thread and engine.tcp_server_thread.is_alive():
                threads_alive.append("TCP Server")
            if engine.pruning_thread and engine.pruning_thread.is_alive():
                threads_alive.append("Pruning")
            
            print(f"✅ Engine started successfully")
            print(f"✅ Active threads: {', '.join(threads_alive)}")
            print(f"✅ UDP Port: {engine.UDP_PORT}")
            print(f"✅ TCP Port: {engine.TCP_PORT}")
            
            if len(threads_alive) == 4:
                self.test_results['start'] = 'PASS'
            else:
                print(f"⚠️  Warning: Only {len(threads_alive)}/4 threads active")
                self.test_results['start'] = 'PARTIAL'
            
        except Exception as e:
            print(f"❌ Start failed: {e}")
            self.test_results['start'] = 'FAIL'
    
    def test_peer_discovery(self, engine, wait_time=15):
        """Test 3: Peer discovery via UDP broadcast."""
        print("\n" + "="*60)
        print("TEST 3: Peer Discovery (UDP Broadcast)")
        print("="*60)
        print(f"⏳ Waiting {wait_time} seconds for peer discovery...")
        print("   (Start another instance of this script in a new terminal)")
        
        time.sleep(wait_time)
        
        peers = engine.get_peers()
        
        if len(peers) > 0:
            print(f"\n✅ Discovery successful! Found {len(peers)} peer(s):")
            for ip, info in peers.items():
                print(f"   - {info['username']} @ {ip}")
            self.test_results['discovery'] = 'PASS'
            return list(peers.keys())[0]  # Return first peer IP for messaging test
        else:
            print(f"\n⚠️  No peers discovered")
            print("   This is expected if no other instances are running")
            self.test_results['discovery'] = 'SKIP'
            return None
    
    def test_encryption_decryption(self, engine):
        """Test 4: Message encryption/decryption."""
        print("\n" + "="*60)
        print("TEST 4: Encryption & Decryption")
        print("="*60)
        
        test_messages = [
            "Hello, Ghost Net!",
            "🚀 Unicode test with emojis 👻",
            "A" * 1000,  # Long message
            "Special chars: !@#$%^&*()"
        ]
        
        all_passed = True
        
        for i, original in enumerate(test_messages, 1):
            try:
                encrypted = engine._encrypt_message(original)
                decrypted = engine._decrypt_message(encrypted)
                
                if decrypted == original:
                    print(f"✅ Test {i}: '{original[:50]}...' - OK")
                else:
                    print(f"❌ Test {i}: Decryption mismatch")
                    all_passed = False
                    
            except Exception as e:
                print(f"❌ Test {i}: Exception - {e}")
                all_passed = False
        
        self.test_results['encryption'] = 'PASS' if all_passed else 'FAIL'
    
    def test_message_sending(self, engine, target_ip):
        """Test 5: TCP message sending."""
        print("\n" + "="*60)
        print("TEST 5: Message Sending (TCP)")
        print("="*60)
        
        if not target_ip:
            print("⚠️  Skipped: No target peer available")
            self.test_results['sending'] = 'SKIP'
            return
        
        test_message = "Test message from automated test suite"
        
        try:
            print(f"📤 Sending to {target_ip}: '{test_message}'")
            success = engine.send_message(target_ip, test_message)
            
            if success:
                print(f"✅ Message sent successfully")
                self.test_results['sending'] = 'PASS'
            else:
                print(f"❌ Message sending failed")
                self.test_results['sending'] = 'FAIL'
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['sending'] = 'FAIL'
    
    def test_message_receiving(self, wait_time=10):
        """Test 6: Check if messages were received."""
        print("\n" + "="*60)
        print("TEST 6: Message Receiving")
        print("="*60)
        print(f"⏳ Waiting {wait_time} seconds for incoming messages...")
        
        time.sleep(wait_time)
        
        if len(self.messages_received) > 0:
            print(f"\n✅ Received {len(self.messages_received)} message(s):")
            for msg in self.messages_received:
                print(f"   - From {msg['sender']} at {msg['timestamp']}: {msg['message']}")
            self.test_results['receiving'] = 'PASS'
        else:
            print(f"\n⚠️  No messages received")
            print("   This is expected if no other instance sent messages")
            self.test_results['receiving'] = 'SKIP'
    
    def test_peer_timeout(self, engine, wait_time=12):
        """Test 7: Peer pruning after timeout."""
        print("\n" + "="*60)
        print("TEST 7: Peer Timeout & Pruning")
        print("="*60)
        print(f"⏳ Waiting {wait_time} seconds to test pruning...")
        print("   (Turn off the other instance to test timeout)")
        
        initial_peers = len(engine.get_peers())
        time.sleep(wait_time)
        final_peers = len(engine.get_peers())
        
        print(f"\n📊 Initial peers: {initial_peers}")
        print(f"📊 Final peers: {final_peers}")
        
        if initial_peers > final_peers:
            print(f"✅ Pruning works! {initial_peers - final_peers} peer(s) removed")
            self.test_results['timeout'] = 'PASS'
        elif initial_peers == 0:
            print(f"⚠️  No peers to test pruning")
            self.test_results['timeout'] = 'SKIP'
        else:
            print(f"⚠️  All peers still active (expected if instances still running)")
            self.test_results['timeout'] = 'SKIP'
    
    def test_engine_shutdown(self, engine):
        """Test 8: Clean shutdown."""
        print("\n" + "="*60)
        print("TEST 8: Engine Shutdown")
        print("="*60)
        
        try:
            engine.stop()
            time.sleep(2)  # Give threads time to stop
            
            # Check if threads are stopped
            threads_stopped = []
            if not engine.beacon_thread.is_alive():
                threads_stopped.append("Beacon")
            if not engine.listener_thread.is_alive():
                threads_stopped.append("Listener")
            if not engine.tcp_server_thread.is_alive():
                threads_stopped.append("TCP Server")
            if not engine.pruning_thread.is_alive():
                threads_stopped.append("Pruning")
            
            print(f"✅ Engine stopped successfully")
            print(f"✅ Stopped threads: {', '.join(threads_stopped)}")
            
            if len(threads_stopped) == 4:
                self.test_results['shutdown'] = 'PASS'
            else:
                print(f"⚠️  Warning: Only {len(threads_stopped)}/4 threads stopped")
                self.test_results['shutdown'] = 'PARTIAL'
            
        except Exception as e:
            print(f"❌ Shutdown failed: {e}")
            self.test_results['shutdown'] = 'FAIL'
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results.values() if result == 'PASS')
        failed = sum(1 for result in self.test_results.values() if result == 'FAIL')
        skipped = sum(1 for result in self.test_results.values() if result == 'SKIP')
        partial = sum(1 for result in self.test_results.values() if result == 'PARTIAL')
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            symbol = {
                'PASS': '✅',
                'FAIL': '❌',
                'SKIP': '⚠️ ',
                'PARTIAL': '⚡'
            }.get(result, '❓')
            
            print(f"{symbol} {test_name.upper()}: {result}")
        
        print(f"\n📊 Results: {passed} passed, {failed} failed, {skipped} skipped, {partial} partial out of {total} tests")
        
        if failed > 0:
            print("\n❌ Some tests failed. Review output above.")
            return False
        else:
            print("\n✅ All critical tests passed!")
            return True


def run_tests(username=None, interactive=True):
    """Run the complete test suite."""
    if username is None:
        import os
        username = os.getenv('USERNAME', 'TestUser') + "_Test"
    
    print("="*60)
    print("👻 GHOST NET - NETWORK ENGINE TEST SUITE")
    print("="*60)
    print(f"Username: {username}")
    print(f"Interactive Mode: {interactive}")
    print()
    
    tester = NetworkTester()
    
    # Run tests
    engine = tester.test_engine_initialization(username)
    
    if engine is None:
        print("\n❌ Cannot continue without engine. Exiting.")
        return False
    
    tester.test_engine_start(engine)
    tester.test_encryption_decryption(engine)
    
    if interactive:
        target_ip = tester.test_peer_discovery(engine, wait_time=15)
        tester.test_message_sending(engine, target_ip)
        tester.test_message_receiving(wait_time=10)
        tester.test_peer_timeout(engine, wait_time=12)
    else:
        print("\n⚠️  Interactive tests skipped (non-interactive mode)")
        tester.test_results['discovery'] = 'SKIP'
        tester.test_results['sending'] = 'SKIP'
        tester.test_results['receiving'] = 'SKIP'
        tester.test_results['timeout'] = 'SKIP'
    
    tester.test_engine_shutdown(engine)
    
    # Print summary
    success = tester.print_summary()
    
    return success


if __name__ == "__main__":
    # Parse command line arguments
    username = None
    interactive = True
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
    
    if len(sys.argv) > 2 and sys.argv[2] == '--no-interactive':
        interactive = False
    
    try:
        success = run_tests(username, interactive)
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
