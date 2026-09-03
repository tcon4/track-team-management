"""Team Results — meet-by-meet summaries and season bests."""

import streamlit as st
from datetime import date
import db
import shared

season_id = shared.setup()

year = st.session_state.current_year
sport = st.session_state.sport
school = db.get_school(st.session_state.school_id)
school_name = school["name"] if school else "—"

st.title("Team Results")
st.caption(f"{year} {sport} — {school_name}")

meets = db.get_meets(season_id)
today = date.today().isoformat()
past_meets = [m for m in meets if m["meet_date"] < today]


# ═══════════════════════════════════════════════════════════════════════════
# Meet-by-Meet Results
# ═══════════════════════════════════════════════════════════════════════════

if not past_meets:
    st.info("No completed meets yet.")
else:
    st.markdown("## Meet Results")

    if sport == "XC":
        from db.xc import _parse_xc_time, fmt_xc_time

        for meet in reversed(past_meets):
            results = db.get_xc_meet_results(meet["id"])
            if not results:
                continue

            gp = meet.get("girls_place") or ""
            bp = meet.get("boys_place") or ""
            place_parts = []
            if gp:
                place_parts.append(f"Girls: {gp}")
            if bp:
                place_parts.append(f"Boys: {bp}")
            place_str = "  ·  ".join(place_parts) if place_parts else ""

            team_stats = db.get_xc_team_stats(meet["id"])

            with st.container(border=True):
                st.markdown(f"### {meet['name']}")
                st.caption(
                    f"{meet['meet_date']}  ·  {meet['location']}"
                    + (f"  ·  {place_str}" if place_str else "")
                )

                prs_at_meet = [r for r in results if r.get("is_pr")]

                tab_b, tab_g = st.tabs(["Boys", "Girls"])
                for tab, gender_code, gender_label in [
                    (tab_b, "M", "Boys"), (tab_g, "F", "Girls"),
                ]:
                    with tab:
                        gender_results = [
                            r for r in results if r["gender"] == gender_code
                        ]
                        if not gender_results:
                            st.caption(f"No {gender_label.lower()} results.")
                            continue

                        gs = team_stats.get(gender_code)
                        if gs:
                            sc1, sc2, sc3, sc4 = st.columns(4)
                            sc1.metric("Average", fmt_xc_time(gs["average"]))
                            sc2.metric("Median", fmt_xc_time(gs["median"]))
                            sc3.metric("Top 5 Avg", fmt_xc_time(gs["top5_avg"]))
                            if gs["split_1_5"] is not None:
                                sc4.metric("1-5 Split", fmt_xc_time(gs["split_1_5"]))
                            else:
                                sc4.metric("1-5 Split", "—")
                            st.write("")

                        try:
                            gender_results.sort(
                                key=lambda r: _parse_xc_time(r["finish_time"])
                            )
                        except (ValueError, ZeroDivisionError):
                            pass

                        top7 = gender_results[:7]
                        for i, r in enumerate(top7):
                            pr_flag = " ✓PR" if r.get("is_pr") else ""
                            place_lbl = (
                                f"{shared.format_place(r['place'])} · "
                                if r.get("place") else ""
                            )
                            medal = ["\U0001f947", "\U0001f948", "\U0001f949"][i] if i < 3 else f"{i+1}."
                            st.write(
                                f"{medal} {r['last_name']}, {r['first_name']} "
                                f"· {r['finish_time']} · "
                                f"{place_lbl}{r.get('distance', '2mi')}{pr_flag}"
                            )

                        rest_prs = [
                            r for r in gender_results[7:]
                            if r.get("is_pr")
                        ]
                        if rest_prs:
                            st.caption("**Other PRs:**")
                            for r in rest_prs:
                                st.caption(
                                    f"✓PR {r['last_name']}, {r['first_name']} "
                                    f"· {r['finish_time']}"
                                )

                if prs_at_meet:
                    st.caption(f"\U0001f3c5 {len(prs_at_meet)} PR{'s' if len(prs_at_meet) != 1 else ''} at this meet")

    else:
        for meet in reversed(past_meets):
            results = db.get_meet_results(meet["id"])
            if not results:
                continue

            gp = meet.get("girls_place") or ""
            bp = meet.get("boys_place") or ""
            place_parts = []
            if gp:
                place_parts.append(f"Girls: {gp}")
            if bp:
                place_parts.append(f"Boys: {bp}")
            place_str = "  ·  ".join(place_parts) if place_parts else ""

            prs_at_meet = [r for r in results if r.get("is_pr")]
            top3_at_meet = [r for r in results if r.get("place") and r["place"] <= 3]

            with st.container(border=True):
                st.markdown(f"### {meet['name']}")
                st.caption(
                    f"{meet['meet_date']}  ·  {meet['location']}"
                    + (f"  ·  {place_str}" if place_str else "")
                )

                tab_b, tab_g = st.tabs(["Boys", "Girls"])
                for tab, gender_code, gender_label in [
                    (tab_b, "M", "Boys"), (tab_g, "F", "Girls"),
                ]:
                    with tab:
                        gender_results = [
                            r for r in results if r["gender"] == gender_code
                        ]
                        if not gender_results:
                            st.caption(f"No {gender_label.lower()} results.")
                            continue

                        g_top3 = [
                            r for r in gender_results
                            if r.get("place") and r["place"] <= 3
                        ]
                        g_prs = [r for r in gender_results if r.get("is_pr")]

                        if g_top3:
                            st.markdown("**Top finishes**")
                            for r in sorted(g_top3, key=lambda x: (x["event_name"], x["place"])):
                                pr_flag = " ✓PR" if r.get("is_pr") else ""
                                st.write(
                                    f"{shared.format_place(r['place'])} · "
                                    f"{r['last_name']}, {r['first_name']} "
                                    f"· {r['event_name']}: {r['result_value']}{pr_flag}"
                                )

                        other_prs = [r for r in g_prs if not (r.get("place") and r["place"] <= 3)]
                        if other_prs:
                            st.markdown("**PRs**")
                            for r in sorted(other_prs, key=lambda x: x["event_name"]):
                                st.write(
                                    f"✓PR {r['last_name']}, {r['first_name']} "
                                    f"· {r['event_name']}: {r['result_value']}"
                                )

                        if not g_top3 and not g_prs:
                            st.caption("No top-3 finishes or PRs.")

                summary_parts = []
                if top3_at_meet:
                    summary_parts.append(f"\U0001f3c5 {len(top3_at_meet)} top-3 finish{'es' if len(top3_at_meet) != 1 else ''}")
                if prs_at_meet:
                    summary_parts.append(f"✓ {len(prs_at_meet)} PR{'s' if len(prs_at_meet) != 1 else ''}")
                if summary_parts:
                    st.caption("  ·  ".join(summary_parts))


# ═══════════════════════════════════════════════════════════════════════════
# Season Bests
# ═══════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown("## Season Bests")

if sport == "XC":
    bests = db.get_xc_season_bests(season_id)

    if not bests:
        st.info("No XC results recorded yet.")
    else:
        pr_count = sum(1 for b in bests if b.get("is_pr"))
        athlete_count = len(bests)
        mc1, mc2 = st.columns(2)
        mc1.metric("Athletes with Results", athlete_count)
        mc2.metric("Season PRs", pr_count)

        st.write("")

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

else:
    bests = db.get_season_bests_track(season_id)

    if not bests:
        st.info("No results recorded yet.")
    else:
        pr_count = sum(1 for b in bests if b.get("is_pr"))
        athlete_count = len(set((b["first_name"], b["last_name"]) for b in bests))
        mc1, mc2 = st.columns(2)
        mc1.metric("Athletes with Results", athlete_count)
        mc2.metric("Season PRs", pr_count)

        st.write("")

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
