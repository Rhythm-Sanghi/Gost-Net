#!/usr/bin/env bash
set -e

# Rust toolchain — must be on PATH before buildozer spawns p4a subprocesses
export CARGO_HOME="$HOME/.cargo"
export RUSTUP_HOME="$HOME/.rustup"
export PATH="$HOME/.cargo/bin:/home/test/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"

# Verify Rust is available
rustup --version || { echo "ERROR: rustup not found on PATH"; exit 1; }
cargo --version  || { echo "ERROR: cargo not found on PATH";  exit 1; }

WORKSPACE="/mnt/c/Users/Test/Documents/Ghost net"
BUILD_DIR="/home/test/gostnet_build"

echo "=== Syncing Source Tree to $BUILD_DIR ==="
mkdir -p "$BUILD_DIR"

# Copy source tree excluding research, git, temporary files
rsync -av \
  --exclude='.git' \
  --exclude='research' \
  --exclude='tests' \
  --exclude='scratch' \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.buildozer' \
  --exclude='bin' \
  "$WORKSPACE/" "$BUILD_DIR/"

cd "$BUILD_DIR"

echo "=== PROFILE: Track A (Sideload - API 33 / NDK 25b) ==="
cp buildozer-sideload.spec buildozer.spec

echo "=== Starting Buildozer Debug Build for Track A ==="
buildozer -v android debug 2>&1 | tee build_sideload.log

echo "=== Ensuring _rust.abi3.so has libpython3.11.so in DT_NEEDED ==="
find .buildozer/ -name "_rust.abi3.so" -exec patchelf --add-needed libpython3.11.so {} + || true

echo "=== Copying Built APK to Workspace ==="
mkdir -p "$WORKSPACE/bin"
cp -v bin/*.apk "$WORKSPACE/bin/"

