from __future__ import annotations

import os

os.environ.setdefault("TARGET_LANGUAGE", "id")

import scraper as base

base.TARGET_LANGUAGE = "id"
base.OUTPUT_CSV = base.BASE_DIR / "books_id.csv"
base.CHECKPOINT_CSV = base.BASE_DIR / "books_id_checkpoint.csv"
base.BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# If books_id.csv / books_id_checkpoint.csv already exist from an earlier run
# (e.g. before the language filtering was correct), load_checkpoint() will
# load those old rows and carry them forward forever, even if the current
# run's filtering is correct. Set FRESH_START=1 to wipe them before running.
if os.getenv("FRESH_START") == "1":
    for _path in (base.OUTPUT_CSV, base.CHECKPOINT_CSV):
        if _path.exists():
            _path.unlink()
            print(f"[FRESH_START] removed stale file: {_path.name}")


if __name__ == "__main__":
    base.run()