"""
app.py — XC / Track Athletics App
Run with: streamlit run app.py

Navigation router: defines which pages are visible based on coach login.
"""

import streamlit as st
import shared

st.set_page_config(
    page_title="Athletics",
    page_icon="\U0001f3c3",
    layout="wide",
)

season_id = shared.init_app()

# --- Define pages ---
parent_pages = [
    st.Page("pages/0_Dashboard.py", title="Dashboard", icon="\U0001f3e0", default=True),
    st.Page("pages/1_Roster.py", title="Roster", icon="\U0001f4cb"),
    st.Page("pages/2_Schedule.py", title="Schedule", icon="\U0001f4c5"),
    st.Page("pages/5_Team_Results.py", title="Team Results", icon="\U0001f3c1"),
    st.Page("pages/8_School_Records.py", title="School Records", icon="\U0001f3c6"),
]

coach_pages = [
    st.Page("pages/3_Lineup.py", title="Lineup Builder", icon="✏️"),
    st.Page("pages/4_Results.py", title="Results", icon="\U0001f4ca"),
    st.Page("pages/6_Workout_Groups.py", title="Workout Groups", icon="\U0001f3c3"),
    st.Page("pages/7_Import_History.py", title="Import History", icon="\U0001f4e5"),
]

if shared.is_coach():
    pg = st.navigation({"": parent_pages, "Coach Tools": coach_pages})
else:
    pg = st.navigation(parent_pages)

pg.run()
