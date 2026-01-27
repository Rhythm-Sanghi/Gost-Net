"""
Ghost Net - Localization Module
Provides multi-language support for the application.

Supported Languages:
- English (en) - Default
- Spanish (es)
- Hindi (hi)
- Chinese Simplified (zh)

Usage:
    from localization import tr, set_language, get_current_language
    
    # Get translated string
    text = tr("radar_screen_title")
    
    # Change language
    set_language("es")
    
    # Get current language
    lang = get_current_language()
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional


class LocalizationManager:
    """Manages application translations and language switching."""
    
    def __init__(self, locale_dir: str = "assets/locales"):
        """
        Initialize the localization manager.
        
        Args:
            locale_dir: Directory containing translation JSON files
        """
        self.locale_dir = Path(locale_dir)
        self.current_language = 'en'
        self.fallback_language = 'en'
        self.translations: Dict[str, Dict[str, str]] = {}
        self.supported_languages = {
            'en': 'English',
            'es': 'Español',
            'hi': 'हिन्दी',
            'zh': '中文'
        }
        
        # Load all available translations
        self._load_translations()
    
    def _load_translations(self):
        """Load all translation files from the locale directory."""
        if not self.locale_dir.exists():
            print(f"[Localization] Warning: Locale directory not found: {self.locale_dir}")
            self.locale_dir.mkdir(parents=True, exist_ok=True)
            return
        
        for lang_code in self.supported_languages.keys():
            locale_file = self.locale_dir / f"{lang_code}.json"
            
            if locale_file.exists():
                try:
                    with open(locale_file, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                    print(f"[Localization] Loaded {lang_code}: {len(self.translations[lang_code])} strings")
                except Exception as e:
                    print(f"[Localization] Error loading {lang_code}.json: {e}")
            else:
                print(f"[Localization] Warning: {locale_file} not found")
    
    def set_language(self, lang_code: str) -> bool:
        """
        Set the current language.
        
        Args:
            lang_code: Language code (e.g., 'en', 'es', 'hi', 'zh')
            
        Returns:
            bool: True if language was set successfully, False otherwise
        """
        if lang_code not in self.supported_languages:
            print(f"[Localization] Unsupported language: {lang_code}")
            return False
        
        if lang_code not in self.translations:
            print(f"[Localization] Translations not loaded for: {lang_code}")
            return False
        
        self.current_language = lang_code
        print(f"[Localization] Language set to: {self.supported_languages[lang_code]} ({lang_code})")
        return True
    
    def get_current_language(self) -> str:
        """
        Get the current language code.
        
        Returns:
            str: Current language code
        """
        return self.current_language
    
    def get_language_name(self, lang_code: Optional[str] = None) -> str:
        """
        Get the native name of a language.
        
        Args:
            lang_code: Language code (uses current if None)
            
        Returns:
            str: Native language name
        """
        if lang_code is None:
            lang_code = self.current_language
        return self.supported_languages.get(lang_code, "Unknown")
    
    def get_supported_languages(self) -> Dict[str, str]:
        """
        Get all supported languages.
        
        Returns:
            dict: Mapping of language codes to native names
        """
        return self.supported_languages.copy()
    
    def translate(self, key: str, **kwargs) -> str:
        """
        Translate a string key to the current language.
        
        Args:
            key: Translation key
            **kwargs: Optional format parameters
            
        Returns:
            str: Translated string, or the key itself if not found
        """
        # Try current language
        if self.current_language in self.translations:
            if key in self.translations[self.current_language]:
                text = self.translations[self.current_language][key]
                try:
                    return text.format(**kwargs) if kwargs else text
                except KeyError as e:
                    print(f"[Localization] Format error in key '{key}': {e}")
                    return text
        
        # Fallback to English
        if self.fallback_language in self.translations:
            if key in self.translations[self.fallback_language]:
                text = self.translations[self.fallback_language][key]
                print(f"[Localization] Using fallback for key: {key}")
                try:
                    return text.format(**kwargs) if kwargs else text
                except KeyError as e:
                    print(f"[Localization] Format error in fallback key '{key}': {e}")
                    return text
        
        # Return key if not found
        print(f"[Localization] Missing translation key: {key}")
        return key
    
    def reload(self):
        """Reload all translation files."""
        self.translations.clear()
        self._load_translations()
        print(f"[Localization] Reloaded translations")
    
    def get_translation_coverage(self, lang_code: str) -> float:
        """
        Calculate translation coverage percentage.
        
        Args:
            lang_code: Language code to check
            
        Returns:
            float: Coverage percentage (0.0 to 100.0)
        """
        if lang_code not in self.translations or self.fallback_language not in self.translations:
            return 0.0
        
        base_keys = set(self.translations[self.fallback_language].keys())
        lang_keys = set(self.translations[lang_code].keys())
        
        if not base_keys:
            return 0.0
        
        coverage = len(lang_keys.intersection(base_keys)) / len(base_keys) * 100
        return round(coverage, 1)


# Global instance
_localization_manager: Optional[LocalizationManager] = None


def get_localization_manager() -> LocalizationManager:
    """
    Get the global localization manager instance.
    
    Returns:
        LocalizationManager: Global instance
    """
    global _localization_manager
    if _localization_manager is None:
        _localization_manager = LocalizationManager()
    return _localization_manager


def tr(key: str, **kwargs) -> str:
    """
    Translate a string key (convenience function).
    
    Args:
        key: Translation key
        **kwargs: Optional format parameters
        
    Returns:
        str: Translated string
        
    Example:
        text = tr("welcome_message", username="Alice")
    """
    return get_localization_manager().translate(key, **kwargs)


def set_language(lang_code: str) -> bool:
    """
    Set the current language (convenience function).
    
    Args:
        lang_code: Language code (e.g., 'en', 'es', 'hi', 'zh')
        
    Returns:
        bool: True if successful
        
    Example:
        set_language("es")
    """
    return get_localization_manager().set_language(lang_code)


def get_current_language() -> str:
    """
    Get the current language code (convenience function).
    
    Returns:
        str: Current language code
        
    Example:
        lang = get_current_language()  # Returns 'en'
    """
    return get_localization_manager().get_current_language()


def get_supported_languages() -> Dict[str, str]:
    """
    Get all supported languages (convenience function).
    
    Returns:
        dict: Mapping of language codes to native names
        
    Example:
        langs = get_supported_languages()
        # Returns: {'en': 'English', 'es': 'Español', ...}
    """
    return get_localization_manager().get_supported_languages()


def reload_translations():
    """
    Reload all translation files (convenience function).
    
    Useful for hot-reloading translations during development.
    """
    get_localization_manager().reload()


# Initialize on import
get_localization_manager()


if __name__ == '__main__':
    # Test the localization system
    print("Ghost Net Localization Module Test")
    print("=" * 50)
    
    manager = get_localization_manager()
    
    print(f"\nSupported Languages:")
    for code, name in manager.get_supported_languages().items():
        coverage = manager.get_translation_coverage(code)
        print(f"  {code}: {name} ({coverage}% coverage)")
    
    print(f"\nCurrent Language: {manager.get_language_name()}")
    
    # Test translation
    test_key = "app_name"
    print(f"\nTest translation ('{test_key}'):")
    print(f"  English: {tr(test_key)}")
    
    set_language("es")
    print(f"  Spanish: {tr(test_key)}")
    
    set_language("hi")
    print(f"  Hindi: {tr(test_key)}")
    
    set_language("zh")
    print(f"  Chinese: {tr(test_key)}")
    
    # Test missing key
    print(f"\nTest missing key:")
    print(f"  Result: {tr('nonexistent_key')}")
