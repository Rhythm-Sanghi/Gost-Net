

#!/bin/bash



set -e

ANDROID_NDK_VERSION="r25b"
ANDROID_NDK_URL="https://dl.google.com/android/repository/android-ndk-${ANDROID_NDK_VERSION}-linux.zip"
BUILDOZER_DIR="$HOME/.buildozer"
ANDROID_NDK_DIR="$BUILDOZER_DIR/android/platform/android-ndk-${ANDROID_NDK_VERSION}"
VENV_DIR="$HOME/ghost_venv"
ANDROID_SDK_ROOT="$BUILDOZER_DIR/android/sdk"

echo "=========================================="
echo "Ghost Net Local Build Environment Setup"
echo "=========================================="
echo ""

echo "[1/7] Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

echo "[2/7] Installing required system dependencies..."
sudo apt-get install -y \
    git \
    zip \
    unzip \
    openjdk-17-jdk \
    python3-pip \
    python3-venv \
    autoconf \
    libtool \
    pkg-config \
    zlib1g-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libtinfo6 \
    cmake \
    libffi-dev \
    libssl-dev \
    automake \
    build-essential

echo ""
echo "[3/7] Creating and activating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip setuptools wheel

echo "[4/7] Installing Python build dependencies..."
pip install buildozer
pip install Cython==0.29.33
pip install kivy==2.3.0

echo ""
echo "[5/7] Creating Android SDK/NDK directory structure..."
mkdir -p "$ANDROID_NDK_DIR"
mkdir -p "$ANDROID_SDK_ROOT"

if [ ! -d "$ANDROID_NDK_DIR/toolchains" ]; then
    echo "Downloading Android NDK r25b..."
    NDK_TEMP="/tmp/android-ndk-${ANDROID_NDK_VERSION}-linux.zip"
    
    curl -L -o "$NDK_TEMP" "$ANDROID_NDK_URL"
    
    echo "Extracting NDK to temporary location..."
    unzip -q "$NDK_TEMP" -d /tmp/
    
    echo "Moving NDK to final location..."
    mv /tmp/android-ndk-${ANDROID_NDK_VERSION}/* "$ANDROID_NDK_DIR/"
    
    rm "$NDK_TEMP"
    echo "NDK installation complete"
else
    echo "NDK r25b already installed at $ANDROID_NDK_DIR"
fi

echo ""
echo "[6/7] Configuring environment variables..."

BASHRC="$HOME/.bashrc"

if ! grep -q "ANDROID_NDK_HOME" "$BASHRC"; then
    echo "" >> "$BASHRC"
    echo "export ANDROID_NDK_HOME=\"$ANDROID_NDK_DIR\"" >> "$BASHRC"
    echo "export ANDROID_SDK_ROOT=\"$ANDROID_SDK_ROOT\"" >> "$BASHRC"
    echo "export PATH=\"\$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin:\$PATH\"" >> "$BASHRC"
    echo "Environment variables added to $BASHRC"
else
    echo "Environment variables already configured in $BASHRC"
fi

source "$BASHRC"

echo ""
echo "[7/7] Verification..."
echo ""
echo "Checking Java installation..."
javac -version

echo ""
echo "Checking Python installation..."
python3 --version

echo ""
echo "Checking Buildozer installation..."
buildozer --version

echo ""
echo "Checking environment variables..."
echo "ANDROID_NDK_HOME: $ANDROID_NDK_HOME"
echo "ANDROID_SDK_ROOT: $ANDROID_SDK_ROOT"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "ADB Bridge Configuration for WSL2 to Windows:"
echo ""
echo "1. Locate your Windows adb.exe (typically in: C:\\Users\\<YourUsername>\\AppData\\Local\\Android\\Sdk\\platform-tools\\)"
echo ""
echo "2. Add Windows adb path to WSL2 .bashrc:"
echo "   Add this line to $BASHRC:"
echo "   export PATH=\"/mnt/c/Users/<YourUsername>/AppData/Local/Android/Sdk/platform-tools:\$PATH\""
echo ""
echo "3. Verify ADB is accessible from WSL2:"
echo "   adb devices"
echo ""
echo "4. Ensure your Android device is connected via USB with USB debugging enabled"
echo ""
echo "5. Build and deploy directly from WSL2:"
echo "   cd <project-directory>"
echo "   source $VENV_DIR/bin/activate"
echo "   buildozer android debug deploy run"
echo ""
echo "6. To view real-time logs:"
echo "   adb logcat"
echo ""
echo "Virtual environment location: $VENV_DIR"
echo "NDK location: $ANDROID_NDK_DIR"
echo "SDK location: $ANDROID_SDK_ROOT"
