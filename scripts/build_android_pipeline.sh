#!/usr/bin/env bash
# Local end-to-end Android build pipeline for Ghost Net.
#
# 16 KB page-size compliance
# --------------------------
# NDK r28b is the single enforcement point. Its clang/LLD (19.0.0) links every
# object with 2**14 LOAD alignment by default, so no linker flag, no ELF
# post-processing and no python-for-android monkey-patching are required. The
# 4 KB alignment in previously shipped APKs came solely from the NDK r25b
# default (clang 14.0.6), whose `.comment` matches the failing artifact exactly.
#
# python-for-android is therefore used pristine; only in-repo local recipes
# under p4a_recipes/ are applied. scripts/check_android_16kb.py then gates the
# result and fails the build on any noncompliant library.
set -e

# Rust toolchain — must be on PATH before buildozer spawns p4a subprocesses
export CARGO_HOME="$HOME/.cargo"
export RUSTUP_HOME="$HOME/.rustup"
export PATH="$HOME/.cargo/bin:/home/test/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"

# Pin the SDK so p4a resolves NDK r28b and build-tools 35+ (zipalign -P 16).
export ANDROIDSDK="$HOME/.buildozer/android/platform/android-sdk"
export ANDROID_SDK_ROOT="$ANDROIDSDK"
export ANDROIDAPI=36
export ANDROIDMINAPI=21
export ANDROIDNDK="$HOME/.buildozer/android/platform/android-ndk-r28b"
export ANDROID_NDK_HOME="$ANDROIDNDK"
export ANDROID_NDK_ROOT="$ANDROIDNDK"

# Verify toolchain is available
rustup --version || { echo "ERROR: rustup not found on PATH"; exit 1; }
cargo --version  || { echo "ERROR: cargo not found on PATH";  exit 1; }

[ -d "$ANDROIDNDK" ] || {
  echo "ERROR: NDK r28b not found at $ANDROIDNDK"
  echo "       buildozer downloads it automatically on first run."
  exit 1
}

WORKSPACE="/mnt/c/Users/Test/Documents/Ghost net"
BUILD_DIR="/home/test/gostnet_build"

echo "=== Syncing Source Tree to $BUILD_DIR ==="
mkdir -p "$BUILD_DIR"

# Copy source tree excluding research, git, temporary files.
# --delete keeps stale local recipes from surviving a rename or removal.
rsync -a --delete \
  --exclude='.git' \
  --exclude='research' \
  --exclude='tests' \
  --exclude='scratch' \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.buildozer' \
  --exclude='bin' \
  --exclude='*.log' \
  "$WORKSPACE/" "$BUILD_DIR/"

cd "$BUILD_DIR"

echo "=== PROFILE: Modern Android (API 36 / NDK r28b / 16 KB Page Alignment) ==="
cp buildozer-sideload.spec buildozer.spec

echo "=== Starting Buildozer Debug Build for Modern Android ==="
buildozer -v android debug 2>&1 | tee build_sideload.log

echo "=== Ensuring _rust.abi3.so has libpython3.11.so in DT_NEEDED ==="
find .buildozer/ -name "_rust.abi3.so" -exec patchelf --add-needed libpython3.11.so {} + || true

echo "=== GATING: 16 KB Memory Page Size & ELF Alignment Audit ==="
# Gated before the artifact leaves this machine: a noncompliant APK is never
# copied into bin/ and can never be uploaded by CI.
python3 "$BUILD_DIR/scripts/check_android_16kb.py" bin/*.apk

echo "=== Copying Built APK to Workspace ==="
mkdir -p "$WORKSPACE/bin"
cp -v bin/*.apk "$WORKSPACE/bin/"
