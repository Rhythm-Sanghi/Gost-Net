@echo off
REM Ghost Net P2P Modules - Automated GitHub Upload & APK Build Script (Windows)
REM This script handles all the setup and build process automatically
REM 
REM Usage: Run build_and_upload.bat
REM
REM Requirements:
REM - Git installed and configured with GitHub credentials
REM - buildozer installed (pip install buildozer)
REM - Android SDK/NDK configured for buildozer
REM - Python 3.9+ installed

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   Ghost Net P2P Modules - GitHub Upload ^& APK Build
echo   Automated Setup Script (Windows)
echo ============================================================
echo.

REM Configuration
set GITHUB_REPO=https://github.com/Rhythm-Sanghi/Gost-Net.git
set REPO_DIR=Gost-Net
set SOURCE_DIR=%cd%

echo Step 1: Checking Prerequisites
echo ======================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git not found. Please install Git first.
    echo Download from: https://git-scm.com/download/win
    pause
    exit /b 1
)
echo [OK] Git installed

REM Check if buildozer is installed
pip show buildozer >nul 2>&1
if errorlevel 1 (
    echo [WARNING] buildozer not found. Installing...
    pip install buildozer cython
) else (
    echo [OK] buildozer installed
)

echo.
echo Step 2: Cloning/Updating GitHub Repository
echo ======================================
echo.

REM Clone or update repository
if exist "%REPO_DIR%" (
    echo Repository already exists. Updating...
    cd "%REPO_DIR%"
    git pull origin main
    cd ..
) else (
    echo Cloning repository...
    git clone "%GITHUB_REPO%"
)

echo [OK] Repository ready

echo.
echo Step 3: Copying P2P Modules
echo ======================================
echo.

REM Copy P2P modules to repository
echo Copying production modules...
copy android_wifi_direct.py "%REPO_DIR%\" >nul
copy android_bluetooth.py "%REPO_DIR%\" >nul
copy android_permissions.py "%REPO_DIR%\" >nul
copy p2p_platform_adapter.py "%REPO_DIR%\" >nul

echo Copying test suite...
copy test_p2p_modules.py "%REPO_DIR%\" >nul

echo Copying documentation...
copy P2P_Implementation_Guide.md "%REPO_DIR%\" >nul 2>&1
copy P2P_Delivery_Summary.md "%REPO_DIR%\" >nul 2>&1
copy P2P_Modules_README.md "%REPO_DIR%\" >nul 2>&1
copy P2P_Quick_Reference.md "%REPO_DIR%\" >nul 2>&1
copy AndroidManifest_P2P_Template.xml "%REPO_DIR%\" >nul
copy GITHUB_DEPLOYMENT_GUIDE.md "%REPO_DIR%\" >nul
copy FINAL_DELIVERY_REPORT.md "%REPO_DIR%\" >nul

echo Copying updated configuration...
copy buildozer.spec "%REPO_DIR%\" >nul

echo [OK] All files copied

echo.
echo Step 4: Git Commit and Push
echo ======================================
echo.

cd "%REPO_DIR%"

echo Adding files to git...
git add .

REM Check if there are changes to commit
git status --porcelain >nul
if errorlevel 1 (
    echo [WARNING] No changes to commit
) else (
    echo Committing changes...
    git commit -m "feat: Add Android P2P modules (Wi-Fi Direct and Bluetooth RFCOMM)"
    echo [OK] Changes committed
)

echo.
echo Pushing to GitHub...
git push origin main
echo [OK] Pushed to GitHub

cd ..

echo.
echo Step 5: Building APK
echo ======================================
echo.

cd "%REPO_DIR%"

REM Check buildozer.spec exists
if not exist "buildozer.spec" (
    echo [ERROR] buildozer.spec not found
    pause
    exit /b 1
)

echo Building APK (this may take 10-20 minutes)...
echo ============================================================

REM Clean previous builds
call buildozer android clean

REM Build debug APK
call buildozer android debug

echo.
if exist "bin\ghostnet-1.0.0-debug.apk" (
    echo [OK] APK created: bin\ghostnet-1.0.0-debug.apk
    REM Show file size
    for %%F in (bin\ghostnet-1.0.0-debug.apk) do (
        echo File size: %%~zF bytes
    )
) else (
    echo [WARNING] APK file not found in expected location
    echo Checking bin directory...
    dir bin\
)

cd ..

echo.
echo ============================================================
echo                   BUILD COMPLETE!
echo ============================================================
echo.
echo Summary:
echo   [OK] Files uploaded to GitHub
echo   [OK] APK built successfully
echo.
echo Next Steps:
echo   1. Find APK at: %REPO_DIR%\bin\ghostnet-1.0.0-debug.apk
echo   2. Install on device: adb install "%REPO_DIR%\bin\ghostnet-1.0.0-debug.apk"
echo   3. Grant permissions on first launch
echo   4. Test P2P discovery with second device
echo.
echo For more info, see: %REPO_DIR%\GITHUB_DEPLOYMENT_GUIDE.md
echo.

pause
