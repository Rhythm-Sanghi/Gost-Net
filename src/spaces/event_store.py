"""
Ghost Net - Local Event Store
Thread-safe, SQLite-backed append-only local event store for Spaces.
Enforces deduplication, deterministic total ordering, signature verification,
dependency tracking, and state digests.
"""

import sqlite3
import json
import time
import os
import hashlib
import threading
from typing import List, Dict, Optional, Tuple, Union, Any

from .models import (
    Space,
    SpaceMember,
    SpaceEvent,
    LifecycleState,
    EventType,
    MemberRole,
    ExpiryPolicy,
    JoinPolicy,
)
from .envelope import (
    validate_event,
    verify_event_signature,
    canonical_serialize,
)


class EventStore:
    """
    Manages persistent local storage and queries for Spaces and signed SpaceEvents.
    Can attach to an existing SQLite connection/path or PersistenceDatabase instance.
    """

    def __init__(self, db_path_or_db: Union[str, Any]):
        if isinstance(db_path_or_db, str):
            self.db_path = db_path_or_db
            self._external_db = None
        elif hasattr(db_path_or_db, 'db_path'):
            # PersistenceDatabase instance
            self.db_path = db_path_or_db.db_path
            self._external_db = db_path_or_db
        else:
            raise ValueError("Expected db_path (str) or PersistenceDatabase instance")

        self.lock = threading.RLock()
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        if self._external_db and hasattr(self._external_db, '_connect'):
            return self._external_db._connect()
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute('PRAGMA journal_mode = WAL;')
            conn.execute('PRAGMA synchronous = NORMAL;')
            conn.execute('PRAGMA busy_timeout = 10000')
        except Exception:
            pass
        return conn

    def _init_tables(self):
        """Creates spaces and space_events schema idempotently."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS spaces (
                        space_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        created_at REAL NOT NULL,
                        created_by TEXT NOT NULL,
                        expiry_policy TEXT NOT NULL,
                        expires_at REAL,
                        join_policy TEXT NOT NULL,
                        lifecycle_state TEXT NOT NULL DEFAULT 'active',
                        local_clock INTEGER DEFAULT 0,
                        state_digest TEXT
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS space_members (
                        space_id TEXT NOT NULL,
                        peer_id TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'member',
                        signing_key TEXT,
                        joined_at REAL NOT NULL,
                        PRIMARY KEY (space_id, peer_id),
                        FOREIGN KEY (space_id) REFERENCES spaces(space_id)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS space_events (
                        event_id TEXT PRIMARY KEY,
                        space_id TEXT NOT NULL,
                        author_id TEXT NOT NULL,
                        device_id TEXT,
                        timestamp REAL NOT NULL,
                        logical_clock INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        object_id TEXT,
                        payload_json TEXT NOT NULL,
                        ref_ids_json TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        author_pubkey TEXT,
                        version INTEGER NOT NULL DEFAULT 1,
                        received_at REAL NOT NULL,
                        FOREIGN KEY (space_id) REFERENCES spaces(space_id)
                    )
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_space_events_order
                    ON space_events(space_id, logical_clock, timestamp, event_id)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_space_events_object
                    ON space_events(space_id, object_id)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_space_events_type
                    ON space_events(space_id, event_type)
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS space_tombstones (
                        space_id TEXT NOT NULL,
                        object_id TEXT NOT NULL,
                        tombstone_event_id TEXT NOT NULL,
                        deleted_at REAL NOT NULL,
                        PRIMARY KEY (space_id, object_id)
                    )
                ''')

                conn.commit()
            finally:
                conn.close()

    # =========================================================================
    # SPACE MANAGEMENT
    # =========================================================================

    def create_space(self, space: Space) -> bool:
        """Persists a new Space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO spaces (
                        space_id, name, description, created_at, created_by,
                        expiry_policy, expires_at, join_policy, lifecycle_state,
                        local_clock, state_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    space.space_id,
                    space.name,
                    space.description,
                    space.created_at,
                    space.created_by,
                    space.expiry_policy,
                    space.expires_at,
                    space.join_policy,
                    space.lifecycle_state,
                    space.local_clock,
                    space.state_digest,
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def get_space(self, space_id: str) -> Optional[Space]:
        """Loads a Space by its identifier, checking expiry status."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT space_id, name, description, created_at, created_by,
                           expiry_policy, expires_at, join_policy, lifecycle_state,
                           local_clock, state_digest
                    FROM spaces WHERE space_id = ?
                ''', (space_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                sp = Space(
                    space_id=row[0],
                    name=row[1],
                    description=row[2] or "",
                    created_at=row[3],
                    created_by=row[4],
                    expiry_policy=row[5],
                    expires_at=row[6],
                    join_policy=row[7],
                    lifecycle_state=row[8],
                    local_clock=row[9] or 0,
                    state_digest=row[10],
                )
                # Check expiration
                if sp.check_and_update_lifecycle() != row[8]:
                    self.update_space_lifecycle(sp.space_id, sp.lifecycle_state)
                return sp
            finally:
                conn.close()

    def list_spaces(self, include_expired: bool = True) -> List[Space]:
        """Returns all registered spaces."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT space_id, name, description, created_at, created_by,
                           expiry_policy, expires_at, join_policy, lifecycle_state,
                           local_clock, state_digest
                    FROM spaces ORDER BY created_at DESC
                ''')
                spaces = []
                for row in cursor.fetchall():
                    sp = Space(
                        space_id=row[0],
                        name=row[1],
                        description=row[2] or "",
                        created_at=row[3],
                        created_by=row[4],
                        expiry_policy=row[5],
                        expires_at=row[6],
                        join_policy=row[7],
                        lifecycle_state=row[8],
                        local_clock=row[9] or 0,
                        state_digest=row[10],
                    )
                    if sp.check_and_update_lifecycle() != row[8]:
                        self.update_space_lifecycle(sp.space_id, sp.lifecycle_state)
                    if include_expired or sp.lifecycle_state != LifecycleState.EXPIRED:
                        spaces.append(sp)
                return spaces
            finally:
                conn.close()

    def update_space_lifecycle(self, space_id: str, new_state: str) -> bool:
        """Updates the lifecycle state (active, archived, expired) of a space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE spaces SET lifecycle_state = ? WHERE space_id = ?
                ''', (new_state, space_id))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def delete_space(self, space_id: str) -> bool:
        """Removes a space, its members, events, and tombstones (used for safe cleanup)."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM space_events WHERE space_id = ?', (space_id,))
                cursor.execute('DELETE FROM space_members WHERE space_id = ?', (space_id,))
                cursor.execute('DELETE FROM space_tombstones WHERE space_id = ?', (space_id,))
                cursor.execute('DELETE FROM spaces WHERE space_id = ?', (space_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    # =========================================================================
    # MEMBER MANAGEMENT
    # =========================================================================

    def add_member(self, member: SpaceMember) -> bool:
        """Adds or updates a member in a Space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO space_members (
                        space_id, peer_id, display_name, role, signing_key, joined_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    member.space_id,
                    member.peer_id,
                    member.display_name,
                    member.role,
                    member.signing_key,
                    member.joined_at,
                ))
                conn.commit()
                return True
            finally:
                conn.close()

    def get_members(self, space_id: str) -> List[SpaceMember]:
        """Lists all members of a Space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT space_id, peer_id, display_name, role, signing_key, joined_at
                    FROM space_members WHERE space_id = ? ORDER BY joined_at ASC
                ''', (space_id,))
                members = []
                for row in cursor.fetchall():
                    members.append(SpaceMember(
                        space_id=row[0],
                        peer_id=row[1],
                        display_name=row[2],
                        role=row[3],
                        signing_key=row[4],
                        joined_at=row[5],
                    ))
                return members
            finally:
                conn.close()

    def get_member(self, space_id: str, peer_id: str) -> Optional[SpaceMember]:
        """Gets a specific member in a Space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT space_id, peer_id, display_name, role, signing_key, joined_at
                    FROM space_members WHERE space_id = ? AND peer_id = ?
                ''', (space_id, peer_id))
                row = cursor.fetchone()
                if not row:
                    return None
                return SpaceMember(
                    space_id=row[0],
                    peer_id=row[1],
                    display_name=row[2],
                    role=row[3],
                    signing_key=row[4],
                    joined_at=row[5],
                )
            finally:
                conn.close()

    def remove_member(self, space_id: str, peer_id: str) -> bool:
        """Removes a member from a Space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM space_members WHERE space_id = ? AND peer_id = ?
                ''', (space_id, peer_id))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    # =========================================================================
    # EVENT STORAGE & VALIDATION
    # =========================================================================

    def store_event(
        self,
        event: SpaceEvent,
        author_pubkey: Optional[Union[bytes, str]] = None,
        verify_sig: bool = True
    ) -> Tuple[bool, str]:
        """
        Validates, verifies, and stores an incoming SpaceEvent.
        Guarantees:
        - Structural schema validity and payload bounds
        - Idempotent deduplication (duplicate event returns (False, "DUPLICATE"))
        - Signature verification against author public key
        - Monotonic logical clock advancement
        - Automatic state digest updates
        """
        # 1. Structural and bounds validation
        is_valid, reason = validate_event(event)
        if not is_valid:
            return False, f"VALIDATION_FAILED: {reason}"

        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()

                # 2. Idempotent Deduplication Check
                cursor.execute('SELECT 1 FROM space_events WHERE event_id = ?', (event.event_id,))
                if cursor.fetchone():
                    return False, "DUPLICATE"

                # 3. Space existence check
                cursor.execute('SELECT local_clock, lifecycle_state FROM spaces WHERE space_id = ?', (event.space_id,))
                space_row = cursor.fetchone()

                if not space_row:
                    # If this is a SPACE_CREATE event, auto-create the space from payload
                    if event.event_type == EventType.SPACE_CREATE:
                        payload = event.payload
                        name = payload.get("name", "Untitled Space")
                        desc = payload.get("description", "")
                        expiry = payload.get("expiry_policy", ExpiryPolicy.NEVER)
                        join_pol = payload.get("join_policy", JoinPolicy.OPEN_NEARBY)
                        new_space = Space(
                            space_id=event.space_id,
                            name=name,
                            description=desc,
                            created_at=event.timestamp,
                            created_by=event.author_id,
                            expiry_policy=expiry,
                            join_policy=join_pol,
                            local_clock=event.logical_clock,
                        )
                        cursor.execute('''
                            INSERT INTO spaces (
                                space_id, name, description, created_at, created_by,
                                expiry_policy, expires_at, join_policy, lifecycle_state,
                                local_clock, state_digest
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            new_space.space_id, new_space.name, new_space.description,
                            new_space.created_at, new_space.created_by, new_space.expiry_policy,
                            new_space.expires_at, new_space.join_policy, new_space.lifecycle_state,
                            new_space.local_clock, new_space.state_digest
                        ))
                        current_local_clock = event.logical_clock
                    else:
                        return False, "SPACE_NOT_FOUND"
                else:
                    space_local_clock = space_row[0] or 0
                    cursor.execute('SELECT COALESCE(MAX(logical_clock), 0) FROM space_events WHERE space_id = ?', (event.space_id,))
                    max_event_clock = cursor.fetchone()[0] or 0
                    current_local_clock = max(space_local_clock, max_event_clock)

                # 4. Digital Signature Verification
                if verify_sig:
                    resolved_pubkey = author_pubkey or event.author_pubkey
                    if not resolved_pubkey:
                        # Try space_members
                        cursor.execute(
                            'SELECT signing_key FROM space_members WHERE space_id = ? AND peer_id = ?',
                            (event.space_id, event.author_id)
                        )
                        mem_row = cursor.fetchone()
                        if mem_row and mem_row[0]:
                            resolved_pubkey = mem_row[0]

                    if not resolved_pubkey:
                        # Try peers table if available
                        try:
                            cursor.execute('SELECT signing_key FROM peers WHERE peer_id = ?', (event.author_id,))
                            peer_row = cursor.fetchone()
                            if peer_row and peer_row[0]:
                                resolved_pubkey = peer_row[0]
                        except Exception:
                            pass

                    if not resolved_pubkey:
                        return False, "UNKNOWN_AUTHOR_KEY"

                    if not verify_event_signature(event, resolved_pubkey):
                        return False, "INVALID_SIGNATURE"

                # 5. Insert event atomically
                cursor.execute('''
                    INSERT INTO space_events (
                        event_id, space_id, author_id, device_id, timestamp,
                        logical_clock, event_type, object_id, payload_json,
                        ref_ids_json, signature, author_pubkey, version, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event.event_id,
                    event.space_id,
                    event.author_id,
                    event.device_id,
                    event.timestamp,
                    event.logical_clock,
                    event.event_type,
                    event.object_id,
                    json.dumps(event.payload, sort_keys=True),
                    json.dumps(list(event.ref_event_ids)),
                    event.signature,
                    event.author_pubkey,
                    event.version,
                    event.received_at,
                ))

                # 6. Advance space local clock
                new_clock = max(current_local_clock, event.logical_clock) + 1
                cursor.execute('UPDATE spaces SET local_clock = ? WHERE space_id = ?', (new_clock, event.space_id))

                # 7. Handle membership state changes
                if event.event_type == EventType.SPACE_JOIN:
                    payload = event.payload
                    disp_name = payload.get("display_name", event.author_id)
                    role = payload.get("role", MemberRole.MEMBER)
                    pubkey = event.author_pubkey or payload.get("signing_key")
                    cursor.execute('''
                        INSERT OR REPLACE INTO space_members (
                            space_id, peer_id, display_name, role, signing_key, joined_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ''', (event.space_id, event.author_id, disp_name, role, pubkey, event.timestamp))
                elif event.event_type == EventType.SPACE_LEAVE:
                    cursor.execute('DELETE FROM space_members WHERE space_id = ? AND peer_id = ?', (event.space_id, event.author_id))

                # 8. Handle object tombstone if applicable
                if event.event_type in (EventType.WAYPOINT_REMOVE,):
                    if event.object_id:
                        cursor.execute('''
                            INSERT OR REPLACE INTO space_tombstones (
                                space_id, object_id, tombstone_event_id, deleted_at
                            ) VALUES (?, ?, ?, ?)
                        ''', (event.space_id, event.object_id, event.event_id, event.timestamp))

                conn.commit()

                # 9. Update state digest
                self._update_space_state_digest(conn, event.space_id)
                conn.commit()

                return True, "STORED"

            except sqlite3.IntegrityError:
                return False, "DUPLICATE"
            except Exception as e:
                return False, f"STORAGE_ERROR: {str(e)}"
            finally:
                conn.close()

    def has_event(self, event_id: str) -> bool:
        """Returns True if event is stored locally."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM space_events WHERE event_id = ?', (event_id,))
                return cursor.fetchone() is not None
            finally:
                conn.close()

    def get_event(self, event_id: str) -> Optional[SpaceEvent]:
        """Fetches a single event by event_id."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT event_id, space_id, author_id, device_id, timestamp,
                           logical_clock, event_type, object_id, payload_json,
                           ref_ids_json, signature, author_pubkey, version, received_at
                    FROM space_events WHERE event_id = ?
                ''', (event_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_event(row)
            finally:
                conn.close()

    def get_events(
        self,
        space_id: str,
        since_clock: int = 0,
        limit: Optional[int] = 200
    ) -> List[SpaceEvent]:
        """
        Retrieves events for a Space in deterministic total order:
        logical_clock ASC, timestamp ASC, event_id ASC.
        Enforces a bounded query size (default 200, maximum 500).
        """
        bounded_limit = min(limit if limit is not None else 200, 500)
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                sql = '''
                    SELECT event_id, space_id, author_id, device_id, timestamp,
                           logical_clock, event_type, object_id, payload_json,
                           ref_ids_json, signature, author_pubkey, version, received_at
                    FROM space_events
                    WHERE space_id = ? AND logical_clock >= ?
                    ORDER BY logical_clock ASC, timestamp ASC, event_id ASC
                    LIMIT ?
                '''
                cursor.execute(sql, [space_id, since_clock, bounded_limit])
                return [self._row_to_event(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_events_for_object(self, space_id: str, object_id: str) -> List[SpaceEvent]:
        """Retrieves all historical events modifying a specific object in deterministic order."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT event_id, space_id, author_id, device_id, timestamp,
                           logical_clock, event_type, object_id, payload_json,
                           ref_ids_json, signature, author_pubkey, version, received_at
                    FROM space_events
                    WHERE space_id = ? AND object_id = ?
                    ORDER BY logical_clock ASC, timestamp ASC, event_id ASC
                ''', (space_id, object_id))
                return [self._row_to_event(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_events_by_type(self, space_id: str, event_type: str) -> List[SpaceEvent]:
        """Retrieves all events of a specific type in a space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT event_id, space_id, author_id, device_id, timestamp,
                           logical_clock, event_type, object_id, payload_json,
                           ref_ids_json, signature, author_pubkey, version, received_at
                    FROM space_events
                    WHERE space_id = ? AND event_type = ?
                    ORDER BY logical_clock ASC, timestamp ASC, event_id ASC
                ''', (space_id, event_type))
                return [self._row_to_event(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_unresolved_dependencies(self, space_id: str) -> Dict[str, List[str]]:
        """
        Identifies out-of-order events whose referenced parent events have not yet arrived.
        Returns mapping: {event_id: [missing_ref_id, ...]}
        """
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT event_id, ref_ids_json FROM space_events WHERE space_id = ?', (space_id,))
                all_stored_ids = set()
                pending_checks = []
                for row in cursor.fetchall():
                    ev_id, refs_json = row
                    all_stored_ids.add(ev_id)
                    refs = json.loads(refs_json) if refs_json else []
                    if refs:
                        pending_checks.append((ev_id, refs))

                unresolved = {}
                for ev_id, refs in pending_checks:
                    missing = [r for r in refs if r not in all_stored_ids]
                    if missing:
                        unresolved[ev_id] = missing
                return unresolved
            finally:
                conn.close()

    def compute_state_digest(self, space_id: str) -> str:
        """
        Computes a deterministic SHA-256 state digest across all events in a Space.
        Used to instantly compare whether two nodes share identical event sets.
        """
        with self.lock:
            conn = self._connect()
            try:
                return self._calculate_digest(conn, space_id)
            finally:
                conn.close()

    def _calculate_digest(self, conn: sqlite3.Connection, space_id: str) -> str:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT logical_clock, timestamp, event_id, signature
            FROM space_events
            WHERE space_id = ?
            ORDER BY logical_clock ASC, timestamp ASC, event_id ASC
        ''', (space_id,))
        rows = cursor.fetchall()
        if not rows:
            return "0" * 64

        hasher = hashlib.sha256()
        for clock, ts, ev_id, sig in rows:
            chunk = f"{clock}:{ts:.6f}:{ev_id}:{sig};".encode('utf-8')
            hasher.update(chunk)
        return hasher.hexdigest().upper()

    def _update_space_state_digest(self, conn: sqlite3.Connection, space_id: str):
        digest = self._calculate_digest(conn, space_id)
        cursor = conn.cursor()
        cursor.execute('UPDATE spaces SET state_digest = ? WHERE space_id = ?', (digest, space_id))

    def get_event_count(self, space_id: str) -> int:
        """Returns total number of events recorded in a space."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM space_events WHERE space_id = ?', (space_id,))
                row = cursor.fetchone()
                return row[0] if row else 0
            finally:
                conn.close()

    def get_latest_event(self, space_id: str) -> Optional[SpaceEvent]:
        """Returns the most recent event in total order."""
        with self.lock:
            conn = self._connect()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT event_id, space_id, author_id, device_id, timestamp,
                           logical_clock, event_type, object_id, payload_json,
                           ref_ids_json, signature, author_pubkey, version, received_at
                    FROM space_events
                    WHERE space_id = ?
                    ORDER BY logical_clock DESC, timestamp DESC, event_id DESC
                    LIMIT 1
                ''', (space_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_event(row)
            finally:
                conn.close()

    @staticmethod
    def _row_to_event(row: Tuple[Any, ...]) -> SpaceEvent:
        return SpaceEvent(
            event_id=row[0],
            space_id=row[1],
            author_id=row[2],
            device_id=row[3] or "",
            timestamp=row[4],
            logical_clock=row[5],
            event_type=row[6],
            object_id=row[7],
            payload=json.loads(row[8]) if row[8] else {},
            ref_event_ids=json.loads(row[9]) if row[9] else [],
            signature=row[10],
            author_pubkey=row[11],
            version=row[12],
            received_at=row[13],
        )
