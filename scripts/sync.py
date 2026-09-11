#!/usr/bin/env python3
"""Resync everything from BGG and rebuild, in one command.

    python3 scripts/sync.py                  # the regular resync
    python3 scripts/sync.py --full           # refetch every game's details too
    python3 scripts/sync.py --no-fetch       # rebuild from the cache, no network
    python3 scripts/sync.py --no-report      # refresh the data only (used by CI)
    python3 scripts/sync.py --no-ai          # skip the `claude` enrichment

Runs the pipeline end to end:

    fetch.py     collection + any new games      (network, BGG API)
    thumbs.py    thumbnails for any new games    (network, image CDN)
    gallery.py   gallery image URLs, new games   (network, geekdo)
    enrich.py    opinion database, new games     (local `claude`, optional)
    build.py     data/games.json                 (offline)
    report.py    reports/collection.html         (offline)

enrich.py needs the `claude` CLI. If it is not installed the step reports that
and is skipped, and the report simply renders without the columns and panels
it would have fed — interaction falls back to the value derived from BGG's
mechanics, and the detail panel omits the opinion block rather than inventing
one. Pass --no-ai to skip it deliberately.

A routine resync is cheap: two collection requests plus one request per twenty
*new* games, so an unchanged collection costs three requests in total. Run it
whenever you have logged plays, changed ratings, or bought something.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, *args):
    print(f"\n--- {script} {' '.join(args)}".ljust(72, "-"))
    r = subprocess.run([sys.executable, str(HERE / script), *args])
    if r.returncode:
        raise SystemExit(f"{script} failed ({r.returncode})")


def main():
    argv = sys.argv[1:]
    full = "--full" in argv
    if "--no-fetch" not in argv:
        run("fetch.py", *(["--full"] if full else []))
        run("thumbs.py", *(["--force"] if full else []))
        run("gallery.py", *(["--force"] if full else []))
    # build first: enrich.py reads games.json, so a newly added game has to be
    # in it before it can be enriched.
    run("build.py")
    if "--no-ai" not in argv:
        run("enrich.py", *(["--force"] if full else []))
    run("build.py")
    if "--no-report" in argv:
        print("\nData refreshed. Commit data/ and push to republish.")
        return
    run("report.py", "-o", "reports/collection.html")
    print("\nDone. Open reports/collection.html, or commit and push to "
          "republish the hosted copy.")


if __name__ == "__main__":
    main()
