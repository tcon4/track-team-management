"""db/athlete.py — Athlete CRUD, roster management, CSV/tryout import."""

import csv
import io
import re

import streamlit as st
from db.connection import get_connection, release_connection, fetchall, fetchone, execute, insert_returning_id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def get_athletes(school_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT * FROM athlete
               WHERE school_id = ?
               ORDER BY last_name, first_name""",
            (school_id,))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_roster(season_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT a.*
               FROM athlete a
               JOIN season_roster sr ON sr.athlete_id = a.id
               WHERE sr.season_id = ?
               ORDER BY a.last_name, a.first_name""",
            (season_id,))
    finally:
        release_connection(conn)


def add_athlete(first_name: str, last_name: str, grade: int,
                gender: str, school_id: int) -> int:
    conn = get_connection()
    try:
        return insert_returning_id(conn,
            """INSERT INTO athlete (first_name, last_name, grade, gender, school_id)
               VALUES (?, ?, ?, ?, ?)""",
            (first_name.strip(), last_name.strip(), grade, gender, school_id))
    finally:
        release_connection(conn)


def update_athlete(athlete_id: int, first_name: str, last_name: str,
                   grade: int, gender: str, status: str) -> None:
    conn = get_connection()
    try:
        execute(conn,
            """UPDATE athlete
               SET first_name=?, last_name=?, grade=?, gender=?, status=?
               WHERE id=?""",
            (first_name.strip(), last_name.strip(), grade, gender, status, athlete_id))
    finally:
        release_connection(conn)


def add_to_roster(season_id: int, athlete_id: int) -> None:
    conn = get_connection()
    try:
        execute(conn,
            """INSERT INTO season_roster (season_id, athlete_id)
               VALUES (?, ?)
               ON CONFLICT (season_id, athlete_id) DO NOTHING""",
            (season_id, athlete_id))
    finally:
        release_connection(conn)


def remove_from_roster(season_id: int, athlete_id: int) -> None:
    conn = get_connection()
    try:
        execute(conn,
            "DELETE FROM season_roster WHERE season_id=? AND athlete_id=?",
            (season_id, athlete_id))
    finally:
        release_connection(conn)


def get_roster_stats(season_id: int) -> dict:
    roster = get_roster(season_id)
    return {
        "total":    len(roster),
        "active":   sum(1 for a in roster if a["status"] == "active"),
        "injured":  sum(1 for a in roster if a["status"] == "injured"),
        "inactive": sum(1 for a in roster if a["status"] == "inactive"),
        "alumni":   sum(1 for a in roster if a["status"] == "alumni"),
    }


def graduate_athletes(season_id: int) -> int:
    """Mark 8th-grade athletes on this season's roster as alumni.

    Only affects athletes currently status='active'. Returns count updated.
    """
    conn = get_connection()
    try:
        cur = execute(conn,
            """UPDATE athlete SET status='alumni'
               WHERE id IN (
                   SELECT athlete_id FROM season_roster WHERE season_id=?
               )
               AND grade = 8 AND status = 'active'""",
            (season_id,))
        return cur.rowcount
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# CSV roster import
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {"first_name", "last_name", "grade", "gender"}

COLUMN_ALIASES = {
    "first":        "first_name",
    "firstname":    "first_name",
    "first name":   "first_name",
    "last":         "last_name",
    "lastname":     "last_name",
    "last name":    "last_name",
    "yr":           "grade",
    "year":         "grade",
    "grade level":  "grade",
    "sex":          "gender",
    "m/f":          "gender",
}

GENDER_ALIASES = {
    "m": "M", "male": "M", "boy": "M", "boys": "M",
    "f": "F", "female": "F", "girl": "F", "girls": "F",
}


def _normalize_headers(headers: list[str]) -> dict[str, str]:
    mapping = {}
    for h in headers:
        key = h.strip().lower()
        canonical = COLUMN_ALIASES.get(key, key.replace(" ", "_"))
        mapping[h] = canonical
    return mapping


def parse_roster_csv(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse a CSV into validated athlete rows ready for preview."""
    errors = []
    rows = []

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["CSV file appears to be empty."]

    col_map = _normalize_headers(list(reader.fieldnames))
    canonical_cols = set(col_map.values())
    missing = REQUIRED_COLUMNS - canonical_cols

    if missing:
        return [], [
            f"Missing required columns: {', '.join(sorted(missing))}. "
            f"Expected: first_name, last_name, grade, gender. "
            f"Found: {', '.join(reader.fieldnames)}"
        ]

    for i, raw_row in enumerate(reader, start=2):
        row = {col_map[k]: v.strip() for k, v in raw_row.items() if k in col_map}

        try:
            grade = int(row.get("grade", ""))
            if grade not in (6, 7, 8):
                errors.append(f"Row {i}: grade must be 6, 7, or 8 (got '{grade}')")
                continue
        except ValueError:
            errors.append(f"Row {i}: invalid grade '{row.get('grade', '')}'")
            continue

        gender_raw = row.get("gender", "").strip().lower()
        gender = GENDER_ALIASES.get(gender_raw)
        if not gender:
            errors.append(
                f"Row {i}: unrecognised gender '{row.get('gender', '')}' "
                f"— use M/F, Male/Female, Boy/Girl"
            )
            continue

        first = row.get("first_name", "").strip()
        last = row.get("last_name", "").strip()
        if not first or not last:
            errors.append(f"Row {i}: missing first or last name")
            continue

        rows.append({
            "first_name": first,
            "last_name":  last,
            "grade":      grade,
            "gender":     gender,
        })

    return rows, errors


def import_roster_from_rows(rows: list[dict], school_id: int,
                             season_id: int) -> dict:
    """Insert pre-validated athlete rows and add them to the season roster."""
    added = skipped = 0

    conn = get_connection()
    try:
        for row in rows:
            existing = fetchone(conn,
                """SELECT id FROM athlete
                   WHERE LOWER(first_name)=LOWER(?)
                     AND LOWER(last_name)=LOWER(?)
                     AND school_id=?""",
                (row["first_name"], row["last_name"], school_id))

            if existing:
                athlete_id = existing["id"]
                skipped += 1
            else:
                athlete_id = insert_returning_id(conn,
                    """INSERT INTO athlete
                       (first_name, last_name, grade, gender, school_id)
                       VALUES (?,?,?,?,?)""",
                    (row["first_name"], row["last_name"],
                     row["grade"], row["gender"], school_id))
                added += 1

            execute(conn,
                """INSERT INTO season_roster (season_id, athlete_id) VALUES (?,?)
                   ON CONFLICT (season_id, athlete_id) DO NOTHING""",
                (season_id, athlete_id))
    finally:
        release_connection(conn)

    return {"added": added, "skipped": skipped}


def generate_csv_template() -> str:
    return "first_name,last_name,grade,gender\nJane,Smith,8,F\nMarcus,Johnson,7,M\n"


# ---------------------------------------------------------------------------
# Normalization helpers (for tryout import)
# ---------------------------------------------------------------------------

def _normalize_field_mark(val: str) -> str | None:
    """Normalize a field event mark to feet-inches format (18-5.50)."""
    val = val.strip().replace('"', '').replace('\u2019', "'")

    m = re.match(r"^(\d+)'(\d+(?:\.\d+)?)$", val)
    if m:
        feet, inches = int(m.group(1)), float(m.group(2))
        return f"{feet}-{inches:.2f}"

    m = re.match(r"^(\d+)-(\d+(?:\.\d+)?)$", val)
    if m:
        feet, inches = int(m.group(1)), float(m.group(2))
        return f"{feet}-{inches:.2f}"

    m = re.match(r"^(\d+\.\d+)$", val)
    if m:
        meters = float(m.group(1))
        total_inches = meters * 39.3701
        feet = int(total_inches // 12)
        inches = total_inches % 12
        return f"{feet}-{inches:.2f}"

    return None


# Events where bare decimals represent minutes, not seconds
_MSS_EVENTS = {"400", "400m", "800", "800m"}  # M.SS pattern (1.07 = 1:07)
_DECIMAL_MIN_EVENTS = {"1600", "1600m"}  # true decimal minutes (6.1 = 6:06)

def _normalize_time(val: str, event: str) -> str | None:
    """Normalize a time value to MM:SS.ss or SS.ss format.
    For 400m/800m, a value like '1.07' is treated as 1:07 (M.SS).
    For 1600m, a value like '6.1' is treated as 6.1 minutes = 6:06."""
    val = val.strip()
    if not val or val.lower() in ("nan", "\u2014", "-", ""):
        return None

    event_key = event.strip().lower().replace("m", "")

    # Already in M:SS or M:SS.ss format
    m = re.match(r"^(\d+):(\d{2}):(\d{2})$", val)
    if m:
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        if minutes > 0:
            return f"{minutes}:{seconds:02d}.00"
        else:
            return f"{seconds}.00"

    m = re.match(r"^(\d+):(\d{2}(?:\.\d+)?)$", val)
    if m:
        return val

    # 1600m: true decimal minutes (6.1 = 6 min 6 sec)
    if event_key in {e.replace("m", "") for e in _DECIMAL_MIN_EVENTS}:
        m = re.match(r"^(\d+(?:\.\d+)?)$", val)
        if m:
            total_minutes = float(m.group(1))
            if 0 < total_minutes <= 20:
                whole_minutes = int(total_minutes)
                frac_seconds = (total_minutes - whole_minutes) * 60
                seconds = round(frac_seconds, 2)
                return f"{whole_minutes}:{seconds:05.2f}"

    # 400m/800m: M.SS pattern (1.07 = 1:07.00)
    if event_key in {e.replace("m", "") for e in _MSS_EVENTS}:
        m = re.match(r"^(\d+)\.(\d{2})$", val)
        if m:
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            if minutes > 0 and seconds < 60:
                return f"{minutes}:{seconds:02d}.00"

    m = re.match(r"^\d+(?:\.\d+)?$", val)
    if m:
        return val

    return None


# ---------------------------------------------------------------------------
# Tryout spreadsheet import
# ---------------------------------------------------------------------------

def parse_tryout_spreadsheet(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Generic tryout spreadsheet parser."""
    try:
        import pandas as pd
    except ImportError:
        return [], ["pandas is required: pip install pandas openpyxl"]

    errors = []
    rows = []

    try:
        xl = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, dtype=str)
    except Exception as e:
        return [], [f"Could not read spreadsheet: {e}"]

    TIME_COL_MAP = {
        "100": "100m", "200": "200m", "400": "400m",
        "800": "800m", "1600": "1600m",
    }

    FIELD_COL_MAP = {
        "shot": "Shot Put",
        "discus": "Discus",
        "long jump": "Long Jump",
        "triple jump": "Triple Jump",
        "high jump": "High Jump",
        "long": "Long Jump",
        "triple": "Triple Jump",
        "high": "High Jump",
        "jump": "Long Jump",
    }

    FLAG_VALUES = {"y", "yes", "x", "\u2713", "true", "1"}

    def clean_col_name(col) -> str:
        s = str(col).strip()
        if re.search(r"190[01]-0[12]-0[234]", s):
            return "400"
        return s

    def detect_gender_from_tab(tab: str) -> str | None:
        t = tab.lower()
        if any(x in t for x in ("girl", " f", "_f", "female")):
            return "F"
        if any(x in t for x in ("boy", " m", "_m", "male")):
            return "M"
        return None

    def detect_grade_from_tab(tab: str) -> int | None:
        m = re.search(r'\b([678])\b', tab)
        return int(m.group(1)) if m else None

    def cell_val(row, col) -> str:
        v = str(row.get(col, "") or "").strip()
        return "" if v.lower() == "nan" else v

    for sheet_name, df in xl.items():
        if "cut" in sheet_name.lower() and len(sheet_name) < 8:
            continue

        df.columns = [clean_col_name(c) for c in df.columns]
        cols = list(df.columns)
        col_lower = {c.lower(): c for c in cols}

        def find_col(*names) -> str | None:
            for n in names:
                if n.lower() in col_lower:
                    return col_lower[n.lower()]
            return None

        first_col = find_col("first name", "firstname", "first")
        last_col = find_col("last name", "lastname", "last")
        if not first_col or not last_col:
            errors.append(
                f"Tab '{sheet_name}': no First/Last Name columns found — skipping."
            )
            continue

        grade_col = find_col("grade", "gr", "gr.")
        cut_col = find_col("cut?", "cut", "cuts", "cut ?")
        gender_col = find_col("gender", "sex", "m/f", "g/b")

        tab_gender = detect_gender_from_tab(sheet_name)
        tab_grade = detect_grade_from_tab(sheet_name)

        time_cols: dict[str, str] = {}
        for col in cols:
            for key, event in TIME_COL_MAP.items():
                if re.fullmatch(key, col.strip()):
                    time_cols[col] = event
                    break

        field_cols: dict[str, str] = {}
        for col in cols:
            cl = col.lower().strip()
            for keyword, event in FIELD_COL_MAP.items():
                if keyword in cl:
                    field_cols[col] = event
                    break

        for _, row in df.iterrows():
            first = cell_val(row, first_col)
            last = cell_val(row, last_col)
            if not first or not last:
                continue

            if cut_col:
                cut_raw = cell_val(row, cut_col).lower()
                if cut_raw in FLAG_VALUES:
                    continue

            gender = tab_gender
            if gender_col:
                g = cell_val(row, gender_col).upper()
                if g in ("G", "F", "GIRL", "GIRLS", "FEMALE"):
                    gender = "F"
                elif g in ("B", "M", "BOY", "BOYS", "MALE"):
                    gender = "M"

            if not gender:
                errors.append(
                    f"Tab '{sheet_name}': can't determine gender for "
                    f"{first} {last} — skipping."
                )
                continue

            grade = tab_grade or 7
            if grade_col:
                try:
                    g = int(float(cell_val(row, grade_col) or "0"))
                    if g in (6, 7, 8):
                        grade = g
                except ValueError:
                    pass

            results = []
            event_names = []

            for col, event in time_cols.items():
                raw = cell_val(row, col)
                if not raw:
                    continue
                normalized = _normalize_time(raw, event)
                if normalized:
                    results.append({"event": event, "value": normalized})
                    if event not in event_names:
                        event_names.append(event)

            for col, event in field_cols.items():
                raw = cell_val(row, col)
                if not raw:
                    continue
                if raw.lower() in FLAG_VALUES:
                    if event not in event_names:
                        event_names.append(event)
                else:
                    mark = _normalize_field_mark(raw)
                    if mark:
                        results.append({"event": event, "value": mark})
                        if event not in event_names:
                            event_names.append(event)

            rows.append({
                "cut":        False,
                "first_name": first,
                "last_name":  last,
                "grade":      grade,
                "gender":     gender,
                "events":     event_names,
                "results":    results,
            })

    return rows, errors


def import_tryout_data(preview_rows: list[dict], school_id: int,
                       season_id: int) -> dict:
    """Import tryout data from parsed preview rows."""
    from db.events import match_event_by_number, get_track_events, get_athlete_events, assign_event
    from db.results import save_track_result

    athletes_added = results_saved = assignments_added = 0

    conn = get_connection()
    try:
        season_row = fetchone(conn,
            "SELECT * FROM season WHERE id=?", (season_id,))
        year = season_row["year"] if season_row else 2026

        tryout_meet = fetchone(conn,
            """SELECT id FROM meet WHERE season_id=? AND name='Tryouts'""",
            (season_id,))

        if not tryout_meet:
            tryout_meet_id = insert_returning_id(conn,
                """INSERT INTO meet
                   (season_id, name, meet_date, location, host_school_id)
                   VALUES (?,?,?,?,?)""",
                (season_id, "Tryouts", f"{year}-01-01",
                 "School Track", school_id))
        else:
            tryout_meet_id = tryout_meet["id"]
    finally:
        release_connection(conn)

    all_events = get_track_events()

    for r in preview_rows:
        if r.get("cut"):
            continue

        conn = get_connection()
        try:
            existing = fetchone(conn,
                """SELECT a.id FROM athlete a
                   JOIN season_roster sr ON sr.athlete_id = a.id
                   WHERE sr.season_id=?
                   AND UPPER(a.first_name)=UPPER(?)
                   AND UPPER(a.last_name)=UPPER(?)""",
                (season_id, r["first_name"], r["last_name"]))
        finally:
            release_connection(conn)

        if existing:
            aid = existing["id"]
        else:
            aid = add_athlete(
                r["first_name"], r["last_name"],
                r["grade"], r["gender"], school_id)
            add_to_roster(season_id, aid)
            athletes_added += 1

        for res in r.get("results", []):
            matched_ev = match_event_by_number(res["event"], r["gender"], all_events)
            if matched_ev:
                try:
                    save_track_result(
                        meet_id=tryout_meet_id,
                        athlete_id=aid,
                        event_id=matched_ev["id"],
                        result_value=res["value"],
                    )
                    results_saved += 1
                except Exception:
                    pass

                existing_evs = get_athlete_events(aid, season_id)
                if not any(e["id"] == matched_ev["id"] for e in existing_evs):
                    assign_event(aid, season_id, matched_ev["id"])
                    assignments_added += 1

        for ev_name in r.get("events", []):
            if ev_name in ("Long Jump", "Triple Jump", "High Jump",
                           "Shot Put", "Discus"):
                matched_ev = match_event_by_number(ev_name, r["gender"], all_events)
                if matched_ev:
                    existing_evs = get_athlete_events(aid, season_id)
                    if not any(e["id"] == matched_ev["id"] for e in existing_evs):
                        assign_event(aid, season_id, matched_ev["id"])
                        assignments_added += 1

    return {
        "athletes":    athletes_added,
        "results":     results_saved,
        "assignments": assignments_added,
    }
