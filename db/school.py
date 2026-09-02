"""db/school.py — School CRUD."""

import streamlit as st
from db.connection import get_connection, release_connection, fetchall, fetchone, execute


@st.cache_data(ttl=120)
def get_schools() -> list[dict]:
    conn = get_connection()
    try:
        return fetchall(conn, "SELECT * FROM school ORDER BY name")
    finally:
        release_connection(conn)


@st.cache_data(ttl=120)
def get_school(school_id: int) -> dict | None:
    conn = get_connection()
    try:
        return fetchone(conn, "SELECT * FROM school WHERE id = ?", (school_id,))
    finally:
        release_connection(conn)


def update_school(school_id: int, name: str, city: str) -> None:
    conn = get_connection()
    try:
        execute(conn,
            "UPDATE school SET name=?, city=? WHERE id=?",
            (name.strip(), city.strip(), school_id))
    finally:
        release_connection(conn)
