"""db/records.py — School records and recent top performances."""

import streamlit as st
from db.connection import (
    get_connection, release_connection,
    fetchall, fetchone, execute,
)


@st.cache_data(ttl=120)
def get_school_records(school_id: int) -> list[dict]:
    """All historic school records for a school."""
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT * FROM school_record
               WHERE school_id = ?
               ORDER BY gender, sport, event_name""",
            (school_id,))
    finally:
        release_connection(conn)


def upsert_school_record(school_id: int, event_name: str, gender: str,
                         record_value: str, holder_name: str, year: int,
                         sport: str = "Track") -> None:
    """Insert or update a school record."""
    conn = get_connection()
    try:
        execute(conn,
            """INSERT INTO school_record
               (school_id, event_name, gender, record_value, holder_name, year, sport)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(school_id, event_name, gender, sport)
               DO UPDATE SET record_value=excluded.record_value,
                             holder_name=excluded.holder_name,
                             year=excluded.year""",
            (school_id, event_name, gender, record_value, holder_name, year, sport))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_top_performances_track(school_id: int, top_n: int = 3) -> list[dict]:
    """Top N performances per event across all seasons from track_result."""
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT te.name AS event_name, te.event_type, te.gender,
                      tr.result_value, a.first_name, a.last_name,
                      s.year, m.name AS meet_name
               FROM track_result tr
               JOIN track_event te ON te.id = tr.event_id
               JOIN athlete a ON a.id = tr.athlete_id
               JOIN meet m ON m.id = tr.meet_id
               JOIN season s ON s.id = m.season_id
               WHERE s.school_id = ?
               ORDER BY te.gender, te.sort_order, te.name, tr.result_value""",
            (school_id,))
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_top_performances_xc(school_id: int) -> list[dict]:
    """Top XC performances across all seasons."""
    conn = get_connection()
    try:
        return fetchall(conn,
            """SELECT xr.finish_time, xr.distance, a.first_name, a.last_name,
                      a.gender, s.year, m.name AS meet_name
               FROM xc_result xr
               JOIN athlete a ON a.id = xr.athlete_id
               JOIN meet m ON m.id = xr.meet_id
               JOIN season s ON s.id = m.season_id
               WHERE s.school_id = ?
               ORDER BY a.gender, xr.distance, xr.finish_time""",
            (school_id,))
    finally:
        release_connection(conn)
