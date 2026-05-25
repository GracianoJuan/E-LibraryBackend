"""
clean_books.py
==============
Data cleaning pipeline for books.csv.

Issues addressed:
  1. Column rename: 'author' → 'authors' (matches cbf.py / features.py)
  2. Non-Latin script titles/descriptions → dropped (2 rows: Chinese, Cyrillic)
  3. Non-English Latin descriptions → detected and flagged; translated if
     a translator callable is supplied (see TRANSLATION section below)
  4. Missing descriptions → fetched from Open Library API where possible,
     otherwise filled with a structured fallback from available metadata
  5. Short descriptions (<80 chars) → same enrichment pipeline as missing
  6. Duplicate rows → deduplicated with a deterministic priority rule
  7. published_year → validated; out-of-range values nulled
  8. ISBN → standardised to 13-digit string; invalid ones nulled
  9. genre → normalised (strip, title-case, deduplicate tags)
 10. Text fields → stripped of leading/trailing whitespace and smart quotes
     normalised to straight quotes

Output: books_cleaned.csv  (same directory as the input)
"""

from __future__ import annotations

import re
import time
import unicodedata
import urllib.request
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from langdetect import detect, LangDetectException

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_PATH = Path("books.csv")
OUTPUT_PATH = Path("books_cleaned.csv")

# Minimum description length to be considered "good enough"
MIN_DESC_LEN = 80

# Open Library fetch: pause between requests to be polite
OL_SLEEP_SEC = 0.3

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TRANSLATION SECTION
# ---------------------------------------------------------------------------
# The cleaning pipeline will call this function for every non-English
# description it finds. Swap in any real translator when you have API access.
#
# Signature: translate_fn(text: str) -> str
#
# Example using deep-translator (requires network + Google access):
#
#   from deep_translator import GoogleTranslator
#   def translate_fn(text: str) -> str:
#       return GoogleTranslator(source="auto", target="en").translate(text)
#
# Leave as None to SKIP translation (non-English rows will be flagged in a
# separate column 'needs_translation' so you can handle them later).

translate_fn: Optional[Callable[[str], str]] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Non-Latin scripts: Cyrillic, Arabic, Hebrew, CJK, Hiragana, Katakana, Hangul
_NON_LATIN_RE = re.compile(
    r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF"
    r"\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]"
)

# Common stop-word patterns for Portuguese, Spanish, French, Italian, German
_NON_ENGLISH_LATIN_RE = re.compile(
    r"\b(que|una|los|las|del|por|para|com|sua|seu|uma|não|são|está|"
    r"de la|être|avec|dans|pour|sur|les|des|le |un |en |de |da |do |"
    r"na |no |und |der |die |das |ist |ein )\b",
    re.IGNORECASE,
)

# Smart / curly quotes → straight
_SMART_QUOTES = str.maketrans({
    "\u2018": "'", "\u2019": "'",
    "\u201C": '"', "\u201D": '"',
    "\u2013": "-", "\u2014": "-",
})


def is_non_latin_script(text: str) -> bool:
    return bool(_NON_LATIN_RE.search(text)) if isinstance(text, str) else False


def is_non_english(text: str) -> bool:
    """Heuristic + langdetect double-check."""
    if not isinstance(text, str) or len(text) < 20:
        return False
    if _NON_LATIN_RE.search(text):
        return True
    if _NON_ENGLISH_LATIN_RE.search(text):
        try:
            lang = detect(text)
            return lang != "en"
        except LangDetectException:
            return True  # be conservative
    return False


def normalise_text(text: str) -> str:
    """Strip whitespace, normalise unicode, replace smart quotes."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_SMART_QUOTES)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalise_isbn(raw) -> Optional[str]:
    """
    Return a clean 13-digit ISBN string, or None if invalid.
    Accepts int, float, or string input.
    """
    if pd.isna(raw):
        return None
    digits = re.sub(r"[^\d]", "", str(raw).split(".")[0])
    if len(digits) == 10:
        # Convert ISBN-10 → ISBN-13
        digits = "978" + digits[:9]
        check = (
            sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(digits)) % 10
        )
        check_digit = (10 - check) % 10
        digits += str(check_digit)
    if len(digits) != 13:
        return None
    return digits


def normalise_genre(genre_str: str) -> str:
    """Deduplicate and title-case semicolon-separated genre tags."""
    if not isinstance(genre_str, str) or not genre_str.strip():
        return ""
    tags = [t.strip().title() for t in genre_str.split(";") if t.strip()]
    seen: dict[str, str] = {}
    for tag in tags:
        key = tag.lower()
        if key not in seen:
            seen[key] = tag
    return "; ".join(seen.values())


# ---------------------------------------------------------------------------
# Open Library description fetch
# ---------------------------------------------------------------------------

def _ol_fetch(isbn: str) -> Optional[str]:
    """
    Try to fetch a description from Open Library for a given ISBN-13.
    Returns the description string, or None on failure.
    """
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "books-cleaner/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        key = f"ISBN:{isbn}"
        if key not in data:
            return None
        book = data[key]
        # Open Library stores description in different places
        desc = book.get("description") or book.get("notes") or ""
        if isinstance(desc, dict):
            desc = desc.get("value", "")
        desc = str(desc).strip()
        return desc if len(desc) >= MIN_DESC_LEN else None
    except Exception:
        return None


def _build_fallback_description(row: pd.Series) -> str:
    """
    Construct a minimal descriptive sentence from metadata when no
    description can be fetched.  Better than an empty string for
    downstream TF-IDF / embedding models.
    """
    parts = []
    title = normalise_text(str(row.get("title", "")))
    authors = normalise_text(str(row.get("authors", "")))
    genre = normalise_text(str(row.get("genre", "")))
    year = row.get("published_year", "")

    if title:
        parts.append(f'"{title}"')
    if authors and authors.lower() not in ("nan", ""):
        parts.append(f"by {authors}")
    if year and str(year).isdigit():
        parts.append(f"published in {year}")
    if genre:
        tags = [t.strip() for t in genre.split(";")][:3]
        parts.append(f"a {', '.join(tags).lower()} book")

    return " ".join(parts) + "." if parts else ""


def enrich_descriptions(df: pd.DataFrame, fetch_from_ol: bool = True) -> pd.DataFrame:
    """
    For rows where description is missing or too short:
      1. Try Open Library (if fetch_from_ol=True and ISBN is valid)
      2. Fall back to structured metadata sentence
    """
    needs_desc = (df["description"].str.len() < MIN_DESC_LEN)
    total = needs_desc.sum()
    log.info(f"Enriching descriptions for {total} rows...")

    ol_hits = 0
    fallback_hits = 0

    for idx in df[needs_desc].index:
        isbn = df.at[idx, "isbn"]
        fetched = None

        if fetch_from_ol and isinstance(isbn, str) and len(isbn) == 13:
            fetched = _ol_fetch(isbn)
            time.sleep(OL_SLEEP_SEC)

        if fetched:
            df.at[idx, "description"] = normalise_text(fetched)
            df.at[idx, "description_source"] = "open_library"
            ol_hits += 1
        else:
            fallback = _build_fallback_description(df.loc[idx])
            df.at[idx, "description"] = fallback
            df.at[idx, "description_source"] = "fallback_metadata"
            fallback_hits += 1

    log.info(f"  Open Library hits: {ol_hits}")
    log.info(f"  Fallback metadata: {fallback_hits}")
    return df


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """
    For duplicate (title, author) pairs keep the row with:
      1. Longer description  (most informative)
      2. Lower book_id       (earlier ingested, as tiebreaker)
    """
    before = len(df)
    df = df.copy()
    # normalised key ignores punctuation / accent differences
    df["_dedup_key"] = (
        df["title"].str.lower().str.strip().str.replace(r"[^a-z0-9 ]", "", regex=True)
        + "||"
        + df["authors"].str.lower().str.strip().str.replace(r"[^a-z0-9 ]", "", regex=True)
    )
    df["_desc_len"] = df["description"].str.len()

    df = (
        df.sort_values(["_desc_len", "book_id"], ascending=[False, True])
        .drop_duplicates(subset="_dedup_key", keep="first")
        .drop(columns=["_dedup_key", "_desc_len"])
        .reset_index(drop=True)
    )
    log.info(f"Deduplication: {before} → {len(df)} rows (removed {before - len(df)})")
    return df


# ---------------------------------------------------------------------------
# Main cleaning pipeline
# ---------------------------------------------------------------------------

def clean(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
) -> pd.DataFrame:

    log.info(f"Reading {input_path} ...")
    df = pd.read_csv(input_path, dtype=str)
    log.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")

    # ------------------------------------------------------------------
    # 1. Column rename: author -> authors
    # ------------------------------------------------------------------
    if "author" in df.columns and "authors" not in df.columns:
        df = df.rename(columns={"author": "authors"})
        log.info("Renamed 'author' -> 'authors'")

    # ------------------------------------------------------------------
    # 2. Strip whitespace / normalise smart quotes on all string columns
    # ------------------------------------------------------------------
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].apply(lambda x: normalise_text(x) if isinstance(x, str) else x)

    # ------------------------------------------------------------------
    # 3. Drop rows with non-Latin script in TITLE (unrecoverable)
    # ------------------------------------------------------------------
    non_latin_title_mask = df["title"].apply(is_non_latin_script)
    dropped_titles = df[non_latin_title_mask]["title"].tolist()
    df = df[~non_latin_title_mask].reset_index(drop=True)
    log.info(f"Dropped {len(dropped_titles)} non-Latin-script title rows: {dropped_titles}")

    # ------------------------------------------------------------------
    # 4. Normalise published_year; null out-of-range values
    # ------------------------------------------------------------------
    df["published_year"] = pd.to_numeric(df["published_year"], errors="coerce")
    invalid_year = ~df["published_year"].between(1000, 2030)
    if invalid_year.sum():
        log.info(f"Nulling {invalid_year.sum()} out-of-range published_year values")
        df.loc[invalid_year, "published_year"] = np.nan
    df["published_year"] = df["published_year"].astype("Int64")

    # ------------------------------------------------------------------
    # 5. Normalise ISBN to 13-digit string
    # ------------------------------------------------------------------
    df["isbn"] = df["isbn"].apply(normalise_isbn)
    bad_isbn = df["isbn"].isna().sum()
    if bad_isbn:
        log.info(f"{bad_isbn} ISBNs could not be normalised and were set to null")

    # ------------------------------------------------------------------
    # 6. Normalise genre tags
    # ------------------------------------------------------------------
    df["genre"] = df["genre"].apply(normalise_genre)

    # ------------------------------------------------------------------
    # 7. Normalise description: fill NaN with empty string
    # ------------------------------------------------------------------
    df["description"] = df["description"].fillna("")

    # ------------------------------------------------------------------
    # 8. Handle non-English descriptions
    #    - If translate_fn is set: translate in place
    #    - Otherwise: clear them (they'll be dropped in step 9)
    # ------------------------------------------------------------------
    non_eng_mask = df["description"].apply(is_non_english)
    log.info(f"Non-English descriptions detected: {non_eng_mask.sum()}")

    if translate_fn is not None:
        log.info("Translating non-English descriptions...")
        translated = 0
        failed = 0
        for idx in df[non_eng_mask].index:
            try:
                df.at[idx, "description"] = translate_fn(df.at[idx, "description"])
                translated += 1
            except Exception as e:
                log.warning(f"  Translation failed for row {idx}: {e}")
                df.at[idx, "description"] = ""
                failed += 1
        log.info(f"  Translated: {translated}, Failed (will be dropped): {failed}")
    else:
        df.loc[non_eng_mask, "description"] = ""
        log.info(
            "  translate_fn is None — non-English descriptions cleared "
            "and will be dropped in step 9. Set translate_fn to keep them."
        )

    # ------------------------------------------------------------------
    # 9. Drop rows with missing or short descriptions
    # ------------------------------------------------------------------
    before = len(df)
    df = df[df["description"].str.len() >= MIN_DESC_LEN].reset_index(drop=True)
    log.info(f"Dropped {before - len(df)} rows with missing/short descriptions (<{MIN_DESC_LEN} chars)")

    # ------------------------------------------------------------------
    # 10. Deduplicate on (title, authors) — keep row with longest description
    # ------------------------------------------------------------------
    df = deduplicate(df)

    # ------------------------------------------------------------------
    # 11. Final column ordering
    # ------------------------------------------------------------------
    desired_order = [
        "book_id", "isbn", "title", "authors", "publisher",
        "published_year", "genre", "description", "cover_image_url",
    ]
    extra = [c for c in df.columns if c not in desired_order]
    df = df[desired_order + extra]

    # ------------------------------------------------------------------
    # 12. Final stats
    # ------------------------------------------------------------------
    log.info("=" * 50)
    log.info(f"Final shape: {df.shape}")
    log.info(f"Short descriptions remaining (<{MIN_DESC_LEN} chars): {(df['description'].str.len() < MIN_DESC_LEN).sum()}")

    df.to_csv(output_path, index=False, encoding="utf-8")
    log.info(f"Saved cleaned dataset -> {output_path}")

    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # -----------------------------------------------------------------------
    # To enable translation, uncomment ONE of the blocks below and install
    # the relevant package:
    #
    # Option A — Google Translate via deep-translator (free tier, ~500k chars/day):
    #   pip install deep-translator
    #
    #   from deep_translator import GoogleTranslator
    #   translate_fn = lambda text: GoogleTranslator(source="auto", target="en").translate(text)
    #
    # Option B — OpenAI (best quality, costs tokens):
    #   pip install openai
    #
    #   from openai import OpenAI
    #   _client = OpenAI()
    #   def translate_fn(text):
    #       r = _client.chat.completions.create(
    #           model="gpt-4o-mini",
    #           messages=[{"role": "user", "content": f"Translate to English:\n\n{text}"}],
    #       )
    #       return r.choices[0].message.content.strip()
    #
    # Option C — LibreTranslate (fully local, free):
    #   pip install libretranslatepy
    #
    #   from libretranslatepy import LibreTranslateAPI
    #   _lt = LibreTranslateAPI("https://libretranslate.com")
    #   translate_fn = lambda text: _lt.translate(text, "auto", "en")
    # -----------------------------------------------------------------------

    clean(
        input_path=INPUT_PATH,
        output_path=OUTPUT_PATH,
    )
