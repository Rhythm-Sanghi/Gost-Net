import platform
import threading
import time
from kivy.clock import Clock


class GPSManager:
    def __init__(self):
        self.latitude = 22.7196
        self.longitude = 75.8577
        self.accuracy = 0.0
        self.is_started = False
        self.gps = None
        self.on_location_update = None
        self._setup_gps()
    
    def _setup_gps(self):
        if platform.system() == 'Android':
            self._setup_android_gps()
        else:
            self._setup_desktop_gps()
    
    def _setup_android_gps(self):
        try:
            from plyer import gps
            self.gps = gps
            print("[GPSManager] Android GPS initialized")
        except ImportError:
            print("[GPSManager] plyer.gps not available, using mock")
            self.gps = None
    
    def _setup_desktop_gps(self):
        self.gps = None
        print("[GPSManager] Desktop mock GPS initialized")
    
    def start(self):
        if self.is_started:
            print("[GPSManager] GPS already started")
            return False
        
        if platform.system() == 'Android':
            return self._start_android_gps()
        else:
            return self._start_desktop_gps()
    
    def _start_android_gps(self):
        try:
            if not self.gps:
                print("[GPSManager] GPS not available")
                return False
            
            self.gps.configure(
                on_location=self._on_gps_location,
                on_status=self._on_gps_status
            )
            self.gps.start(minTime=1000, minDistance=0)
            self.is_started = True
            print("[GPSManager] Android GPS started")
            return True
        
        except Exception as e:
            print(f"[GPSManager] Android GPS start error: {e}")
            return False
    
    def _start_desktop_gps(self):
        self.is_started = True
        print("[GPSManager] Desktop GPS mock started")
        
        def mock_gps_loop():
            import random
            while self.is_started:
                self.latitude = 22.7196 + random.uniform(-0.01, 0.01)
                self.longitude = 75.8577 + random.uniform(-0.01, 0.01)
                self.accuracy = random.uniform(5, 15)
                
                if self.on_location_update:
                    Clock.schedule_once(
                        lambda dt: self.on_location_update(
                            self.latitude,
                            self.longitude,
                            self.accuracy
                        ),
                        0
                    )
                
                time.sleep(2)
        
        threading.Thread(target=mock_gps_loop, daemon=True).start()
        return True
    
    def _on_gps_location(self, **kwargs):
        try:
            self.latitude = kwargs.get('lat', self.latitude)
            self.longitude = kwargs.get('lon', self.longitude)
            self.accuracy = kwargs.get('accuracy', 0.0)
            
            if self.on_location_update:
                Clock.schedule_once(
                    lambda dt: self.on_location_update(
                        self.latitude,
                        self.longitude,
                        self.accuracy
                    ),
                    0
                )
        
        except Exception as e:
            print(f"[GPSManager] Location callback error: {e}")
    
    def _on_gps_status(self, status_type, status_message):
        print(f"[GPSManager] GPS status: {status_type} - {status_message}")
    
    def stop(self):
        if not self.is_started:
            return
        
        if platform.system() == 'Android':
            self._stop_android_gps()
        else:
            self._stop_desktop_gps()
        
        self.is_started = False
    
    def _stop_android_gps(self):
        try:
            if self.gps:
                self.gps.stop()
            print("[GPSManager] Android GPS stopped")
        except Exception as e:
            print(f"[GPSManager] Android GPS stop error: {e}")
    
    def _stop_desktop_gps(self):
        print("[GPSManager] Desktop GPS mock stopped")
    
    def get_location(self):
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'accuracy': self.accuracy
        }
    
    def get_coordinates(self):
        return (self.latitude, self.longitude)
    
    def cleanup(self):
        self.stop()
        print("[GPSManager] Cleaned up")


_gps_manager_instance = None

def get_gps_manager():
    global _gps_manager_instance
    if _gps_manager_instance is None:
        _gps_manager_instance = GPSManager()
    return _gps_manager_instance
