"""Roster & Events page."""

import streamlit as st
import pandas as pd
import altair as alt
import db
import shared
from db.results import _parse_result


def _fmt_time(seconds: float) -> str:
    """Format seconds as M:SS or S.ss for axis labels."""
    if seconds >= 60:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}:{s:05.2f}"
    return f"{seconds:.2f}"

season_id = shared.setup()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title("Roster")
st.caption(f"{year} {sport} — {school_name}")

gender_filter = st.radio("View", ["All", "Boys (M)", "Girls (F)"],
                         horizontal=True)
gender_map = {"All": None, "Boys (M)": "M", "Girls (F)": "F"}
selected_gender = gender_map[gender_filter]

roster = db.get_roster(season_id)
if sport == "XC":
    xc_bests_list = db.get_xc_season_bests(season_id)
    season_bests = {b["athlete_id"]: b["season_best"] for b in xc_bests_list}
    all_event_assignments = {}
else:
    season_bests = {}
    all_event_assignments = db.get_all_athlete_events(season_id)

if selected_gender:
    roster = [a for a in roster if a["gender"] == selected_gender]

# Stats
stats = db.get_roster_stats(season_id)
cols = st.columns(5 if stats.get("alumni") else 4)
cols[0].metric("Total", stats["total"])
cols[1].metric("Active", stats["active"])
cols[2].metric("Injured", stats["injured"])
cols[3].metric("Inactive", stats["inactive"])
if stats.get("alumni"):
    cols[4].metric("Alumni", stats["alumni"])

from datetime import date
if year < date.today().year:
    eighth_graders = [a for a in roster if a["grade"] == 8 and a["status"] == "active"]
    if eighth_graders:
        if st.button(
            f"Graduate {len(eighth_graders)} 8th graders to alumni",
            help="Marks active 8th graders on this roster as alumni",
        ):
            count = db.graduate_athletes(season_id)
            st.success(f"Graduated {count} athletes to alumni status.")
            shared.data_changed()

st.divider()

# ---------------------------------------------------------------------------
# Roster list
# ---------------------------------------------------------------------------

if not roster:
    st.info("No athletes on the roster yet. Use one of the options below to add athletes individually, import a CSV, or upload a tryout spreadsheet.")
else:
    for athlete in roster:
        aid = athlete["id"]
        sb = season_bests.get(aid, "—")
        gender_label = "Boys" if athlete["gender"] == "M" else "Girls"
        status = athlete["status"]
        status_icon = {"active": "\U0001f7e2", "injured": "\U0001f7e1",
                       "inactive": "\u26ab", "alumni": "\U0001f393"}.get(status, "\u26aa")

        if sport == "Track":
            events = all_event_assignments.get(aid, [])
            event_str = ", ".join(e["name"] for e in events) if events else "—"
        else:
            event_str = sb

        col_name, col_edit = st.columns([5, 1])
        is_profile_open = st.session_state.get("profile_athlete") == aid
        with col_name:
            if st.button(
                f"**{athlete['last_name']}, {athlete['first_name']}**",
                key=f"profile_{aid}", use_container_width=True
            ):
                st.session_state.profile_athlete = None if is_profile_open else aid
                st.rerun()
            st.caption(f"Gr. {athlete['grade']} \u00b7 {gender_label} \u00b7 {status_icon}")

        is_editing = st.session_state.editing_athlete == aid
        if shared.is_coach():
            btn_label = "\u2715" if is_editing else "Edit"
            if col_edit.button(btn_label, key=f"edit_{aid}"):
                st.session_state.editing_athlete = None if is_editing else aid
                st.rerun()

        # ---- Athlete profile panel ----
        if is_profile_open and sport == "Track":
            with st.container(border=True):
                profile = db.get_athlete_profile(aid, season_id)
                bests = profile["season_bests"]
                history = profile["history"]

                st.caption(
                    f"{athlete['first_name']} {athlete['last_name']} \u00b7 "
                    f"Gr. {athlete['grade']} \u00b7 {gender_label} \u00b7 "
                    f"{status_icon} {status.capitalize()}"
                )
                if event_str != "—":
                    st.caption(f"Events: {event_str}")

                if not history:
                    if bests:
                        st.markdown("**Season bests**")
                        for ev, data in bests.items():
                            pr_flag = " \u2713 PR" if data["has_pr"] else ""
                            st.write(f"{ev}: **{data['result_value']}**{pr_flag}")
                    else:
                        st.caption("No results recorded yet this season.")

                if history:
                    # Build chart data before layout
                    import math
                    chart_rows = []
                    for h in history:
                        try:
                            val = _parse_result(h["result_value"])
                            chart_rows.append({
                                "Meet": h["meet_name"],
                                "Date": h["meet_date"],
                                "Event": h["event_name"],
                                "Seconds": val,
                                "Result": h["result_value"],
                                "PR": bool(h["is_pr"]),
                            })
                        except (ValueError, ZeroDivisionError):
                            continue

                    chartable = []
                    if chart_rows:
                        chart_df = pd.DataFrame(chart_rows)
                        event_counts = chart_df["Event"].value_counts()
                        chartable = event_counts[event_counts >= 2].index.tolist()

                    # Side-by-side: bests + history left, trends right
                    col_left, col_right = st.columns(
                        [1, 1] if chartable else [1, 0.01]
                    )

                    with col_left:
                        if bests:
                            st.markdown("**Season bests**")
                            for ev, data in bests.items():
                                pr_flag = " \u2713 PR" if data["has_pr"] else ""
                                st.write(f"{ev}: **{data['result_value']}**{pr_flag}")

                        st.markdown("**Meet history**")
                        for h in history:
                            pr_flag = " \u2713 PR" if h["is_pr"] else ""
                            place_str = f" \u00b7 {shared.format_place(h['place'])}" if h["place"] else ""
                            st.caption(
                                f"{h['meet_date']} — {h['meet_name']} \u00b7 "
                                f"{h['event_name']} \u00b7 "
                                f"{h['result_value']}{place_str}{pr_flag}"
                            )

                    if chartable:
                        with col_right:
                            st.markdown("**Season trends**")
                            for ev_name in chartable:
                                ev_df = (
                                    chart_df[chart_df["Event"] == ev_name]
                                    .sort_values("Date")
                                    .reset_index(drop=True)
                                )
                                ev_df["Order"] = range(len(ev_df))

                                is_field = any(
                                    h["event_type"] == "field"
                                    for h in history
                                    if h["event_name"] == ev_name
                                )

                                y_min = ev_df["Seconds"].min()
                                y_max = ev_df["Seconds"].max()
                                rng = y_max - y_min if y_max > y_min else 1
                                padding = rng * 0.08
                                y_scale = alt.Scale(
                                    domain=[y_min - padding, y_max + padding],
                                )

                                ev_df["Label"] = ev_df["Seconds"].apply(_fmt_time)

                                span = y_max - y_min
                                step = 15 if span > 30 else (5 if span > 10 else 2)
                                tick_start = math.floor(y_min / step) * step
                                tick_end = math.ceil(y_max / step) * step + step
                                tick_vals = list(range(int(tick_start), int(tick_end), int(step)))

                                time_label_expr = (
                                    "datum.value >= 60 "
                                    "? floor(datum.value / 60) + ':' "
                                    "+ (datum.value % 60 < 10 ? '0' : '') "
                                    "+ format(datum.value % 60, '.0f') "
                                    ": format(datum.value, '.1f')"
                                )

                                base = alt.Chart(ev_df).encode(
                                    x=alt.X(
                                        "Meet:N",
                                        sort=alt.SortField("Order"),
                                        title=None,
                                        axis=alt.Axis(
                                            labelAngle=-30,
                                            labelFontSize=9,
                                        ),
                                    ),
                                )

                                area = base.mark_area(
                                    opacity=0.1, color="#4A90D9",
                                ).encode(
                                    y=alt.Y(
                                        "Seconds:Q", scale=y_scale, title=ev_name,
                                        axis=alt.Axis(
                                            values=tick_vals,
                                            labelExpr=time_label_expr,
                                            grid=True, gridDash=[2, 2], gridOpacity=0.3,
                                        ),
                                    ),
                                )

                                line = base.mark_line(
                                    strokeWidth=2.5, color="#4A90D9",
                                ).encode(y=alt.Y("Seconds:Q", scale=y_scale))

                                points = base.mark_circle(size=60).encode(
                                    y=alt.Y("Seconds:Q", scale=y_scale),
                                    color=alt.condition(
                                        alt.datum.PR, alt.value("#E8542F"), alt.value("#4A90D9"),
                                    ),
                                    tooltip=[
                                        alt.Tooltip("Meet:N"),
                                        alt.Tooltip("Label:N", title="Result"),
                                    ],
                                )

                                labels = base.mark_text(
                                    dy=-12, fontSize=10, fontWeight="bold",
                                ).encode(
                                    y=alt.Y("Seconds:Q", scale=y_scale),
                                    text="Label:N",
                                    color=alt.condition(
                                        alt.datum.PR, alt.value("#E8542F"), alt.value("#555"),
                                    ),
                                )

                                chart = (area + line + points + labels).properties(height=220)
                                st.altair_chart(chart, use_container_width=True)

                                first = ev_df["Seconds"].iloc[0]
                                last = ev_df["Seconds"].iloc[-1]
                                diff = last - first
                                if is_field:
                                    if diff > 0:
                                        st.caption(f"↑ Improved by {_fmt_time(abs(diff))}")
                                    elif diff < 0:
                                        st.caption(f"↓ Down by {_fmt_time(abs(diff))}")
                                else:
                                    if diff < 0:
                                        st.caption(f"↓ Improved by {_fmt_time(abs(diff))}")
                                    elif diff > 0:
                                        st.caption(f"↑ Slower by {_fmt_time(abs(diff))}")

                if st.button("Close profile", key=f"close_profile_{aid}"):
                    st.session_state.profile_athlete = None
                    st.rerun()

        # ---- XC athlete profile panel ----
        elif is_profile_open and sport == "XC":
            from db.xc import _parse_xc_time, fmt_xc_time
            with st.container(border=True):
                profile = db.get_xc_athlete_profile(aid, season_id)
                history = profile["history"]

                st.caption(
                    f"{athlete['first_name']} {athlete['last_name']} · "
                    f"Gr. {athlete['grade']} · {gender_label} · "
                    f"{status_icon} {status.capitalize()}"
                )

                if profile["season_best"]:
                    st.write(f"Season best: **{profile['season_best']}**")

                if not history:
                    st.caption("No XC results recorded yet this season.")
                elif history:
                    import math

                    career = db.get_xc_career_results(
                        aid, st.session_state.school_id
                    )

                    chart_rows = []
                    for h in career:
                        try:
                            val = _parse_xc_time(h["finish_time"])
                            chart_rows.append({
                                "Date": h["meet_date"],
                                "Meet": h["meet_name"],
                                "Seconds": val,
                                "Label": h["finish_time"],
                                "PR": bool(h["is_pr"]),
                                "Year": str(h["year"]),
                            })
                        except (ValueError, ZeroDivisionError):
                            continue

                    has_chart = len(chart_rows) >= 2
                    multi_season = len(set(r["Year"] for r in chart_rows)) > 1

                    col_left, col_right = st.columns(
                        [1, 1] if has_chart else [1, 0.01]
                    )

                    with col_left:
                        st.markdown("**Meet history**")
                        for h in history:
                            pr_flag = " ✓ PR" if h["is_pr"] else ""
                            place_str = (
                                f" · {shared.format_place(h['place'])}"
                                if h["place"] else ""
                            )
                            st.caption(
                                f"{h['meet_date']} — {h['meet_name']} · "
                                f"{h['distance']} · "
                                f"{h['finish_time']}{place_str}{pr_flag}"
                            )

                    if has_chart:
                        with col_right:
                            title = "Performance history" if multi_season else "Season trends"
                            st.markdown(f"**{title}**")
                            chart_df = pd.DataFrame(chart_rows)
                            chart_df = chart_df.sort_values("Date").reset_index(drop=True)
                            chart_df["Order"] = range(len(chart_df))

                            y_min = chart_df["Seconds"].min()
                            y_max = chart_df["Seconds"].max()

                            span = y_max - y_min
                            if span > 120:
                                step = 60
                            elif span > 60:
                                step = 30
                            elif span > 30:
                                step = 15
                            else:
                                step = 10
                            tick_start = math.floor(y_min / step) * step - step
                            tick_end = math.ceil(y_max / step) * step + step
                            tick_vals = list(range(
                                int(tick_start), int(tick_end) + int(step), int(step)
                            ))
                            y_scale = alt.Scale(
                                domain=[tick_start, tick_end],
                            )

                            time_label_expr = (
                                "floor(datum.value / 60) + ':' "
                                "+ (datum.value % 60 < 10 ? '0' : '') "
                                "+ format(datum.value % 60, '.0f')"
                            )

                            line = alt.Chart(chart_df).mark_line(
                                strokeWidth=2.5, color="#1B2A4A",
                            ).encode(
                                x=alt.X(
                                    "Date:N", title=None,
                                    sort=alt.SortField("Order"),
                                    axis=alt.Axis(
                                        labelAngle=-45, labelFontSize=9,
                                        grid=True, gridColor="black", gridOpacity=0.4,
                                    ),
                                ),
                                y=alt.Y(
                                    "Seconds:Q", scale=y_scale, title="Finish time",
                                    axis=alt.Axis(
                                        values=tick_vals,
                                        labelExpr=time_label_expr,
                                        grid=True, gridDash=[2, 2], gridOpacity=0.3,
                                    ),
                                ),
                            )

                            points = alt.Chart(chart_df).mark_circle(
                                size=50, color="#1B2A4A",
                            ).encode(
                                x=alt.X("Date:N", sort=alt.SortField("Order")),
                                y=alt.Y("Seconds:Q", scale=y_scale),
                                tooltip=[
                                    alt.Tooltip("Date:N", title="Date"),
                                    alt.Tooltip("Meet:N"),
                                    alt.Tooltip("Label:N", title="Time"),
                                ],
                            )

                            chart = (line + points).properties(height=250)
                            st.altair_chart(chart, use_container_width=True)

                            first = chart_df["Seconds"].iloc[0]
                            last = chart_df["Seconds"].iloc[-1]
                            diff = last - first
                            if diff < 0:
                                st.caption(f"↓ Improved by {fmt_xc_time(abs(diff))}")
                            elif diff > 0:
                                st.caption(f"↑ Slower by {fmt_xc_time(abs(diff))}")

                if st.button("Close profile", key=f"close_xc_profile_{aid}"):
                    st.session_state.profile_athlete = None
                    st.rerun()

        # ---- Inline edit panel ----
        if is_editing:
            with st.container(border=True):
                st.caption(f"Editing: {athlete['first_name']} {athlete['last_name']}")

                with st.form(f"edit_form_{aid}"):
                    ec1, ec2 = st.columns(2)
                    new_first = ec1.text_input("First name", value=athlete["first_name"])
                    new_last = ec2.text_input("Last name", value=athlete["last_name"])
                    ec3, ec4, ec5 = st.columns(3)
                    new_grade = ec3.selectbox("Grade", [6, 7, 8],
                                             index=[6, 7, 8].index(athlete["grade"]))
                    new_gender = ec4.selectbox("Gender", ["M", "F"],
                                              index=["M", "F"].index(athlete["gender"]))
                    _statuses = ["active", "injured", "inactive", "alumni"]
                    new_status = ec5.selectbox(
                        "Status", _statuses,
                        index=_statuses.index(athlete["status"])
                    )
                    s_col, c_col, r_col = st.columns(3)
                    save = s_col.form_submit_button("Save changes", type="primary")
                    cancel = c_col.form_submit_button("Cancel")
                    remove = r_col.form_submit_button("Remove from roster")

                if save:
                    db.update_athlete(aid, new_first, new_last,
                                      new_grade, new_gender, new_status)
                    st.session_state.editing_athlete = None
                    st.success(f"Saved {new_first} {new_last}.")
                    shared.data_changed()
                if cancel:
                    st.session_state.editing_athlete = None
                    st.rerun()
                if remove:
                    db.remove_from_roster(season_id, aid)
                    st.session_state.editing_athlete = None
                    st.success("Removed from roster.")
                    shared.data_changed()

                # Event assignment (Track only)
                if sport == "Track":
                    st.markdown("**Event assignments**")
                    all_events = db.get_track_events(gender=athlete["gender"])
                    current_events = db.get_athlete_events(aid, season_id)
                    current_ids = {e["id"] for e in current_events}

                    selected_ids = []
                    running = [e for e in all_events if e["event_type"] == "running"]
                    field = [e for e in all_events if e["event_type"] == "field"]
                    relay = [e for e in all_events if e["event_type"] == "relay"]

                    for section_label, section_events in [
                        ("Running", running), ("Field", field), ("Relays", relay)
                    ]:
                        if section_events:
                            st.caption(section_label)
                            ev_cols = st.columns(min(len(section_events), 4))
                            for i, ev in enumerate(section_events):
                                checked = ev_cols[i % 4].checkbox(
                                    ev["name"],
                                    value=ev["id"] in current_ids,
                                    key=f"ev_{aid}_{ev['id']}"
                                )
                                if checked:
                                    selected_ids.append(ev["id"])

                    if len(selected_ids) > 4:
                        st.warning(
                            f"4 events max per meet — you've selected {len(selected_ids)}. "
                            "Fine for season planning, just watch per-meet entries."
                        )

                    if st.button("Save event assignments", type="primary",
                                 key=f"save_ev_{aid}"):
                        db.set_athlete_events(aid, season_id, selected_ids)
                        st.success("Event assignments saved.")
                        shared.data_changed()

if shared.is_coach():
    st.divider()

    with st.expander("+ Add a single athlete"):
        with st.form("add_athlete_form", clear_on_submit=True):
            ac1, ac2 = st.columns(2)
            first = ac1.text_input("First name", placeholder="e.g. Jane")
            last = ac2.text_input("Last name", placeholder="e.g. Smith")
            ac3, ac4 = st.columns(2)
            grade = ac3.selectbox("Grade", [6, 7, 8])
            gender = ac4.selectbox("Gender", ["M", "F"],
                                   format_func=lambda x: "Boys (M)" if x == "M" else "Girls (F)")
            submitted = st.form_submit_button("Add to roster", type="primary")

        if submitted:
            if not first.strip() or not last.strip():
                st.error("First and last name are required.")
            else:
                aid = db.add_athlete(first, last, grade, gender,
                                     st.session_state.school_id)
                db.add_to_roster(season_id, aid)
                st.success(f"Added {first} {last}.")
                shared.data_changed()

    with st.expander("⬆ Import from CSV file"):
        st.caption(
            "Your CSV needs columns: `first_name`, `last_name`, `grade`, `gender`. "
            "Other column names are fine too — see the template."
        )
        template = db.generate_csv_template()
        st.download_button(
            "Download CSV template",
            data=template,
            file_name="roster_template.csv",
            mime="text/csv",
        )
        uploaded = st.file_uploader("Upload roster CSV", type=["csv"])
        if uploaded:
            file_bytes = uploaded.read()
            rows, errors = db.parse_roster_csv(file_bytes)
            if errors:
                for e in errors:
                    st.error(e)
            if rows:
                st.success(f"Preview: {len(rows)} athletes ready to import.")
                preview_data = [
                    {
                        "First": r["first_name"],
                        "Last": r["last_name"],
                        "Grade": r["grade"],
                        "Gender": "Boys" if r["gender"] == "M" else "Girls",
                    }
                    for r in rows
                ]
                st.dataframe(preview_data, use_container_width=True, hide_index=True)
                st.session_state.csv_preview_rows = rows
        if st.session_state.csv_preview_rows:
            if st.button("Confirm import", type="primary"):
                result = db.import_roster_from_rows(
                    st.session_state.csv_preview_rows,
                    st.session_state.school_id,
                    season_id,
                )
                st.session_state.csv_preview_rows = None
                st.success(
                    f"Imported: {result['added']} added, "
                    f"{result['skipped']} already existed."
                )
                shared.data_changed()

    with st.expander("⬆ Import from tryout spreadsheet (.xlsx)"):
        st.caption(
            "Upload your tryout spreadsheet. Tabs should be named by grade/gender "
            "(e.g. **6th Girls**, **7th Boys**). "
            "Cut athletes (y in Cut? column) are skipped entirely. "
            "Non-empty time columns auto-assign events and import as Tryouts meet results."
        )
        tryout_file = st.file_uploader("Upload tryout spreadsheet", type=["xlsx"],
                                       key="tryout_upload")
        if tryout_file:
            preview, errors = db.parse_tryout_spreadsheet(tryout_file.read())
            if errors:
                for e in errors:
                    st.warning(e)
            if preview:
                added_count = len([r for r in preview if not r.get("cut")])
                cut_count = len([r for r in preview if r.get("cut")])
                result_count = sum(len(r.get("results", [])) for r in preview)
                st.success(
                    f"Found **{added_count}** athletes to import · "
                    f"{cut_count} cuts skipped · "
                    f"{result_count} tryout results"
                )
                preview_rows = [
                    {
                        "First": r["first_name"],
                        "Last": r["last_name"],
                        "Gr.": r["grade"],
                        "Gender": "Boys" if r["gender"] == "M" else "Girls",
                        "Events": ", ".join(r.get("events", [])) or "—",
                    }
                    for r in preview if not r.get("cut")
                ]
                st.dataframe(preview_rows, use_container_width=True, hide_index=True)
                st.session_state["tryout_preview"] = preview
        if st.session_state.get("tryout_preview"):
            if st.button("Import tryout data", type="primary"):
                result = db.import_tryout_data(
                    st.session_state["tryout_preview"],
                    st.session_state.school_id,
                    season_id,
                )
                st.session_state["tryout_preview"] = None
                st.success(
                    f"Imported {result['athletes']} athletes · "
                    f"{result['results']} tryout results · "
                    f"{result['assignments']} event assignments."
                )
                shared.data_changed()
