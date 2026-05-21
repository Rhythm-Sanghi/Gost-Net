# Ghost Net - Localization Integration Guide

Complete guide for integrating multi-language support into Ghost Net v1.0.0.

---

## 📋 Overview

Ghost Net now supports 4 languages:
- **English (en)** - Default
- **Español (es)** - Spanish
- **हिन्दी (hi)** - Hindi  
- **中文 (zh)** - Chinese Simplified

---

## 🎯 What's Been Created

### 1. Localization System

**[`localization.py`](localization.py:1)** - Complete translation management:
- `LocalizationManager` class with JSON-based translations
- Automatic fallback to English for missing keys
- Hot-reload capability for development
- Translation coverage reporting
- Format string support (e.g., `tr("message", count=5)`)

**Helper Functions:**
```python
from localization import tr, set_language, get_current_language, get_supported_languages

# Translate a string
text = tr("radar_screen.title")  # Returns: "👻 Ghost Net"

# Change language
set_language("es")  # Switch to Spanish

# Get current language
lang = get_current_language()  # Returns: "es"

# Get all supported languages
langs = get_supported_languages()  # Returns: {'en': 'English', 'es': 'Español', ...}
```

### 2. Translation Files

**Location:** [`assets/locales/`](assets/locales/)

- **[`en.json`](assets/locales/en.json:1)** - English (Master) - 100+ keys
- **[`es.json`](assets/locales/es.json:1)** - Spanish - 100% coverage
- **[`hi.json`](assets/locales/hi.json:1)** - Hindi - 100% coverage
- **[`zh.json`](assets/locales/zh.json:1)** - Chinese - 100% coverage

**Structure:**
```json
{
  "boot_screen": {
    "title": "👻 Ghost Net",
    "status_ready": "Ready!"
  },
  "radar_screen": {
    "status_scanning": "Scanning for peers..."
  },
  "common": {
    "ok": "OK",
    "cancel": "Cancel"
  }
}
```

**Accessing nested keys:**
```python
# Use dot notation
title = tr("boot_screen.title")  # "👻 Ghost Net"
status = tr("radar_screen.status_scanning")  # "Scanning for peers..."
```

---

## 🔧 Integration Steps

### Step 1: Add Language Support to config.py

Add these methods to the `ConfigManager` class:

```python
def get_language(self) -> str:
    """Get the user's preferred language."""
    return self.config.get('language', 'en')

def set_language(self, language: str):
    """Set the user's preferred language."""
    if language in ['en', 'es', 'hi', 'zh']:
        self.config['language'] = language
        self.save_config()
        self._notify_change('language', self.get_language(), language)
    else:
        print(f"[Config] Unsupported language: {language}")
```

### Step 2: Initialize Localization in main.py

**Add import at the top:**
```python
from localization import tr, set_language, get_current_language, get_supported_languages
```

**In `GhostNetApp.build()` or `on_start()`:**
```python
def on_start(self):
    """Called when the app starts."""
    # ... existing code ...
    
    # Load user's language preference
    preferred_lang = self.config.get_language()
    set_language(preferred_lang)
    print(f"[GhostNet] Language set to: {get_current_language()}")
```

### Step 3: Refactor UI Strings

**Before (Hardcoded):**
```python
MDLabel(text="Scanning for peers...")
MDButton(MDButtonText(text="Send"))
self.status_label.text = "No peers found. Waiting..."
```

**After (Localized):**
```python
MDLabel(text=tr("radar_screen.status_scanning"))
MDButton(MDButtonText(text=tr("chat_screen.btn_send")))
self.status_label.text = tr("radar_screen.status_no_peers")
```

**With format parameters:**
```python
# Before
self.status_label.text = f"Found {len(peers_dict)} peer(s)"

# After
self.status_label.text = tr("radar_screen.status_found_peers", count=len(peers_dict))
```

---

## 📝 Main.py Refactoring Checklist

### BootScreen (Lines 37-123)

```python
class BootScreen(MDScreen):
    def __init__(self, **kwargs):
        # Line 60: App name
        app_name = MDLabel(
            text=tr("boot_screen.title"),  # Was: "👻 Ghost Net"
            # ...
        )
        
        # Line 68: Tagline
        tagline = MDLabel(
            text=tr("boot_screen.tagline"),  # Was: "Secure • Offline • Free"
            # ...
        )
        
        # Line 90: Status label
        self.status_label = MDLabel(
            text=tr("boot_screen.status_initializing"),  # Was: "Initializing..."
            # ...
        )
        
        # Line 107: Version
        version_label = MDLabel(
            text=tr("boot_screen.version_label"),  # Was: "v1.0.0"
            # ...
        )
```

### RadarScreen (Lines 170-307)

```python
class RadarScreen(MDScreen):
    def __init__(self, **kwargs):
        # Line 187: Title
        title = MDLabel(
            text=tr("radar_screen.title"),  # Was: "👻 Ghost Net"
            # ...
        )
        
        # Line 211: Status label
        self.status_label = MDLabel(
            text=tr("radar_screen.status_scanning"),  # Was: "Scanning for peers..."
            # ...
        )
        
        # Line 222: Section title
        peers_label = MDLabel(
            text=tr("radar_screen.section_peers"),  # Was: "Discovered Peers"
            # ...
        )
    
    def update_peers(self, peers_dict):
        # Line 244: No peers message
        self.status_label.text = tr("radar_screen.status_no_peers")
        # Was: "No peers found. Waiting..."
        
        # Line 248: Peers found message
        self.status_label.text = tr("radar_screen.status_found_peers", count=len(peers_dict))
        # Was: f"Found {len(peers_dict)} peer(s)"
        
        # Line 287: Chat button
        chat_btn.add_widget(MDButtonText(text=tr("radar_screen.btn_chat")))
        # Was: "Chat"
```

### ChatScreen (Lines 482-729)

```python
class ChatScreen(MDScreen):
    def __init__(self, **kwargs):
        # Line 509: Default title
        self.peer_label = MDLabel(
            text=tr("chat_screen.title_default"),  # Was: "Select a peer"
            # ...
        )
        
        # Line 550: Message hint
        self.message_input.add_widget(MDTextFieldHintText(
            text=tr("chat_screen.hint_message")  # Was: "Type a message..."
        ))
        
        # Line 556: Send button
        send_btn.add_widget(MDButtonText(text=tr("chat_screen.btn_send")))
        # Was: "Send"
    
    def set_peer(self, peer_ip, peer_name):
        # Line 570: Chat title with peer name
        self.peer_label.text = tr("chat_screen.title_prefix") + peer_name
        # Was: f"💬 {peer_name}"
```

### SettingsScreen (Lines 734-1222)

```python
class SettingsScreen(MDScreen):
    def __init__(self, **kwargs):
        # Line 767: Title
        title = MDLabel(
            text=tr("settings_screen.title"),  # Was: "⚙️ Settings"
            # ...
        )
        
        # Line 786: Identity section
        identity_card = self._create_section_card(
            tr("settings_screen.section_identity"),  # Was: "🪪 Identity"
            tr("settings_screen.identity_subtitle")   # Was: "Manage your display name"
        )
        
        # Line 799: Username hint
        self.username_field.add_widget(MDTextFieldHintText(
            text=tr("settings_screen.label_username")  # Was: "Username"
        ))
        
        # Line 804: Update button
        username_btn.add_widget(MDButtonText(
            text=tr("settings_screen.btn_update_username")  # Was: "Update Username"
        ))
        
        # And so on for all other sections...
```

### Dialogs

**About Dialog:**
```python
def show_about_dialog(self, *args):
    self.about_dialog = MDDialog(
        MDDialogHeadlineText(text=tr("about_dialog.title")),  # Was: "About Ghost Net"
        # ... rest of dialog content with tr() calls
    )
```

**Panic Dialog:**
```python
def show_panic_confirmation(self, *args):
    dialog = MDDialog(
        MDDialogHeadlineText(text=tr("panic_dialog.title_confirm")),
        MDDialogContentContainer(
            MDLabel(text=tr("panic_dialog.message_confirm")),
            # ...
        ),
        # ...
    )
```

---

## 🎨 Adding Language Selector to Settings

Add a new section in `SettingsScreen.__init__()` after the Appearance section:

```python
# 4. Language Section
language_card = self._create_section_card(
    tr("settings_screen.section_language"),     # "🌐 Language"
    tr("settings_screen.language_subtitle")      # "Choose your preferred language"
)

language_content = MDBoxLayout(
    orientation='vertical',
    adaptive_height=True,
    spacing=dp(10),
    padding=dp(10)
)

# Current language display
current_lang = get_current_language()
lang_name = get_supported_languages()[current_lang]

self.language_label = MDLabel(
    text=f"{tr('settings_screen.label_language')}: {lang_name}",
    font_style='Body',
    role='large',
    size_hint_y=None,
    height=dp(30)
)

# Change language button
lang_btn = MDButton(style='elevated')
lang_btn.add_widget(MDButtonText(text=tr("settings_screen.btn_change_language")))
lang_btn.bind(on_release=self.show_language_dialog)

language_content.add_widget(self.language_label)
language_content.add_widget(lang_btn)
language_card.add_widget(language_content)
settings_content.add_widget(language_card)
```

**Add the language dialog method:**

```python
def show_language_dialog(self, *args):
    """Show language selection dialog."""
    app = MDApp.get_running_app()
    
    # Create content with radio buttons
    content = MDBoxLayout(
        orientation='vertical',
        spacing=dp(10),
        padding=dp(20),
        adaptive_height=True
    )
    
    current_lang = get_current_language()
    
    for lang_code, lang_name in get_supported_languages().items():
        item = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(10),
            size_hint_y=None,
            height=dp(40)
        )
        
        # Radio button (simplified - use actual radio button widget)
        radio = MDLabel(
            text="●" if lang_code == current_lang else "○",
            font_style='Body',
            role='large',
            size_hint_x=0.1
        )
        
        # Language name
        label = MDLabel(
            text=lang_name,
            font_style='Body',
            role='large',
            size_hint_x=0.9
        )
        
        item.add_widget(radio)
        item.add_widget(label)
        
        # Make clickable
        item.bind(on_touch_down=lambda x, y, code=lang_code: self.select_language(code))
        
        content.add_widget(item)
    
    dialog = MDDialog(
        MDDialogHeadlineText(text=tr("language_dialog.title")),
        MDDialogContentContainer(content, orientation="vertical"),
        MDDialogButtonContainer(
            MDButton(
                MDButtonText(text=tr("language_dialog.btn_cancel")),
                style="text",
                on_release=lambda x: dialog.dismiss()
            ),
            spacing=dp(8)
        )
    )
    
    self.lang_dialog = dialog
    dialog.open()

def select_language(self, lang_code):
    """Handle language selection."""
    if hasattr(self, 'lang_dialog'):
        self.lang_dialog.dismiss()
    
    app = MDApp.get_running_app()
    
    # Save to config
    app.config.set_language(lang_code)
    
    # Update localization
    set_language(lang_code)
    
    # Update UI label
    lang_name = get_supported_languages()[lang_code]
    self.language_label.text = f"{tr('settings_screen.label_language')}: {lang_name}"
    
    print(f"[Settings] {tr('settings_screen.msg_language_changed', language=lang_name)}")
    print(f"[Settings] {tr('settings_screen.msg_restart_required')}")
```

---

## 🌐 Web Localization (Bonus)

Add simple JavaScript language detection to `web/index.html`:

**Add before closing `</body>` tag:**

```html
<script>
// Simple web localization
const translations = {
    en: {
        tagline: "The Network is You",
        download: "DOWNLOAD APK (v1.0.0)",
        features: "FEATURES"
    },
    es: {
        tagline: "La Red Eres Tú",
        download: "DESCARGAR APK (v1.0.0)",
        features: "CARACTERÍSTICAS"
    },
    hi: {
        tagline: "नेटवर्क आप हैं",
        download: "APK डाउनलोड करें (v1.0.0)",
        features: "विशेषताएं"
    },
    zh: {
        tagline: "网络就是你",
        download: "下载 APK (v1.0.0)",
        features: "功能特性"
    }
};

// Detect browser language
const userLang = navigator.language.substring(0, 2);
const lang = translations[userLang] || translations['en'];

// Apply translations (optional - keep English as default)
// document.querySelector('.hero-title .highlight').textContent = lang.tagline;
</script>
```

---

## 🧪 Testing Localization

### 1. Test Translation Loading

```bash
# Run the localization module test
python localization.py
```

**Expected output:**
```
Ghost Net Localization Module Test
==================================================

Supported Languages:
  en: English (100.0% coverage)
  es: Español (100.0% coverage)
  hi: हिन्दी (100.0% coverage)
  zh: 中文 (100.0% coverage)

Current Language: English

Test translation ('app_name'):
  English: Ghost Net
  Spanish: Ghost Net
  Hindi: Ghost Net
  Chinese: Ghost Net
```

### 2. Test in App

```python
# In main.py, add test code temporarily:
def test_translations(self):
    """Test all languages."""
    for lang_code in ['en', 'es', 'hi', 'zh']:
        set_language(lang_code)
        print(f"\n{lang_code}: {tr('radar_screen.title')}")
        print(f"  Status: {tr('radar_screen.status_scanning')}")
        print(f"  Button: {tr('chat_screen.btn_send')}")
```

### 3. Test Language Switching

1. Run app → Go to Settings
2. Click "Change Language"
3. Select Spanish
4. Restart app
5. Verify UI is in Spanish

---

## 📊 Translation Coverage

Run this to check coverage:

```python
from localization import get_localization_manager

manager = get_localization_manager()
for lang_code in ['en', 'es', 'hi', 'zh']:
    coverage = manager.get_translation_coverage(lang_code)
    print(f"{lang_code}: {coverage}% coverage")
```

---

## 🔄 Adding New Translations

### 1. Add to all JSON files

**English (`en.json`):**
```json
{
  "new_feature": {
    "title": "New Feature",
    "description": "This is a new feature"
  }
}
```

**Spanish (`es.json`):**
```json
{
  "new_feature": {
    "title": "Nueva Función",
    "description": "Esta es una nueva función"
  }
}
```

### 2. Use in code

```python
title = tr("new_feature.title")
description = tr("new_feature.description")
```

### 3. Reload translations (development)

```python
from localization import reload_translations
reload_translations()
```

---

## ⚠️ Important Notes

### 1. Emoji Consistency

Emojis should be **consistent across languages**:
```json
// ✅ Good - emoji stays the same
"title": "👻 Ghost Net"

// ❌ Bad - don't translate emoji
"title": "🌐 Ghost Net"  // Wrong emoji
```

### 2. Format Strings

Always use the same placeholders:
```json
// English
"status_found_peers": "Found {count} peer(s)"

// Spanish
"status_found_peers": "Se encontraron {count} par(es)"
```

### 3. RTL Languages (Future)

For Arabic/Hebrew support (future):
- Add `"rtl": true` to JSON
- Implement RTL layout switching
- Mirror UI elements

### 4. Pluralization (Advanced)

Current system doesn't handle plurals. For better plural support:

```json
"peers": {
  "zero": "No peers",
  "one": "1 peer",
  "other": "{count} peers"
}
```

---

## 🚀 Deployment Checklist

Before releasing with localization:

- [ ] All translation files present in `assets/locales/`
- [ ] `localization.py` imported in `main.py`
- [ ] Language preference added to `config.py`
- [ ] All UI strings replaced with `tr()` calls
- [ ] Language selector added to Settings
- [ ] Tested all 4 languages
- [ ] Updated `buildozer.spec` to include `assets/` directory:
  ```
  source.include_exts = py,png,jpg,kv,atlas,json
  ```
- [ ] Documentation updated (README, RELEASE_NOTES)

---

## 📚 Resources

### Translation Tools

- **Google Translate** - Quick translations (review needed)
- **DeepL** - Better quality translations
- **Native speakers** - Best for accuracy

### Testing Tools

```python
# Check for missing keys
from localization import get_localization_manager

manager = get_localization_manager()
en_keys = set(manager.translations['en'].keys())
es_keys = set(manager.translations['es'].keys())
missing = en_keys - es_keys
print(f"Missing in Spanish: {missing}")
```

---

## 🎯 Quick Reference

```python
# Import
from localization import tr, set_language, get_current_language

# Simple translation
text = tr("key")

# Nested translation
text = tr("section.key")

# With parameters
text = tr("message", count=5, name="Alice")

# Change language
set_language("es")

# Get current
lang = get_current_language()
```

---

**Status:** Localization system complete and ready for integration!

**Next Steps:**
1. Add language methods to `config.py`
2. Refactor `main.py` strings to use `tr()`
3. Add language selector to Settings
4. Test all languages
5. Deploy!

---

*Last Updated: 2026-01-27*  
*Ghost Net v1.0.0 - Internationalization*
