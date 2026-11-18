#!/usr/bin/env python3
"""
Download what build_airports.py needs for a NASR cycle.

  python3 fetch_nasr.py --out ~/nasr                 # cycle in effect today (UTC)
  python3 fetch_nasr.py --out ~/nasr --cycle 2026-11-26
  python3 fetch_nasr.py --print-cycle                # just print today's cycle date

Writes <out>/APT_CSV/*.csv, <out>/FRQ_CSV/*.csv and <out>/geoid/egm96_15.gtx (the geoid grid never
changes, so it is only downloaded when missing). Python 3.8+, standard library only.
"""
import argparse
import datetime
import io
import os
import sys
import urllib.request
import zipfile

# NASR cycles are 28 days apart; any known effective date anchors the sequence.
ANCHOR = datetime.date(2026, 10, 1)
CYCLE = datetime.timedelta(days=28)
CSV_URL = "https://nfdc.faa.gov/webContent/28DaySub/extra/{d:%d}_{d:%b}_{d:%Y}_{name}_CSV.zip"
GEOID_URL = "https://download.osgeo.org/proj/vdatum/egm96_15/egm96_15.gtx"
# nfdc.faa.gov answers HEAD with 503 and is picky about clients; a plain GET with a UA works.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FinalCheck-airport-builder)"}


def cycle_in_effect(today):
    return ANCHOR + CYCLE * ((today - ANCHOR) // CYCLE)


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", help="folder to download into")
    p.add_argument("--cycle", help="cycle effective date, YYYY-MM-DD (default: in effect today, UTC)")
    p.add_argument("--print-cycle", action="store_true", help="print the cycle date and exit")
    args = p.parse_args()

    if args.cycle:
        cycle = datetime.date.fromisoformat(args.cycle)
        if (cycle - ANCHOR) % CYCLE:
            sys.exit(f"{cycle} is not a NASR cycle date")
    else:
        cycle = cycle_in_effect(datetime.datetime.now(datetime.timezone.utc).date())
    if args.print_cycle:
        print(cycle.isoformat())
        return
    if not args.out:
        p.error("--out is required")

    for name in ("APT", "FRQ"):
        url = CSV_URL.format(d=cycle, name=name)
        print(f"GET {url}", flush=True)
        dest = os.path.join(args.out, f"{name}_CSV")
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(get(url))) as z:
            for member in z.namelist():
                # Flatten: the zips hold the CSVs at the root today, but don't trust paths.
                base = os.path.basename(member)
                if base.lower().endswith(".csv"):
                    with open(os.path.join(dest, base), "wb") as f:
                        f.write(z.read(member))

    geoid = os.path.join(args.out, "geoid", "egm96_15.gtx")
    if not os.path.exists(geoid):
        print(f"GET {GEOID_URL}", flush=True)
        os.makedirs(os.path.dirname(geoid), exist_ok=True)
        data = get(GEOID_URL)
        with open(geoid, "wb") as f:
            f.write(data)
    print(f"NASR cycle {cycle} ready in {args.out}")


if __name__ == "__main__":
    main()
