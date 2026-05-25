"""
scraper.py  –  Multi-source book data collector
================================================================
Sources  (in priority order for field merging):
  1. Open Library API  – best for subjects + bulk ISBN coverage
  2. Goodreads         – best for community genres + cover
  3. Amazon Books      – supplementary publisher / year data

Output fields per book (published_year filtered to YEAR_MIN..YEAR_MAX):
  title, author, publisher, published_year, description,
  cover_image_url, genre  (multi-value, consensus-based), isbn

Usage:
  python scraper.py

  # Limit total books (for testing):
  MAX_BOOKS=200 python scraper.py

  # Custom year range:
  YEAR_MIN=2023 YEAR_MAX=2026 python scraper.py
================================================================
"""

from __future__ import annotations

import csv
import html
import os
import re
import sys
import time
import unicodedata
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")

# ── runtime config ────────────────────────────────────────────────────────────
import datetime as _dt
MAX_BOOKS        = int(os.getenv("MAX_BOOKS", "0"))          # 0 = unlimited
DELAY_API        = float(os.getenv("DELAY_API",    "0.35"))  # s between API calls
DELAY_HTML       = float(os.getenv("DELAY_HTML",   "1.2"))   # s between HTML scrapes
MAX_RETRIES      = 3
CHECKPOINT_EVERY = 100    # save to disk every N new books
OL_PAGE_SIZE     = 100    # OpenLibrary docs per request
OL_QUERY_LIMIT   = 400    # max docs per OL query

# ── publication year filter ───────────────────────────────────────────────────
# Keep only books published within the last 2–5 years.
# Override via env vars: YEAR_MIN=2021 YEAR_MAX=2025 python scraper.py
_CURRENT_YEAR = _dt.date.today().year
YEAR_MIN = int(os.getenv("YEAR_MIN", str(_CURRENT_YEAR - 5)))  # default: 5 years back
YEAR_MAX = int(os.getenv("YEAR_MAX", str(_CURRENT_YEAR)))      # default: current year

# ── output ────────────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).resolve().parent
OUTPUT_CSV       = BASE_DIR / "books.csv"
CHECKPOINT_CSV   = BASE_DIR / "books_checkpoint.csv"

FIELDNAMES = [
    "book_id", "isbn", "title", "author", "publisher",
    "published_year", "description", "cover_image_url", "genre",
]

# ── search queries ────────────────────────────────────────────────────────────
QUERIES: List[str] = [
    # fiction sub-genres
    "fantasy fiction", "science fiction", "mystery thriller", "romance novel",
    "horror fiction", "historical fiction", "literary fiction", "adventure fiction",
    "young adult fiction", "children fiction",
    # nonfiction categories
    "biography memoir", "history nonfiction", "science popular",
    "self help personal development", "business leadership",
    "psychology cognitive", "philosophy ethics", "economics finance",
    "politics government", "technology computer programming",
    "health nutrition wellness", "medicine clinical",
    "mathematics statistics", "law legal",
    "travel guidebook", "cooking recipes", "art design",
    "music", "sports athletics", "religion spirituality",
    "education teaching", "nature environment ecology",
]

# ── genre taxonomy (specific → broad; order matters) ─────────────────────────
#   key   = canonical genre name stored in CSV
#   value = keyword triggers (matched in lowercased combined subject strings)
GENRE_MAP: Dict[str, List[str]] = {
    # Fiction sub-genres (specific first)
    "Fantasy":            ["fantasy", "magic", "wizard", "dragon", "sorcery", "fairy tale", "mytholog"],
    "Science Fiction":    ["science fiction", "sci-fi", "scifi", "space opera", "dystopia", "cyberpunk", "post-apocalyptic", "time travel"],
    "Horror":             ["horror", "gothic fiction", "supernatural fiction", "ghost story", "terror"],
    "Mystery":            ["mystery", "detective", "whodunit", "crime fiction", "cozy mystery"],
    "Thriller":           ["thriller", "suspense", "espionage", "spy fiction", "psychological thriller"],
    "Romance":            ["romance", "love story", "romantic fiction", "chick lit"],
    "Historical Fiction": ["historical fiction", "historical novel"],
    "Adventure":          ["adventure fiction", "adventure story", "quest fiction"],
    "Young Adult":        ["young adult", "ya fiction", "ya novel", "teen fiction"],
    "Children":           ["children", "juvenile fiction", "picture book", "middle grade", "early reader"],
    "Literary Fiction":   ["literary fiction", "literary novel", "contemporary fiction", "women's fiction"],
    # Broad fiction umbrella (matched last so sub-genres win)
    "Fiction":            ["fiction", "novel", "short stories", "short story collection"],
    # Nonfiction sub-genres
    "Biography":          ["biography", "memoir", "autobiography", "life story"],
    "History":            ["history", "historical account", "ancient history", "world war", "civil war"],
    "Self-Help":          ["self-help", "self help", "personal development", "productivity", "habit", "motivation", "mindset", "life coach"],
    "Business":           ["business", "management", "leadership", "entrepreneur", "marketing", "startup", "corporate"],
    "Economics":          ["economics", "finance", "investing", "money", "market", "stock", "financial"],
    "Psychology":         ["psychology", "mental health", "cognitive", "neuroscience", "behavior", "psychiatry"],
    "Philosophy":         ["philosophy", "ethics", "metaphysics", "logic", "existentialism", "stoicism"],
    "Politics":           ["politics", "political", "government", "democracy", "policy", "international relations"],
    "Science":            ["science", "physics", "chemistry", "biology", "astronomy", "geology", "scientific"],
    "Technology":         ["technology", "software", "computer", "artificial intelligence", "programming", "internet", "machine learning"],
    "Mathematics":        ["mathematics", "math", "algebra", "geometry", "calculus", "statistics", "probability"],
    "Medicine":           ["medicine", "clinical", "surgery", "pharmacology", "anatomy", "disease", "oncology"],
    "Health":             ["health", "wellness", "nutrition", "diet", "fitness", "exercise", "yoga"],
    "Law":                ["law", "legal", "jurisprudence", "court", "constitutional"],
    "Religion":           ["religion", "spirituality", "theology", "faith", "christian", "islam", "buddhism", "judaism", "hinduism"],
    "Education":          ["education", "teaching", "pedagogy", "learning", "academic"],
    "Nature":             ["nature", "wildlife", "botany", "zoology", "ecology", "environment", "climate", "conservation"],
    "Travel":             ["travel", "guidebook", "tourism", "journey", "exploration", "travelogue"],
    "Cooking":            ["cooking", "recipe", "culinary", "food", "baking", "gastronomy", "cuisine"],
    "Art":                ["art", "design", "painting", "photography", "illustration", "sculpture", "architecture"],
    "Music":              ["music", "song", "instrument", "jazz", "classical music", "rock", "musicology"],
    "Sports":             ["sports", "athletics", "football", "basketball", "tennis", "soccer", "cricket", "baseball"],
    # Broad nonfiction umbrella
    "Nonfiction":         ["nonfiction", "non-fiction", "essay", "true story", "true crime"],
}

# ── how many sources must agree on a genre for it to appear in output ─────────
# 1 = include if ANY source matched it  (more genres, less strict)
# 2 = include only if 2+ sources agree  (fewer genres, higher precision)
GENRE_CONSENSUS = 1


# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BookRecord:
    """Intermediate record from one source. Multiple records merge into one row."""
    source:       str
    isbn:         str
    title:        str          = ""
    author:       str          = ""
    publisher:    str          = ""
    published_year: Optional[int] = None
    description:  str          = ""
    cover_image_url: str       = ""
    raw_genres:   List[str]    = field(default_factory=list)   # raw tags/categories
    inferred_genres: List[str] = field(default_factory=list)   # after infer_genres()


# ══════════════════════════════════════════════════════════════════════════════
# Text utilities
# ══════════════════════════════════════════════════════════════════════════════

def clean(text: Optional[str]) -> str:
    """Strip HTML, decode entities, normalize whitespace, remove control chars."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("C"))
    return re.sub(r"\s+", " ", text).strip()


def year_from_string(s: str) -> Optional[int]:
    m = re.search(r"\b(1[5-9]\d{2}|20[012]\d)\b", s)
    return int(m.group(1)) if m else None


def normalize_isbn(raw: str) -> Optional[str]:
    if not raw:
        return None
    c = re.sub(r"[^0-9Xx]", "", raw).upper()
    return c if len(c) in {10, 13} else None


def pick_isbn(candidates: List[str]) -> Optional[str]:
    normed = [normalize_isbn(x) for x in candidates]
    normed = [x for x in normed if x]
    # Prefer ISBN-13 over ISBN-10
    return (next((x for x in normed if len(x) == 13), None)
            or next((x for x in normed if len(x) == 10), None))


# ══════════════════════════════════════════════════════════════════════════════
# Genre helpers
# ══════════════════════════════════════════════════════════════════════════════

def infer_genres(tags: List[str]) -> List[str]:
    """
    Given a list of raw subject/category/shelf strings from one source,
    return matching canonical genres (in taxonomy order).
    """
    combined = " ".join(tags).lower()
    matched = []
    for genre, keywords in GENRE_MAP.items():
        if any(kw in combined for kw in keywords):
            matched.append(genre)
    return matched or []


def consensus_genres(records: List[BookRecord]) -> List[str]:
    """
    Merge inferred genres from all records.
    A genre is included if it appears in >= GENRE_CONSENSUS sources.
    Result is ordered by GENRE_MAP taxonomy.
    """
    counts: Dict[str, int] = {}
    for rec in records:
        # count each genre once per source record
        for g in set(rec.inferred_genres):
            counts[g] = counts.get(g, 0) + 1

    qualified = {g for g, c in counts.items() if c >= GENRE_CONSENSUS}
    ordered   = [g for g in GENRE_MAP if g in qualified]
    return ordered or ["General"]


# ══════════════════════════════════════════════════════════════════════════════
# HTTP session
# ══════════════════════════════════════════════════════════════════════════════

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def http_get(session: requests.Session, url: str,
             params: Optional[Dict] = None,
             delay: float = DELAY_API,
             timeout: int = 25) -> Optional[requests.Response]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, timeout=timeout)
            time.sleep(delay)
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (403, 429):
                wait = delay * (attempt ** 2) * 3
                log.warning("HTTP %d – backing off %.1fs (attempt %d/%d)",
                            code, wait, attempt, MAX_RETRIES)
                time.sleep(wait)
            elif attempt < MAX_RETRIES:
                time.sleep(delay * attempt)
            else:
                log.debug("Failed: %s → %s", url, exc)
        except Exception as exc:
            if attempt < MAX_RETRIES:
                time.sleep(delay * attempt)
            else:
                log.debug("Failed: %s → %s", url, exc)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Source 2 – Open Library API
# ══════════════════════════════════════════════════════════════════════════════
_OL_SEARCH = "https://openlibrary.org/search.json"
_OL_FIELDS = ",".join([
    "key", "title", "author_name", "language",
    "publish_year", "first_publish_year",
    "isbn", "subject", "publisher",
    "first_sentence", "cover_i",
])


def _ol_is_english(doc: Dict) -> bool:
    langs = [str(l).lower() for l in doc.get("language", [])]
    if not langs:
        return True   # no lang info → assume ok
    return any(l in {"eng", "en"} or "eng" in l for l in langs)


def _ol_parse_doc(doc: Dict) -> Optional[BookRecord]:
    title = clean(doc.get("title", ""))
    if not title:
        return None
    if not _ol_is_english(doc):
        return None

    isbn = pick_isbn(doc.get("isbn", []))
    if not isbn:
        return None

    authors = [clean(a) for a in doc.get("author_name", [])[:3] if a]
    publishers = doc.get("publisher", [])
    publisher  = clean(str(publishers[0])) if publishers else ""

    # Year: prefer most recent valid year (book may have been republished)
    years = [int(y) for y in doc.get("publish_year", []) if str(y).isdigit()]
    fy = doc.get("first_publish_year")
    if fy and str(fy).isdigit():
        years.append(int(fy))
    year = max((y for y in years if YEAR_MIN <= y <= YEAR_MAX), default=None)

    # Description fallback: first_sentence
    desc = ""
    fs = doc.get("first_sentence")
    if isinstance(fs, dict):
        desc = clean(fs.get("value", ""))
    elif isinstance(fs, list) and fs:
        item = fs[0]
        desc = clean(item.get("value", "") if isinstance(item, dict) else item)
    elif isinstance(fs, str):
        desc = clean(fs)

    # Cover
    cover_id = doc.get("cover_i")
    cover    = (f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                if cover_id
                else f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg")

    subjects = [clean(s) for s in doc.get("subject", []) if s][:12]
    if year is None:
        return None   # outside YEAR_MIN..YEAR_MAX

    genres   = infer_genres(subjects)

    return BookRecord(
        source      = "openlibrary",
        isbn        = isbn,
        title       = title,
        author      = "; ".join(authors),
        publisher   = publisher,
        published_year = year,
        description = desc,
        cover_image_url = cover,
        raw_genres  = subjects,
        inferred_genres = genres,
    )


def ol_search(session: requests.Session, query: str) -> Iterator[BookRecord]:
    """Yield BookRecords from Open Library search."""
    for offset in range(0, OL_QUERY_LIMIT, OL_PAGE_SIZE):
        params = {
            "q":      query,
            "limit":  OL_PAGE_SIZE,
            "offset": offset,
            "fields": _OL_FIELDS,
        }
        r = http_get(session, _OL_SEARCH, params=params, delay=DELAY_API)
        if r is None:
            break
        data  = r.json()
        docs  = data.get("docs", [])
        total = int(data.get("numFound", 0))
        if not docs:
            break
        for doc in docs:
            rec = _ol_parse_doc(doc)
            if rec:
                yield rec
        if offset + OL_PAGE_SIZE >= min(total, OL_QUERY_LIMIT):
            break


# ══════════════════════════════════════════════════════════════════════════════
# Source 3 – Goodreads (HTML)
# ══════════════════════════════════════════════════════════════════════════════
_GR_BASE = "https://www.goodreads.com"


def _gr_book_paths(session: requests.Session, query: str,
                   max_results: int = 12) -> List[str]:
    url = f"{_GR_BASE}/search"
    r   = http_get(session, url,
                   params={"q": query, "search_type": "books"},
                   delay=DELAY_HTML)
    if r is None:
        return []
    soup  = BeautifulSoup(r.text, "html.parser")
    paths = []
    for a in soup.select("a.bookTitle")[:max_results]:
        href = a.get("href", "")
        if href:
            # strip query params
            paths.append(href.split("?")[0])
    return paths


def _gr_parse_page(session: requests.Session, path: str) -> Optional[BookRecord]:
    r = http_get(session, f"{_GR_BASE}{path}", delay=DELAY_HTML)
    if r is None:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    text = r.text

    # ── title ──
    title_el = (soup.select_one("h1[data-testid='bookTitle']")
                or soup.select_one("h1#bookTitle"))
    title = clean(title_el.get_text()) if title_el else ""
    if not title:
        return None

    # ── author ──
    author_el = (soup.select_one("span[data-testid='name']")
                 or soup.select_one("a.authorName span[itemprop='name']"))
    author = clean(author_el.get_text()) if author_el else ""

    # ── description ──
    desc_el = (soup.select_one("div[data-testid='description']")
               or soup.select_one("div#description span"))
    description = clean(desc_el.get_text()) if desc_el else ""

    # ── cover ──
    cover = ""
    img = (soup.select_one("img.ResponsiveImage")
           or soup.select_one("img#coverImage"))
    if img:
        cover = img.get("src", "") or img.get("data-src", "")

    # ── genres / shelves ──
    genre_tags: List[str] = []
    # New GR layout
    for el in soup.select("span.BookPageMetaData__genreChip"):
        genre_tags.append(el.get_text(strip=True))
    # Old GR layout
    if not genre_tags:
        for el in soup.select("a.actionLinkLite.bookPageGenreLink"):
            genre_tags.append(el.get_text(strip=True))
    genres = infer_genres(genre_tags)

    # ── publisher / year ──
    publisher, year = "", None
    pub_el = soup.select_one("div[data-testid='publicationInfo']")
    pub_text = pub_el.get_text(" ") if pub_el else ""
    if not pub_text:
        for row in soup.select("div.BookDetails .DetailsLayoutRightParagraph"):
            pub_text += " " + row.get_text()
    m = re.search(r"(?:by|Published by)\s+([^,\n]+)", pub_text, re.I)
    if m:
        publisher = clean(m.group(1))
    year = year_from_string(pub_text)

    # ── ISBN from meta / JSON-LD ──
    isbn = None
    isbn_meta = soup.select_one("meta[property='books:isbn']")
    if isbn_meta:
        isbn = normalize_isbn(isbn_meta.get("content", ""))
    if not isbn:
        m13 = re.search(r'"isbn13"\s*:\s*"(\d{13})"', text)
        if m13:
            isbn = m13.group(1)
    if not isbn:
        m10 = re.search(r'"isbn"\s*:\s*"(\d{10})"', text)
        if m10:
            isbn = normalize_isbn(m10.group(1))
    if not isbn:
        return None

    return BookRecord(
        source      = "goodreads",
        isbn        = isbn,
        title       = title,
        author      = author,
        publisher   = publisher,
        published_year = year,
        description = description,
        cover_image_url = cover,
        raw_genres  = genre_tags,
        inferred_genres = genres,
    )


def gr_search(session: requests.Session, query: str) -> Iterator[BookRecord]:
    """Yield BookRecords from Goodreads search."""
    paths = _gr_book_paths(session, query)
    for path in paths:
        rec = _gr_parse_page(session, path)
        if rec:
            yield rec


# ══════════════════════════════════════════════════════════════════════════════
# Source 4 – Amazon Books (HTML)
# ══════════════════════════════════════════════════════════════════════════════
_AZ_BASE   = "https://www.amazon.com"
_AZ_SEARCH = f"{_AZ_BASE}/s"


def _az_book_paths(session: requests.Session, query: str,
                   max_results: int = 8) -> List[str]:
    r = http_get(
        session, _AZ_SEARCH,
        params={"k": query, "i": "stripbooks", "rh": "n:283155"},
        delay=DELAY_HTML,
    )
    if r is None:
        return []
    soup  = BeautifulSoup(r.text, "html.parser")
    paths = []
    seen: Set[str] = set()
    for a in soup.select("a.a-link-normal[href*='/dp/']"):
        href = a.get("href", "")
        m    = re.search(r"(/dp/[A-Z0-9]{10})", href)
        if m:
            p = m.group(1)
            if p not in seen:
                seen.add(p)
                paths.append(p)
        if len(paths) >= max_results:
            break
    return paths


def _az_parse_page(session: requests.Session, path: str) -> Optional[BookRecord]:
    r = http_get(session, f"{_AZ_BASE}{path}", delay=DELAY_HTML)
    if r is None:
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    # ── title ──
    title_el = soup.select_one("#productTitle, #ebooksProductTitle")
    title    = clean(title_el.get_text()) if title_el else ""
    if not title:
        return None

    # ── author ──
    author = ""
    for sel in ("a.a-link-normal.contributorNameID",
                "span.author a", ".author .a-link-normal"):
        el = soup.select_one(sel)
        if el:
            author = clean(el.get_text())
            break

    # ── description ──
    desc = ""
    for sel in ("#bookDescription_feature_div noscript",
                "#bookDescription_feature_div span.a-text-normal",
                "#productDescription p",
                "#editorialReviews_feature_div .a-expander-content p"):
        el = soup.select_one(sel)
        if el:
            desc = clean(el.get_text())
            if desc:
                break

    # ── cover ──
    cover = ""
    for sel in ("#imgBlkFront", "#ebooksImgBlkFront", "#landingImage", "#main-image"):
        img = soup.select_one(sel)
        if img:
            dyn = img.get("data-a-dynamic-image", "")
            if dyn:
                # data-a-dynamic-image is a JSON dict of url→[w,h]
                m = re.search(r'"(https://[^"]+\.jpg[^"]*)"', dyn)
                if m:
                    cover = m.group(1)
            if not cover:
                cover = img.get("src", "")
            if cover:
                break

    # ── details table ──
    publisher, year, isbn = "", None, None
    for li in soup.select("#detailBullets_feature_div li, #productDetailsTable tr"):
        txt = li.get_text(" ", strip=True)
        if re.search(r"publisher", txt, re.I) and not publisher:
            # pattern: "Publisher : Penguin (January 1, 2020)"
            m = re.search(r"Publisher\s*[:\u200e\u200f]+\s*([^(;\n]+)", txt, re.I)
            if m:
                publisher = clean(m.group(1))
            if not year:
                year = year_from_string(txt)
        for pat in (r"ISBN-13\s*[:\u200e\u200f]+\s*([\d\-]{13,17})",
                    r"ISBN-10\s*[:\u200e\u200f]+\s*([\dXx\-]{9,13})"):
            m = re.search(pat, txt, re.I)
            if m:
                cand = normalize_isbn(m.group(1))
                if cand and (not isbn or len(cand) == 13):
                    isbn = cand

    if not isbn:
        return None

    # ── genres from breadcrumb ──
    genre_tags: List[str] = []
    for el in soup.select("#wayfinding-breadcrumbs_feature_div li,"
                          " #prodDetails .a-link-normal"):
        t = el.get_text(strip=True)
        if t and t.lower() not in ("books", "›", "see all"):
            genre_tags.append(t)
    genres = infer_genres(genre_tags)

    return BookRecord(
        source      = "amazon",
        isbn        = isbn,
        title       = title,
        author      = author,
        publisher   = publisher,
        published_year = year,
        description = desc,
        cover_image_url = cover,
        raw_genres  = genre_tags,
        inferred_genres = genres,
    )


def az_search(session: requests.Session, query: str) -> Iterator[BookRecord]:
    """Yield BookRecords from Amazon search."""
    paths = _az_book_paths(session, query)
    for path in paths:
        rec = _az_parse_page(session, path)
        if rec:
            yield rec


# ══════════════════════════════════════════════════════════════════════════════
# Merging
# ══════════════════════════════════════════════════════════════════════════════

def _longest(a: str, b: str) -> str:
    return a if len(a) >= len(b) else b


def merge_records(records: List[BookRecord]) -> Dict:
    """
    Merge records from multiple sources into a single canonical dict.
    Priority for each field (highest first):
      description  → longest wins
      cover        → Goodreads > OpenLibrary > Amazon
      publisher    → first non-empty
      year         → earliest plausible (first publication)
      author/title → longest/most complete
      genre        → consensus across all sources
    """
    assert records

    # Sort so OpenLibrary comes first (broadest coverage)
    priority = {"openlibrary": 0, "goodreads": 1, "amazon": 2}
    records  = sorted(records, key=lambda r: priority.get(r.source, 9))

    base = records[0]

    title       = base.title
    author      = base.author
    publisher   = base.publisher
    year        = base.published_year
    description = base.description
    cover       = base.cover_image_url

    for rec in records[1:]:
        title       = _longest(title,       rec.title)
        author      = _longest(author,      rec.author)
        publisher   = publisher or rec.publisher
        if rec.published_year:
            year = (min(year, rec.published_year) if year else rec.published_year)
        description = _longest(description, rec.description)
        cover       = cover or rec.cover_image_url

    genres = consensus_genres(records)

    return {
        "isbn":           records[0].isbn,
        "title":          title,
        "author":         author,
        "publisher":      publisher,
        "published_year": year or "",
        "description":    description,
        "cover_image_url": cover,
        "genre":          "; ".join(genres),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Persistence
# ══════════════════════════════════════════════════════════════════════════════

def save_csv(rows: List[Dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log.info("Saved %d rows → %s", len(rows), path.name)


def load_checkpoint(path: Path) -> Tuple[List[Dict], Set[str]]:
    if not path.exists():
        return [], set()
    rows, seen = [], set()
    with path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            isbn = normalize_isbn(row.get("isbn", ""))
            if isbn and isbn not in seen:
                row["isbn"] = isbn
                rows.append(row)
                seen.add(isbn)
    log.info("Checkpoint loaded: %d books", len(rows))
    return rows, seen


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline
# ══════════════════════════════════════════════════════════════════════════════

def run() -> None:
    log.info("=== Book Scraper starting ===")
    log.info("MAX_BOOKS: %s", MAX_BOOKS or "unlimited")

    session = make_session()

    final_rows, seen = load_checkpoint(CHECKPOINT_CSV)
    staged:     Dict[str, List[BookRecord]] = {}  # isbn → source records
    new_count   = 0

    def register(rec: BookRecord) -> None:
        if rec.isbn in seen:
            return
        staged.setdefault(rec.isbn, []).append(rec)

    def flush(isbn: str) -> None:
        nonlocal new_count
        if isbn in seen or isbn not in staged:
            return
        merged = merge_records(staged.pop(isbn))
        if not merged.get("title") or not merged.get("author"):
            return
        # Year filter: skip books outside the 2-5 year window
        yr = merged.get("published_year")
        if not yr or not (YEAR_MIN <= int(yr) <= YEAR_MAX):
            return
        new_count += 1
        merged["book_id"] = f"B{len(final_rows) + 1:05d}"
        final_rows.append(merged)
        seen.add(isbn)
        if new_count % CHECKPOINT_EVERY == 0:
            log.info("Progress: %d new, %d total – checkpointing…", new_count, len(final_rows))
            save_csv(final_rows, CHECKPOINT_CSV)
        if MAX_BOOKS and len(final_rows) >= MAX_BOOKS:
            raise StopIteration("MAX_BOOKS reached")

    def flush_all() -> None:
        for isbn in list(staged.keys()):
            flush(isbn)

    try:
        # ── Phase 2: Open Library (broad ISBN coverage) ──────────────────────
        log.info("── Phase 1: Open Library search ──")
        for query in QUERIES:
            log.info("  OL query: %s", query)
            for rec in ol_search(session, query):
                register(rec)
                flush(rec.isbn)

        # ── Phase 2: Goodreads (genre signal + community data) ───────────────
        log.info("── Phase 2: Goodreads search ──")
        for query in QUERIES[:20]:   # lighter – HTML scraping
            log.info("  GR query: %s", query)
            for rec in gr_search(session, query):
                register(rec)
                flush(rec.isbn)

        # ── Phase 3: Amazon (supplementary data) ─────────────────────────────
        log.info("── Phase 3: Amazon search ──")
        for query in QUERIES[:12]:   # lightest – strictest anti-scrape
            log.info("  AZ query: %s", query)
            for rec in az_search(session, query):
                register(rec)
                flush(rec.isbn)

        # ── Flush remaining staged records ───────────────────────────────────
        flush_all()

    except StopIteration as e:
        log.info("Stopping: %s", e)
        flush_all()
    except KeyboardInterrupt:
        log.info("Interrupted – flushing staged records…")
        flush_all()
    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
        flush_all()
    finally:
        save_csv(final_rows, OUTPUT_CSV)
        save_csv(final_rows, CHECKPOINT_CSV)
        _print_summary(final_rows)


def _print_summary(rows: List[Dict]) -> None:
    log.info("\n═══ Summary ═══")
    log.info("Total books : %d", len(rows))

    genre_counts: Dict[str, int] = {}
    year_counts:  Dict[str, int] = {}
    for row in rows:
        for g in str(row.get("genre", "General")).split("; "):
            g = g.strip()
            if g:
                genre_counts[g] = genre_counts.get(g, 0) + 1
        y = str(row.get("published_year", ""))
        if y:
            year_counts[y] = year_counts.get(y, 0) + 1

    print("\nGenre distribution:")
    for g, c in sorted(genre_counts.items(), key=lambda x: -x[1]):
        bar = "█" * (c * 30 // max(genre_counts.values()))
        print(f"  {g:<22} {c:>5}  {bar}")

    print("\nTop publication years:")
    for y, c in sorted(year_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {y}: {c}")


if __name__ == "__main__":
    run()
