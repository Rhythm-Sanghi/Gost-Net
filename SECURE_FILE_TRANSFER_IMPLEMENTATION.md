# Secure File & Media Transfer Pipeline - Implementation Summary

## Overview
Implemented end-to-end encrypted file chunking with AES-GCM, native file picker integration, and real-time progress tracking for Ghost Net P2P messaging.

---

## 1. Network Engine Updates (`network.py`)

### Constants Added
```python
CHUNK_SIZE = 8192              # 8KB chunks for encrypted transfer
CHUNK_DELIMITER = b"<CHUNK_END>"  # Chunk boundary marker
```

### Enhanced File Header Protocol (JSON)
```json
{
  "type": "FILE",
  "filename": "document.pdf",
  "filesize": 1048576,
  "file_id": "unique_hash",
  "checksum": "sha256_hash",
  "chunked": true,
  "timestamp": "2026-03-09T17:50:00"
}
```

### Key Methods Implemented

#### `send_file(target_ip, file_path, progress_callback, use_chunking=True)`
- **Background Thread**: Runs file transfer without blocking UI
- **Encrypted Chunking**: 
  - Reads file in 8KB chunks
  - Encrypts each chunk with AES-GCM (unique nonce per chunk)
  - Sends chunk header (12-byte nonce + 4-byte size) followed by encrypted data
- **Progress Tracking**: Calls `progress_callback(bytes_sent, total_size)` for real-time updates
- **Fallback**: If crypto unavailable, falls back to unencrypted chunking
- **Checksum**: SHA256 verification on receiver side

#### `_handle_chunked_file_transfer(filepath, filesize, initial_bytes, initial_data, conn, sender_ip, filename, checksum)`
- **On-the-fly Decryption**: Decrypts chunks as they arrive
- **Stream Writing**: Writes directly to file stream (memory-efficient)
- **Nonce Extraction**: Extracts nonce from chunk header for AES-GCM decryption
- **Progress Logging**: Outputs transfer progress every 80KB (10 * CHUNK_SIZE)
- **Checksum Validation**: Verifies file integrity after reception

#### `_handle_file_transfer(sender_ip, header, initial_data, conn)`
- **Protocol Detection**: Routes to chunked or legacy handler based on header
- **File Safety**: Sanitizes filenames and prevents path traversal
- **Duplicate Handling**: Appends numeric suffix if file exists

---

## 2. File Picker Integration (`android_mocks.py`)

### MockFilePicker Class
```python
class MockFilePicker:
    @staticmethod
    def pick_file(filters=None):  # Single file selection
    @staticmethod
    def pick_multiple_files(filters=None)  # Multi-file selection
```

### Features
- **Plyer Integration**: Uses `plyer.filechooser` on Android
- **Desktop Fallback**: Uses `tkinter.filedialog` on desktop
- **Graceful Degradation**: Returns None/[] if picker unavailable
- **Filter Support**: Customizable file type filters

### Factory Function
```python
def get_file_picker():
    if _is_android:
        try:
            from plyer import filechooser
            return filechooser
        except ImportError:
            return MockFilePicker()
    return MockFilePicker()
```

---

## 3. UI Enhancements (`main.py`)

### FileBubble Widget
Enhanced with progress tracking:

#### Constructor Changes
- Added `self.progress_bar` (MDProgressBar) 
- Added `self.minimum_height = dp(120)` to accommodate progress bar
- Progress bar appears between file info and action buttons

#### New Method: `update_progress(bytes_sent, total_size)`
```python
def update_progress(self, bytes_sent, total_size):
    """Update progress bar (thread-safe via Clock)."""
    if not self.progress_bar or total_size == 0:
        return
    
    progress_percent = (bytes_sent / total_size) * 100
    Clock.schedule_once(
        lambda dt: setattr(self.progress_bar, 'value', progress_percent),
        0
    )
```

**Thread Safety**: Uses `Clock.schedule_once()` to ensure UI updates on main thread

### ChatScreen Enhancements

#### File Selection Flow
1. User taps attachment button → `open_file_picker()`
2. Native picker (plyer) or MDFileManager shown
3. Selected file → `select_file(path)`
4. FileBubble created with progress bar
5. Progress callback passed to `send_file()`

#### Updated Methods

**`open_file_picker()`**
- Tries native plyer picker first on Android
- Falls back to MDFileManager if unavailable
- Cross-platform file browsing (Windows, macOS, Linux, Android)

**`select_file(path)`**
- Creates FileBubble immediately (optimistic UI)
- Defines progress callback that updates bubble
- Calls `engine.send_file()` with callback
- Auto-scrolls to newly added file bubble

**`add_received_file(sender_ip, filename, filepath, timestamp)`**
- Stores FileBubble reference in `self.received_file_bubbles[filepath]`
- Enables progress updates for incoming transfers

**`update_received_file_progress(filepath, bytes_received, total_size)`**
- Called from network thread via Clock scheduler
- Updates progress bar safely

### Initialization
```python
def __init__(self, **kwargs):
    ...
    self.received_file_bubbles = {}  # Track incoming file bubbles
```

---

## 4. Encryption Details

### AES-GCM Chunk Encryption
From `security.py`:
```python
def encrypt_file_chunk(self, peer_id: str, chunk: bytes) -> Optional[Tuple[bytes, bytes]]:
    """Encrypts file chunk with unique nonce."""
    nonce = os.urandom(12)  # 96-bit nonce (12 bytes)
    cipher = AESGCM(aes_key)
    ciphertext = cipher.encrypt(nonce, chunk, None)
    return (nonce, ciphertext)

def decrypt_file_chunk(self, peer_id: str, nonce: bytes, chunk: bytes) -> Optional[bytes]:
    """Decrypts with peer's AES key."""
    cipher = AESGCM(aes_key)
    plaintext = cipher.decrypt(nonce, chunk, None)
    return plaintext
```

### Chunk Structure
```
┌─────────────────────────────────────┐
│ Chunk Header (16 bytes)             │
├──────────────┬──────────────────────┤
│ Nonce (12B)  │ Size (4B, big-endian)│
├──────────────┴──────────────────────┤
│ Encrypted Payload (variable)        │
└─────────────────────────────────────┘
```

---

## 5. Thread Safety & Performance

### UI Updates (Main Thread)
- All progress bar updates use `Clock.schedule_once()`
- No blocking operations on Kivy thread
- File picker runs in separate thread on desktop

### File I/O (Background Thread)
- Send: `send_file()` spawns daemon thread `_send_file_worker()`
- Receive: Handled in `_handle_file_transfer()` (already in daemon thread)
- Encryption/decryption runs on background threads
- Checksum calculation on background thread

### Locks
- `CryptoManager.keys_lock`: Protects peer key dictionary
- `GhostEngine.peers_lock`: Protects peer list
- No locks needed for FileBubble (UI-only, single-threaded access)

---

## 6. Error Handling

### Send Path
- File not found validation
- File size limit check (100MB max)
- Socket timeout (30 seconds for large files)
- Exception logging without app crash
- Graceful fallback if crypto unavailable

### Receive Path
- Header validation and deserialization
- File existence check with suffix numbering
- Checksum mismatch detection → file cleanup
- Incomplete transfer detection
- Graceful exception handling per connection

### File Picker
- Try plyer → fallback to tkinter → fallback to MDFileManager
- Non-blocking error recovery
- User-friendly error messages

---

## 7. Protocol Compatibility

### Legacy Support
- Existing TCP text/file protocol unmodified
- Chunked flag in header allows backward compatibility
- Receiver auto-detects chunked vs. legacy transfer

### Header Detection
```python
if header.get("chunked", False):
    self._handle_chunked_file_transfer(...)
else:
    # Legacy handler for non-chunked transfers
    with open(filepath, 'wb') as f:
        f.write(initial_data)
        # Stream remaining data...
```

---

## 8. Testing Recommendations

### Unit Tests
- Chunk encryption/decryption round-trip
- File picker with various filters
- Progress callback invocation timing
- Checksum validation

### Integration Tests
- Small file transfer (< 100KB)
- Large file transfer (50MB+)
- Network interruption recovery
- Progress accuracy (bytes sent vs. actual)
- Cross-platform file picker

### Performance Tests
- Encryption throughput (MB/s)
- Memory usage during 100MB transfer
- UI responsiveness (no jank during transfer)
- Battery impact (background thread CPU)

---

## 9. Configuration & Deployment

### No Configuration Required
- Uses default constants from `GhostEngine` class
- File picker adapter automatically detects platform
- Crypto manager auto-initializes if available

### Dependencies
- cryptography (AES-GCM, HKDF, EC)
- kivy/kivymd (UI)
- plyer (optional, Android file picker)
- tkinter (optional, desktop fallback)

### Build Considerations
- `buildozer.spec`: Include `plyer` in requirements.txt for Android
- APK will include both plyer and tkinter fallbacks

---

## 10. Code Quality

### No Comments in Implementation
Per project rules, all code is self-documenting with:
- Descriptive function/method names
- Type hints on all parameters
- Docstrings explaining purpose
- Clear variable naming

### Thread Safety Compliance
- All file operations on background threads
- All UI updates via `Clock.schedule_once()`
- No blocking waits on UI thread
- Proper exception handling

### Security
- AES-GCM authenticated encryption
- Unique nonce per chunk (prevents replay)
- SHA256 checksum verification
- ECDH key exchange (via `CryptoManager`)
- Path traversal prevention (`_sanitize_filename()`)

---

## 11. Future Enhancements

### Possible Extensions
- Resume interrupted transfers (chunk-based advantage)
- Bandwidth throttling control
- Batch file transfer UI
- Download folder management
- File preview thumbnails
- ZIP compression before transfer
- Deduplication (identify duplicate chunks)

### Known Limitations
- Single file at a time per peer (queue transfers)
- No folder recursive transfer
- Progress only updated every 80KB (for performance)
- No pause/resume mechanism

---

## Summary of Changes

| File | Changes |
|------|---------|
| `network.py` | Added CHUNK_SIZE constant, updated `send_file()` for AES-GCM chunking, added `_handle_chunked_file_transfer()`, enhanced `_handle_file_transfer()` with protocol detection |
| `android_mocks.py` | Added MockFilePicker class with desktop fallback, added `get_file_picker()` factory |
| `main.py` | Added MDProgressBar import, enhanced FileBubble with progress bar & `update_progress()`, updated ChatScreen file picker & selection, added `received_file_bubbles` tracking |
| `security.py` | No changes (already had `encrypt_file_chunk()` and `decrypt_file_chunk()`) |

Total implementations:
- **4 new methods** (network chunking, crypto helpers)
- **2 new classes** (MockFilePicker, enhanced FileBubble)
- **3 dialog/UI enhancements** (progress bar, file picker integration)
- **0 breaking changes** (fully backward compatible)

