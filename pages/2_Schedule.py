"""Schedule page."""

import streamlit as st
from datetime import date
import db
import shared

season_id = shared.setup()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title("Schedule")
st.caption(f"{year} {sport} — {school_name}")

meets = db.get_meets(season_id)
today = date.today().isoformat()

if not meets:
    st.info("No meets scheduled yet. Add your first meet below to start tracking your season!")
else:
    # Season progress bar
    past_count = sum(1 for m in meets if m["meet_date"] < today)
    progress_val = past_count / len(meets) if meets else 0
    st.progress(progress_val, text=f"{past_count} of {len(meets)} meets complete")
    st.write("")

    # Find next upcoming meet
    upcoming = [m for m in meets if m["meet_date"] >= today]
    next_meet_id = upcoming[0]["id"] if upcoming else None

    for meet in meets:
        is_past = meet["meet_date"] < today
        is_host = meet["host_school_id"] == st.session_state.school_id
        is_next = meet["id"] == next_meet_id
        if is_next:
            status_pill = "⭐ Next up"
        elif is_host:
            status_pill = "\U0001f3e0 You're hosting"
        elif is_past:
            status_pill = "\u2713 Past"
        else:
            status_pill = "Upcoming"

        with st.container(border=True):
            # Meet header row
            hc1, hc2, hc3, hc4 = st.columns([2, 3, 2, 1])
            hc1.markdown(f"**{meet['meet_date']}**")
            hc2.markdown(f"**{meet['name']}**")
            hc3.write(f"{status_pill} \u00b7 {meet['location']}")
            if shared.is_coach():
                if hc4.button("Edit", key=f"meet_edit_{meet['id']}"):
                    st.session_state.editing_meet = meet["id"]
                    st.rerun()

            # Score + Milesplit link row
            sc1, sc2, sc3 = st.columns([2, 2, 3])
            gp = meet.get("girls_place") or ""
            bp = meet.get("boys_place") or ""
            ms = meet.get("milesplit_url") or ""
            if gp:
                sc1.caption(f"\U0001f467 Girls: {gp}")
            if bp:
                sc2.caption(f"\U0001f466 Boys: {bp}")
            if ms:
                sc3.markdown(f"[View on Milesplit \u2197]({ms})")

            # Meet report (results)
            report = db.get_meet_report(meet["id"])
            has_results = any(
                report[g][t]
                for g in ("M", "F")
                for t in ("field", "running", "relay")
            )

            if has_results:
                with st.expander("Meet report"):
                    for gender_val, gender_label in [("F", "Girls"), ("M", "Boys")]:
                        g_data = report[gender_val]
                        if not any(g_data.values()):
                            continue
                        st.markdown(f"**{gender_label}**")

                        for section, section_label in [
                            ("field", "Field Events"),
                            ("running", "Running Events"),
                            ("relay", "Relays"),
                        ]:
                            rows = g_data[section]
                            if not rows:
                                continue

                            events_seen: dict = {}
                            for r in rows:
                                events_seen.setdefault(r["event_name"], []).append(r)

                            st.caption(section_label)
                            for event_name, athletes in events_seen.items():
                                st.markdown(f"**{event_name}**")
                                for a in athletes:
                                    pr_badge = " \u2713PR" if a["is_pr"] else ""
                                    place_str = shared.format_place(a["place"])

                                    profile_key = (
                                        f"rpt_profile_{meet['id']}_"
                                        f"{a['athlete_id']}_{a.get('event_name', '')}"
                                    )
                                    is_open = st.session_state.get(profile_key, False)

                                    rc1, rc2 = st.columns([5, 1])
                                    rc1.write(
                                        f"{a['last_name']}, {a['first_name']} \u00b7 "
                                        f"{a['result_value']} \u00b7 {place_str}{pr_badge}"
                                    )
                                    btn_label = "\u25b2" if is_open else "\u25bc"
                                    if rc2.button(btn_label, key=f"btn_{profile_key}"):
                                        st.session_state[profile_key] = not is_open
                                        st.rerun()

                                    if is_open:
                                        with st.container(border=True):
                                            profile = db.get_athlete_profile(
                                                a["athlete_id"], season_id
                                            )
                                            ath = profile["athlete"]
                                            st.caption(
                                                f"Gr. {ath.get('grade')} \u00b7 "
                                                f"{'Boys' if ath.get('gender') == 'M' else 'Girls'}"
                                            )
                                            bests = profile["season_bests"]
                                            if bests:
                                                st.markdown("**Season bests**")
                                                for ev, data in bests.items():
                                                    pr_flag = " \u2713PR" if data["has_pr"] else ""
                                                    st.write(
                                                        f"{ev}: {data['result_value']}{pr_flag}"
                                                    )
                                            history = profile["history"]
                                            if len(history) > 1:
                                                st.markdown("**Meet history**")
                                                for h in history:
                                                    pr_flag = " \u2713PR" if h["is_pr"] else ""
                                                    place_h = (
                                                        f" \u00b7 {shared.format_place(h['place'])}"
                                                        if h["place"] else ""
                                                    )
                                                    st.caption(
                                                        f"{h['meet_date']} {h['meet_name']} \u00b7 "
                                                        f"{h['event_name']} \u00b7 "
                                                        f"{h['result_value']}{place_h}{pr_flag}"
                                                    )

        # Edit panel (coach only)
        if shared.is_coach() and st.session_state.get("editing_meet") == meet["id"]:
            with st.container(border=True):
                st.caption(f"Editing: {meet['name']}")
                with st.form(f"edit_meet_{meet['id']}"):
                    em1, em2 = st.columns(2)
                    new_name = em1.text_input("Meet name", value=meet["name"])
                    new_date = em2.date_input(
                        "Date",
                        value=date.fromisoformat(meet["meet_date"])
                    )
                    em3, em4 = st.columns(2)
                    new_loc = em3.text_input("Location", value=meet["location"])
                    schools = db.get_schools()
                    school_names = [s["name"] for s in schools]
                    host_idx = next(
                        (i for i, s in enumerate(schools)
                         if s["id"] == meet["host_school_id"]), 0
                    )
                    new_host_name = em4.selectbox("Host school", school_names,
                                                  index=host_idx)
                    new_host_id = next(
                        s["id"] for s in schools if s["name"] == new_host_name
                    )
                    ep1, ep2 = st.columns(2)
                    new_girls = ep1.text_input(
                        "Girls team place",
                        value=meet.get("girls_place") or "",
                        placeholder="e.g. 2nd of 6"
                    )
                    new_boys = ep2.text_input(
                        "Boys team place",
                        value=meet.get("boys_place") or "",
                        placeholder="e.g. 1st of 6"
                    )
                    new_ms = st.text_input(
                        "Milesplit results URL",
                        value=meet.get("milesplit_url") or "",
                        placeholder="https://nc.milesplit.com/meets/.../teams/22928"
                    )
                    es1, es2, es3 = st.columns(3)
                    save_m = es1.form_submit_button("Save", type="primary")
                    cancel_m = es2.form_submit_button("Cancel")
                    delete_m = es3.form_submit_button("Delete meet")

                if save_m:
                    db.update_meet(
                        meet["id"], new_name, new_date.isoformat(),
                        new_loc, new_host_id,
                        new_girls, new_boys, new_ms
                    )
                    st.session_state.editing_meet = None
                    st.success("Meet updated.")
                    shared.data_changed()
                if cancel_m:
                    st.session_state.editing_meet = None
                    st.rerun()
                if delete_m:
                    db.delete_meet(meet["id"])
                    st.session_state.editing_meet = None
                    st.success("Meet deleted.")
                    shared.data_changed()

st.divider()

# ---------------------------------------------------------------------------
# Add meet form
# ---------------------------------------------------------------------------

if not shared.is_coach():
    st.stop()

with st.expander("+ Add meet"):
    with st.form("add_meet_form", clear_on_submit=True):
        am1, am2 = st.columns(2)
        meet_name = am1.text_input("Meet name",
                                   placeholder="e.g. Conference Championship")
        meet_date_input = am2.date_input("Date", value=date.today())
        am3, am4 = st.columns(2)
        meet_loc = am3.text_input("Location",
                                  placeholder="e.g. Jefferson MS Track")
        schools = db.get_schools()
        school_names_add = [s["name"] for s in schools]
        host_name_add = am4.selectbox("Host school", school_names_add)
        host_id_add = next(
            s["id"] for s in schools if s["name"] == host_name_add
        )
        add_meet_btn = st.form_submit_button("Add meet", type="primary")

    if add_meet_btn:
        if not meet_name.strip() or not meet_loc.strip():
            st.error("Meet name and location are required.")
        else:
            db.add_meet(season_id, meet_name,
                        meet_date_input.isoformat(), meet_loc, host_id_add)
            st.success(f"Added: {meet_name}")
            shared.data_changed()
