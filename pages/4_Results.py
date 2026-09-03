"""Results page."""

import streamlit as st
import db
import shared

season_id = shared.setup()
shared.require_coach()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title("Results")
st.caption(f"{year} {sport} — {school_name}")

meets = db.get_meets(season_id)

if not meets:
    st.info("No meets on the schedule yet.")
    st.page_link("pages/2_Schedule.py", label="Add a meet on the Schedule page →")
    st.stop()

# Meet selector — shared between Track and XC
confirm_key = "results_confirmed_meet"

with st.container(border=True):
    meet_options = {f"{m['meet_date']} · {m['name']}": m["id"] for m in meets}
    selected_meet_label = st.selectbox(
        "Select a meet", list(meet_options.keys()), key="results_meet"
    )
    selected_meet_id = meet_options[selected_meet_label]
    selected_meet_obj = db.get_meet(selected_meet_id)
    if selected_meet_obj:
        st.caption(f"Location: {selected_meet_obj['location']}  ·  "
                   f"Host: {selected_meet_obj.get('host_name', '—')}")

    confirmed_id = st.session_state.get(confirm_key)
    if confirmed_id == selected_meet_id:
        if st.button("Change meet", key="results_change_meet"):
            st.session_state[confirm_key] = None
            st.rerun()
    else:
        if st.button("Load results", type="primary", key="results_confirm_meet"):
            st.session_state[confirm_key] = selected_meet_id
            st.rerun()

if st.session_state.get(confirm_key) != selected_meet_id:
    st.stop()


# ###########################################################################
# XC RESULTS
# ###########################################################################

if sport == "XC":
    # --- Existing results for this meet ---
    existing_results = db.get_xc_meet_results(selected_meet_id)
    if existing_results:
        stats = db.get_xc_team_stats(selected_meet_id)
        for gender, label in [("M", "Boys"), ("F", "Girls")]:
            g_stats = stats.get(gender)
            g_results = [r for r in existing_results if r["gender"] == gender]
            if not g_results:
                continue

            with st.expander(f"**{label}** — {len(g_results)} runners", expanded=True):
                if g_stats:
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    sc1.metric("Average", db.fmt_xc_time(g_stats["average"]))
                    sc2.metric("Median", db.fmt_xc_time(g_stats["median"]))
                    sc3.metric("Top 5 Avg", db.fmt_xc_time(g_stats["top5_avg"]))
                    if g_stats["split_1_5"] is not None:
                        sc4.metric("1-5 Split", db.fmt_xc_time(g_stats["split_1_5"]))
                    else:
                        sc4.metric("1-5 Split", "—")

                for r in g_results:
                    pr_flag = " PR" if r["is_pr"] else ""
                    place_str = f"{r['place']}." if r["place"] else ""
                    st.caption(
                        f"{place_str} {r['last_name']}, {r['first_name']} — "
                        f"**{r['finish_time']}**{pr_flag}"
                    )

        st.divider()

    # --- Entry mode ---
    xc_entry_mode = st.radio(
        "Entry method",
        ["Team results URL", "Manual entry"],
        horizontal=True,
        key="xc_entry_mode",
    )

    st.divider()

    # --- Team results URL import ---
    if xc_entry_mode == "Team results URL":
        st.subheader("Import via team results page")
        st.caption(
            "Go to the meet on nc.milesplit.com, click the **Teams** tab, "
            "then click your school. Copy that URL and paste it here."
        )

        team_url = st.text_input(
            "Team results URL",
            placeholder="https://nc.milesplit.com/meets/696119-.../teams/22928",
            key="xc_team_url_input",
        )

        xc_distance = st.selectbox(
            "Race distance", ["2mi", "3K", "5K"],
            key="xc_distance_select",
        )

        if st.button("Fetch & preview", type="primary",
                     disabled=not team_url.strip(), key="xc_fetch_btn"):
            from milesplit import parse_team_results_html, match_to_roster, _fetch_html

            with st.spinner("Fetching results..."):
                html, err = _fetch_html(team_url.strip())

            if err:
                st.error(f"Couldn't fetch page: {err}")
            else:
                meet_data = db.get_meet(selected_meet_id)
                if meet_data and not meet_data.get("milesplit_url"):
                    db.update_meet(
                        selected_meet_id,
                        meet_data["name"],
                        meet_data["meet_date"],
                        meet_data["location"],
                        meet_data["host_school_id"],
                        meet_data.get("girls_place") or "",
                        meet_data.get("boys_place") or "",
                        team_url.strip(),
                    )
                raw_results = parse_team_results_html(html)
                if not raw_results:
                    st.error("No results found on that page.")
                else:
                    roster = db.get_roster(season_id)
                    matched_data = match_to_roster(raw_results, roster)
                    st.session_state["xc_matched"] = matched_data["matched"]
                    st.session_state["xc_absent"] = matched_data["absent"]
                    st.session_state["xc_meet_id"] = selected_meet_id
                    st.session_state["xc_total"] = len(raw_results)
                    st.session_state["xc_distance"] = xc_distance
                    st.rerun()

        # Preview & save XC matched results
        if (st.session_state.get("xc_matched") is not None
                and st.session_state.get("xc_meet_id") == selected_meet_id):

            matched = st.session_state["xc_matched"]
            absent = st.session_state["xc_absent"]
            total = st.session_state["xc_total"]
            dist = st.session_state.get("xc_distance", "2mi")

            st.success(
                f"Parsed {total} results · "
                f"**{len(matched)} matched** to your roster · "
                f"{len(absent)} DNF/DNS"
            )

            if matched:
                st.markdown("**Results to import:**")
                preview_rows = []
                for r in matched:
                    confidence_icon = (
                        "✓" if r["match_confidence"] == "exact" else
                        "~" if r["match_confidence"] in ("initial", "last_only") else
                        "?"
                    )
                    preview_rows.append({
                        "": confidence_icon,
                        "Athlete": f"{r['last_name']}, {r['first_name']}",
                        "Time": r["result_value"],
                        "Place": r["place"] or "—",
                    })
                st.dataframe(preview_rows, use_container_width=True,
                             hide_index=True)

            if matched and st.button("Save all matched results",
                                     type="primary", key="xc_save_btn"):
                db.clear_xc_results(selected_meet_id)
                saved = 0
                for r in matched:
                    try:
                        db.save_xc_result(
                            meet_id=selected_meet_id,
                            athlete_id=r["athlete_id"],
                            finish_time=r["result_value"],
                            place=r["place"],
                            distance=dist,
                        )
                        saved += 1
                    except Exception as ex:
                        st.warning(f"Skipped {r['last_name']}: {ex}")

                st.success(f"Saved {saved} XC results.")
                st.session_state["xc_matched"] = None
                shared.data_changed()

    # --- Manual entry ---
    elif xc_entry_mode == "Manual entry":
        st.subheader("Enter XC results")

        xc_distance_manual = st.selectbox(
            "Race distance", ["2mi", "3K", "5K"],
            key="xc_distance_manual",
        )

        gender_filter = st.radio(
            "Gender", ["M", "F"], horizontal=True,
            format_func=lambda x: "Boys" if x == "M" else "Girls",
            key="xc_manual_gender",
        )

        roster_all = db.get_roster(season_id)
        gender_roster = [
            a for a in roster_all
            if a["gender"] == gender_filter and a["status"] == "active"
        ]

        if not gender_roster:
            st.info("No active athletes on roster for this gender.")
        else:
            st.caption(
                "Enter finish times as MM:SS.ss (e.g. 14:35.68). "
                "Leave blank to skip."
            )

            time_inputs: dict[int, str] = {}
            place_inputs: dict[int, str] = {}

            hc = st.columns([3, 2, 1])
            hc[0].markdown("**Athlete**")
            hc[1].markdown("**Time**")
            hc[2].markdown("**Place**")

            for athlete in sorted(gender_roster,
                                  key=lambda a: (a["last_name"], a["first_name"])):
                rc = st.columns([3, 2, 1])
                rc[0].write(
                    f"{athlete['last_name']}, {athlete['first_name']} "
                    f"(Gr. {athlete['grade']})"
                )
                time_inputs[athlete["id"]] = rc[1].text_input(
                    "Time",
                    key=f"xc_t_{selected_meet_id}_{athlete['id']}",
                    label_visibility="collapsed",
                )
                place_inputs[athlete["id"]] = rc[2].text_input(
                    "Place",
                    key=f"xc_p_{selected_meet_id}_{athlete['id']}",
                    label_visibility="collapsed",
                )

            if st.button("Save results", type="primary", key="xc_manual_save"):
                saved = 0
                for aid, time_val in time_inputs.items():
                    if time_val.strip():
                        place_raw = place_inputs.get(aid, "").strip()
                        try:
                            place = int(place_raw) if place_raw else None
                        except ValueError:
                            place = None
                        try:
                            db.save_xc_result(
                                meet_id=selected_meet_id,
                                athlete_id=aid,
                                finish_time=time_val.strip(),
                                place=place,
                                distance=xc_distance_manual,
                            )
                            saved += 1
                        except Exception as ex:
                            st.error(f"Error saving result: {ex}")
                if saved:
                    st.success(f"Saved {saved} result(s).")
                    shared.data_changed()

    st.stop()


# ###########################################################################
# TRACK RESULTS (existing code, unchanged)
# ###########################################################################

entry_mode = st.radio(
    "Entry method",
    ["Team results URL", "Paste raw text", "Milesplit URL", "Manual entry"],
    horizontal=True,
)

st.divider()

# ---------------------------------------------------------------------------
# TEAM RESULTS URL (primary — free, no paywall)
# ---------------------------------------------------------------------------

if entry_mode == "Team results URL":
    st.subheader("Import via team results page")
    st.caption(
        "Go to the meet on nc.milesplit.com, click the **Teams** tab, "
        "then click your school. Copy that URL and paste it here. "
        "No PRO account needed — this page is always free."
    )
    st.code(
        "https://nc.milesplit.com/meets/{ID}-{slug}/teams/{TEAM_ID}",
        language=None,
    )

    team_url = st.text_input(
        "Team results URL",
        placeholder="https://nc.milesplit.com/meets/737047-.../teams/22928",
        key="team_url_input",
    )

    if st.button("Fetch & preview", type="primary",
                 disabled=not team_url.strip()):
        from milesplit import parse_team_results_html, match_to_roster, _fetch_html

        with st.spinner("Fetching your team's results…"):
            html, err = _fetch_html(team_url.strip())

        if err:
            st.error(f"Couldn't fetch page: {err}")
        else:
            meet_data = db.get_meet(selected_meet_id)
            if meet_data and not meet_data.get("milesplit_url"):
                db.update_meet(
                    selected_meet_id,
                    meet_data["name"],
                    meet_data["meet_date"],
                    meet_data["location"],
                    meet_data["host_school_id"],
                    meet_data.get("girls_place") or "",
                    meet_data.get("boys_place") or "",
                    team_url.strip(),
                )
            raw_results = parse_team_results_html(html)
            if not raw_results:
                st.error(
                    "No results found on that page. "
                    "Make sure the URL ends in /teams/{TEAM_ID} "
                    "and that results have been uploaded to this meet."
                )
            else:
                roster = db.get_roster(season_id)
                matched_data = match_to_roster(raw_results, roster)
                st.session_state["ms_matched"] = matched_data["matched"]
                st.session_state["ms_absent"] = matched_data["absent"]
                st.session_state["ms_meet_id"] = selected_meet_id
                st.session_state["ms_total"] = len(raw_results)
                st.rerun()

# ---------------------------------------------------------------------------
# PASTE RAW TEXT
# ---------------------------------------------------------------------------

if entry_mode == "Paste raw text":
    st.subheader("Paste Milesplit raw results")
    st.caption(
        "1. Go to your meet on nc.milesplit.com and open the results page  \n"
        "2. Change the URL from `/formatted` to `/raw` (or click the Raw link if visible)  \n"
        "3. Select all text on that page (Ctrl+A / Cmd+A) and paste it below"
    )

    raw_text = st.text_area(
        "Paste raw results here",
        height=200,
        placeholder="Pierre Timing    DirectAthletics MeetPro\n"
                    "          Mooresville Middle Meet...\n"
                    "Boys 100 Meters\nFinals\n=====...",
        key="ms_paste_input",
    )

    if st.button("Preview matches", type="primary",
                 disabled=not raw_text.strip()):
        from milesplit import parse_raw_results, match_to_roster

        raw_results = parse_raw_results(raw_text)
        if not raw_results:
            st.error(
                "Couldn't find any results in that text. "
                "Make sure you're pasting from the /raw page, "
                "not the formatted results page."
            )
        else:
            roster = db.get_roster(season_id)
            school_obj = db.get_school(st.session_state.school_id)
            school_name_match = school_obj["name"] if school_obj else ""

            matched_data = match_to_roster(
                raw_results, roster, team_name=school_name_match
            )
            st.session_state["ms_matched"] = matched_data["matched"]
            st.session_state["ms_absent"] = matched_data["absent"]
            st.session_state["ms_meet_id"] = selected_meet_id
            st.session_state["ms_total"] = len(raw_results)
            st.rerun()

# ---------------------------------------------------------------------------
# MILESPLIT URL IMPORT
# ---------------------------------------------------------------------------

elif entry_mode == "Milesplit URL":
    st.subheader("Import via URL")
    st.caption(
        "Paste the meet results URL from nc.milesplit.com. "
        "Works with `/raw`, `/formatted`, or the base results URL. "
        "Note: may require a Milesplit PRO account for some meets."
    )

    ms_url = st.text_input(
        "Milesplit results URL",
        placeholder="https://nc.milesplit.com/meets/XXXXX-.../results/YYYYY",
        key="ms_url_input",
    )

    if st.button("Fetch & preview", type="primary",
                 disabled=not ms_url.strip()):
        from milesplit import (
            fetch_raw_text, parse_raw_results,
            match_to_roster, is_valid_milesplit_url
        )

        if not is_valid_milesplit_url(ms_url):
            st.error(
                "That doesn't look like a Milesplit results URL. "
                "Make sure it contains /meets/ and /results/."
            )
        else:
            with st.spinner("Fetching results from Milesplit…"):
                text, err = fetch_raw_text(ms_url)

            if err:
                st.error(f"Couldn't fetch results: {err}")
            else:
                raw_results = parse_raw_results(text)
                roster = db.get_roster(season_id)
                school_obj = db.get_school(st.session_state.school_id)
                school_name_match = school_obj["name"] if school_obj else ""

                matched_data = match_to_roster(
                    raw_results, roster, team_name=school_name_match
                )

                st.session_state["ms_matched"] = matched_data["matched"]
                st.session_state["ms_absent"] = matched_data["absent"]
                st.session_state["ms_meet_id"] = selected_meet_id
                st.session_state["ms_total"] = len(raw_results)
                st.rerun()

# ---------------------------------------------------------------------------
# Preview & save matched results
# ---------------------------------------------------------------------------

if (st.session_state.get("ms_matched") is not None
        and st.session_state.get("ms_meet_id") == selected_meet_id):

    matched = st.session_state["ms_matched"]
    absent = st.session_state["ms_absent"]
    total = st.session_state["ms_total"]

    st.success(
        f"Parsed {total} total results · "
        f"**{len(matched)} matched** to your roster · "
        f"{len(absent)} DNF/DNS"
    )

    if matched:
        st.markdown("**Results to import:**")
        all_events = db.get_track_events()

        preview_rows = []
        for r in matched:
            confidence_icon = (
                "✓" if r["match_confidence"] == "exact" else
                "~" if r["match_confidence"] in ("initial", "last_only") else
                "?"
            )
            preview_rows.append({
                "": confidence_icon,
                "Event": r["event"],
                "Athlete": f"{r['last_name']}, {r['first_name']}",
                "Result": r["result_value"],
                "Place": r["place"] or "—",
            })

        st.dataframe(preview_rows, use_container_width=True, hide_index=True)
        st.caption(
            "✓ = exact name match · ~ = partial match · "
            "? = ambiguous — review before saving"
        )

    if absent:
        with st.expander(f"DNF / DNS athletes ({len(absent)})"):
            for r in absent:
                st.caption(
                    f"{r['last_name']}, {r['first_name']} — "
                    f"{r['event']} — {r['result_value']}"
                )

    if matched and st.button("Save all matched results", type="primary"):
        db.clear_meet_results(selected_meet_id)
        all_events = db.get_track_events()
        saved = skipped = assigned = 0
        unmatched_events = []

        for r in matched:
            matched_event = db.match_event_by_number(
                r["event"], r["gender"], all_events
            )

            if matched_event:
                try:
                    db.save_track_result(
                        meet_id=selected_meet_id,
                        athlete_id=r["athlete_id"],
                        event_id=matched_event["id"],
                        result_value=r["result_value"],
                        place=r["place"],
                    )
                    saved += 1

                    existing = db.get_athlete_events(
                        r["athlete_id"], season_id
                    )
                    if not any(e["id"] == matched_event["id"]
                               for e in existing):
                        db.assign_event(
                            r["athlete_id"], season_id,
                            matched_event["id"]
                        )
                        assigned += 1

                except Exception as ex:
                    st.warning(f"Skipped {r['last_name']}: {ex}")
                    skipped += 1
            else:
                unmatched_events.append(f"{r['event']} ({r['gender']})")
                skipped += 1

        st.success(
            f"Saved {saved} results · "
            f"{assigned} new event assignments added · "
            f"{skipped} skipped (event not matched)."
        )
        if unmatched_events:
            unique = sorted(set(unmatched_events))
            st.warning(f"Unmatched events: {', '.join(unique)}")
            db_events = [(e['name'], e['gender']) for e in all_events]
            st.caption(f"DB events: {db_events}")
        st.session_state["ms_matched"] = None
        shared.data_changed()

# ---------------------------------------------------------------------------
# MANUAL ENTRY
# ---------------------------------------------------------------------------

elif entry_mode == "Manual entry":
    gender_for_events = st.radio(
        "Gender", ["M", "F"], horizontal=True,
        format_func=lambda x: "Boys" if x == "M" else "Girls",
        key="results_gender"
    )
    events = db.get_track_events(gender=gender_for_events)
    event_names = [e["name"] for e in events]
    selected_event_name = st.selectbox("Event", event_names)
    selected_event = next(
        (e for e in events if e["name"] == selected_event_name), None
    )

    st.subheader(f"Enter results — {selected_event_name}")
    st.caption(
        "Times: MM:SS.s (e.g. 1:54.3) or seconds (e.g. 11.24). "
        "Field events: meters (e.g. 5.82) or feet-inches (e.g. 18-04). "
        "Leave blank to skip."
    )

    roster_all = db.get_roster(season_id)
    gender_roster = [a for a in roster_all
                     if a["gender"] == gender_for_events
                     and a["status"] == "active"]

    if not gender_roster:
        st.info("No active athletes on roster for this gender.")
    else:
        result_inputs: dict[int, str] = {}
        place_inputs: dict[int, str] = {}

        hc = st.columns([3, 2, 1])
        hc[0].markdown("**Athlete**")
        hc[1].markdown("**Result**")
        hc[2].markdown("**Place**")

        for athlete in gender_roster:
            rc = st.columns([3, 2, 1])
            rc[0].write(
                f"{athlete['last_name']}, {athlete['first_name']} "
                f"(Gr. {athlete['grade']})"
            )
            result_inputs[athlete["id"]] = rc[1].text_input(
                "Result",
                key=f"res_{selected_meet_id}_{athlete['id']}_{selected_event['id']}",
                label_visibility="collapsed",
            )
            place_inputs[athlete["id"]] = rc[2].text_input(
                "Place",
                key=f"pl_{selected_meet_id}_{athlete['id']}_{selected_event['id']}",
                label_visibility="collapsed",
            )

        if st.button("Save results", type="primary"):
            saved = assigned = 0
            for aid, result_val in result_inputs.items():
                if result_val.strip():
                    place_raw = place_inputs.get(aid, "").strip()
                    try:
                        place = int(place_raw) if place_raw else None
                    except ValueError:
                        place = None
                    try:
                        db.save_track_result(
                            meet_id=selected_meet_id,
                            athlete_id=aid,
                            event_id=selected_event["id"],
                            result_value=result_val.strip(),
                            place=place,
                        )
                        saved += 1
                        existing = db.get_athlete_events(aid, season_id)
                        if not any(e["id"] == selected_event["id"]
                                   for e in existing):
                            db.assign_event(aid, season_id,
                                            selected_event["id"])
                            assigned += 1
                    except Exception as ex:
                        st.error(f"Error saving result: {ex}")
            if saved:
                msg = f"Saved {saved} result(s)."
                if assigned:
                    msg += f" {assigned} new event assignment(s) added."
                st.success(msg)
                shared.data_changed()
