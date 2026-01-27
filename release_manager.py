#!/usr/bin/env python3
"""
Ghost Net Release Manager
Automates the Android APK signing process for production releases.

This script:
1. Checks environment (Java, Buildozer, Android SDK tools)
2. Generates or uses existing keystore
3. Builds release APK with Buildozer
4. Signs the APK with apksigner
5. Verifies the signature
6. Calculates checksums (MD5, SHA256)
7. Outputs final APK to dist/ folder

Usage:
    python release_manager.py

Requirements:
    - buildozer
    - Java JDK (for keytool)
    - Android SDK Build Tools (for apksigner, zipalign)
"""

import os
import sys
import subprocess
import shutil
import hashlib
import getpass
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")


def print_step(step_num, text):
    """Print formatted step."""
    print(f"{Colors.OKCYAN}{Colors.BOLD}[Step {step_num}]{Colors.ENDC} {text}")


def print_success(text):
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def check_command(command, description):
    """
    Check if a command is available.
    
    Args:
        command: Command to check
        description: Human-readable description
        
    Returns:
        bool: True if command exists, False otherwise
    """
    try:
        result = subprocess.run(
            [command, '--version'] if command != 'java' else ['java', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 or (command == 'java' and result.stderr):
            print_success(f"{description} found")
            return True
        else:
            print_error(f"{description} not found")
            return False
    except FileNotFoundError:
        print_error(f"{description} not found")
        return False
    except Exception as e:
        print_error(f"Error checking {description}: {e}")
        return False


def check_environment():
    """
    Check if all required tools are installed.
    
    Returns:
        bool: True if environment is ready, False otherwise
    """
    print_step(1, "Checking environment...")
    
    checks = [
        ('python3', 'Python 3'),
        ('buildozer', 'Buildozer'),
        ('java', 'Java JDK'),
    ]
    
    all_ok = True
    for command, description in checks:
        if not check_command(command, description):
            all_ok = False
    
    # Check for Android SDK (optional but recommended)
    android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if android_home and os.path.exists(android_home):
        print_success(f"Android SDK found at {android_home}")
    else:
        print_warning("ANDROID_HOME not set (Buildozer will download SDK)")
    
    if not all_ok:
        print_error("\nMissing required tools. Install them and try again.")
        print("\nInstallation guide:")
        print("  • Buildozer: pip install buildozer")
        print("  • Java JDK: https://adoptium.net/")
        print("  • Android SDK: Set ANDROID_HOME environment variable")
        return False
    
    print_success("\n✓ Environment check passed!\n")
    return True


def generate_keystore(keystore_path, keystore_password, key_alias):
    """
    Generate a new Android keystore if it doesn't exist.
    
    Args:
        keystore_path: Path to keystore file
        keystore_password: Password for keystore
        key_alias: Alias for the signing key
        
    Returns:
        bool: True if successful, False otherwise
    """
    if os.path.exists(keystore_path):
        print_warning(f"Keystore already exists: {keystore_path}")
        response = input("Use existing keystore? (y/n): ").lower()
        if response == 'y':
            return True
        else:
            print("Aborting. Delete the existing keystore manually if needed.")
            return False
    
    print_step(2, f"Generating new keystore: {keystore_path}")
    
    # Collect information for certificate
    print("\nEnter certificate information:")
    cn = input("  Your name (CN): ") or "Ghost Net Developer"
    ou = input("  Organization unit (OU): ") or "Ghost Net"
    o = input("  Organization (O): ") or "Ghost Net Project"
    l = input("  City (L): ") or "Unknown"
    st = input("  State (ST): ") or "Unknown"
    c = input("  Country code (C, 2 letters): ") or "US"
    
    dname = f"CN={cn}, OU={ou}, O={o}, L={l}, ST={st}, C={c}"
    
    # Generate keystore
    cmd = [
        'keytool',
        '-genkeypair',
        '-v',
        '-keystore', keystore_path,
        '-alias', key_alias,
        '-keyalg', 'RSA',
        '-keysize', '2048',
        '-validity', '10000',
        '-storepass', keystore_password,
        '-keypass', keystore_password,
        '-dname', dname
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print_success(f"Keystore generated: {keystore_path}")
            print_warning(f"⚠ IMPORTANT: Backup this keystore! You cannot update your app without it!")
            return True
        else:
            print_error(f"Failed to generate keystore: {result.stderr}")
            return False
    except Exception as e:
        print_error(f"Error generating keystore: {e}")
        return False


def build_release_apk():
    """
    Build release APK using Buildozer.
    
    Returns:
        bool: True if successful, False otherwise
    """
    print_step(3, "Building release APK with Buildozer...")
    print("This may take 10-30 minutes on first run (downloading dependencies).\n")
    
    try:
        # Run buildozer in the current directory
        result = subprocess.run(
            ['buildozer', 'android', 'release'],
            cwd='.',
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            print_success("APK built successfully")
            return True
        else:
            print_error("Buildozer build failed")
            return False
            
    except subprocess.TimeoutExpired:
        print_error("Build timed out (>1 hour). Check your internet connection.")
        return False
    except Exception as e:
        print_error(f"Build error: {e}")
        return False


def find_unsigned_apk():
    """
    Find the unsigned release APK.
    
    Returns:
        Path object or None: Path to unsigned APK
    """
    # Buildozer outputs to bin/ directory
    bin_dir = Path('.buildozer/android/platform/build-*/dists/ghostnet/build/outputs/apk/release/')
    
    # Try to find with glob pattern
    apk_files = list(Path('.buildozer').glob('**/outputs/apk/release/*-unsigned.apk'))
    
    if apk_files:
        return apk_files[0]
    
    # Fallback: check bin directory
    bin_path = Path('bin')
    if bin_path.exists():
        apk_files = list(bin_path.glob('*-release-unsigned.apk'))
        if apk_files:
            return apk_files[0]
    
    return None


def sign_apk(unsigned_apk, signed_apk, keystore_path, keystore_password, key_alias):
    """
    Sign the APK using apksigner or jarsigner.
    
    Args:
        unsigned_apk: Path to unsigned APK
        signed_apk: Path for signed APK output
        keystore_path: Path to keystore
        keystore_password: Keystore password
        key_alias: Key alias
        
    Returns:
        bool: True if successful, False otherwise
    """
    print_step(4, "Signing APK...")
    
    # First, try to align the APK with zipalign (if available)
    aligned_apk = unsigned_apk.with_name(unsigned_apk.stem + '-aligned.apk')
    
    try:
        # Try zipalign
        zipalign_result = subprocess.run(
            ['zipalign', '-v', '-p', '4', str(unsigned_apk), str(aligned_apk)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if zipalign_result.returncode == 0:
            print_success("APK aligned with zipalign")
            apk_to_sign = aligned_apk
        else:
            print_warning("zipalign not available or failed, using unaligned APK")
            apk_to_sign = unsigned_apk
            
    except FileNotFoundError:
        print_warning("zipalign not found, using unaligned APK")
        apk_to_sign = unsigned_apk
    except Exception as e:
        print_warning(f"zipalign error: {e}, using unaligned APK")
        apk_to_sign = unsigned_apk
    
    # Try apksigner (preferred)
    try:
        apksigner_cmd = [
            'apksigner', 'sign',
            '--ks', keystore_path,
            '--ks-pass', f'pass:{keystore_password}',
            '--ks-key-alias', key_alias,
            '--out', str(signed_apk),
            str(apk_to_sign)
        ]
        
        result = subprocess.run(
            apksigner_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print_success(f"APK signed with apksigner: {signed_apk}")
            
            # Clean up aligned APK if it exists
            if aligned_apk.exists() and aligned_apk != unsigned_apk:
                aligned_apk.unlink()
            
            return True
        else:
            print_error(f"apksigner failed: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print_warning("apksigner not found, trying jarsigner...")
        
        # Fallback to jarsigner
        try:
            jarsigner_cmd = [
                'jarsigner',
                '-verbose',
                '-sigalg', 'SHA256withRSA',
                '-digestalg', 'SHA-256',
                '-keystore', keystore_path,
                '-storepass', keystore_password,
                '-signedjar', str(signed_apk),
                str(apk_to_sign),
                key_alias
            ]
            
            result = subprocess.run(
                jarsigner_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print_success(f"APK signed with jarsigner: {signed_apk}")
                
                # Clean up aligned APK if it exists
                if aligned_apk.exists() and aligned_apk != unsigned_apk:
                    aligned_apk.unlink()
                
                return True
            else:
                print_error(f"jarsigner failed: {result.stderr}")
                return False
                
        except Exception as e:
            print_error(f"Signing error: {e}")
            return False


def verify_signature(signed_apk):
    """
    Verify the APK signature.
    
    Args:
        signed_apk: Path to signed APK
        
    Returns:
        bool: True if verification passed, False otherwise
    """
    print_step(5, "Verifying APK signature...")
    
    try:
        # Try apksigner verify
        result = subprocess.run(
            ['apksigner', 'verify', '--verbose', str(signed_apk)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print_success("APK signature verified with apksigner")
            return True
        else:
            print_error(f"Signature verification failed: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print_warning("apksigner not found, trying jarsigner...")
        
        # Fallback to jarsigner
        try:
            result = subprocess.run(
                ['jarsigner', '-verify', '-verbose', '-certs', str(signed_apk)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and 'jar verified' in result.stdout.lower():
                print_success("APK signature verified with jarsigner")
                return True
            else:
                print_error(f"Signature verification failed: {result.stdout}")
                return False
                
        except Exception as e:
            print_error(f"Verification error: {e}")
            return False


def calculate_checksum(file_path, algorithm='md5'):
    """
    Calculate file checksum.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm ('md5' or 'sha256')
        
    Returns:
        str: Hexadecimal checksum
    """
    hash_obj = hashlib.md5() if algorithm == 'md5' else hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()


def create_dist_package(signed_apk, version='1.0.0'):
    """
    Create distribution package in dist/ folder.
    
    Args:
        signed_apk: Path to signed APK
        version: Version string
        
    Returns:
        Path: Path to final APK in dist/
    """
    print_step(6, "Creating distribution package...")
    
    # Create dist directory
    dist_dir = Path('dist')
    dist_dir.mkdir(exist_ok=True)
    
    # Copy APK with version name
    final_apk = dist_dir / f'GhostNet_v{version}.apk'
    shutil.copy2(signed_apk, final_apk)
    
    print_success(f"APK copied to: {final_apk}")
    
    # Calculate checksums
    print("\nCalculating checksums...")
    md5_hash = calculate_checksum(final_apk, 'md5')
    sha256_hash = calculate_checksum(final_apk, 'sha256')
    
    print(f"  MD5:    {md5_hash}")
    print(f"  SHA256: {sha256_hash}")
    
    # Write checksums to file
    checksum_file = dist_dir / f'GhostNet_v{version}.checksums.txt'
    with open(checksum_file, 'w') as f:
        f.write(f"Ghost Net v{version} - Checksums\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(f"File: {final_apk.name}\n")
        f.write(f"Size: {final_apk.stat().st_size:,} bytes\n\n")
        f.write(f"MD5:    {md5_hash}\n")
        f.write(f"SHA256: {sha256_hash}\n\n")
        f.write(f"Verify with:\n")
        f.write(f"  md5sum {final_apk.name}\n")
        f.write(f"  sha256sum {final_apk.name}\n")
    
    print_success(f"Checksums written to: {checksum_file}")
    
    return final_apk


def main():
    """Main release manager workflow."""
    print_header("Ghost Net Release Manager v1.0.0")
    
    # Configuration
    VERSION = '1.0.0'
    KEYSTORE_PATH = 'ghostnet.keystore'
    KEY_ALIAS = 'ghostnet'
    
    # Step 1: Check environment
    if not check_environment():
        sys.exit(1)
    
    # Step 2: Handle keystore
    print_step(2, "Checking keystore...")
    
    if not os.path.exists(KEYSTORE_PATH):
        print(f"\nKeystore not found: {KEYSTORE_PATH}")
        print("A keystore is required to sign your APK.")
        create_new = input("Generate new keystore? (y/n): ").lower()
        
        if create_new != 'y':
            print_error("Cannot proceed without keystore. Exiting.")
            sys.exit(1)
        
        # Get keystore password
        print("\nEnter keystore password (min 6 characters):")
        keystore_password = getpass.getpass("Password: ")
        keystore_password_confirm = getpass.getpass("Confirm password: ")
        
        if keystore_password != keystore_password_confirm:
            print_error("Passwords don't match. Exiting.")
            sys.exit(1)
        
        if len(keystore_password) < 6:
            print_error("Password too short (min 6 characters). Exiting.")
            sys.exit(1)
        
        if not generate_keystore(KEYSTORE_PATH, keystore_password, KEY_ALIAS):
            sys.exit(1)
    else:
        print_success(f"Keystore found: {KEYSTORE_PATH}")
        keystore_password = getpass.getpass("Enter keystore password: ")
    
    # Step 3: Build release APK
    print("\n")
    build_confirm = input("Build release APK with Buildozer? This may take 10-30 minutes. (y/n): ").lower()
    if build_confirm != 'y':
        print_warning("Skipping build. Looking for existing unsigned APK...")
    else:
        if not build_release_apk():
            print_error("Build failed. Check buildozer output above.")
            sys.exit(1)
    
    # Find unsigned APK
    print("\nSearching for unsigned APK...")
    unsigned_apk = find_unsigned_apk()
    
    if not unsigned_apk:
        print_error("Could not find unsigned APK. Build may have failed.")
        print("Expected location: .buildozer/android/platform/build-*/dists/ghostnet/build/outputs/apk/release/")
        sys.exit(1)
    
    print_success(f"Found unsigned APK: {unsigned_apk}")
    
    # Step 4: Sign APK
    signed_apk = Path('ghostnet-release-signed.apk')
    if not sign_apk(unsigned_apk, signed_apk, KEYSTORE_PATH, keystore_password, KEY_ALIAS):
        sys.exit(1)
    
    # Step 5: Verify signature
    if not verify_signature(signed_apk):
        print_warning("Signature verification failed, but APK may still work.")
        proceed = input("Continue anyway? (y/n): ").lower()
        if proceed != 'y':
            sys.exit(1)
    
    # Step 6: Create distribution package
    final_apk = create_dist_package(signed_apk, VERSION)
    
    # Cleanup temporary signed APK
    if signed_apk.exists():
        signed_apk.unlink()
    
    # Success!
    print_header("Release Complete!")
    print(f"{Colors.OKGREEN}{Colors.BOLD}✓ Signed APK ready for distribution:{Colors.ENDC}")
    print(f"  {final_apk}")
    print(f"\n{Colors.OKGREEN}File size: {final_apk.stat().st_size:,} bytes{Colors.ENDC}")
    print(f"\n{Colors.WARNING}Next steps:{Colors.ENDC}")
    print(f"  1. Test the APK on a real Android device")
    print(f"  2. Upload to GitHub Releases or your website")
    print(f"  3. Share the download link and checksums")
    print(f"  4. Consider submitting to F-Droid or Play Store")
    print(f"\n{Colors.WARNING}⚠ IMPORTANT: Backup {KEYSTORE_PATH}!{Colors.ENDC}")
    print(f"  You cannot update your app without this keystore.\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Interrupted by user. Exiting.{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.FAIL}Unexpected error: {e}{Colors.ENDC}")
        sys.exit(1)
