"""
db/ package — Re-exports all public functions so existing code
that does `import db; db.get_roster(...)` continues to work.
"""

# Connection & setup
from db.connection import init_db, get_connection, release_connection

# School
from db.school import get_schools, get_school, update_school

# Season
from db.season import get_or_create_season, get_seasons

# Athletes & roster
from db.athlete import (
    get_athletes, get_roster, add_athlete, update_athlete,
    add_to_roster, remove_from_roster, get_roster_stats,
    parse_roster_csv, import_roster_from_rows, generate_csv_template,
    parse_tryout_spreadsheet, import_tryout_data,
    graduate_athletes,
)

# Meets
from db.meet import (
    get_meets, get_meet, add_meet, update_meet, delete_meet,
    get_meet_report,
)

# Events
from db.events import (
    get_track_events, get_athlete_events, get_all_athlete_events,
    assign_event, set_athlete_events,
    match_event_by_number,
)

# Results
from db.results import (
    save_track_result, get_meet_results, clear_meet_results,
    get_season_bests_track, get_season_best_per_event,
    get_season_bests, get_athlete_profile,
    is_track_pr, recalculate_pr_flags,
    get_athlete_meet_counts,
)

# Lineup
from db.lineup import (
    get_lineup, save_lineup, get_athlete_event_counts,
    auto_suggest_lineup, generate_lineup_pdf, generate_checklist_pdf,
)

# XC history import
from db.import_history import parse_xc_xlsx, import_xc_season

# XC
from db.xc import (
    save_xc_result, clear_xc_results, get_xc_meet_results,
    get_xc_season_bests, get_xc_team_stats, fmt_xc_time,
    get_xc_athlete_profile, get_xc_career_results, get_xc_meet_counts,
    suggest_workout_groups, get_workout_groups,
    save_workout_groups, move_athlete_between_groups,
    is_xc_pr, recalculate_xc_pr_flags,
)
