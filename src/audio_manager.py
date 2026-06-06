import os
import shutil
import time
import threading
from pathlib import Path
from kivy.clock import Clock
try:
    from kivy.utils import platform as kivy_platform
    is_android = (kivy_platform == 'android')
except ImportError:
    is_android = False


class AudioManager:
    def __init__(self):
        self.is_recording = False
        self.is_playing = False
        self.current_recording_path = None
        self.current_playback_progress = 0.0
        self.on_recording_complete = None
        self.on_playback_progress = None
        self.on_playback_complete = None
        self._setup_recording_dir()
    
    def _setup_recording_dir(self):
        try:
            if is_android:
                from jnius import autoclass
                Context = autoclass('android.content.Context')
                PythonService = autoclass('org.kivy.android.PythonService')
                service = PythonService.mService
                cache_dir = service.getCacheDir().getAbsolutePath()
                self.recording_dir = cache_dir
            else:
                import tempfile
                self.recording_dir = tempfile.gettempdir()
            
            os.makedirs(self.recording_dir, exist_ok=True)
            print(f"[AudioManager] Recording directory: {self.recording_dir}")
        except Exception as e:
            print(f"[AudioManager] Setup error: {e}")
            import tempfile
            self.recording_dir = tempfile.gettempdir()
    
    def start_recording(self):
        if self.is_recording:
            print("[AudioManager] Already recording")
            return False
        
        timestamp = int(time.time() * 1000)
        self.current_recording_path = os.path.join(
            self.recording_dir,
            f"voice_msg_{timestamp}.m4a"
        )
        
        if is_android:
            return self._start_recording_android()
        else:
            return self._start_recording_desktop()
    
    def _start_recording_android(self):
        try:
            from jnius import autoclass, cast
            
            MediaRecorder = autoclass('android.media.MediaRecorder')
            AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
            OutputFormat = autoclass('android.media.MediaRecorder$OutputFormat')
            AudioEncoder = autoclass('android.media.MediaRecorder$AudioEncoder')
            
            self.recorder = MediaRecorder()
            self.recorder.setAudioSource(AudioSource.MIC)
            self.recorder.setOutputFormat(OutputFormat.MPEG_4)
            self.recorder.setAudioEncoder(AudioEncoder.AAC)
            self.recorder.setOutputFile(self.current_recording_path)
            self.recorder.setAudioSamplingRate(44100)
            self.recorder.setAudioEncodingBitRate(128000)
            
            self.recorder.prepare()
            self.recorder.start()
            
            self.is_recording = True
            print(f"[AudioManager] Recording started: {self.current_recording_path}")
            return True
        
        except Exception as e:
            print(f"[AudioManager] Android recording error: {e}")
            self.current_recording_path = None
            return False
    
    def _start_recording_desktop(self):
        try:
            dummy_file = self.current_recording_path
            with open(dummy_file, 'wb') as f:
                f.write(b'MOCK_AUDIO_DATA')
            
            self.is_recording = True
            print(f"[AudioManager] Mock recording started: {dummy_file}")
            return True
        
        except Exception as e:
            print(f"[AudioManager] Desktop recording error: {e}")
            self.current_recording_path = None
            return False
    
    def stop_recording(self):
        if not self.is_recording:
            print("[AudioManager] Not currently recording")
            return self.current_recording_path
        
        if is_android:
            return self._stop_recording_android()
        else:
            return self._stop_recording_desktop()
    
    def _stop_recording_android(self):
        try:
            if hasattr(self, 'recorder') and self.recorder:
                self.recorder.stop()
                self.recorder.release()
                del self.recorder
            
            self.is_recording = False
            recording_path = self.current_recording_path
            print(f"[AudioManager] Recording stopped: {recording_path}")
            
            if self.on_recording_complete:
                Clock.schedule_once(
                    lambda dt: self.on_recording_complete(recording_path),
                    0
                )
            
            return recording_path
        
        except Exception as e:
            print(f"[AudioManager] Android stop error: {e}")
            self.is_recording = False
            return self.current_recording_path
    
    def _stop_recording_desktop(self):
        self.is_recording = False
        recording_path = self.current_recording_path
        print(f"[AudioManager] Mock recording stopped: {recording_path}")
        
        if self.on_recording_complete:
            Clock.schedule_once(
                lambda dt: self.on_recording_complete(recording_path),
                0
            )
        
        return recording_path
    
    def play_audio(self, file_path):
        if self.is_playing:
            print("[AudioManager] Already playing audio")
            return False
        
        if not os.path.exists(file_path):
            print(f"[AudioManager] File not found: {file_path}")
            return False
        
        if is_android:
            return self._play_audio_android(file_path)
        else:
            return self._play_audio_desktop(file_path)
    
    def _play_audio_android(self, file_path):
        try:
            from jnius import autoclass
            
            MediaPlayer = autoclass('android.media.MediaPlayer')
            
            self.player = MediaPlayer()
            self.player.setDataSource(file_path)
            self.player.prepare()
            
            duration_ms = self.player.getDuration()
            self.is_playing = True
            
            print(f"[AudioManager] Playing: {file_path} (duration: {duration_ms}ms)")
            
            self.player.start()
            
            self._monitor_playback_android(duration_ms)
            
            return True
        
        except Exception as e:
            print(f"[AudioManager] Android playback error: {e}")
            return False
    
    def _monitor_playback_android(self, duration_ms):
        def monitor_worker():
            try:
                start_time = time.time()
                while self.is_playing and hasattr(self, 'player') and self.player:
                    if not self.player.isPlaying():
                        self.is_playing = False
                        if self.on_playback_complete:
                            Clock.schedule_once(
                                lambda dt: self.on_playback_complete(),
                                0
                            )
                        break
                    
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    progress = min((elapsed_ms / duration_ms) * 100, 100)
                    
                    if self.on_playback_progress:
                        Clock.schedule_once(
                            lambda dt, p=progress: self.on_playback_progress(p),
                            0
                        )
                    
                    time.sleep(0.1)
            
            except Exception as e:
                print(f"[AudioManager] Playback monitor error: {e}")
        
        threading.Thread(target=monitor_worker, daemon=True).start()
    
    def _play_audio_desktop(self, file_path=None):
        self.is_playing = True
        print("[AudioManager] Mock playback started")
        
        def mock_playback():
            for i in range(101):
                if not self.is_playing:
                    break
                if self.on_playback_progress:
                    Clock.schedule_once(
                        lambda dt, p=i: self.on_playback_progress(p),
                        0
                    )
                time.sleep(0.05)
            
            if self.is_playing:
                self.is_playing = False
                if self.on_playback_complete:
                    Clock.schedule_once(
                        lambda dt: self.on_playback_complete(),
                        0
                    )
        
        threading.Thread(target=mock_playback, daemon=True).start()
        return True
    
    def stop_playback(self):
        if not self.is_playing:
            return
        
        if is_android:
            try:
                if hasattr(self, 'player') and self.player:
                    self.player.stop()
                    self.player.release()
                    del self.player
            except Exception as e:
                print(f"[AudioManager] Android stop playback error: {e}")
        
        self.is_playing = False
        print("[AudioManager] Playback stopped")
    
    def cancel_recording(self):
        if not self.is_recording:
            return
        
        recording_path = self.stop_recording()
        
        if recording_path and os.path.exists(recording_path):
            try:
                from security import shred_file
                shred_file(recording_path)
                print(f"[AudioManager] Recording cancelled and shredded: {recording_path}")
            except Exception as e:
                print(f"[AudioManager] Error shredding cancelled recording: {e}")
        
        self.current_recording_path = None
    
    def cleanup(self):
        self.stop_recording()
        self.stop_playback()
        print("[AudioManager] Cleaned up")
    
    def shred_cache(self):
        try:
            from security import shred_file
            if os.path.exists(self.recording_dir):
                for filename in os.listdir(self.recording_dir):
                    if filename.endswith('.m4a'):
                        file_path = os.path.join(self.recording_dir, filename)
                        try:
                            shred_file(file_path)
                            print(f"[AudioManager] Shredded audio file: {file_path}")
                        except Exception as e:
                            print(f"[AudioManager] Error shredding {file_path}: {e}")
            
            print("[AudioManager] Cache shredding complete")
            return True
        except Exception as e:
            print(f"[AudioManager] Error during cache shredding: {e}")
            return False


_audio_manager_instance = None

def get_audio_manager():
    global _audio_manager_instance
    if _audio_manager_instance is None:
        _audio_manager_instance = AudioManager()
    return _audio_manager_instance
