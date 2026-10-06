# Changelog

All notable changes to Derby-PACup. The same history is kept in the
`Changelog:` section of the `Derby-PACup.pyw` module docstring; the version
number is the `VERSION` constant in that file.

## 1.6.0

- Blank **Age Up Year** now defaults to the latest race year found among the
  directory's XML files, minus 1, instead of the current year minus 1. It
  falls back to the current year minus 1 if there's no directory or no
  readable race dates. A value typed into the field (or passed with
  `--age-up-year`) still takes precedence.
- The GUI's "(blank = ####)" hint now updates when the directory changes, not
  just when the field is edited.
- PDF titles and filenames now use the newest race date found among the
  directory's XML files instead of today's date.

## 1.5.0

- Added a selectable **U21** class (age 18-20). The scoring function already
  existed but was never wired into the GUI/CLI-selectable class list.
- Reordered the class checkboxes, PDF/tab generation order, and CLI
  `--classes` help text to U18, U21, U21U18, U19.

## 1.4.0

- Added a **Use WC Points** checkbox (checked by default). When unchecked,
  each race is scored by the racer's raw finish place (1st = 1, 2nd = 2, ...)
  instead of WC points, and "best" flips accordingly: POINTS and RANK then
  favor the lowest total instead of the highest.
- Per-race column headers switch between "... Pts" and "... Place" to match,
  and the PDF's total column relabels from "WC POINTS" to "TOTAL PLACE".
- Added the matching CLI `--no-wc-points` flag. The checkbox state is saved to
  and restored from the JSON config.

## 1.3.0

- A single unreadable XML file (corrupted, empty, or encrypted by antivirus
  software) no longer crashes the whole run. It's logged and skipped, and
  every other file still processes normally.
- Fixed a data bug where the same athlete could be split into two different
  ids and never combine into one row. `NAT_code` isn't consistently formatted
  even within one season -- some race files prefix it with a nationality
  letter (`E6480922`), others don't (`6480922`) -- and unconditionally
  stripping the first character either way corrupted the no-prefix case by
  chopping off a real digit. The leading character is now only stripped when
  it's actually a letter.

## 1.2.0

- Added a **Generate CSV files** checkbox (checked by default) so
  `Results-<Sex>-<Class>.csv` writing can be turned off. PDFs are always
  written regardless.
- Added the matching CLI `--no-csv` flag. The checkbox state is saved to and
  restored from the JSON config.

## 1.1.0

- Added class-selection checkboxes so the user can choose which classes
  (HS/U21U18/U18 at the time, since renamed to U19/U21U18/U18) to include in
  a run.
- Output changed from one combined PDF per sex (all classes as sections) to
  one PDF per (sex, class) combination. The GUI now shows one tab per
  (sex, class) PDF instead of one per sex.
- Added the CLI `--classes` flag. Selected classes are saved to and restored
  from the JSON config.

## 1.0.0

- Initial release: single-file merge of `Derby-PACup-XML.py` and
  `Derby-PACup-GUI.pyw`, runnable as either a GUI (no args) or a CLI (with
  args).
- GUI: directory picker, XML file tree (shows each file's
  Racedate/Eventname/Place), Age Up Year field, Exclude IDs / Exclude Clubs
  filters (comma-separated, club matching case-insensitive), Run button, Log
  tab, one PDF preview tab per sex with page navigation. Settings saved to a
  JSON config file under `%APPDATA%\Derby-PACup\` and restored on the next
  launch.
- CLI: `--age-up-year`, `--exclude-ids`, `--exclude-clubs`. Version number,
  About dialog, `--version` flag.

## Unreleased

- CLI `--age-up-year` help text now describes the 1.6.0 default (latest race
  year in the XML files minus 1).
