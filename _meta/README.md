# `_meta/` — notes for whoever picks this up next

This folder is for agents and maintainers, not for users of the report. The
user-facing documentation is the repository `README.md`; `SKILL.md` is the
short "how do I answer a question about this collection" card. Everything
here is the reasoning *behind* the code: why things are built the way they
are, what was tried and abandoned, and what is still open.

Read in this order for a cold start:

1. **This file** — the shape of the project and the rules that are not
   negotiable.
2. **`ARCHITECTURE.md`** — the pipeline, what each script owns, and the one
   ordering mistake that costs an hour if you make it.
3. **`LEARNINGS.md`** — the traps. Most of them look like bugs in the data
   and are actually bugs in how it was measured.
4. **`DECISIONS.md`** — choices with their rationale, including the ones that
   were reverted.
5. **`TODO.md`** — what is unfinished, with costs where they are known.
6. **`PLAN-thematic-ameritrash.md`** — one unfinished piece of work in
   detail; it is the worked example of how a new axis gets added.

## What this project is

A cached copy of one person's BoardGameGeek collection, plus a single
self-contained HTML report of it. The report is one file: no build step for
the reader, no server, no network calls when it opens. It is published to
GitHub Pages by the workflow in `.github/workflows/`.

The repository is **public**. Everything committed here is world-readable and
permanent.

## Rules that are not negotiable

**Private collection data never leaves the machine.** BoardGameGeek keeps
part of a collection entry private: the price paid and its currency, the
acquisition date, who it was acquired from, the inventory location, private
comments. None of it may reach a committed file or the published page. The
architecture enforces this rather than relying on care: the private source is
a CSV export that is gitignored (`data/collection.csv`), and `report.py`
merges it at *render* time, so `data/games.json` never carries it and a build
without the file simply shows blanks. If you add a field, ask which side of
that line it is on before you add it to the build.

Public fields from the same collection — the owner's own ratings, play counts
— are fine; they are already visible on the owner's public profile.

**Be sparing with the BoardGameGeek API.** The token is a courtesy, not a
licence to fan out. Batch requests up to the endpoint's limit, space them
deliberately, and skip anything already cached so a re-run costs no requests.
Only `fetch.py`, `thumbs.py`, `gallery.py` and `bggids.py` touch the network;
everything else is offline and instant.

**Secrets stay out of the repository.** The real token lives in
`credentials.env`, which is gitignored; `credentials.env.example` shows the
shape with a fake value. A secret that is ever committed is compromised and
must be rotated, not just removed.

**Nothing from outside this repository belongs in it.** Only files this
project generates or a person deliberately adds. Before committing, read the
whole of `git status`, not just the files you edited — a stray artefact from
another tool landing in `docs/` and being swept in by `git add -A` has
happened, and in a public repository that is a leak, not an untidiness.

**No committed file knows where it is checked out.** Not the README, not
`SKILL.md`, not a script, not a workflow. The scripts resolve their paths from
`__file__` (`common.py` sets `ROOT`), so a checkout works anywhere under any
name; documentation refers to "this repository" and to paths relative to its
root. Anything machine-specific — absolute paths, one person's directory
layout — belongs in a gitignored file, which today means
`.claude/settings.local.json` and `credentials.env`. Someone cloning this on
another machine should never read a sentence about somebody else's setup, and
a folder that gets renamed or moved should break nothing that is committed.

**Do not hardcode the owner's own judgements.** The derived columns must come
from general rules over facts. When a rule disagrees with the owner, the
disagreement is recorded as a test case in `tests/`, and the rule is either
improved or the disagreement is documented — it is never special-cased by
game name.

## Running an agent in this repository, and keeping it here

Start the session **in this directory**, not in a parent. Two layers then
confine it, and both are configured in `.claude/`:

- `.claude/settings.json` is committed and machine-independent: it asks
  before any push, and refuses to read the two files that hold private data
  (`credentials.env` and `data/collection.csv`) even though they are also
  gitignored.
- `.claude/settings.local.json` is **gitignored** because it contains
  absolute paths for one machine. It denies reads of the sibling directories
  beside this one and of the usual credential locations, then allows this
  repository back in, and it limits writes to this repository alone.

Both layers were tested rather than assumed. From a session started here, a
file in a sibling directory is refused by the permission layer when read with
the file tools, and refused by the kernel with `Operation not permitted` when
read with `cat` from a shell.

**What this does not do.** It is a guard against accidents, not a security
boundary. Paths outside the home directory stay readable because the
toolchain needs them. An agent that can write to `.claude/settings.local.json`
can weaken the file, and a session started with permission checks bypassed
loses the first layer, though the kernel sandbox still applies to shell
commands. Treat it as making the common mistake impossible, not as a jail.

If you set this up on another machine, copy the local file's shape and
replace the absolute paths; nothing else needs changing.
