"""
Scraper Buku Indonesia
Sumber: Google Books API + Open Library API
Output : buku_indonesia.csv

Kolom  : isbn, title, author, publisher, published_year,
          description, cover_image_url, genre

Catatan genre:
- Satu buku bisa punya lebih dari satu genre
- Format multi-genre: "Fiction; Romance" (dipisah titik koma)
- Hanya buku berbahasa Indonesia yang diambil
- Baris yang ada field kosong dibuang otomatis

Cara pakai:
  pip install requests
  python scrape_buku_indonesia.py

Opsional – pasang API key Google Books supaya rate limit lebih longgar:
  set GOOGLE_BOOKS_API_KEY=AIza...   (Windows)
  export GOOGLE_BOOKS_API_KEY=AIza... (Linux/Mac)
"""

import csv
import os
import re
import time
import logging
import requests
from collections import defaultdict

# ── Konfigurasi ──────────────────────────────────────────────────────────────
OUTPUT_FILE      = "buku_indonesia.csv"
MIN_PER_GENRE    = 5          # minimal buku per genre
MAX_PER_GENRE    = 15         # maksimal buku per genre
REQUEST_DELAY    = 0.5        # jeda antar request (detik)
GOOGLE_API_KEY   = os.environ.get("GOOGLE_BOOKS_API_KEY", "")  # opsional

# Genre yang dicari beserta kata kunci pencariannya di masing-masing API
GENRE_QUERIES = {
    "Fiction":    ["fiksi indonesia novel", "sastra fiksi indonesia", "cerita fiksi indonesia"],
    "Romance":    ["novel romantis indonesia", "novel cinta indonesia", "romance indonesia"],
    "Children":   ["buku anak indonesia", "cerita anak indonesia", "dongeng indonesia anak"],
    "Religion":   ["agama islam indonesia", "buku islam indonesia", "religi indonesia"],
    "History":    ["sejarah indonesia", "sejarah nusantara", "kronik sejarah indonesia"],
    "Science":    ["sains ilmu pengetahuan indonesia", "fisika kimia biologi indonesia", "ilmu alam indonesia"],
    "Technology": ["teknologi komputer indonesia", "pemrograman indonesia", "teknologi informasi indonesia"],
    "Law":        ["hukum indonesia", "ilmu hukum pidana indonesia", "perundangan hukum indonesia"],
    "Health":     ["kesehatan medis indonesia", "ilmu kedokteran indonesia", "keperawatan gizi indonesia"],
    "Education":  ["pendidikan pembelajaran indonesia", "kurikulum pedagogik indonesia", "ilmu pendidikan indonesia"],
}

FIELDNAMES = ["isbn", "title", "author", "publisher",
              "published_year", "description", "cover_image_url", "genre"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Utilitas ─────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    """Bersihkan whitespace dan karakter aneh."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    # Hapus karakter kontrol
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return text


def extract_isbn(identifiers: list) -> str:
    """Ambil ISBN-13 atau ISBN-10 dari daftar identifier Google Books."""
    if not identifiers:
        return ""
    for id_type in ("ISBN_13", "ISBN_10"):
        for item in identifiers:
            if item.get("type") == id_type:
                return item.get("identifier", "")
    return ""


def join_genres(genres: list) -> str:
    """Gabung beberapa genre jadi string dipisah titik koma."""
    seen = []
    for g in genres:
        if g and g not in seen:
            seen.append(g)
    return "; ".join(seen)


# ── Google Books ──────────────────────────────────────────────────────────────
GOOGLE_BASE = "https://www.googleapis.com/books/v1/volumes"

def _google_request(params: dict) -> dict:
    if GOOGLE_API_KEY:
        params["key"] = GOOGLE_API_KEY
    try:
        r = requests.get(GOOGLE_BASE, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Google Books request gagal: {e}")
        return {}


def fetch_google_books(query: str, max_results: int = 40) -> list[dict]:
    """
    Ambil buku dari Google Books API.
    Kembalikan list dict mentah (belum difilter genre).
    """
    books = []
    start = 0
    per_page = min(max_results, 40)

    while len(books) < max_results:
        params = {
            "q":           query,
            "langRestrict": "id",
            "printType":   "books",
            "maxResults":  per_page,
            "startIndex":  start,
            "fields":      "totalItems,items(id,volumeInfo(title,authors,publisher,"
                           "publishedDate,description,industryIdentifiers,"
                           "imageLinks,categories,language))",
        }
        data = _google_request(params)
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            info = item.get("volumeInfo", {})
            # Filter ketat: hanya bahasa Indonesia
            if info.get("language", "") != "id":
                continue
            books.append(info)

        start += per_page
        time.sleep(REQUEST_DELAY)

        if start >= data.get("totalItems", 0):
            break

    return books


def parse_google_book(info: dict, target_genre: str) -> dict | None:
    """Ubah raw volumeInfo jadi row CSV. Return None jika ada field wajib kosong."""
    isbn = extract_isbn(info.get("industryIdentifiers", []))
    title = clean(info.get("title", ""))
    authors = "; ".join(info.get("authors", []))
    author = clean(authors)
    publisher = clean(info.get("publisher", ""))
    pub_date = clean(info.get("publishedDate", ""))
    # Ambil tahun saja
    year_match = re.search(r"\d{4}", pub_date)
    published_year = year_match.group() if year_match else ""
    description = clean(info.get("description", ""))
    # Cover image – pakai ukuran terbesar yang tersedia
    image_links = info.get("imageLinks", {})
    cover = (image_links.get("extraLarge")
             or image_links.get("large")
             or image_links.get("medium")
             or image_links.get("small")
             or image_links.get("thumbnail")
             or image_links.get("smallThumbnail")
             or "")
    cover = clean(cover).replace("http://", "https://")  # paksa HTTPS

    # Genre: gabung dari categories API + target_genre pencarian
    raw_cats = info.get("categories", [])
    genres = [target_genre]
    for cat in raw_cats:
        # Google Books kadang tulis "Fiction / Fantasy" – pisah
        for part in re.split(r"[/&,]", cat):
            g = part.strip().title()
            if g and g not in genres:
                genres.append(g)
    genre_str = join_genres(genres)

    # Validasi – semua field wajib harus ada
    row = {
        "isbn":            isbn,
        "title":           title,
        "author":          author,
        "publisher":       publisher,
        "published_year":  published_year,
        "description":     description,
        "cover_image_url": cover,
        "genre":           genre_str,
    }
    if any(not v for v in row.values()):
        return None
    return row


# ── Open Library ──────────────────────────────────────────────────────────────
OL_SEARCH  = "https://openlibrary.org/search.json"
OL_COVERS  = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
OL_WORKS   = "https://openlibrary.org{work_key}.json"


def _ol_request(url: str, params: dict = None) -> dict:
    try:
        r = requests.get(url, params=params, timeout=20,
                         headers={"User-Agent": "BukuIndonesiaScraper/1.0"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Open Library request gagal ({url}): {e}")
        return {}


def fetch_ol_books(query: str, max_results: int = 40) -> list[dict]:
    """Ambil buku dari Open Library search."""
    params = {
        "q":        query,
        "language": "ind",
        "limit":    max_results,
        "fields":   "key,title,author_name,publisher,first_publish_year,"
                    "isbn,cover_i,subject,language",
    }
    data = _ol_request(OL_SEARCH, params)
    docs = data.get("docs", [])
    # Filter: hanya yang ada bahasa Indonesia
    return [d for d in docs if "ind" in d.get("language", [])]


def _fetch_ol_description(work_key: str) -> str:
    """Ambil deskripsi dari endpoint works Open Library."""
    if not work_key:
        return ""
    data = _ol_request(OL_WORKS.format(work_key=work_key))
    desc = data.get("description", "")
    if isinstance(desc, dict):
        desc = desc.get("value", "")
    return clean(desc)


def parse_ol_book(doc: dict, target_genre: str) -> dict | None:
    """Ubah raw Open Library doc jadi row CSV."""
    # ISBN – ambil ISBN-13 dulu
    isbns = doc.get("isbn", [])
    isbn = next((i for i in isbns if len(i) == 13), "")
    if not isbn:
        isbn = next((i for i in isbns if len(i) == 10), "")
    isbn = clean(isbn)

    title = clean(doc.get("title", ""))
    authors = doc.get("author_name", [])
    author = clean("; ".join(authors))
    publishers = doc.get("publisher", [])
    publisher = clean(publishers[0]) if publishers else ""
    published_year = str(doc.get("first_publish_year", "")).strip()

    # Cover
    cover_id = doc.get("cover_i", "")
    cover = OL_COVERS.format(cover_id=cover_id) if cover_id else ""

    # Deskripsi – perlu request ke works endpoint (lebih lambat)
    work_key = doc.get("key", "")
    description = ""
    if work_key:
        description = _fetch_ol_description(work_key)
        time.sleep(REQUEST_DELAY)

    # Genre
    subjects = doc.get("subject", [])
    genres = [target_genre]
    for s in subjects[:10]:
        g = s.strip().title()
        if g and g not in genres:
            genres.append(g)
    genre_str = join_genres(genres)

    row = {
        "isbn":            isbn,
        "title":           title,
        "author":          author,
        "publisher":       publisher,
        "published_year":  published_year,
        "description":     description,
        "cover_image_url": cover,
        "genre":           genre_str,
    }
    if any(not v for v in row.values()):
        return None
    return row


# ── Dedup & merge ─────────────────────────────────────────────────────────────
def merge_by_isbn(rows: list[dict]) -> list[dict]:
    """
    Gabung baris dengan ISBN sama jadi satu baris.
    Genre di-union, field lain diambil dari baris pertama.
    """
    seen: dict[str, dict] = {}
    for row in rows:
        key = row["isbn"]
        if key in seen:
            # Merge genre
            existing_genres = set(seen[key]["genre"].split("; "))
            new_genres = set(row["genre"].split("; "))
            merged = sorted(existing_genres | new_genres)
            seen[key]["genre"] = "; ".join(merged)
        else:
            seen[key] = dict(row)
    return list(seen.values())


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("Scraper Buku Indonesia – mulai")
    log.info("=" * 60)

    all_rows: list[dict] = []
    genre_counts: dict[str, int] = defaultdict(int)

    for genre, queries in GENRE_QUERIES.items():
        log.info(f"\n[{genre}] Mulai scraping ...")
        genre_rows: list[dict] = []
        collected_isbns: set[str] = set()

        for query in queries:
            if len(genre_rows) >= MAX_PER_GENRE:
                break

            # ── Google Books ──
            log.info(f"  Google Books  ← '{query}'")
            gb_raw = fetch_google_books(query, max_results=40)
            log.info(f"    {len(gb_raw)} hasil mentah")
            for info in gb_raw:
                if len(genre_rows) >= MAX_PER_GENRE:
                    break
                row = parse_google_book(info, genre)
                if row and row["isbn"] not in collected_isbns:
                    genre_rows.append(row)
                    collected_isbns.add(row["isbn"])
            time.sleep(REQUEST_DELAY)

            # ── Open Library ──
            if len(genre_rows) < MIN_PER_GENRE:
                log.info(f"  Open Library  ← '{query}'")
                ol_raw = fetch_ol_books(query, max_results=40)
                log.info(f"    {len(ol_raw)} hasil mentah")
                for doc in ol_raw:
                    if len(genre_rows) >= MAX_PER_GENRE:
                        break
                    row = parse_ol_book(doc, genre)
                    if row and row["isbn"] not in collected_isbns:
                        genre_rows.append(row)
                        collected_isbns.add(row["isbn"])
                time.sleep(REQUEST_DELAY)

        count = len(genre_rows)
        genre_counts[genre] = count
        log.info(f"  → {count} buku valid untuk genre {genre}")

        if count < MIN_PER_GENRE:
            log.warning(f"  ⚠  Kurang dari {MIN_PER_GENRE} buku untuk genre {genre}!")

        all_rows.extend(genre_rows)

    # Dedup + merge genre
    log.info(f"\nTotal sebelum dedup : {len(all_rows)}")
    all_rows = merge_by_isbn(all_rows)
    log.info(f"Total setelah dedup : {len(all_rows)}")

    # Tulis CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    log.info(f"\nFile disimpan: {OUTPUT_FILE}")
    log.info("\nRingkasan per genre:")
    for genre, count in sorted(genre_counts.items()):
        status = "OK" if count >= MIN_PER_GENRE else "KURANG"
        log.info(f"  {genre:<12} {count:>3} buku  [{status}]")
    log.info("\nSelesai!")


if __name__ == "__main__":
    main()
