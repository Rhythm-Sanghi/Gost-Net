# Ghost Net - Quick Start Commands

## GOAL 1: Local Desktop Execution

### Setup (One-Time)
```bash
python -m venv venv
venv\Scripts\activate                    # Windows CMD
source venv/bin/activate                 # WSL2/Linux
pip install -r requirements.txt
```

### Run on Desktop
```bash
python main.py
```

The `android_mocks.py` module automatically detects your platform and mocks Android APIs on desktop. No crashes from missing `pyjnius` or Android-specific imports.

---

## GOAL 2: Syntax Error Checking

### Check All Python Files Before Running/Building
```bash
python -m compileall .
```

### One-Command: Check Syntax → Run App
```bash
python -m compileall . && python main.py
```

### Check Syntax → Build APK
```bash
python -m compileall . && buildozer android debug
```

If any `.py` file has a SyntaxError (missing colon, unmatched bracket, etc.), compilation stops immediately with error details.

---

## GOAL 3: Buildozer APK Building

### Prerequisites (WSL2/Linux Only)
```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev python3-venv git build-essential libssl-dev libffi-dev cython3 openjdk-11-jdk-headless android-sdk android-ndk
pip install buildozer
```

### Build APK (5-30 minutes depending on first/subsequent build)
```bash
buildozer android debug
```

Output: `bin/ghostnet-1.0.0-debug.apk`

### Deploy to Phone via USB (Requires USB Debugging Enabled)
```bash
buildozer android debug deploy run logcat
```

This:
1. Builds APK
2. Pushes to phone via ADB
3. Launches app
4. Streams crash logs in real-time

### View Only Logs (After App is Running)
```bash
adb logcat | grep -i ghostnet
```

---

## typical Development Workflow

**Desktop Testing Loop:**
```bash
# Edit code
nano main.py

# Check syntax instantly
python -m compileall .

# Test on desktop (5 seconds)
python main.py

# [Press ESC to exit]
```

**Phone Testing Loop:**
```bash
# Edit code
nano network.py

# Check syntax
python -m compileall .

# Build, deploy, and stream logs (5-15 seconds)
buildozer android debug deploy run logcat
```

---

## How It Works

### Android Mocks on Desktop
When you run `python main.py` on Windows/WSL2, the `android_mocks.py` module:
- Detects platform using `kivy.utils.platform`
- Returns **Mock classes** instead of real Android modules
- Prints debug logs like: `[MockWiFiDirect] Discovering peers (mock)`
- App runs without crashes

When Buildozer deploys to phone:
- Kivy detects `platform == 'android'`
- Real Android modules load instead
- App functions normally with full network/Bluetooth support

### Syntax Checking
`python -m compileall` compiles all `.py` files to bytecode `.pyc` files. If any file has syntax errors, it stops and reports the line number immediately—before runtime.

---

## Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: pyjnius` | Already handled by `android_mocks.py` |
| `SyntaxError in main.py line 42` | Run `python -m compileall .` |
| `buildozer: command not found` | Run `pip install buildozer` |
| APK won't deploy (USB issues) | Check `adb devices`, enable USB Debugging |
| App crashes on phone | Check logs: `buildozer android debug deploy run logcat` |

---

## File Locations

| File | Purpose |
|------|---------|
| `android_mocks.py` | Platform detection & Android API mocks for desktop |
| `LOCAL_DEVELOPMENT_SETUP.md` | Detailed setup guide (you're reading it!) |
| `buildozer.spec` | APK build configuration (already configured) |
| `bin/ghostnet-1.0.0-debug.apk` | Output APK after building |

---

## Platform Detection in Your Code

If you need to check platform in your own modules:

```python
from android_mocks import is_android

if is_android():
    print("Running on Android phone")
else:
    print("Running on desktop (mocking Android APIs)")
```

Or import real modules conditionally:

```python
from android_mocks import get_android_wifi_direct, get_android_bluetooth

wifi_direct = get_android_wifi_direct()   # Real on Android, Mock on desktop
bluetooth = get_android_bluetooth()       # Real on Android, Mock on desktop
```

---

## Next: Update Your Modules to Use Android Mocks

If your code imports Android-specific modules directly (like `pyjnius`, custom `android_*.py` files), wrap them:

**Before:**
```python
from pyjnius import autoclass  # Crashes on desktop!
WiFiManager = autoclass('android.net.wifi.WifiManager')
```

**After:**
```python
from android_mocks import is_android, conditional_import

if is_android():
    WiFiManager = conditional_import('pyjnius', 'autoclass')
else:
    WiFiManager = None
```

Or use the pre-built mock getters:

```python
from android_mocks import get_android_wifi_direct
wifi_direct = get_android_wifi_direct()  # Works everywhere!
```
