"""
milesplit.py — Milesplit Raw Results Importer
Fetches and parses the /raw results page from any Milesplit meet URL,
then matches results against a roster by last name.

Usage:
    from milesplit import fetch_and_parse, match_to_roster
"""

import re
import urllib.request
from typing import Optional


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """
    Accept several URL forms and return the canonical /raw URL.

    Accepted inputs:
      nc.milesplit.com/meets/...                 (no protocol)
      https://nc.milesplit.com/meets/.../results/ID
      https://nc.milesplit.com/meets/.../results/ID/raw
      https://nc.milesplit.com/meets/.../results/ID/formatted
    """
    url = url.strip().rstrip("/")

    # Add protocol if missing
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # Swap any trailing variant for /raw
    for suffix in ("/formatted", "/raw"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break

    if "/results/" in url:
        return url + "/raw"

    # meet home page — can't build results path without scraping
    return url + "/raw"


def is_valid_milesplit_url(url: str) -> bool:
    return "milesplit.com/meets/" in url and "/results/" in url


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_raw_text(url: str, timeout: int = 15) -> tuple[str, Optional[str]]:
    """
    Fetch the raw results page.
    Returns (text, error_message). On success error_message is None.
    """
    raw_url = normalize_url(url)
    html, err = _fetch_html(raw_url, timeout)
    if err:
        return "", err

    # Raw results are inside a <pre> block
    pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL)
    if not pre_match:
        pre_match = re.search(r"<code[^>]*>(.*?)</code>", html, re.DOTALL)
    if not pre_match:
        return "", "No raw results block found on this page. Make sure you're using the /raw URL."
    text = pre_match.group(1)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    return text, None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Matches event headers like "Boys 1600 Meters", "Girls Long Jump", etc.
EVENT_HEADER = re.compile(
    r"^((?:Boys|Girls|Mixed)\s+[\w\s\(\)xX]+?)$",
    re.MULTILINE
)

# Matches a result row. Handles:
#   - Running times: 11.24, 1:54.32, 10:18.72
#   - Field marks:   5.82m, 18-04, 1.85m
#   - DNF/DNS/NT/DQ
#   - Names with apostrophes, hyphens, accents
#   - Grade as FR/SO/JR/SR or digit (middle school)
RESULT_ROW = re.compile(
    r"^\s{1,4}(\d*)\s+"                          # place (optional)
    r"([A-Z][A-Z'\-\.À-ÿ\s]+),\s+"              # LAST NAME,
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-\s]+?)\s{2,}"   # First name (2+ spaces terminate)
    r"(?:FR|SO|JR|SR|\d+)\s+"                    # grade/year
    r"(.+?)\s{2,}"                                # team name
    r"(\d[\d:.\-]+m?|DNF|DNS|NT|DQ)",            # result value
    re.MULTILINE
)

# Section dividers — lines of = signs separate finals from sections
DIVIDER = re.compile(r"^={10,}", re.MULTILINE)

# Detects the "Finals" block vs repeated section blocks
FINALS_MARKER = re.compile(r"^Finals\s*$", re.MULTILINE)


def _clean_name(s: str) -> str:
    return s.strip().upper()


def parse_raw_results(text: str) -> list[dict]:
    """
    Parse the full raw results text into a list of result dicts:
    {
        event:        str,   e.g. "Boys 1600 Meters"
        gender:       str,   "M" or "F"
        last_name:    str,
        first_name:   str,
        team:         str,
        result_value: str,   e.g. "4:48.44", "5.82m", "DNF"
        place:        int | None,
        is_valid:     bool,  False for DNF/DNS/NT/DQ
    }
    """
    results = []

    # Split text into event chunks by finding event headers
    # Each chunk = from one header to the next (or end of text)
    header_positions = [(m.start(), m.group(1).strip())
                        for m in EVENT_HEADER.finditer(text)]

    for i, (start, event_name) in enumerate(header_positions):
        end = header_positions[i + 1][0] if i + 1 < len(header_positions) else len(text)
        chunk = text[start:end]

        gender = "M" if event_name.startswith("Boys") else "F"

        # Only parse the Finals block — skip repeated section blocks
        # (Milesplit raw repeats results once per section AND once in finals)
        finals_match = FINALS_MARKER.search(chunk)
        if finals_match:
            finals_text = chunk[finals_match.start():]
            dividers = list(DIVIDER.finditer(finals_text))
            if len(dividers) >= 2:
                # Structure: Finals / divider1 / column headers / divider2 / results / divider3?
                parse_region = finals_text[dividers[1].end():]
                next_div = DIVIDER.search(parse_region)
                if next_div:
                    parse_region = parse_region[:next_div.start()]
            elif len(dividers) == 1:
                parse_region = finals_text[dividers[0].end():]
            else:
                parse_region = finals_text
        else:
            parse_region = chunk

        seen_in_event = set()  # deduplicate within an event

        for m in RESULT_ROW.finditer(parse_region):
            place_str   = m.group(1).strip()
            last_name   = _clean_name(m.group(2))
            first_name  = m.group(3).strip().title()
            team        = m.group(4).strip()
            result_val  = m.group(5).strip()

            dedup_key = (last_name, first_name)
            if dedup_key in seen_in_event:
                continue
            seen_in_event.add(dedup_key)

            is_valid = result_val not in ("DNF", "DNS", "NT", "DQ")
            place    = int(place_str) if place_str and is_valid else None

            results.append({
                "event":        event_name,
                "gender":       gender,
                "last_name":    last_name,
                "first_name":   first_name,
                "team":         team,
                "result_value": result_val,
                "place":        place,
                "is_valid":     is_valid,
            })

    return results


# ---------------------------------------------------------------------------
# Roster matching
# ---------------------------------------------------------------------------

def match_to_roster(parsed_results: list[dict],
                    roster: list[dict],
                    team_name: str = "") -> dict:
    """
    Match parsed results against a roster.

    Matching strategy (in order of confidence):
      1. Last name + first name exact match (case-insensitive)
      2. Last name + first initial match
      3. Last name only (flagged as ambiguous if multiple athletes share it)

    Args:
        parsed_results: output of parse_raw_results()
        roster:         list of athlete dicts from db.get_roster()
        team_name:      if provided, pre-filter results to this team name
                        (partial match, case-insensitive)

    Returns:
        {
          "matched":   [{result_dict, athlete_id, match_confidence}, ...],
          "unmatched": [result_dict, ...],   # on Milesplit but not on roster
          "absent":    [result_dict, ...],   # DNF/DNS athletes on roster
        }
    """
    # Build lookup structures
    # last_name -> [athlete, ...]
    by_last: dict[str, list[dict]] = {}
    for a in roster:
        key = a["last_name"].upper()
        by_last.setdefault(key, []).append(a)

    # (last, first) -> athlete
    by_full = {
        (a["last_name"].upper(), a["first_name"].upper()): a
        for a in roster
    }

    # (last, first_initial) -> [athlete, ...]
    by_initial: dict[tuple, list[dict]] = {}
    for a in roster:
        key = (a["last_name"].upper(), a["first_name"][0].upper())
        by_initial.setdefault(key, []).append(a)

    matched   = []
    unmatched = []
    absent    = []

    # Pre-filter to school team if name provided
    if team_name:
        candidates = [
            r for r in parsed_results
            if team_name.lower() in r["team"].lower()
        ]
    else:
        candidates = parsed_results

    for result in candidates:
        last  = result["last_name"].upper()
        first = result["first_name"].upper()
        first_initial = first[0] if first else ""

        athlete = None
        confidence = None

        # Strategy 1: exact full name
        full_key = (last, first)
        if full_key in by_full:
            athlete    = by_full[full_key]
            confidence = "exact"

        # Strategy 2: last + first initial
        if athlete is None:
            init_key = (last, first_initial)
            init_matches = by_initial.get(init_key, [])
            if len(init_matches) == 1:
                athlete    = init_matches[0]
                confidence = "initial"
            elif len(init_matches) > 1:
                confidence = "ambiguous"

        # Strategy 3: last name only
        if athlete is None and confidence != "ambiguous":
            last_matches = by_last.get(last, [])
            if len(last_matches) == 1:
                athlete    = last_matches[0]
                confidence = "last_only"
            elif len(last_matches) > 1:
                confidence = "ambiguous"

        if athlete and confidence != "ambiguous":
            entry = {**result, "athlete_id": athlete["id"],
                     "match_confidence": confidence}
            if result["is_valid"]:
                matched.append(entry)
            else:
                absent.append(entry)
        else:
            unmatched.append({**result, "match_confidence": confidence or "none"})

    return {"matched": matched, "unmatched": unmatched, "absent": absent}


# ---------------------------------------------------------------------------
# Team results page parser (free, no paywall)
# URL: /meets/{ID}-{slug}/teams/{TEAM_ID}
# ---------------------------------------------------------------------------

def build_team_results_url(meet_url: str, team_id: int) -> str:
    """
    Given any meet URL, build the team results page URL.
    e.g. https://nc.milesplit.com/meets/737047-mooresville.../results
      → https://nc.milesplit.com/meets/737047-mooresville.../teams/22928
    """
    url = meet_url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    # Strip any trailing path segments after the meet slug
    # Keep everything up to and including the meet slug
    match = re.search(r"(https?://[^/]+/meets/\d+-[^/]+)", url)
    if match:
        base = match.group(1)
    else:
        # Fallback: strip known suffixes
        for suffix in ("/results", "/teams", "/info", "/entries", "/articles"):
            if suffix in url:
                url = url[:url.index(suffix)]
        base = url
    return f"{base}/teams/{team_id}"


def parse_team_results_html(html: str) -> list[dict]:
    """
    Parse the /teams/{ID} results page HTML into result dicts.
    Supports both the legacy layout (id="teamResultsByEvent", thead rows)
    and the current layout (class="meetTeams__table", groupTitle headings).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    PLACE_RE = re.compile(r"(\d+)(?:st|nd|rd|th)")

    # --- Try current layout first (meetTeams__table) ---
    new_tables = soup.find_all("table", class_="meetTeams__table")
    if new_tables:
        return _parse_new_layout(new_tables, soup, PLACE_RE)

    # --- Fall back to legacy layout ---
    table = soup.find("table", id="teamResultsByEvent") or soup.find("table")
    if not table:
        return []
    return _parse_legacy_layout(table, PLACE_RE)


def _parse_new_layout(tables, soup, PLACE_RE) -> list[dict]:
    """Parse the current MileSplit meetTeams__table layout."""
    results = []

    for table in tables:
        heading = table.find_previous("h3", class_="meetTeams__groupTitle")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if title.startswith("Girls"):
            gender = "F"
            event = title[5:].strip()
        elif title.startswith("Boys"):
            gender = "M"
            event = title[4:].strip()
        else:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            participant = row.find("td", class_="meetTeams__participant")
            mark = row.find("td", class_="meetTeams__mark")
            place_cell = row.find("td", class_="meetTeams__place")

            if not participant or not mark:
                continue

            link = participant.find("a")
            full_name = " ".join(
                (link or participant).get_text(strip=True).split()
            )
            result_val = mark.get_text(strip=True)
            if not full_name or not result_val:
                continue

            place = None
            if place_cell:
                place_match = PLACE_RE.search(place_cell.get_text(strip=True))
                place = int(place_match.group(1)) if place_match else None

            parts = full_name.split()
            first = parts[0] if parts else ""
            last = " ".join(parts[1:]) if len(parts) > 1 else ""

            if not first and not last:
                continue

            results.append({
                "event":        event,
                "gender":       gender,
                "first_name":   first,
                "last_name":    last,
                "result_value": result_val,
                "place":        place,
                "is_valid":     True,
            })

    return results


def _parse_legacy_layout(table, PLACE_RE) -> list[dict]:
    """Parse the legacy teamResultsByEvent layout."""
    results = []
    current_gender = None
    current_event = None

    for row in table.find_all("tr"):
        classes = row.get("class", [])

        if "thead" in classes and "tertiary" not in classes:
            th = row.find("th")
            if th:
                text = th.get_text(strip=True)
                if text in ("Girls", "Boys"):
                    current_gender = "F" if text == "Girls" else "M"
                    current_event = None
            continue

        if "thead" in classes and "tertiary" in classes:
            th = row.find("th")
            if th:
                current_event = th.get_text(strip=True)
            continue

        if not current_event or not current_gender:
            continue

        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        result_val = cells[0].get_text(strip=True)
        if not result_val:
            continue

        athlete_link = cells[2].find("a")
        if not athlete_link:
            continue

        full_name = " ".join(athlete_link.get_text(strip=True).split())
        place_text = cells[3].get_text(strip=True)
        place_match = PLACE_RE.match(place_text)
        place = int(place_match.group(1)) if place_match else None

        parts = full_name.split()
        first = parts[0] if parts else ""
        last = " ".join(parts[1:]) if len(parts) > 1 else ""

        if not first and not last:
            continue

        results.append({
            "event":        current_event,
            "gender":       current_gender,
            "first_name":   first,
            "last_name":    last,
            "result_value": result_val,
            "place":        place,
            "is_valid":     True,
        })

    return results


def fetch_team_results(meet_url: str, team_id: int,
                       timeout: int = 15) -> tuple[list[dict], str | None]:
    """
    Fetch and parse the team results page for a meet.
    Returns (results, error_message).
    """
    url = build_team_results_url(meet_url, team_id)
    html, err = fetch_raw_text.__wrapped__(url, timeout) \
        if hasattr(fetch_raw_text, "__wrapped__") else _fetch_html(url, timeout)
    if err:
        return [], err
    results = parse_team_results_html(html)
    if not results:
        return [], "No results found on that page. Check the meet URL and team ID."
    return results, None


def _fetch_html(url: str, timeout: int = 15) -> tuple[str, str | None]:
    """Fetch raw HTML from a URL. Returns (html, error)."""
    try:
        import requests as req_lib
        resp = req_lib.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; athletics-coach-tool/1.0)"}
        )
        resp.raise_for_status()
        return resp.text, None
    except Exception as e:
        return "", f"Network error: {e}"

if __name__ == "__main__":
    test_url = "https://nc.milesplit.com/meets/660711-mooresville-mid-season-meet-2025/results/1141175/raw"
    print(f"Fetching: {test_url}")
    text, err = fetch_raw_text(test_url)
    if err:
        print(f"Error: {err}")
    else:
        results = parse_raw_results(text)
        mooresville = [r for r in results if "Mooresville" in r["team"]]
        print(f"\nTotal results parsed: {len(results)}")
        print(f"Mooresville results:  {len(mooresville)}")
        print("\nSample Mooresville results:")
        for r in mooresville[:8]:
            print(f"  {r['event']:<25} {r['last_name']}, {r['first_name']:<15} {r['result_value']}")
