# Gost-Net Storage Architecture & Deprecation Plan

**Context:** Phase 24 — Persistence Architecture Audit  
**Version:** 1.0.0  

---

## 1. Current Storage Landscape

The Gost-Net repository currently maintains two SQLite database modules:

1. **`src/database.py` (`PersistenceDatabase`):**
   - **Status:** Authoritative Active Storage Engine.
   - **Database File:** `ghostnet_persistence.db`
   - **Features:** Write-Ahead Logging (`WAL`), `NORMAL` synchronous PRAGMA, 10-second busy timeout, Fernet encryption at rest, TTL message expiration indexing, waypoint storage, revocation lists, and in-RAM ephemeral mode.
   - **Write Path:** Drained asynchronously via a bounded FIFO persistence queue (`Queue(maxsize=2000)`) in `GhostEngine`.

2. **`src/storage.py` (`DatabaseManager`):**
   - **Status:** Legacy Compatibility Engine.
   - **Database File:** `ghostnet.db`
   - **Features:** Direct synchronous writes, unindexed TTL queries, basic Fernet encryption, and peer tracking.
   - **Callers:** Maintained for backwards compatibility with historical scripts and legacy test fixtures.

---

## 2. Migration Rationale & Safeguards

Having two independent SQLite database managers introduces technical debt, redundant disk I/O, and potential lock contention. However, **abruptly deleting or forcibly merging `storage.py` risks breaking backwards-compatibility tests and legacy headless tools**.

### Authoritative Architecture Principles
- All new network writes (`GhostEngine`) route exclusively to `PersistenceDatabase` via the persistence queue.
- No direct synchronous disk writes occur on the Kivy UI thread.
- Data integrity is preserved across application restarts.

---

## 3. Deprecation Roadmap

### Phase 1: Call-Site Audit (Current Release v1.0.0)
- All active application screens (`LockScreen`, `RadarScreen`, `ChatScreen`, `MapScreen`, `DiagnosticsScreen`) interface primarily with `PersistenceDatabase`.
- `DatabaseManager` is retained and documented as deprecated for active networking.

### Phase 2: Adapter Layer (v1.1.0 Target)
- Create a transparent wrapper inside `storage.py` where `DatabaseManager` delegates directly to an underlying `PersistenceDatabase` instance.
- Redirect legacy `ghostnet.db` operations into `ghostnet_persistence.db`.
- Provide an automatic one-time SQLite table data migration script:
  ```python
  def migrate_legacy_database(legacy_path="ghostnet.db", target_db=None):
      # Copy peers and historical messages into PersistenceDatabase
      ...
  ```

### Phase 3: Formal Removal (v2.0.0 Target)
- Remove `src/storage.py` entirely after deprecation warnings have been active for two minor release cycles.
- Single unified database: `ghostnet_persistence.db`.
