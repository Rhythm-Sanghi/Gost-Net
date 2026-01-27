# Ghost Net - Deployment Guide

Complete guide for building, signing, and deploying Ghost Net to production.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Build Process](#detailed-build-process)
4. [Website Deployment](#website-deployment)
5. [Distribution Channels](#distribution-channels)
6. [Post-Release](#post-release)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

**Operating System:**
- Linux (Ubuntu 20.04+ recommended)
- macOS 10.15+
- Windows 10/11 with WSL2

**Required Software:**
- Python 3.8+
- Java JDK 11+
- Android SDK (or let Buildozer download it)
- Git

### Installation

```bash
# Install Python dependencies
pip install buildozer cython pillow

# Install system dependencies (Ubuntu/Debian)
sudo apt update
sudo apt install -y git zip unzip openjdk-11-jdk \
    python3-pip autoconf libtool pkg-config zlib1g-dev \
    libncurses5-dev libncursesw5-dev libtinfo5 cmake \
    libffi-dev libssl-dev

# Install system dependencies (macOS)
brew install python@3.9 java11 git
brew install --cask android-sdk

# Verify installations
python3 --version
java -version
buildozer --version
```

### Environment Setup

```bash
# Set Android SDK environment (if not using Buildozer's download)
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools
```

---

## Quick Start

### 1. Generate Assets

```bash
# Generate icon and presplash
python create_assets.py
```

**Output:**
- `icon.png` (512x512)
- `presplash.png` (1080x1920)

### 2. Build and Sign APK

```bash
# Run the automated release manager
python release_manager.py
```

**This will:**
1. Check your environment
2. Generate keystore (first time only)
3. Build release APK with Buildozer
4. Sign the APK
5. Verify signature
6. Generate checksums
7. Output final APK to `dist/GhostNet_v1.0.0.apk`

**Expected Time:** 10-30 minutes (first run downloads dependencies)

### 3. Test the APK

```bash
# Install on connected Android device
adb install dist/GhostNet_v1.0.0.apk

# Or manually transfer the APK and install
```

---

## Detailed Build Process

### Step 1: Environment Check

```bash
python release_manager.py
```

The script checks for:
- ✓ Python 3
- ✓ Buildozer
- ✓ Java JDK
- ⚠ Android SDK (optional, Buildozer downloads if missing)

### Step 2: Keystore Generation

**First Time Only:**

The release manager will prompt you to create a keystore:

```
Enter keystore password (min 6 characters):
Password: ********
Confirm password: ********

Enter certificate information:
  Your name (CN): John Doe
  Organization unit (OU): Ghost Net
  Organization (O): Ghost Net Project
  City (L): New York
  State (ST): NY
  Country code (C, 2 letters): US
```

**Important:** 
- Backup `ghostnet.keystore` immediately!
- Store the password securely (use a password manager)
- You **cannot** update your app without this keystore

**Keystore Backup Locations:**
- Cloud storage (encrypted)
- External hard drive
- USB drive (offline)
- Password manager (1Password, Bitwarden)

### Step 3: Build Release APK

```bash
buildozer android release
```

**What happens:**
1. Buildozer downloads Android SDK/NDK (first time)
2. Compiles Python to native code
3. Packages app with dependencies
4. Creates unsigned APK in `.buildozer/android/.../outputs/apk/release/`

**Build Output:**
```
# Preparing build
# -> running python3 setup.py...
# -> compile platform
# -> Build the application #0
# -> running python-for-android create...

✓ APK built successfully
```

### Step 4: Sign the APK

The release manager automatically:

1. **Aligns** the APK with `zipalign` (if available)
2. **Signs** with `apksigner` or `jarsigner`
3. **Verifies** the signature

**Manual Signing (if needed):**

```bash
# Align
zipalign -v -p 4 app-release-unsigned.apk app-release-unsigned-aligned.apk

# Sign
apksigner sign --ks ghostnet.keystore \
    --ks-key-alias ghostnet \
    --out dist/GhostNet_v1.0.0.apk \
    app-release-unsigned-aligned.apk

# Verify
apksigner verify --verbose dist/GhostNet_v1.0.0.apk
```

### Step 5: Generate Checksums

```bash
# MD5
md5sum dist/GhostNet_v1.0.0.apk

# SHA256
sha256sum dist/GhostNet_v1.0.0.apk
```

**Output saved to:** `dist/GhostNet_v1.0.0.checksums.txt`

---

## Website Deployment

### Option 1: GitHub Pages (Recommended - Free)

**Step 1: Create GitHub Repository**

```bash
git init
git add .
git commit -m "Initial commit - Ghost Net v1.0.0"
git branch -M main
git remote add origin https://github.com/yourusername/ghostnet.git
git push -u origin main
```

**Step 2: Enable GitHub Pages**

1. Go to repository Settings → Pages
2. Source: Deploy from branch `main`
3. Folder: `/` (root) or `/web`
4. Click Save

**Step 3: Copy Website Files**

```bash
# If deploying from root
cp web/* .
git add index.html style.css script.js
git commit -m "Add landing page"
git push

# OR create gh-pages branch
git checkout --orphan gh-pages
cp web/* .
rm -rf web/
git add .
git commit -m "Deploy website"
git push origin gh-pages
```

**Step 4: Upload APK to GitHub Releases**

1. Go to Releases → Create new release
2. Tag: `v1.0.0`
3. Title: `Ghost Net v1.0.0 - Initial Release`
4. Upload `dist/GhostNet_v1.0.0.apk`
5. Copy checksums from `dist/GhostNet_v1.0.0.checksums.txt`
6. Publish release

**Step 5: Update Website Links**

In `web/index.html`, update the download link:

```html
<a href="https://github.com/yourusername/ghostnet/releases/download/v1.0.0/GhostNet_v1.0.0.apk" 
   class="btn btn-primary btn-large" download>
    <span class="btn-icon">⬇</span>
    DOWNLOAD APK
</a>
```

**Your site will be live at:** `https://yourusername.github.io/ghostnet/`

### Option 2: Netlify (Alternative - Free)

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
cd web
netlify deploy --prod

# Follow prompts
# Site name: ghostnet
# Deploy path: .
```

### Option 3: Self-Hosted

Requirements:
- Web server (Apache, Nginx)
- Domain name
- SSL certificate (Let's Encrypt)

```bash
# Copy files to web server
scp -r web/* user@yourserver.com:/var/www/html/ghostnet/
scp dist/GhostNet_v1.0.0.apk user@yourserver.com:/var/www/html/ghostnet/dist/
```

**Nginx Configuration:**

```nginx
server {
    listen 80;
    server_name ghostnet.example.com;
    root /var/www/html/ghostnet;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # Enable APK downloads
    location ~* \.apk$ {
        add_header Content-Type application/vnd.android.package-archive;
        add_header Content-Disposition attachment;
    }
}
```

---

## Distribution Channels

### 1. Direct Distribution (Current)

**Advantages:**
- ✓ No approval process
- ✓ No fees
- ✓ Full control
- ✓ Immediate updates

**Disadvantages:**
- ✗ Users must enable "Unknown Sources"
- ✗ No automatic updates
- ✗ Less discoverability

**Best for:** Privacy-focused users, testing, beta releases

### 2. F-Droid (Recommended for Open Source)

**Steps:**

1. **Prepare metadata:**
   - Create `metadata/org.ghostnet.txt`
   - Add app description, license, changelog

2. **Submit to F-Droid:**
   - Fork https://gitlab.com/fdroid/fdroiddata
   - Add metadata file
   - Create merge request

3. **Wait for review:**
   - F-Droid team reviews code
   - Builds app from source
   - Publishes to F-Droid store

**Timeline:** 2-4 weeks for first submission

**Resources:**
- https://f-droid.org/docs/Inclusion_Policy/
- https://f-droid.org/docs/All_About_Descriptions_Graphics_and_Screenshots/

### 3. Google Play Store (Optional)

**Requirements:**
- $25 one-time registration fee
- Privacy policy URL
- Content rating questionnaire
- Store listing assets (screenshots, graphics)

**Steps:**

1. **Create Developer Account:**
   - https://play.google.com/console/signup

2. **Prepare Store Listing:**
   - Short description (80 chars)
   - Full description (4000 chars max)
   - Screenshots (2-8 images)
   - Feature graphic (1024x500)
   - App icon (512x512)

3. **Upload APK:**
   - Production track
   - Internal testing first (recommended)
   - Gradual rollout

4. **Submit for Review:**
   - Review time: 1-7 days
   - Address any policy issues

**Challenges for Ghost Net:**
- P2P functionality may trigger security reviews
- "Dangerous permissions" (storage, network)
- Encryption export compliance

**Alternative:** Google Play Console → Internal Testing (no review)

### 4. Alternative App Stores

- **Amazon Appstore** (easier approval)
- **APKPure** (no approval needed)
- **Aptoide** (open marketplace)
- **GetJar** (independent store)

---

## Post-Release

### Monitoring

**Track Downloads:**
- GitHub Releases download count
- Website analytics (Google Analytics, Plausible)
- Server logs (if self-hosted)

**Track Issues:**
- GitHub Issues
- Email support
- Community forums (Reddit, Discord)

### User Support

**Create Support Channels:**

1. **GitHub Issues:**
   - Bug reports
   - Feature requests
   - Technical questions

2. **Documentation:**
   - FAQ section
   - Troubleshooting guide
   - Video tutorials

3. **Community:**
   - Reddit: r/GhostNetApp
   - Discord server
   - Twitter: @GhostNetApp

### Updates

**Version Naming:**
- Major: 1.0.0 → 2.0.0 (breaking changes)
- Minor: 1.0.0 → 1.1.0 (new features)
- Patch: 1.0.0 → 1.0.1 (bug fixes)

**Update Process:**

1. Update version in `buildozer.spec`:
   ```
   version = 1.0.1
   ```

2. Rebuild and re-sign:
   ```bash
   python release_manager.py
   ```

3. Upload to GitHub Releases

4. Update website:
   - Change version number
   - Update download link
   - Update checksums

5. Notify users:
   - GitHub release notes
   - Social media announcement
   - Email newsletter (if applicable)

---

## Troubleshooting

### Build Errors

**Error:** `buildozer: command not found`

**Solution:**
```bash
pip install --upgrade buildozer
```

---

**Error:** `Java version mismatch`

**Solution:**
```bash
# Set JAVA_HOME explicitly
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
```

---

**Error:** `SDK not found`

**Solution:**
```bash
# Let Buildozer download it
buildozer android clean
buildozer android debug  # First time downloads SDK
```

---

**Error:** `Insufficient disk space`

**Solution:**
```bash
# Clean Buildozer cache
buildozer android clean
rm -rf .buildozer/

# Free space on Linux
sudo apt-get clean
```

---

### Signing Errors

**Error:** `apksigner: command not found`

**Solution:**
```bash
# Install Android SDK Build Tools
sdkmanager "build-tools;33.0.0"

# Or use jarsigner (fallback)
jarsigner -verbose -sigalg SHA256withRSA \
    -digestalg SHA-256 -keystore ghostnet.keystore \
    app-release-unsigned.apk ghostnet
```

---

**Error:** `Keystore password incorrect`

**Solution:**
- Check password in password manager
- Re-create keystore (users must uninstall old app)
- Use key recovery if available

---

**Error:** `Key alias not found`

**Solution:**
```bash
# List keys in keystore
keytool -list -v -keystore ghostnet.keystore

# Use correct alias
```

---

### Runtime Errors

**Error:** App crashes on startup

**Solution:**
1. Check logs:
   ```bash
   adb logcat | grep python
   ```
2. Test on different Android versions
3. Verify all permissions granted
4. Check for missing dependencies

---

**Error:** "App not installed" or "Package appears corrupt"

**Solution:**
1. Uninstall old version first
2. Verify APK signature:
   ```bash
   apksigner verify --verbose app.apk
   ```
3. Re-download APK (may be corrupted)
4. Try zipalign again

---

**Error:** No peers found

**Solution:**
1. Both devices on same WiFi network
2. WiFi not in isolation mode (common on public WiFi)
3. Firewall not blocking ports 37020/37021
4. Try creating WiFi hotspot from one device

---

## Security Considerations

### Keystore Security

**DO:**
- ✓ Use strong password (16+ chars, mixed case, symbols)
- ✓ Backup to multiple secure locations
- ✓ Store offline copies
- ✓ Use hardware security module (HSM) for production
- ✓ Document keystore location and password storage

**DON'T:**
- ✗ Commit keystore to Git
- ✗ Share keystore password in plain text
- ✗ Store password in code
- ✗ Use same keystore for multiple apps
- ✗ Store keystore on cloud without encryption

### Code Signing

**Best Practices:**
- Sign all releases (never distribute unsigned APKs)
- Use consistent signing certificate
- Verify signature before distribution
- Publish checksums for verification
- Consider code signing certificate (for enterprise)

### Privacy Compliance

**GDPR/Privacy:**
- Ghost Net collects NO personal data
- No analytics, no tracking
- Document in privacy policy
- Users own their data (stored locally)

**Encryption Export:**
- AES-128 encryption used
- May require export license (USA)
- Check local regulations
- Document encryption use

---

## Checklist

### Pre-Release

- [ ] All tests passing
- [ ] Assets generated (icon, presplash)
- [ ] Version number updated
- [ ] Changelog written
- [ ] Documentation updated
- [ ] Keystore backed up

### Build

- [ ] Environment check passed
- [ ] APK built successfully
- [ ] APK signed and verified
- [ ] Checksums generated
- [ ] APK tested on real device(s)

### Website

- [ ] Landing page deployed
- [ ] Download link works
- [ ] Checksums displayed
- [ ] All links tested
- [ ] Mobile-responsive verified

### Distribution

- [ ] GitHub Release created
- [ ] APK uploaded
- [ ] Release notes published
- [ ] Social media announced
- [ ] Community notified

### Post-Release

- [ ] Monitor for issues
- [ ] Respond to user feedback
- [ ] Track downloads
- [ ] Plan next release

---

## Resources

### Official Links

- **GitHub:** https://github.com/yourusername/ghostnet
- **Website:** https://yourusername.github.io/ghostnet/
- **Issues:** https://github.com/yourusername/ghostnet/issues
- **Releases:** https://github.com/yourusername/ghostnet/releases

### Documentation

- **README.md** - User guide
- **ARCHITECTURE_REVIEW.md** - Technical architecture
- **FILE_TRANSFER_DOCS.md** - File transfer protocol
- **STORAGE_DOCS.md** - Encrypted storage
- **SETTINGS_DOCS.md** - Settings features
- **RELEASE_NOTES.md** - App store listing

### Tools

- **Buildozer:** https://buildozer.readthedocs.io/
- **python-for-android:** https://python-for-android.readthedocs.io/
- **KivyMD:** https://kivymd.readthedocs.io/

### Support

- **Buildozer Issues:** https://github.com/kivy/buildozer/issues
- **KivyMD Discord:** https://discord.gg/wu3qBST
- **Kivy Community:** https://kivy.org/community

---

## Maintenance Schedule

### Daily
- Monitor GitHub Issues
- Check for crash reports
- Respond to user questions

### Weekly
- Review pull requests
- Update dependencies
- Test on new Android versions

### Monthly
- Security audit
- Performance review
- Feature planning

### Quarterly
- Major version release
- Documentation update
- Community survey

---

## License & Legal

**Ghost Net** is released under the MIT License.

**Disclaimer:**
- Provided "as is" without warranty
- Users responsible for local compliance
- Not liable for misuse
- Check encryption export laws

**Attribution:**
- Built with Python, KivyMD, and Kivy
- Encryption via Python Cryptography library
- Icons and design by Ghost Net team

---

**Questions?** Open an issue on GitHub or email ghostnet@example.com

---

*Last Updated: 2026-01-27*  
*Version: 1.0.0*  
*Ghost Net Project*
