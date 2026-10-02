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



def apply_premium_background(screen):
    """Applies a premium space-obsidian dark canvas background to a screen."""
    from kivy.graphics import Color, Rectangle
    from kivymd.app import MDApp
    
    app = MDApp.get_running_app()
    if not app:
        return
    is_dark = getattr(getattr(app, 'theme_cls', None), 'theme_style', 'Dark') == "Dark"
    bg_color = (0.04, 0.04, 0.05, 1) if is_dark else (0.96, 0.97, 0.99, 1)
    
    with screen.canvas.before:
        screen.bg_color_inst = Color(*bg_color)
        screen.bg_rect = Rectangle(pos=screen.pos, size=screen.size)
    
    def _update_bg(instance, value):
        screen.bg_rect.pos = screen.pos
        screen.bg_rect.size = screen.size
        
    screen.bind(pos=_update_bg, size=_update_bg)
    
    def _update_theme_color(*args):
        is_dark = app.theme_cls.theme_style == "Dark"
        c = (0.04, 0.04, 0.05, 1) if is_dark else (0.96, 0.97, 0.99, 1)
        screen.bg_color_inst.rgba = c
        
    if getattr(app, 'theme_cls', None):
        app.theme_cls.bind(theme_style=_update_theme_color)
