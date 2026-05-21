# 🧪 Ghost Net APK Testing Guide

## Overview
This guide helps you build, test, and validate the fixed Ghost Net Android APK on your mobile device.

## Prerequisites
- **Android Device** with USB Debugging enabled (Android 6.0+)
- **USB Cable** to connect device to computer
- **ADB (Android Debug Bridge)** installed
- **Buildozer** installed (`pip install buildozer`)
- **Python 3.10+** and all dependencies from `requirements.txt`

---

## 📱 STEP 1: Enable USB Debugging on Your Device

### Android 6.0-10:
1. Go to **Settings** → **About Phone**
2. Tap **Build Number** 7 times (until "Developer mode enabled")
3. Go to **Settings** → **Developer Options**
4. Enable **USB Debugging**
5. When prompted, allow USB debugging from this computer

### Android 11+:
1. Go to **Settings** → **System** → **About Phone**
2. Tap **Build Number** 7 times
3. Go to **Settings** → **System** → **Developer Options**
4. Enable **USB Debugging**
5. Allow the connection on your device

---

## 🔨 STEP 2: Build the APK

Run the automated build and debug helper:

```bash
python build_and_debug.py
```

This will:
1. Run crash diagnostics
2. Clean previous builds
3. Verify buildozer configuration
4. Build the debug APK (takes 10-30 minutes)
5. Output APK location in `./bin/`

### Alternative: Manual Build

```bash
buildozer -v android debug
```

Output: `bin/ghostnet-*-debug.apk`

---

## 📲 STEP 3: Install APK on Device

### Connect device via USB and run:

```bash
adb devices
```

You should see your device listed. Then install:

```bash
adb install bin/ghostnet-*-debug.apk
```

Or if updating:

```bash
adb install -r bin/ghostnet-*-debug.apk
```

---

## ✅ STEP 4: Test the App

### Launch the app:

```bash
adb shell am start -n org.ghostnet.ghostnet/org.kivy.android.PythonActivity
```

### Monitor real-time logs:

```bash
adb logcat | grep -i "python\|ghost\|kivy"
```

---

## 🔍 STEP 5: Validate Fixes

### Expected Behavior:

✅ **Boot Screen Should Appear**
- App loads with "👻 Ghost Net" splash screen
- Shows "Initializing..." status with spinner
- No immediate crashes

✅ **Main Screen Should Load**
- After 3-5 seconds, transitions to Radar screen
- Shows "Scanning for peers..."
- Settings button visible in top-right

✅ **No Import Errors in Logs**
- Should NOT see: "ImportError", "ModuleNotFoundError", "libtinfo5"
- Should see: "[GhostNet] App started as..."

---

## 🐛 STEP 6: Check Logs for Specific Markers

### Successful startup logs should contain:

```
[GhostNet] Starting as 'SilentWolf42' on 192.168.x.x
[GhostEngine] Persistent storage enabled
[GhostEngine] UDP socket bound to port 37020
[GhostEngine] TCP server listening on port 37021
[GhostEngine] All threads started successfully
[GhostNet] App started as 'SilentWolf42'
```

### Check for crash indicators:

```bash
adb logcat | grep -i "crash\|exception\|fatal"
```

If you see crashes, that's important debugging info!

---

## 📊 STEP 7: Functionality Testing

### Test 1: Network Discovery
1. Launch app on two devices on same WiFi network
2. Check if peers appear in the Radar screen
3. Expected: Both devices should see each other

### Test 2: Navigation
1. Tap on a discovered peer
2. Should navigate to Chat screen
3. Should show previous chat history (if any)

### Test 3: Settings
1. Tap settings icon (⚙️) in top-right
2. Should show: Identity, Privacy, Appearance, About, Danger Zone
3. Try updating username and verify it's saved

### Test 4: Message Sending
1. Select a peer
2. Type a message
3. Tap Send
4. Message should appear in chat as "Sent" (blue bubble, right side)

---

## 🚨 TROUBLESHOOTING

### Issue: "Unable to locate package libtinfo5"
**Status**: ✅ FIXED in GitHub Actions
- Local builds use your system's libtinfo6
- This error only affected CI/CD builds

### Issue: App crashes immediately
**Check logs for**:
- KivyMD import errors → Update buildozer.spec to `kivymd==1.1.1`
- Permission errors → Check Android version (API 33+ needs special handling)
- Network errors → Check logcat for socket binding failures

### Issue: No peers discovered
**Possible causes**:
1. Both devices not on same WiFi network
2. Firewall blocking ports 37020-37021
3. Network permissions not granted
4. Try restarting both apps

### Issue: App runs but can't send messages
**Check**:
1. Both devices have internet connectivity
2. They're on the same local network
3. TCP port 37021 is accessible
4. Check logs for network errors

---

## 📋 Testing Checklist

Use this checklist to validate the APK:

- [ ] APK builds successfully without errors
- [ ] App installs on device without errors
- [ ] App launches and shows Ghost Net splash screen
- [ ] No crashes appear in first 5 seconds
- [ ] Transitions to Radar screen after boot
- [ ] Settings button is accessible
- [ ] Username can be viewed/updated
- [ ] App doesn't show import/module errors in logcat
- [ ] Network engine starts without socket errors
- [ ] Can discover peers on same WiFi (if two devices)
- [ ] Can navigate to chat screen
- [ ] Can send messages (if peer available)

---

## 📝 Logging Commands Reference

```bash
# View all logs
adb logcat

# Filter for app-specific logs
adb logcat | grep "ghost\|kivy\|python"

# View logs with timestamp
adb logcat -v time

# Clear logs before test
adb logcat -c

# View logs in real-time and save to file
adb logcat > app_logs.txt

# View crash/exception logs only
adb logcat | grep -i "crash\|exception\|fatal\|error"

# View network-related logs
adb logcat | grep -i "socket\|network\|port\|bind"

# View permission-related logs
adb logcat | grep -i "permission\|android\.permissions"
```

---

## 🎯 Success Criteria

Your APK is working correctly if:

✅ App opens without crashing
✅ No import/module errors in logs
✅ Boots to Radar screen within 5 seconds
✅ Settings are accessible
✅ No socket binding errors for network engine
✅ Can discover peers on same network (if available)

---

## 📞 Getting Help

If the APK still crashes:
1. Run `python crash_diagnostics.py` on your computer
2. Check `crash_diagnostics.log` for specific issues
3. Share the logcat output from `adb logcat > logs.txt`
4. Include the error messages in crash reports

---

## 🔄 Next Steps

After successful testing:
1. ✅ Report results of this APK test
2. Share logcat output if any issues found
3. Test file transfer functionality if desired
4. Test on multiple Android versions if available
5. Report any additional bugs found

Good luck! 👻