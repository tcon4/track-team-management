"""
shared.py — Common sidebar, session state, and bootstrap logic.
Every page calls setup() at the top to get the sidebar and season_id.
"""

import streamlit as st
from datetime import date
import db

COACH_PASSWORD = "mms2026"


def _season_label(s: dict) -> str:
    return f"{s['year']} {s['sport']}"


def is_coach() -> bool:
    return st.session_state.get("is_coach", False)


def require_coach() -> None:
    """Stop page execution if not logged in as coach."""
    if not is_coach():
        st.warning("This page is for coaches only. Please log in via the sidebar.")
        st.stop()


def setup() -> int:
    """
    Bootstrap the app: init DB, render sidebar, resolve season.
    Returns the current season_id.
    """
    st.set_page_config(
        page_title="Athletics",
        page_icon="\U0001f3c3",
        layout="wide",
    )

    db.init_db()

    for key in ("editing_athlete", "editing_meet", "profile_athlete",
                "ms_matched", "csv_preview_rows"):
        if key not in st.session_state:
            st.session_state[key] = None

    if "is_coach" not in st.session_state:
        st.session_state.is_coach = False

    # Sidebar — single schools fetch
    schools = db.get_schools()

    if "school_id" not in st.session_state:
        st.session_state.school_id = schools[0]["id"] if schools else None

    with st.sidebar:
        if not schools:
            st.error("No schools found in database. Check your database connection.")
            st.stop()
        school_names = [s["name"] for s in schools]
        selected_school_name = st.selectbox("School", school_names)
        school = next(s for s in schools if s["name"] == selected_school_name)
        st.session_state.school_id = school["id"]

        # Season selector — single dropdown
        seasons = db.get_seasons(school["id"])

        if not seasons:
            now = date.today()
            sport = "XC" if now.month >= 7 else "Track"
            sid = db.get_or_create_season(now.year, sport, school["id"])
            seasons = db.get_seasons(school["id"])

        season_labels = [_season_label(s) for s in seasons]
        default_idx = 0
        if "selected_season_id" in st.session_state:
            for i, s in enumerate(seasons):
                if s["id"] == st.session_state.selected_season_id:
                    default_idx = i
                    break

        selected_label = st.selectbox(
            "Season", season_labels, index=default_idx,
        )
        selected_season = seasons[season_labels.index(selected_label)]
        st.session_state.selected_season_id = selected_season["id"]
        st.session_state.sport = selected_season["sport"]
        st.session_state.current_year = selected_season["year"]

        sport_label = selected_season["sport"]
        st.sidebar.markdown(
            f"### \U0001f3c3 {sport_label} Manager"
        )

        # Coach login
        st.divider()
        if st.session_state.is_coach:
            st.success("Logged in as Coach")
            if st.button("Log out", key="coach_logout"):
                st.session_state.is_coach = False
                st.rerun()

            with st.expander("New season"):
                with st.form("new_season_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        new_sport = st.selectbox(
                            "Sport", ["XC", "Track"], key="new_season_sport",
                        )
                    with col2:
                        new_year = st.number_input(
                            "Year", value=date.today().year,
                            min_value=2020, max_value=2030,
                            key="new_season_year",
                        )
                    if st.form_submit_button("Create"):
                        new_sid = db.get_or_create_season(
                            int(new_year), new_sport, school["id"],
                        )
                        st.session_state.selected_season_id = new_sid
                        data_changed()

            st.divider()

            with st.expander("Edit school name"):
                with st.form("school_form"):
                    new_name = st.text_input("School name", value=school["name"])
                    new_city = st.text_input("City", value=school["city"])
                    if st.form_submit_button("Save"):
                        db.update_school(school["id"], new_name, new_city)
                        data_changed()
        else:
            with st.popover("Coach Login"):
                pwd = st.text_input("Password", type="password", key="coach_pwd")
                if st.button("Log in", key="coach_login_btn"):
                    if pwd == COACH_PASSWORD:
                        st.session_state.is_coach = True
                        st.rerun()
                    else:
                        st.error("Incorrect password")

    return selected_season["id"]


def data_changed():
    """Clear all data caches and rerun. Call after any database write."""
    st.cache_data.clear()
    st.rerun()


def format_place(place: int | None) -> str:
    """Format a place number as '1st', '2nd', '3rd', '4th', etc."""
    if place is None:
        return "—"
    if place == 1:
        return "1st"
    if place == 2:
        return "2nd"
    if place == 3:
        return "3rd"
    return f"{place}th"
