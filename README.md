# FinalCheck airport data

Signed towered-airport data for the FinalCheck app, rebuilt from each FAA NASR 28-day cycle.

A daily GitHub Action ([airport-data.yml](.github/workflows/airport-data.yml)) checks which cycle is in effect. When a new one is out, it downloads the FAA CSVs, builds `airports.json`, sanity-checks it and signs it with Ed25519. Then it publishes `airports.json` and `manifest.json` as a release. The app reads:

```
https://github.com/bmkuzior/FinalCheck-airports/releases/latest/download/manifest.json
```

The app installs a cycle only if:
- the cycle is already in effect,
- the signature verifies against the public key built into the app,
- the file passes the same sanity checks as the build job.

## Contents

- `Tools/fetch_nasr.py`: downloads a cycle's `APT_CSV` and `FRQ_CSV` and the EGM96 geoid grid
- `Tools/build_airports.py`: builds `airports.json` (open, towered US land airports)
- `Tools/sign_airports.py`: signs it and writes the manifest

These are copies of the scripts in the FinalCheck app repo. If you change them there, copy them here too.

## Setup

One Actions secret: `AIRPORTS_SIGNING_KEY`, an Ed25519 private key in PEM format. To publish right away, run the workflow by hand under Actions → Airport data → Run workflow.

## Data

The source is the FAA National Airspace System Resources (NASR) subscription, which is public domain. The geoid grid is EGM96 15' from PROJ. This data is advisory only: verify it against the FAA Chart Supplement and airport diagrams.
