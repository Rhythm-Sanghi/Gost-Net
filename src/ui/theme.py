"""
Ghost Net UI - Theme and Styling Framework
Provides centralized styling, adaptive color palettes, KivyMD compatibility shims,
and custom background decorators.
"""

import os
import sys

def _safe_import(module_path, name, fallback_class=None):
    try:
        parts = module_path.rsplit('.', 1)
        module = __import__(module_path, fromlist=[name])
        return getattr(module, name)
    except (ImportError, AttributeError):
        if fallback_class:
            return fallback_class
        raise

# Prevent OpenGL FBO crashes (Incomplete attachment 36054) on Android during widget creation
try:
    from kivymd.uix.behaviors.ripple_behavior import RectangularRippleBehavior
    def _noop_init_fbos(self):
        self._phase = 0.0
        self.ripple_pos = (0, 0)
        self.fbo = None
    RectangularRippleBehavior.init_fbos = _noop_init_fbos
    
    _orig_lay = getattr(RectangularRippleBehavior, 'lay_canvas_instructions', None)
    def _safe_lay(self):
        if getattr(self, 'fbo', None) is None:
            return
        if _orig_lay:
            return _orig_lay(self)
    RectangularRippleBehavior.lay_canvas_instructions = _safe_lay
except Exception:
    pass

try:
    from kivymd.app import MDApp
    from kivy.metrics import dp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.screenmanager import MDScreenManager
    from kivymd.uix.button import MDButton, MDIconButton
    try:
        from kivymd.uix.button import MDFloatingActionButton
    except ImportError:
        MDFloatingActionButton = None
    from kivymd.uix.textfield import MDTextField
    from kivymd.uix.label import MDLabel
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.scrollview import MDScrollView
    from kivymd.uix.card import MDCard
    try:
        MDCard.init_fbos = _noop_init_fbos
        MDCard.lay_canvas_instructions = _safe_lay
    except Exception:
        pass
    from kivymd.uix.slider import MDSlider
    from kivymd.uix.floatlayout import MDFloatLayout
    
    # Create fallback classes for optional components
    from kivy.uix.widget import Widget as KivyWidget
    from kivy.properties import BooleanProperty
    
    class _DummySpinner(KivyWidget):
        """Fallback spinner for KivyMD versions without MDSpinner."""
        active = BooleanProperty(True)
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
    
    class _DummyDialog(KivyWidget):
        """Fallback dialog for KivyMD versions without MDDialog."""
        def __init__(self, *args, **kwargs):
            super().__init__(**kwargs)
        def open(self, *args): pass
        def dismiss(self, *args): pass
    
    class _DummySwitch(KivyWidget):
        """Fallback switch for KivyMD versions without MDSwitch."""
        active = BooleanProperty(False)
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
    
    # Import optional components with fallbacks
    try:
        # Try KivyMD 2.0+ first (MDCircularProgressIndicator)
        from kivymd.uix.progressindicator import MDCircularProgressIndicator as MDSpinner
    except ImportError:
        try:
            # Fall back to older MDSpinner
            from kivymd.uix.spinner import MDSpinner
        except ImportError:
            MDSpinner = _DummySpinner
    
    try:
        from kivymd.uix.button import MDButtonText
        from kivymd.uix.textfield import MDTextFieldHintText, MDTextFieldHelperText
    except ImportError:
        MDButtonText = MDLabel
        MDTextFieldHintText = lambda **kwargs: KivyWidget(**{k: v for k, v in kwargs.items() if k != 'text'})
        MDTextFieldHelperText = lambda **kwargs: KivyWidget(**{k: v for k, v in kwargs.items() if k != 'text'})
    
    try:
        from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogContentContainer, MDDialogButtonContainer
        _orig_dialog_open = MDDialog.open
        _orig_dialog_dismiss = MDDialog.dismiss
        def _tracked_dialog_open(self, *args, **kwargs):
            try:
                from ui.navigation import get_navigation_controller
                get_navigation_controller().register_dialog(self)
            except Exception:
                pass
            return _orig_dialog_open(self, *args, **kwargs)
        def _tracked_dialog_dismiss(self, *args, **kwargs):
            try:
                from ui.navigation import get_navigation_controller
                get_navigation_controller().unregister_dialog(self)
            except Exception:
                pass
            return _orig_dialog_dismiss(self, *args, **kwargs)
        MDDialog.open = _tracked_dialog_open
        MDDialog.dismiss = _tracked_dialog_dismiss
    except ImportError:
        MDDialog = _DummyDialog
        MDDialogHeadlineText = MDLabel
        MDDialogContentContainer = MDBoxLayout
        MDDialogButtonContainer = MDBoxLayout
    
    try:
        from kivymd.uix.switch import MDSwitch
    except ImportError:
        MDSwitch = _DummySwitch
    
    try:
        from kivymd.uix.progressbar import MDProgressBar
    except ImportError:
        MDProgressBar = None
    
    KIVYMD_AVAILABLE = True
except ImportError as e:
    import traceback
    err_msg = f"[CRITICAL] KivyMD import failed: {e}\n{traceback.format_exc()}"
    try:
        sys.__stderr__.write(err_msg + "\n")
        sys.__stderr__.flush()
    except Exception:
        pass
    raise RuntimeError(err_msg) from e




# =============================================================================
# WORKSHOP GRID DESIGN TOKENS
# =============================================================================

class WorkshopGridTokens:
    """
    Semantic color, spacing, radius, and typography tokens for the
    Workshop Grid design system.
    """
    # Palette - Dark Mode (Default for Gost-Net radio/mesh environment)
    DARK_CANVAS = (0.067, 0.071, 0.063, 1.0)           # #111210
    DARK_SURFACE = (0.090, 0.094, 0.086, 1.0)          # #171816
    DARK_SURFACE_RAISED = (0.114, 0.118, 0.106, 1.0)   # #1D1E1B
    DARK_BORDER = (0.188, 0.192, 0.176, 1.0)           # #30312D
    DARK_BORDER_STRONG = (0.280, 0.285, 0.270, 1.0)    # #474945
    DARK_TEXT_PRIMARY = (0.910, 0.914, 0.894, 1.0)     # #E8E9E4
    DARK_TEXT_SECONDARY = (0.627, 0.631, 0.604, 1.0)   # #A0A19A
    DARK_TEXT_MUTED = (0.451, 0.459, 0.435, 1.0)       # #73756F

    # Palette - Light Mode
    LIGHT_CANVAS = (0.957, 0.957, 0.945, 1.0)          # #F4F4F1
    LIGHT_SURFACE = (0.980, 0.980, 0.973, 1.0)         # #FAFAF8
    LIGHT_SURFACE_RAISED = (1.000, 1.000, 1.000, 1.0)  # #FFFFFF
    LIGHT_BORDER = (0.843, 0.847, 0.824, 1.0)          # #D7D8D2
    LIGHT_BORDER_STRONG = (0.722, 0.729, 0.702, 1.0)   # #B8BAB3
    LIGHT_TEXT_PRIMARY = (0.098, 0.102, 0.094, 1.0)    # #191A18
    LIGHT_TEXT_SECONDARY = (0.400, 0.408, 0.384, 1.0)  # #666862
    LIGHT_TEXT_MUTED = (0.565, 0.569, 0.549, 1.0)      # #90918C

    # Signature Accent: Industrial Cobalt/Steel Blue (restrained, 5-10% of UI)
    ACCENT = (0.24, 0.44, 0.64, 1.0)                   # #3D70A3 (industrial blue)
    ACCENT_MUTED = (0.18, 0.32, 0.48, 1.0)             # muted accent
    ACCENT_HOVER = (0.30, 0.52, 0.74, 1.0)

    # Restrained Status Indicators (symbol + text + color)
    STATUS_SUCCESS = (0.35, 0.62, 0.42, 1.0)           # muted forest green
    STATUS_WARNING = (0.78, 0.58, 0.28, 1.0)           # warm amber
    STATUS_DANGER = (0.75, 0.32, 0.30, 1.0)            # muted oxide red
    STATUS_INFO = (0.32, 0.52, 0.70, 1.0)              # muted blue

    # Radii - Intentionally restrained
    RADIUS_SM = [dp(3), dp(3), dp(3), dp(3)]
    RADIUS_MD = [dp(5), dp(5), dp(5), dp(5)]
    RADIUS_LG = [dp(8), dp(8), dp(8), dp(8)]
    RADIUS_NONE = [0, 0, 0, 0]

    @classmethod
    def get_canvas(cls, is_dark=True):
        return cls.DARK_CANVAS if is_dark else cls.LIGHT_CANVAS

    @classmethod
    def get_surface(cls, is_dark=True):
        return cls.DARK_SURFACE if is_dark else cls.LIGHT_SURFACE

    @classmethod
    def get_surface_raised(cls, is_dark=True):
        return cls.DARK_SURFACE_RAISED if is_dark else cls.LIGHT_SURFACE_RAISED

    @classmethod
    def get_border(cls, is_dark=True):
        return cls.DARK_BORDER if is_dark else cls.LIGHT_BORDER

    @classmethod
    def get_border_strong(cls, is_dark=True):
        return cls.DARK_BORDER_STRONG if is_dark else cls.LIGHT_BORDER_STRONG

    @classmethod
    def get_text_primary(cls, is_dark=True):
        return cls.DARK_TEXT_PRIMARY if is_dark else cls.LIGHT_TEXT_PRIMARY

    @classmethod
    def get_text_secondary(cls, is_dark=True):
        return cls.DARK_TEXT_SECONDARY if is_dark else cls.LIGHT_TEXT_SECONDARY

    @classmethod
    def get_text_muted(cls, is_dark=True):
        return cls.DARK_TEXT_MUTED if is_dark else cls.LIGHT_TEXT_MUTED


def apply_workshop_background(screen):
    """
    Applies the Workshop Grid canvas background to a screen.
    Uses precise structural background tones instead of generic gradients.
    """
    from kivy.graphics import Color, Rectangle
    from kivymd.app import MDApp
    
    app = MDApp.get_running_app()
    is_dark = True
    if app and hasattr(app, 'theme_cls') and getattr(app.theme_cls, 'theme_style', 'Dark') == 'Light':
        is_dark = False
        
    bg_color = WorkshopGridTokens.get_canvas(is_dark)
    
    with screen.canvas.before:
        screen.bg_color_inst = Color(*bg_color)
        screen.bg_rect = Rectangle(pos=screen.pos, size=screen.size)
    
    def _update_bg(instance, value):
        screen.bg_rect.pos = screen.pos
        screen.bg_rect.size = screen.size
        
    screen.bind(pos=_update_bg, size=_update_bg)
    
    def _update_theme_color(*args):
        dark_now = getattr(getattr(app, 'theme_cls', None), 'theme_style', 'Dark') == "Dark"
        screen.bg_color_inst.rgba = WorkshopGridTokens.get_canvas(dark_now)
        
    if app and getattr(app, 'theme_cls', None):
        app.theme_cls.bind(theme_style=_update_theme_color)


def apply_premium_background(screen):
    """Backward-compatible alias for apply_workshop_background."""
    apply_workshop_background(screen)

