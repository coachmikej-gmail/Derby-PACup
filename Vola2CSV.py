"""Python port of Vola2CSVr3.tcl (non-GUI).

Author: Michael Jacobson, coachmikej@gmail.com
License: MIT (see LICENSE file in this directory)

Converts a Vola/FIS AL_race results XML file into the CSV format used
throughout this directory's PA Cup pipeline:
    Bib,FIS,Last,First,Sex,Nation,Year,Club,NAT,Run1,Run2,Total,Points,

Unlike the original Tcl tool (and unlike an earlier version of this
script), each field is looked up by its XML tag name rather than by
position -- some seasons' Vola exports put Clubname before Yearofbirth
(or the reverse), and some records omit fields entirely, which corrupts
a purely positional read. One side effect: every output row now always
has all 13 columns (blank where a field like Total/Points doesn't apply,
e.g. a DNS), rather than the original's variable-length rows.

Usage:
    python Vola2CSV.py <input.xml> [output.csv]

If output.csv is omitted, it defaults to <input>.csv next to the input file.
"""

import sys
import xml.etree.ElementTree as ET

HEADER = "Bib,FIS,Last,First,Sex,Nation,Year,Club,NAT,Run1,Run2,Total,Points,"

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
    return [fis, last, first, sex, nation, year, club, nat_code]


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

    return [as_seconds(get("Timerun1")), as_seconds(get("Timerun2")),
            as_seconds(get("Totaltime")), as_seconds(get("Racepoints"))]


def convert(xml_path, csv_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    lines = [HEADER]
    for path in RACER_PATHS:
        for racer in root.findall(path):
            bib = elem_text(racer.find("Bib"))
            competitor = racer.find("Competitor")
            al_result = racer.find("AL_result")

            row = [bib] + competitor_fields(competitor) + result_fields(al_result)
            lines.append(",".join(row) + ",")

    with open(csv_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    if len(sys.argv) < 2:
        print("usage: python Vola2CSV.py <input.xml> [output.csv]")
        sys.exit(1)

    xml_path = sys.argv[1]
    if len(sys.argv) >= 3:
        csv_path = sys.argv[2]
    else:
        csv_path = xml_path.rsplit(".", 1)[0] + ".csv"

    convert(xml_path, csv_path)
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
