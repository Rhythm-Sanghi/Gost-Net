# Ghost Net - Development Cheat Sheet

One-page reference for all local development commands and workflows.

---

## 🚀 First-Time Setup (5 minutes)

```bash
python -m venv venv
venv\Scripts\activate                    # Windows CMD
source venv/bin/activate                 # WSL2/Linux/Mac

pip install --upgrade pip
pip install -r requirements.txt
```

---

## 💻 Desktop Testing (Instant Feedback)

### Run App on Your Laptop
```bash
python main.py
```

**What happens:**
- Kivy window opens
- `android_mocks.py` detects non-Android platform
- Mock WiFi/Bluetooth APIs log debug messages
- App runs without crashes from missing `pyjnius`

### Check Syntax Before Running
```bash
python -m compileall .
```

If any syntax error exists (missing colon, unclosed bracket), compilation stops immediately with line number.

### One-Command: Check Syntax → Run
```bash
python -m compileall . && python main.py
```

---

## 📱 Android Phone Testing (20-30 min first time)

### Prerequisites
- WSL2 or Linux machine (Buildozer needs Linux kernel)
- Android phone with USB Debugging enabled
- Phone connected via USB

### Build APK
```bash
buildozer android debug
```

Output: `bin/ghostnet-1.0.0-debug.apk` (~40-50 MB)

**Time:** 20-30 minutes (first time), 5-10 minutes (subsequent)

### Deploy to Phone & Stream Logs
```bash
buildozer android debug deploy run logcat
```

This single command:
1. Builds APK (if needed)
2. Pushes to phone via ADB
3. Launches app
4. Streams logs in real-time

Look for errors starting with `E/` in red.

### View Logs Only (App Already Running)
```bash
adb logcat | grep -i ghostnet
```

### Rebuild & Redeploy (Fast Iteration)
```bash
python -m compileall . && buildozer android debug deploy run logcat
```

---

## 🔍 Typical Debugging Workflow

### Desktop Bug Testing Loop
1. Edit code: `nano network.py`
2. Check syntax: `python -m compileall .`
3. Run: `python main.py` (5 seconds)
4. Press `ESC` to exit
5. Go to step 1

### Phone Debug Loop
1. Edit code: `nano main.py`
2. Check syntax: `python -m compileall .`
3. Deploy: `buildozer android debug deploy run logcat` (10-15 sec)
4. Watch logs scroll in terminal
5. Fix errors, go to step 1

---

## 📋 File Structure

| File | Purpose | When to Edit |
|------|---------|--------------|
| `main.py` | Main Kivy app & screens | UI/logic changes |
| `network.py` | P2P networking engine | Network protocol changes |
| `android_*.py` | Android-specific modules | Platform-specific APIs |
| `config.py` | User settings storage | Config schema/defaults |
| `storage.py` | Message database | Storage/persistence logic |
| `android_mocks.py` | Desktop API mocks | Platform detection (rarely) |
| `buildozer.spec` | APK build config | Build settings (rarely) |
| `requirements.txt` | Python dependencies | Add new packages here |

---

## 🛠️ Common Tasks

### Add New Python Dependency
```bash
pip install package_name
pip freeze > requirements.txt
```

Then commit `requirements.txt`. Next venv setup will install it.

### Rebuild APK from Scratch
```bash
buildozer android clean
buildozer android debug
```

(Use if APK is corrupted or build cache is stale)

### View Current Platform
```bash
python -c "from kivy.utils import platform; print(f'Platform: {platform()}')"
```

### Test Import Without Running
```bash
python -c "import main; print('Import OK')"
```

### Check for Circular Imports
```bash
python -c "import network; import config; import storage; print('All imports OK')"
```

---

## ⚙️ Buildozer Configuration

Located in `buildozer.spec`. Key settings:

```ini
[app]
title = Ghost Net
package.name = ghostnet
package.domain = org.ghostnet
version = 1.0.0

[app:android]
android.api = 33              # Target API
android.minapi = 21           # Minimum API
android.archs = arm64-v8a,armeabi-v7a  # CPU architectures
android.permissions = INTERNET,ACCESS_NETWORK_STATE,...
```

**No changes needed unless:**
- Targeting older Android devices: Lower `android.minapi`
- Building for different CPU: Modify `android.archs`
- Adding new Android features: Add to `android.permissions`

---

## 🐛 Troubleshooting

| Problem | Command to Try |
|---------|----------------|
| App won't start on desktop | `python -m compileall .` |
| Missing Python packages | `pip install -r requirements.txt` |
| App crashes on phone | `buildozer android debug deploy run logcat` |
| Old APK not updating | `buildozer android clean && buildozer android debug` |
| Syntax errors not caught | `python -m py_compile *.py` |
| Buildozer not found (WSL2) | `pip install buildozer --user` |
| Phone not detected | `adb devices` (check USB Debugging enabled) |
| WiFi Direct doesn't work | Expected on desktop (mocked). Test on real phone. |

---

## 📊 Development Metrics

| Task | Time | Frequency |
|------|------|-----------|
| Edit code | Variable | Every change |
| Syntax check | <1 sec | Before every run |
| Test on desktop | 5-30 sec | Every logic change |
| Build APK | 5-30 min | First build, clean builds |
| Deploy to phone | 10-15 sec | Every APK rebuild |
| View logs | Instant | When debugging |

**Total iteration time (phone):** ~20-30 seconds per change after first build

---

## 📞 Platform Detection in Code

Use this to customize behavior:

```python
from android_mocks import is_android

if is_android():
    print("Running on Android - real APIs available")
else:
    print("Running on desktop - APIs mocked")
```

Or get mock instances:

```python
from android_mocks import get_android_wifi_direct, get_android_bluetooth

wifi = get_android_wifi_direct()      # Mock on desktop, real on Android
bt = get_android_bluetooth()          # Mock on desktop, real on Android
```

---

## 🔐 Environment Variables (Optional)

For advanced users:

```bash
BUILDOZER_LOG_LEVEL=2                 # Verbose build logs
ANDROID_SDK_ROOT=/path/to/android-sdk
ANDROID_NDK_ROOT=/path/to/android-ndk
```

---

## 📚 Documentation Files

Generated for you:

- **LOCAL_DEVELOPMENT_SETUP.md** — Detailed step-by-step guide
- **QUICK_START_COMMANDS.md** — Command reference with examples
- **ANDROID_MOCKS_INTEGRATION.md** — How to use android_mocks.py in code
- **Development_Cheat_Sheet.md** — This file!

---

## ✅ Pre-Deployment Checklist

Before building final APK:

- [ ] Syntax check passes: `python -m compileall .`
- [ ] Desktop test passes: `python main.py` (no crashes)
- [ ] Manual testing done on laptop (UI, inputs, logic)
- [ ] All imports tested: `python -c "import main; import network; import config"`
- [ ] buildozer.spec reviewed for correct permissions
- [ ] APK builds without errors: `buildozer android debug`
- [ ] APK deploys to phone: `buildozer android debug deploy run`
- [ ] App starts on phone without crashes
- [ ] Core features tested on phone (messaging, file transfer, settings)

---

## 🚨 Emergency Commands

Nuke everything and rebuild:

```bash
buildozer clean
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
buildozer android debug
```

Check what's eating disk space:

```bash
du -sh .buildozer/*
du -sh bin/
```

---

## 💡 Pro Tips

1. **Keep terminal open** — Logs stay visible while editing in VS Code
2. **Use `&&` chaining** — `syntax check && run` prevents wasted time
3. **Terminal at bottom** — Easy to see compile errors without switching windows
4. **Phone across desk** — Watch app in real-time while logs stream in terminal
5. **Commit working versions** — `git commit` before major changes
6. **Test on desktop first** — Save 10 minutes vs re-building APK

---

## 📖 Further Reading

- Kivy docs: https://kivy.org/doc/stable/
- KivyMD docs: https://kivymd.readthedocs.io/
- Buildozer docs: https://buildozer.readthedocs.io/
- Android Permissions: https://developer.android.com/guide/topics/permissions/overview
