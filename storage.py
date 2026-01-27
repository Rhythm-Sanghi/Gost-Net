"""
Ghost Net - Encrypted Storage Module
Persistent storage for chat history and file records using SQLite with encryption.
All message content is encrypted at rest using Fernet symmetric encryption.
"""

import sqlite3
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from cryptography.fernet import Fernet
import threading


class DatabaseManager:
    """
    Manages encrypted persistent storage for Ghost Net.
    
    Features:
    - SQLite database for chat history and file records
    - Fernet encryption for message content at rest
    - Automatic key generation and storage
    - Thread-safe database operations
    - Privacy-focused cleanup of old messages
    """
    
    def __init__(self, db_path: str = "ghostnet.db", key_path: str = "secret.key"):
        """
        Initialize the database manager.
        
        Args:
            db_path: Path to SQLite database file
            key_path: Path to encryption key file
        """
        self.db_path = db_path
        self.key_path = key_path
        self.cipher = None
        self.db_lock = threading.Lock()
        
        # Initialize encryption and database
        self._initialize_encryption()
        self._initialize_database()
        
        print(f"[DatabaseManager] Initialized with database: {db_path}")
    
    def _initialize_encryption(self):
        """Initialize or load the encryption key."""
        key = self._get_or_create_key()
        self.cipher = Fernet(key)
        print("[DatabaseManager] Encryption initialized")
    
    def _get_or_create_key(self) -> bytes:
        """
        Get existing encryption key or generate a new one.
        
        Returns:
            Encryption key (32 bytes, base64 encoded)
        """
        if os.path.exists(self.key_path):
            # Load existing key
            try:
                with open(self.key_path, 'rb') as f:
                    key = f.read()
                print(f"[DatabaseManager] Loaded encryption key from {self.key_path}")
                return key
            except Exception as e:
                print(f"[DatabaseManager] Error loading key: {e}")
                print("[DatabaseManager] Generating new key...")
        
        # Generate new key
        key = Fernet.generate_key()
        
        try:
            with open(self.key_path, 'wb') as f:
                f.write(key)
            
            # Set restrictive permissions (Unix-like systems)
            try:
                os.chmod(self.key_path, 0o600)
            except:
                pass
            
            print(f"[DatabaseManager] Generated new encryption key: {self.key_path}")
        except Exception as e:
            print(f"[DatabaseManager] Error saving key: {e}")
        
        return key
    
    def _encrypt_content(self, content: str) -> bytes:
        """Encrypt message content."""
        try:
            return self.cipher.encrypt(content.encode('utf-8'))
        except Exception as e:
            print(f"[DatabaseManager] Encryption error: {e}")
            return content.encode('utf-8')
    
    def _decrypt_content(self, encrypted: bytes) -> str:
        """Decrypt message content."""
        try:
            return self.cipher.decrypt(encrypted).decode('utf-8')
        except Exception as e:
            print(f"[DatabaseManager] Decryption error: {e}")
            return encrypted.decode('utf-8', errors='ignore')
    
    def _initialize_database(self):
        """Create database tables if they don't exist."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Peers table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS peers (
                        ip_address TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        last_seen REAL NOT NULL
                    )
                ''')
                
                # Messages table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        peer_ip TEXT NOT NULL,
                        sender TEXT NOT NULL,
                        content BLOB NOT NULL,
                        message_type TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        file_path TEXT,
                        FOREIGN KEY (peer_ip) REFERENCES peers(ip_address)
                    )
                ''')
                
                # Create indexes for performance
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_messages_peer 
                    ON messages(peer_ip)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                    ON messages(timestamp)
                ''')
                
                conn.commit()
                conn.close()
                
                print("[DatabaseManager] Database tables initialized")
                
            except Exception as e:
                print(f"[DatabaseManager] Database initialization error: {e}")
    
    def save_peer(self, ip_address: str, username: str, last_seen: Optional[float] = None):
        """
        Save or update a peer in the database.
        
        Args:
            ip_address: Peer's IP address
            username: Peer's username
            last_seen: Unix timestamp (defaults to current time)
        """
        if last_seen is None:
            last_seen = time.time()
        
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO peers (ip_address, username, last_seen)
                    VALUES (?, ?, ?)
                ''', (ip_address, username, last_seen))
                
                conn.commit()
                conn.close()
                
                # print(f"[DatabaseManager] Saved peer: {username} @ {ip_address}")
                
            except Exception as e:
                print(f"[DatabaseManager] Error saving peer: {e}")
    
    def get_peer_username(self, ip_address: str) -> Optional[str]:
        """
        Get username for a peer IP address.
        
        Args:
            ip_address: Peer's IP address
            
        Returns:
            Username or None if not found
        """
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT username FROM peers WHERE ip_address = ?
                ''', (ip_address,))
                
                result = cursor.fetchone()
                conn.close()
                
                return result[0] if result else None
                
            except Exception as e:
                print(f"[DatabaseManager] Error getting peer username: {e}")
                return None
    
    def save_message(self, peer_ip: str, sender: str, content: str, 
                     message_type: str, file_path: Optional[str] = None,
                     timestamp: Optional[float] = None):
        """
        Save a message to the database (encrypted).
        
        Args:
            peer_ip: Peer's IP address
            sender: "ME" or "PEER"
            content: Message content (will be encrypted)
            message_type: "TEXT" or "FILE"
            file_path: Path to file (for FILE type)
            timestamp: Unix timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Encrypt content
                encrypted_content = self._encrypt_content(content)
                
                cursor.execute('''
                    INSERT INTO messages (peer_ip, sender, content, message_type, timestamp, file_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (peer_ip, sender, encrypted_content, message_type, timestamp, file_path))
                
                conn.commit()
                conn.close()
                
                # print(f"[DatabaseManager] Saved message: {message_type} from {sender}")
                
            except Exception as e:
                print(f"[DatabaseManager] Error saving message: {e}")
    
    def get_history(self, peer_ip: str, limit: int = 100) -> List[Dict]:
        """
        Get chat history with a peer (decrypted).
        
        Args:
            peer_ip: Peer's IP address
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dictionaries with keys:
            - id, sender, content, message_type, timestamp, file_path
        """
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, sender, content, message_type, timestamp, file_path
                    FROM messages
                    WHERE peer_ip = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                ''', (peer_ip, limit))
                
                rows = cursor.fetchall()
                conn.close()
                
                # Decrypt and format messages
                messages = []
                for row in rows:
                    msg_id, sender, encrypted_content, msg_type, ts, file_path = row
                    
                    try:
                        content = self._decrypt_content(encrypted_content)
                    except:
                        content = "[Decryption Failed]"
                    
                    messages.append({
                        'id': msg_id,
                        'sender': sender,
                        'content': content,
                        'message_type': msg_type,
                        'timestamp': ts,
                        'file_path': file_path
                    })
                
                print(f"[DatabaseManager] Loaded {len(messages)} messages for {peer_ip}")
                return messages
                
            except Exception as e:
                print(f"[DatabaseManager] Error getting history: {e}")
                return []
    
    def get_all_peers(self) -> List[Dict]:
        """
        Get all known peers from database.
        
        Returns:
            List of peer dictionaries with keys: ip_address, username, last_seen
        """
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT ip_address, username, last_seen
                    FROM peers
                    ORDER BY last_seen DESC
                ''')
                
                rows = cursor.fetchall()
                conn.close()
                
                peers = []
                for row in rows:
                    peers.append({
                        'ip_address': row[0],
                        'username': row[1],
                        'last_seen': row[2]
                    })
                
                return peers
                
            except Exception as e:
                print(f"[DatabaseManager] Error getting peers: {e}")
                return []
    
    def cleanup_old_messages(self, hours: int = 24) -> int:
        """
        Delete messages older than specified hours (privacy feature).
        
        Args:
            hours: Age threshold in hours (default 24)
            
        Returns:
            Number of messages deleted
        """
        cutoff_time = time.time() - (hours * 3600)
        
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get count before deletion
                cursor.execute('''
                    SELECT COUNT(*) FROM messages WHERE timestamp < ?
                ''', (cutoff_time,))
                count = cursor.fetchone()[0]
                
                # Delete old messages
                cursor.execute('''
                    DELETE FROM messages WHERE timestamp < ?
                ''', (cutoff_time,))
                
                conn.commit()
                conn.close()
                
                print(f"[DatabaseManager] Cleaned up {count} messages older than {hours} hours")
                return count
                
            except Exception as e:
                print(f"[DatabaseManager] Error cleaning up messages: {e}")
                return 0
    
    def delete_peer_history(self, peer_ip: str) -> int:
        """
        Delete all messages with a specific peer.
        
        Args:
            peer_ip: Peer's IP address
            
        Returns:
            Number of messages deleted
        """
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM messages WHERE peer_ip = ?
                ''', (peer_ip,))
                
                deleted = cursor.rowcount
                conn.commit()
                conn.close()
                
                print(f"[DatabaseManager] Deleted {deleted} messages with {peer_ip}")
                return deleted
                
            except Exception as e:
                print(f"[DatabaseManager] Error deleting peer history: {e}")
                return 0
    
    def get_statistics(self) -> Dict:
        """
        Get database statistics.
        
        Returns:
            Dictionary with: total_messages, total_peers, oldest_message, newest_message
        """
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Count messages
                cursor.execute('SELECT COUNT(*) FROM messages')
                total_messages = cursor.fetchone()[0]
                
                # Count peers
                cursor.execute('SELECT COUNT(*) FROM peers')
                total_peers = cursor.fetchone()[0]
                
                # Get timestamp range
                cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM messages')
                oldest, newest = cursor.fetchone()
                
                conn.close()
                
                return {
                    'total_messages': total_messages,
                    'total_peers': total_peers,
                    'oldest_message': oldest,
                    'newest_message': newest
                }
                
            except Exception as e:
                print(f"[DatabaseManager] Error getting statistics: {e}")
                return {
                    'total_messages': 0,
                    'total_peers': 0,
                    'oldest_message': None,
                    'newest_message': None
                }
    
    def export_chat(self, peer_ip: str, output_path: str) -> bool:
        """
        Export chat history to a text file (decrypted).
        
        Args:
            peer_ip: Peer's IP address
            output_path: Path to output file
            
        Returns:
            True if successful
        """
        try:
            messages = self.get_history(peer_ip, limit=10000)
            username = self.get_peer_username(peer_ip) or peer_ip
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Ghost Net Chat History\n")
                f.write(f"Peer: {username} ({peer_ip})\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                
                for msg in messages:
                    dt = datetime.fromtimestamp(msg['timestamp'])
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    sender = "You" if msg['sender'] == 'ME' else username
                    
                    if msg['message_type'] == 'TEXT':
                        f.write(f"[{time_str}] {sender}: {msg['content']}\n")
                    else:
                        f.write(f"[{time_str}] {sender}: [FILE] {msg['content']}\n")
                        if msg['file_path']:
                            f.write(f"    Path: {msg['file_path']}\n")
                    
                    f.write("\n")
            
            print(f"[DatabaseManager] Exported {len(messages)} messages to {output_path}")
            return True
            
        except Exception as e:
            print(f"[DatabaseManager] Error exporting chat: {e}")
            return False
    
    def vacuum_database(self):
        """Optimize database by reclaiming unused space."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute('VACUUM')
                conn.close()
                print("[DatabaseManager] Database vacuumed successfully")
            except Exception as e:
                print(f"[DatabaseManager] Error vacuuming database: {e}")
    
    def close(self):
        """Clean up database resources."""
        print("[DatabaseManager] Closing database manager")
        # SQLite connections are per-operation, no persistent connection to close


# Example usage and testing
if __name__ == "__main__":
    print("=== Ghost Net Database Manager Test ===\n")
    
    # Initialize database
    db = DatabaseManager(db_path="test_ghostnet.db", key_path="test_secret.key")
    
    # Test peer storage
    print("\n1. Testing peer storage...")
    db.save_peer("192.168.1.100", "Alice")
    db.save_peer("192.168.1.101", "Bob")
    
    # Test message storage
    print("\n2. Testing message storage...")
    db.save_message("192.168.1.100", "ME", "Hello Alice!", "TEXT")
    db.save_message("192.168.1.100", "PEER", "Hi there!", "TEXT")
    db.save_message("192.168.1.100", "ME", "photo.jpg", "FILE", file_path="/downloads/photo.jpg")
    
    db.save_message("192.168.1.101", "ME", "Hey Bob!", "TEXT")
    db.save_message("192.168.1.101", "PEER", "Hello!", "TEXT")
    
    # Test history retrieval
    print("\n3. Testing history retrieval...")
    alice_history = db.get_history("192.168.1.100")
    print(f"   Alice's history: {len(alice_history)} messages")
    for msg in alice_history:
        print(f"   - {msg['sender']}: {msg['content']} ({msg['message_type']})")
    
    # Test peer listing
    print("\n4. Testing peer listing...")
    peers = db.get_all_peers()
    print(f"   Total peers: {len(peers)}")
    for peer in peers:
        print(f"   - {peer['username']} @ {peer['ip_address']}")
    
    # Test statistics
    print("\n5. Testing statistics...")
    stats = db.get_statistics()
    print(f"   Total messages: {stats['total_messages']}")
    print(f"   Total peers: {stats['total_peers']}")
    
    # Test export
    print("\n6. Testing chat export...")
    db.export_chat("192.168.1.100", "alice_chat_export.txt")
    
    # Test cleanup (set to very old time so nothing is deleted in this test)
    print("\n7. Testing cleanup (1000 hours)...")
    deleted = db.cleanup_old_messages(hours=1000)
    print(f"   Deleted {deleted} old messages")
    
    print("\n=== Test Complete ===")
    print("Check test_ghostnet.db and test_secret.key files")
    print("Try opening the .db file - content should be encrypted!")
