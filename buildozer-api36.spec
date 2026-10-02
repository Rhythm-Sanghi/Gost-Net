# =============================================================================
# Gost-Net - Buildozer Specification: Modern Android Profile
# Profile: Android 16 (API 36) Google Play 2026 Target
# NDK: 27b (27.0.12077973) | Architecture: arm64-v8a
# Target: 16 KB Memory Page Size Alignment (-Wl,-z,max-page-size=16384)
# Note: Pending upstream python-for-android 16 KB ELF recipe stabilization
# =============================================================================

[app]

title = Gost-Net
package.name = ghostnet
package.domain = org.ghostnet
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,wav,mbtiles,txt
source.include_dirs = src
source.exclude_dirs = tests,docs,scripts,scratch,research,experiments,assets/mockups,assets/web,.git,.github,.vscode,.idea,__pycache__,*.egg-info,build,dist
source.exclude_patterns = *.orig,*.pyc,*.pyo,*~,*.swp,.DS_Store,*badsyntax*.py,test_*.py,scratch/*,verify_*.py

version = 1.0.0

requirements = hostpython3==3.11.9,python3==3.11.9,kivy==2.3.0,kivymd>=2.0.0,asynckivy,asyncgui,pillow,cryptography,openssl,libffi,plyer,netifaces,materialyoucolor

garden_requirements = mapview

presplash.filename = %(source.dir)s/presplash.png
icon.filename = %(source.dir)s/icon.png
orientation = portrait
services = GhostService:service.py
fullscreen = 0

android.presplash_color = #121212
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,CHANGE_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,WAKE_LOCK,NEARBY_WIFI_DEVICES,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,CHANGE_WIFI_STATE,POST_NOTIFICATIONS,FOREGROUND_SERVICE,RECORD_AUDIO

# Modern Android 16 Target
android.api = 36
android.minapi = 26
android.ndk = 27b
android.accept_sdk_license = True
android.enable_androidx = True
android.manifest.activity_attrs = {"android:windowSoftInputMode": "adjustResize|stateHidden"}
android.wakelock = True
android.logcat_filters = *:S python:D
android.logcat_pid_only = True
android.archs = arm64-v8a
android.allow_backup = False

# 16 KB Memory Page Size Alignment Flags for Android 16
# In NDK r27+, lld defaults to 16 KB alignment for arm64; explicit linker flag passed here:
p4a.extra_args = --extra-link-args="-Wl,-z,max-page-size=16384"
p4a.log_level = ERROR
p4a.cython_directives = {"language_level": "3"}
p4a.release_dir = .buildozer/android/platform/build-{arch}/dist
android.release_artifact = aab

[buildozer]
log_level = 1
warn_on_root = 1
