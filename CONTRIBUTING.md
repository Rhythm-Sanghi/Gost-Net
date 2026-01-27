# 🤝 Contributing to Ghost Net

Thank you for considering contributing to Ghost Net! This guide will help you get started.

## 📋 Table of Contents

- [Code of Conduct](#-code-of-conduct)
- [How Can I Contribute?](#-how-can-i-contribute)
- [Development Setup](#-development-setup)
- [Coding Standards](#-coding-standards)
- [Pull Request Process](#-pull-request-process)
- [Testing Guidelines](#-testing-guidelines)
- [Documentation](#-documentation)

---

## 🌟 Code of Conduct

Ghost Net is committed to providing a welcoming and inclusive environment. By participating, you agree to:

- **Be respectful** - Treat everyone with respect and empathy
- **Be constructive** - Provide helpful feedback and criticism
- **Be collaborative** - Work together toward common goals
- **Focus on privacy** - Align contributions with Ghost Net's privacy-first philosophy

---

## 🎯 How Can I Contribute?

### 1. Report Bugs 🐛

Found a bug? Please [open a bug report](../../issues/new?template=bug_report.md) with:
- Device model and Android version
- Clear steps to reproduce
- Expected vs actual behavior
- Relevant logs from `adb logcat`

### 2. Suggest Features 💡

Have an idea? [Submit a feature request](../../issues/new?template=feature_request.md) explaining:
- What problem it solves
- How it should work
- Privacy/security implications
- Specific use cases

### 3. Submit Code 🔧

Ready to code? Great! See [Development Setup](#-development-setup) below.

### 4. Improve Documentation 📖

Documentation improvements are always welcome:
- Fix typos or unclear explanations
- Add examples or use cases
- Translate to new languages (see [`LOCALIZATION_GUIDE.md`](LOCALIZATION_GUIDE.md))
- Create video tutorials

### 5. Help Others 💬

- Answer questions in issues
- Help troubleshoot problems
- Review pull requests
- Share your Ghost Net setup/workflow

---

## 🛠️ Development Setup

### Prerequisites

**Required:**
- Python 3.10 or higher
- Git
- Basic knowledge of Python and Kivy

**For Android builds:**
- Linux or macOS (or WSL on Windows)
- Java JDK 17
- Android SDK/NDK (installed automatically by Buildozer)

### Quick Start

1. **Fork the repository**

   Click the "Fork" button at the top right of the GitHub page.

2. **Clone your fork**

   ```bash
   git clone https://github.com/YOUR_USERNAME/Ghost_Net.git
   cd Ghost_Net
   ```

3. **Create a virtual environment**

   ```bash
   python -m venv venv
   
   # Linux/macOS
   source venv/bin/activate
   
   # Windows
   venv\Scripts\activate
   ```

4. **Install dependencies**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **Generate app assets**

   ```bash
   python create_assets.py
   ```

6. **Run the app (desktop)**

   ```bash
   python main.py
   ```

### Building for Android

**Install Buildozer:**
```bash
pip install buildozer
```

**Build debug APK:**
```bash
buildozer -v android debug
```

**Deploy to device:**
```bash
buildozer android deploy run
```

**Clean build (if issues):**
```bash
buildozer android clean
```

For detailed build instructions, see [`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## 📝 Coding Standards

### Python Style Guide

Ghost Net follows **PEP 8** guidelines:

```python
# Good: Clear, descriptive names
def send_encrypted_message(peer_id: str, content: str) -> bool:
    """Send an encrypted message to a peer.
    
    Args:
        peer_id: Unique identifier for the peer
        content: Message content to send
        
    Returns:
        True if message sent successfully, False otherwise
    """
    pass

# Bad: Unclear names, missing docstring
def send(p, c):
    pass
```

### Code Formatting

**Use consistent formatting:**
- 4 spaces for indentation (no tabs)
- Max line length: 100 characters
- Two blank lines between top-level functions/classes
- One blank line between methods

**Type hints are encouraged:**
```python
from typing import Dict, List, Optional

def get_peer_list(self) -> List[Dict[str, str]]:
    return self.peers
```

### Thread Safety

Ghost Net uses multithreading extensively. **Always use thread-safe patterns:**

```python
# Good: Schedule UI updates on main thread
from kivy.clock import Clock

def on_message_received(self, message: str):
    Clock.schedule_once(
        lambda dt: self.update_ui(message), 
        0
    )

# Bad: Direct UI update from network thread
def on_message_received(self, message: str):
    self.message_label.text = message  # ❌ Thread-unsafe!
```

### Security Best Practices

1. **Encryption**: Always encrypt sensitive data
2. **Validation**: Validate all user inputs
3. **Logging**: Never log passwords, keys, or message content
4. **Error handling**: Fail gracefully, don't expose internals

```python
# Good: Generic error message
except Exception as e:
    logger.error("Failed to send message")
    return False

# Bad: Exposes internal details
except Exception as e:
    logger.error(f"Encryption failed: {e}")  # ❌ Leaks key info
```

---

## 🔄 Pull Request Process

### 1. Create a Branch

```bash
# Create feature branch from main
git checkout -b feature/amazing-feature

# Or bugfix branch
git checkout -b fix/bug-description
```

**Branch naming:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation only
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Your Changes

- Write clear, descriptive commit messages
- Keep commits focused and atomic
- Test your changes thoroughly

```bash
# Good commit messages
git commit -m "Add Diffie-Hellman key exchange for per-peer encryption"
git commit -m "Fix peer timeout race condition in pruning thread"
git commit -m "Update Spanish translations for settings screen"

# Bad commit messages
git commit -m "fixed stuff"
git commit -m "WIP"
```

### 3. Test Your Changes

**Run the test suite:**
```bash
python test_network.py
```

**Manual testing:**
- Test on desktop
- Test on Android (if applicable)
- Test network edge cases (disconnection, reconnection)
- Verify no regressions

### 4. Update Documentation

- Update relevant `.md` files
- Add docstrings to new functions
- Update [`RELEASE_NOTES.md`](RELEASE_NOTES.md) if user-facing
- Add translation keys if UI changes (see [`LOCALIZATION_GUIDE.md`](LOCALIZATION_GUIDE.md))

### 5. Push and Create PR

```bash
git push origin feature/amazing-feature
```

Then open a Pull Request on GitHub with:
- **Clear title**: "Add Diffie-Hellman key exchange"
- **Description**: What, why, and how
- **Screenshots**: If UI changes
- **Testing**: What you tested
- **Related issues**: Closes #123

**PR Template:**
```markdown
## Description
Brief description of changes

## Motivation
Why is this change needed?

## Changes
- Added X feature
- Fixed Y bug
- Updated Z documentation

## Testing
- [ ] Tested on desktop (Python 3.10)
- [ ] Tested on Android (specify device/version)
- [ ] All tests pass (`python test_network.py`)
- [ ] No regressions

## Screenshots (if applicable)
[Add screenshots here]

## Checklist
- [ ] Code follows PEP 8 style guide
- [ ] Added/updated docstrings
- [ ] Updated relevant documentation
- [ ] No security vulnerabilities introduced
```

### 6. Code Review

- Be responsive to feedback
- Make requested changes promptly
- Keep discussions professional and constructive

### 7. Merge

Once approved, a maintainer will merge your PR. Thank you! 🎉

---

## 🧪 Testing Guidelines

### Automated Tests

**Run full test suite:**
```bash
python test_network.py
```

**Run specific tests:**
```bash
# Test with specific username
python test_network.py TestUser

# Non-interactive mode
python test_network.py TestUser --no-interactive
```

### Manual Testing Checklist

For features touching the network layer:
- [ ] Peer discovery works
- [ ] Messages send/receive correctly
- [ ] File transfers complete
- [ ] Encryption/decryption works
- [ ] Peer timeout/pruning functions
- [ ] Clean shutdown (no hanging threads)

For UI changes:
- [ ] UI renders correctly on different screen sizes
- [ ] No UI blocking/freezing
- [ ] Responsive to user input
- [ ] Material Design guidelines followed
- [ ] Dark theme looks good

For storage changes:
- [ ] Database migrations work
- [ ] Data persists correctly
- [ ] Cleanup/deletion works
- [ ] No SQL injection vulnerabilities

### Android Testing

```bash
# Install on device
adb install -r bin/ghostnet-*.apk

# Check logs
adb logcat | grep -i ghostnet

# Monitor network
adb shell netstat
```

---

## 📖 Documentation

### Code Documentation

**Always document:**
- Public functions and methods
- Complex algorithms
- Non-obvious behavior
- Security considerations

**Use Google-style docstrings:**
```python
def encrypt_message(self, plaintext: str) -> bytes:
    """Encrypt a message using Fernet symmetric encryption.
    
    Uses the current daily encryption key based on date-seed.
    Falls back to previous day's key if decryption fails (for
    messages sent near midnight).
    
    Args:
        plaintext: The unencrypted message string
        
    Returns:
        Encrypted message as bytes
        
    Raises:
        EncryptionError: If encryption fails
        
    Security:
        - Uses AES-128-CBC via Fernet
        - HMAC-SHA256 for authentication
        - Key rotation every 24 hours
    """
    pass
```

### Project Documentation

When adding features, update:
- [`README.md`](README.md) - User-facing features
- [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md) - Technical details
- Feature-specific docs (e.g., [`FILE_TRANSFER_DOCS.md`](FILE_TRANSFER_DOCS.md))
- [`RELEASE_NOTES.md`](RELEASE_NOTES.md) - Version history

### Translation

To add a new language:

1. Copy [`assets/locales/en.json`](assets/locales/en.json)
2. Rename to your language code (e.g., `fr.json`)
3. Translate all strings
4. Update [`localization.py`](localization.py) to include new language
5. See [`LOCALIZATION_GUIDE.md`](LOCALIZATION_GUIDE.md) for details

---

## 🏆 Recognition

Contributors are recognized in:
- GitHub contributors page
- [`README.md`](README.md) acknowledgments
- [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for significant features

---

## 📞 Getting Help

**Stuck? Need clarification?**

- 💬 Open a [discussion](../../discussions)
- 🐛 Check [existing issues](../../issues)
- 📖 Read the [documentation](README.md)
- 💡 Ask in your PR/issue

---

## 🎯 Priority Areas

We especially welcome contributions in:

### High Priority
- 🔐 Security audits and improvements
- 🐛 Bug fixes (especially Android-specific)
- 📱 iOS port (React Native/Kivy iOS)
- 🌍 Translations (new languages)
- 📖 Documentation improvements

### Medium Priority
- ✨ New features from roadmap (see [`README.md`](README.md))
- 🎨 UI/UX improvements
- ⚡ Performance optimizations
- 🧪 Test coverage expansion

### Future Ideas
- 📡 Bluetooth mesh networking
- 🖥️ Desktop apps (Windows/Mac/Linux)
- 🔊 Voice messages
- 👥 Group chat support
- 🎬 Video/audio calls (ambitious!)

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the **MIT License**.

---

## 🙏 Thank You!

Every contribution, no matter how small, makes Ghost Net better. Thank you for being part of the privacy-first movement! 👻

**Questions?** Open an issue or discussion. We're here to help! 🚀

---

**Built with ❤️ by the Ghost Net community**

*Ghost Net - Message freely, locally, securely*
