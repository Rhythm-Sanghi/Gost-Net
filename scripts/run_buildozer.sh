#!/usr/bin/env bash
set -e
export PATH="/home/test/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export ANDROIDSDK="/mnt/c/Users/Test/AppData/Local/Android/Sdk"
export ANDROIDNDK="/mnt/c/Users/Test/AppData/Local/Android/Sdk/ndk/27.0.12077973"

echo "=== Toolchain Details ==="
echo "Buildozer: $(buildozer version)"
echo "p4a: $(p4a --version 2>&1 | tail -n 1)"
echo "Java: $(javac -version 2>&1)"
echo "Python Host: $(python3 --version)"
echo "SDK: $ANDROIDSDK"
echo "NDK: $ANDROIDNDK"

cd "/mnt/c/Users/Test/Documents/Ghost net"

# Test buildozer spec check with sideload profile
cp buildozer-sideload.spec buildozer.spec
echo "=== Running Buildozer Android Check / Dry-run ==="
buildozer android help || true
