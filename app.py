"""
app.py — XC / Track Athletics App
Run with: streamlit run app.py

This is the landing page dashboard.
"""

import shared

season_id = shared.setup()

import streamlit as st
from datetime import date
import db

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title(f"{school_name} {sport}")
st.caption(f"{year} Season Dashboard")

# --- Quick stats row ---
stats = db.get_roster_stats(season_id)
meets = db.get_meets(season_id)
today = date.today().isoformat()
past_meets = [m for m in meets if m["meet_date"] < today]
upcoming_meets = [m for m in meets if m["meet_date"] >= today]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Athletes", stats["active"], help="Active roster count")
c2.metric("Meets Complete", len(past_meets))
c3.metric("Meets Upcoming", len(upcoming_meets))

if sport == "Track":
    bests = db.get_season_bests_track(season_id)
    pr_count = sum(1 for b in bests if b.get("is_pr"))
    c4.metric("Season PRs", pr_count)
else:
    xc_bests = db.get_xc_season_bests(season_id)
    xc_pr_count = sum(1 for b in xc_bests if b.get("is_pr"))
    c4.metric("Season PRs", xc_pr_count)

st.divider()

# --- Dashboard cards ---
col_left, col_right = st.columns(2)

with col_left:
    # Next meet card
    with st.container(border=True):
        if upcoming_meets:
            next_meet = upcoming_meets[0]
            st.markdown("**Next Meet**")
            st.markdown(f"### {next_meet['name']}")
            st.caption(f"{next_meet['meet_date']}  ·  {next_meet['location']}")
            st.page_link("pages/2_Schedule.py", label="View full schedule →")
        else:
            st.markdown("**Next Meet**")
            if past_meets:
                st.caption("Season complete — all meets finished!")
            else:
                st.caption("No meets scheduled yet.")
            st.page_link("pages/2_Schedule.py", label="Add a meet →")

with col_right:
    # Roster summary card
    with st.container(border=True):
        st.markdown("**Roster**")
        if stats["total"] > 0:
            st.markdown(f"### {stats['active']} active athletes")
            detail_parts = []
            if stats["injured"] > 0:
                detail_parts.append(f"🟡 {stats['injured']} injured")
            if stats["inactive"] > 0:
                detail_parts.append(f"⚫ {stats['inactive']} inactive")
            if detail_parts:
                st.caption("  ·  ".join(detail_parts))
            st.page_link("pages/1_Roster.py", label="Manage roster →")
        else:
            st.caption("No athletes yet — start by adding your team.")
            st.page_link("pages/1_Roster.py", label="Add athletes →")

# --- Recent results / PRs ---
if sport == "Track" and bests:
    prs = [b for b in bests if b.get("is_pr")]
    if prs:
        st.divider()
        st.markdown("**Recent PRs**")
        for b in prs[:5]:
            st.caption(
                f"🏅 {b['first_name']} {b['last_name']} — "
                f"{b['event_name']}: **{b['season_best']}**"
            )
        if len(prs) > 5:
            st.page_link("pages/5_Season_Bests.py",
                         label=f"View all {len(prs)} PRs →")

elif sport == "XC" and xc_bests:
    prs = [b for b in xc_bests if b.get("is_pr")]
    if prs:
        st.divider()
        st.markdown("**Recent PRs**")
        for b in prs[:5]:
            st.caption(
                f"🏅 {b['first_name']} {b['last_name']} — "
                f"**{b['season_best']}**"
            )
        if len(prs) > 5:
            st.page_link("pages/5_Season_Bests.py",
                         label=f"View all {len(prs)} PRs →")

# --- Participation tracker ---
roster = db.get_roster(season_id)
active_roster = [a for a in roster if a["status"] == "active"]
if sport == "Track":
    meet_counts = db.get_athlete_meet_counts(season_id)
else:
    meet_counts = db.get_xc_meet_counts(season_id)
total_real_meets = len(past_meets)

low_participation = [
    (a, meet_counts.get(a["id"], 0))
    for a in active_roster
    if meet_counts.get(a["id"], 0) <= 1
]

if low_participation and total_real_meets >= 1:
    st.divider()
    with st.expander(
        f"**Participation watch** — {len(low_participation)} athletes "
        f"with 0-1 meets",
        expanded=False,
    ):
        zero_meets = [(a, c) for a, c in low_participation if c == 0]
        one_meet = [(a, c) for a, c in low_participation if c == 1]

        if zero_meets:
            st.markdown("**No meets yet:**")
            for a, _ in sorted(
                zero_meets,
                key=lambda x: (x[0]["last_name"], x[0]["first_name"]),
            ):
                gender_label = "B" if a["gender"] == "M" else "G"
                st.caption(
                    f"{a['last_name']}, {a['first_name']} "
                    f"({gender_label}, Gr. {a['grade']})"
                )

        if one_meet:
            st.markdown("**1 meet only:**")
            for a, _ in sorted(
                one_meet,
                key=lambda x: (x[0]["last_name"], x[0]["first_name"]),
            ):
                gender_label = "B" if a["gender"] == "M" else "G"
                st.caption(
                    f"{a['last_name']}, {a['first_name']} "
                    f"({gender_label}, Gr. {a['grade']})"
                )

# --- Quick links ---
st.divider()
st.markdown("**Quick Links**")
if sport == "XC":
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.page_link("pages/1_Roster.py", label="📋 Roster")
    lc2.page_link("pages/2_Schedule.py", label="📅 Schedule")
    lc3.page_link("pages/4_Results.py", label="🏁 Results")
    lc4.page_link("pages/6_Workout_Groups.py", label="🏃 Workout Groups")
else:
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.page_link("pages/1_Roster.py", label="📋 Roster")
    lc2.page_link("pages/2_Schedule.py", label="📅 Schedule")
    lc3.page_link("pages/3_Lineup.py", label="✏️ Lineup Builder")
    lc4.page_link("pages/4_Results.py", label="🏁 Results")
