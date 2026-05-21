import sqlite3
import os
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional


class PersistenceDatabase:

    def __init__(self, db_path: str = "ghostnet_persistence.db"):
        self.db_path = db_path
        self.db_lock = threading.Lock()
        self.initialization_error = None
        
        try:
            self._initialize_database()
        except Exception as e:
            self.initialization_error = f"Database initialization failed: {e}"
            print(f"[PersistenceDatabase] ERROR: {self.initialization_error}")
    
    def _initialize_database(self):
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                conn.execute('PRAGMA busy_timeout = 10000')
                cursor = conn.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS peers (
                        peer_id TEXT PRIMARY KEY,
                        device_name TEXT NOT NULL,
                        mac_address TEXT,
                        discovery_type TEXT,
                        last_seen REAL NOT NULL
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        peer_id TEXT NOT NULL,
                        sender_type TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        content BLOB NOT NULL,
                        timestamp REAL NOT NULL,
                        expires_at REAL,
                        FOREIGN KEY (peer_id) REFERENCES peers(peer_id)
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_messages_peer_timestamp
                    ON messages(peer_id, timestamp)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_messages_expires_at
                    ON messages(expires_at)
                ''')
                
                conn.commit()
                
                self._migrate_add_expires_at_column(conn, cursor)
                
                conn.close()
                
                print("[PersistenceDatabase] Database initialized successfully")
                
            except Exception as e:
                print(f"[PersistenceDatabase] Initialization error: {e}")
                raise
    
    def _migrate_add_expires_at_column(self, conn, cursor):
        try:
            cursor.execute("PRAGMA table_info(messages)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'expires_at' not in columns:
                cursor.execute('ALTER TABLE messages ADD COLUMN expires_at REAL')
                conn.commit()
                print("[PersistenceDatabase] Migration: Added expires_at column to messages table")
                
                try:
                    cursor.execute('''
                        CREATE INDEX IF NOT EXISTS idx_messages_expires_at
                        ON messages(expires_at)
                    ''')
                    conn.commit()
                except:
                    pass
        except Exception as e:
            print(f"[PersistenceDatabase] Migration error: {e}")
    
    def save_peer(self, peer_id: str, device_name: str, mac_address: Optional[str] = None,
                  discovery_type: Optional[str] = None, last_seen: Optional[float] = None) -> bool:
        if last_seen is None:
            last_seen = time.time()
        
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO peers (peer_id, device_name, mac_address, discovery_type, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                ''', (peer_id, device_name, mac_address, discovery_type, last_seen))
                
                conn.commit()
                return True
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error saving peer: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def get_all_peers(self) -> List[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT peer_id, device_name, mac_address, discovery_type, last_seen
                    FROM peers
                    ORDER BY last_seen DESC
                ''')
                
                rows = cursor.fetchall()
                
                peers = []
                for row in rows:
                    peers.append({
                        'peer_id': row[0],
                        'device_name': row[1],
                        'mac_address': row[2],
                        'discovery_type': row[3],
                        'last_seen': row[4]
                    })
                
                return peers
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting all peers: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def get_peer(self, peer_id: str) -> Optional[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT peer_id, device_name, mac_address, discovery_type, last_seen
                    FROM peers
                    WHERE peer_id = ?
                ''', (peer_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'peer_id': row[0],
                        'device_name': row[1],
                        'mac_address': row[2],
                        'discovery_type': row[3],
                        'last_seen': row[4]
                    }
                return None
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting peer: {e}")
                return None
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def save_message(self, peer_id: str, sender_type: str, content_type: str,
                    content: str, timestamp: Optional[float] = None, ttl_seconds: Optional[int] = None) -> bool:
        if timestamp is None:
            timestamp = time.time()
        
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = timestamp + ttl_seconds
        
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                content_blob = content.encode('utf-8')
                
                cursor.execute('''
                    INSERT INTO messages (peer_id, sender_type, content_type, content, timestamp, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (peer_id, sender_type, content_type, content_blob, timestamp, expires_at))
                
                conn.commit()
                return True
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error saving message: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def get_messages_for_peer(self, peer_id: str, limit: int = 100) -> List[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT message_id, sender_type, content_type, content, timestamp
                    FROM messages
                    WHERE peer_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                ''', (peer_id, limit))
                
                rows = cursor.fetchall()
                
                messages = []
                for row in rows:
                    try:
                        content_str = row[3].decode('utf-8') if isinstance(row[3], bytes) else row[3]
                    except:
                        content_str = "[Decoding Error]"
                    
                    messages.append({
                        'message_id': row[0],
                        'sender_type': row[1],
                        'content_type': row[2],
                        'content': content_str,
                        'timestamp': row[4]
                    })
                
                return messages
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting messages: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def get_message_count_for_peer(self, peer_id: str) -> int:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT COUNT(*) FROM messages WHERE peer_id = ?
                ''', (peer_id,))
                
                result = cursor.fetchone()
                return result[0] if result else 0
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting message count: {e}")
                return 0
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def delete_peer_history(self, peer_id: str) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM messages WHERE peer_id = ?', (peer_id,))
                conn.commit()
                return True
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error deleting peer history: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def cleanup_old_messages(self, days: int = 7) -> int:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cutoff_time = time.time() - (days * 24 * 3600)
                
                cursor.execute('DELETE FROM messages WHERE timestamp < ?', (cutoff_time,))
                conn.commit()
                
                deleted_count = cursor.rowcount
                return deleted_count
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error cleaning up messages: {e}")
                return 0
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def scrub_expired_messages(self) -> int:
        conn = None
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                current_time = time.time()
                
                cursor.execute('''
                    SELECT message_id, content_type, content
                    FROM messages
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                ''', (current_time,))
                
                expired_rows = cursor.fetchall()
                
                for message_id, content_type, content in expired_rows:
                    if content_type == 'file':
                        try:
                            file_path = content.decode('utf-8') if isinstance(content, bytes) else content
                            if file_path and os.path.isfile(file_path):
                                os.remove(file_path)
                                print(f"[PersistenceDatabase] Deleted file: {file_path}")
                        except Exception as e:
                            print(f"[PersistenceDatabase] Error deleting file: {e}")
                
                cursor.execute('DELETE FROM messages WHERE expires_at IS NOT NULL AND expires_at < ?', (current_time,))
                conn.commit()
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    print(f"[PersistenceDatabase] Scrubbed {deleted_count} expired messages")
                return deleted_count
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error scrubbing expired messages: {e}")
                return 0
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def shred_everything(self) -> bool:
        with self.db_lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                
                for table in tables:
                    table_name = table[0]
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                    except Exception as e:
                        print(f"[PersistenceDatabase] Error dropping table {table_name}: {e}")
                
                cursor.execute("VACUUM")
                conn.commit()
                conn.close()
                conn = None
                
                print("[PersistenceDatabase] Database shredded successfully")
                return True
                
            except Exception as e:
                print(f"[PersistenceDatabase] Error during database shredding: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                try:
                    if os.path.exists(self.db_path):
                        for _ in range(3):
                            with open(self.db_path, 'r+b') as f:
                                size = os.path.getsize(self.db_path)
                                f.seek(0)
                                f.write(os.urandom(size))
                except Exception as e:
                    print(f"[PersistenceDatabase] Error overwriting database file: {e}")
