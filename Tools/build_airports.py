#!/usr/bin/env python3
"""
Build FinalCheck's airport database from the FAA NASR 28-day subscription.

Inputs (download and unzip each cycle from
https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/):
  <nasr>/APT_CSV/   APT_BASE.csv, APT_RWY.csv, APT_RWY_END.csv   (DD_Mon_YYYY_APT_CSV.zip)
  <nasr>/FRQ_CSV/   FRQ.csv                                      (DD_Mon_YYYY_FRQ_CSV.zip)
and the EGM96 15' geoid grid egm96_15.gtx (PROJ: download.osgeo.org/proj/vdatum/egm96_15/).

  python3 build_airports.py --nasr ~/nasr --geoid ~/nasr/geoid/egm96_15.gtx

Writes ApproachCore/Sources/ApproachCore/Resources/airports.json with every open, towered
(ATCT*) US land airport: landing thresholds (displaced where published), threshold elevations,
true landing headings, tower frequency/hours, and the EGM96 geoid separation at the airport.

Python 3.8+, standard library only.
"""
import argparse
import csv
import datetime
import json
import math
import os
import struct

# Runways NASR lists that must never alert, with the reason.
EXCLUDED_RUNWAYS = {
    ("YNG", "143/323"): "military assault strip, mil use only",
}

def rows(path):
    with open(path, encoding="latin-1", newline="") as f:
        yield from csv.DictReader(f)

def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None

class Geoid:
    """Bilinear lookup in a GTX grid (big-endian: lat0, lon0, dlat, dlon, rows, cols, float32 m)."""
    def __init__(self, path):
        self.data = open(path, "rb").read()
        self.lat0, self.lon0, self.dlat, self.dlon, self.rows, self.cols = struct.unpack(">ddddii", self.data[:40])

    def _at(self, r, c):
        c %= self.cols
        off = 40 + 4 * (r * self.cols + c)
        return struct.unpack(">f", self.data[off:off + 4])[0]

    def meters(self, lat, lon):
        r = (lat - self.lat0) / self.dlat
        c = ((lon - self.lon0) % 360) / self.dlon
        r0, c0 = int(r), int(c)
        fr, fc = r - r0, c - c0
        return (self._at(r0, c0) * (1 - fr) * (1 - fc) + self._at(r0, c0 + 1) * (1 - fr) * fc
                + self._at(r0 + 1, c0) * fr * (1 - fc) + self._at(r0 + 1, c0 + 1) * fr * fc)

def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nasr", required=True, help="folder holding the unzipped APT_CSV and FRQ_CSV folders")
    p.add_argument("--geoid", required=True, help="egm96_15.gtx")
    p.add_argument("--out", default=os.path.join(here, "..", "ApproachCore", "Sources", "ApproachCore",
                                                 "Resources", "airports.json"))
    args = p.parse_args()
    geoid = Geoid(args.geoid)

    airports, cycle = {}, None
    for r in rows(os.path.join(args.nasr, "APT_CSV", "APT_BASE.csv")):
        if (r["SITE_TYPE_CODE"] != "A" or r["ARPT_STATUS"] != "O"
                or not r["TWR_TYPE_CODE"].startswith("ATCT")):
            continue
        cycle = r["EFF_DATE"]
        lat, lon = float(r["LAT_DECIMAL"]), float(r["LONG_DECIMAL"])
        airports[r["SITE_NO"]] = {
            "ident": r["ICAO_ID"] or r["ARPT_ID"],
            "faaIdent": r["ARPT_ID"],
            "name": r["ARPT_NAME"].title(),
            "towered": True,
            "geoidSeparationFeet": round(geoid.meters(lat, lon) / 0.3048, 1),
            "elevationFeet": num(r["ELEV"]),
            "fuelTypes": r["FUEL_TYPES"] or None,
            "reference": {"latitude": lat, "longitude": lon},
            "runwayEnds": [],
        }

    excluded_rwys = set()
    for r in rows(os.path.join(args.nasr, "APT_CSV", "APT_RWY.csv")):
        if r["SITE_NO"] not in airports:
            continue
        surface = r["SURFACE_TYPE_CODE"].upper()
        if (r["RWY_ID"].startswith("H") or "WATER" in surface
                or (r["ARPT_ID"], r["RWY_ID"]) in EXCLUDED_RUNWAYS):
            excluded_rwys.add((r["SITE_NO"], r["RWY_ID"]))

    ends = {}
    for r in rows(os.path.join(args.nasr, "APT_CSV", "APT_RWY_END.csv")):
        if r["SITE_NO"] not in airports or (r["SITE_NO"], r["RWY_ID"]) in excluded_rwys:
            continue
        lat, lon = num(r["LAT_DECIMAL"]), num(r["LONG_DECIMAL"])
        if lat is None or lon is None:
            continue
        ends.setdefault((r["SITE_NO"], r["RWY_ID"]), []).append(r)

    for (site, _), pair in ends.items():
        for r in pair:
            other = next((o for o in pair if o is not r), None)
            # Landing threshold: the displaced threshold when one is published.
            tlat, tlon = num(r["LAT_DISPLACED_THR_DECIMAL"]), num(r["LONG_DISPLACED_THR_DECIMAL"])
            elev = num(r["DISPLACED_THR_ELEV"])
            if tlat is None or tlon is None:
                tlat, tlon = float(r["LAT_DECIMAL"]), float(r["LONG_DECIMAL"])
            if elev is None:
                elev = num(r["RWY_END_ELEV"])
            if elev is None:
                continue
            # Heading from the runway's own geometry beats NASR's whole-degree TRUE_ALIGNMENT.
            if other is not None:
                hdg = bearing(float(r["LAT_DECIMAL"]), float(r["LONG_DECIMAL"]),
                              float(other["LAT_DECIMAL"]), float(other["LONG_DECIMAL"]))
            elif num(r["TRUE_ALIGNMENT"]) is not None:
                hdg = num(r["TRUE_ALIGNMENT"])
            else:
                continue
            apt = airports[site]
            apt["runwayEnds"].append({
                "airport": apt["ident"],
                "ident": r["RWY_END_ID"].lstrip("0") or r["RWY_END_ID"],
                "threshold": {"latitude": round(tlat, 7), "longitude": round(tlon, 7)},
                "elevationFeet": elev,
                "headingTrue": round(hdg, 1),
            })

    # Airport's own VHF frequencies by published use (first match wins, primary before secondary).
    FREQ_FIELDS = [
        ("towerFrequency", ("LCL/P",)),
        ("groundFrequency", ("GND/P", "GND/S")),
        ("clearanceFrequency", ("CD/P", "CD")),
        ("atisFrequency", ("ATIS", "D-ATIS ARR", "D-ATIS")),
        ("departureAtisFrequency", ("D-ATIS DEP",)),
        ("unicomFrequency", ("UNICOM",)),
        ("rampFrequency", ("RAMP",)),
    ]
    by_faa = {a["faaIdent"]: a for a in airports.values()}
    candidates = {}
    for r in rows(os.path.join(args.nasr, "FRQ_CSV", "FRQ.csv")):
        a = by_faa.get(r["SERVICED_FACILITY"])
        if a is None or r["FACILITY"] != r["SERVICED_FACILITY"]:
            continue
        freq = num(r["FREQ"].split("/")[0])
        if freq is None or not 118 <= freq < 137:
            continue
        use = r["FREQ_USE"].strip()
        # D-ATIS arrival/departure split lives in SECTORIZATION ("ARR" / "DEP").
        if use == "D-ATIS" and r["SECTORIZATION"].strip() in ("ARR", "DEP"):
            use = "D-ATIS " + r["SECTORIZATION"].strip()
        for field, uses in FREQ_FIELDS:
            for rank, u in enumerate(uses):
                if use == u or (u in ("ATIS", "UNICOM", "RAMP", "CD") and use.split(" ")[0] == u):
                    key = (a["faaIdent"], field)
                    if key not in candidates or rank < candidates[key][0]:
                        candidates[key] = (rank, r)
    for (faa, field), (_, r) in candidates.items():
        a = by_faa[faa]
        a[field] = r["FREQ"]
        if field == "towerFrequency":
            a["towerCall"] = (r["TOWER_OR_COMM_CALL"] or "").title()
            a["towerHours"] = r["TOWER_HRS"]

    out_airports = sorted((a for a in airports.values() if a["runwayEnds"]), key=lambda a: a["ident"])
    for a in out_airports:
        a["runwayEnds"].sort(key=lambda e: e["ident"])
    eff = datetime.datetime.strptime(cycle, "%Y/%m/%d").date()
    db = {
        "source": "FAA NASR 28-day subscription; geoid EGM96 15' (PROJ egm96_15.gtx)",
        "effectiveDate": eff.isoformat(),
        "expiresDate": (eff + datetime.timedelta(days=28)).isoformat(),
        "airports": out_airports,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(db, f, separators=(",", ":"))
    n_ends = sum(len(a["runwayEnds"]) for a in out_airports)
    print(f"NASR cycle {eff} (expires {db['expiresDate']}): {len(out_airports)} towered airports, "
          f"{n_ends} runway ends -> {os.path.relpath(args.out)} ({os.path.getsize(args.out) // 1024} KB)")

if __name__ == "__main__":
    main()
