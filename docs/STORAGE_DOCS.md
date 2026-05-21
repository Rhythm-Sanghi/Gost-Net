# Ghost Net - Encrypted Storage Documentation

## 🔒 Persistent Encrypted Storage Feature

Ghost Net now includes **encrypted persistent storage** using SQLite with Fernet encryption. All chat history and file records are stored locally and encrypted at rest, ensuring privacy even if someone accesses the raw database file.

---

## 📋 Overview

### Key Features

- ✅ **SQLite Database** - Lightweight, file-based storage
- ✅ **Fernet Encryption** - AES-128 + HMAC-SHA256 for message content
- ✅ **Automatic Key Management** - Generates and stores encryption key securely
- ✅ **Thread-Safe** - Database locks prevent race conditions
- ✅ **Chat History** - Load previous conversations when opening a peer
- ✅ **File Records** - Track sent and received files with paths
- ✅ **Privacy Mode** - Auto-delete messages older than 24 hours
- ✅ **Export Feature** - Export chats to readable text files

---

## 🏗️ Architecture

### Database Schema

#### **peers** Table
```sql
CREATE TABLE peers (
    ip_address TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    last_seen REAL NOT NULL
);
```

| Column | Type | Description |
|--------|------|-------------|
| `ip_address` | TEXT | Peer's IP (Primary Key) |
| `username` | TEXT | Peer's display name |
| `last_seen` | REAL | Unix timestamp of last beacon |

#### **messages** Table
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_ip TEXT NOT NULL,
    sender TEXT NOT NULL,
    content BLOB NOT NULL,
    message_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    file_path TEXT,
    FOREIGN KEY (peer_ip) REFERENCES peers(ip_address)
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment message ID |
| `peer_ip` | TEXT | IP of peer (Foreign Key) |
| `sender` | TEXT | "ME" or "PEER" |
| `content` | BLOB | **Encrypted** message content |
| `message_type` | TEXT | "TEXT" or "FILE" |
| `timestamp` | REAL | Unix timestamp |
| `file_path` | TEXT | Path to file (for FILE type) |

### Encryption Flow

```
┌─────────────────┐                    ┌──────────────────┐
│  Plain Message  │                    │  Encrypted BLOB  │
│  "Hello World"  │                    │  gAAAABh9k3j...  │
└────────┬────────┘                    └────────▲─────────┘
         │                                      │
         │ 1. Fernet Encrypt                   │ 3. Store
         ├──────────────────────────────────────┤
         │                                      │
         │      2. Base64 Encode                │
         │                                      │
┌────────▼────────┐                    ┌────────┴─────────┐
│  Encryption Key │──────────────────>│   SQLite DB      │
│   (secret.key)  │   Uses Key         │  (ghostnet.db)   │
└─────────────────┘                    └──────────────────┘
```

---

## 📦 Implementation ([`storage.py`](storage.py))

### DatabaseManager Class

#### Initialization

```python
from storage import DatabaseManager

# Default paths
db = DatabaseManager()  # Uses ghostnet.db and secret.key

# Custom paths
db = DatabaseManager(
    db_path="custom.db",
    key_path="custom.key"
)
```

#### Key Methods

##### **`save_message(peer_ip, sender, content, message_type, file_path, timestamp)`**

Save a message to the database (encrypts content automatically).

```python
db.save_message(
    peer_ip="192.168.1.100",
    sender="ME",
    content="Hello, Ghost Net!",
    message_type="TEXT",
    file_path=None,
    timestamp=time.time()
)
```

##### **`get_history(peer_ip, limit=100)`**

Retrieve chat history with a peer (decrypts automatically).

```python
messages = db.get_history("192.168.1.100", limit=50)

for msg in messages:
    print(f"{msg['sender']}: {msg['content']} ({msg['message_type']})")
```

Returns:
```python
[
    {
        'id': 1,
        'sender': 'ME',
        'content': 'Hello!',  # Decrypted
        'message_type': 'TEXT',
        'timestamp': 1706310000.0,
        'file_path': None
    },
    ...
]
```

##### **`save_peer(ip_address, username, last_seen)`**

Save or update peer information.

```python
db.save_peer("192.168.1.100", "Alice", time.time())
```

##### **`cleanup_old_messages(hours=24)`**

Delete messages older than specified hours (privacy feature).

```python
deleted = db.cleanup_old_messages(hours=24)
print(f"Deleted {deleted} old messages")
```

##### **`export_chat(peer_ip, output_path)`**

Export chat history to a readable text file.

```python
db.export_chat("192.168.1.100", "alice_chat.txt")
```

Output format:
```
Ghost Net Chat History
Peer: Alice (192.168.1.100)
Exported: 2026-01-27 05:23:45
============================================================

[2026-01-27 05:20:00] You: Hello Alice!

[2026-01-27 05:20:15] Alice: Hi there!

[2026-01-27 05:21:00] You: [FILE] photo.jpg
    Path: /downloads/photo.jpg
```

---

## 🔧 Integration

### Network Layer ([`network.py`](network.py))

The `GhostEngine` automatically saves all messages and files to the database.

```python
# Initialization with storage enabled (default)
engine = GhostEngine(
    username="TestUser",
    enable_storage=True  # Enable persistent storage
)

# Disable storage (RAM only)
engine = GhostEngine(
    username="TestUser",
    enable_storage=False
)
```

**Automatic Saving:**
- ✅ Sent messages saved when `send_message()` succeeds
- ✅ Received messages saved in `_handle_text_message()`
- ✅ Sent files saved when `send_file()` completes
- ✅ Received files saved in `_handle_file_transfer()`
- ✅ Peers saved/updated on every beacon received

### UI Layer ([`main.py`](main.py))

The `ChatScreen` automatically loads history when opening a peer.

```python
def set_peer(self, peer_ip, peer_name):
    """Set the current chat peer and load history."""
    self.peer_ip = peer_ip
    self.peer_name = peer_name
    
    # Clear current messages
    self.messages_list.clear_widgets()
    
    # Load history from database
    self.load_history()  # Loads last 100 messages
```

**Auto-Cleanup on Startup:**
```python
def on_start(self):
    # Privacy feature: Delete messages > 24 hours old
    self.cleanup_old_messages(hours=24)
```

---

## 🔐 Security

### Encryption Details

**Algorithm:** Fernet (Symmetric Encryption)
- **Cipher:** AES-128-CBC
- **Authentication:** HMAC-SHA256
- **Key Size:** 32 bytes (256 bits)
- **Encoding:** Base64 URL-safe

**Key Storage:**
- Stored in `secret.key` file
- File permissions set to `0o600` (owner read/write only)
- Generated once on first app launch
- Reused for all subsequent encryptions

### What's Encrypted

✅ **Message Content** (`content` column in `messages` table)
- Text messages
- File names

❌ **Not Encrypted** (Metadata)
- Peer IP addresses
- Usernames
- Timestamps
- Message types
- File paths

### Security Considerations

#### ⚠️ Limitations

1. **Single Key for All Messages**
   - Same key encrypts all content
   - Key compromise = full history exposed
   
2. **Key Stored Plaintext**
   - `secret.key` not password-protected
   - Anyone with file access can decrypt

3. **Metadata Leakage**
   - Who you talked to (IPs, usernames)
   - When messages were sent
   - Message/file counts

#### ✅ Mitigations

1. **Filesystem Permissions**
   ```python
   os.chmod(self.key_path, 0o600)  # Owner only
   ```

2. **Android Scoped Storage**
   - Database stored in app-private directory
   - `/data/data/org.ghostnet.ghostnet/`
   - Only accessible by the app

3. **Auto-Cleanup**
   - Messages auto-deleted after 24 hours
   - Configurable retention period

#### 🔒 Future Enhancements

1. **Password-Protected Key**
   ```python
   # Derive key from user password
   key = PBKDF2(password, salt, iterations=100000)
   ```

2. **Per-Peer Keys**
   ```python
   # Different key for each peer
   peer_keys = {
       "192.168.1.100": key1,
       "192.168.1.101": key2
   }
   ```

3. **Encrypted Metadata**
   ```python
   # Store encrypted usernames/IPs
   encrypted_username = cipher.encrypt(username)
   ```

---

## 🧪 Testing

### Desktop Testing

```bash
# Test the database manager
python storage.py

# Expected output:
# === Ghost Net Database Manager Test ===
# [DatabaseManager] Generated new encryption key: test_secret.key
# [DatabaseManager] Initialized with database: test_ghostnet.db
# ...
# Total messages: 5
# Total peers: 2
```

### Integration Testing

```python
# Terminal 1
python main.py

# Terminal 2
python main.py

# 1. Send messages between instances
# 2. Close both apps
# 3. Restart both apps
# 4. Open chat with peer
# 5. Verify history loads automatically
```

### Verify Encryption

```bash
# Try to read the database directly
sqlite3 ghostnet.db

# Query messages
SELECT * FROM messages;

# Content column should show encrypted blob:
# gAAAABh9k3j2kF8vN... (NOT readable text)
```

### Test Privacy Cleanup

```python
# Modify cleanup hours in main.py
self.cleanup_old_messages(hours=0.001)  # ~4 seconds

# Send messages
# Wait 5 seconds
# Restart app
# Messages should be deleted
```

---

## 📊 Performance

### Database Size

| Data | Size | 1000 Messages |
|------|------|---------------|
| **Text Message** | ~200 bytes | ~200 KB |
| **File Record** | ~250 bytes | ~250 KB |
| **Peer Entry** | ~100 bytes | - |
| **Indexes** | Varies | ~50 KB |

**Estimated Total:** 1000 messages ≈ 500 KB

### Query Performance

| Operation | Time | Notes |
|-----------|------|-------|
| **Save Message** | < 1ms | Background thread |
| **Load History (100)** | 5-10ms | With decryption |
| **Cleanup Old** | 10-50ms | Depends on count |
| **Export Chat** | 50-200ms | File I/O bound |

### Thread Safety

✅ **All database operations use locks:**
```python
with self.db_lock:
    # Thread-safe database access
```

✅ **Background saving prevents UI lag:**
```python
threading.Thread(
    target=self.db_manager.save_message,
    args=(...),
    daemon=True
).start()
```

---

## 🛠️ Configuration

### Retention Policy

**Default:** 24 hours

**Change globally** in [`main.py`](main.py):
```python
def on_start(self):
    # Change to 7 days
    self.cleanup_old_messages(hours=168)
    
    # Or disable cleanup
    # self.cleanup_old_messages(hours=99999)
```

### Database Location

**Default:** `./ghostnet.db` and `./secret.key` in project root

**Custom location:**
```python
from storage import DatabaseManager

# User-specific location
import os
db_path = os.path.expanduser("~/.ghostnet/data.db")
key_path = os.path.expanduser("~/.ghostnet/secret.key")

db = DatabaseManager(db_path=db_path, key_path=key_path)

engine = GhostEngine(
    username="User",
    db_manager=db  # Use custom database
)
```

### History Limit

**Default:** 100 messages per peer

**Change in [`main.py`](main.py):**
```python
def load_history(self):
    # Load last 500 messages
    messages = app.engine.db_manager.get_history(self.peer_ip, limit=500)
```

---

## 🐛 Troubleshooting

### Issue: "No database manager available"

**Symptoms:** History doesn't load, messages not saved

**Causes:**
1. Storage module not imported
2. `enable_storage=False` in GhostEngine
3. `storage.py` file missing

**Solutions:**
```python
# Verify storage is enabled
engine = GhostEngine(username="User", enable_storage=True)

# Check if module loaded
from network import STORAGE_AVAILABLE
print(f"Storage available: {STORAGE_AVAILABLE}")
```

### Issue: "Decryption error"

**Symptoms:** History shows "[Decryption Failed]"

**Causes:**
1. `secret.key` file changed or deleted
2. Database created with different key
3. Corrupted database file

**Solutions:**
1. Delete `secret.key` and `ghostnet.db` (loses all history)
2. Restore backup of `secret.key`
3. Export chat before key rotation

### Issue: Database locked

**Symptoms:** "database is locked" error

**Causes:**
- Multiple processes accessing same database
- Long-running transaction

**Solutions:**
```python
# Use separate database per instance
db1 = DatabaseManager(db_path="instance1.db")
db2 = DatabaseManager(db_path="instance2.db")

# Or enable WAL mode (Write-Ahead Logging)
conn = sqlite3.connect("ghostnet.db")
conn.execute("PRAGMA journal_mode=WAL")
```

### Issue: Large database file

**Symptoms:** `ghostnet.db` file is very large

**Solutions:**
```python
# 1. Reduce retention period
cleanup_old_messages(hours=1)  # Keep only 1 hour

# 2. Manually delete history
db.delete_peer_history("192.168.1.100")

# 3. Vacuum database (reclaim space)
db.vacuum_database()
```

---

## 📝 Usage Examples

### Example 1: Custom Retention Policy

```python
# Different retention for different scenarios

# Development: Keep everything
self.cleanup_old_messages(hours=99999)

# Normal use: 24 hours
self.cleanup_old_messages(hours=24)

# High security: 1 hour
self.cleanup_old_messages(hours=1)

# Extreme privacy: 5 minutes
self.cleanup_old_messages(hours=0.083)
```

### Example 2: Export All Chats

```python
from storage import DatabaseManager

db = DatabaseManager()

# Get all known peers
peers = db.get_all_peers()

# Export each chat
for peer in peers:
    output_file = f"export_{peer['username']}.txt"
    db.export_chat(peer['ip_address'], output_file)
    print(f"Exported chat with {peer['username']}")
```

### Example 3: Search Messages

```python
def search_messages(db, keyword):
    """Search for keyword in all messages."""
    # Get all peers
    peers = db.get_all_peers()
    
    results = []
    for peer in peers:
        messages = db.get_history(peer['ip_address'], limit=1000)
        for msg in messages:
            if keyword.lower() in msg['content'].lower():
                results.append({
                    'peer': peer['username'],
                    'content': msg['content'],
                    'timestamp': msg['timestamp']
                })
    
    return results

# Usage
results = search_messages(db, "important")
print(f"Found {len(results)} messages containing 'important'")
```

### Example 4: Statistics Dashboard

```python
from storage import DatabaseManager
from datetime import datetime

db = DatabaseManager()
stats = db.get_statistics()

print("=== Ghost Net Statistics ===")
print(f"Total Messages: {stats['total_messages']}")
print(f"Total Peers: {stats['total_peers']}")

if stats['oldest_message']:
    oldest = datetime.fromtimestamp(stats['oldest_message'])
    print(f"Oldest Message: {oldest.strftime('%Y-%m-%d %H:%M:%S')}")

if stats['newest_message']:
    newest = datetime.fromtimestamp(stats['newest_message'])
    print(f"Newest Message: {newest.strftime('%Y-%m-%d %H:%M:%S')}")
```

---

## 🔄 Migration & Backup

### Backup Database

```bash
# Simple file copy
cp ghostnet.db ghostnet_backup.db
cp secret.key secret_backup.key

# Timestamped backup
cp ghostnet.db "ghostnet_backup_$(date +%Y%m%d).db"
```

### Restore Backup

```bash
# Restore database
cp ghostnet_backup.db ghostnet.db
cp secret_backup.key secret.key

# Restart app
python main.py
```

### Export/Import

```python
# Export all chats
peers = db.get_all_peers()
for peer in peers:
    db.export_chat(peer['ip_address'], f"backup_{peer['username']}.txt")

# Import not directly supported - would need custom parser
```

---

## ✅ Feature Checklist

### Implemented
- [x] SQLite database with encryption
- [x] Automatic message/file storage
- [x] Chat history loading on peer selection
- [x] Privacy cleanup (24-hour retention)
- [x] Thread-safe database operations
- [x] Export chat to text file
- [x] Database statistics
- [x] Peer tracking

### Future Enhancements
- [ ] Password-protected encryption key
- [ ] Per-peer encryption keys
- [ ] Full-text search across messages
- [ ] Message sync between devices
- [ ] Cloud backup (encrypted)
- [ ] Message deletion confirmation
- [ ] Starred/bookmarked messages
- [ ] Database compression
- [ ] Import/export in JSON format

---

## 📚 API Reference

### DatabaseManager Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `__init__` | `db_path, key_path` | `DatabaseManager` | Initialize database |
| `save_message` | `peer_ip, sender, content, message_type, file_path, timestamp` | `None` | Save encrypted message |
| `get_history` | `peer_ip, limit` | `List[Dict]` | Get decrypted history |
| `save_peer` | `ip_address, username, last_seen` | `None` | Save/update peer |
| `get_peer_username` | `ip_address` | `str` | Get peer username |
| `get_all_peers` | None | `List[Dict]` | Get all known peers |
| `cleanup_old_messages` | `hours` | `int` | Delete old messages, return count |
| `delete_peer_history` | `peer_ip` | `int` | Delete all messages with peer |
| `get_statistics` | None | `Dict` | Get database stats |
| `export_chat` | `peer_ip, output_path` | `bool` | Export chat to file |
| `vacuum_database` | None | `None` | Optimize database |

---

**Encrypted Storage Complete! 🎉**

Ghost Net now provides secure, persistent storage with automatic history loading and privacy-focused cleanup features.
