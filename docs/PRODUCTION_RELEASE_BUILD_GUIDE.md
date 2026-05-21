PRODUCTION_RELEASE_BUILD_GUIDE.md

Ghost Net - Production Release Build Configuration

OPSEC Log Suppression

The logger.py module automatically activates production mode on Android devices, completely suppressing sys.stdout and sys.stderr to prevent logcat USB snooping. This is transparent and requires no additional setup.

Key Security Features:
- All print() calls are silenced in production
- No cryptographic keys leak to logcat
- No GPS coordinates exposed in logs
- No plaintext data visible via USB debugging
- Zero logging overhead in production builds

Android Keystore Generation

Step 1: Generate the Keystore

Execute the generate_keys.sh script to create a 2048-bit RSA keystore valid for 10,000 days:

bash generate_keys.sh

The script will prompt for:
1. Keystore password (encrypt keystore file)
2. Key password (sign APK/AAB, can be same as keystore)

Step 2: Export Environment Variables

After successful keystore generation, export these variables before building:

export P4A_RELEASE_KEYSTORE='/path/to/ghostnet.keystore'
export P4A_RELEASE_KEYSTORE_PASSWD='your_keystore_password'
export P4A_RELEASE_KEYALIAS='ghostnet-release-key'
export P4A_RELEASE_KEYALIAS_PASSWD='your_key_password'

buildozer.spec Configuration for Release Builds

The buildozer.spec has been updated with these key settings:

1. OPSEC Logging Suppression:
   android.logcat_filters = *:S python:D
   android.logcat_pid_only = True

2. Build Tool Logging:
   p4a.log_level = ERROR
   log_level = 1

3. Release Output Configuration:
   p4a.release_dir = .buildozer/android/platform/build-{arch}/dist
   android.release_artifact = aab

These settings ensure:
- Minimal logcat noise in production
- No debug symbols in release build
- Bundle format (AAB) for Play Store submission
- Complete OPSEC compliance

Building the Release APK/AAB

Via Command Line:

buildozer android release

This automatically:
1. Reads P4A_RELEASE_KEYSTORE environment variables
2. Compiles with optimizations and no debug symbols
3. Signs the APK/AAB with the release key
4. Outputs to bin/ghostnet-1.0-release.aab

Building Specific Architecture:

buildozer android release -- --arch=arm64-v8a
buildozer android release -- --arch=armeabi-v7a

Clean Release Build (recommended):

buildozer android clean
buildozer android release

Signature Verification

Verify the APK/AAB signature:

jarsigner -verify -verbose bin/ghostnet-1.0-release.aab

Extract certificate info:

keytool -printcert -jarfile bin/ghostnet-1.0-release.aab

Critical Release Checklist

✓ Keystore generated with 2048-bit RSA
✓ Environment variables exported before build
✓ buildozer.spec contains release logging settings
✓ PRODUCTION_MODE activated (automatic on Android)
✓ No debug symbols in binary
✓ Logcat filtering enabled (python:D, *:S)
✓ APK/AAB signed with release key
✓ Signature verified before distribution
✓ logger.py present in project directory
✓ main.py contains OPSEC activation code

Play Store Distribution

The generated AAB (Android App Bundle) is the modern format required for Google Play Store:

1. Upload bin/ghostnet-1.0-release.aab to Play Console
2. Google Play auto-generates optimized APKs per device config
3. No additional signing required (Play App Signing handles this)

For direct APK distribution (outside Play Store):

1. Generate APK: buildozer android release
2. Output: bin/ghostnet-1.0-release-unsigned.apk
3. Sign with release key using jarsigner or apksigner
4. Distribute securely

Security Notes for Production

1. Keystore Security:
   - Store ghostnet.keystore in a secure location
   - Never commit to version control
   - Backup to secure encrypted storage
   - Restrict file permissions to 0600

2. Key Management:
   - Use strong passwords (minimum 20 characters, mixed case/symbols)
   - Never share keystore passwords or environment variables
   - Rotate keys every 2-3 years (generate new keystore if needed)
   - Keep keystore password in secure password manager

3. Build Security:
   - Build only on secure, offline machines when possible
   - Clear shell history after exporting environment variables
   - Use encrypted CI/CD pipelines if automating builds
   - Never log or display keystore passwords

4. Distribution Security:
   - Sign APK/AAB with release key for authenticity
   - Verify signatures before installation
   - Use HTTPS for all download channels
   - Include signature fingerprint in documentation

Advanced Configuration (Optional)

To further harden the release build, you can add these settings to buildozer.spec:

Android API Hardening:
android.api = 34
android.minapi = 24

Disable Debuggable Flag:
android.debuggable = 0

Enable ProGuard Obfuscation (requires custom rules):
android.gradle_dependencies = com.android.support:appcompat-v7:28.0.0

Release Build Environment Setup

Create a .env file (never commit to git):

P4A_RELEASE_KEYSTORE=/home/user/buildkeys/ghostnet.keystore
P4A_RELEASE_KEYSTORE_PASSWD=YourSecurePassword123!@#
P4A_RELEASE_KEYALIAS=ghostnet-release-key
P4A_RELEASE_KEYALIAS_PASSWD=YourSecurePassword123!@#

Load before building:

source .env
buildozer android release

Troubleshooting

Issue: "Keystore not found" during build
Solution: Verify P4A_RELEASE_KEYSTORE path is absolute and file exists

Issue: "Invalid password" error
Solution: Ensure P4A_RELEASE_KEYSTORE_PASSWD and P4A_RELEASE_KEYALIAS_PASSWD are correct

Issue: Logs appearing in production
Solution: Verify logger.py is present and main.py contains OPSEC activation code

Issue: Build fails with signature error
Solution: Verify keystore file is not corrupted, regenerate if needed

Version History

v1.0.0 - Initial production release configuration
- OPSEC log suppression
- 2048-bit RSA keystore generation
- Release build pipeline
- Play Store AAB output format
