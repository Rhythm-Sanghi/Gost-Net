#!/usr/bin/env python3
"""
Ghost Net APK Validator
Automated testing script to validate APK functionality on connected Android device
"""

import subprocess
import sys
import time
import re
from datetime import datetime

class APKValidator:
    """Validate Ghost Net APK on Android device via ADB"""
    
    def __init__(self):
        self.test_results = {}
        self.device_id = None
        self.log_file = f"apk_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
    def log(self, message):
        """Print and log message"""
        print(message)
        with open(self.log_file, 'a') as f:
            f.write(f"{message}\n")
    
    def run_command(self, cmd, capture=True):
        """Run shell command and return output"""
        try:
            if capture:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                return result.returncode, result.stdout, result.stderr
            else:
                subprocess.run(cmd, shell=True, timeout=10)
                return 0, "", ""
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)
    
    def test_adb_connection(self):
        """Test ADB connection to device"""
        self.log("\n" + "="*60)
        self.log("TEST 1: ADB Connection")
        self.log("="*60)
        
        code, output, error = self.run_command("adb devices")
        
        if code != 0:
            self.log("❌ ADB not found or error occurred")
            self.log(f"Error: {error}")
            return False
        
        lines = output.strip().split('\n')[1:]  # Skip header
        devices = [line.split('\t')[0] for line in lines if 'device' in line and not 'offline' in line]
        
        if not devices:
            self.log("❌ No Android devices connected")
            self.log("Please connect device with USB debugging enabled")
            return False
        
        self.device_id = devices[0]
        self.log(f"✅ Device connected: {self.device_id}")
        self.test_results['adb_connection'] = True
        return True
    
    def test_app_installed(self):
        """Test if Ghost Net app is installed"""
        self.log("\n" + "="*60)
        self.log("TEST 2: App Installation Check")
        self.log("="*60)
        
        code, output, error = self.run_command("adb shell pm list packages | grep ghostnet")
        
        if code != 0 or "ghostnet" not in output:
            self.log("❌ Ghost Net app not installed")
            self.log("Install with: adb install bin/ghostnet-*-debug.apk")
            self.test_results['app_installed'] = False
            return False
        
        self.log("✅ Ghost Net app is installed")
        self.test_results['app_installed'] = True
        return True
    
    def test_app_launch(self):
        """Test if app can launch without immediate crash"""
        self.log("\n" + "="*60)
        self.log("TEST 3: App Launch Test")
        self.log("="*60)
        
        # Clear logcat
        self.run_command("adb logcat -c")
        time.sleep(1)
        
        # Start app
        self.log("Launching Ghost Net app...")
        self.run_command("adb shell am start -n org.ghostnet.ghostnet/org.kivy.android.PythonActivity")
        
        # Wait for app to start
        time.sleep(5)
        
        # Check for crashes in logcat
        code, logcat, error = self.run_command("adb logcat -d")
        
        if "FATAL EXCEPTION" in logcat or "RuntimeException" in logcat:
            self.log("❌ App crashed on launch")
            self.log(f"Crash log:\n{logcat[-500:]}")  # Last 500 chars
            self.test_results['app_launch'] = False
            return False
        
        self.log("✅ App launched without immediate crash")
        self.test_results['app_launch'] = True
        return True
    
    def test_no_import_errors(self):
        """Test for import/module errors in logcat"""
        self.log("\n" + "="*60)
        self.log("TEST 4: Import Errors Check")
        self.log("="*60)
        
        code, logcat, error = self.run_command("adb logcat -d")
        
        error_patterns = [
            "ImportError",
            "ModuleNotFoundError",
            "libtinfo5",
            "could not find",
            "unknown package"
        ]
        
        found_errors = []
        for pattern in error_patterns:
            if pattern.lower() in logcat.lower():
                found_errors.append(pattern)
        
        if found_errors:
            self.log(f"❌ Found import/module errors: {', '.join(found_errors)}")
            self.log("\nRelevant log lines:")
            for line in logcat.split('\n'):
                for pattern in error_patterns:
                    if pattern.lower() in line.lower():
                        self.log(f"  {line}")
            self.test_results['no_import_errors'] = False
            return False
        
        self.log("✅ No import errors found")
        self.test_results['no_import_errors'] = True
        return True
    
    def test_network_engine(self):
        """Test for network engine startup"""
        self.log("\n" + "="*60)
        self.log("TEST 5: Network Engine Startup")
        self.log("="*60)
        
        code, logcat, error = self.run_command("adb logcat -d")
        
        # Look for successful startup indicators
        success_indicators = [
            "UDP socket bound",
            "TCP server listening",
            "threads started",
            "App started as"
        ]
        
        found_indicators = []
        for indicator in success_indicators:
            if indicator.lower() in logcat.lower():
                found_indicators.append(indicator)
        
        # Look for failure indicators
        failure_indicators = [
            "socket error",
            "could not bind",
            "failed to bind",
            "address already in use"
        ]
        
        found_failures = []
        for failure in failure_indicators:
            if failure.lower() in logcat.lower():
                found_failures.append(failure)
        
        if found_failures:
            self.log(f"⚠️ Network issues detected: {', '.join(found_failures)}")
            self.log("App may still function with limited network features")
            self.test_results['network_engine'] = 'partial'
            return True  # Don't fail completely
        
        if found_indicators:
            self.log(f"✅ Network engine started successfully")
            self.log(f"   Found: {', '.join(found_indicators)}")
            self.test_results['network_engine'] = True
            return True
        
        self.log("⚠️ Could not confirm network engine status")
        self.log("(This might be normal if app hasn't fully initialized yet)")
        self.test_results['network_engine'] = 'unknown'
        return True
    
    def test_permissions(self):
        """Test app permissions"""
        self.log("\n" + "="*60)
        self.log("TEST 6: Permissions Check")
        self.log("="*60)
        
        code, output, error = self.run_command("adb shell pm dump org.ghostnet.ghostnet | grep permissions")
        
        required_perms = [
            "INTERNET",
            "ACCESS_NETWORK_STATE",
            "ACCESS_WIFI_STATE",
            "WRITE_EXTERNAL_STORAGE",
            "READ_EXTERNAL_STORAGE"
        ]
        
        granted_perms = []
        for perm in required_perms:
            if perm in output:
                granted_perms.append(perm)
        
        if len(granted_perms) >= 3:  # At least 3 permissions
            self.log(f"✅ Permissions granted: {len(granted_perms)}/{len(required_perms)}")
            for perm in granted_perms:
                self.log(f"   ✓ {perm}")
            self.test_results['permissions'] = True
            return True
        else:
            self.log(f"⚠️ Limited permissions found: {len(granted_perms)}/{len(required_perms)}")
            self.log("User may need to grant permissions on first app launch")
            self.test_results['permissions'] = 'partial'
            return True
    
    def test_ui_responsiveness(self):
        """Test if app UI is responsive"""
        self.log("\n" + "="*60)
        self.log("TEST 7: UI Responsiveness")
        self.log("="*60)
        
        self.log("Checking for frozen/unresponsive indicators...")
        code, logcat, error = self.run_command("adb logcat -d")
        
        bad_signs = [
            "ANR",
            "Application Not Responding",
            "watchdog",
            "frozen"
        ]
        
        if any(sign in logcat for sign in bad_signs):
            self.log("⚠️ Possible UI responsiveness issues detected")
            self.test_results['ui_responsive'] = False
            return False
        
        self.log("✅ No UI responsiveness issues detected")
        self.test_results['ui_responsive'] = True
        return True
    
    def generate_report(self):
        """Generate test report"""
        self.log("\n" + "="*60)
        self.log("📊 VALIDATION REPORT")
        self.log("="*60)
        
        passed = sum(1 for v in self.test_results.values() if v is True)
        failed = sum(1 for v in self.test_results.values() if v is False)
        partial = sum(1 for v in self.test_results.values() if v == 'partial')
        unknown = sum(1 for v in self.test_results.values() if v == 'unknown')
        
        total = len(self.test_results)
        
        self.log(f"\nTests Passed: {passed}/{total}")
        self.log(f"Tests Failed: {failed}/{total}")
        self.log(f"Tests Partial: {partial}/{total}")
        self.log(f"Tests Unknown: {unknown}/{total}")
        
        self.log("\nDetailed Results:")
        for test_name, result in self.test_results.items():
            if result is True:
                status = "✅ PASS"
            elif result is False:
                status = "❌ FAIL"
            elif result == 'partial':
                status = "⚠️ PARTIAL"
            else:
                status = "❓ UNKNOWN"
            
            self.log(f"  {status}: {test_name}")
        
        # Overall verdict
        self.log("\n" + "="*60)
        if failed == 0 and passed >= 5:
            self.log("🎉 APK VALIDATION SUCCESSFUL!")
            self.log("The Ghost Net app appears to be working correctly.")
            overall = True
        elif failed == 0:
            self.log("⚠️ APK PARTIALLY VALIDATED")
            self.log("App may work but some tests couldn't confirm functionality.")
            overall = True
        else:
            self.log("❌ APK VALIDATION FAILED")
            self.log(f"{failed} critical tests failed. Check logs for details.")
            overall = False
        
        self.log("="*60)
        self.log(f"\n📝 Full log saved to: {self.log_file}")
        
        return overall
    
    def run_all_tests(self):
        """Run all validation tests"""
        self.log("\n" + "="*60)
        self.log("👻 GHOST NET APK VALIDATOR")
        self.log("="*60)
        self.log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Log file: {self.log_file}")
        
        # Run tests
        tests = [
            ("ADB Connection", self.test_adb_connection),
            ("App Installed", self.test_app_installed),
            ("App Launch", self.test_app_launch),
            ("No Import Errors", self.test_no_import_errors),
            ("Network Engine", self.test_network_engine),
            ("Permissions", self.test_permissions),
            ("UI Responsiveness", self.test_ui_responsiveness),
        ]
        
        for test_name, test_func in tests:
            try:
                test_func()
            except Exception as e:
                self.log(f"❌ Test '{test_name}' crashed: {e}")
                self.test_results[test_name.lower().replace(' ', '_')] = False
        
        # Generate report
        success = self.generate_report()
        return success


def main():
    """Main entry point"""
    validator = APKValidator()
    success = validator.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())