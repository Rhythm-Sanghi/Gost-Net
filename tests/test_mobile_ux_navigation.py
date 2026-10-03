"""
Tests for Gost-Net Mobile UX, Navigation Controller, and Interaction Stabilization.
Validates centralized navigation stack, hardware back priority, dialog dismissal,
root double-back exit confirmation, setup form focus/submission guards,
and PIN auto-unlock opsec boundaries.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from kivymd.app import MDApp
from ui.navigation import NavigationController, get_navigation_controller


@pytest.fixture(scope="session", autouse=True)
def init_kivy_app():
    app = MDApp.get_running_app()
    if not app:
        app = MDApp()
    return app


class MockScreen:
    def __init__(self, name, handle_back_return=None):
        self.name = name
        self.handle_back_return = handle_back_return
        self.handle_back_called = False
        self.exit_notice_shown = False

    def handle_back(self):
        self.handle_back_called = True
        return self.handle_back_return

    def show_exit_notice(self, msg=""):
        self.exit_notice_shown = True


class MockScreenManager:
    def __init__(self):
        self.current = 'radar'
        self.screens = {}

    def get_screen(self, name):
        return self.screens.get(name)

    def has_screen(self, name):
        return name in self.screens or name in ('radar', 'settings', 'diagnostics', 'map', 'notes', 'chat', 'lock', 'boot')


class MockDialog:
    def __init__(self):
        self.dismissed = False

    def dismiss(self):
        self.dismissed = True


def test_navigation_controller_singleton():
    c1 = get_navigation_controller()
    c2 = get_navigation_controller()
    assert c1 is c2


def test_navigation_controller_stack():
    controller = NavigationController()
    sm = MockScreenManager()
    controller.bind_screen_manager(sm)

    assert sm.current == 'radar'

    controller.navigate_to('settings')
    assert sm.current == 'settings'
    assert controller.history == ['radar']

    controller.navigate_to('diagnostics')
    assert sm.current == 'diagnostics'
    assert controller.history == ['radar', 'settings']

    # Go back pops to settings
    handled = controller.go_back()
    assert handled is True
    assert sm.current == 'settings'
    assert controller.history == ['radar']

    # Go back pops to radar
    handled = controller.go_back()
    assert handled is True
    assert sm.current == 'radar'
    assert controller.history == []


def test_hardware_back_dialog_dismissal_priority():
    controller = NavigationController()
    sm = MockScreenManager()
    radar_screen = MockScreen('radar')
    sm.screens['radar'] = radar_screen
    controller.bind_screen_manager(sm)

    d1 = MockDialog()
    d2 = MockDialog()

    controller.register_dialog(d1)
    controller.register_dialog(d2)

    # First back key should dismiss topmost dialog d2
    handled = controller.handle_back_key()
    assert handled is True
    assert d2.dismissed is True
    assert d1.dismissed is False
    assert len(controller.active_dialogs) == 1

    # Second back key should dismiss d1
    handled = controller.handle_back_key()
    assert handled is True
    assert d1.dismissed is True
    assert len(controller.active_dialogs) == 0


def test_hardware_back_screen_level_handler():
    controller = NavigationController()
    sm = MockScreenManager()
    radar_screen = MockScreen('radar', handle_back_return=True)
    sm.screens['radar'] = radar_screen
    controller.bind_screen_manager(sm)

    # When radar screen's handle_back returns True, it is consumed
    handled = controller.handle_back_key()
    assert handled is True
    assert radar_screen.handle_back_called is True
    assert radar_screen.exit_notice_shown is False


def test_hardware_back_root_double_back_exit():
    controller = NavigationController()
    sm = MockScreenManager()
    radar_screen = MockScreen('radar', handle_back_return=False)
    sm.screens['radar'] = radar_screen
    controller.bind_screen_manager(sm)

    # First back press at root: shows notice, does not exit
    mock_app = MagicMock()
    with patch('kivymd.app.MDApp.get_running_app', return_value=mock_app):
        handled = controller.handle_back_key()
        assert handled is True
        assert radar_screen.exit_notice_shown is True
        assert mock_app.stop.called is False

        # Second back press within exit confirmation window: triggers exit
        handled = controller.handle_back_key()
        assert handled is False  # returns False to allow key bubble to exit
        assert mock_app.stop.called is True


def test_hardware_back_lock_screen_safety():
    controller = NavigationController()
    sm = MockScreenManager()
    sm.current = 'lock'
    lock_screen = MockScreen('lock')
    sm.screens['lock'] = lock_screen
    controller.bind_screen_manager(sm)

    # Must not navigate back or expose unauthenticated screens
    handled = controller.handle_back_key()
    assert handled is True
    assert sm.current == 'lock'
    assert len(controller.history) == 0


def test_setup_form_submission_guard():
    from ui.screens.lock_screen import LockScreen
    screen = LockScreen()
    assert screen._setup_in_progress is False

    # Simulate in-progress guard
    screen._setup_in_progress = True
    # Calling on_setup_submit while in progress must safely abort without duplicate run
    screen.on_setup_submit()
    assert screen._setup_in_progress is True


def test_auto_unlock_pin_length_and_duress_rules():
    from ui.screens.lock_screen import LockScreen
    screen = LockScreen()

    # In unlock mode (or mocked unlock UI)
    mock_pin_field = MagicMock()
    screen.pin_field = mock_pin_field

    # Master PIN with length < 6: auto-unlock must NOT trigger
    screen._on_pin_text_changed(mock_pin_field, "1234")
    assert screen._debounce_event is None

    # Master PIN with length >= 6: schedules debounced auto-unlock
    screen._on_pin_text_changed(mock_pin_field, "123456")
    assert screen._debounce_event is not None
    if screen._debounce_event:
        screen._debounce_event.cancel()
        screen._debounce_event = None

    # When unlock is in progress, further changes are ignored
    screen._unlock_in_progress = True
    screen._on_pin_text_changed(mock_pin_field, "12345678")
    assert screen._debounce_event is None


def test_map_screen_always_accessible():
    from ui.screens.map_screen import MapScreen
    map_screen = MapScreen()
    assert map_screen.name == 'map'
    assert hasattr(map_screen, 'go_back')
    assert hasattr(map_screen, 'load_offline_map')
    assert hasattr(map_screen, 'update_user_location')
