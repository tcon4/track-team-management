"""db/events.py — Track events and event assignments."""

import re

import streamlit as st
from db.connection import get_connection, release_connection, fetchall, execute


@st.cache_data(ttl=120)
def get_track_events(gender: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        if gender:
            return fetchall(conn,
                """SELECT * FROM track_event
                   WHERE gender=? OR gender='combined'
                   ORDER BY sort_order""",
                (gender,))
        else:
            return fetchall(conn,
                "SELECT * FROM track_event ORDER BY sort_order")
    finally:
        release_connection(conn)


def get_athlete_events(athlete_id: int, season_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT te.*
               FROM event_assignment ea
               JOIN track_event te ON te.id = ea.event_id
               WHERE ea.athlete_id=? AND ea.season_id=?
               ORDER BY te.sort_order""",
            (athlete_id, season_id))
    finally:
        release_connection(conn)


def get_all_athlete_events(season_id: int) -> dict[int, list[dict]]:
    """Batch-fetch all event assignments for a season.
    Returns {athlete_id: [event_dict, ...]}."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT ea.athlete_id, te.id, te.name, te.event_type,
                      te.gender, te.sort_order
               FROM event_assignment ea
               JOIN track_event te ON te.id = ea.event_id
               WHERE ea.season_id=?
               ORDER BY te.sort_order""",
            (season_id,))
        result: dict[int, list[dict]] = {}
        for r in rows:
            result.setdefault(r["athlete_id"], []).append(r)
        return result
    finally:
        release_connection(conn)


def assign_event(athlete_id: int, season_id: int, event_id: int) -> None:
    """Add a single event assignment. Safe to call if already assigned."""
    conn = get_connection()
    try:
        execute(conn,
            """INSERT INTO event_assignment
               (season_id, athlete_id, event_id) VALUES (?,?,?)
               ON CONFLICT (season_id, athlete_id, event_id) DO NOTHING""",
            (season_id, athlete_id, event_id))
    finally:
        release_connection(conn)


def set_athlete_events(athlete_id: int, season_id: int,
                       event_ids: list[int]) -> None:
    """Replace all event assignments for an athlete in a season."""
    conn = get_connection()
    try:
        execute(conn,
            "DELETE FROM event_assignment WHERE athlete_id=? AND season_id=?",
            (athlete_id, season_id))
        for eid in event_ids:
            execute(conn,
                """INSERT INTO event_assignment
                   (season_id, athlete_id, event_id) VALUES (?,?,?)
                   ON CONFLICT (season_id, athlete_id, event_id) DO NOTHING""",
                (season_id, athlete_id, eid))
    finally:
        release_connection(conn)


def match_event_by_number(event_name: str, gender: str,
                           all_events: list[dict]) -> dict | None:
    """
    Match a Milesplit event name to a track_event row by extracting
    the numeric value and relay multiplier, then matching gender.
    """
    name = event_name.strip()
    name = re.sub(r'^(girls?|boys?)[\.\s]+', '', name, flags=re.IGNORECASE)
    name = name.strip(' .')
    name_lower = name.lower()

    num_match = re.match(r"(4x\d+|\d+)", name_lower)
    num_str = num_match.group(1) if num_match else None

    is_hurdles = "hurdle" in name_lower

    field_keywords = {
        "long jump":   "Long Jump",
        "triple jump": "Triple Jump",
        "high jump":   "High Jump",
        "shot put":    "Shot Put",
        "discus":      "Discus",
    }
    for keyword, canonical in field_keywords.items():
        if keyword in name_lower:
            for ev in all_events:
                if ev["name"] == canonical and ev["gender"] == gender:
                    return ev
            return None

    if num_str is None:
        return None

    for ev in all_events:
        ev_lower = ev["name"].lower()
        if ev["gender"] != gender:
            continue

        ev_num = re.match(r"(4x\d+|\d+)", ev_lower)
        if not ev_num:
            continue

        if ev_num.group(1) != num_str:
            continue

        ev_hurdles = "hurdle" in ev_lower
        if is_hurdles != ev_hurdles:
            continue

        return ev

    return None
