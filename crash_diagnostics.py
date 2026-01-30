"""
Ghost Net - Crash Diagnostics with Strategic Logging
Comprehensive startup checkpoint logging to identify crash causes.
"""

import os
import sys
import threading
import time
from datetime import datetime
import platform

class CrashDiagnostics:
    """Diagnostic toolkit for startup crashes."""
    
    # Singleton instance
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CrashDiagnostics, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.start_time = time.time()
        self.checkpoints = []
        self.log_file = "crash_diagnostics.log"
        self.thread_info = {}
        
        # Initialize log file
        self._write_header()
    
    def _write_header(self):
        """Write diagnostic header to log file."""
        header = f"""
{'='*80}
GHOST NET CRASH DIAGNOSTICS LOG
{'='*80}
Start Time: {datetime.now().isoformat()}
Platform: {platform.system()} {platform.release()}
Python: {sys.version.split()[0]}
Architecture: {platform.machine()}
Current Directory: {os.getcwd()}
{'='*80}

"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(header)
        print(f"[DIAGNOSTICS] Log file: {self.log_file}")
    
    def checkpoint(self, name: str, status: str = "OK", details: str = ""):
        """
        Record a startup checkpoint.
        
        Args:
            name: Checkpoint name
            status: "OK", "WARNING", "ERROR", "CRITICAL"
            details: Additional information
        """
        elapsed = time.time() - self.start_time
        thread_id = threading.current_thread().ident
        thread_name = threading.current_thread().name
        
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'elapsed': f"{elapsed:.3f}s",
            'thread_id': thread_id,
            'thread_name': thread_name,
            'checkpoint': name,
            'status': status,
            'details': details
        }
        
        self.checkpoints.append(checkpoint_data)
        
        # Format log line
        status_symbol = {
            'OK': '✓',
            'WARNING': '⚠',
            'ERROR': '✗',
            'CRITICAL': '🔴'
        }.get(status, '?')
        
        log_line = f"[{elapsed:7.3f}s] {status_symbol} {name:40} | {status:8} | {details}"
        
        # Print to console
        print(log_line)
        
        # Write to log file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line + "\n")
        
        return checkpoint_data
    
    def section(self, title: str):
        """Write a section header."""
        separator = f"\n{'─'*80}\n{title}\n{'─'*80}\n"
        print(separator)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(separator)
    
    def exception(self, context: str, exc: Exception):
        """Log an exception with full traceback."""
        import traceback
        
        tb_str = traceback.format_exc()
        log_entry = f"\n[EXCEPTION] {context}\n{tb_str}\n"
        
        print(f"[DIAGNOSTICS] EXCEPTION in {context}: {exc}")
        print(tb_str)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    
    def environment_check(self):
        """Check environment variables and paths."""
        self.section("ENVIRONMENT CHECK")
        
        # Check important environment variables
        env_vars = {
            'PATH': os.environ.get('PATH', 'NOT SET'),
            'PYTHONPATH': os.environ.get('PYTHONPATH', 'NOT SET'),
            'ANDROID_SDK_ROOT': os.environ.get('ANDROID_SDK_ROOT', 'NOT ANDROID'),
            'KIVY_HOME': os.environ.get('KIVY_HOME', 'DEFAULT'),
        }
        
        for var, value in env_vars.items():
            self.checkpoint(f"ENV: {var}", "OK", value[:50])
        
        # Check important paths
        paths = {
            'Current Dir': os.getcwd(),
            'Downloads Dir': os.path.abspath("downloads"),
            'Assets Dir': os.path.abspath("assets"),
            'Home Dir': os.path.expanduser("~"),
        }
        
        for path_name, path_value in paths.items():
            exists = "✓" if os.path.exists(path_value) else "✗"
            writable = "W" if os.access(path_value, os.W_OK) else "-"
            self.checkpoint(f"PATH: {path_name}", "OK", f"{path_value} [{exists}{writable}]")
    
    def import_check(self):
        """Check critical imports."""
        self.section("IMPORT CHECKS")
        
        imports = {
            'kivy': 'from kivy import __version__',
            'kivymd': 'from kivymd import __version__',
            'cryptography': 'from cryptography.fernet import Fernet',
            'sqlite3': 'import sqlite3',
            'threading': 'import threading',
            'json': 'import json',
            'socket': 'import socket',
        }
        
        for module_name, import_stmt in imports.items():
            try:
                exec(import_stmt)
                self.checkpoint(f"IMPORT: {module_name}", "OK", "Available")
            except ImportError as e:
                self.checkpoint(f"IMPORT: {module_name}", "ERROR", str(e))
            except Exception as e:
                self.checkpoint(f"IMPORT: {module_name}", "WARNING", f"Unexpected: {e}")
    
    def storage_check(self):
        """Check storage initialization."""
        self.section("STORAGE CHECKS")
        
        # Check config file path
        config_path = "settings.json"
        try:
            # Try to create it
            if not os.path.exists(config_path):
                with open(config_path, 'w') as f:
                    f.write('{"test": true}')
                self.checkpoint("CONFIG: Write", "OK", f"Created {config_path}")
            else:
                self.checkpoint("CONFIG: Exists", "OK", config_path)
            
            # Try to read it
            with open(config_path, 'r') as f:
                content = f.read()
            self.checkpoint("CONFIG: Read", "OK", "File readable")
        except IOError as e:
            self.checkpoint("CONFIG: IO Error", "ERROR", str(e))
        except Exception as e:
            self.checkpoint("CONFIG: Error", "ERROR", str(e))
        
        # Check database paths
        db_paths = ["ghostnet.db", "secret.key"]
        for db_file in db_paths:
            if os.path.exists(db_file):
                size = os.path.getsize(db_file)
                self.checkpoint(f"DB: {db_file}", "OK", f"Exists ({size} bytes)")
            else:
                self.checkpoint(f"DB: {db_file}", "OK", "Will be created")
    
    def directory_check(self):
        """Check directory creation and permissions."""
        self.section("DIRECTORY CHECKS")
        
        dirs_to_check = [
            "downloads",
            "assets",
            "assets/locales",
        ]
        
        for dir_path in dirs_to_check:
            try:
                os.makedirs(dir_path, exist_ok=True)
                writable = os.access(dir_path, os.W_OK)
                status = "OK" if writable else "WARNING"
                self.checkpoint(f"DIR: {dir_path}", status, 
                              f"Created/Exists, Writable: {writable}")
            except OSError as e:
                self.checkpoint(f"DIR: {dir_path}", "ERROR", str(e))
            except Exception as e:
                self.checkpoint(f"DIR: {dir_path}", "ERROR", f"Unexpected: {e}")
    
    def network_check(self):
        """Check network port availability."""
        self.section("NETWORK CHECKS")
        
        import socket
        
        ports = [
            (37020, "UDP Discovery"),
            (37021, "TCP Messaging"),
        ]
        
        for port, desc in ports:
            try:
                # Try UDP
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('', port))
                sock.close()
                self.checkpoint(f"NETWORK: Port {port} ({desc})", "OK", "Available")
            except OSError as e:
                self.checkpoint(f"NETWORK: Port {port} ({desc})", "WARNING", str(e))
            except Exception as e:
                self.checkpoint(f"NETWORK: Port {port} ({desc})", "ERROR", str(e))
    
    def threading_check(self):
        """Check threading functionality."""
        self.section("THREADING CHECKS")
        
        # Check current thread
        self.checkpoint("THREAD: Current", "OK", threading.current_thread().name)
        
        # Check daemon threads
        daemon_count = sum(1 for t in threading.enumerate() if t.daemon)
        self.checkpoint("THREAD: Daemon Threads", "OK", f"Count: {daemon_count}")
        
        # Test thread creation
        test_completed = []
        
        def test_worker():
            test_completed.append(True)
        
        try:
            test_thread = threading.Thread(target=test_worker, daemon=True)
            test_thread.start()
            test_thread.join(timeout=2.0)
            
            if test_completed:
                self.checkpoint("THREAD: Creation Test", "OK", "Thread executed successfully")
            else:
                self.checkpoint("THREAD: Creation Test", "WARNING", "Thread did not complete")
        except Exception as e:
            self.checkpoint("THREAD: Creation Test", "ERROR", str(e))
    
    def summary(self):
        """Print summary of diagnostics."""
        self.section("SUMMARY")
        
        errors = [c for c in self.checkpoints if c['status'] == 'ERROR']
        warnings = [c for c in self.checkpoints if c['status'] == 'WARNING']
        criticals = [c for c in self.checkpoints if c['status'] == 'CRITICAL']
        
        total = len(self.checkpoints)
        passed = total - len(errors) - len(warnings) - len(criticals)
        
        summary_text = f"""
Total Checkpoints: {total}
Passed: {passed}
Warnings: {len(warnings)}
Errors: {len(errors)}
Critical: {len(criticals)}

Crash Risk Level: {'🔴 CRITICAL' if criticals else '🟠 HIGH' if errors else '🟡 MEDIUM' if warnings else '✅ LOW'}
"""
        
        print(summary_text)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(summary_text)
        
        if criticals:
            print("\n🔴 CRITICAL ISSUES:")
            for c in criticals:
                print(f"  - {c['checkpoint']}: {c['details']}")
        
        if errors:
            print("\n✗ ERRORS:")
            for e in errors:
                print(f"  - {e['checkpoint']}: {e['details']}")
        
        if warnings:
            print("\n⚠ WARNINGS:")
            for w in warnings:
                print(f"  - {w['checkpoint']}: {w['details']}")
        
        print(f"\n📋 Full log: {self.log_file}")
    
    def run_full_diagnostic(self):
        """Run complete diagnostic suite."""
        try:
            self.environment_check()
            self.import_check()
            self.storage_check()
            self.directory_check()
            self.network_check()
            self.threading_check()
            self.summary()
        except Exception as e:
            self.exception("run_full_diagnostic", e)


# Global instance
_diagnostics = None

def get_diagnostics():
    """Get the global diagnostics instance."""
    global _diagnostics
    if _diagnostics is None:
        _diagnostics = CrashDiagnostics()
    return _diagnostics


# CLI interface
if __name__ == "__main__":
    diag = get_diagnostics()
    diag.run_full_diagnostic()
