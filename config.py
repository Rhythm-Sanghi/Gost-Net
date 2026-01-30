"""
Ghost Net - Configuration Manager
Persistent configuration storage with thread-safe access.
Handles app settings, user preferences, and hot-reloading.
"""

import json
import os
import threading
import random
import string
from typing import Any, Dict, Optional


class ConfigManager:
    """
    Manages application configuration with JSON persistence.
    
    Features:
    - Thread-safe read/write operations
    - Automatic defaults on first run
    - Hot-reloadable settings
    - Change event callbacks
    """
    
    DEFAULT_CONFIG = {
        "username": None,  # Will be generated on first run
        "retention_hours": 24,
        "dark_mode": True,
        "auto_cleanup": True,
        "notification_sound": True,
        "save_files": True,
        "max_file_size_mb": 100
    }
    
    def __init__(self, config_path: str = "settings.json"):
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Path to configuration file
        """
        # Use platform-aware paths
        import platform
        if platform.system() == 'Android':
            # On Android, use app-specific storage (don't import kivy.core.window here)
            try:
                config_path = os.path.join(os.path.expanduser("~"), ".ghostnet", config_path)
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
            except Exception as e:
                print(f"[ConfigManager] WARNING: Could not create config directory: {e}")
                # Fallback to current directory
                config_path = "settings.json"
        
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.config_lock = threading.Lock()
        self.change_callbacks = []
        self.initialization_error = None
        
        # Load or create config with error handling
        try:
            self.load()
            print(f"[ConfigManager] Initialized with config: {self.config_path}")
        except Exception as e:
            self.initialization_error = str(e)
            print(f"[ConfigManager] WARNING: Config initialization failed: {e}")
            print("[ConfigManager] Using default configuration")
            # Still initialize with defaults
            with self.config_lock:
                self.config = self.DEFAULT_CONFIG.copy()
                self.config["username"] = self._generate_random_username()
    
    def _generate_random_username(self) -> str:
        """Generate a random username for first-time users."""
        adjectives = [
            "Silent", "Shadow", "Phantom", "Ghost", "Dark", "Night",
            "Cyber", "Neon", "Electric", "Quantum", "Digital", "Crypto"
        ]
        
        nouns = [
            "Wolf", "Hawk", "Fox", "Raven", "Tiger", "Dragon",
            "Ninja", "Samurai", "Knight", "Warrior", "Sentinel", "Guardian"
        ]
        
        adjective = random.choice(adjectives)
        noun = random.choice(nouns)
        number = random.randint(10, 99)
        
        return f"{adjective}{noun}{number}"
    
    def load(self):
        """Load configuration from file or create defaults."""
        with self.config_lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        self.config = json.load(f)
                    print(f"[ConfigManager] Loaded config from {self.config_path}")
                except Exception as e:
                    print(f"[ConfigManager] Error loading config: {e}")
                    self.config = self.DEFAULT_CONFIG.copy()
            else:
                print("[ConfigManager] No config file found, creating defaults")
                self.config = self.DEFAULT_CONFIG.copy()
            
            # Generate username if not set
            if not self.config.get("username"):
                self.config["username"] = self._generate_random_username()
                print(f"[ConfigManager] Generated username: {self.config['username']}")
            
            # Ensure all default keys exist
            for key, value in self.DEFAULT_CONFIG.items():
                if key not in self.config:
                    self.config[key] = value
            
            # Save to persist generated values
            self._save_internal()
    
    def _save_internal(self):
        """Internal save method (assumes lock is held)."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            # print(f"[ConfigManager] Saved config to {self.config_path}")
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")
    
    def save(self):
        """Save configuration to file (thread-safe)."""
        with self.config_lock:
            self._save_internal()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        with self.config_lock:
            return self.config.get(key, default)
    
    def set(self, key: str, value: Any, save: bool = True):
        """
        Set a configuration value.
        
        Args:
            key: Configuration key
            value: Value to set
            save: Whether to save to disk immediately
        """
        with self.config_lock:
            old_value = self.config.get(key)
            self.config[key] = value
            
            if save:
                self._save_internal()
            
            # Trigger change callbacks
            if old_value != value:
                self._trigger_callbacks(key, old_value, value)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values as a dictionary."""
        with self.config_lock:
            return self.config.copy()
    
    def update(self, updates: Dict[str, Any], save: bool = True):
        """
        Update multiple configuration values.
        
        Args:
            updates: Dictionary of key-value pairs to update
            save: Whether to save to disk immediately
        """
        with self.config_lock:
            for key, value in updates.items():
                old_value = self.config.get(key)
                self.config[key] = value
                
                # Trigger change callbacks
                if old_value != value:
                    self._trigger_callbacks(key, old_value, value)
            
            if save:
                self._save_internal()
    
    def reset_to_defaults(self):
        """Reset configuration to defaults (except username)."""
        with self.config_lock:
            username = self.config.get("username")
            self.config = self.DEFAULT_CONFIG.copy()
            
            # Preserve username
            if username:
                self.config["username"] = username
            else:
                self.config["username"] = self._generate_random_username()
            
            self._save_internal()
            print("[ConfigManager] Reset to defaults")
    
    def delete_config(self):
        """Delete the configuration file."""
        try:
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
                print(f"[ConfigManager] Deleted config file: {self.config_path}")
        except Exception as e:
            print(f"[ConfigManager] Error deleting config: {e}")
    
    def register_change_callback(self, callback):
        """
        Register a callback to be called when config changes.
        
        Args:
            callback: Function(key, old_value, new_value)
        """
        if callback not in self.change_callbacks:
            self.change_callbacks.append(callback)
    
    def unregister_change_callback(self, callback):
        """Unregister a change callback."""
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    def _trigger_callbacks(self, key: str, old_value: Any, new_value: Any):
        """Trigger registered callbacks (assumes lock is held)."""
        for callback in self.change_callbacks:
            try:
                callback(key, old_value, new_value)
            except Exception as e:
                print(f"[ConfigManager] Callback error: {e}")
    
    # Convenience methods for common settings
    
    def get_username(self) -> str:
        """Get the current username."""
        return self.get("username", "GhostUser")
    
    def set_username(self, username: str):
        """Set the username."""
        if username and username.strip():
            self.set("username", username.strip())
    
    def get_retention_hours(self) -> int:
        """Get message retention period in hours."""
        return self.get("retention_hours", 24)
    
    def set_retention_hours(self, hours: int):
        """Set message retention period."""
        if 1 <= hours <= 168:  # 1 hour to 7 days
            self.set("retention_hours", hours)
    
    def is_dark_mode(self) -> bool:
        """Check if dark mode is enabled."""
        return self.get("dark_mode", True)
    
    def set_dark_mode(self, enabled: bool):
        """Set dark mode."""
        self.set("dark_mode", enabled)
    
    def is_auto_cleanup_enabled(self) -> bool:
        """Check if auto cleanup is enabled."""
        return self.get("auto_cleanup", True)
    
    def set_auto_cleanup(self, enabled: bool):
        """Enable/disable auto cleanup."""
        self.set("auto_cleanup", enabled)
    
    def get_max_file_size_mb(self) -> int:
        """Get maximum file size for transfers in MB."""
        return self.get("max_file_size_mb", 100)
    
    def set_max_file_size_mb(self, size_mb: int):
        """Set maximum file size."""
        if 1 <= size_mb <= 500:
            self.set("max_file_size_mb", size_mb)
    
    def __str__(self) -> str:
        """String representation of config."""
        with self.config_lock:
            return json.dumps(self.config, indent=2)


# Global configuration instance
_config_instance: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """
    Get the global configuration instance (singleton pattern).
    
    Returns:
        ConfigManager instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance


def reset_config():
    """Reset the global configuration instance (for testing)."""
    global _config_instance
    _config_instance = None


# Example usage and testing
if __name__ == "__main__":
    print("=== Ghost Net Configuration Manager Test ===\n")
    
    # Test config creation
    print("1. Testing configuration initialization...")
    config = ConfigManager(config_path="test_settings.json")
    print(f"   Username: {config.get_username()}")
    print(f"   Retention: {config.get_retention_hours()} hours")
    print(f"   Dark Mode: {config.is_dark_mode()}")
    
    # Test setting values
    print("\n2. Testing configuration updates...")
    config.set_username("TestGhost")
    config.set_retention_hours(48)
    config.set_dark_mode(False)
    
    print(f"   New Username: {config.get_username()}")
    print(f"   New Retention: {config.get_retention_hours()} hours")
    print(f"   New Dark Mode: {config.is_dark_mode()}")
    
    # Test change callbacks
    print("\n3. Testing change callbacks...")
    def on_config_change(key, old, new):
        print(f"   Config changed: {key} = {old} → {new}")
    
    config.register_change_callback(on_config_change)
    config.set_username("GhostWolf42")
    config.set_retention_hours(12)
    
    # Test persistence
    print("\n4. Testing persistence...")
    config2 = ConfigManager(config_path="test_settings.json")
    print(f"   Loaded Username: {config2.get_username()}")
    print(f"   Loaded Retention: {config2.get_retention_hours()} hours")
    
    # Test bulk update
    print("\n5. Testing bulk update...")
    config.update({
        "username": "BulkUpdated",
        "retention_hours": 72,
        "dark_mode": True
    })
    print(f"   Username: {config.get_username()}")
    print(f"   Retention: {config.get_retention_hours()} hours")
    print(f"   Dark Mode: {config.is_dark_mode()}")
    
    # Test reset
    print("\n6. Testing reset to defaults...")
    config.reset_to_defaults()
    print(f"   Username: {config.get_username()}")
    print(f"   Retention: {config.get_retention_hours()} hours")
    print(f"   Dark Mode: {config.is_dark_mode()}")
    
    # Display all config
    print("\n7. Complete configuration:")
    print(config)
    
    print("\n=== Test Complete ===")
    print("Check test_settings.json for persisted config")
