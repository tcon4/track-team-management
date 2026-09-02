"""Lineup Builder page."""

import streamlit as st
from datetime import date
import db
import shared

season_id = shared.setup()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title("Lineup Builder")
st.caption(f"{year} {sport} — {school_name}")

if sport != "Track":
    st.info("Lineup builder is for Track meets. Switch sport in the sidebar.")
    st.stop()

meets = db.get_meets(season_id)

if not meets:
    st.info("No meets on the schedule yet.")
    st.page_link("pages/2_Schedule.py", label="Add a meet on the Schedule page →")
    st.stop()

# ---------------------------------------------------------------------------
# Meet selector — must confirm before anything else shows
# ---------------------------------------------------------------------------

confirm_key = "lineup_confirmed_meet"

with st.container(border=True):
    meet_options = {f"{m['meet_date']} · {m['name']}": m["id"] for m in meets}
    selected_meet_label = st.selectbox("Select a meet", list(meet_options.keys()))
    selected_meet_id = meet_options[selected_meet_label]
    selected_meet = db.get_meet(selected_meet_id)
    st.caption(f"Location: {selected_meet['location']}  ·  "
               f"Host: {selected_meet['host_name']}")

    # Check if this meet is in the past
    today = date.today().isoformat()
    is_past = selected_meet["meet_date"] < today

    if is_past:
        st.info(f"This meet has passed ({selected_meet['meet_date']}).")

    # Confirm / change meet button
    confirmed_id = st.session_state.get(confirm_key)
    if confirmed_id == selected_meet_id:
        if st.button("Change meet", key="change_meet"):
            st.session_state[confirm_key] = None
            st.rerun()
    else:
        if st.button("Load lineup", type="primary", key="confirm_meet"):
            st.session_state[confirm_key] = selected_meet_id
            st.rerun()

# Stop here if meet not confirmed
if st.session_state.get(confirm_key) != selected_meet_id:
    st.stop()

# ---------------------------------------------------------------------------
# Read-only mode for past meets (with unlock override)
# ---------------------------------------------------------------------------

unlock_key = f"unlock_past_{selected_meet_id}"
read_only = is_past and not st.session_state.get(unlock_key, False)

if is_past:
    if read_only:
        if st.button("Unlock for editing (what-if mode)"):
            st.session_state[unlock_key] = True
            st.rerun()
    else:
        st.warning("What-if mode — this meet has passed. Changes can still be saved.")
        if st.button("Lock editing"):
            st.session_state[unlock_key] = False
            st.rerun()

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

MAX_PER_INDIVIDUAL = 3
MAX_PER_RELAY = 5
MAX_PER_ATHLETE = 4


def max_for_event(event: dict) -> int:
    """Return the max entries allowed for an event."""
    return MAX_PER_RELAY if event.get("event_type") == "relay" else MAX_PER_INDIVIDUAL


# Load current lineup as set of (athlete_id, event_id) tuples
saved_lineup = db.get_lineup(selected_meet_id)
saved_set = {(e["athlete_id"], e["event_id"]) for e in saved_lineup}

# Session state for working lineup (before save)
lineup_key = f"lineup_{selected_meet_id}"
if lineup_key not in st.session_state:
    st.session_state[lineup_key] = saved_set

working_set: set = set(st.session_state[lineup_key])


def _sync_checkbox_keys(new_set: set):
    """Set all lu_ checkbox keys to match the new working set."""
    prefix = f"lu_{selected_meet_id}_"
    for k in list(st.session_state.keys()):
        if k.startswith(prefix):
            st.session_state[k] = False
    for aid, eid in new_set:
        st.session_state[f"{prefix}{aid}_{eid}"] = True


def _on_checkbox_change(aid: int, eid: int):
    """Callback: sync checkbox state into the working lineup set."""
    cb_key = f"lu_{selected_meet_id}_{aid}_{eid}"
    current = set(st.session_state.get(lineup_key, set()))
    entry = (aid, eid)
    if st.session_state.get(cb_key):
        current.add(entry)
        db.assign_event(aid, season_id, eid)
    else:
        current.discard(entry)
    st.session_state[lineup_key] = current


# ---------------------------------------------------------------------------
# Action buttons
# ---------------------------------------------------------------------------

if not read_only:
    col_suggest, col_save, col_clear, col_export, col_checklist = st.columns(
        [2, 2, 2, 2, 2]
    )

    if col_suggest.button("Auto-suggest lineup", type="secondary"):
        suggestion = db.auto_suggest_lineup(
            selected_meet_id, season_id,
            max_per_individual=MAX_PER_INDIVIDUAL,
            max_per_relay=MAX_PER_RELAY,
            max_per_athlete=MAX_PER_ATHLETE,
        )
        new_set = {
            (e["athlete_id"], e["event_id"]) for e in suggestion["entries"]
        }
        st.session_state[lineup_key] = new_set
        _sync_checkbox_keys(new_set)

        if suggestion["conflicts"]:
            for c in suggestion["conflicts"]:
                gender_label = "Boys" if c["gender"] == "M" else "Girls"
                st.warning(
                    f"⚠ {c['event_name']} ({gender_label}): only "
                    f"{c['available']} of {c['needed']} slots filled — "
                    f"not enough athletes assigned or available."
                )
        else:
            st.success("Lineup suggested — review and save when ready.")
        st.rerun()

    if col_save.button("Save lineup", type="primary"):
        entries = [
            {"athlete_id": aid, "event_id": eid}
            for aid, eid in st.session_state[lineup_key]
        ]
        db.save_lineup(selected_meet_id, entries)
        st.success("Lineup saved.")
        shared.data_changed()

    if col_clear.button("Clear lineup"):
        st.session_state[lineup_key] = set()
        _sync_checkbox_keys(set())
        st.rerun()

    if col_export.button("Export PDF"):
        st.session_state["export_lineup_meet"] = selected_meet_id

    if col_checklist.button("Meet Checklist"):
        st.session_state["export_checklist_meet"] = selected_meet_id
else:
    # Read-only: show both export options
    rc1, rc2 = st.columns(2)
    if rc1.button("Export PDF"):
        st.session_state["export_lineup_meet"] = selected_meet_id
    if rc2.button("Meet Checklist"):
        st.session_state["export_checklist_meet"] = selected_meet_id

# PDF export download — lineup grid
if st.session_state.get("export_lineup_meet") == selected_meet_id:
    current_set = set(st.session_state.get(lineup_key, set()))
    if not read_only and current_set != saved_set:
        st.warning(
            "Your lineup has unsaved changes — save before exporting "
            "to get the latest version."
        )
    with st.spinner("Generating PDF..."):
        try:
            lineup_entries = [
                {"athlete_id": aid, "event_id": eid}
                for aid, eid in current_set
            ]
            pdf_bytes = db.generate_lineup_pdf(
                selected_meet_id, season_id,
                lineup_entries=lineup_entries
            )
            meet_slug = selected_meet["name"].replace(" ", "_").lower()
            st.download_button(
                label="Download lineup PDF",
                data=pdf_bytes,
                file_name=f"lineup_{meet_slug}.pdf",
                mime="application/pdf",
                type="primary",
            )
            st.session_state["export_lineup_meet"] = None
        except Exception as ex:
            st.error(f"PDF generation failed: {ex}")
            st.session_state["export_lineup_meet"] = None

# PDF export download — meet day checklist
if st.session_state.get("export_checklist_meet") == selected_meet_id:
    current_set = set(st.session_state.get(lineup_key, set()))
    if not read_only and current_set != saved_set:
        st.warning(
            "Your lineup has unsaved changes — save before exporting "
            "to get the latest version."
        )
    with st.spinner("Generating checklist..."):
        try:
            lineup_entries = [
                {"athlete_id": aid, "event_id": eid}
                for aid, eid in current_set
            ]
            checklist_bytes = db.generate_checklist_pdf(
                selected_meet_id, season_id,
                lineup_entries=lineup_entries
            )
            meet_slug = selected_meet["name"].replace(" ", "_").lower()
            st.download_button(
                label="Download meet checklist",
                data=checklist_bytes,
                file_name=f"checklist_{meet_slug}.pdf",
                mime="application/pdf",
                type="primary",
            )
            st.session_state["export_checklist_meet"] = None
        except Exception as ex:
            st.error(f"Checklist generation failed: {ex}")
            st.session_state["export_checklist_meet"] = None

st.divider()

# ---------------------------------------------------------------------------
# Shared data
# ---------------------------------------------------------------------------

athlete_counts: dict[int, int] = {}
for aid, eid in working_set:
    athlete_counts[aid] = athlete_counts.get(aid, 0) + 1

season_bests_map = db.get_season_best_per_event(season_id)
roster_all = db.get_roster(season_id)
roster_by_id = {a["id"]: a for a in roster_all}
all_event_assignments = db.get_all_athlete_events(season_id)
all_events = db.get_track_events()
events_by_id = {e["id"]: e for e in all_events}

RELAY_TO_INDIVIDUAL = {"4x100 Relay": "100m", "4x200 Relay": "200m", "4x400 Relay": "400m"}
relay_sb_event_map: dict[int, int] = {}
for e in all_events:
    if e["event_type"] == "relay" and e["name"] in RELAY_TO_INDIVIDUAL:
        indiv_name = RELAY_TO_INDIVIDUAL[e["name"]]
        for ie in all_events:
            if ie["name"] == indiv_name and ie["gender"] == e["gender"]:
                relay_sb_event_map[e["id"]] = ie["id"]
                break

event_athletes: dict[int, list[str]] = {}
for aid, eid in working_set:
    a = roster_by_id.get(aid)
    if a:
        event_athletes.setdefault(eid, []).append(a["first_name"])

unique_athletes = set(aid for aid, eid in working_set)

# ---------------------------------------------------------------------------
# Top summary (collapsible)
# ---------------------------------------------------------------------------

mc1, mc2 = st.columns([1, 3])
mc1.metric("Total Athletes", len(unique_athletes))

with st.expander("Athlete event totals", expanded=False):
    for gender_val, gender_label in [("M", "Boys"), ("F", "Girls")]:
        gender_roster = [
            a for a in roster_all
            if a["gender"] == gender_val and a["status"] == "active"
        ]
        in_lineup = [
            a for a in gender_roster
            if athlete_counts.get(a["id"], 0) > 0
        ]
        not_in_lineup = [
            a for a in gender_roster
            if athlete_counts.get(a["id"], 0) == 0
        ]

        if not in_lineup and not not_in_lineup:
            continue

        st.markdown(f"**{gender_label}**")

        if in_lineup:
            cols = st.columns(min(len(in_lineup), 4))
            for i, athlete in enumerate(sorted(
                in_lineup,
                key=lambda a: -athlete_counts.get(a["id"], 0)
            )):
                aid = athlete["id"]
                cnt = athlete_counts.get(aid, 0)
                bar = "█" * cnt + "░" * (MAX_PER_ATHLETE - cnt)
                warning = " ⚠" if cnt >= MAX_PER_ATHLETE else ""
                cols[i % 4].caption(
                    f"{athlete['first_name']} {athlete['last_name']}\n"
                    f"{bar} {cnt}/{MAX_PER_ATHLETE}{warning}"
                )

        if not_in_lineup:
            names = ", ".join(
                f"{a['first_name']} {a['last_name']}"
                for a in sorted(not_in_lineup, key=lambda a: (a["last_name"], a["first_name"]))
            )
            st.caption(f"Not in lineup ({len(not_in_lineup)}): {names}")

# ---------------------------------------------------------------------------
# Lineup progress (collapsible)
# ---------------------------------------------------------------------------

with st.expander("Lineup progress", expanded=False):
    for gender_val, gender_label in [("M", "Boys"), ("F", "Girls")]:
        gender_events_prog = [
            e for e in all_events
            if e["gender"] == gender_val
        ]
        event_counts = {}
        for aid, eid in working_set:
            a = roster_by_id.get(aid)
            if a and a["gender"] == gender_val:
                event_counts[eid] = event_counts.get(eid, 0) + 1

        total_slots = sum(max_for_event(e) for e in gender_events_prog)
        filled_slots = sum(event_counts.values())

        st.markdown(
            f"**{gender_label}** — {filled_slots}/{total_slots} slots"
        )

        row_size = 5
        for i in range(0, len(gender_events_prog), row_size):
            bcols = st.columns(row_size)
            for j, e in enumerate(gender_events_prog[i:i + row_size]):
                n = event_counts.get(e["id"], 0)
                mx = max_for_event(e)
                icon = "🟢" if n == mx else (
                    "🟡" if n > 0 else "🔴"
                )
                names = event_athletes.get(e["id"], [])
                names_str = ", ".join(sorted(names)) if names else "—"
                bcols[j].caption(f"{icon} **{e['name']}** {n}/{mx}")
                bcols[j].caption(f"  {names_str}")

st.divider()

# ---------------------------------------------------------------------------
# Event-by-event grid (collapsible)
# ---------------------------------------------------------------------------

gender_tab_b, gender_tab_g = st.tabs(["Boys", "Girls"])

TOP_N = 15

for gender_val, gtab in [("M", gender_tab_b), ("F", gender_tab_g)]:
    with gtab:
        events = db.get_track_events(gender=gender_val)
        gender_roster = [
            a for a in roster_all
            if a["gender"] == gender_val and a["status"] == "active"
        ]

        for event in events:
            eid = event["id"]
            mx = max_for_event(event)
            is_relay = event["event_type"] == "relay"

            if is_relay:
                sb_event_id = relay_sb_event_map.get(eid, eid)
                indiv_name = RELAY_TO_INDIVIDUAL.get(event["name"], "")
            else:
                sb_event_id = eid
                indiv_name = ""

            def _sort_key(a):
                checked = (a["id"], eid) in working_set
                sb = season_bests_map.get((a["id"], sb_event_id))
                has_sb = sb is not None
                return (
                    0 if checked else 1,
                    0 if has_sb else 1,
                    sb if has_sb else "z",
                )

            sorted_roster = sorted(gender_roster, key=_sort_key)

            event_selected = [
                aid for aid, e in working_set if e == eid
            ]
            count_label = f"{len(event_selected)}/{mx}"
            over_limit = len(event_selected) > mx

            header_color = "🔴" if over_limit else (
                "🟢" if len(event_selected) == mx else "⚪"
            )

            with st.expander(
                f"{header_color}  **{event['name']}** — {count_label} entered",
                expanded=len(event_selected) < mx and not read_only
            ):
                if is_relay:
                    st.caption(f"Sorted by {indiv_name} season best")

                top_athletes = sorted_roster[:TOP_N]
                remaining_athletes = sorted_roster[TOP_N:]

                checked_beyond = [
                    a for a in remaining_athletes
                    if (a["id"], eid) in working_set
                ]
                if checked_beyond:
                    top_athletes = top_athletes + checked_beyond
                    remaining_athletes = [
                        a for a in remaining_athletes
                        if (a["id"], eid) not in working_set
                    ]

                def _render_athlete(athlete):
                    aid = athlete["id"]
                    is_checked = (aid, eid) in working_set
                    sb = season_bests_map.get((aid, sb_event_id), "—")
                    total_events = athlete_counts.get(aid, 0)
                    at_limit = total_events >= MAX_PER_ATHLETE and not is_checked

                    sb_label = f"{indiv_name}: {sb}" if is_relay else f"SB: {sb}"
                    label = (
                        f"{athlete['last_name']}, {athlete['first_name']} "
                        f"· Gr. {athlete['grade']} · {sb_label}"
                    )
                    if total_events >= MAX_PER_ATHLETE:
                        label += f" ⚠ {total_events}/{MAX_PER_ATHLETE} events"

                    st.checkbox(
                        label,
                        value=is_checked,
                        disabled=read_only or at_limit,
                        key=f"lu_{selected_meet_id}_{aid}_{eid}",
                        on_change=_on_checkbox_change,
                        args=(aid, eid),
                    )

                for athlete in top_athletes:
                    _render_athlete(athlete)

                if remaining_athletes and not read_only:
                    exp_key = f"expanded_show_all_{selected_meet_id}_{eid}"
                    is_expanded = st.session_state.get(exp_key, False)

                    if is_expanded:
                        if st.button(
                            f"Hide full roster",
                            key=f"hide_{selected_meet_id}_{eid}",
                        ):
                            st.session_state[exp_key] = False
                            st.rerun()
                        st.caption("—")
                        for athlete in remaining_athletes:
                            _render_athlete(athlete)
                    else:
                        if st.button(
                            f"Show full roster ({len(remaining_athletes)} more)",
                            key=f"show_{selected_meet_id}_{eid}",
                        ):
                            st.session_state[exp_key] = True
                            st.rerun()
