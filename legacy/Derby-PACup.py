"""Python port of Derby-PACup.tcl (Y:\\Derby SW\\PA Cup\\2024)

Author: Michael Jacobson, coachmikej@gmail.com
License: MIT (see LICENSE file in this directory)

The source .tcl hardcodes the age-up-year via:
    proc AgeUpYear {} {2023}
which is actually broken Tcl (missing "return" -- raises "invalid command
name 2023" whenever called). The pre-existing Results-*.csv files in this
directory are only consistent with an intended fixed age-up-year of 2023
(e.g. birth year 2006 -> age 17 -> class U18), so that's what's used here.
"""

AGE_UP_YEAR = 2023


def HS(year):
    age = AGE_UP_YEAR - year
    return 15 < age < 19


def U21U18(year):
    age = AGE_UP_YEAR - year
    return 15 < age < 21


def U21U18U16(year):
    age = AGE_UP_YEAR - year
    return 13 < age < 21


def U21(year):
    age = AGE_UP_YEAR - year
    return 17 < age < 21


def U18(year):
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
RACES = ["Tussey-SL1", "Tussey-SL2", "Blue-SG3", "Blue-GS4", "Blue-SL5"]
SEXS = ["Men", "Women"]

# race-file columns: bib,fis,last,first,sex,nation,year,club,id,r1,r2,total,points,rank,order


def process_race_file(path, race, racers, racer_order):
    with open(path) as f:
        lines = f.read().splitlines()

    for i, line in enumerate(lines):
        if i == 0:
            continue  # header row
        fields = line.split(",")
        if not line:
            continue
        fields = (fields + [""] * 15)[:15]
        (bib, _fis, last, first, sex, nation, year, club, id_,
         r1, r2, total, points, rank, order) = fields
        id_ = id_[1:]

        if id_ not in racers:
            racers[id_] = {
                "last": last,
                "first": first,
                "sex": sex,
                "nation": nation,
                "year": year,
                "club": club,
                "id": id_,
            }
            racers[id_]["class"] = class_name(int(racers[id_]["year"]))
            racer_order.append(id_)

        print(f"{id_}. {racers[id_]['first']} {racers[id_]['last']}")

        if total != "":
            racers[id_][(race, "time")] = total
        elif is_number(r1):
            racers[id_][(race, "time")] = r2
        else:
            racers[id_][(race, "time")] = r1


def main():
    for sex in SEXS:
        racers = {}
        racer_order = []

        for race in RACES:
            filename = f"{race}-{sex}.csv"
            print(f"Processing {sex} Race Data File ... {filename}")
            process_race_file(filename, race, racers, racer_order)

        # determine overall place per class
        for cls in CLASSES:
            for race in RACES:
                print(f"Processing {sex} Race {cls} ... {race}")
                race_times = []
                race_ids = []
                for a in racer_order:
                    t = racers[a].get((race, "time"))
                    if t is not None and is_number(t):
                        if CLASS_FUNCS[cls](int(racers[a]["year"])):
                            race_times.append(t)
                            race_ids.append(a)

                if race_times:
                    sorted_times = sorted(race_times, key=float)
                    for id_ in race_ids:
                        t = racers[id_][(race, "time")]
                        rank = sorted_times.index(t) + 1
                        racers[id_][(race, cls)] = rank

        # print out the results
        for cls in CLASSES:
            print(f"Class {cls} results")
            out_name = f"Results-{sex}-{cls}.csv"
            with open(out_name, "w") as fout:
                header = "RANK,USSA,LAST,FIRST,CLUB,YEAR,CLASS"
                for r in RACES:
                    header += "," + " ".join(r.split("-")) + " Pts"
                fout.write(header + ",POINTS\n")

                entries = []
                for a in racer_order:
                    if not CLASS_FUNCS[cls](int(racers[a]["year"])):
                        continue
                    summary = ""
                    points = 0
                    for race in RACES:
                        if (race, cls) in racers[a]:
                            pts = WC(racers[a][(race, cls)])
                            summary += f",{pts}"
                            points += pts
                        elif (race, "time") in racers[a]:
                            summary += f",{racers[a][(race, 'time')]}"
                        else:
                            summary += ", "
                    entries.append((a, summary, points))

                # standard competition ranking (ties share a rank; the
                # next distinct rank skips ahead by the number of ties)
                for a, summary, points in entries:
                    rank = 1 + sum(1 for _, _, p in entries if p > points)
                    racers[a][(cls, "rank")] = rank

                entries.sort(key=lambda e: -e[2])

                for a, summary, points in entries:
                    row = (
                        f"{racers[a][(cls, 'rank')]},{a},"
                        f"{racers[a]['last']},{racers[a]['first']},"
                        f"{racers[a]['club']},{racers[a]['year']},"
                        f"{racers[a].get('class', '')}{summary},{points},"
                    )
                    fout.write(row + "\n")


if __name__ == "__main__":
    main()
