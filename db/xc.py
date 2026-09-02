"""db/xc.py — XC results, season bests, team stats, and workout groups."""

import streamlit as st
from db.connection import (
    get_connection, release_connection,
    fetchall, fetchone, execute, insert_returning_id,
)


def _parse_xc_time(value: str) -> float:
    """Convert XC finish time string to total seconds.
    Handles: '14:35.68', '6:06.00', '25:10.80', '00:19:32.00'
    """
    v = value.strip()
    if ":" in v:
        parts = v.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return int(parts[0]) * 60 + float(parts[1])
    return float(v)


# ---------------------------------------------------------------------------
# XC Results
# ---------------------------------------------------------------------------

def is_xc_pr(athlete_id: int, new_time: str, distance: str = "2mi") -> bool:
    """Check if a finish time is a PR (fastest ever at this distance) for an XC athlete."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            "SELECT finish_time FROM xc_result WHERE athlete_id=? AND distance=?",
            (athlete_id, distance))
    finally:
        release_connection(conn)

    if not rows:
        return True

    try:
        new = _parse_xc_time(new_time)
        return all(new < _parse_xc_time(r["finish_time"]) for r in rows)
    except (ValueError, ZeroDivisionError):
        return False


def save_xc_result(meet_id: int, athlete_id: int, finish_time: str,
                   place: int | None = None,
                   distance: str = "2mi") -> None:
    pr = is_xc_pr(athlete_id, finish_time, distance)
    conn = get_connection()
    try:
        execute(conn,
            """INSERT INTO xc_result
               (meet_id, athlete_id, finish_time, place, distance, is_pr)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(meet_id, athlete_id)
               DO UPDATE SET finish_time=excluded.finish_time,
                             place=excluded.place,
                             distance=excluded.distance,
                             is_pr=excluded.is_pr""",
            (meet_id, athlete_id, finish_time.strip(), place,
             distance.strip(), int(pr)))
    finally:
        release_connection(conn)


def clear_xc_results(meet_id: int) -> int:
    conn = get_connection()
    try:
        cur = execute(conn,
            "DELETE FROM xc_result WHERE meet_id=?", (meet_id,))
        return cur.rowcount
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_xc_meet_results(meet_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT xr.*, a.first_name, a.last_name, a.gender
               FROM xc_result xr
               JOIN athlete a ON a.id = xr.athlete_id
               WHERE xr.meet_id = ?
               ORDER BY xr.place NULLS LAST, xr.finish_time""",
            (meet_id,))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_xc_season_bests(season_id: int) -> list[dict]:
    """Season bests using numeric comparison."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT xr.athlete_id, xr.finish_time, xr.is_pr,
                      xr.distance, xr.place,
                      a.first_name, a.last_name, a.gender,
                      m.name AS meet_name, m.meet_date
               FROM xc_result xr
               JOIN meet m ON m.id = xr.meet_id
               JOIN athlete a ON a.id = xr.athlete_id
               WHERE m.season_id = ?
               ORDER BY a.last_name""",
            (season_id,))
    finally:
        release_connection(conn)

    grouped: dict[int, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["athlete_id"], []).append(r)

    bests = []
    for aid, results in grouped.items():
        best_row = None
        best_val = None
        has_pr = False
        for r in results:
            if r["is_pr"]:
                has_pr = True
            try:
                val = _parse_xc_time(r["finish_time"])
            except (ValueError, ZeroDivisionError):
                continue
            if best_val is None or val < best_val:
                best_val = val
                best_row = r

        if best_row:
            bests.append({
                "athlete_id": best_row["athlete_id"],
                "first_name": best_row["first_name"],
                "last_name": best_row["last_name"],
                "gender": best_row["gender"],
                "season_best": best_row["finish_time"],
                "distance": best_row["distance"],
                "meet_name": best_row["meet_name"],
                "is_pr": has_pr,
            })

    bests.sort(key=lambda b: b["last_name"])
    return bests


# ---------------------------------------------------------------------------
# Team stats for a single meet
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def get_xc_team_stats(meet_id: int) -> dict:
    """Calculate team stats for a meet: avg, median, 1-5 split, top5 avg.

    Returns stats per gender.
    """
    results = get_xc_meet_results(meet_id)
    stats = {}

    for gender, label in [("M", "Boys"), ("F", "Girls")]:
        gender_results = [r for r in results if r["gender"] == gender]
        times = []
        for r in gender_results:
            try:
                times.append(_parse_xc_time(r["finish_time"]))
            except (ValueError, ZeroDivisionError):
                continue

        times.sort()
        if not times:
            stats[gender] = None
            continue

        n = len(times)
        avg = sum(times) / n
        median = times[n // 2] if n % 2 == 1 else (times[n // 2 - 1] + times[n // 2]) / 2
        top5 = times[:5]
        top5_avg = sum(top5) / len(top5) if top5 else 0
        split_1_5 = (times[4] - times[0]) if len(times) >= 5 else None

        stats[gender] = {
            "count": n,
            "average": avg,
            "median": median,
            "top5_avg": top5_avg,
            "split_1_5": split_1_5,
            "fastest": times[0],
            "slowest": times[-1],
        }

    return stats


def fmt_xc_time(seconds: float) -> str:
    """Format seconds as M:SS.ss for display."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


# ---------------------------------------------------------------------------
# Athlete XC profile
# ---------------------------------------------------------------------------

def get_xc_athlete_profile(athlete_id: int, season_id: int) -> dict:
    conn = get_connection()
    try:
        athlete = fetchone(conn,
            "SELECT * FROM athlete WHERE id=?", (athlete_id,))
        history = fetchall(conn,
            """SELECT m.name AS meet_name, m.meet_date,
                      xr.finish_time, xr.place, xr.distance, xr.is_pr
               FROM xc_result xr
               JOIN meet m ON m.id = xr.meet_id
               WHERE xr.athlete_id = ? AND m.season_id = ?
               ORDER BY m.meet_date""",
            (athlete_id, season_id))
    finally:
        release_connection(conn)

    # Season best via numeric comparison
    best_time = None
    best_val = None
    for h in history:
        try:
            val = _parse_xc_time(h["finish_time"])
        except (ValueError, ZeroDivisionError):
            continue
        if best_val is None or val < best_val:
            best_val = val
            best_time = h["finish_time"]

    return {
        "athlete": athlete or {},
        "season_best": best_time,
        "history": history,
    }


# ---------------------------------------------------------------------------
# XC meet participation counts (for dashboard tracker)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120)
def get_xc_meet_counts(season_id: int) -> dict[int, int]:
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT xr.athlete_id, COUNT(DISTINCT xr.meet_id) AS meet_count
               FROM xc_result xr
               JOIN meet m ON m.id = xr.meet_id
               WHERE m.season_id = ?
               GROUP BY xr.athlete_id""",
            (season_id,))
    finally:
        release_connection(conn)
    return {r["athlete_id"]: r["meet_count"] for r in rows}


# ---------------------------------------------------------------------------
# PR recalculation
# ---------------------------------------------------------------------------

def recalculate_xc_pr_flags() -> int:
    """Recalculate is_pr flags for all XC results, chronologically per athlete per distance."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT xr.id, xr.athlete_id, xr.finish_time, xr.distance,
                      m.meet_date
               FROM xc_result xr
               JOIN meet m ON m.id = xr.meet_id
               ORDER BY xr.athlete_id, xr.distance, m.meet_date, xr.finish_time""")

        updated = 0
        current_athlete = None
        current_distance = None
        best_time = None

        for r in rows:
            if r["athlete_id"] != current_athlete or r["distance"] != current_distance:
                current_athlete = r["athlete_id"]
                current_distance = r["distance"]
                best_time = None

            try:
                t = _parse_xc_time(r["finish_time"])
            except (ValueError, ZeroDivisionError):
                continue

            is_pr = best_time is None or t < best_time
            if is_pr:
                best_time = t

            execute(conn,
                "UPDATE xc_result SET is_pr=? WHERE id=?",
                (int(is_pr), r["id"]))
            updated += 1

        return updated
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Workout groups
# ---------------------------------------------------------------------------

def suggest_workout_groups(season_id: int, meet_id: int | None = None,
                          gender: str | None = None) -> list[dict]:
    """Auto-suggest workout groups via gap detection on latest race times.

    Returns a list of groups: [{"name": "A", "athletes": [...]}, ...]
    Each athlete dict includes id, name, time, and seconds.
    """
    # Get latest results — either from a specific meet or the most recent one
    conn = get_connection()
    try:
        if meet_id is None:
            latest = fetchone(conn,
                """SELECT m.id FROM meet m
                   JOIN xc_result xr ON xr.meet_id = m.id
                   WHERE m.season_id = ?
                   ORDER BY m.meet_date DESC LIMIT 1""",
                (season_id,))
            if not latest:
                return []
            meet_id = latest["id"]

        rows = fetchall(conn,
            """SELECT xr.athlete_id, xr.finish_time,
                      a.first_name, a.last_name, a.gender
               FROM xc_result xr
               JOIN athlete a ON a.id = xr.athlete_id
               WHERE xr.meet_id = ?
               ORDER BY xr.finish_time""",
            (meet_id,))
    finally:
        release_connection(conn)

    if gender:
        rows = [r for r in rows if r["gender"] == gender]

    if len(rows) < 3:
        return [{"name": "A", "athletes": [
            {**r, "seconds": _parse_xc_time(r["finish_time"])}
            for r in rows
        ]}]

    # Parse times and sort
    athletes = []
    for r in rows:
        try:
            seconds = _parse_xc_time(r["finish_time"])
            athletes.append({**r, "seconds": seconds})
        except (ValueError, ZeroDivisionError):
            continue

    athletes.sort(key=lambda a: a["seconds"])

    # Find the two largest gaps between consecutive athletes
    gaps = []
    for i in range(len(athletes) - 1):
        gap = athletes[i + 1]["seconds"] - athletes[i]["seconds"]
        gaps.append((gap, i + 1))

    gaps.sort(reverse=True)

    # Use top 2 gaps if they're significant (> 20 seconds)
    split_points = sorted([g[1] for g in gaps[:2]])

    # If the second-largest gap is small, use only 2 groups
    if len(gaps) >= 2 and gaps[1][0] < 20:
        split_points = [gaps[0][1]]

    group_names = ["A", "B", "C"]
    groups = []
    prev = 0
    for i, sp in enumerate(split_points):
        groups.append({
            "name": group_names[i],
            "athletes": athletes[prev:sp],
        })
        prev = sp
    groups.append({
        "name": group_names[len(split_points)],
        "athletes": athletes[prev:],
    })

    return groups


def get_workout_groups(season_id: int) -> list[dict]:
    """Get saved workout groups with their members."""
    conn = get_connection()
    try:
        groups = fetchall(conn,
            """SELECT * FROM workout_group
               WHERE season_id = ?
               ORDER BY sort_order""",
            (season_id,))

        result = []
        for g in groups:
            members = fetchall(conn,
                """SELECT wgm.athlete_id,
                          a.first_name, a.last_name, a.gender
                   FROM workout_group_member wgm
                   JOIN athlete a ON a.id = wgm.athlete_id
                   WHERE wgm.group_id = ?
                   ORDER BY a.last_name""",
                (g["id"],))
            result.append({
                "id": g["id"],
                "name": g["name"],
                "sort_order": g["sort_order"],
                "members": members,
            })
    finally:
        release_connection(conn)
    return result


def save_workout_groups(season_id: int,
                        groups: list[dict]) -> None:
    """Save workout groups. Each group: {"name": str, "athlete_ids": [int]}

    Replaces all existing groups for this season.
    """
    conn = get_connection()
    try:
        # Delete existing groups for this season
        existing = fetchall(conn,
            "SELECT id FROM workout_group WHERE season_id=?",
            (season_id,))
        for g in existing:
            execute(conn,
                "DELETE FROM workout_group_member WHERE group_id=?",
                (g["id"],))
            execute(conn,
                "DELETE FROM workout_group WHERE id=?",
                (g["id"],))

        # Insert new groups
        for i, group in enumerate(groups):
            gid = insert_returning_id(conn,
                """INSERT INTO workout_group (season_id, name, sort_order)
                   VALUES (?, ?, ?)""",
                (season_id, group["name"], i))
            for aid in group["athlete_ids"]:
                execute(conn,
                    """INSERT INTO workout_group_member (group_id, athlete_id)
                       VALUES (?, ?)""",
                    (gid, aid))
    finally:
        release_connection(conn)


def move_athlete_between_groups(season_id: int, athlete_id: int,
                                from_group_id: int,
                                to_group_id: int) -> None:
    """Move an athlete from one workout group to another."""
    conn = get_connection()
    try:
        execute(conn,
            "DELETE FROM workout_group_member WHERE group_id=? AND athlete_id=?",
            (from_group_id, athlete_id))
        execute(conn,
            """INSERT INTO workout_group_member (group_id, athlete_id)
               VALUES (?, ?)
               ON CONFLICT(group_id, athlete_id) DO NOTHING""",
            (to_group_id, athlete_id))
    finally:
        release_connection(conn)
