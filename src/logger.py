import sys
import os
from io import StringIO
from typing import Optional

PRODUCTION_MODE = False

class _DevNullWriter:
    def write(self, text: str) -> int:
        return len(text) if text else 0
    
    def flush(self):
        pass
    
    def isatty(self) -> bool:
        return False

class _OpsecLogger:
    def __init__(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.dev_null = _DevNullWriter()
        self.production_mode = False
        self._devnull_file = None

    def activate_production_mode(self):
        global PRODUCTION_MODE
        PRODUCTION_MODE = True
        self.production_mode = True
        sys.stdout = self.dev_null
        sys.stderr = self.dev_null
        
        try:
            import os
            self._devnull_file = open(os.devnull, 'w')
            sys.stdout = self._devnull_file
            sys.stderr = self._devnull_file
        except:
            sys.stdout = self.dev_null
            sys.stderr = self.dev_null

    def deactivate_production_mode(self):
        global PRODUCTION_MODE
        PRODUCTION_MODE = False
        self.production_mode = False
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        if self._devnull_file:
            try:
                self._devnull_file.close()
            except:
                pass
            self._devnull_file = None

    def is_production(self) -> bool:
        return self.production_mode

_opsec_logger_instance = _OpsecLogger()

def activate_opsec():
    _opsec_logger_instance.activate_production_mode()

def deactivate_opsec():
    _opsec_logger_instance.deactivate_production_mode()

def is_opsec_active() -> bool:
    return _opsec_logger_instance.is_production()

def get_logger():
    return _opsec_logger_instance
