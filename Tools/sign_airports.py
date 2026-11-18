#!/usr/bin/env python3
"""
Sign airports.json for in-app download and write the manifest the app polls.

  python3 sign_airports.py --key ~/.config/finalcheck/airports-signing-key.pem --out dist/
  python3 sign_airports.py --print-public-key --key <key.pem>

Copies airports.json into <out>/ and writes <out>/manifest.json:
  {"effectiveDate", "expiresDate", "file": "airports.json", "size", "signature"}
`signature` is a base64 Ed25519 signature over the exact bytes of airports.json. The app checks it
against the public key compiled into ApproachCore (AirportUpdateConfig.publicKeyBase64) and refuses
anything that doesn't verify.

The key is an Ed25519 PEM private key (`openssl genpkey -algorithm ed25519`). Keep it out of the
repo; CI gets it from the AIRPORTS_SIGNING_KEY secret. Needs Python 3.8+ and OpenSSL 3.
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile


def openssl(*args, data=None):
    return subprocess.run(["openssl", *args], input=data, capture_output=True, check=True).stdout


def public_key_b64(key):
    der = openssl("pkey", "-in", key, "-pubout", "-outform", "DER")
    return base64.b64encode(der[-32:]).decode()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--key", required=True, help="Ed25519 private key (PEM)")
    p.add_argument("--airports", default=os.path.join(here, "..", "ApproachCore", "Sources", "ApproachCore",
                                                      "Resources", "airports.json"))
    p.add_argument("--out", help="folder for airports.json + manifest.json")
    p.add_argument("--print-public-key", action="store_true")
    args = p.parse_args()

    if args.print_public_key:
        print(public_key_b64(args.key))
        return
    if not args.out:
        p.error("--out is required")

    data = open(args.airports, "rb").read()
    db = json.loads(data)
    with tempfile.TemporaryDirectory() as tmp:
        src, sig = os.path.join(tmp, "in"), os.path.join(tmp, "sig")
        with open(src, "wb") as f:
            f.write(data)
        openssl("pkeyutl", "-sign", "-inkey", args.key, "-rawin", "-in", src, "-out", sig)
        signature = open(sig, "rb").read()
        # Verify with the public half before publishing anything.
        pub = os.path.join(tmp, "pub.pem")
        openssl("pkey", "-in", args.key, "-pubout", "-out", pub)
        openssl("pkeyutl", "-verify", "-pubin", "-inkey", pub, "-rawin", "-in", src, "-sigfile", sig)

    os.makedirs(args.out, exist_ok=True)
    shutil.copyfile(args.airports, os.path.join(args.out, "airports.json"))
    manifest = {
        "effectiveDate": db["effectiveDate"],
        "expiresDate": db["expiresDate"],
        "file": "airports.json",
        "size": len(data),
        "signature": base64.b64encode(signature).decode(),
    }
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Signed cycle {db['effectiveDate']} ({len(db['airports'])} airports, {len(data) // 1024} KB) "
          f"with key {public_key_b64(args.key)} -> {args.out}")


if __name__ == "__main__":
    main()
