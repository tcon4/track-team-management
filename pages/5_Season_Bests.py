"""Season Bests page."""

import streamlit as st
import db
import shared

season_id = shared.setup()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title("Season Bests")
st.caption(f"{year} {sport} — {school_name}")

# ###########################################################################
# XC Season Bests
# ###########################################################################

if sport == "XC":
    bests = db.get_xc_season_bests(season_id)

    if not bests:
        st.info("No XC results recorded yet.")
        st.page_link("pages/4_Results.py", label="Enter results →")
        st.stop()

    pr_count = sum(1 for b in bests if b.get("is_pr"))
    athlete_count = len(bests)
    mc1, mc2 = st.columns(2)
    mc1.metric("Athletes with Results", athlete_count)
    mc2.metric("Season PRs", pr_count)

    st.divider()

    gender_tab_b, gender_tab_g = st.tabs(["Boys", "Girls"])

    for gender_val, tab in [("M", gender_tab_b), ("F", gender_tab_g)]:
        with tab:
            filtered = [b for b in bests if b["gender"] == gender_val]
            if not filtered:
                st.info("No results yet.")
                continue

            from db.xc import _parse_xc_time
            filtered.sort(key=lambda b: _parse_xc_time(b["season_best"]))

            st.dataframe(
                [{
                    "Athlete": f"{b['last_name']}, {b['first_name']}",
                    "Season best": b["season_best"],
                    "Distance": b["distance"],
                    "Meet": b.get("meet_name", ""),
                    "PR": "✓" if b.get("is_pr") else "",
                } for b in filtered],
                use_container_width=True,
                hide_index=True,
            )

    st.stop()

# ###########################################################################
# Track Season Bests
# ###########################################################################

bests = db.get_season_bests_track(season_id)

if not bests:
    st.info("No results recorded yet.")
    st.page_link("pages/4_Results.py", label="Enter results →")
    st.stop()

pr_count = sum(1 for b in bests if b.get("is_pr"))
athlete_count = len(set((b["first_name"], b["last_name"]) for b in bests))
mc1, mc2 = st.columns(2)
mc1.metric("Athletes with Results", athlete_count)
mc2.metric("Season PRs", pr_count)

st.divider()

gender_tab_b, gender_tab_g = st.tabs(["Boys", "Girls"])

for gender_val, tab in [("M", gender_tab_b), ("F", gender_tab_g)]:
    with tab:
        filtered = [b for b in bests if b["gender"] == gender_val]
        if not filtered:
            st.info("No results yet.")
            continue

        events_seen = {}
        for b in filtered:
            events_seen.setdefault(b["event_name"], []).append(b)

        for event_name, event_bests in events_seen.items():
            st.subheader(event_name)
            st.dataframe(
                [{
                    "Athlete": f"{b['last_name']}, {b['first_name']}",
                    "Season best": b["season_best"],
                    "PR": "✓" if b.get("is_pr") else "",
                } for b in event_bests],
                use_container_width=True,
                hide_index=True,
            )
