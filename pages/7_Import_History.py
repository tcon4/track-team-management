"""Import Historic XC Results — upload an xlsx spreadsheet to import past seasons."""

import shared

season_id = shared.setup()

import os
import tempfile

import streamlit as st

import db

sport = st.session_state.sport
if sport != "XC":
    st.info("Historic import is only available for XC.")
    st.stop()

st.title("Import XC History")
st.caption("Import past-season results from an xlsx spreadsheet (BOYS / GIRLS tabs)")

uploaded = st.file_uploader("Upload xlsx file", type=["xlsx"])
year = st.number_input("Season year", value=2024, min_value=2020, max_value=2026)

if not uploaded:
    st.stop()

with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
    f.write(uploaded.getbuffer())
    tmp_path = f.name

try:
    parsed = db.parse_xc_xlsx(tmp_path, year)
finally:
    os.unlink(tmp_path)

if not parsed["meets"]:
    st.warning("No meets found in the spreadsheet. Check that it has BOYS / GIRLS tabs with dates in row 1 and venue names in row 2.")
    st.stop()

# --- Preview ---
st.divider()
st.subheader("Preview")

st.markdown(f"**{len(parsed['meets'])} meets found:**")
for m in sorted(parsed["meets"], key=lambda x: x["date"]):
    dist_label = f" ({m['distance']})" if m["distance"] != "2mi" else ""
    st.caption(f"📅 {m['date']}  —  {m['venue']}{dist_label}")

boys = [a for a in parsed["athletes"] if a["gender"] == "M"]
girls = [a for a in parsed["athletes"] if a["gender"] == "F"]
total_results = sum(len(a["results"]) for a in parsed["athletes"])

st.markdown(
    f"**{len(parsed['athletes'])} athletes**  ·  "
    f"**{total_results} results**"
)

col1, col2 = st.columns(2)
with col1:
    with st.expander(f"Boys ({len(boys)})"):
        for a in sorted(boys, key=lambda x: x["last"]):
            st.caption(f"{a['last']}, {a['first']} — {len(a['results'])} results")

with col2:
    with st.expander(f"Girls ({len(girls)})"):
        for a in sorted(girls, key=lambda x: x["last"]):
            st.caption(f"{a['last']}, {a['first']} — {len(a['results'])} results")

# --- Import ---
st.divider()
st.markdown(
    f"This will create a **{year} XC** season with the meets and results above. "
    "Athletes already on the roster will be matched by name; new athletes will be created."
)

if st.button(f"Import {year} XC season", type="primary"):
    with st.spinner("Importing..."):
        result = db.import_xc_season(
            parsed, st.session_state.school_id, year
        )
    st.success(
        f"Import complete!  \n"
        f"**{result['meets_created']}** meets created  ·  "
        f"**{result['athletes_created']}** new athletes  ·  "
        f"**{result['athletes_matched']}** matched existing  ·  "
        f"**{result['results_imported']}** results imported"
    )
