"""School Records page — Historic records and recent top performances."""

import streamlit as st
import db
import shared

season_id = shared.setup()

school_id = st.session_state.school_id
school = db.get_school(school_id)
school_name = school["name"] if school else "—"

st.title("School Records")
st.caption(f"{school_name}")


def _parse_record(value: str) -> float | None:
    """Parse a record value to a numeric for comparison.
    Handles: '11.24', '1:05.28', '46 ft. 7 in.', '21 ft. 3 in.'
    """
    v = value.strip()
    if "ft." in v:
        import re
        m = re.match(r"(\d+)\s*ft\.\s*([\d.]+)\s*in\.", v)
        if m:
            return int(m.group(1)) * 12 + float(m.group(2))
        m = re.match(r"(\d+)\s*ft\.", v)
        if m:
            return int(m.group(1)) * 12
        return None
    if ":" in v:
        parts = v.split(":")
        try:
            return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_track_result(value: str) -> float | None:
    """Parse track result_value for comparison."""
    v = value.strip().rstrip("m").strip()
    if ":" in v:
        parts = v.split(":")
        try:
            return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            return None
    if "-" in v and not v.startswith("-"):
        try:
            feet, inches = v.split("-", 1)
            return int(feet) * 12 + float(inches)
        except ValueError:
            return None
    try:
        return float(v)
    except ValueError:
        return None


def _format_gap(gap: float, is_field: bool) -> str:
    """Format the gap between a performance and the school record."""
    if gap >= 60:
        m = int(gap // 60)
        s = gap % 60
        return f"{m}:{s:04.1f}"
    if is_field:
        feet = int(gap // 12)
        inches = gap % 12
        if feet > 0:
            return f"{feet} ft. {inches:.1f} in."
        return f"{inches:.1f} in."
    return f"{gap:.2f}"


# ---------------------------------------------------------------------------
# Historic School Records
# ---------------------------------------------------------------------------

st.markdown("## Historic School Records")
st.caption("All-time Mooresville Middle School records")

records = db.get_school_records(school_id)

if not records:
    st.info("No school records have been entered yet.")
else:
    boys_records = [r for r in records if r["gender"] == "M"]
    girls_records = [r for r in records if r["gender"] == "F"]

    FIELD_EVENTS = {"Shot Put", "Discus", "Long Jump", "Triple Jump",
                    "High Jump", "Pole Vault"}

    def _display_records(recs: list[dict]) -> None:
        field = [r for r in recs if r["event_name"] in FIELD_EVENTS]
        running = [r for r in recs if r["event_name"] not in FIELD_EVENTS
                   and "Relay" not in r["event_name"]]
        relays = [r for r in recs if "Relay" in r["event_name"]]

        for section_name, section_recs in [
            ("Field Events", field),
            ("Running Events", running),
            ("Relays", relays),
        ]:
            if not section_recs:
                continue
            st.markdown(f"**{section_name}**")
            for r in section_recs:
                st.caption(
                    f"**{r['event_name']}** — {r['record_value']} · "
                    f"{r['holder_name']} ({r['year']})"
                )

    tab_boys, tab_girls = st.tabs(["Boys", "Girls"])

    with tab_boys:
        if boys_records:
            _display_records(boys_records)
        else:
            st.caption("No boys records.")

    with tab_girls:
        if girls_records:
            _display_records(girls_records)
        else:
            st.caption("No girls records.")

# ---------------------------------------------------------------------------
# Recent Top Performances
# ---------------------------------------------------------------------------

st.divider()
st.markdown("## Recent Top Performances")
st.caption("Best performances from your database — see how they stack up against school records")

sport = st.session_state.sport

record_lookup = {}
for r in records:
    key = (r["event_name"], r["gender"])
    record_lookup[key] = r

if sport == "Track":
    all_perfs = db.get_top_performances_track(school_id)

    if not all_perfs:
        st.info("No track results recorded yet.")
    else:
        from db.results import _parse_result

        grouped: dict[tuple[str, str], list[dict]] = {}
        for p in all_perfs:
            key = (p["event_name"], p["gender"])
            grouped.setdefault(key, [])
            grouped[key].append(p)

        tab_b, tab_g = st.tabs(["Boys", "Girls"])

        for tab, gender_code, gender_label in [
            (tab_b, "M", "Boys"), (tab_g, "F", "Girls"),
        ]:
            with tab:
                events = [
                    (k, v) for k, v in grouped.items() if k[1] == gender_code
                ]
                if not events:
                    st.caption(f"No {gender_label.lower()} results yet.")
                    continue

                for (ev_name, _), perfs in events:
                    is_field = perfs[0].get("event_type") == "field"
                    higher_better = is_field

                    try:
                        parsed = [
                            (p, _parse_result(p["result_value"]))
                            for p in perfs
                        ]
                        parsed = [(p, v) for p, v in parsed if v is not None]
                        parsed.sort(
                            key=lambda x: x[1],
                            reverse=higher_better,
                        )
                    except (ValueError, TypeError):
                        continue

                    top = parsed[:3]
                    if not top:
                        continue

                    rec = record_lookup.get((ev_name, gender_code))
                    rec_val = _parse_record(rec["record_value"]) if rec else None

                    with st.container(border=True):
                        st.markdown(f"**{ev_name}**")
                        if rec:
                            st.caption(
                                f"School record: {rec['record_value']} — "
                                f"{rec['holder_name']} ({rec['year']})"
                            )

                        for i, (p, val) in enumerate(top):
                            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
                            name = f"{p['first_name']} {p['last_name']}"
                            line = (
                                f"{medal} {p['result_value']} — "
                                f"{name} ({p['year']})"
                            )

                            if rec_val is not None:
                                gap = abs(rec_val - val)
                                if (higher_better and val >= rec_val) or \
                                   (not higher_better and val <= rec_val):
                                    line += " · **NEW SCHOOL RECORD**"
                                elif gap > 0:
                                    gap_str = _format_gap(gap, is_field)
                                    line += f" · {gap_str} off record"

                            st.markdown(line)

elif sport == "XC":
    from db.xc import _parse_xc_time, fmt_xc_time

    all_xc = db.get_top_performances_xc(school_id)

    if not all_xc:
        st.info("No XC results recorded yet.")
    else:
        grouped_xc: dict[tuple[str, str], list[dict]] = {}
        for p in all_xc:
            key = (p["distance"], p["gender"])
            grouped_xc.setdefault(key, [])
            grouped_xc[key].append(p)

        tab_b, tab_g = st.tabs(["Boys", "Girls"])

        for tab, gender_code, gender_label in [
            (tab_b, "M", "Boys"), (tab_g, "F", "Girls"),
        ]:
            with tab:
                events = [
                    (k, v) for k, v in grouped_xc.items()
                    if k[1] == gender_code
                ]
                if not events:
                    st.caption(f"No {gender_label.lower()} XC results yet.")
                    continue

                for (distance, _), perfs in events:
                    try:
                        parsed = [
                            (p, _parse_xc_time(p["finish_time"]))
                            for p in perfs
                        ]
                        parsed.sort(key=lambda x: x[1])
                    except (ValueError, TypeError):
                        continue

                    top = parsed[:5]
                    if not top:
                        continue

                    with st.container(border=True):
                        st.markdown(f"**{distance}**")

                        for i, (p, val) in enumerate(top):
                            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
                            name = f"{p['first_name']} {p['last_name']}"
                            st.markdown(
                                f"{medal} {p['finish_time']} — "
                                f"{name} ({p['year']})"
                            )


# ---------------------------------------------------------------------------
# Coach: edit records
# ---------------------------------------------------------------------------

if st.session_state.get("is_coach"):
    st.divider()
    with st.expander("Edit school records (coach only)"):
        with st.form("edit_record"):
            ec1, ec2 = st.columns(2)
            ev_name = ec1.text_input("Event name")
            gender = ec2.selectbox("Gender", ["M", "F"])
            ec3, ec4 = st.columns(2)
            rec_value = ec3.text_input("Record value")
            holder = ec4.text_input("Record holder")
            ec5, ec6 = st.columns(2)
            year = ec5.number_input("Year", min_value=1980, max_value=2030, value=2024)
            rec_sport = ec6.selectbox("Sport", ["Track", "XC"])

            if st.form_submit_button("Save record"):
                if ev_name and rec_value and holder:
                    db.upsert_school_record(
                        school_id, ev_name, gender,
                        rec_value, holder, int(year), rec_sport,
                    )
                    shared.data_changed()
                else:
                    st.warning("Please fill in all fields.")
