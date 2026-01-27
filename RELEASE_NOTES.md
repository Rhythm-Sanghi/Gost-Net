# Ghost Net v1.0.0 - Release Notes

## 🎉 Initial Production Release

**Ghost Net** is a privacy-focused, offline-first P2P messaging application for Android. Connect directly with nearby users without servers, internet, or registration.

---

## 📱 App Store Listing

### Short Description (80 characters)
Secure P2P messaging. No servers, no internet, no tracking. Truly private.

### Full Description

**Ghost Net - Secure Offline P2P Messaging**

Ghost Net enables direct peer-to-peer communication over local networks without requiring internet, servers, or accounts. Your messages stay on your device, encrypted and private.

**🔒 Privacy First**
• No servers - Direct P2P communication only
• End-to-end encryption with AES-128 + HMAC-SHA256
• Auto-delete messages after configurable time periods (1-168 hours)
• Panic Mode - Instantly delete all data with one tap
• No tracking, no analytics, no data collection

**📡 Offline Communication**
• Automatic peer discovery via UDP broadcast
• Works on any local WiFi network
• No internet connection required
• Ideal for privacy-conscious users, protests, disaster areas, or restricted networks

**💬 Feature-Rich Messaging**
• Real-time text messaging
• Binary file transfer (images, PDFs, videos, documents)
• Persistent chat history with encrypted storage
• Material Design UI with dark mode
• Dynamic username updates visible to peers instantly

**⚙️ Complete Control**
• Customizable message retention (1-168 hours)
• Dark mode with hot-reloading
• Configurable privacy settings
• No permissions abuse - only what's needed for P2P networking

**🛡️ Security Features**
• SQLite database with Fernet encryption at rest
• SHA256 checksum verification for file transfers
• Thread-safe operations throughout
• No cloud storage or backups

**📖 Open Source**
Ghost Net is built with Python and KivyMD, fully open source. Audit the code yourself at github.com/yourusername/ghostnet

---

## ✨ Key Features

### 🌐 P2P Networking
- **UDP Discovery**: Automatic peer detection on port 37020
- **TCP Messaging**: Reliable message and file transfer on port 37021
- **Local Network**: Works on any WiFi network without internet
- **Zero Configuration**: Just install and start chatting

### 💾 Encrypted Storage
- **Fernet Encryption**: AES-128-CBC + HMAC-SHA256 for message content
- **SQLite Database**: Persistent chat history and file records
- **Auto-Cleanup**: Configurable message retention (1-168 hours)
- **Secure Key Management**: Encryption keys stored locally

### 🎨 Modern UI
- **Material Design**: Clean, intuitive interface with KivyMD
- **Dark Mode**: Eye-friendly theme with instant hot-reloading
- **BootScreen**: Professional loading screen with startup status
- **Responsive**: Optimized for portrait orientation

### 🔧 Settings & Configuration
- **Identity Management**: Change username with instant peer updates
- **Privacy Controls**: Configure auto-cleanup and retention hours
- **Appearance**: Toggle dark mode with hot-reloading
- **Panic Mode**: Emergency data destruction with double confirmation

### 📂 File Transfer
- **Binary Transfer**: Send images, PDFs, videos, and any file type
- **Streaming**: Efficient 4KB chunk transfers
- **Verification**: SHA256 checksum validation
- **File Browser**: Built-in file picker with MDFileManager

---

## 🎯 Use Cases

### Privacy-Conscious Communication
Perfect for users who want messaging without corporate surveillance or data mining.

### Offline Events
Ideal for conferences, meetups, or areas with limited internet connectivity.

### Emergency Situations
Critical for disaster relief, protests, or regions with internet shutdowns.

### Corporate Security
Secure internal communication without cloud dependency.

### Educational Settings
Safe messaging for schools without external internet risks.

---

## 📊 Technical Specifications

### Platform
- **Operating System**: Android 5.0+ (API 21+)
- **Target API**: Android 13 (API 33)
- **Architecture**: arm64-v8a, armeabi-v7a

### Requirements
- WiFi connection (local network)
- 50MB storage space
- No internet required

### Permissions
- `INTERNET`: Local network communication
- `ACCESS_NETWORK_STATE`: Network status checks
- `ACCESS_WIFI_STATE`: WiFi state detection
- `CHANGE_WIFI_MULTICAST_STATE`: UDP broadcast support
- `READ/WRITE_EXTERNAL_STORAGE`: File transfers and storage
- `WAKE_LOCK`: Prevent connection drops during idle

### Technology Stack
- **Framework**: KivyMD 1.1.1 (Material Design for Python)
- **Backend**: Python 3.x with threading
- **Encryption**: Cryptography library (Fernet)
- **Database**: SQLite3 with encrypted BLOBs
- **Build**: Buildozer + python-for-android

---

## 🚀 Getting Started

### Installation
1. Download the APK from the releases page
2. Enable "Install from Unknown Sources" in Android settings
3. Install Ghost Net
4. Grant required permissions
5. Start chatting!

### First Use
1. **Boot Screen**: App initializes database and network engine
2. **Radar Screen**: Automatically discovers nearby peers
3. **Chat**: Tap any peer to start messaging
4. **Settings**: Customize your username and privacy settings

### File Transfer
1. Open chat with any peer
2. Tap the paperclip icon
3. Browse and select file
4. File transfers automatically with progress feedback

### Privacy Setup
1. Open Settings (⚙️ icon on Radar screen)
2. Set your desired message retention hours (1-168)
3. Enable/disable dark mode
4. Configure your username

---

## 🔐 Security & Privacy

### What We Do
✅ Encrypt all message content at rest with Fernet (AES-128 + HMAC-SHA256)  
✅ Use SHA256 checksums for file transfer verification  
✅ Auto-delete old messages based on retention settings  
✅ Store all data locally on your device  
✅ Provide Panic Mode for emergency data destruction  

### What We DON'T Do
❌ No internet servers - all communication is peer-to-peer  
❌ No cloud storage or backups  
❌ No tracking, analytics, or telemetry  
❌ No user accounts or registration  
❌ No data collection of any kind  

### Threat Model
Ghost Net is designed for **local network privacy**, not anonymity. Your IP address is visible to peers on the same network. For true anonymity, use Tor or similar tools.

---

## 📝 Changelog

### Version 1.0.0 (2026-01-27)

**Initial Release**
- ✨ P2P messaging with UDP discovery and TCP transfer
- 🔒 Encrypted SQLite storage with Fernet encryption
- 📂 Binary file transfer with SHA256 verification
- ⚙️ Complete settings screen with privacy controls
- 🎨 Material Design UI with dark mode
- 🚀 Professional boot screen with async startup
- 💀 Panic Mode for emergency data destruction
- 📱 Android 5.0+ support with multi-arch builds
- 📖 Comprehensive documentation suite

---

## 🐛 Known Issues

### Current Limitations
1. **Network Discovery**: Requires devices on same subnet
2. **File Size**: Large files (>1GB) may take time to transfer
3. **Background Mode**: Android may kill the app if running in background too long
4. **iOS Support**: Not currently available (Android-only)

### Workarounds
- For cross-subnet communication: Use a WiFi hotspot
- For large files: Keep screen on during transfer
- For background mode: Wakelock keeps connection active

---

## 🛠️ Troubleshooting

### No Peers Found
- Ensure both devices are on the same WiFi network
- Check that WiFi is not isolated (some public WiFi blocks P2P)
- Verify app has network permissions granted
- Try restarting the app on both devices

### Messages Not Sending
- Check if peer is still online (visible in Radar screen)
- Verify network connection is stable
- Check device storage is not full

### Files Not Receiving
- Ensure storage permissions are granted
- Check available storage space
- Verify file size is reasonable (<1GB recommended)

### App Crashes on Startup
- Check that all permissions were granted
- Try clearing app data and reinstalling
- Verify Android version is 5.0 or higher

---

## 📞 Support & Community

### Getting Help
- **Documentation**: Full docs available in the repository
- **GitHub Issues**: Report bugs and request features
- **Reddit**: Join r/GhostNetApp (hypothetical community)

### Contributing
Ghost Net is open source! Contributions are welcome:
- **Bug Reports**: Submit issues on GitHub
- **Feature Requests**: Open a discussion
- **Pull Requests**: Follow contribution guidelines
- **Translations**: Help localize the app

### Contact
- **GitHub**: github.com/yourusername/ghostnet
- **Email**: ghostnet@example.com (replace with real contact)
- **License**: MIT License (see LICENSE file)

---

## 🎁 Credits

**Developed by**: Ghost Net Team  
**Framework**: KivyMD and Kivy  
**Encryption**: Python Cryptography Library  
**Built with**: Python, Love, and Privacy in Mind

### Special Thanks
- Kivy & KivyMD communities for excellent frameworks
- Python Cryptography team for robust encryption
- Open source community for inspiration and support

---

## 📄 License

Ghost Net is released under the MIT License. See LICENSE file for details.

**TL;DR**: Free to use, modify, and distribute. No warranty. Use at your own risk.

---

## 🔮 Future Roadmap

### Planned Features (v1.1+)
- [ ] Group chat support
- [ ] Voice messages
- [ ] End-to-end encryption upgrade (Signal Protocol)
- [ ] QR code peer exchange
- [ ] Bluetooth fallback for no-WiFi scenarios
- [ ] iOS support via Kivy-iOS
- [ ] Message reactions and read receipts (optional)
- [ ] Custom themes and color schemes
- [ ] Export chat history to encrypted backup
- [ ] Multi-language support

### Under Consideration
- Video/audio calls (may compromise privacy/battery)
- Cloud sync option (opt-in, defeats offline-first purpose)
- Desktop client (Windows, Mac, Linux)

---

## ⚠️ Disclaimer

Ghost Net is provided "as is" without warranty. Users are responsible for compliance with local laws regarding encryption and peer-to-peer communication. The developers are not liable for misuse or legal consequences.

**Important**: Ghost Net provides privacy, not anonymity. Your IP address is visible to peers. For anonymous communication, use additional tools like Tor.

---

## 🌟 Why Ghost Net?

In an era of mass surveillance and data harvesting, Ghost Net offers a return to direct, private communication. No tech giants reading your messages. No governments with backdoor access. No corporations selling your data.

**Just you, your device, and the people you choose to connect with.**

Welcome to Ghost Net. The network that respects your privacy.

---

*Last Updated: 2026-01-27*  
*Version: 1.0.0*  
*Build: Production*
