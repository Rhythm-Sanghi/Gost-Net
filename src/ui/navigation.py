"""
Ghost Net - Centralized Navigation & Back Button Controller
Unified screen transitions, back-stack management, modal/dialog dismissal,
and deliberate root exit confirmation.
"""

import time
from typing import Any, List, Optional
from kivy.core.window import Window
from kivymd.app import MDApp


class NavigationController:
    """
    Central navigation authority for Gost-Net.
    Tracks screen history, handles Android hardware Back (key 27) and toolbar Back,
    dismisses open dialogs/overlays first, and prevents accidental app exit.
    """
    _instance: Optional['NavigationController'] = None

    def __init__(self):
        self.history: List[str] = []
        self.active_dialogs: List[Any] = []
        self._last_root_back_time: float = 0.0
        self._root_back_timeout: float = 2.5
        self._keyboard_hooked: bool = False
        self._screen_manager: Optional[Any] = None

    @classmethod
    def get_instance(cls) -> 'NavigationController':
        if cls._instance is None:
            cls._instance = NavigationController()
        return cls._instance

    def bind_screen_manager(self, sm: Any):
        """Explicitly bind screen manager (supports unit testing and custom topologies)."""
        self._screen_manager = sm

    def _get_screen_manager(self) -> Optional[Any]:
        if self._screen_manager is not None:
            return self._screen_manager
        app = MDApp.get_running_app()
        if app and hasattr(app, 'root'):
            return app.root
        return None

    def setup_window_hooks(self):
        """Bind hardware keyboard/back key handler once."""
        if not self._keyboard_hooked:
            Window.bind(on_keyboard=self._on_window_keyboard)
            self._keyboard_hooked = True

    def _on_window_keyboard(self, window, key, scancode, codepoint, modifier) -> bool:
        # Key 27 is Android KEYCODE_BACK and Esc
        if key == 27:
            return self.handle_back_key()
        return False

    def register_dialog(self, dialog: Any):
        """Track open dialog so hardware Back can dismiss it first."""
        if dialog and dialog not in self.active_dialogs:
            self.active_dialogs.append(dialog)

    def unregister_dialog(self, dialog: Any):
        """Untrack dismissed dialog."""
        if dialog in self.active_dialogs:
            self.active_dialogs.remove(dialog)

    def navigate_to(self, screen_name: str, direction: str = 'left'):
        """Navigate to a target screen, updating navigation history."""
        sm = self._get_screen_manager()
        if not sm:
            return

        has_screen = getattr(sm, 'has_screen', None)
        if callable(has_screen) and not has_screen(screen_name):
            print(f"[Navigation] Screen '{screen_name}' does not exist in ScreenManager")
            return

        current = sm.current
        if current != screen_name:
            # Don't add transient bootstrap or lock screens to back history
            if current not in ('boot', 'lock'):
                if not self.history or self.history[-1] != current:
                    self.history.append(current)

            if hasattr(sm, 'transition') and sm.transition:
                sm.transition.direction = direction
            sm.current = screen_name

    def go_back(self, direction: str = 'right') -> bool:
        """Invoked by toolbar back buttons and Android hardware Back."""
        return self.handle_back_key(direction=direction)

    def handle_back_key(self, direction: str = 'right') -> bool:
        """
        Handle back action according to strict priority order:
        1. Close topmost active dialog/modal
        2. Screen-level nested back handler (e.g. tabs, search)
        3. Navigate back to previous screen in history
        4. If on sub-screen without history, return to 'radar'
        5. If on 'radar' root: deliberate exit confirmation ("Press back again to exit")
        6. If on 'lock' or 'boot': do not expose content
        """
        # Priority 1: Dismiss topmost open dialog
        while self.active_dialogs:
            dialog = self.active_dialogs.pop()
            try:
                dialog.dismiss()
                return True
            except Exception as e:
                print(f"[Navigation] Dialog dismissal exception: {e}")

        sm = self._get_screen_manager()
        if not sm:
            return False

        current_screen_name = sm.current
        current_screen = getattr(sm, 'current_screen', None)
        if not current_screen and hasattr(sm, 'get_screen'):
            try:
                current_screen = sm.get_screen(current_screen_name)
            except Exception:
                current_screen = None

        # Priority 2: Custom screen-level back handler (nested views, tabs)
        if current_screen and hasattr(current_screen, 'handle_back') and callable(current_screen.handle_back):
            try:
                if current_screen.handle_back():
                    return True
            except Exception as e:
                print(f"[Navigation] Screen handle_back error: {e}")

        # Priority 3 & 4: Sub-screen back to previous history or 'radar'
        if current_screen_name not in ('radar', 'lock', 'boot'):
            target_screen = 'radar'
            has_screen_fn = getattr(sm, 'has_screen', lambda x: True)
            while self.history:
                prev = self.history.pop()
                if has_screen_fn(prev) and prev not in ('lock', 'boot', current_screen_name):
                    target_screen = prev
                    break

            if hasattr(sm, 'transition') and sm.transition:
                sm.transition.direction = direction
            sm.current = target_screen
            return True

        # Priority 5: On 'radar' root screen: deliberate exit with timeout
        if current_screen_name == 'radar':
            now = time.time()
            if now - self._last_root_back_time < self._root_back_timeout:
                # User pressed back twice within 2.5s -> exit application deliberately
                app = MDApp.get_running_app()
                if app and hasattr(app, 'stop'):
                    app.stop()
                return False  # letting key 27 bubble allows Android/Kivy to exit cleanly
            else:
                self._last_root_back_time = now
                if hasattr(current_screen, 'show_exit_notice'):
                    current_screen.show_exit_notice("Press back again to exit")
                return True

        # Priority 6: On 'lock' or 'boot' - consume event to protect locked state
        return True


def get_navigation_controller() -> NavigationController:
    return NavigationController.get_instance()
