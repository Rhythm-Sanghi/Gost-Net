#!/usr/bin/env bash
set -e
export PATH="/home/test/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "=== WSL2 Ubuntu Environment Check ==="
echo "Python:" $(python3 --version)
echo "Buildozer:" $(buildozer version)
echo "Cython:" $(cython --version)
echo "Java:" $(javac -version 2>&1)
echo "Git:" $(git --version)

echo ""
echo "=== Android SDK on Host ==="
ls -la /mnt/c/Users/Test/AppData/Local/Android/Sdk/platforms || true
echo "=== Android NDK on Host ==="
ls -la /mnt/c/Users/Test/AppData/Local/Android/Sdk/ndk || true
