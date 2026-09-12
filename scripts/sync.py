#!/usr/bin/env python3
"""Resync everything from BGG and rebuild, in one command.

    python3 scripts/sync.py                  # the regular resync
    python3 scripts/sync.py --full           # refetch every game's details too
    python3 scripts/sync.py --no-fetch       # rebuild from the cache, no network
    python3 scripts/sync.py --no-report      # refresh the data only (used by CI)
    python3 scripts/sync.py --no-ai          # skip the `claude` enrichment

Runs the pipeline end to end:

    fetch.py     collection + any new games      (network, BGG API)
    plays.py     the play log, for "last played" (network, BGG API)
    thumbs.py    thumbnails for any new games    (network, image CDN)
    gallery.py   gallery image URLs, new games   (network, geekdo)
    build.py     data/games.json                 (offline)
    enrich.py    opinion database, new games     (local `claude`, optional)
    bggids.py    BGG ids for newly named games   (network, BGG API)
    build.py     again, now with the opinions    (offline)
    report.py    reports/collection.html         (offline)

The report's **Win condition**, **Point salad** and **Winning score** are not
stored anywhere: scripts/scoring.py computes them at render time from the
facts enrich.py collects, and scripts/check_scoring.py says whether those
rules still agree with the judgements in tests/expectations.txt.
scripts/check_interaction.py does the same for the interaction level against
tests/interaction_calls.txt.

The second build.py above is not optional, and it is the step that is easy to
forget when running the pieces by hand. report.py renders from the `ai`
payload build.py copies into games.json, never from data/ai/ directly, so an
enrich.py run that is not followed by a build.py run changes nothing on
screen while the checks — which do read data/ai/ — report new numbers.
report.py warns when it spots that, but only sync.py gets the order right for
free.

enrich.py needs the `claude` CLI. If it is not installed the step reports that
and is skipped, and the report simply renders without the columns and panels
it would have fed — interaction falls back to the value derived from BGG's
mechanics, and the detail panel omits the opinion block rather than inventing
one. Pass --no-ai to skip it deliberately.

A routine resync is cheap: two collection requests plus one request per twenty
*new* games, so an unchanged collection costs three requests in total. Run it
whenever you have logged plays, changed ratings, or bought something.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, *args):
    print(f"\n--- {script} {' '.join(args)}".ljust(72, "-"))
    r = subprocess.run([sys.executable, str(HERE / script), *args])
    if r.returncode:
        raise SystemExit(f"{script} failed ({r.returncode})")


def csv_only():
    """No credentials but a CSV export present: everything network is skipped.

    A BGG collection CSV carries the numbers and BGG's own summary of which
    player counts are best or recommended, which is enough for the report's
    main question. It has no mechanics, poll percentages or images, so those
    parts stay empty.
    """
    from common import ROOT
    if (ROOT / "credentials.env").exists() or os.environ.get("BGG_TOKEN"):
        return False
    return (ROOT / "data" / "collection.csv").exists()


def csv_note():
    """Say, once per sync, how to get the fields the API will not hand over."""
    from common import ROOT
    if (ROOT / "data" / "collection.csv").exists():
        return
    print("\nPrice paid and acquisition date are not in the XML API — BGG keeps\n"
          "them in the private part of a collection entry. To fill those two\n"
          "columns, open your collection on boardgamegeek.com, choose\n"
          "Download → CSV, and save the file as data/collection.csv; the next\n"
          "build picks it up. (It is gitignored: it says what you paid.)")


def main():
    argv = sys.argv[1:]
    full = "--full" in argv
    if csv_only() and "--no-fetch" not in argv:
        print("No BGG token, but data/collection.csv is here — building from "
              "the export alone.")
        argv = argv + ["--no-fetch"]
    if "--no-fetch" not in argv:
        run("fetch.py", *(["--full"] if full else []))
        run("plays.py")
        run("thumbs.py", *(["--force"] if full else []))
        run("gallery.py", *(["--force"] if full else []))
    # build first: enrich.py reads games.json, so a newly added game has to be
    # in it before it can be enriched.
    run("build.py")
    csv_note()
    if "--no-ai" not in argv:
        run("enrich.py", *(["--force"] if full else []))
        # enrich.py is what names the similar games, so their ids can only be
        # looked up afterwards. Cached, so this costs nothing for known names.
        if "--no-fetch" not in argv:
            run("bggids.py")
    run("build.py")
    if "--no-report" in argv:
        print("\nData refreshed. Commit data/ and push to republish.")
        return
    run("report.py", "-o", "reports/collection.html")
    print("\nDone. Open reports/collection.html, or commit and push to "
          "republish the hosted copy.")


if __name__ == "__main__":
    main()
