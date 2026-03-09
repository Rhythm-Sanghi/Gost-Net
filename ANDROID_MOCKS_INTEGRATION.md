# Ghost Net - Android Mocks Integration Guide

Shows how to integrate `android_mocks.py` with your existing modules to enable desktop testing without Android crashes.

---

## Overview

Your Ghost Net codebase already has graceful fallbacks in `android_wifi_direct.py` and `android_bluetooth.py` (they check `PYJNIUS_AVAILABLE`). The `android_mocks.py` module provides an additional layer of mocking specifically for desktop environments.

**How it works:**
1. Desktop (`python main.py`): `kivy.utils.platform == 'linux'` → Mock classes activate
2. Android (Buildozer APK): `kivy.utils.platform == 'android'` → Real Android modules load

---

## Current State: What Already Works

### android_wifi_direct.py
```python
try:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    PYJNIUS_AVAILABLE = True
except ImportError:
    PYJNIUS_AVAILABLE = False
    logger.warning("[WiFiDirect] pyjnius not available - Wi-Fi Direct disabled")
```

✅ Already handles ImportError gracefully. When run on desktop, pyjnius import fails and code continues.

### android_bluetooth.py
```python
try:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    PYJNIUS_AVAILABLE = True
except ImportError:
    PYJNIUS_AVAILABLE = False
    logger.warning("[Bluetooth] pyjnius not available - Bluetooth disabled")
```

✅ Same pattern. Works on desktop by skipping Java interop.

---

## Recommended: Add Android Mocks for Better Desktop Testing

While your current code won't crash on desktop, it won't actually *test* the Android APIs at all—it will silently skip them. Using `android_mocks.py` gives you:

1. **Mock API responses** on desktop (e.g., fake peer lists)
2. **Debug logging** showing what Android APIs *would* be called
3. **Testable behavior** without a real phone

### Step 1: Import Android Mocks in network.py

```python
from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

class GhostEngine:
    def __init__(self, ...):
        self.is_android = is_android()
        
        if self.is_android:
            self.wifi_direct = get_android_wifi_direct()
            self.bluetooth = get_android_bluetooth()
            print("[GhostEngine] Running on Android with real WiFi Direct/Bluetooth")
        else:
            self.wifi_direct = get_android_wifi_direct()
            self.bluetooth = get_android_bluetooth()
            print("[GhostEngine] Running on desktop with mocked WiFi Direct/Bluetooth")
```

### Step 2: Use Mocked APIs in Your Code

```python
def discover_peers_via_wifi_direct(self):
    peers = self.wifi_direct.discover_peers()
    return peers
```

On desktop: Returns empty list (mock) + logs `[MockWiFiDirect] Discovering peers (mock)`
On Android: Returns actual discovered peers from Android WifiP2pManager

### Step 3: Add Conditional Logic for Desktop Testing

```python
def start(self):
    if self.is_android:
        self._start_android_discovery()
    else:
        self._start_desktop_discovery()

def _start_desktop_discovery(self):
    print("[GhostEngine] Desktop mode - using UDP broadcast only (no WiFi Direct)")
    
    self.wifi_direct.enable()
    print("[GhostEngine] WiFi Direct mock enabled (would be searching on Android)")

def _start_android_discovery(self):
    print("[GhostEngine] Android mode - starting WiFi Direct + Bluetooth discovery")
    self.wifi_direct.enable()
    self.bluetooth.enable()
```

---

## Quick Integration Checklist

- [ ] `android_mocks.py` exists in project root ✅
- [ ] Import in any Android-dependent modules:
  ```python
  from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth
  ```
- [ ] Replace direct Android API calls with mock getters:
  ```python
  # Before: wifi_direct = AndroidWiFiDirect()  # Crashes on desktop!
  # After:
  wifi_direct = get_android_wifi_direct()  # Mock on desktop, real on Android
  ```
- [ ] (Optional) Add `if is_android():` checks for Android-specific startup logic
- [ ] Test on desktop: `python main.py`
- [ ] Check for mock debug logs in terminal
- [ ] Build and test on phone: `buildozer android debug deploy run logcat`

---

## Example: Full Integration in Custom Module

**my_network_module.py (Before - Crashes on Desktop):**
```python
from android_wifi_direct import AndroidWiFiDirect
from android_bluetooth import AndroidBluetooth

class MyNetworkManager:
    def __init__(self):
        self.wifi = AndroidWiFiDirect()
        self.bt = AndroidBluetooth()
```

**my_network_module.py (After - Works Everywhere):**
```python
from android_mocks import is_android, get_android_wifi_direct, get_android_bluetooth

class MyNetworkManager:
    def __init__(self):
        if is_android():
            from android_wifi_direct import AndroidWiFiDirect
            from android_bluetooth import AndroidBluetooth
            self.wifi = AndroidWiFiDirect()
            self.bt = AndroidBluetooth()
            print("[MyNetworkManager] Running on Android")
        else:
            self.wifi = get_android_wifi_direct()
            self.bt = get_android_bluetooth()
            print("[MyNetworkManager] Running on desktop (mocking Android APIs)")
```

Or even simpler (recommended):

```python
from android_mocks import get_android_wifi_direct, get_android_bluetooth

class MyNetworkManager:
    def __init__(self):
        self.wifi = get_android_wifi_direct()
        self.bt = get_android_bluetooth()
```

The mock getters automatically detect the platform and return real or mock instances.

---

## Testing the Integration

### Test on Desktop
```bash
python main.py
```

Look for these log messages:
```
[GhostEngine] Running on desktop with mocked WiFi Direct/Bluetooth
[MockWiFiDirect] Wi-Fi Direct mock: enabled
[MockWiFiDirect] Discovering peers (mock)
[MockBluetooth] Bluetooth mock: enabled
```

### Test on Android
```bash
buildozer android debug deploy run logcat
```

Should NOT see "[Mock..." messages—instead, real Android APIs execute.

---

## android_mocks.py Exported Functions

```python
is_android()
    Boolean: True if platform == 'android', False otherwise

get_android_wifi_direct()
    Returns: AndroidWiFiDirect (real on Android) or MockWiFiDirect (on desktop)

get_android_bluetooth()
    Returns: AndroidBluetooth (real on Android) or MockBluetooth (on desktop)

get_android_permissions()
    Returns: MockAndroidPermissions object with request_permissions() method

conditional_import(module_name, class_name, fallback_class=None)
    Advanced: Import module conditionally, with fallback
    Example: conditional_import('pyjnius', 'autoclass', SomeDefaultClass)
```

---

## Common Patterns

### Pattern 1: Simple Mock Usage
```python
from android_mocks import get_android_wifi_direct

wifi = get_android_wifi_direct()
wifi.enable()
peers = wifi.discover_peers()
```

### Pattern 2: Conditional Initialization
```python
from android_mocks import is_android, get_android_wifi_direct

if is_android():
    wifi = get_android_wifi_direct()
    wifi.enable()
else:
    print("Desktop mode - WiFi Direct disabled")
```

### Pattern 3: Custom Fallback
```python
from android_mocks import conditional_import

MyClass = conditional_import(
    'my_android_module',
    'MyAndroidClass',
    fallback_class=MyDesktopClass
)

instance = MyClass()
```

---

## Troubleshooting

**Q: App still crashes with ImportError on desktop**
A: Check if you're importing Android modules directly without using `android_mocks.py`. 
Solution: Wrap the import:
```python
from android_mocks import get_android_wifi_direct
wifi = get_android_wifi_direct()  # Works on desktop and Android
```

**Q: Mock methods don't do anything (wireless is always empty)**
A: This is expected! The mocks print debug logs but don't actually discover peers. 
Solution: Simulate peer data for testing, or test network discovery separately.

**Q: Is_android() returns False on my Android phone**
A: Rare. Check that Buildozer correctly built the APK. 
Solution: Add logging at startup:
```python
from android_mocks import is_android
print(f"[DEBUG] Platform detected as: {'Android' if is_android() else 'Desktop'}")
```

---

## Next Steps

1. **Verify current state** (5 min):
   ```bash
   python main.py
   ```
   Should start without crashes.

2. **Add android_mocks imports** (10 min):
   Update `network.py`, `main.py`, and any custom Android modules.

3. **Add debug logging** (5 min):
   Print what APIs are being called (real or mock).

4. **Test on desktop** (5 min):
   Verify mock log messages appear in terminal.

5. **Test on Android** (20 min):
   Build, deploy, check that real code runs:
   ```bash
   buildozer android debug deploy run logcat
   ```

---

## Reference: Full android_mocks.py API

See `android_mocks.py` in project root for complete source code with all mock class methods.

Key mock classes:
- `MockWiFiDirect`: enable(), discover_peers(), connect(), disconnect()
- `MockBluetooth`: enable(), scan_devices(), connect(), disconnect()
- `MockAndroidPermissions`: request_permissions(), check_permission()
