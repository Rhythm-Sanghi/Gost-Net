# =============================================================================
# Gost-Net - Buildozer Specification: Stable Sideload Profile
# Profile: Android 13 (API 33) Sideload / Direct Distribution
# NDK: 25b (25.1.8937393) | Architecture: arm64-v8a
# Tested: python-for-android stable recipe set, 4KB page alignment
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

android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.enable_androidx = True
android.manifest.activity_attrs = {"android:windowSoftInputMode": "adjustResize|stateHidden"}
android.wakelock = True
android.logcat_filters = *:S python:D
android.logcat_pid_only = True
android.archs = arm64-v8a
android.allow_backup = False

p4a.log_level = ERROR
p4a.cython_directives = {"language_level": "3"}
p4a.local_recipes = ./p4a_recipes
p4a.release_dir = .buildozer/android/platform/build-{arch}/dist
android.release_artifact = apk

[buildozer]
log_level = 1
warn_on_root = 1
