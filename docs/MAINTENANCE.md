# Gost-Net Maintenance & Release Qualification Guide

**Audience:** Core Maintainers & Release Engineers  
**Target:** Gost-Net v1.0.0+  

---

## 1. How to Report Bugs

When submitting a bug report or regression finding:
1. **Environment:** Specify Host OS (Windows, Linux, macOS, or Android version), Python version, and Kivy / KivyMD versions.
2. **Network Topology:** State whether the issue occurred over Local Wi-Fi, Ethernet, Mobile Hotspot, or Simulated Loopback.
3. **Reproduction Steps:** Provide the exact sequence of actions starting from application launch.
4. **Sanitized Diagnostics:** Attach the export from **Settings → Diagnostics → Export Diagnostics**. (Diagnostic exports automatically scrub private keys, PINs, and message plaintext).

---

## 2. Reproducing Network & Transport Failures

To isolate networking failures from UI rendering:

### Headless Loopback Test Harness
Execute the two-process desktop test harness:
```powershell
python -m pytest tests/test_phase3_real_desktop_processes.py -v
```
This tests:
- Independent process binding on dynamic TCP ports.
- UDP discovery beacon exchange over loopback (`127.0.0.1`).
- Bidirectional TCP socket transmission and application-layer ACKs.
- Chunked file transfer and SHA-256 validation.

### Simulating Packet Loss & Delay
Use the built-in chaos fuzzer in test fixtures:
```python
from chaos_fuzzer import ProtocolChaosFuzzer
fuzzer = ProtocolChaosFuzzer(drop_rate=0.20, corruption_rate=0.05)
```

---

## 3. Running the Test Suite

### Full Automated Suite
```powershell
# Run all 256 unit and integration tests
python -m pytest tests/ --tb=short -q
```

### Targeted Core Subsystem Tests
```powershell
# Security, PIN authentication, and key derivation
python -m pytest tests/test_ghostnet.py -k "auth or security or encryption" -v

# Real desktop multi-process integration tests
python -m pytest tests/test_phase3_real_desktop_processes.py -v

# Source code syntax and bytecode compilation check
python -m compileall -q src/ main.py service.py
```

---

## 4. Building the Android APK

### Prerequisites
- Linux host or Docker container (Ubuntu 22.04 recommended).
- OpenJDK 17.
- Python 3.11.
- Android SDK (API 33) & NDK (r25b).

### Build Command
```bash
# Debug APK
buildozer android debug

# Release APK (requires keystore environment variables)
buildozer android release
```

### Continuous Integration (CI)
GitHub Actions workflow `.github/workflows/build.yml` automatically:
1. Runs the full test suite in a headless Xvfb container.
2. Executes Python bytecode compilation checks.
3. Compiles the Android APK via Buildozer upon successful test completion.

---

## 5. Release Qualification Gate Checklist

Before tagging a new release:

- [ ] `python -m compileall -q src/ main.py service.py` exits with code 0.
- [ ] `pytest tests/` passes with 100% green tests.
- [ ] `test_phase3_real_desktop_processes.py` passes 10/10 tests.
- [ ] Standalone encryption-at-rest verification passes (`scratch/verify_p26_p27_p57.py`).
- [ ] Default PINs (`1234` / `9999`) verified absent from production credential stores.
- [ ] Clean install first-run setup creates new keys without default PIN fallback.
- [ ] Android APK built and verified signed.
- [ ] Physical device qualification results recorded truthfully.
- [ ] `git status` clean with zero uncommitted artifacts.
