[app]

title = Ghost Net

package.name = ghostnet

package.domain = org.ghostnet

source.dir = .

source.include_exts = py,png,jpg,kv,atlas,json

# Include the src/ package directory
source.include_dirs = src

source.exclude_dirs = tests,docs,scripts,assets/mockups,assets/web,.git,.github,.vscode,.idea,__pycache__,*.egg-info,build,dist
source.exclude_patterns = *.orig,*.pyc,*.pyo,*~,*.swp,.DS_Store,*badsyntax*.py,test_*.py

version = 1.0.0

requirements = hostpython3,python3,kivy==2.3.0,kivymd==1.2.0,asynckivy,asyncgui,pillow,cryptography,openssl,libffi,plyer

garden_requirements = mapview

presplash.filename = %(source.dir)s/presplash.png

icon.filename = %(source.dir)s/icon.png

orientation = portrait

services = GhostService:service.py

osx.python_version = 3

osx.kivy_version = 2.3.0

fullscreen = 0

android.presplash_color = #121212

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,CHANGE_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,WAKE_LOCK,NEARBY_WIFI_DEVICES,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,CHANGE_WIFI_STATE,LOCAL_MAC_ADDRESS,POST_NOTIFICATIONS,FOREGROUND_SERVICE,RECORD_AUDIO

android.api = 33

android.minapi = 21

android.ndk = 25b

android.sdk_path = /usr/local/lib/android/sdk

android.ndk_path = /usr/local/lib/android/sdk/ndk/25.1.8937393

android.accept_sdk_license = True

android.enable_androidx = True

android.manifest.activity_attrs = {"android:windowSoftInputMode": "adjustResize|stateHidden"}

android.wakelock = True

android.logcat_filters = *:S python:D
android.logcat_pid_only = True

android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True

# p4a.branch = master

p4a.log_level = ERROR

p4a.cython_directives = {"language_level": "3"}

p4a.release_dir = .buildozer/android/platform/build-{arch}/dist
android.release_artifact = aab

ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.10.0

ios.codesign.allowed = false

[buildozer]

log_level = 1

warn_on_root = 1
