#!/usr/bin/env python3
"""
Ghost Net - Android Crash Diagnostics
Comprehensive logging and error detection for Android debugging.
Run this before main.py to validate crash hypotheses.
"""

import sys
import os
import traceback
import platform
import subprocess
from datetime import datetime
from pathlib import Path
import json

class CrashDiagnostics:
    """Comprehensive crash diagnostics for Ghost Net Android app."""
    
    def __init__(self):
        self.log_file = "crash_diagnostics.log"
        self.results = {}
        self._setup_logging()
    
    def _setup_logging(self):
        """Initialize logging to file."""
        self.log(f"=== GHOST NET CRASH DIAGNOSTICS ===")
        self.log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Platform: {platform.platform()}")
        self.log(f"Python: {sys.version}")
        self.log("")
    
    def log(self, message):
        """Write message to both console and log file."""
        print(message)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"{message}\n")
        except:
            pass  # Don't fail if we can't write to log
    
    def test_hypothesis_1_android_permissions(self):
        """HYPOTHESIS 1: Android Permissions Failure"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 1: ANDROID PERMISSIONS FAILURE")
        self.log("="*60)
        
        try:
            # Check if we're on Android
            is_android = 'ANDROID_BOOTLOGO' in os.environ or 'ANDROID_ROOT' in os.environ
            self.log(f"Android detected: {is_android}")
            
            if is_android:
                # Test Android permissions import
                try:
                    from android.permissions import request_permissions, Permission
                    self.log("✅ Android permissions module available")
                    
                    # Test specific permissions
                    permissions = [
                        'WRITE_EXTERNAL_STORAGE',
                        'READ_EXTERNAL_STORAGE', 
                        'INTERNET',
                        'ACCESS_NETWORK_STATE',
                        'ACCESS_WIFI_STATE'
                    ]
                    
                    for perm in permissions:
                        if hasattr(Permission, perm):
                            self.log(f"✅ Permission available: {perm}")
                        else:
                            self.log(f"❌ Permission missing: {perm}")
                            return False
                    
                except ImportError as e:
                    self.log(f"❌ Android permissions import failed: {e}")
                    return False
                except Exception as e:
                    self.log(f"❌ Android permissions error: {e}")
                    return False
            else:
                self.log("ℹ️ Not on Android - permissions test skipped")
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 1 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def test_hypothesis_2_kivymd_version_mismatch(self):
        """HYPOTHESIS 2: KivyMD Version Mismatch"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 2: KIVYMD VERSION MISMATCH")
        self.log("="*60)
        
        try:
            # Test Kivy import first
            try:
                import kivy
                self.log(f"✅ Kivy version: {kivy.__version__}")
                
                # Check if Kivy version matches requirements
                required_kivy = "2.3.0"
                if kivy.__version__ != required_kivy:
                    self.log(f"⚠️ Kivy version mismatch: have {kivy.__version__}, need {required_kivy}")
            
            except ImportError as e:
                self.log(f"❌ Kivy import failed: {e}")
                return False
            
            # Test KivyMD import
            try:
                import kivymd
                self.log(f"✅ KivyMD version: {kivymd.__version__}")
                
                # Check version consistency
                if hasattr(kivymd, '__version__'):
                    version = kivymd.__version__
                    if "1.1.1" not in version and "dev" not in version:
                        self.log(f"⚠️ KivyMD version mismatch detected: {version}")
                
            except ImportError as e:
                self.log(f"❌ KivyMD import failed: {e}")
                return False
            except Exception as e:
                self.log(f"❌ KivyMD error: {e}")
                return False
            
            # Test specific KivyMD components used in main.py
            critical_imports = [
                'kivymd.app.MDApp',
                'kivymd.uix.screen.MDScreen',
                'kivymd.uix.screenmanager.MDScreenManager',
                'kivymd.uix.spinner.MDSpinner',
                'kivymd.uix.button.MDButton',
                'kivymd.uix.textfield.MDTextField'
            ]
            
            for import_path in critical_imports:
                try:
                    module_path = '.'.join(import_path.split('.')[:-1])
                    class_name = import_path.split('.')[-1]
                    
                    module = __import__(module_path, fromlist=[class_name])
                    getattr(module, class_name)
                    self.log(f"✅ Import successful: {import_path}")
                    
                except Exception as e:
                    self.log(f"❌ Import failed: {import_path} - {e}")
                    return False
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 2 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def test_hypothesis_3_network_socket_binding(self):
        """HYPOTHESIS 3: Network Socket Binding Failure"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 3: NETWORK SOCKET BINDING FAILURE")
        self.log("="*60)
        
        try:
            import socket
            
            # Test UDP socket binding (Port 37020)
            try:
                udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                udp_socket.bind(('', 37020))
                udp_socket.close()
                self.log("✅ UDP socket binding successful (port 37020)")
            except Exception as e:
                self.log(f"❌ UDP socket binding failed (port 37020): {e}")
                return False
            
            # Test TCP socket binding (Port 37021)
            try:
                tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                tcp_socket.bind(('0.0.0.0', 37021))
                tcp_socket.listen(1)
                tcp_socket.close()
                self.log("✅ TCP socket binding successful (port 37021)")
            except Exception as e:
                self.log(f"❌ TCP socket binding failed (port 37021): {e}")
                return False
            
            # Test broadcast capability
            try:
                udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                udp_socket.close()
                self.log("✅ Broadcast socket capability available")
            except Exception as e:
                self.log(f"❌ Broadcast socket failed: {e}")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 3 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def test_hypothesis_4_filesystem_access(self):
        """HYPOTHESIS 4: File System Access Violation"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 4: FILESYSTEM ACCESS VIOLATION")
        self.log("="*60)
        
        try:
            # Test directory creation
            test_dirs = ["downloads", "assets/locales"]
            
            for dir_path in test_dirs:
                try:
                    Path(dir_path).mkdir(parents=True, exist_ok=True)
                    if Path(dir_path).exists():
                        self.log(f"✅ Directory creation successful: {dir_path}")
                    else:
                        self.log(f"❌ Directory creation failed: {dir_path}")
                        return False
                except Exception as e:
                    self.log(f"❌ Directory creation error: {dir_path} - {e}")
                    return False
            
            # Test file creation/writing
            test_files = ["settings.json", "test_write.txt"]
            
            for file_path in test_files:
                try:
                    with open(file_path, 'w') as f:
                        f.write('{"test": true}' if file_path.endswith('.json') else 'test')
                    self.log(f"✅ File write successful: {file_path}")
                    
                    # Clean up
                    os.remove(file_path)
                except Exception as e:
                    self.log(f"❌ File write failed: {file_path} - {e}")
                    return False
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 4 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def test_hypothesis_5_threading_race_condition(self):
        """HYPOTHESIS 5: Threading Race Condition"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 5: THREADING RACE CONDITION")
        self.log("="*60)
        
        try:
            import threading
            import time
            
            # Test basic threading
            test_result = {"success": False}
            
            def test_thread():
                time.sleep(0.1)
                test_result["success"] = True
            
            thread = threading.Thread(target=test_thread, daemon=True)
            thread.start()
            thread.join(timeout=1.0)
            
            if test_result["success"]:
                self.log("✅ Basic threading works")
            else:
                self.log("❌ Basic threading failed")
                return False
            
            # Test Kivy Clock (if available)
            try:
                from kivy.clock import Clock
                
                test_clock_result = {"called": False}
                
                def test_clock_callback(dt):
                    test_clock_result["called"] = True
                
                Clock.schedule_once(test_clock_callback, 0)
                time.sleep(0.1)
                
                if test_clock_result["called"]:
                    self.log("✅ Kivy Clock.schedule_once works")
                else:
                    self.log("⚠️ Kivy Clock.schedule_once not called (may indicate issue)")
                
            except Exception as e:
                self.log(f"⚠️ Kivy Clock test failed: {e}")
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 5 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def test_hypothesis_6_cryptography_incompatibility(self):
        """HYPOTHESIS 6: Cryptography Library Incompatibility"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 6: CRYPTOGRAPHY LIBRARY INCOMPATIBILITY")
        self.log("="*60)
        
        try:
            # Test cryptography import
            try:
                import cryptography
                self.log(f"✅ Cryptography version: {cryptography.__version__}")
            except ImportError as e:
                self.log(f"❌ Cryptography import failed: {e}")
                return False
            
            # Test Fernet import and basic operation
            try:
                from cryptography.fernet import Fernet
                
                # Generate key
                key = Fernet.generate_key()
                cipher = Fernet(key)
                
                # Test encryption/decryption
                test_data = b"Hello Ghost Net"
                encrypted = cipher.encrypt(test_data)
                decrypted = cipher.decrypt(encrypted)
                
                if decrypted == test_data:
                    self.log("✅ Fernet encryption/decryption works")
                else:
                    self.log("❌ Fernet encryption/decryption failed")
                    return False
                    
            except Exception as e:
                self.log(f"❌ Fernet operation failed: {e}")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 6 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def test_hypothesis_7_kivymd_widget_initialization(self):
        """HYPOTHESIS 7: KivyMD Widget Initialization"""
        self.log("\n" + "="*60)
        self.log("HYPOTHESIS 7: KIVYMD WIDGET INITIALIZATION")
        self.log("="*60)
        
        try:
            # Test critical KivyMD widgets used in BootScreen
            from kivymd.uix.spinner import MDSpinner
            from kivymd.uix.label import MDLabel
            from kivymd.uix.boxlayout import MDBoxLayout
            
            # Test widget creation (without adding to parent)
            try:
                spinner = MDSpinner()
                self.log("✅ MDSpinner creation successful")
                
                label = MDLabel(text="Test")
                self.log("✅ MDLabel creation successful")
                
                layout = MDBoxLayout()
                self.log("✅ MDBoxLayout creation successful")
                
            except Exception as e:
                self.log(f"❌ Widget creation failed: {e}")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"❌ HYPOTHESIS 7 FAILED: {e}")
            self.log(traceback.format_exc())
            return False
    
    def run_all_tests(self):
        """Run all diagnostic tests and generate report."""
        self.log("\n" + "="*80)
        self.log("STARTING COMPREHENSIVE CRASH DIAGNOSIS")
        self.log("="*80)
        
        # Define test methods
        tests = [
            ("Android Permissions", self.test_hypothesis_1_android_permissions),
            ("KivyMD Version Mismatch", self.test_hypothesis_2_kivymd_version_mismatch),
            ("Network Socket Binding", self.test_hypothesis_3_network_socket_binding),
            ("Filesystem Access", self.test_hypothesis_4_filesystem_access),
            ("Threading Race Condition", self.test_hypothesis_5_threading_race_condition),
            ("Cryptography Incompatibility", self.test_hypothesis_6_cryptography_incompatibility),
            ("KivyMD Widget Initialization", self.test_hypothesis_7_kivymd_widget_initialization),
        ]
        
        # Run each test
        results = {}
        for test_name, test_func in tests:
            try:
                results[test_name] = test_func()
            except Exception as e:
                self.log(f"\n❌ Test '{test_name}' crashed with exception: {e}")
                results[test_name] = False
        
        # Generate summary report
        self.log("\n" + "="*80)
        self.log("DIAGNOSTIC SUMMARY REPORT")
        self.log("="*80)
        
        passed = 0
        failed = 0
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            self.log(f"{status}: {test_name}")
            if result:
                passed += 1
            else:
                failed += 1
        
        self.log(f"\nResults: {passed} passed, {failed} failed")
        
        # Identify most likely crash causes
        self.log("\n" + "="*60)
        self.log("CRASH CAUSE ANALYSIS")
        self.log("="*60)
        
        failed_tests = [name for name, result in results.items() if not result]
        
        if not failed_tests:
            self.log("✅ All tests passed - crash may be in application logic or runtime environment")
        else:
            self.log(f"❌ {len(failed_tests)} critical issues found:")
            for i, test_name in enumerate(failed_tests, 1):
                self.log(f"   {i}. {test_name}")
            
            self.log(f"\n🎯 PRIMARY CRASH CAUSE: {failed_tests[0]}")
            if len(failed_tests) > 1:
                self.log(f"🎯 SECONDARY CAUSES: {', '.join(failed_tests[1:])}")
        
        self.log(f"\n📁 Full diagnostic log saved to: {self.log_file}")
        
        return results


def main():
    """Run crash diagnostics."""
    diagnostics = CrashDiagnostics()
    results = diagnostics.run_all_tests()
    
    # Return exit code based on results
    failed_count = sum(1 for result in results.values() if not result)
    return failed_count


if __name__ == "__main__":
    sys.exit(main())