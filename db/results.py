"""db/results.py — Track results, PR detection, and season bests."""

import streamlit as st
from db.connection import get_connection, release_connection, fetchall, fetchone, execute


def _parse_result(value: str) -> float:
    """
    Convert result strings to float for comparison.
    Handles: "11.24", "1:54.3", "5.82m", "18-04"
    """
    v = value.strip().rstrip("m").strip()
    if ":" in v:
        parts = v.split(":")
        return int(parts[0]) * 60 + float(parts[1])
    if "-" in v and not v.startswith("-"):
        feet, inches = v.split("-", 1)
        return int(feet) * 12 + float(inches)
    return float(v)


def is_track_pr(athlete_id: int, event_id: int, new_value: str) -> bool:
    conn = get_connection()
    try:
        event = fetchone(conn,
            "SELECT event_type FROM track_event WHERE id=?", (event_id,))
        rows = fetchall(conn,
            "SELECT result_value FROM track_result WHERE athlete_id=? AND event_id=?",
            (athlete_id, event_id))
    finally:
        release_connection(conn)

    if not rows:
        return True

    try:
        new = _parse_result(new_value)
        is_field = event and event["event_type"] == "field"
        if is_field:
            return all(new > _parse_result(r["result_value"]) for r in rows)
        else:
            return all(new < _parse_result(r["result_value"]) for r in rows)
    except (ValueError, ZeroDivisionError):
        return False


def clear_meet_results(meet_id: int) -> int:
    """Delete all track results for a meet. Returns number of rows deleted."""
    conn = get_connection()
    try:
        cur = execute(conn,
            "DELETE FROM track_result WHERE meet_id=?", (meet_id,))
        return cur.rowcount
    finally:
        release_connection(conn)


def save_track_result(meet_id: int, athlete_id: int, event_id: int,
                      result_value: str, place: int | None = None) -> None:
    pr = is_track_pr(athlete_id, event_id, result_value)
    conn = get_connection()
    try:
        execute(conn,
            """INSERT INTO track_result
               (meet_id, athlete_id, event_id, result_value, is_pr, place)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(meet_id, athlete_id, event_id)
               DO UPDATE SET result_value=excluded.result_value,
                             is_pr=excluded.is_pr,
                             place=excluded.place""",
            (meet_id, athlete_id, event_id, result_value.strip(), int(pr), place))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_meet_results(meet_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT tr.*, a.first_name, a.last_name, a.gender,
                      te.name AS event_name, te.event_type
               FROM track_result tr
               JOIN athlete a ON a.id = tr.athlete_id
               JOIN track_event te ON te.id = tr.event_id
               WHERE tr.meet_id = ?
               ORDER BY te.sort_order, tr.place""",
            (meet_id,))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_season_bests_track(season_id: int) -> list[dict]:
    """Season bests using numeric comparison instead of string MIN()."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT tr.athlete_id, tr.event_id,
                      a.first_name, a.last_name, a.gender,
                      te.name AS event_name, te.event_type,
                      te.sort_order,
                      tr.result_value, tr.is_pr
               FROM track_result tr
               JOIN meet m ON m.id = tr.meet_id
               JOIN athlete a ON a.id = tr.athlete_id
               JOIN track_event te ON te.id = tr.event_id
               WHERE m.season_id = ?
               ORDER BY te.sort_order, a.last_name""",
            (season_id,))
    finally:
        release_connection(conn)

    grouped: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["athlete_id"], r["event_id"])
        grouped.setdefault(key, []).append(r)

    bests = []
    for (aid, eid), results in grouped.items():
        event_type = results[0]["event_type"]
        is_field = event_type == "field"

        best_row = None
        best_val = None
        for r in results:
            try:
                val = _parse_result(r["result_value"])
            except (ValueError, ZeroDivisionError):
                continue
            if best_val is None:
                best_val = val
                best_row = r
            elif is_field and val > best_val:
                best_val = val
                best_row = r
            elif not is_field and val < best_val:
                best_val = val
                best_row = r

        if best_row:
            has_pr = any(r["is_pr"] for r in results)
            bests.append({
                "athlete_id": best_row["athlete_id"],
                "event_id": best_row["event_id"],
                "first_name": best_row["first_name"],
                "last_name": best_row["last_name"],
                "gender": best_row["gender"],
                "event_name": best_row["event_name"],
                "event_type": best_row["event_type"],
                "sort_order": best_row["sort_order"],
                "season_best": best_row["result_value"],
                "is_pr": has_pr,
            })

    bests.sort(key=lambda b: (b["sort_order"], b["last_name"]))
    return bests


def get_season_best_per_event(season_id: int) -> dict[tuple, str]:
    """Returns {(athlete_id, event_id): season_best} using numeric comparison."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT tr.athlete_id, tr.event_id, tr.result_value,
                      te.event_type
               FROM track_result tr
               JOIN meet m ON m.id = tr.meet_id
               JOIN track_event te ON te.id = tr.event_id
               WHERE m.season_id = ?""",
            (season_id,))
    finally:
        release_connection(conn)

    grouped: dict[tuple, list] = {}
    for row in rows:
        key = (row["athlete_id"], row["event_id"])
        grouped.setdefault(key, []).append(row)

    result = {}
    for key, entries in grouped.items():
        is_field = entries[0]["event_type"] == "field"
        best_val = None
        best_str = None
        for e in entries:
            try:
                val = _parse_result(e["result_value"])
            except (ValueError, ZeroDivisionError):
                continue
            if best_val is None:
                best_val = val
                best_str = e["result_value"]
            elif is_field and val > best_val:
                best_val = val
                best_str = e["result_value"]
            elif not is_field and val < best_val:
                best_val = val
                best_str = e["result_value"]
        if best_str:
            result[key] = best_str

    return result


def recalculate_pr_flags() -> int:
    """Recalculate all is_pr flags using numeric comparison.

    For each (athlete, event) group, marks the single best result as PR.
    Running/relay: lowest time. Field: highest value.
    Returns the number of flags changed.
    """
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT tr.id, tr.athlete_id, tr.event_id,
                      tr.result_value, tr.is_pr,
                      te.event_type, m.meet_date
               FROM track_result tr
               JOIN track_event te ON te.id = tr.event_id
               JOIN meet m ON m.id = tr.meet_id
               ORDER BY tr.athlete_id, tr.event_id, m.meet_date""")
    finally:
        release_connection(conn)

    # Group by (athlete, event)
    grouped: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["athlete_id"], r["event_id"])
        grouped.setdefault(key, []).append(r)

    updates = []
    for (aid, eid), results in grouped.items():
        is_field = results[0]["event_type"] == "field"

        # Find the best result (earliest date wins ties)
        best_id = None
        best_val = None
        for r in results:
            try:
                val = _parse_result(r["result_value"])
            except (ValueError, ZeroDivisionError):
                continue
            if best_val is None:
                best_val = val
                best_id = r["id"]
            elif is_field and val > best_val:
                best_val = val
                best_id = r["id"]
            elif not is_field and val < best_val:
                best_val = val
                best_id = r["id"]

        # Set is_pr=1 for the best, is_pr=0 for all others
        for r in results:
            should_be_pr = 1 if r["id"] == best_id else 0
            if r["is_pr"] != should_be_pr:
                updates.append((should_be_pr, r["id"]))

    if updates:
        conn = get_connection()
        try:
            for new_flag, row_id in updates:
                execute(conn,
                    "UPDATE track_result SET is_pr=? WHERE id=?",
                    (new_flag, row_id))
        finally:
            release_connection(conn)

    return len(updates)


def get_season_bests(season_id: int) -> dict[int, str]:
    """XC season bests (finish_time based)."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT re.athlete_id, MIN(r.finish_time) AS best_time
               FROM result r
               JOIN race_entry re ON re.id = r.race_entry_id
               JOIN race rc ON rc.id = re.race_id
               JOIN meet m ON m.id = rc.meet_id
               WHERE m.season_id = ?
               GROUP BY re.athlete_id""",
            (season_id,))
    finally:
        release_connection(conn)
    return {row["athlete_id"]: row["best_time"] for row in rows}


@st.cache_data(ttl=120)
def get_athlete_meet_counts(season_id: int) -> dict[int, int]:
    """Returns {athlete_id: number_of_meets_participated} for the season.

    Counts meets where athlete had results OR was in the lineup (captures
    relay-only athletes). Excludes the 'Tryouts' pseudo-meet.
    """
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT athlete_id, COUNT(DISTINCT meet_id) AS meet_count
               FROM (
                   SELECT tr.athlete_id, tr.meet_id
                   FROM track_result tr
                   JOIN meet m ON m.id = tr.meet_id
                   WHERE m.season_id = ? AND m.name != 'Tryouts'
                   UNION
                   SELECT le.athlete_id, le.meet_id
                   FROM lineup_entry le
                   JOIN meet m ON m.id = le.meet_id
                   WHERE m.season_id = ? AND m.name != 'Tryouts'
               ) combined
               GROUP BY athlete_id""",
            (season_id, season_id))
    finally:
        release_connection(conn)
    return {r["athlete_id"]: r["meet_count"] for r in rows}


@st.cache_data(ttl=120)
def get_athlete_profile(athlete_id: int, season_id: int) -> dict:
    """Returns full season history for an athlete."""
    conn = get_connection()
    try:
        athlete = fetchone(conn,
            "SELECT * FROM athlete WHERE id=?", (athlete_id,))

        history = fetchall(conn,
            """SELECT m.name AS meet_name, m.meet_date,
                      te.name AS event_name, te.event_type, te.sort_order,
                      tr.result_value, tr.place, tr.is_pr
               FROM track_result tr
               JOIN meet m       ON m.id  = tr.meet_id
               JOIN track_event te ON te.id = tr.event_id
               WHERE tr.athlete_id = ? AND m.season_id = ?
               ORDER BY m.meet_date, te.sort_order""",
            (athlete_id, season_id))

        bests_rows = fetchall(conn,
            """SELECT te.name AS event_name, te.event_type, te.sort_order,
                      tr.result_value, tr.is_pr
               FROM track_result tr
               JOIN meet m       ON m.id  = tr.meet_id
               JOIN track_event te ON te.id = tr.event_id
               WHERE tr.athlete_id = ? AND m.season_id = ?
               ORDER BY te.sort_order""",
            (athlete_id, season_id))
    finally:
        release_connection(conn)

    # Compute season bests using numeric comparison (not string MIN)
    grouped_bests: dict[str, list[dict]] = {}
    for row in bests_rows:
        grouped_bests.setdefault(row["event_name"], []).append(row)

    season_bests = {}
    for event_name, rows in grouped_bests.items():
        is_field = rows[0]["event_type"] == "field"
        best_val = None
        best_str = None
        has_pr = False
        for r in rows:
            if r["is_pr"]:
                has_pr = True
            try:
                val = _parse_result(r["result_value"])
            except (ValueError, ZeroDivisionError):
                continue
            if best_val is None:
                best_val = val
                best_str = r["result_value"]
            elif is_field and val > best_val:
                best_val = val
                best_str = r["result_value"]
            elif not is_field and val < best_val:
                best_val = val
                best_str = r["result_value"]
        if best_str:
            season_bests[event_name] = {
                "result_value": best_str,
                "has_pr": has_pr,
            }

    return {
        "athlete": athlete or {},
        "season_bests": season_bests,
        "history": history,
    }
