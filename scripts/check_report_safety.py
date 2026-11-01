#!/usr/bin/env python3
"""Render a page from hostile text and check none of it escapes into markup.

Usage:  python3 scripts/check_report_safety.py

Game names, comments, descriptions and opinion records are written by other
people, so report.py must treat them as text. This copies one real game into
a scratch data directory (MYBG_ROOT), rewrites its text fields with attacks,
renders it with --owner and an empty --bgg-user, and checks:

- the page has exactly the template's <script> elements, so "</script>" in
  a string did not end one early;
- a name spelling a placeholder ("/*__DATA__*/") is shown, not filled;
- a javascript: source link is dropped;
- the title shows --owner, escaped, and there is no link to BGG.

Exits non-zero on the first failure.
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATTACK = '</script><script>alert(1)</script><!--'
PLACEHOLDER = "/*__DATA__*/ __HEADLINE__ <!--__ROWS__-->"


def hostile_game():
    games = json.loads((HERE.parent / "data" / "games.json").read_text())
    g = next(g for g in games
             if (g.get("ai") or {}).get("confidence") in ("high", "medium")
             and not g["is_expansion"])
    g = json.loads(json.dumps(g))
    g["name"] = PLACEHOLDER
    g["comment"] = ATTACK
    g["description"] = ATTACK
    g["designers"] = [ATTACK]
    g["ai"]["summary"] = ATTACK
    g["ai"]["sources"] = ["javascript:alert(1)", "https://example.com/review"]
    return g


def main():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "data").mkdir()
        game = hostile_game()
        (Path(tmp) / "data" / "games.json").write_text(json.dumps([game]))
        out = Path(tmp) / "page.html"
        res = subprocess.run([sys.executable, str(HERE / "report.py"),
                              "--link-thumbs", f"--owner={ATTACK}",
                              "--bgg-user=", "-o", str(out)],
                             env={**os.environ, "MYBG_ROOT": tmp})
        if res.returncode:
            sys.exit("FAIL: report.py could not render the hostile game")
        html = out.read_text(encoding="utf-8")

    tpl = (HERE / "report_template.html").read_text(encoding="utf-8")
    failures = []
    if html.count("<script") != tpl.count("<script"):
        failures.append(f"{html.count('<script')} <script> tags, the template "
                        f"has {tpl.count('<script')}")
    if "alert(1)</script>" in html:
        failures.append("an attack string reached the page unescaped")
    # Filled, the name would carry a second copy of the game's record.
    if html.count('{"id":"%s",' % game["id"]) != 1:
        failures.append("a placeholder in a game name was filled with data")
    if "javascript:alert" in html:
        failures.append("a javascript: link survived")
    if "https://example.com/review" not in html:
        failures.append("the https source was dropped too")
    if "boardgamegeek.com/collection/user/" in html:
        failures.append("--bgg-user= still links to BGG")
    if not re.search(r"<h1[^>]*>.*&lt;/script&gt;", html, re.S):
        failures.append("--owner is not in the title, escaped")
    for f in failures:
        print("FAIL:", f)
    if failures:
        sys.exit(1)
    print("ok: hostile text stays text")


if __name__ == "__main__":
    main()
