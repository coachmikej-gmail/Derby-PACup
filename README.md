# Derby-PACup

Scores the PA Cup ski racing series from Vola/FIS race-results XML files and
produces standings as CSV and PDF. It runs as a GUI (no arguments) or as a
command-line tool (with arguments), from a single file: `Derby-PACup.pyw`.

It is a Python port of the legacy `Derby-PACup.tcl` scripts. Current version:
see `VERSION` in `Derby-PACup.pyw` and [CHANGELOG.md](CHANGELOG.md). The
sibling age-group series is scored by [Derby-Agegroup](../Derby-Agegroup/).

## What it does

Point it at a directory of Vola/FIS results XML files. Every `*.xml` file is
treated as one race. The Raceheader `Gender` attribute (`M`/`L`, or the older
`Sex` attribute some seasons use) decides whether it is a Men's or Women's
race. The XML is parsed directly; no intermediate CSV is needed.

For each (sex, class) combination that had races, it writes:

- `Results-<Sex>-<Class>.csv` (can be turned off)
- `PA-Cup Standings <date>-<Sex>-<Class>.pdf`, a gridded, paginated standings
  sheet. Up to 8 PDFs if both sexes raced and all four classes are selected.

Race columns are labeled `<Eventname> @ <Place>` from the XML and ordered by
`Racedate`, earliest first, with the most recent race next to the total
column. The date in the PDF title and filename is the **newest race date
found among the XML files**.

### Classes

Class membership is by age, where age = Age Up Year - birth year:

| Class  | Age   | Notes |
|--------|-------|-------|
| U18    | 16-17 | |
| U21    | 18-20 | |
| U21U18 | 16-20 | combined U18 + U21 |
| U19    | 16-18 | |

A racer can appear in more than one class (for example a 17-year-old is in
U18, U21U18 and U19). Racers with a missing or non-numeric birth year are
kept in the log but excluded from every class.

### Scoring

Points are scored **per race by total race time**. Within each class, racers
are ranked by that race's total time. If a racer has no total, the one valid
run time is used.

- **Use WC Points** (default): each race scores World Cup points for the
  racer's place (1st = 100, 2nd = 80, 3rd = 60, ... 30th = 1). The total
  column is the sum across races. Higher is better.
- Unchecked / `--no-wc-points`: each race scores the raw finish place
  (1st = 1, 2nd = 2, ...). Lower is better, and POINTS, RANK and sort order
  flip to match. Column headers read "... Place" and the PDF total column
  reads "TOTAL PLACE".
- Ties share a rank, and the next distinct rank skips ahead by the tie count.

### Age Up Year

When left blank, the Age Up Year defaults to **the latest race year found in
the XML files, minus 1**. It falls back to the current year minus 1 if there's
no directory or no readable race dates. A value you type always takes
precedence. The GUI shows the effective value live as `(blank = ####)` /
`(using ####)`.

## Requirements

- Python 3 with Tkinter (included with the standard Windows installer)
- `reportlab` and `pymupdf`:

```
pip install reportlab pymupdf
```

## Usage

### GUI

```
python Derby-PACup.pyw
```

Or double-click `Derby-PACup.pyw`. Choose the directory of XML files, adjust
the options, and press **Run**.

- **Select Directory...** shows each XML file with its Racedate, Eventname and
  Place.
- **Age Up Year**, **Exclude IDs**, **Exclude Clubs** (comma-separated; club
  matching is case-insensitive).
- Class checkboxes (U18, U21U18, U19, U21), **Generate CSV files**,
  **Use WC Points**.
- The **Log** tab shows progress. There is one PDF preview tab per
  (sex, class), with page navigation and an "Open in default viewer" button.
- Settings (including window position and last directory) are saved on exit to
  `%APPDATA%\Derby-PACup\Derby-PACup-GUI-config.json` and restored on the next
  launch.

### Command line

```
python Derby-PACup.pyw [directory] [options]
```

`directory` defaults to the current directory.

| Option | Meaning |
|--------|---------|
| `--age-up-year`, `-a YEAR` | Age Up Year; blank = latest race year in the XML files - 1 |
| `--exclude-ids ID,ID,...` | Drop these USSA ids from every output |
| `--exclude-clubs CLUB,...` | Drop these club codes from every output |
| `--classes U18,U19,...` | Classes to produce; blank = all four |
| `--no-csv` | Skip writing `Results-*.csv` (PDFs are always written) |
| `--no-wc-points` | Score by raw finish place instead of WC points |
| `--version` | Print the version |

Example:

```
python Derby-PACup.pyw "Y:\Derby SW\PA Cup\2024" --classes U18,U21
```

## Notes

- A corrupted, empty or encrypted XML file (e.g. one mangled by antivirus
  software) is logged and skipped; the remaining files still process.
- Output files are written into the XML directory.
- `Vola2CSV.py` is a standalone converter from a Vola XML file to the older
  per-race CSV format. `Derby-PACup.pyw` does not need it.
- Older scripts (the original GUI/XML split and the Tcl originals) are kept in
  [legacy](legacy/) for reference.

## License

MIT. See [LICENSE](LICENSE). Author: Michael Jacobson, coachmikej@gmail.com.
