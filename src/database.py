import sqlite3
import os
import sys
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional
from cryptography.fernet import Fernet

_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


class PersistenceDatabase:

    def __init__(self, db_path: str = "ghostnet_persistence.db", decrypted_key: Optional[bytes] = None):
        self.db_path = db_path
        self.db_lock = threading.Lock()
        self.initialization_error = None
        self.ephemeral_mode = False
        self.ephemeral_messages = []
        self.cipher = Fernet(decrypted_key) if decrypted_key else None
        
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        try:
            self._initialize_database()
        except Exception as e:
            self.initialization_error = f"Database initialization failed: {e}"
            print(f"[PersistenceDatabase] ERROR: {self.initialization_error}")
            
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute('PRAGMA journal_mode = WAL;')
            conn.execute('PRAGMA synchronous = NORMAL;')
            conn.execute('PRAGMA busy_timeout = 10000')
        except Exception as e:
            print(f"[PersistenceDatabase] Warning setting PRAGMAs: {e}")
        return conn
    
    def close(self):
        """Cleanly releases any cached handles or connections."""
        pass
    
    def _initialize_database(self):
        with self.db_lock:
            try:
                conn = self._connect()
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
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS double_ratchet_sessions (
                        peer_id TEXT PRIMARY KEY,
                        session_data TEXT NOT NULL
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS waypoints (
                        waypoint_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        waypoint_type TEXT NOT NULL,
                        latitude REAL NOT NULL,
                        longitude REAL NOT NULL,
                        altitude REAL DEFAULT 0.0,
                        created_by TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS revoked_peers (
                        peer_id TEXT PRIMARY KEY,
                        reason TEXT NOT NULL,
                        revoked_at REAL NOT NULL,
                        signature TEXT
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_channels (
                        channel_id TEXT PRIMARY KEY,
                        channel_name TEXT NOT NULL,
                        passphrase_salt TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        is_active INTEGER DEFAULT 1
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_messages (
                        message_id TEXT PRIMARY KEY,
                        channel_id TEXT NOT NULL,
                        sender_id TEXT NOT NULL,
                        sender_name TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        is_read INTEGER DEFAULT 0
                    )
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_group_messages_channel_time
                    ON group_messages(channel_id, timestamp)
                ''')
                
                conn.commit()

                
                self._migrate_add_expires_at_column(conn, cursor)
                self._migrate_add_signing_key_columns(conn, cursor)
                
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
            
    def _migrate_add_signing_key_columns(self, conn, cursor):
        try:
            cursor.execute("PRAGMA table_info(peers)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'signing_key' not in columns:
                cursor.execute('ALTER TABLE peers ADD COLUMN signing_key TEXT')
                conn.commit()
                print("[PersistenceDatabase] Migration: Added signing_key column to peers table")
            if 'is_verified' not in columns:
                cursor.execute('ALTER TABLE peers ADD COLUMN is_verified INTEGER DEFAULT 0')
                conn.commit()
                print("[PersistenceDatabase] Migration: Added is_verified column to peers table")
        except Exception as e:
            print(f"[PersistenceDatabase] Migration error for peers table: {e}")

    def get_peer(self, peer_id: str) -> Optional[dict]:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT peer_id, device_name, mac_address, discovery_type, last_seen, signing_key, is_verified
                    FROM peers WHERE peer_id = ?
                ''', (peer_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'peer_id': row[0],
                        'device_name': row[1],
                        'mac_address': row[2],
                        'discovery_type': row[3],
                        'last_seen': row[4],
                        'signing_key': row[5],
                        'is_verified': row[6]
                    }
                return None
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting peer {peer_id}: {e}")
                return None
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def update_peer_signing_key(self, peer_id: str, signing_key: str, is_verified: int = 0) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE peers SET signing_key = ?, is_verified = ? WHERE peer_id = ?
                ''', (signing_key, is_verified, peer_id))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error updating peer signing key: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def set_peer_verified(self, peer_id: str, is_verified: bool = True) -> bool:
        """Mark a peer's identity key as verified or unverified out-of-band."""
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE peers SET is_verified = ? WHERE peer_id = ?
                ''', (1 if is_verified else 0, peer_id))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error setting peer verification for {peer_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def is_peer_verified(self, peer_id: str) -> bool:
        """Check whether a peer's identity key has been verified out-of-band."""
        peer = self.get_peer(peer_id)
        if peer:
            return bool(peer.get('is_verified', 0))
        return False
    
    def save_peer(self, peer_id: str, device_name: str, mac_address: Optional[str] = None,
                  discovery_type: Optional[str] = None, last_seen: Optional[float] = None) -> bool:
        if last_seen is None:
            last_seen = time.time()
        
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
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
                conn = self._connect()
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
    

    
    def save_message(self, peer_id: str, sender_type: str, content_type: str,
                    content: str, timestamp: Optional[float] = None, ttl_seconds: Optional[int] = None) -> bool:
        if timestamp is None:
            timestamp = time.time()
        
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = timestamp + ttl_seconds
            
        if self.ephemeral_mode:
            with self.db_lock:
                self.ephemeral_messages.append({
                    'message_id': len(self.ephemeral_messages) + 1,
                    'peer_id': peer_id,
                    'sender_type': sender_type,
                    'content_type': content_type,
                    'content': content,
                    'timestamp': timestamp,
                    'expires_at': expires_at
                })
            return True
        
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                if self.cipher:
                    content_blob = self.cipher.encrypt(content.encode('utf-8'))
                else:
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
        if self.ephemeral_mode:
            with self.db_lock:
                now = time.time()
                self.ephemeral_messages = [m for m in self.ephemeral_messages if not (m.get('expires_at') and m['expires_at'] < now)]
                msgs = [m for m in self.ephemeral_messages if m['peer_id'] == peer_id]
                msgs = sorted(msgs, key=lambda x: x['timestamp'])[-limit:]
                return msgs
                
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
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
                        if self.cipher and isinstance(row[3], bytes):
                            content_str = self.cipher.decrypt(row[3]).decode('utf-8')
                        else:
                            content_str = row[3].decode('utf-8') if isinstance(row[3], bytes) else row[3]
                    except Exception as e:
                        content_str = f"[Decryption/Decoding Error: {e}]"
                    
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
                conn = self._connect()
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
                conn = self._connect()
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
                conn = self._connect()
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
                conn = self._connect()
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
                            if self.cipher and isinstance(content, bytes):
                                file_path = self.cipher.decrypt(content).decode('utf-8')
                            else:
                                file_path = content.decode('utf-8') if isinstance(content, bytes) else content
                            
                            if file_path and os.path.isfile(file_path):
                                try:
                                    from src.security import shred_file
                                except ImportError:
                                    from security import shred_file
                                shred_file(file_path)
                                print(f"[PersistenceDatabase] Shredded file: {file_path}")
                        except Exception as e:
                            print(f"[PersistenceDatabase] Error shredding file: {e}")
                
                cursor.execute('DELETE FROM messages WHERE expires_at IS NOT NULL AND expires_at < ?', (current_time,))
                conn.commit()
                
                deleted_count = cursor.rowcount

                # Also scrub in-memory ephemeral messages
                now = current_time
                initial_ephem = len(self.ephemeral_messages)
                valid_ephem = []
                for m in self.ephemeral_messages:
                    if m.get('expires_at') and m['expires_at'] < now:
                        if m.get('content_type') == 'file':
                            f_path = m.get('content')
                            if f_path and os.path.isfile(f_path):
                                try:
                                    from security import shred_file
                                    shred_file(f_path)
                                except Exception:
                                    pass
                    else:
                        valid_ephem.append(m)
                self.ephemeral_messages = valid_ephem
                deleted_count += (initial_ephem - len(self.ephemeral_messages))

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
        self.ephemeral_messages.clear()
        with self.db_lock:
            try:
                try:
                    from src.security import shred_file
                except ImportError:
                    from security import shred_file
                shred_file(self.db_path)
                print("[PersistenceDatabase] Database file securely shredded and deleted")
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error during database shredding: {e}")
                return False

    def recreate_and_populate_mock_data(self) -> bool:
        # 1. Initialize empty tables
        self._initialize_database()
        
        # 2. Insert mock peers and messages
        import time
        now = time.time()
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                # Mock Peers
                peers = [
                    ("wfd_alice", "Alice (Base)", "12:34:56:78:90:AB", "wifi-direct", now),
                    ("bt_bob", "Bob (Mobile)", "CD:EF:12:34:56:78", "bluetooth", now - 300),
                    ("mesh_charlie", "Charlie (Relay)", "90:AB:CD:EF:12:34", "mesh", now - 1200)
                ]
                for p in peers:
                    cursor.execute('''
                        INSERT OR REPLACE INTO peers (peer_id, device_name, mac_address, discovery_type, last_seen)
                        VALUES (?, ?, ?, ?, ?)
                    ''', p)
                
                # Mock Messages
                messages = [
                    ("wfd_alice", "peer", "text", "Hey, did you make it to the safe zone?", now - 3600),
                    ("wfd_alice", "me", "text", "Yes, just arrived. How's the situation?", now - 3500),
                    ("wfd_alice", "peer", "text", "Quiet for now. Keep your radio on.", now - 3400),
                    ("bt_bob", "peer", "text", "Meeting at coordinates 45.123, -12.345 at 1800.", now - 1800),
                    ("bt_bob", "me", "text", "Copy that, see you there.", now - 1700),
                    ("mesh_charlie", "peer", "text", "Supplies are running low, anyone got extra water?", now - 1200),
                    ("wfd_alice", "peer", "text", "We have some at the base.", now - 1100)
                ]
                for m in messages:
                    content_blob = m[3].encode('utf-8')
                    cursor.execute('''
                        INSERT INTO messages (peer_id, sender_type, content_type, content, timestamp, expires_at)
                        VALUES (?, ?, ?, ?, ?, NULL)
                    ''', (m[0], m[1], m[2], content_blob, m[4]))
                
                conn.commit()
                print("[PersistenceDatabase] Decoy mock data populated successfully")
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error populating mock data: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def save_ratchet_session(self, peer_id: str, session_data: str) -> bool:
        import base64
        session_data_to_save = session_data
        if self.cipher:
            try:
                encrypted = self.cipher.encrypt(session_data.encode('utf-8'))
                session_data_to_save = base64.b64encode(encrypted).decode('utf-8')
            except Exception as e:
                print(f"[PersistenceDatabase] Ratchet encryption warning: {e}")
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO double_ratchet_sessions (peer_id, session_data)
                    VALUES (?, ?)
                ''', (peer_id, session_data_to_save))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error saving ratchet session for {peer_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def get_ratchet_session(self, peer_id: str) -> Optional[str]:
        import base64
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT session_data FROM double_ratchet_sessions WHERE peer_id = ?
                ''', (peer_id,))
                row = cursor.fetchone()
                if row:
                    raw_val = row[0]
                    if self.cipher:
                        try:
                            decrypted = self.cipher.decrypt(base64.b64decode(raw_val.encode('utf-8'))).decode('utf-8')
                            return decrypted
                        except Exception as e:
                            if raw_val.strip().startswith('{'):
                                return raw_val
                            print(f"[PersistenceDatabase] Ratchet decryption failed: {e}")
                            return None
                    return raw_val
                return None
            except Exception as e:
                print(f"[PersistenceDatabase] Error loading ratchet session for {peer_id}: {e}")
                return None
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def save_waypoint(self, waypoint_id: str, title: str, description: str,
                      waypoint_type: str, latitude: float, longitude: float,
                      altitude: float = 0.0, created_by: str = 'unknown',
                      created_at: Optional[float] = None,
                      expires_at: Optional[float] = None) -> bool:
        if created_at is None:
            created_at = time.time()
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO waypoints
                    (waypoint_id, title, description, waypoint_type, latitude, longitude, altitude, created_by, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (waypoint_id, title, description, waypoint_type, latitude, longitude, altitude, created_by, created_at, expires_at))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error saving waypoint {waypoint_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def get_all_waypoints(self) -> List[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT waypoint_id, title, description, waypoint_type, latitude, longitude, altitude, created_by, created_at, expires_at
                    FROM waypoints
                    ORDER BY created_at DESC
                ''')
                rows = cursor.fetchall()
                now = time.time()
                waypoints = []
                for r in rows:
                    exp = r[9]
                    if exp is not None and exp < now:
                        continue
                    waypoints.append({
                        'waypoint_id': r[0],
                        'title': r[1],
                        'description': r[2],
                        'waypoint_type': r[3],
                        'latitude': r[4],
                        'longitude': r[5],
                        'altitude': r[6],
                        'created_by': r[7],
                        'created_at': r[8],
                        'expires_at': r[9]
                    })
                return waypoints
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting all waypoints: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def delete_waypoint(self, waypoint_id: str) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM waypoints WHERE waypoint_id = ?', (waypoint_id,))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error deleting waypoint {waypoint_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def scrub_expired_waypoints(self) -> int:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                now = time.time()
                cursor.execute('DELETE FROM waypoints WHERE expires_at IS NOT NULL AND expires_at < ?', (now,))
                conn.commit()
                deleted = cursor.rowcount
                if deleted > 0:
                    print(f"[PersistenceDatabase] Scrubbed {deleted} expired waypoints")
                return deleted
            except Exception as e:
                print(f"[PersistenceDatabase] Error scrubbing expired waypoints: {e}")
                return 0
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def revoke_peer(self, peer_id: str, reason: str, signature: Optional[str] = None) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                revoked_at = time.time()
                cursor.execute('''
                    INSERT OR REPLACE INTO revoked_peers (peer_id, reason, revoked_at, signature)
                    VALUES (?, ?, ?, ?)
                ''', (peer_id, reason, revoked_at, signature))
                conn.commit()
                print(f"[PersistenceDatabase] Peer {peer_id} blacklisted/revoked: {reason}")
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error revoking peer {peer_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def is_peer_revoked(self, peer_id: str) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('SELECT peer_id FROM revoked_peers WHERE peer_id = ?', (peer_id,))
                row = cursor.fetchone()
                return row is not None
            except Exception as e:
                print(f"[PersistenceDatabase] Error checking revocation for {peer_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def get_revoked_peers(self) -> List[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('SELECT peer_id, reason, revoked_at, signature FROM revoked_peers ORDER BY revoked_at DESC')
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    results.append({
                        'peer_id': r[0],
                        'reason': r[1],
                        'revoked_at': r[2],
                        'signature': r[3]
                    })
                return results
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting revoked peers: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def unrevoke_peer(self, peer_id: str) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM revoked_peers WHERE peer_id = ?', (peer_id,))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error un-revoking peer {peer_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def create_group_channel(self, channel_id: str, channel_name: str, passphrase_salt: str, created_at: Optional[float] = None) -> bool:
        if created_at is None:
            created_at = time.time()
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO group_channels (channel_id, channel_name, passphrase_salt, created_at, is_active)
                    VALUES (?, ?, ?, ?, 1)
                ''', (channel_id, channel_name, passphrase_salt, created_at))
                conn.commit()
                print(f"[PersistenceDatabase] Created group channel: {channel_name} ({channel_id})")
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error creating group channel {channel_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def get_all_group_channels(self) -> List[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('SELECT channel_id, channel_name, passphrase_salt, created_at, is_active FROM group_channels WHERE is_active = 1 ORDER BY created_at ASC')
                rows = cursor.fetchall()
                channels = []
                for r in rows:
                    channels.append({
                        'channel_id': r[0],
                        'channel_name': r[1],
                        'passphrase_salt': r[2],
                        'created_at': r[3],
                        'is_active': r[4]
                    })
                return channels
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting group channels: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def delete_group_channel(self, channel_id: str) -> bool:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM group_channels WHERE channel_id = ?', (channel_id,))
                cursor.execute('DELETE FROM group_messages WHERE channel_id = ?', (channel_id,))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error deleting group channel {channel_id}: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def save_group_message(self, message_id: str, channel_id: str, sender_id: str, sender_name: str, content: str, timestamp: Optional[float] = None) -> bool:
        if timestamp is None:
            timestamp = time.time()
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO group_messages (message_id, channel_id, sender_id, sender_name, content, timestamp, is_read)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                ''', (message_id, channel_id, sender_id, sender_name, content, timestamp))
                conn.commit()
                return True
            except Exception as e:
                print(f"[PersistenceDatabase] Error saving group message: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def get_group_messages(self, channel_id: str, limit: int = 50) -> List[Dict]:
        conn = None
        with self.db_lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT message_id, channel_id, sender_id, sender_name, content, timestamp, is_read
                    FROM group_messages
                    WHERE channel_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                ''', (channel_id, limit))
                rows = cursor.fetchall()
                messages = []
                for r in rows:
                    messages.append({
                        'message_id': r[0],
                        'channel_id': r[1],
                        'sender_id': r[2],
                        'sender_name': r[3],
                        'content': r[4],
                        'timestamp': r[5],
                        'is_read': r[6]
                    })
                return messages
            except Exception as e:
                print(f"[PersistenceDatabase] Error getting group messages for {channel_id}: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

