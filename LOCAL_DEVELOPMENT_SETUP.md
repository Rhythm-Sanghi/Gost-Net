# Ghost Net - Local Development Setup Guide

Complete instructions to run Ghost Net on your Windows laptop (or WSL2) for instant UI/logic testing without GitHub Actions.

---

## GOAL 1: Local Desktop Execution (Instant UI Testing)

### Step 1: Create Python Virtual Environment

On **Windows CMD** (or WSL2 bash):

```bash
python -m venv venv
```

### Step 2: Activate Virtual Environment

**Windows CMD:**
```cmd
venv\Scripts\activate
```

**Windows PowerShell:**
```powershell
venv\Scripts\Activate.ps1
```

**WSL2/Linux:**
```bash
source venv/bin/activate
```

**Expected output:** Your command prompt should show `(venv)` prefix.

### Step 3: Install All Dependencies from requirements.txt

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Verify installation:**
```bash
pip list
```

You should see: `kivy==2.3.0`, `kivymd==1.2.0`, `pillow`, `cryptography`, `asynckivy`, etc.

---

### Step 4: Handle Android-Only Imports

Ghost Net uses Android-specific libraries (`pyjnius` for Wi-Fi Direct/Bluetooth). Running `python main.py` directly will crash with `ImportError` because these modules don't exist on desktop.

**Solution:** Use the `android_mocks.py` wrapper module that conditionally mocks Android imports on non-Android platforms.

#### How to Modify Your Code to Use Android Mocks:

In **any file that imports Android-specific modules**, add this at the top:

```python
from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

if is_android():
    wifi_direct = get_android_wifi_direct()
    bluetooth = get_android_bluetooth()
else:
    wifi_direct = get_android_wifi_direct()
    bluetooth = get_android_bluetooth()
```

The `android_mocks.py` module detects your platform using `kivy.utils.platform`:
- **On Android:** Returns real Android modules
- **On Desktop/WSL2:** Returns Mock classes that print debug messages instead of crashing

#### Example: Wrapping network.py

If `network.py` imports Android modules, modify it like this:

```python
from android_mocks import is_android, get_android_wifi_direct
from kivy.utils import platform

wifi_direct = get_android_wifi_direct()

if is_android():
    print("[Network] Running on Android")
else:
    print("[Network] Running on desktop (mocking Android APIs)")
```

---

### Step 5: Run the App on Desktop

```bash
python main.py
```

**Expected behavior:**
- Kivy window opens on your desktop
- Boot screen shows "Initializing..." with status updates
- No crashes from missing Android modules
- Mock classes log messages like: `[MockWiFiDirect] Discovering peers (mock)`

**To exit:** Press `ESC` or close the window.

---

### Step 6: Test UI Without Network

Since the app won't find real peers on desktop, you can:

1. **Test UI navigation:**
   - Click through the radar/chat/settings screens
   - Verify text input fields work
   - Check button responsiveness

2. **Test local logic:**
   - Add test peers manually to the UI
   - Test message sending/receiving (loopback)
   - Verify file selection dialogs

3. **Monitor console output:**
   - Watch for errors in the terminal
   - Check timestamp and status messages
   - Verify mock API calls are logged

---

## GOAL 2: Catching Syntax Errors Locally

### Compile All Python Files to Catch SyntaxError Instantly

Before running or building the APK, compile all `.py` files to catch syntax errors immediately:

```bash
python -m py_compile *.py
```

Or for all Python files recursively:

```bash
python -m compileall .
```

**Expected output:**
- If successful: No output (silent success)
- If syntax error: Error message like:
  ```
  SyntaxError in 'main.py' line 42: missing ':' in function definition
  ```

### Alternative: Run Python Syntax Check with AST

For more detailed error reporting:

```bash
python -c "import ast; [ast.parse(open(f).read()) for f in __import__('glob').glob('*.py')]"
```

### One-Command Workflow: Syntax Check → Run

Combine both steps:

```bash
python -m compileall . && python main.py
```

This will:
1. Compile all `.py` files and stop if any syntax errors exist
2. Only run `main.py` if compilation succeeds

### Add to VS Code Build Task (Optional)

Create `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Check Syntax & Run Ghost Net",
      "type": "shell",
      "command": "${workspaceFolder}/venv/Scripts/python",
      "args": ["-m", "compileall", ".", "&&", "python", "main.py"],
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "problemMatcher": []
    }
  ]
}
```

Then press `Ctrl+Shift+B` in VS Code to run this task.

---

## GOAL 3: Local APK Building (Buildozer)

### Prerequisites for Buildozer

Buildozer requires **Linux/WSL2** (not native Windows).

**On Windows 11:** Use WSL2 (Windows Subsystem for Linux 2)

```bash
wsl --install Ubuntu-22.04
```

Then open Ubuntu terminal and continue.

---

### Step 1: Install Buildozer Dependencies (WSL2/Linux)

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-venv \
    git \
    build-essential \
    libssl-dev \
    libffi-dev \
    cython3 \
    openjdk-11-jdk-headless \
    android-sdk \
    android-ndk
```

### Step 2: Install Buildozer

```bash
pip install --upgrade pip
pip install buildozer
```

**Verify:**
```bash
buildozer --version
```

---

### Step 3: Configure buildozer.spec

Your `buildozer.spec` is already configured. Key settings:

```ini
[app]
title = Ghost Net
package.name = ghostnet
package.domain = org.ghostnet
version = 1.0.0

[app:android]
android.api = 33
android.minapi = 21
android.archs = arm64-v8a,armeabi-v7a
android.permissions = INTERNET,ACCESS_NETWORK_STATE,CHANGE_WIFI_MULTICAST_STATE,...
```

No changes needed unless you want to build for a different API level.

---

### Step 4: Build APK Locally

```bash
cd /path/to/Zero_Net
buildozer android debug
```

**What happens:**
1. Buildozer downloads Android SDK, NDK, and build tools (~3-5 GB)
2. Compiles Python files to C/Cython
3. Packages everything into APK
4. Output: `bin/ghostnet-1.0.0-debug.apk`

**Time:** First build takes 20-30 minutes. Subsequent builds: 5-10 minutes.

**To skip the long setup on first build:**
```bash
buildozer android debug -- --accept-sdk-license
```

---

### Step 5: Deploy to Phone via USB

Connect your Android phone via USB and enable **USB Debugging** in Developer Options.

```bash
buildozer android debug deploy run
```

**What happens:**
1. Builds APK (if not already built)
2. Pushes APK to phone via `adb install`
3. Launches app automatically
4. Streams logs to terminal

**Expected output:**
```
[INFO] Installing apk on the default devices
[INFO] adb devices: ['device_id']
[INFO] Installing bin/ghostnet-1.0.0-debug.apk
[INFO] Installation succeeded
[INFO] Starting app org.ghostnet.ghostnet
[INFO] App started successfully
```

---

### Step 6: View Crash Logs in Real-Time

```bash
buildozer android debug deploy run logcat
```

This combines the deploy + run + continuous logcat streaming.

**Reading logcat output:**
```
I/python: [Network] Connected to peer
D/GhostNet: Received message from 192.168.1.5
E/GhostNet: [ERROR] Disk write failed
W/python: [WARNING] Memory low
```

**Log levels:**
- `I` = Info (blue)
- `D` = Debug (green)
- `W` = Warning (yellow)
- `E` = Error (red)

**Filter logs for Ghost Net only:**
```bash
adb logcat | grep -i ghostnet
```

---

### Step 7: Iterate Fast: Modify → Rebuild → Redeploy

Typical development cycle:

```bash
nano network.py              # Edit code
python -m compileall .       # Check syntax
python main.py               # Test on desktop (5 seconds)
buildozer android debug deploy run logcat   # Build & deploy to phone (5-15 sec)
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'pyjnius'"

**Cause:** Running on desktop, but code tried to import pyjnius (Android-only).

**Fix:** Use `android_mocks.py`:
```python
from android_mocks import is_android
if is_android():
    from pyjnius import autoclass
else:
    print("[Desktop] Mocking Android APIs")
```

---

### Issue: "Buildozer not found" (WSL2)

**Fix:**
```bash
pip install buildozer --user
export PATH="$HOME/.local/bin:$PATH"
buildozer --version
```

---

### Issue: APK Installation Fails ("Insufficient Storage")

**Fix:** Free up phone storage OR build release APK (smaller):
```bash
buildozer android release
```

---

### Issue: App Crashes Immediately on Phone

**View detailed logs:**
```bash
buildozer android debug deploy run logcat
```

Look for lines starting with `E/` or `FATAL`.

Common causes:
- Missing permission in `buildozer.spec`
- Incompatible Kivy/KivyMD version
- Unhandled exception in startup code

---

## Quick Reference: Terminal Commands

| Goal | Command |
|------|---------|
| Create venv | `python -m venv venv` |
| Activate venv (CMD) | `venv\Scripts\activate` |
| Activate venv (WSL2) | `source venv/bin/activate` |
| Install dependencies | `pip install -r requirements.txt` |
| Check syntax | `python -m compileall .` |
| Run on desktop | `python main.py` |
| Build APK | `buildozer android debug` |
| Deploy to phone | `buildozer android debug deploy run logcat` |

---

## Next Steps

1. **Set up venv** (5 min): Follow Step 1-3 of GOAL 1
2. **Test on desktop** (5 min): Run `python main.py`
3. **Fix syntax errors** (as needed): Use `python -m compileall .`
4. **Set up Buildozer** (30 min first time): Follow GOAL 3 steps 1-2
5. **Build & deploy** (20-30 min first build): Follow GOAL 3 steps 4-6
