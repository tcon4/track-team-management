"""Workout Groups page — XC only."""

import streamlit as st
import db
import shared
from db.xc import _parse_xc_time, fmt_xc_time

season_id = shared.setup()
shared.require_coach()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

if sport != "XC":
    st.title("Workout Groups")
    st.info("Workout groups are for XC only. Switch to XC in the sidebar.")
    st.stop()

st.title("Workout Groups")
st.caption(f"{year} XC — {school_name}")

# ---------------------------------------------------------------------------
# Auto-suggest controls
# ---------------------------------------------------------------------------

meets = db.get_meets(season_id)
past_meets = [m for m in meets if m["meet_date"] <= __import__("datetime").date.today().isoformat()]

if not past_meets:
    st.info("No completed meets yet — workout groups are suggested from race results.")
    st.page_link("pages/4_Results.py", label="Enter results →")
    st.stop()

with st.container(border=True):
    st.markdown("**Auto-suggest from race results**")
    st.caption(
        "Groups are determined by finding the largest time gaps between "
        "consecutive athletes. Early in the season you'll typically see 3 "
        "groups; late season it often consolidates to 2."
    )

    sc1, sc2 = st.columns(2)
    meet_options = {f"{m['meet_date']} · {m['name']}": m["id"] for m in reversed(past_meets)}
    selected_meet_label = sc1.selectbox(
        "Base results on", list(meet_options.keys()), key="wg_meet"
    )
    selected_meet_id = meet_options[selected_meet_label]

    gender_filter = sc2.radio(
        "Gender", ["All", "Boys", "Girls"],
        horizontal=True, key="wg_gender",
    )
    gender_map = {"All": None, "Boys": "M", "Girls": "F"}
    gender_val = gender_map[gender_filter]

    if st.button("Generate groups", type="primary", key="wg_suggest"):
        suggested = db.suggest_workout_groups(
            season_id, meet_id=selected_meet_id, gender=gender_val
        )
        st.session_state["wg_suggested"] = suggested
        st.session_state["wg_source_meet"] = selected_meet_id
        st.rerun()

# ---------------------------------------------------------------------------
# Suggested groups (editable before saving)
# ---------------------------------------------------------------------------

if st.session_state.get("wg_suggested"):
    groups = st.session_state["wg_suggested"]

    st.divider()
    st.markdown("**Suggested groups** — review and adjust before saving")

    for gi, group in enumerate(groups):
        athletes = group["athletes"]
        if not athletes:
            continue

        times = [a["seconds"] for a in athletes]
        avg_time = sum(times) / len(times)
        fastest = min(times)
        slowest = max(times)
        spread = slowest - fastest

        with st.expander(
            f"**Group {group['name']}** — {len(athletes)} athletes "
            f"(avg {fmt_xc_time(avg_time)}, spread {fmt_xc_time(spread)})",
            expanded=True,
        ):
            for ai, athlete in enumerate(athletes):
                ac1, ac2, ac3 = st.columns([3, 2, 1])
                ac1.write(
                    f"{athlete['last_name']}, {athlete['first_name']}"
                )
                ac2.caption(athlete["finish_time"])

                # Move buttons
                move_options = [
                    g["name"] for g in groups if g["name"] != group["name"]
                ]
                if move_options:
                    move_to = ac3.selectbox(
                        "Move to",
                        ["—"] + move_options,
                        key=f"move_{gi}_{ai}",
                        label_visibility="collapsed",
                    )
                    if move_to != "—":
                        target_gi = next(
                            i for i, g in enumerate(groups)
                            if g["name"] == move_to
                        )
                        groups[target_gi]["athletes"].append(athlete)
                        group["athletes"] = [
                            a for a in group["athletes"]
                            if a["athlete_id"] != athlete["athlete_id"]
                        ]
                        st.session_state["wg_suggested"] = groups
                        st.rerun()

    if st.button("Save groups", type="primary", key="wg_save"):
        save_data = []
        for group in groups:
            save_data.append({
                "name": group["name"],
                "athlete_ids": [a["athlete_id"] for a in group["athletes"]],
            })
        db.save_workout_groups(season_id, save_data)
        st.session_state["wg_suggested"] = None
        st.success("Workout groups saved!")
        shared.data_changed()

# ---------------------------------------------------------------------------
# Saved groups (current)
# ---------------------------------------------------------------------------

st.divider()

saved_groups = db.get_workout_groups(season_id)

if saved_groups:
    st.markdown("**Current workout groups**")

    for group in saved_groups:
        members = group["members"]
        with st.expander(
            f"**Group {group['name']}** — {len(members)} athletes",
            expanded=True,
        ):
            if not members:
                st.caption("No athletes in this group.")
                continue

            for mi, member in enumerate(members):
                mc1, mc2 = st.columns([4, 1])
                mc1.write(f"{member['last_name']}, {member['first_name']}")

                other_groups = [g for g in saved_groups if g["id"] != group["id"]]
                if other_groups:
                    move_opts = ["—"] + [g["name"] for g in other_groups]
                    move_to = mc2.selectbox(
                        "Move",
                        move_opts,
                        key=f"saved_move_{group['id']}_{mi}",
                        label_visibility="collapsed",
                    )
                    if move_to != "—":
                        target = next(
                            g for g in other_groups if g["name"] == move_to
                        )
                        db.move_athlete_between_groups(
                            season_id,
                            member["athlete_id"],
                            group["id"],
                            target["id"],
                        )
                        shared.data_changed()

    if st.button("Clear all groups", key="wg_clear"):
        db.save_workout_groups(season_id, [])
        st.success("Groups cleared.")
        shared.data_changed()
else:
    st.caption("No workout groups saved yet. Use auto-suggest above to create them.")
