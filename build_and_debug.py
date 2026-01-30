#!/usr/bin/env python3
"""
Ghost Net - Build and Debug Helper Script
Automated build process with crash fixes and diagnostics.
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path

def print_banner():
    """Print the script banner."""
    print("\n" + "="*80)
    print("👻 GHOST NET - BUILD & DEBUG HELPER")
    print("="*80)
    print("This script will:")
    print("1. Run crash diagnostics to validate fixes")
    print("2. Clean previous build artifacts")
    print("3. Build APK with crash-resistant configuration")
    print("4. Provide debugging instructions")
    print("="*80 + "\n")

def run_crash_diagnostics():
    """Run crash diagnostics before building."""
    print("🔍 STEP 1: Running crash diagnostics...")
    print("-" * 60)
    
    try:
        result = subprocess.run([sys.executable, "crash_diagnostics.py"], 
                              capture_output=True, text=True)
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode != 0:
            print("⚠️ Some diagnostic tests failed - check crash_diagnostics.log")
            print("   Continuing with build anyway...")
        else:
            print("✅ All diagnostic tests passed!")
        
        return True
        
    except Exception as e:
        print(f"❌ Could not run diagnostics: {e}")
        print("   Continuing with build...")
        return False

def clean_build():
    """Clean previous build artifacts."""
    print("\n🧹 STEP 2: Cleaning build artifacts...")
    print("-" * 60)
    
    # Directories to clean
    clean_dirs = [
        ".buildozer",
        "bin",
        "__pycache__",
        ".kivy",
        "build"
    ]
    
    # Files to clean
    clean_files = [
        "ghostnet.db",
        "secret.key",
        "settings.json"
    ]
    
    cleaned = 0
    
    for dir_name in clean_dirs:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"✅ Removed directory: {dir_name}")
                cleaned += 1
            except Exception as e:
                print(f"⚠️ Could not remove {dir_name}: {e}")
    
    for file_name in clean_files:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                print(f"✅ Removed file: {file_name}")
                cleaned += 1
            except Exception as e:
                print(f"⚠️ Could not remove {file_name}: {e}")
    
    if cleaned == 0:
        print("ℹ️ No artifacts to clean")
    else:
        print(f"✅ Cleaned {cleaned} items")

def verify_buildozer_config():
    """Verify buildozer.spec has the correct fixes."""
    print("\n🔧 STEP 3: Verifying buildozer configuration...")
    print("-" * 60)
    
    if not os.path.exists("buildozer.spec"):
        print("❌ buildozer.spec not found!")
        return False
    
    with open("buildozer.spec", "r") as f:
        content = f.read()
    
    # Check for fixes
    checks = [
        ("KivyMD version fix", "kivymd==1.1.1" in content),
        ("Android API 33", "android.api = 33" in content),
        ("Required permissions", "INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE" in content),
        ("Android archs", "arm64-v8a, armeabi-v7a" in content),
    ]
    
    all_good = True
    for check_name, check_result in checks:
        if check_result:
            print(f"✅ {check_name}")
        else:
            print(f"❌ {check_name}")
            all_good = False
    
    return all_good

def build_apk():
    """Build the APK using buildozer."""
    print("\n🏗️ STEP 4: Building APK...")
    print("-" * 60)
    print("This may take 10-30 minutes on first build...")
    print("Subsequent builds will be faster.")
    print("")
    
    try:
        # Run buildozer android debug
        result = subprocess.run(
            ["buildozer", "android", "debug"],
            cwd=".",
            text=True
        )
        
        if result.returncode == 0:
            print("\n✅ APK build completed successfully!")
            
            # Find the APK
            bin_dir = Path("bin")
            if bin_dir.exists():
                apk_files = list(bin_dir.glob("*.apk"))
                if apk_files:
                    apk_path = apk_files[0]
                    print(f"📱 APK location: {apk_path}")
                    return str(apk_path)
            
            print("📱 APK should be in ./bin/ directory")
            return "bin/ghostnet-*-debug.apk"
        else:
            print("\n❌ APK build failed!")
            return None
            
    except FileNotFoundError:
        print("❌ buildozer command not found!")
        print("   Install with: pip install buildozer")
        return None
    except Exception as e:
        print(f"❌ Build error: {e}")
        return None

def show_debugging_instructions(apk_path):
    """Show debugging and installation instructions."""
    print("\n🐛 STEP 5: Debugging Instructions")
    print("=" * 60)
    
    print("\n1. INSTALL APK:")
    print(f"   adb install {apk_path}")
    print("   (Make sure USB debugging is enabled)")
    
    print("\n2. VIEW LOGS (in real-time):")
    print("   adb logcat | grep -i 'python\\|ghost\\|kivy'")
    
    print("\n3. VIEW SPECIFIC APP LOGS:")
    print("   adb logcat | grep org.ghostnet.ghostnet")
    
    print("\n4. CRASH ANALYSIS:")
    print("   adb logcat | grep -i 'androidruntime\\|crash\\|exception'")
    
    print("\n5. IF APP STILL CRASHES:")
    print("   a) Check logs for import errors")
    print("   b) Verify Android permissions in device settings")
    print("   c) Try installing on different Android device/version")
    print("   d) Run: python crash_diagnostics.py")
    
    print("\n6. COMMON FIXES:")
    print("   • Update buildozer: pip install --upgrade buildozer")
    print("   • Clean build: rm -rf .buildozer")
    print("   • Check Android SDK/NDK versions")
    
    print("\n📊 SUCCESS INDICATORS:")
    print("   ✅ App opens and shows Ghost Net boot screen")
    print("   ✅ No import/module errors in logcat")
    print("   ✅ Permissions requested successfully")
    print("   ✅ Network engine starts without socket errors")

def main():
    """Main build and debug process."""
    print_banner()
    
    # Step 1: Run diagnostics
    run_crash_diagnostics()
    
    # Step 2: Clean build
    clean_build()
    
    # Step 3: Verify config
    if not verify_buildozer_config():
        print("\n❌ Buildozer configuration issues detected!")
        print("   Please check buildozer.spec file")
        return 1
    
    # Ask user if they want to proceed with build
    print("\n" + "="*60)
    response = input("Proceed with APK build? (y/N): ").lower().strip()
    if response not in ['y', 'yes']:
        print("Build cancelled.")
        return 0
    
    # Step 4: Build APK
    apk_path = build_apk()
    
    # Step 5: Show instructions
    if apk_path:
        show_debugging_instructions(apk_path)
        
        print("\n" + "="*80)
        print("🎉 BUILD COMPLETE!")
        print("="*80)
        print("Your Android APK is ready for testing.")
        print("Follow the debugging instructions above if issues occur.")
        return 0
    else:
        print("\n" + "="*80)
        print("❌ BUILD FAILED!")
        print("="*80)
        print("Check the error messages above and try again.")
        return 1

if __name__ == "__main__":
    sys.exit(main())