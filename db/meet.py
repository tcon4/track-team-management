"""db/meet.py — Meet CRUD and meet reports."""

import streamlit as st
from db.connection import get_connection, release_connection, fetchall, fetchone, execute, insert_returning_id


@st.cache_data(ttl=120)
def get_meets(season_id: int) -> list[dict]:
    """All meets for a season, ordered by date."""
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT m.*, s.name AS host_name
               FROM meet m
               JOIN school s ON s.id = m.host_school_id
               WHERE m.season_id = ?
               ORDER BY m.meet_date""",
            (season_id,))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_meet(meet_id: int) -> dict | None:
    conn = get_connection()
    try:
        return fetchone(conn,
            """SELECT m.*, s.name AS host_name
               FROM meet m
               JOIN school s ON s.id = m.host_school_id
               WHERE m.id = ?""",
            (meet_id,))
    finally:
        release_connection(conn)


def add_meet(season_id: int, name: str, meet_date: str,
             location: str, host_school_id: int,
             milesplit_url: str = "") -> int:
    conn = get_connection()
    try:
        return insert_returning_id(conn,
            """INSERT INTO meet
               (season_id, name, meet_date, location, host_school_id, milesplit_url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (season_id, name.strip(), meet_date,
             location.strip(), host_school_id, milesplit_url.strip()))
    finally:
        release_connection(conn)


def update_meet(meet_id: int, name: str, meet_date: str,
                location: str, host_school_id: int,
                girls_place: str = "", boys_place: str = "",
                milesplit_url: str = "") -> None:
    conn = get_connection()
    try:
        execute(conn,
            """UPDATE meet
               SET name=?, meet_date=?, location=?, host_school_id=?,
                   girls_place=?, boys_place=?, milesplit_url=?
               WHERE id=?""",
            (name.strip(), meet_date, location.strip(), host_school_id,
             (girls_place or "").strip(), (boys_place or "").strip(),
             (milesplit_url or "").strip(), meet_id))
    finally:
        release_connection(conn)


def delete_meet(meet_id: int) -> None:
    conn = get_connection()
    try:
        execute(conn, "DELETE FROM xc_result WHERE meet_id=?", (meet_id,))
        execute(conn, "DELETE FROM track_result WHERE meet_id=?", (meet_id,))
        execute(conn, "DELETE FROM lineup_entry WHERE meet_id=?", (meet_id,))
        execute(conn,
            """DELETE FROM result WHERE race_entry_id IN
               (SELECT re.id FROM race_entry re
                JOIN race r ON r.id = re.race_id
                WHERE r.meet_id = ?)""", (meet_id,))
        execute(conn,
            """DELETE FROM race_entry WHERE race_id IN
               (SELECT id FROM race WHERE meet_id = ?)""", (meet_id,))
        execute(conn, "DELETE FROM race WHERE meet_id=?", (meet_id,))
        execute(conn, "DELETE FROM meet WHERE id=?", (meet_id,))
    finally:
        release_connection(conn)


def get_meet_report(meet_id: int) -> dict:
    """Returns all results for a meet grouped by gender and event type."""
    conn = get_connection()
    try:
        rows = fetchall(conn,
            """SELECT tr.athlete_id, a.first_name, a.last_name, a.gender,
                      te.name AS event_name, te.event_type, te.sort_order,
                      tr.result_value, tr.place, tr.is_pr
               FROM track_result tr
               JOIN athlete a  ON a.id  = tr.athlete_id
               JOIN track_event te ON te.id = tr.event_id
               WHERE tr.meet_id = ?
               ORDER BY te.sort_order, tr.place""",
            (meet_id,))
    finally:
        release_connection(conn)

    report: dict = {
        "M": {"field": [], "running": [], "relay": []},
        "F": {"field": [], "running": [], "relay": []},
    }
    for r in rows:
        gender = r["gender"]
        etype = r["event_type"]
        if gender in report and etype in report[gender]:
            report[gender][etype].append(r)

    return report
