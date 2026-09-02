"""
db/connection.py — Database connection, schema creation, and migrations.
Uses Supabase (Postgres) when Streamlit secrets are available,
falls back to local SQLite for development.
"""

import os

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_pg_config() -> dict | None:
    """Try to load Postgres config from Streamlit secrets."""
    try:
        import streamlit as st
        db_conf = st.secrets.get("database")
        if db_conf and db_conf.get("host"):
            return dict(db_conf)
    except FileNotFoundError:
        pass  # no secrets file — expected in local dev
    except Exception:
        pass
    return None


_pg_pool = None


def _get_pool():
    """Get or create the Postgres connection pool (cached globally)."""
    global _pg_pool
    if _pg_pool is None:
        config = _get_pg_config()
        if config:
            import psycopg2.pool
            _pg_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                host=config["host"],
                port=config.get("port", 5432),
                dbname=config.get("dbname", "postgres"),
                user=config.get("user", "postgres"),
                password=config["password"],
            )
    return _pg_pool


def get_connection():
    """
    Return a database connection.
    - If Streamlit secrets have a [database] section → pooled Postgres
    - Otherwise → local SQLite (for development / testing)
    """
    pool = _get_pool()
    if pool:
        conn = pool.getconn()
        conn.autocommit = True
        return conn
    else:
        return _sqlite_connect()


def release_connection(conn):
    """Return a Postgres connection to the pool, or close SQLite."""
    pool = _get_pool()
    if pool:
        try:
            pool.putconn(conn)
        except Exception:
            pass
    else:
        conn.close()


def _sqlite_connect():
    """Fallback: local SQLite for development."""
    import sqlite3
    db_path = os.getenv("XC_DB_PATH", "xc_app.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _is_postgres() -> bool:
    """Check if we're using Postgres."""
    return _get_pg_config() is not None


# ---------------------------------------------------------------------------
# Query helpers — smooth over SQLite vs Postgres differences
# ---------------------------------------------------------------------------

def execute(conn, sql: str, params: tuple = ()):
    """Execute a query, adapting placeholders for the current backend."""
    cur = _cursor(conn)
    cur.execute(_adapt_sql(sql), params)
    return cur


def executemany(conn, sql: str, params_list: list):
    """Execute a query with many parameter sets."""
    cur = _cursor(conn)
    cur.executemany(_adapt_sql(sql), params_list)
    return cur


def fetchone(conn, sql: str, params: tuple = ()) -> dict | None:
    """Execute and fetch one row as a dict."""
    cur = execute(conn, sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def fetchall(conn, sql: str, params: tuple = ()) -> list[dict]:
    """Execute and fetch all rows as dicts."""
    cur = execute(conn, sql, params)
    rows = cur.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    return [dict(r) for r in rows]


def insert_returning_id(conn, sql: str, params: tuple = ()) -> int:
    """Execute an INSERT and return the new row's id.
    Appends RETURNING id for Postgres; uses lastrowid for SQLite."""
    if _is_postgres():
        adapted = _adapt_sql(sql)
        if "RETURNING" not in adapted.upper():
            adapted = adapted.rstrip().rstrip(";") + " RETURNING id"
        cur = _cursor(conn)
        cur.execute(adapted, params)
        return cur.fetchone()["id"]
    else:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.lastrowid


def _cursor(conn):
    """Get an appropriate cursor for the connection type."""
    try:
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except (ImportError, Exception):
        return conn.cursor()


def _adapt_sql(sql: str) -> str:
    """Convert ? placeholders to %s for Postgres."""
    if _is_postgres():
        return sql.replace("?", "%s")
    return sql


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS school (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete (
    id         SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    grade      INTEGER NOT NULL CHECK (grade IN (6, 7, 8)),
    gender     TEXT NOT NULL CHECK (gender IN ('M', 'F')),
    school_id  INTEGER NOT NULL REFERENCES school(id),
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'injured', 'inactive', 'alumni'))
);

CREATE TABLE IF NOT EXISTS season (
    id        SERIAL PRIMARY KEY,
    year      INTEGER NOT NULL,
    sport     TEXT NOT NULL DEFAULT 'XC',
    school_id INTEGER NOT NULL REFERENCES school(id)
);

CREATE TABLE IF NOT EXISTS season_roster (
    id         SERIAL PRIMARY KEY,
    season_id  INTEGER NOT NULL REFERENCES season(id),
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    UNIQUE (season_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS meet (
    id             SERIAL PRIMARY KEY,
    season_id      INTEGER NOT NULL REFERENCES season(id),
    name           TEXT NOT NULL,
    meet_date      TEXT NOT NULL,
    location       TEXT NOT NULL,
    host_school_id INTEGER NOT NULL REFERENCES school(id),
    girls_place    TEXT,
    boys_place     TEXT,
    milesplit_url  TEXT
);

CREATE TABLE IF NOT EXISTS race (
    id      SERIAL PRIMARY KEY,
    meet_id INTEGER NOT NULL REFERENCES meet(id),
    gender  TEXT NOT NULL CHECK (gender IN ('M', 'F', 'combined')),
    level   TEXT NOT NULL DEFAULT 'varsity'
                CHECK (level IN ('varsity', 'jv', 'combined'))
);

CREATE TABLE IF NOT EXISTS track_event (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    event_type  TEXT NOT NULL DEFAULT 'running'
                    CHECK (event_type IN ('running', 'field', 'relay')),
    gender      TEXT NOT NULL DEFAULT 'M'
                    CHECK (gender IN ('M', 'F', 'combined')),
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_assignment (
    id         SERIAL PRIMARY KEY,
    season_id  INTEGER NOT NULL REFERENCES season(id),
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    event_id   INTEGER NOT NULL REFERENCES track_event(id),
    UNIQUE (season_id, athlete_id, event_id)
);

CREATE TABLE IF NOT EXISTS track_result (
    id           SERIAL PRIMARY KEY,
    meet_id      INTEGER NOT NULL REFERENCES meet(id),
    athlete_id   INTEGER NOT NULL REFERENCES athlete(id),
    event_id     INTEGER NOT NULL REFERENCES track_event(id),
    result_value TEXT NOT NULL,
    is_pr        INTEGER NOT NULL DEFAULT 0,
    place        INTEGER,
    UNIQUE (meet_id, athlete_id, event_id)
);

CREATE TABLE IF NOT EXISTS lineup_entry (
    id         SERIAL PRIMARY KEY,
    meet_id    INTEGER NOT NULL REFERENCES meet(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    event_id   INTEGER NOT NULL REFERENCES track_event(id),
    UNIQUE (meet_id, athlete_id, event_id)
);

CREATE TABLE IF NOT EXISTS race_entry (
    id         SERIAL PRIMARY KEY,
    race_id    INTEGER NOT NULL REFERENCES race(id),
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    seed_time  TEXT,
    bib_number INTEGER,
    UNIQUE (race_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS result (
    id             SERIAL PRIMARY KEY,
    race_entry_id  INTEGER NOT NULL UNIQUE REFERENCES race_entry(id),
    finish_place   INTEGER NOT NULL,
    finish_time    TEXT NOT NULL,
    is_pr          INTEGER NOT NULL DEFAULT 0,
    team_points    INTEGER
);

CREATE TABLE IF NOT EXISTS xc_result (
    id           SERIAL PRIMARY KEY,
    meet_id      INTEGER NOT NULL REFERENCES meet(id),
    athlete_id   INTEGER NOT NULL REFERENCES athlete(id),
    finish_time  TEXT NOT NULL,
    place        INTEGER,
    distance     TEXT NOT NULL DEFAULT '2mi',
    is_pr        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (meet_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS workout_group (
    id         SERIAL PRIMARY KEY,
    season_id  INTEGER NOT NULL REFERENCES season(id),
    name       TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workout_group_member (
    id         SERIAL PRIMARY KEY,
    group_id   INTEGER NOT NULL REFERENCES workout_group(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    UNIQUE (group_id, athlete_id)
);
"""

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS school (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    grade      INTEGER NOT NULL CHECK (grade IN (6, 7, 8)),
    gender     TEXT NOT NULL CHECK (gender IN ('M', 'F')),
    school_id  INTEGER NOT NULL REFERENCES school(id),
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'injured', 'inactive', 'alumni'))
);

CREATE TABLE IF NOT EXISTS season (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    year      INTEGER NOT NULL,
    sport     TEXT NOT NULL DEFAULT 'XC',
    school_id INTEGER NOT NULL REFERENCES school(id)
);

CREATE TABLE IF NOT EXISTS season_roster (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id  INTEGER NOT NULL REFERENCES season(id),
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    UNIQUE (season_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS meet (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id      INTEGER NOT NULL REFERENCES season(id),
    name           TEXT NOT NULL,
    meet_date      TEXT NOT NULL,
    location       TEXT NOT NULL,
    host_school_id INTEGER NOT NULL REFERENCES school(id),
    girls_place    TEXT,
    boys_place     TEXT,
    milesplit_url  TEXT
);

CREATE TABLE IF NOT EXISTS race (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    meet_id INTEGER NOT NULL REFERENCES meet(id),
    gender  TEXT NOT NULL CHECK (gender IN ('M', 'F', 'combined')),
    level   TEXT NOT NULL DEFAULT 'varsity'
                CHECK (level IN ('varsity', 'jv', 'combined'))
);

CREATE TABLE IF NOT EXISTS track_event (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    event_type  TEXT NOT NULL DEFAULT 'running'
                    CHECK (event_type IN ('running', 'field', 'relay')),
    gender      TEXT NOT NULL DEFAULT 'M'
                    CHECK (gender IN ('M', 'F', 'combined')),
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_assignment (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id  INTEGER NOT NULL REFERENCES season(id),
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    event_id   INTEGER NOT NULL REFERENCES track_event(id),
    UNIQUE (season_id, athlete_id, event_id)
);

CREATE TABLE IF NOT EXISTS track_result (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    meet_id      INTEGER NOT NULL REFERENCES meet(id),
    athlete_id   INTEGER NOT NULL REFERENCES athlete(id),
    event_id     INTEGER NOT NULL REFERENCES track_event(id),
    result_value TEXT NOT NULL,
    is_pr        INTEGER NOT NULL DEFAULT 0,
    place        INTEGER,
    UNIQUE (meet_id, athlete_id, event_id)
);

CREATE TABLE IF NOT EXISTS lineup_entry (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    meet_id    INTEGER NOT NULL REFERENCES meet(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    event_id   INTEGER NOT NULL REFERENCES track_event(id),
    UNIQUE (meet_id, athlete_id, event_id)
);

CREATE TABLE IF NOT EXISTS race_entry (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id    INTEGER NOT NULL REFERENCES race(id),
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    seed_time  TEXT,
    bib_number INTEGER,
    UNIQUE (race_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS result (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    race_entry_id  INTEGER NOT NULL UNIQUE REFERENCES race_entry(id),
    finish_place   INTEGER NOT NULL,
    finish_time    TEXT NOT NULL,
    is_pr          INTEGER NOT NULL DEFAULT 0,
    team_points    INTEGER
);

CREATE TABLE IF NOT EXISTS xc_result (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    meet_id      INTEGER NOT NULL REFERENCES meet(id),
    athlete_id   INTEGER NOT NULL REFERENCES athlete(id),
    finish_time  TEXT NOT NULL,
    place        INTEGER,
    distance     TEXT NOT NULL DEFAULT '2mi',
    is_pr        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (meet_id, athlete_id)
);

CREATE TABLE IF NOT EXISTS workout_group (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id  INTEGER NOT NULL REFERENCES season(id),
    name       TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workout_group_member (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL REFERENCES workout_group(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athlete(id),
    UNIQUE (group_id, athlete_id)
);
"""


def create_tables() -> None:
    """Create all tables if they don't already exist."""
    conn = get_connection()
    try:
        if _is_postgres():
            cur = _cursor(conn)
            cur.execute(_PG_SCHEMA)
        else:
            conn.executescript(_SQLITE_SCHEMA)
    finally:
        release_connection(conn)


DEFAULT_TRACK_EVENTS = [
    ("100m",         "running", "M",  1),
    ("200m",         "running", "M",  2),
    ("400m",         "running", "M",  3),
    ("800m",         "running", "M",  4),
    ("1600m",        "running", "M",  5),
    ("110m Hurdles", "running", "M",  6),
    ("300m Hurdles", "running", "M",  7),
    ("4x100 Relay",  "relay",   "M",  8),
    ("4x200 Relay",  "relay",   "M",  9),
    ("4x400 Relay",  "relay",   "M", 10),
    ("100m",         "running", "F", 11),
    ("200m",         "running", "F", 12),
    ("400m",         "running", "F", 13),
    ("800m",         "running", "F", 14),
    ("1600m",        "running", "F", 15),
    ("100m Hurdles", "running", "F", 16),
    ("300m Hurdles", "running", "F", 17),
    ("4x100 Relay",  "relay",   "F", 18),
    ("4x200 Relay",  "relay",   "F", 19),
    ("4x400 Relay",  "relay",   "F", 20),
    ("Long Jump",    "field",   "M", 21),
    ("Triple Jump",  "field",   "M", 22),
    ("High Jump",    "field",   "M", 23),
    ("Shot Put",     "field",   "M", 24),
    ("Discus",       "field",   "M", 25),
    ("Long Jump",    "field",   "F", 26),
    ("Triple Jump",  "field",   "F", 27),
    ("High Jump",    "field",   "F", 28),
    ("Shot Put",     "field",   "F", 29),
    ("Discus",       "field",   "F", 30),
]


def seed_default_track_events() -> None:
    """Insert default track events if the table is empty."""
    conn = get_connection()
    try:
        count = fetchone(conn, "SELECT COUNT(*) AS cnt FROM track_event")["cnt"]
        if count == 0:
            for ev in DEFAULT_TRACK_EVENTS:
                execute(conn,
                    """INSERT INTO track_event (name, event_type, gender, sort_order)
                       VALUES (?, ?, ?, ?)""", ev)
    finally:
        release_connection(conn)


def migrate_track_events() -> None:
    """Idempotent migration to fix the track_event table."""
    conn = get_connection()
    try:
        execute(conn,
            """UPDATE track_event SET name='110m Hurdles'
               WHERE name='100m Hurdles' AND gender='M'""")
        execute(conn, "DELETE FROM track_event WHERE name='3200m'")
        execute(conn, "DELETE FROM track_event WHERE name='400m Hurdles'")

        for gender, sort_order in [("M", 8), ("F", 18)]:
            row = fetchone(conn,
                """SELECT COUNT(*) AS cnt FROM track_event
                   WHERE name='300m Hurdles' AND gender=?""",
                (gender,))
            if row["cnt"] == 0:
                execute(conn,
                    """INSERT INTO track_event
                       (name, event_type, gender, sort_order)
                       VALUES ('300m Hurdles', 'running', ?, ?)""",
                    (gender, sort_order))

        for gender, sort_order in [("M", 9), ("F", 19)]:
            row = fetchone(conn,
                """SELECT COUNT(*) AS cnt FROM track_event
                   WHERE name='4x200 Relay' AND gender=?""",
                (gender,))
            if row["cnt"] == 0:
                execute(conn,
                    """INSERT INTO track_event
                       (name, event_type, gender, sort_order)
                       VALUES ('4x200 Relay', 'relay', ?, ?)""",
                    (gender, sort_order))
    finally:
        release_connection(conn)


def migrate_meet_columns() -> None:
    """Add girls_place, boys_place, milesplit_url to meet table if missing."""
    conn = get_connection()
    try:
        if _is_postgres():
            for col, typedef in [
                ("girls_place", "TEXT"),
                ("boys_place", "TEXT"),
                ("milesplit_url", "TEXT"),
            ]:
                try:
                    execute(conn,
                        f"ALTER TABLE meet ADD COLUMN {col} {typedef}")
                except Exception:
                    pass  # column already exists
        else:
            existing = [
                row[1] for row in
                conn.execute("PRAGMA table_info(meet)").fetchall()
            ]
            for col, typedef in [
                ("girls_place", "TEXT"),
                ("boys_place", "TEXT"),
                ("milesplit_url", "TEXT"),
            ]:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE meet ADD COLUMN {col} {typedef}")
    finally:
        release_connection(conn)


def migrate_long_event_times() -> None:
    """Fix tryout times for 400m/800m/1600m stored without proper M:SS format.

    400m & 800m: M.SS pattern (e.g. '1.07' → '1:07.00', '3.28' → '3:28.00')
    1600m: true decimal minutes (e.g. '6.1' → '6:06.00', '5.75' → '5:45.00')
    """
    import re
    conn = get_connection()
    try:
        # --- 400m and 800m: M.SS pattern (minutes.seconds) ---
        mss_events = fetchall(conn,
            "SELECT id FROM track_event WHERE name IN ('400m', '800m')")
        for ev in mss_events:
            results = fetchall(conn,
                "SELECT id, result_value FROM track_result WHERE event_id=?",
                (ev["id"],))
            for r in results:
                val = r["result_value"]
                if ":" in val:
                    continue  # already formatted
                m = re.match(r"^(\d+)\.(\d{2})$", val)
                if m:
                    minutes = int(m.group(1))
                    seconds = int(m.group(2))
                    if 0 < minutes <= 20 and seconds < 60:
                        new_val = f"{minutes}:{seconds:02d}.00"
                        execute(conn,
                            "UPDATE track_result SET result_value=? WHERE id=?",
                            (new_val, r["id"]))

        # --- 1600m: true decimal minutes (e.g. 6.1 = 6 min 6 sec) ---
        m16_events = fetchall(conn,
            "SELECT id FROM track_event WHERE name='1600m'")
        for ev in m16_events:
            results = fetchall(conn,
                "SELECT id, result_value FROM track_result WHERE event_id=?",
                (ev["id"],))
            for r in results:
                val = r["result_value"]
                if ":" in val:
                    continue  # already formatted
                m = re.match(r"^(\d+(?:\.\d+)?)$", val)
                if m:
                    total_minutes = float(m.group(1))
                    if 0 < total_minutes <= 20:
                        whole_minutes = int(total_minutes)
                        frac_seconds = (total_minutes - whole_minutes) * 60
                        seconds = round(frac_seconds, 2)
                        new_val = f"{whole_minutes}:{seconds:05.2f}"
                        execute(conn,
                            "UPDATE track_result SET result_value=? WHERE id=?",
                            (new_val, r["id"]))
    finally:
        release_connection(conn)


def migrate_recalculate_prs() -> None:
    """Recalculate all is_pr flags after time format migrations."""
    from db.results import recalculate_pr_flags
    recalculate_pr_flags()


def migrate_alumni_status() -> None:
    """Add 'alumni' to the athlete status CHECK constraint."""
    conn = get_connection()
    try:
        if _is_postgres():
            row = fetchone(conn,
                """SELECT 1 FROM information_schema.check_constraints
                   WHERE constraint_name = 'athlete_status_check'
                     AND check_clause LIKE ?""", ('%alumni%',))
            if not row:
                execute(conn, "ALTER TABLE athlete DROP CONSTRAINT IF EXISTS athlete_status_check")
                execute(conn,
                    """ALTER TABLE athlete ADD CONSTRAINT athlete_status_check
                       CHECK (status IN ('active', 'injured', 'inactive', 'alumni'))""")
            return

        row = fetchone(conn,
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='athlete'")
        if not row or "alumni" in row["sql"]:
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        execute(conn, """CREATE TABLE athlete_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            grade      INTEGER NOT NULL CHECK (grade IN (6, 7, 8)),
            gender     TEXT NOT NULL CHECK (gender IN ('M', 'F')),
            school_id  INTEGER NOT NULL REFERENCES school(id),
            status     TEXT NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active', 'injured', 'inactive', 'alumni'))
        )""")
        execute(conn, "INSERT INTO athlete_new SELECT * FROM athlete")
        execute(conn, "DROP TABLE athlete")
        execute(conn, "ALTER TABLE athlete_new RENAME TO athlete")
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        release_connection(conn)


_db_initialized = False

def init_db() -> None:
    """Create tables, seed default events, run migrations, create default school.
    Skips if already run this process."""
    global _db_initialized
    if _db_initialized:
        return
    create_tables()
    seed_default_track_events()
    migrate_track_events()
    migrate_meet_columns()
    migrate_long_event_times()
    migrate_recalculate_prs()
    migrate_alumni_status()
    conn = get_connection()
    try:
        row = fetchone(conn, "SELECT COUNT(*) AS cnt FROM school")
        if row["cnt"] == 0:
            execute(conn,
                "INSERT INTO school (name, city) VALUES (?, ?)",
                ("My School", "My City"))
    finally:
        release_connection(conn)
    _db_initialized = True
