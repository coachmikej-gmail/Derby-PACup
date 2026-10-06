"""Derby-PACup: Vola XML -> PA Cup Results, GUI + CLI in one file.

Author: Michael Jacobson, coachmikej@gmail.com
License: MIT (see LICENSE file in this directory)

This is a straight merge of the older Derby-PACup-XML.py (the XML ->
CSV/PDF pipeline) and Derby-PACup-GUI.pyw (the Tkinter front end for it)
into a single standalone script -- no more importlib loading of a sibling
file. The older scripts are kept in the legacy directory.

Takes every Vola/FIS results XML file in a directory, parses each one
in-memory (see Vola2CSV.py for the field mapping this mirrors), and
produces one Results-<Sex>-<Class>.csv plus one gridded, paginated
"PA-Cup Standings <date>-<Sex>-<Class>.pdf" for each (sex, class)
combination that had races -- up to 8 if both sexes raced and all 4
classes are selected. The <date> is the newest <Racedate> found among the
XML files. The GUI shows one tab per (sex, class) PDF; which classes run
is controlled by checkboxes (U18/U21/U21U18/U19).

Each race's points column is labeled with that race's "<Eventname> @
<Place>" from the XML, ordered by <Racedate> (earliest first, most recent
last, immediately before POINTS/WC POINTS).

Usage:
    python Derby-PACup.pyw                       # launches the GUI
    python Derby-PACup.pyw [directory] [--age-up-year YEAR]
        [--exclude-ids ID,ID,...] [--exclude-clubs CLUB,CLUB,...]
        [--classes U18,U21,U21U18,U19] [--no-csv] [--no-wc-points]
                                                   # runs headless (CLI)

directory defaults to the current directory. Every *.xml file found there
is treated as one race; its Raceheader Gender attribute ("M"/"L", or the
older "Sex" attribute some seasons use) decides whether it's a Men's or
Women's race. --age-up-year (-a) sets the age-up year used for
U18/U21/U21U18/U19 class calculations; if omitted or blank, it defaults to
the latest race year found among the directory's XML files, minus 1 (or
the current year minus 1 if that can't be determined).
--exclude-ids/--exclude-clubs drop any race result matching one of the
(comma-separated) USSA ids or club codes (case-insensitive) from every
output -- no points, not listed anywhere. --classes selects which of
U18/U21/U21U18/U19 to produce results for; blank means all four. --no-csv
skips writing Results-*.csv files; PDFs are always written regardless
(the GUI has a matching "Generate CSV files" toggle). --no-wc-points
scores each race by raw finish place instead of WC points (lower totals
are then better); the GUI has a matching "Use WC Points" toggle.

Changelog:
    1.0.0 -- Initial release: single-file merge of Derby-PACup-XML.py and
        Derby-PACup-GUI.pyw, runnable as either a GUI (no args) or a CLI
        (with args). GUI: directory picker, XML file tree (shows each
        file's Racedate/Eventname/Place), Age Up Year field (blank =
        current year minus 1), Exclude IDs / Exclude Clubs filters
        (comma-separated, club matching case-insensitive), Run button,
        Log tab, one PDF preview tab per sex with page navigation.
        Settings (age up year, window size/position, last directory,
        exclude filters) saved to a JSON config file under
        %APPDATA%\\Derby-PACup\\ and restored on the next launch. CLI:
        --age-up-year, --exclude-ids, --exclude-clubs. Version number,
        About dialog, --version flag.
    1.1.0 -- Added class-selection checkboxes so the user can choose
        which classes (HS/U21U18/U18 at the time, since renamed to
        U19/U21U18/U18) to include in a run. Output changed from one
        combined PDF per sex (all classes as sections) to one PDF per
        (sex, class) combination -- up to 6 total. The GUI now shows one
        tab per (sex, class) PDF instead of one tab per sex -- up to 6
        tabs when every class is selected for both sexes. Added the CLI
        --classes flag. Selected classes are now saved to and restored
        from the JSON config file as well.
    1.2.0 -- Added a "Generate CSV files" checkbox (checked by default)
        so Results-<Sex>-<Class>.csv writing can be turned off; PDFs are
        always written regardless of this setting. Added the matching
        CLI --no-csv flag. The checkbox state is saved to and restored
        from the JSON config file as well.
    1.3.0 -- A single unreadable XML file (corrupted, empty, or encrypted
        by antivirus software) no longer crashes the whole run -- it's
        now logged and skipped, and every other file still processes
        normally. Fixed a data bug where the same athlete could get
        split into two different ids and never combine into one row:
        NAT_code isn't consistently formatted even within one season --
        some race files prefix it with a nationality letter
        ("E6480922"), others don't ("6480922") -- and unconditionally
        stripping the first character either way corrupted the
        no-prefix case by chopping off a real digit. The leading
        character is now only stripped when it's actually a letter.
    1.4.0 -- Added a "Use WC Points" checkbox (checked by default). When
        unchecked, each race is scored by the racer's raw finish place
        (1st = 1, 2nd = 2, ...) instead of WC points, and "best" flips
        accordingly: POINTS and RANK then favor the lowest total instead
        of the highest. Per-race column headers switch between "... Pts"
        and "... Place" to match, and the PDF's total column relabels
        from "WC POINTS" to "TOTAL PLACE". Added the matching CLI
        --no-wc-points flag; the checkbox state is saved to and restored
        from the JSON config as well.
    1.5.0 -- Added a selectable U21 class (age 18-20). The scoring
        function already existed but was never wired into the
        GUI/CLI-selectable class list. Reordered the class checkboxes,
        PDF/tab generation order, and CLI --classes help text to
        U18, U21, U21U18, U19.
    1.6.0 -- Blank Age Up Year now defaults to the latest race year found
        among the directory's XML files, minus 1, instead of the current
        year minus 1 (falls back to current year minus 1 if there's no
        directory or no readable race dates). The GUI's "(blank = ####)"
        hint now updates when the directory changes, not just when the
        field is edited. PDF titles and filenames now use the newest
        race date found among the directory's XML files instead of
        today's date.

Requires: reportlab, pymupdf (pip install reportlab pymupdf)
"""

import argparse
import datetime
import json
import os
import queue
import sys
import threading
import tkinter as tk
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pymupdf
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

VERSION = "1.6.0"


# --------------------------------------------------------------------------
# Age-class / points logic
# --------------------------------------------------------------------------

# Set by process_directory()/main() before any class computation runs.
# Configurable (CLI --age-up-year, or the GUI's Age Up Year field); when
# left blank it defaults to the current year minus 1, same as the
# original Derby-PACup.tcl's (intended) AgeUpYear proc.
AGE_UP_YEAR = None


def default_age_up_year(directory=None):
    """Blank Age Up Year default: the latest race year found among the
    directory's XML files, minus 1. Falls back to the current year minus
    1 if there's no directory, no XML files, or no readable race dates."""
    if directory:
        years = []
        for path in sorted(Path(directory).glob("*.xml")):
            try:
                race_date = read_race_summary(path)["date"]
            except Exception:  # noqa: BLE001 -- an unreadable file just doesn't count
                continue
            if race_date and race_date != datetime.date.min:
                years.append(race_date.year)
        if years:
            return max(years) - 1
    return datetime.date.today().year - 1


def parse_year(text):
    """Return the birth year as an int, or None if missing/not numeric
    (some Vola exports have racers with no <Yearofbirth> at all -- such
    a racer can't be placed in any age class, but shouldn't crash the run)."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def U19(year):
    if year is None:
        return False
    age = AGE_UP_YEAR - year
    return 15 < age < 19


def U21U18(year):
    if year is None:
        return False
    age = AGE_UP_YEAR - year
    return 15 < age < 21


def U21U18U16(year):
    if year is None:
        return False
    age = AGE_UP_YEAR - year
    return 13 < age < 21


def U21(year):
    if year is None:
        return False
    age = AGE_UP_YEAR - year
    return 17 < age < 21


def U18(year):
    if year is None:
        return False
    age = AGE_UP_YEAR - year
    return 15 < age < 18


CLASS_FUNCS = {
    "U19": U19,
    "U21U18": U21U18,
    "U21U18U16": U21U18U16,
    "U21": U21,
    "U18": U18,
}


def class_name(year):
    if year is None:
        return "Unknown"
    age = AGE_UP_YEAR - year
    if age > 20:
        return "Master"
    elif age > 17:
        return "U21"
    elif age > 15:
        return "U18"
    elif age > 13:
        return "U16"
    elif age > 11:
        return "U14"
    elif age > 9:
        return "U12"
    elif age > 7:
        return "U10"
    else:
        return "U8"


WC_TABLE = [-1, 100, 80, 60, 50, 45, 40, 36, 32, 29, 26, 24, 22, 20, 18, 16,
            15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]


def WC(plc):
    if plc > 30:
        return 0
    return WC_TABLE[plc]


def is_number(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


CLASSES = ["U18", "U21U18", "U19", "U21"]

# order the PDF's class sections appear in (CSVs are independent files, so
# their write order doesn't matter and stays keyed off CLASSES above)
PDF_CLASS_ORDER = ["U18", "U21", "U21U18", "U19"]

GENDER_MAP = {"M": "Men", "L": "Women"}

RACER_PATHS = [
    "AL_race/AL_classified/AL_ranked",
    "AL_race/AL_notclassified/AL_notranked",
]


# --------------------------------------------------------------------------
# XML parsing
# --------------------------------------------------------------------------

def elem_text(elem):
    return (elem.text or "").strip() if elem is not None else ""


def round_to(value):
    return f"{value:.2f}"


def normalize_nat_code(text):
    """Strip a leading nationality-code letter from a raw NAT_code, if
    there is one -- but the SAME athlete's NAT_code isn't consistently
    formatted even within one season: some race files have it prefixed
    ("E6480922"), others have the bare digits with no prefix at all
    ("6480922"). Blindly dropping the first character either way
    corrupts the no-prefix case by chopping off a real digit -- confirmed
    against real data where that bug split one real athlete into two
    "different" ids across race files, because one file's NAT_code
    happened to have no letter prefix. Only strip when the leading
    character is actually a letter. (The extra unconditional strip this
    directory's pipeline applies afterward, in process_directory(),
    still runs on top of this either way -- for a same-length prefixed
    vs. non-prefixed NAT_code, both paths converge on the same final id.)"""
    if text and text[0].isalpha():
        return text[1:8]
    return text


def competitor_fields(competitor):
    """Look up each Competitor field by tag name rather than position --
    real Vola exports vary: some seasons put Clubname before Yearofbirth
    (or the reverse), and some records omit Clubname entirely."""
    def get(tag):
        return elem_text(competitor.find(tag)) if competitor is not None else ""

    fis = get("Fiscode")
    last = get("Lastname")
    first = get("Firstname")
    sex = get("Gender")
    nation = get("Nation")
    year = get("Yearofbirth")
    club = get("Clubname")
    nat_code = normalize_nat_code(get("NAT_code"))
    return fis, last, first, sex, nation, year, club, nat_code


def result_fields(al_result):
    """Look up each AL_result field by tag name rather than position --
    some records only have Timerun2 (no Timerun1), or no result fields
    at all."""
    def get(tag):
        return elem_text(al_result.find(tag)) if al_result is not None else ""

    def as_seconds(text):
        parts = text.split(":")
        if len(parts) < 2:
            return text
        minutes, seconds = float(parts[0]), float(parts[1])
        return round_to(minutes * 60 + seconds)

    r1 = as_seconds(get("Timerun1"))
    r2 = as_seconds(get("Timerun2"))
    total = as_seconds(get("Totaltime"))
    points = as_seconds(get("Racepoints"))
    return r1, r2, total, points


def parse_race_date(raceheader):
    racedate = raceheader.find("Racedate") if raceheader is not None else None
    if racedate is None:
        return datetime.date.min
    try:
        year = int(elem_text(racedate.find("Year")))
        month = int(elem_text(racedate.find("Month")))
        day = int(elem_text(racedate.find("Day")))
        return datetime.date(year, month, day)
    except (TypeError, ValueError):
        return datetime.date.min


def read_raceheader(root):
    """Pull the small set of Raceheader fields used for race identity/sorting."""
    raceheader = root.find("Raceheader")
    # older Vola exports use Sex= instead of Gender= on Raceheader (same
    # "M"/"L" codes) -- 2017's data mixes both across files
    gender_code = raceheader.get("Gender") or raceheader.get("Sex", "") if raceheader is not None else ""
    sex = GENDER_MAP.get(gender_code, gender_code)
    eventname = elem_text(raceheader.find("Eventname")) if raceheader is not None else ""
    place = elem_text(raceheader.find("Place")) if raceheader is not None else ""
    race_date = parse_race_date(raceheader)
    return {
        "sex": sex,
        "eventname": eventname,
        "place": place,
        "label": f"{eventname} @ {place}",
        "date": race_date,
    }


def read_race_summary(path):
    """Read just the Raceheader info for one XML file (date, eventname, place)
    without parsing racer rows -- used for lightweight file listings."""
    root = ET.parse(path).getroot()
    return read_raceheader(root)


def parse_race_xml(path):
    """Parse one Vola XML file into (sex, label, date, [racer rows]) without writing a CSV."""
    root = ET.parse(path).getroot()
    header = read_raceheader(root)
    sex, label, race_date = header["sex"], header["label"], header["date"]

    rows = []
    for racer_path in RACER_PATHS:
        for racer in root.findall(racer_path):
            _fis, last, first, _sex, _nation, year, club, id_raw = competitor_fields(
                racer.find("Competitor")
            )
            r1, r2, total, _points = result_fields(racer.find("AL_result"))
            rows.append({
                "id": id_raw[1:],
                "last": last,
                "first": first,
                "club": club,
                "year": year,
                "r1": r1,
                "r2": r2,
                "total": total,
            })
    return sex, label, race_date, rows


# --------------------------------------------------------------------------
# PDF output
# --------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = landscape(letter)
MARGIN = 20
TITLE_FONT, TITLE_SIZE = "Helvetica-Bold", 12
HEADER_FONT, HEADER_SIZE = "Helvetica-Bold", 6
BODY_FONT, BODY_SIZE = "Helvetica", 7
HEADER_LINE_HEIGHT = 7
ROW_HEIGHT = 11
# columns whose values are left-aligned like text; RANK, USSA, YEAR, CLASS,
# and every points column (race "... Pts" columns plus WC POINTS) are
# centered instead
LEFT_ALIGN_COLUMNS = {"LAST", "FIRST", "CLUB"}


def wrap_to_width(c, text, width, font, size):
    c.setFont(font, size)
    pad = 4
    words = text.split()
    lines = []
    cur = ""
    for word in words:
        trial = (cur + " " + word).strip()
        if c.stringWidth(trial, font, size) <= width - pad:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def build_pdf_columns(races, points_label):
    fixed = [("RANK", 32), ("USSA", 46), ("LAST", 70), ("FIRST", 65),
             ("CLUB", 50), ("YEAR", 36), ("CLASS", 40)]
    total_label = "WC POINTS" if points_label == "Pts" else "TOTAL PLACE"
    points_col = (total_label, 55)
    usable = PAGE_WIDTH - 2 * MARGIN
    fixed_width = sum(w for _, w in fixed) + points_col[1]
    race_width = (usable - fixed_width) / max(1, len(races))
    return fixed + [(f"{r} {points_label}", race_width) for r in races] + [points_col]


def write_pdf(out_path, sex, date_str, sections, points_label):
    """sections: list of (cls, races, rows) where rows are lists of
    stringified cell values in column order (matching build_pdf_columns)."""
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))

    for cls, races, rows in sections:
        title = f"Results-{sex}-{cls} PA CUP STANDINGS {date_str}"
        columns = build_pdf_columns(races, points_label)
        row_idx = 0

        while row_idx < len(rows) or row_idx == 0:
            c.setFont(TITLE_FONT, TITLE_SIZE)
            c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN, title)

            x_positions = []
            xc = MARGIN
            for _, w in columns:
                x_positions.append(xc)
                xc += w
            table_right = xc

            header_top = PAGE_HEIGHT - MARGIN - 20
            wrapped = [wrap_to_width(c, h, w, HEADER_FONT, HEADER_SIZE)
                       for h, w in columns]
            max_lines = max(len(w) for w in wrapped)
            header_height = max_lines * HEADER_LINE_HEIGHT + 4

            c.setLineWidth(0.5)
            c.line(MARGIN, header_top, table_right, header_top)
            for i, (h, w) in enumerate(columns):
                ty = header_top - HEADER_LINE_HEIGHT
                for line in wrapped[i]:
                    c.setFont(HEADER_FONT, HEADER_SIZE)
                    c.drawCentredString(x_positions[i] + w / 2, ty, line)
                    ty -= HEADER_LINE_HEIGHT
            header_bottom = header_top - header_height
            c.line(MARGIN, header_bottom, table_right, header_bottom)

            y = header_bottom
            max_rows = max(1, int((y - MARGIN) / ROW_HEIGHT))
            page_rows = rows[row_idx:row_idx + max_rows]

            for row in page_rows:
                row_bottom = y - ROW_HEIGHT
                for j, (val, (h, w)) in enumerate(zip(row, columns)):
                    c.setFont(BODY_FONT, BODY_SIZE)
                    if h in LEFT_ALIGN_COLUMNS:
                        c.drawString(x_positions[j] + 3, row_bottom + 2, val)
                    else:
                        c.drawCentredString(x_positions[j] + w / 2, row_bottom + 2, val)
                c.line(MARGIN, row_bottom, table_right, row_bottom)
                y = row_bottom

            for xp in x_positions + [table_right]:
                c.line(xp, header_top, xp, y)

            row_idx += len(page_rows)
            if row_idx >= len(rows):
                c.showPage()
                break
            c.showPage()

    c.save()


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def parse_filter_set(text):
    """Parse a comma-separated filter string ("123, 456,789") into a set
    of trimmed, non-empty entries. Also accepts an iterable of strings."""
    if not isinstance(text, str):
        text = ",".join(text or [])
    return {s.strip() for s in text.split(",") if s.strip()}


def process_directory(directory, age_up_year=None, exclude_ids="", exclude_clubs="",
                       classes=None, write_csv=True, use_wc_points=True, log=print):
    """Run the full XML -> Results CSV/PDF pipeline for a directory.

    `age_up_year` drives the age-class calculations (U19/U18/U21U18/etc).
    If None or blank, it defaults to the latest race year found among the
    directory's XML files, minus 1 (or the current year minus 1 if that
    can't be determined).

    `exclude_ids` / `exclude_clubs` are comma-separated strings (or an
    iterable of strings). Any race result whose USSA id or club matches
    (club matching is case-insensitive) is dropped entirely -- no points,
    not listed in any output.

    `classes` is an iterable of class codes (subset of CLASSES) to
    produce results for; None or empty means all of CLASSES.

    `write_csv` controls whether Results-<Sex>-<Class>.csv files are
    written. PDFs are always written regardless of this flag.

    `use_wc_points` picks what each race's score actually is: True
    (default) awards WC points for the racer's finish place in that race
    (higher is better, first place scores the most); False uses the raw
    finish place itself (lower is better -- 1st place scores 1, 2nd
    scores 2, etc). This flips which direction "best" means for the
    POINTS total and RANK: highest total wins with WC points, lowest
    total wins with finish place.

    `log` is called with each progress message (defaults to print; a GUI
    can pass something that appends to a text widget instead).
    Returns a list of (sex, cls, pdf_path) for each PDF written -- one
    per (sex, class) combination that had races (e.g. up to 6 if both
    sexes raced and all 3 classes are selected).
    """
    directory = Path(directory)
    xml_files = sorted(directory.glob("*.xml"))
    if not xml_files:
        log(f"No .xml files found in {directory}")
        return []

    global AGE_UP_YEAR
    AGE_UP_YEAR = (int(age_up_year) if age_up_year not in (None, "")
                   else default_age_up_year(directory))
    log(f"Using Age Up Year: {AGE_UP_YEAR}")

    classes_to_run = [c for c in PDF_CLASS_ORDER if c in (classes or CLASSES)]
    log(f"Classes: {', '.join(classes_to_run)}")
    log(f"Generate CSV files: {write_csv}")
    log(f"Use WC Points: {use_wc_points}"
        + ("" if use_wc_points else " (using finish place; lower total is better)"))
    points_label = "Pts" if use_wc_points else "Place"

    exclude_id_set = parse_filter_set(exclude_ids)
    exclude_club_set = {c.upper() for c in parse_filter_set(exclude_clubs)}
    if exclude_id_set:
        log(f"Excluding IDs: {', '.join(sorted(exclude_id_set))}")
    if exclude_club_set:
        log(f"Excluding Clubs: {', '.join(sorted(exclude_club_set))}")

    races_by_sex = {"Men": [], "Women": []}
    for path in xml_files:
        try:
            sex, label, race_date, rows = parse_race_xml(path)
        except ET.ParseError as exc:
            log(f"Skipping {path.name}: not valid XML ({exc}) -- the file "
                f"may be corrupted, empty, or encrypted (e.g. by antivirus "
                f"software)")
            continue
        if sex not in races_by_sex:
            log(f"Skipping {path.name}: unrecognized Gender")
            continue
        races_by_sex[sex].append((path.name, label, race_date, rows))

    valid_race_dates = [race_date for entries in races_by_sex.values()
                         for _, _, race_date, _ in entries
                         if race_date != datetime.date.min]
    newest_race_date = max(valid_race_dates) if valid_race_dates else datetime.date.today()
    date_str = newest_race_date.strftime("%#m/%#d/%Y")

    pdf_paths = []
    for sex, race_entries in races_by_sex.items():
        if not race_entries:
            continue
        # earliest Racedate first, latest last
        race_entries = sorted(race_entries, key=lambda e: e[2])
        RACES = [label for _, label, _, _ in race_entries]
        racers = {}
        racer_order = []

        for filename, race_label, race_date, rows in race_entries:
            log(f"Processing {sex} Race Data File ... {filename} ({race_label}, {race_date})")
            for row in rows:
                id_ = row["id"]
                if id_ in exclude_id_set or row["club"].strip().upper() in exclude_club_set:
                    log(f"{id_}. {row['first']} {row['last']} ({row['club']}): "
                        f"filtered out, race result excluded")
                    continue

                if id_ not in racers:
                    racers[id_] = {
                        "last": row["last"],
                        "first": row["first"],
                        "club": row["club"],
                        "year": row["year"],
                    }
                    racers[id_]["class"] = class_name(parse_year(racers[id_]["year"]))
                    racer_order.append(id_)
                    if parse_year(racers[id_]["year"]) is None:
                        log(f"{id_}. {racers[id_]['first']} {racers[id_]['last']}: "
                            f"missing/invalid birth year {racers[id_]['year']!r} -- "
                            "excluded from all class standings")

                log(f"{id_}. {racers[id_]['first']} {racers[id_]['last']}")

                total, r1, r2 = row["total"], row["r1"], row["r2"]
                if total != "":
                    racers[id_][(race_label, "time")] = total
                elif is_number(r1):
                    racers[id_][(race_label, "time")] = r2
                else:
                    racers[id_][(race_label, "time")] = r1

        # determine overall place per class
        for cls in classes_to_run:
            for race in RACES:
                log(f"Processing {sex} Race {cls} ... {race}")
                race_times = []
                race_ids = []
                for a in racer_order:
                    t = racers[a].get((race, "time"))
                    if t is not None and is_number(t):
                        if CLASS_FUNCS[cls](parse_year(racers[a]["year"])):
                            race_times.append(t)
                            race_ids.append(a)

                if race_times:
                    sorted_times = sorted(race_times, key=float)
                    for id_ in race_ids:
                        t = racers[id_][(race, "time")]
                        rank = sorted_times.index(t) + 1
                        racers[id_][(race, cls)] = rank

        # print out the results
        for cls in classes_to_run:
            log(f"Class {cls} results")
            out_name = directory / f"Results-{sex}-{cls}.csv"

            entries = []
            for a in racer_order:
                if not CLASS_FUNCS[cls](parse_year(racers[a]["year"])):
                    continue
                race_vals = []
                points = 0
                has_races = False
                for race in RACES:
                    if (race, cls) in racers[a]:
                        finish_place = racers[a][(race, cls)]
                        pts = WC(finish_place) if use_wc_points else finish_place
                        race_vals.append(str(pts))
                        points += pts
                        has_races = True
                    elif (race, "time") in racers[a]:
                        race_vals.append(str(racers[a][(race, "time")]))
                    else:
                        race_vals.append(" ")
                entries.append((a, race_vals, points, has_races))

            # standard competition ranking (ties share a rank; the next
            # distinct rank skips ahead by the number of ties). Higher
            # POINTS is better with WC points; lower is better with raw
            # finish place -- except a racer with zero scored races
            # (points == 0 only because there was nothing to sum) is the
            # worst possible outcome in finish place mode, not the
            # literal best, so treat that case as "infinitely bad" rather
            # than reading 0 as a great score.
            def rank_key(p, has_races_):
                if use_wc_points or has_races_:
                    return p
                return float("inf")

            for a, race_vals, points, has_races in entries:
                key = rank_key(points, has_races)
                rank = 1 + sum(
                    1 for _, _, p2, hr2 in entries
                    if (rank_key(p2, hr2) > key if use_wc_points else rank_key(p2, hr2) < key)
                )
                racers[a][(cls, "rank")] = rank

            entries.sort(key=lambda e: -rank_key(e[2], e[3]) if use_wc_points
                         else rank_key(e[2], e[3]))

            if write_csv:
                with open(out_name, "w") as fout:
                    header = "RANK,USSA,LAST,FIRST,CLUB,YEAR,CLASS"
                    for r in RACES:
                        header += f",{r} {points_label}"
                    fout.write(header + ",POINTS\n")

                    for a, race_vals, points, has_races in entries:
                        summary = "," + ",".join(race_vals)
                        row = (
                            f"{racers[a][(cls, 'rank')]},{a},"
                            f"{racers[a]['last']},{racers[a]['first']},"
                            f"{racers[a]['club']},{racers[a]['year']},"
                            f"{racers[a].get('class', '')}{summary},{points},"
                        )
                        fout.write(row + "\n")

            pdf_rows = []
            for a, race_vals, points, has_races in entries:
                pdf_rows.append(
                    [str(racers[a][(cls, "rank")]), a,
                     racers[a]["last"], racers[a]["first"],
                     racers[a]["club"], racers[a]["year"],
                     racers[a].get("class", "")]
                    + race_vals + [str(points)]
                )

            pdf_name = directory / f"PA-Cup Standings {date_str.replace('/', '-')}-{sex}-{cls}.pdf"
            write_pdf(pdf_name, sex, date_str, [(cls, RACES, pdf_rows)], points_label)
            log(f"Wrote {pdf_name}")
            pdf_paths.append((sex, cls, pdf_name))

    return pdf_paths


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

ZOOM = 1.4
CONFIG_DIR = Path(os.getenv("APPDATA", Path.home())) / "Derby-PACup"
CONFIG_PATH = CONFIG_DIR / "Derby-PACup-GUI-config.json"
DEFAULT_GEOMETRY = "1100x750"


class PdfViewer(ttk.Frame):
    """One tab: a scrollable page image plus Prev/Next/Open controls."""

    def __init__(self, parent, pdf_path):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.doc = pymupdf.open(str(self.pdf_path))
        self.page_index = 0
        self._photo = None  # keep a reference so Tk doesn't garbage-collect it

        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Button(toolbar, text="< Prev", command=self.prev_page).pack(side="left")
        ttk.Button(toolbar, text="Next >", command=self.next_page).pack(side="left", padx=(4, 0))
        self.page_label = ttk.Label(toolbar, text="")
        self.page_label.pack(side="left", padx=12)
        ttk.Button(toolbar, text="Open in default viewer",
                   command=self.open_external).pack(side="right")

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(side="top", fill="both", expand=True)
        h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal")
        v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.canvas = tk.Canvas(
            canvas_frame, background="#808080",
            xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set,
        )
        h_scroll.config(command=self.canvas.xview)
        v_scroll.config(command=self.canvas.yview)
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.show_page(0)

    def show_page(self, index):
        index = max(0, min(index, self.doc.page_count - 1))
        self.page_index = index
        page = self.doc[index]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
        self._photo = tk.PhotoImage(data=pix.tobytes("ppm"))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.page_label.config(text=f"Page {index + 1} / {self.doc.page_count}")

    def prev_page(self):
        self.show_page(self.page_index - 1)

    def next_page(self):
        self.show_page(self.page_index + 1)

    def open_external(self):
        os.startfile(self.pdf_path)


class DerbyPACupGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"PA Cup Results v{VERSION}")
        self.geometry(DEFAULT_GEOMETRY)

        self.directory = None
        self.log_queue = queue.Queue()
        self.worker = None

        self._build_layout()
        self._load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_log_queue)

    def _build_layout(self):
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=8, pady=8)

        ttk.Button(top, text="Select Directory...", command=self.choose_directory).pack(side="left")
        self.dir_label = ttk.Label(top, text="(no directory selected)")
        self.dir_label.pack(side="left", padx=8)
        ttk.Button(top, text="About", command=self.show_about).pack(side="left", padx=(8, 0))

        self.run_button = ttk.Button(top, text="Run", command=self.run_processing, state="disabled")
        self.run_button.pack(side="right")

        self.effective_age_label = ttk.Label(top, foreground="gray")
        self.effective_age_label.pack(side="right", padx=(0, 8))

        self.age_up_year_var = tk.StringVar()
        self.age_up_year_var.trace_add("write", lambda *_: self._update_effective_age_label())
        age_entry = ttk.Entry(top, width=6, textvariable=self.age_up_year_var, justify="center")
        age_entry.pack(side="right")

        ttk.Label(top, text="Age Up Year:").pack(side="right", padx=(0, 4))

        self._update_effective_age_label()

        filters = ttk.Frame(self)
        filters.pack(side="top", fill="x", padx=8, pady=(0, 8))

        ttk.Label(filters, text="Exclude IDs:").pack(side="left")
        self.exclude_ids_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.exclude_ids_var, width=30).pack(
            side="left", padx=(4, 16)
        )

        ttk.Label(filters, text="Exclude Clubs:").pack(side="left")
        self.exclude_clubs_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.exclude_clubs_var, width=30).pack(
            side="left", padx=(4, 16)
        )

        ttk.Label(filters, text="Classes:").pack(side="left")
        self.class_vars = {}
        for cls in PDF_CLASS_ORDER:
            var = tk.BooleanVar(value=True)
            self.class_vars[cls] = var
            ttk.Checkbutton(filters, text=cls, variable=var).pack(side="left", padx=(4, 0))

        self.write_csv_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filters, text="Generate CSV files", variable=self.write_csv_var
        ).pack(side="left", padx=(16, 0))

        self.use_wc_points_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filters, text="Use WC Points", variable=self.use_wc_points_var
        ).pack(side="left", padx=(16, 0))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(body)
        ttk.Label(left, text="XML files").pack(anchor="w")
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True)
        self.file_tree = ttk.Treeview(tree_frame, show="tree")
        tree_scroll = ttk.Scrollbar(tree_frame, command=self.file_tree.yview)
        self.file_tree.config(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.file_tree.pack(side="left", fill="both", expand=True)
        body.add(left, weight=1)

        right = ttk.Frame(body)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        body.add(right, weight=3)

        self.log_tab = ttk.Frame(self.notebook)
        self.log_text = tk.Text(self.log_tab, state="disabled", wrap="word")
        log_scroll = ttk.Scrollbar(self.log_tab, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.notebook.add(self.log_tab, text="Log")

    def _load_config(self):
        if not CONFIG_PATH.exists():
            # First run: nothing to restore. Write literal defaults rather
            # than self.geometry() -- the window hasn't been drawn yet, so
            # Tk would report a meaningless "1x1+0+0" placeholder size.
            self._write_config({
                "age_up_year": "",
                "window_geometry": DEFAULT_GEOMETRY,
                "directory": "",
                "exclude_ids": "",
                "exclude_clubs": "",
                "classes": list(PDF_CLASS_ORDER),
                "write_csv": True,
                "use_wc_points": True,
            })
            return

        try:
            config = json.loads(CONFIG_PATH.read_text())
        except (OSError, ValueError) as exc:
            self._log(f"Could not read config file {CONFIG_PATH}: {exc}")
            return

        geometry = config.get("window_geometry")
        if geometry:
            try:
                self.geometry(geometry)
            except tk.TclError:
                pass

        age_up_year = config.get("age_up_year", "")
        if age_up_year:
            self.age_up_year_var.set(str(age_up_year))

        self.exclude_ids_var.set(config.get("exclude_ids", ""))
        self.exclude_clubs_var.set(config.get("exclude_clubs", ""))

        selected_classes = config.get("classes", list(PDF_CLASS_ORDER))
        for cls, var in self.class_vars.items():
            var.set(cls in selected_classes)

        self.write_csv_var.set(config.get("write_csv", True))
        self.use_wc_points_var.set(config.get("use_wc_points", True))

        directory = config.get("directory")
        if directory and Path(directory).is_dir():
            self.directory = Path(directory)
            self.dir_label.config(text=str(self.directory))
            self.refresh_file_list()

    def _save_config(self):
        self._write_config({
            "age_up_year": self.age_up_year_var.get().strip(),
            "window_geometry": self.geometry(),
            "directory": str(self.directory) if self.directory else "",
            "exclude_ids": self.exclude_ids_var.get().strip(),
            "exclude_clubs": self.exclude_clubs_var.get().strip(),
            "classes": [cls for cls, var in self.class_vars.items() if var.get()],
            "write_csv": self.write_csv_var.get(),
            "use_wc_points": self.use_wc_points_var.get(),
        })

    def _write_config(self, config):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(config, indent=2))
        except OSError as exc:
            self._log(f"Could not write config file {CONFIG_PATH}: {exc}")

    def _on_close(self):
        self._save_config()
        self.destroy()

    def show_about(self):
        messagebox.showinfo(
            "About PA Cup Results",
            f"PA Cup Results\nVersion {VERSION}\n"
            "By Michael Jacobson - coachmikej@gmail.com\n\n"
            "Converts Vola/FIS/LiveTiming XML race results into PA Cup Results CSVs "
            "and standings PDFs.",
        )

    def choose_directory(self):
        chosen = filedialog.askdirectory(title="Select directory with XML race files")
        if not chosen:
            return
        self.directory = Path(chosen)
        self.dir_label.config(text=str(self.directory))
        self.refresh_file_list()

    def refresh_file_list(self):
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        xml_files = sorted(self.directory.glob("*.xml")) if self.directory else []
        for path in xml_files:
            node = self.file_tree.insert("", "end", text=path.name, open=True)
            try:
                info = read_race_summary(path)
                self.file_tree.insert(node, "end", text=f"Racedate: {info['date']}")
                self.file_tree.insert(node, "end", text=f"Eventname: {info['eventname']}")
                self.file_tree.insert(node, "end", text=f"Place: {info['place']}")
            except Exception as exc:  # noqa: BLE001 -- surface a bad XML file inline
                self.file_tree.insert(node, "end", text=f"(could not read: {exc})")

        self.run_button.config(state="normal" if xml_files else "disabled")
        if self.directory and not xml_files:
            self._log(f"No .xml files found in {self.directory}")

        self._update_effective_age_label()

    def _update_effective_age_label(self):
        text = self.age_up_year_var.get().strip()
        if not text:
            self.effective_age_label.config(
                text=f"(blank = {default_age_up_year(self.directory)})")
            return
        try:
            int(text)
            self.effective_age_label.config(text=f"(using {text})")
        except ValueError:
            self.effective_age_label.config(text="(must be a year)")

    def run_processing(self):
        if not self.directory or self.worker and self.worker.is_alive():
            return

        age_text = self.age_up_year_var.get().strip()
        if age_text:
            try:
                int(age_text)
            except ValueError:
                messagebox.showerror("Invalid Age Up Year", f"{age_text!r} is not a valid year.")
                return

        selected_classes = [cls for cls, var in self.class_vars.items() if var.get()]
        if not selected_classes:
            messagebox.showerror("No classes selected", "Select at least one class to run.")
            return

        self.run_button.config(state="disabled")
        self._clear_pdf_tabs()
        self._log(f"--- Processing {self.directory} ---")

        exclude_ids = self.exclude_ids_var.get().strip()
        exclude_clubs = self.exclude_clubs_var.get().strip()
        write_csv = self.write_csv_var.get()
        use_wc_points = self.use_wc_points_var.get()
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(age_text, exclude_ids, exclude_clubs, selected_classes, write_csv,
                  use_wc_points),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, age_up_year, exclude_ids, exclude_clubs, classes, write_csv,
                     use_wc_points):
        try:
            pdf_paths = process_directory(
                self.directory, age_up_year=age_up_year,
                exclude_ids=exclude_ids, exclude_clubs=exclude_clubs,
                classes=classes, write_csv=write_csv, use_wc_points=use_wc_points,
                log=lambda msg: self.log_queue.put(("log", msg)),
            )
            self.log_queue.put(("done", pdf_paths))
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the GUI
            self.log_queue.put(("error", str(exc)))

    def _poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self._log("--- Done ---")
                    self._show_pdfs(payload)
                    self.run_button.config(state="normal")
                elif kind == "error":
                    self._log(f"ERROR: {payload}")
                    messagebox.showerror("Processing failed", payload)
                    self.run_button.config(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_pdf_tabs(self):
        for tab_id in self.notebook.tabs():
            if tab_id != str(self.log_tab):
                self.notebook.forget(tab_id)

    def _show_pdfs(self, pdf_paths):
        if not pdf_paths:
            messagebox.showinfo("No results", "No PDFs were generated (no races found for the "
                                               "selected classes).")
            return
        for sex, cls, path in pdf_paths:
            viewer = PdfViewer(self.notebook, path)
            self.notebook.add(viewer, text=f"{sex} - {cls}")
        self.notebook.select(1)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def main_cli():
    parser = argparse.ArgumentParser(
        description="Convert Vola XML race results into PA Cup Results CSVs/PDFs."
    )
    parser.add_argument("--version", action="version", version=f"Derby-PACup {VERSION}")
    parser.add_argument("directory", nargs="?", default=".",
                         help="directory containing the XML race files (default: current directory)")
    parser.add_argument("--age-up-year", "-a", default="",
                         help="age-up year for class calculations; blank = latest race year in "
                              "the XML files - 1")
    parser.add_argument("--exclude-ids", default="",
                         help="comma-separated USSA ids to exclude from all results")
    parser.add_argument("--exclude-clubs", default="",
                         help="comma-separated club codes to exclude from all results")
    parser.add_argument("--classes", default="",
                         help=f"comma-separated classes to run, from {CLASSES}; blank = all")
    parser.add_argument("--no-csv", action="store_true",
                         help="skip writing Results-*.csv files (PDFs are always written)")
    parser.add_argument("--no-wc-points", action="store_true",
                         help="score each race by its raw finish place instead of WC points "
                              "(lower totals are then better, not higher)")
    args = parser.parse_args()
    classes = parse_filter_set(args.classes) or None
    process_directory(Path(args.directory), age_up_year=args.age_up_year,
                       exclude_ids=args.exclude_ids, exclude_clubs=args.exclude_clubs,
                       classes=classes, write_csv=not args.no_csv,
                       use_wc_points=not args.no_wc_points)


def main_gui():
    app = DerbyPACupGUI()
    app.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main_cli()
    else:
        main_gui()
