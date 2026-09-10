"""Shared helpers: credential loading and repo paths."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def load_creds():
    """Read credentials.env (KEY=VALUE lines); env vars win over the file."""
    creds = {}
    f = ROOT / "credentials.env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip()
    for k in ("BGG_USERNAME", "BGG_TOKEN"):
        if os.environ.get(k):
            creds[k] = os.environ[k]
    missing = [k for k in ("BGG_USERNAME", "BGG_TOKEN") if not creds.get(k)]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}. Copy credentials.env.example to "
            f"credentials.env and fill it in."
        )
    return creds
