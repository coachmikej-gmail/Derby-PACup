"""Combined Vola XML -> PA Cup Results pipeline (no intermediate CSVs).

Author: Michael Jacobson, coachmikej@gmail.com
License: MIT (see LICENSE file in this directory)

Takes every Vola/FIS results XML file in a directory, parses each one
in-memory the same way Vola2CSV.py does (see that file for the field
mapping this mirrors), and feeds the parsed racer data straight into the
same class/ranking logic as Derby-PACup.py to produce Results-*.csv files.

Each race's points column in the output is labeled with that race's
"<Eventname> @ <Place>" from the XML (e.g. "PA Cup #1 - Mens SL @ Tussey
Mountain") instead of a race name, since there's no longer a
"{race}-{sex}.csv" filename to derive one from. Race columns are ordered
by each race's <Racedate> (earliest first, most recent last, immediately
before the POINTS/WC POINTS column).

Alongside the CSVs, one PDF per sex is written -- "PA-Cup Standings
<date>-<Sex>.pdf" -- combining every class's table into one gridded,
paginated, landscape document, in the same style as the existing
"PA-Cup Standings ...-Men.pdf" / "...-Women.pdf" files in this directory
(title bar per class, repeated header row, full grid, new page as needed).
Requires reportlab (pip install reportlab).

Usage:
    python Derby-PACup-XML.py [directory] [--age-up-year YEAR]
        [--exclude-ids ID,ID,...] [--exclude-clubs CLUB,CLUB,...]

directory defaults to the current directory. Every *.xml file found there
is treated as one race; its Raceheader Gender attribute ("M"/"L", or the
older "Sex" attribute some seasons use) decides whether it's a Men's or
Women's race. --age-up-year (-a) sets the age-up year used for
HS/U18/U21U18/etc class calculations; if omitted or blank, it defaults to
the current year minus 1. --exclude-ids/--exclude-clubs drop any race
result matching one of the (comma-separated) USSA ids or club codes
(case-insensitive) from every output -- no points, not listed anywhere.
"""

import argparse
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

# Set by process_directory()/main() before any class computation runs.
# Configurable (CLI --age-up-year, or the GUI's Age Up Year field); when
# left blank it defaults to the current year minus 1, same as the
# original Derby-PACup.tcl's (intended) AgeUpYear proc.
AGE_UP_YEAR = None


def default_age_up_year():
    return datetime.date.today().year - 1


def parse_year(text):
    """Return the birth year as an int, or None if missing/not numeric
    (some Vola exports have racers with no <Yearofbirth> at all -- such
    a racer can't be placed in any age class, but shouldn't crash the run)."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def HS(year):
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
    "HS": HS,
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


CLASSES = ["U18", "U21U18", "HS"]

# order the PDF's class sections appear in (CSVs are independent files, so
# their write order doesn't matter and stays keyed off CLASSES above)
PDF_CLASS_ORDER = ["HS", "U21U18", "U18"]

GENDER_MAP = {"M": "Men", "L": "Women"}

RACER_PATHS = [
    "AL_race/AL_classified/AL_ranked",
    "AL_race/AL_notclassified/AL_notranked",
]


def elem_text(elem):
    return (elem.text or "").strip() if elem is not None else ""


def round_to(value):
    return f"{value:.2f}"


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
    nat_code = get("NAT_code")[1:8]
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


def build_pdf_columns(races):
    fixed = [("RANK", 32), ("USSA", 46), ("LAST", 70), ("FIRST", 65),
             ("CLUB", 50), ("YEAR", 36), ("CLASS", 40)]
    points_col = ("WC POINTS", 55)
    usable = PAGE_WIDTH - 2 * MARGIN
    fixed_width = sum(w for _, w in fixed) + points_col[1]
    race_width = (usable - fixed_width) / max(1, len(races))
    return fixed + [(f"{r} Pts", race_width) for r in races] + [points_col]


def write_pdf(out_path, sex, date_str, sections):
    """sections: list of (cls, races, rows) where rows are lists of
    stringified cell values in column order (matching build_pdf_columns)."""
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))

    for cls, races, rows in sections:
        title = f"Results-{sex}-{cls} PA CUP STANDINGS {date_str}"
        columns = build_pdf_columns(races)
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


def parse_filter_set(text):
    """Parse a comma-separated filter string ("123, 456,789") into a set
    of trimmed, non-empty entries. Also accepts an iterable of strings."""
    if not isinstance(text, str):
        text = ",".join(text or [])
    return {s.strip() for s in text.split(",") if s.strip()}


def process_directory(directory, age_up_year=None, exclude_ids="", exclude_clubs="", log=print):
    """Run the full XML -> Results CSV/PDF pipeline for a directory.

    `age_up_year` drives the age-class calculations (HS/U18/U21U18/etc).
    If None or blank, it defaults to the current year minus 1.

    `exclude_ids` / `exclude_clubs` are comma-separated strings (or an
    iterable of strings). Any race result whose USSA id or club matches
    (club matching is case-insensitive) is dropped entirely -- no points,
    not listed in any output.

    `log` is called with each progress message (defaults to print; a GUI
    can pass something that appends to a text widget instead).
    Returns a list of (sex, pdf_path) for each PDF written (one per sex
    that had races).
    """
    global AGE_UP_YEAR
    AGE_UP_YEAR = int(age_up_year) if age_up_year not in (None, "") else default_age_up_year()
    log(f"Using Age Up Year: {AGE_UP_YEAR}")

    exclude_id_set = parse_filter_set(exclude_ids)
    exclude_club_set = {c.upper() for c in parse_filter_set(exclude_clubs)}
    if exclude_id_set:
        log(f"Excluding IDs: {', '.join(sorted(exclude_id_set))}")
    if exclude_club_set:
        log(f"Excluding Clubs: {', '.join(sorted(exclude_club_set))}")

    directory = Path(directory)
    xml_files = sorted(directory.glob("*.xml"))
    if not xml_files:
        log(f"No .xml files found in {directory}")
        return []

    races_by_sex = {"Men": [], "Women": []}
    for path in xml_files:
        sex, label, race_date, rows = parse_race_xml(path)
        if sex not in races_by_sex:
            log(f"Skipping {path.name}: unrecognized Gender")
            continue
        races_by_sex[sex].append((path.name, label, race_date, rows))

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
        for cls in CLASSES:
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
        pdf_sections = []
        for cls in CLASSES:
            log(f"Class {cls} results")
            out_name = directory / f"Results-{sex}-{cls}.csv"

            entries = []
            for a in racer_order:
                if not CLASS_FUNCS[cls](parse_year(racers[a]["year"])):
                    continue
                race_vals = []
                points = 0
                for race in RACES:
                    if (race, cls) in racers[a]:
                        pts = WC(racers[a][(race, cls)])
                        race_vals.append(str(pts))
                        points += pts
                    elif (race, "time") in racers[a]:
                        race_vals.append(str(racers[a][(race, "time")]))
                    else:
                        race_vals.append(" ")
                entries.append((a, race_vals, points))

            # standard competition ranking (ties share a rank; the
            # next distinct rank skips ahead by the number of ties)
            for a, race_vals, points in entries:
                rank = 1 + sum(1 for _, _, p in entries if p > points)
                racers[a][(cls, "rank")] = rank

            entries.sort(key=lambda e: -e[2])

            with open(out_name, "w") as fout:
                header = "RANK,USSA,LAST,FIRST,CLUB,YEAR,CLASS"
                for r in RACES:
                    header += f",{r} Pts"
                fout.write(header + ",POINTS\n")

                for a, race_vals, points in entries:
                    summary = "," + ",".join(race_vals)
                    row = (
                        f"{racers[a][(cls, 'rank')]},{a},"
                        f"{racers[a]['last']},{racers[a]['first']},"
                        f"{racers[a]['club']},{racers[a]['year']},"
                        f"{racers[a].get('class', '')}{summary},{points},"
                    )
                    fout.write(row + "\n")

            pdf_rows = []
            for a, race_vals, points in entries:
                pdf_rows.append(
                    [str(racers[a][(cls, "rank")]), a,
                     racers[a]["last"], racers[a]["first"],
                     racers[a]["club"], racers[a]["year"],
                     racers[a].get("class", "")]
                    + race_vals + [str(points)]
                )
            pdf_sections.append((cls, RACES, pdf_rows))

        pdf_sections.sort(key=lambda s: PDF_CLASS_ORDER.index(s[0]))

        date_str = datetime.date.today().strftime("%#m/%#d/%Y")
        pdf_name = directory / f"PA-Cup Standings {date_str.replace('/', '-')}-{sex}.pdf"
        write_pdf(pdf_name, sex, date_str, pdf_sections)
        log(f"Wrote {pdf_name}")
        pdf_paths.append((sex, pdf_name))

    return pdf_paths


def main():
    parser = argparse.ArgumentParser(
        description="Convert Vola XML race results into PA Cup Results CSVs/PDFs."
    )
    parser.add_argument("directory", nargs="?", default=".",
                         help="directory containing the XML race files (default: current directory)")
    parser.add_argument("--age-up-year", "-a", default="",
                         help="age-up year for class calculations; blank = current year - 1")
    parser.add_argument("--exclude-ids", default="",
                         help="comma-separated USSA ids to exclude from all results")
    parser.add_argument("--exclude-clubs", default="",
                         help="comma-separated club codes to exclude from all results")
    args = parser.parse_args()
    process_directory(Path(args.directory), age_up_year=args.age_up_year,
                       exclude_ids=args.exclude_ids, exclude_clubs=args.exclude_clubs)


if __name__ == "__main__":
    main()
