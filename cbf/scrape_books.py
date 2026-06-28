"""
Book Scraper - Google Books, Open Library, Perpusnas, Gramedia
Khusus buku berbahasa INDONESIA
Output: books.csv
Rules:
- Hanya buku berbahasa Indonesia
- Genre dalam bahasa Inggris, bisa lebih dari satu (dipisah ;)
- Semua field wajib terisi (tidak ada filter minimum per genre)
- Hasil dari SEMUA sumber digabung
"""

import requests
import csv
import time
import re
import json
import sys
from collections import defaultdict
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
OUTPUT_FILE = "books2.csv"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9",
}
FIELDNAMES = ["title", "authors", "publisher", "published_year",
              "description", "genre", "cover_url", "source"]

# ─────────────────────────────────────────────
# GENRE MAPPING
# ─────────────────────────────────────────────
GENRE_MAP = {
    "fiksi": "fiction", "fiksi ilmiah": "science fiction",
    "fiksi sejarah": "historical fiction", "nonfiksi": "non-fiction",
    "non fiksi": "non-fiction", "non-fiksi": "non-fiction",
    "sejarah": "history", "biografi": "biography",
    "otobiografi": "biography", "memoar": "biography",
    "pendidikan": "education", "agama": "religion", "islam": "religion",
    "kristen": "religion", "filsafat": "philosophy", "hukum": "law",
    "ekonomi": "economics", "bisnis": "business", "manajemen": "business",
    "keuangan": "economics", "sains": "science",
    "ilmu pengetahuan": "science", "matematika": "science",
    "fisika": "science", "kimia": "science", "biologi": "science",
    "teknologi": "technology", "komputer": "technology",
    "informatika": "technology", "seni": "art", "budaya": "culture",
    "sastra": "literature", "psikologi": "psychology",
    "kesehatan": "health", "kedokteran": "health",
    "masak": "cooking", "kuliner": "cooking", "resep": "cooking",
    "perjalanan": "travel", "wisata": "travel",
    "anak": "children", "anak-anak": "children", "cerita anak": "children",
    "remaja": "young adult", "komik": "comics", "manga": "manga",
    "puisi": "poetry", "drama": "drama", "horor": "horror",
    "misteri": "mystery", "detektif": "mystery",
    "romantis": "romance", "roman": "romance", "cinta": "romance",
    "petualangan": "adventure", "fantasi": "fantasy", "thriller": "thriller",
    "motivasi": "self-help", "pengembangan diri": "self-help",
    "inspirasi": "self-help", "sosial": "culture", "politik": "history",
    "novel": "fiction", "cerpen": "fiction",
    # English aliases
    "sci-fi": "science fiction", "sci fi": "science fiction",
    "science fiction": "science fiction", "young adult": "young adult",
    "ya fiction": "young adult", "juvenile fiction": "children",
    "juvenile nonfiction": "children", "juvenile literature": "children",
    "detective": "mystery", "mystery & detective": "mystery",
    "love stories": "romance", "love story": "romance",
    "historical fiction": "historical fiction",
    "graphic novels": "comics", "graphic novel": "comics",
    "self-help": "self-help", "self help": "self-help",
    "personal development": "self-help", "computers": "technology",
    "computer science": "technology", "medicine": "health",
    "medical": "health", "cooking": "cooking", "food": "cooking",
    "travel": "travel", "geography": "travel",
    "poetry": "poetry", "poems": "poetry",
    "short stories": "fiction", "essays": "non-fiction",
    "fiction": "fiction", "non-fiction": "non-fiction",
    "nonfiction": "non-fiction", "fantasy": "fantasy",
    "mystery": "mystery", "thriller": "thriller", "romance": "romance",
    "horror": "horror", "biography": "biography", "history": "history",
    "education": "education", "science": "science",
    "technology": "technology", "philosophy": "philosophy",
    "religion": "religion", "law": "law", "economics": "economics",
    "business": "business", "psychology": "psychology", "health": "health",
    "art": "art", "literature": "literature", "drama": "drama",
    "comics": "comics", "adventure": "adventure", "culture": "culture",
    "children": "children",
}

VALID_GENRES = set(GENRE_MAP.values())

# Query → genre hint (untuk inferensi jika API tidak beri genre)
QUERY_GENRE_HINT = {
    "novel fiksi indonesia": "fiction",
    "novel sejarah indonesia": "historical fiction",
    "novel romance indonesia": "romance",
    "buku anak indonesia": "children",
    "buku remaja indonesia": "young adult",
    "buku biografi indonesia": "biography",
    "buku pendidikan indonesia": "education",
    "buku agama islam indonesia": "religion",
    "buku psikologi indonesia": "psychology",
    "buku bisnis indonesia": "business",
    "buku kesehatan indonesia": "health",
    "buku masak indonesia": "cooking",
    "buku teknologi indonesia": "technology",
    "buku filsafat indonesia": "philosophy",
    "buku hukum indonesia": "law",
    "buku ekonomi indonesia": "economics",
    "buku sains indonesia": "science",
    "puisi indonesia": "poetry",
    "buku motivasi indonesia": "self-help",
    "buku sejarah indonesia": "history",
    "cerpen indonesia": "fiction",
    "fantasi indonesia": "fantasy",
    "horor indonesia": "horror",
    "misteri indonesia": "mystery",
    "thriller indonesia": "thriller",
    "fiksi": "fiction", "novel": "fiction", "sejarah": "history",
    "pendidikan": "education", "anak": "children", "biografi": "biography",
    "hukum": "law", "ekonomi": "economics", "agama": "religion",
    "sains": "science", "teknologi": "technology", "psikologi": "psychology",
    "kesehatan": "health", "filsafat": "philosophy", "seni": "art",
    "sastra": "literature", "puisi": "poetry", "drama": "drama",
    "horor": "horror", "misteri": "mystery", "romantis": "romance",
    "petualangan": "adventure", "fantasi": "fantasy", "thriller": "thriller",
    "motivasi": "self-help", "fiksi ilmiah": "science fiction",
    "non-fiksi": "non-fiction", "remaja": "young adult", "komik": "comics",
    "bisnis": "business", "masak": "cooking", "wisata": "travel",
    "kuliner": "cooking",
}


def normalize_genres(raw_genres: list, query_hint: str = "") -> str:
    result = set()
    for g in raw_genres:
        if not g:
            continue
        g_lower = str(g).lower().strip()
        if g_lower in GENRE_MAP:
            result.add(GENRE_MAP[g_lower])
        elif g_lower in VALID_GENRES:
            result.add(g_lower)
        else:
            for key, val in GENRE_MAP.items():
                if key in g_lower or g_lower in key:
                    result.add(val)
                    break
    # Fallback: pakai hint dari query
    if not result and query_hint:
        hint = QUERY_GENRE_HINT.get(query_hint.lower(), "")
        if hint:
            result.add(hint)
    return ";".join(sorted(result)) if result else ""


def clean_text(text) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    text = re.sub(r"<[^>]+>", "", text)
    return text


def is_complete(book: dict) -> bool:
    """Semua field wajib harus terisi."""
    for field in FIELDNAMES:
        if field == "source":
            continue
        if not book.get(field, "").strip():
            return False
    return True


# ─────────────────────────────────────────────
# 1. GOOGLE BOOKS
# ─────────────────────────────────────────────
GOOGLE_BOOKS_QUERIES = [
    "novel fiksi indonesia", "novel sejarah indonesia",
    "novel romance indonesia", "buku anak indonesia",
    "buku remaja indonesia", "buku biografi indonesia",
    "buku pendidikan indonesia", "buku agama islam indonesia",
    "buku psikologi indonesia", "buku bisnis indonesia",
    "buku kesehatan indonesia", "buku masak indonesia",
    "buku teknologi indonesia", "buku filsafat indonesia",
    "buku hukum indonesia", "buku ekonomi indonesia",
    "buku sains indonesia", "puisi indonesia",
    "buku motivasi indonesia", "buku sejarah indonesia",
    "cerpen indonesia", "fantasi indonesia", "horor indonesia",
    "misteri indonesia", "thriller indonesia",
]


def scrape_google_books(max_per_query: int = 40) -> list:
    print("\n[Google Books] Mulai scraping...")
    # FIX: inisialisasi list lokal, bukan referensi global
    result = []
    seen_ids = set()

    for query in GOOGLE_BOOKS_QUERIES:
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": query,
            "maxResults": max_per_query,
            "printType": "books",
            "langRestrict": "id",
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [Google Books] Error '{query}': {e}")
            time.sleep(1)
            continue

        for item in data.get("items", []):
            book_id = item.get("id", "")
            if book_id in seen_ids:
                continue
            seen_ids.add(book_id)

            vi = item.get("volumeInfo", {})
            lang = vi.get("language", "id")
            if lang and lang != "id":
                continue

            title       = clean_text(vi.get("title", ""))
            authors     = "; ".join(vi.get("authors", []))
            publisher   = clean_text(vi.get("publisher", ""))
            pub_year    = str(vi.get("publishedDate", ""))[:4]
            description = clean_text(vi.get("description", ""))
            raw_genres  = vi.get("categories", [])
            cover_url   = (
                vi.get("imageLinks", {}).get("thumbnail") or
                vi.get("imageLinks", {}).get("smallThumbnail") or ""
            )
            cover_url = cover_url.replace("http://", "https://")
            genre = normalize_genres(raw_genres, query_hint=query)

            book = {
                "title": title, "authors": authors,
                "publisher": publisher, "published_year": pub_year,
                "description": description, "genre": genre,
                "cover_url": cover_url, "source": "Google Books",
            }
            if is_complete(book):
                result.append(book)

        print(f"  [Google Books] '{query}' → subtotal: {len(result)}")
        time.sleep(0.4)

    print(f"[Google Books] Selesai: {len(result)} buku")
    return result   # ← return eksplisit list lokal


# ─────────────────────────────────────────────
# 2. OPEN LIBRARY
# ─────────────────────────────────────────────
OL_QUERIES = [
    "fiksi indonesia", "novel indonesia", "sejarah indonesia",
    "romance indonesia", "anak indonesia", "remaja indonesia",
    "biografi indonesia", "pendidikan indonesia", "agama indonesia",
    "psikologi indonesia", "bisnis indonesia", "kesehatan indonesia",
    "masak indonesia", "teknologi indonesia", "filsafat indonesia",
    "hukum indonesia", "ekonomi indonesia", "sains indonesia",
    "puisi indonesia", "motivasi indonesia", "cerpen indonesia",
    "fantasi indonesia", "horor indonesia", "misteri indonesia",
    "thriller indonesia",
]


def get_ol_description(work_key: str) -> str:
    try:
        url = f"https://openlibrary.org{work_key}.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        desc = data.get("description", "")
        if isinstance(desc, dict):
            desc = desc.get("value", "")
        return clean_text(str(desc))
    except Exception:
        return ""


def scrape_open_library(max_per_query: int = 30) -> list:
    print("\n[Open Library] Mulai scraping...")
    result = []   # FIX: list lokal
    seen_keys = set()

    for query in OL_QUERIES:
        url = "https://openlibrary.org/search.json"
        params = {
            "q": query,
            "limit": max_per_query,
            "fields": "key,title,author_name,publisher,first_publish_year,subject,cover_i,language",
            "language": "ind",
        }
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [Open Library] Error '{query}': {e}")
            time.sleep(1)
            continue

        for doc in data.get("docs", []):
            work_key = doc.get("key", "")
            if work_key in seen_keys:
                continue

            langs = doc.get("language", [])
            if langs and "ind" not in langs and "id" not in langs:
                continue

            seen_keys.add(work_key)

            title      = clean_text(doc.get("title", ""))
            authors    = "; ".join(doc.get("author_name", []))
            publishers = doc.get("publisher", [])
            publisher  = clean_text(publishers[0]) if publishers else ""
            pub_year   = str(doc.get("first_publish_year", ""))
            subjects   = doc.get("subject", [])[:10]
            cover_id   = doc.get("cover_i")
            cover_url  = (
                f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                if cover_id else ""
            )
            genre = normalize_genres(subjects, query_hint=query)

            # Deskripsi: fetch dari works endpoint
            description = ""
            if work_key:
                description = get_ol_description(work_key)
                time.sleep(0.2)

            book = {
                "title": title, "authors": authors,
                "publisher": publisher, "published_year": pub_year,
                "description": description, "genre": genre,
                "cover_url": cover_url, "source": "Open Library",
            }
            if is_complete(book):
                result.append(book)

        print(f"  [Open Library] '{query}' → subtotal: {len(result)}")
        time.sleep(0.5)

    print(f"[Open Library] Selesai: {len(result)} buku")
    return result   # ← return eksplisit


# ─────────────────────────────────────────────
# 3. PERPUSNAS
# ─────────────────────────────────────────────
PERPUSNAS_CATEGORIES = [
    "fiksi", "novel", "sejarah", "pendidikan", "anak",
    "biografi", "hukum", "ekonomi", "agama", "sains",
    "teknologi", "psikologi", "kesehatan", "filsafat", "seni",
    "sastra", "puisi", "drama", "horor", "misteri",
    "romantis", "petualangan", "fantasi", "thriller", "motivasi",
]


def scrape_perpusnas(max_pages: int = 5) -> list:
    print("\n[Perpusnas] Mulai scraping...")
    result = []   # FIX: list lokal
    seen_titles = set()
    base_url = "https://opac.perpusnas.go.id"

    for category in PERPUSNAS_CATEGORIES:
        for page in range(1, max_pages + 1):
            start_row = (page - 1) * 20
            try:
                resp = requests.get(
                    f"{base_url}/index.aspx",
                    params={
                        "SearchKey": category,
                        "SearchType": "subject",
                        "StartRow": start_row,
                    },
                    headers=HEADERS, timeout=20,
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                print(f"  [Perpusnas] Error '{category}' page {page}: {e}")
                break

            # Coba berbagai selector
            rows = (
                soup.select("table.table-striped tr") or
                soup.select(".result-item") or
                soup.select("div.biblio-info") or
                soup.select(".item-result") or
                soup.select("tr.odd, tr.even")
            )
            if not rows:
                print(f"  [Perpusnas] Tidak ada hasil '{category}' page {page}")
                break

            found_in_page = 0
            for row in rows:
                title_el = (
                    row.select_one("a.titleField") or
                    row.select_one(".title a") or
                    row.select_one("td:nth-child(2) a") or
                    row.select_one("a[href*='DetailOpac']")
                )
                if not title_el:
                    continue

                title = clean_text(title_el.get_text())
                if not title or title in seen_titles:
                    continue

                detail_url = title_el.get("href", "")
                if detail_url and not detail_url.startswith("http"):
                    detail_url = base_url + "/" + detail_url.lstrip("/")

                authors = publisher = pub_year = description = cover_url = ""

                if detail_url:
                    try:
                        dresp = requests.get(detail_url, headers=HEADERS, timeout=15)
                        dresp.raise_for_status()
                        dsoup = BeautifulSoup(dresp.text, "html.parser")

                        def get_field(label: str) -> str:
                            el = dsoup.find(string=re.compile(label, re.I))
                            if el and el.parent:
                                sib = el.parent.find_next_sibling()
                                if sib:
                                    return clean_text(sib.get_text())
                            # Coba td sebelah
                            td = dsoup.find("td", string=re.compile(label, re.I))
                            if td:
                                nxt = td.find_next_sibling("td")
                                if nxt:
                                    return clean_text(nxt.get_text())
                            return ""

                        authors     = get_field(r"Pengarang|Author|Penulis")
                        publisher   = get_field(r"Penerbit|Publisher|Imprint")
                        pub_year    = get_field(r"Tahun Terbit|Year|Tahun")[:4]
                        description = get_field(r"Abstrak|Abstract|Deskripsi|Sinopsis|Catatan|Ringkasan")
                        lang_field  = get_field(r"Bahasa|Language").lower()

                        # Skip buku bukan Indonesia
                        if lang_field and "indonesia" not in lang_field and lang_field not in ("ind", "id", ""):
                            seen_titles.add(title)  # tetap tandai agar tidak re-fetch
                            time.sleep(0.2)
                            continue

                        img = (
                            dsoup.select_one("img.cover") or
                            dsoup.select_one("img[src*='cover']") or
                            dsoup.select_one("img[src*='Cover']")
                        )
                        if img:
                            src = img.get("src", "")
                            if src and not src.startswith("http"):
                                src = base_url + "/" + src.lstrip("/")
                            cover_url = src

                        time.sleep(0.3)
                    except Exception as ex:
                        print(f"    [Perpusnas] Gagal fetch detail: {ex}")

                seen_titles.add(title)
                genre = normalize_genres([category], query_hint=category)

                book = {
                    "title": title, "authors": authors,
                    "publisher": publisher, "published_year": pub_year,
                    "description": description, "genre": genre,
                    "cover_url": cover_url, "source": "Perpusnas",
                }
                if is_complete(book):
                    result.append(book)
                    found_in_page += 1

            print(f"  [Perpusnas] '{category}' page {page} +{found_in_page} → subtotal: {len(result)}")
            time.sleep(0.5)

    print(f"[Perpusnas] Selesai: {len(result)} buku")
    return result   # ← return eksplisit


# ─────────────────────────────────────────────
# 4. GRAMEDIA
# ─────────────────────────────────────────────
GRAMEDIA_CATEGORIES = [
    "fiksi", "non-fiksi", "anak", "remaja", "novel",
    "sejarah", "biografi", "sains", "teknologi", "bisnis",
    "psikologi", "agama", "hukum", "seni", "masak",
    "kesehatan", "filsafat", "komik", "puisi", "thriller",
    "horor", "misteri", "romantis", "petualangan", "fantasi",
    "motivasi", "pendidikan", "ekonomi", "kuliner", "wisata",
]


def _gramedia_parse_detail(html: str, category: str) -> dict:
    """
    Parse halaman detail produk Gramedia.
    Strategi utama: __NEXT_DATA__ JSON (embedded, paling reliable).
    Fallback: data-testid selectors (stable, jarang berubah).
    """
    soup = BeautifulSoup(html, "html.parser")
    title = authors = publisher = pub_year = description = cover_url = genre = ""

    # ── STRATEGI 1: __NEXT_DATA__ JSON ──────────────────────────────
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd:
        try:
            nd_data = json.loads(nd.string or "{}")
            meta = (nd_data.get("props", {})
                          .get("pageProps", {})
                          .get("productDetailMeta", {}))

            title       = clean_text(meta.get("title", ""))
            description = clean_text(meta.get("description", ""))
            authors     = clean_text(meta.get("author", ""))

            # Cover: ambil image pertama dari array
            images = meta.get("image", [])
            if images:
                img_url = images[0].get("image", "")
                if img_url:
                    cover_url = ("https://cdn.gramedia.com/" +
                                 img_url.split("cdn.gramedia.com/")[-1]
                                 if "cdn.gramedia.com" in img_url else img_url)

            # Kategori dari nested category tree → genre
            raw_genres = [category]
            cat = meta.get("category", {})
            while cat:
                raw_genres.append(cat.get("title", ""))
                cat = cat.get("subcategory")
            genre = normalize_genres(raw_genres, query_hint=category)

        except Exception as e:
            pass  # fallback ke selector

    # ── STRATEGI 2: data-testid selectors ───────────────────────────
    if not title:
        el = soup.select_one('h1[data-testid="productDetailTitle"]')
        title = clean_text(el.get_text()) if el else ""

    if not authors:
        el = soup.select_one('a[data-testid="productDetailAuthor"]')
        authors = clean_text(el.get_text()) if el else ""

    if not description:
        el = soup.select_one('[data-testid="productDetailDescriptionContainer"]')
        description = clean_text(el.get_text()) if el else ""

    if not cover_url:
        el = soup.select_one('img[data-testid="productDetailImage#0"]')
        cover_url = el.get("src", "") if el else ""

    # Spec table: Penerbit, Tanggal Terbit, Bahasa
    # Format: <div data-testid="productDetailSpecificationItem#N">
    #           <div data-testid="...Label">Penerbit</div>
    #           <div data-testid="...Value">...</div>
    #         </div>
    specs = {}
    for item in soup.select('[data-testid^="productDetailSpecificationItem"]'):
        label_el = item.select_one('[data-testid="productDetailSpecificationItemLabel"]')
        value_el = item.select_one('[data-testid="productDetailSpecificationItemValue"]')
        if label_el and value_el:
            specs[clean_text(label_el.get_text()).lower()] = clean_text(value_el.get_text())

    if not publisher:
        publisher = specs.get("penerbit", "")
    if not pub_year:
        raw_date = specs.get("tanggal terbit", "")
        m = re.search(r"\d{4}", raw_date)
        pub_year = m.group() if m else ""

    # Filter bahasa Indonesia
    lang = specs.get("bahasa", "").lower()
    if lang and "indonesia" not in lang and lang not in ("", "ind", "id"):
        return {}  # bukan buku Indonesia

    # Genre dari breadcrumb jika belum ada
    if not genre:
        crumbs = soup.select('[data-testid^="productDetailBreadcrumbsCategory"] a')
        raw_genres = [category] + [c.get_text() for c in crumbs]
        genre = normalize_genres(raw_genres, query_hint=category)

    return {
        "title": title, "authors": authors,
        "publisher": publisher, "published_year": pub_year,
        "description": description, "genre": genre,
        "cover_url": cover_url, "source": "Gramedia",
    }


def _gramedia_get_product_urls(soup: BeautifulSoup, base_url: str) -> list:
    """
    Ekstrak URL produk dari halaman listing/search Gramedia.
    Gramedia adalah Next.js SSR — link produk ada di <a href="/products/...">
    """
    urls = []
    seen = set()

    # Selector utama: semua link yang mengandung /products/
    for a in soup.select('a[href*="/products/"]'):
        href = a.get("href", "")
        if not href:
            continue
        # Pastikan ini link produk buku, bukan halaman lain
        if href.count("/") < 2:
            continue
        if not href.startswith("http"):
            href = base_url + href
        # Deduplikasi
        key = href.split("?")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            urls.append(key)

    return urls


def scrape_gramedia(max_pages: int = 4) -> list:
    """
    Scraping Gramedia.com menggunakan:
    - Halaman kategori buku: /categories/buku/{slug}
    - Halaman search: /search?q={keyword}
    - Detail produk: /products/{slug}
    - Parse via __NEXT_DATA__ JSON + data-testid selectors
    """
    print("\n[Gramedia] Mulai scraping...")
    result = []
    seen_urls = set()
    base_url = "https://www.gramedia.com"

    # Mapping kategori → slug kategori Gramedia yang valid
    GRAMEDIA_CATEGORY_SLUGS = [
        # (query_keyword, category_slug)
        ("novel",       "buku/fiksi/novel"),
        ("fiksi",       "buku/fiksi"),
        ("non-fiksi",   "buku/nonfiksi"),
        ("anak",        "buku/nonfiksi-anak-remaja"),
        ("remaja",      "buku/fiksi-anak-remaja"),
        ("sains",       "buku/nonfiksi-anak-remaja/sains-2"),
        ("sejarah",     "buku/nonfiksi/sejarah"),
        ("biografi",    "buku/nonfiksi/biografi"),
        ("agama",       "buku/nonfiksi/agama"),
        ("bisnis",      "buku/nonfiksi/bisnis-ekonomi"),
        ("teknologi",   "buku/nonfiksi/teknologi"),
        ("psikologi",   "buku/nonfiksi/psikologi"),
        ("kesehatan",   "buku/nonfiksi/kesehatan"),
        ("pendidikan",  "buku/nonfiksi/pendidikan"),
        ("hukum",       "buku/nonfiksi/hukum"),
        ("ekonomi",     "buku/nonfiksi/ekonomi"),
        ("filsafat",    "buku/nonfiksi/filsafat"),
        ("masak",       "buku/nonfiksi/masakan-minuman"),
        ("wisata",      "buku/nonfiksi/travel"),
        ("motivasi",    "buku/nonfiksi/motivasi-inspirasi"),
        ("komik",       "buku/komik-manga/komik"),
        ("manga",       "buku/komik-manga/manga"),
        ("horor",       "buku/fiksi/horor"),
        ("misteri",     "buku/fiksi/misteri-thriller"),
        ("romantis",    "buku/fiksi/romance"),
        ("fantasi",     "buku/fiksi/fantasi-fiksi-ilmiah"),
        ("thriller",    "buku/fiksi/misteri-thriller"),
        ("seni",        "buku/nonfiksi/seni-budaya"),
        ("puisi",       "buku/fiksi/puisi-drama"),
    ]

    for category, slug in GRAMEDIA_CATEGORY_SLUGS:
        for page in range(1, max_pages + 1):
            detail_urls = []

            # ── Coba halaman kategori ──────────────────────────────
            try:
                cat_url = f"{base_url}/categories/{slug}"
                resp = requests.get(
                    cat_url,
                    params={"page": page},
                    headers=HEADERS, timeout=20,
                )
                resp.raise_for_status()
                csoup = BeautifulSoup(resp.text, "html.parser")
                detail_urls = _gramedia_get_product_urls(csoup, base_url)
            except Exception as e:
                pass

            # ── Fallback: search ───────────────────────────────────
            if not detail_urls:
                try:
                    resp = requests.get(
                        f"{base_url}/search",
                        params={"q": category, "page": page, "type": "buku"},
                        headers=HEADERS, timeout=20,
                    )
                    resp.raise_for_status()
                    ssoup = BeautifulSoup(resp.text, "html.parser")
                    detail_urls = _gramedia_get_product_urls(ssoup, base_url)
                except Exception as e:
                    print(f"  [Gramedia] Error '{category}' page {page}: {e}")

            if not detail_urls:
                break  # tidak ada hasil, skip ke kategori berikutnya

            found_in_page = 0
            for detail_url in detail_urls:
                # Normalisasi URL
                detail_url = detail_url.split("?")[0].rstrip("/")
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)

                try:
                    dresp = requests.get(detail_url, headers=HEADERS, timeout=15)
                    dresp.raise_for_status()

                    book = _gramedia_parse_detail(dresp.text, category)
                    if book and is_complete(book):
                        result.append(book)
                        found_in_page += 1

                    time.sleep(0.4)

                except Exception as e:
                    print(f"    [Gramedia] Skip {detail_url}: {e}")
                    continue

            print(f"  [Gramedia] '{category}' page {page} +{found_in_page} → subtotal: {len(result)}")
            time.sleep(0.5)

    print(f"[Gramedia] Selesai: {len(result)} buku")
    return result


# ─────────────────────────────────────────────
# DEDUPLICATE
# ─────────────────────────────────────────────
def deduplicate(books: list) -> list:
    seen   = set()
    result = []
    for book in books:
        key = (
            re.sub(r"\s+", " ", book["title"].lower().strip()),
            re.sub(r"\s+", " ", book["authors"].lower().strip()),
        )
        if key not in seen:
            seen.add(key)
            result.append(book)
    return result


# ─────────────────────────────────────────────
# MAIN — gabung semua sumber
# ─────────────────────────────────────────────
def main():
    print("=" * 65)
    print("BOOK SCRAPER — Buku Berbahasa Indonesia")
    print("Sumber: Google Books | Open Library | Perpusnas | Gramedia")
    print("=" * 65)

    # FIX: akumulasi eksplisit dari tiap fungsi yang return list
    sources = sys.argv[1:] if len(sys.argv) > 1 else [
        "google", "openlibrary", "perpusnas", "gramedia"]

    # google_books   = scrape_google_books()    if "google"      in sources else []
    # open_library   = scrape_open_library()    if "openlibrary" in sources else []
    # perpusnas      = scrape_perpusnas()       if "perpusnas"   in sources else []
    gramedia       = scrape_gramedia()        if "gramedia"    in sources else []

    # Gabungkan — bug lama: pakai += pada variable yang salah
    all_books = gramedia

    print(f"\n[Subtotal per sumber]")
    # print(f"  Google Books : {len(google_books)}")
    # print(f"  Open Library : {len(open_library)}")
    # print(f"  Perpusnas    : {len(perpusnas)}")
    print(f"  Gramedia     : {len(gramedia)}")
    print(f"  Total mentah : {len(all_books)}")

    all_books = deduplicate(all_books)
    print(f"  Setelah dedup: {len(all_books)}")

    if not all_books:
        print("\n[WARNING] Tidak ada buku yang lolos. CSV tidak dibuat.")
        return

    # Tulis CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_books)

    print(f"\n[SELESAI] {len(all_books)} buku ditulis ke '{OUTPUT_FILE}'")

    # Summary genre
    genre_counts = defaultdict(int)
    for b in all_books:
        for g in b["genre"].split(";"):
            g = g.strip()
            if g:
                genre_counts[g] += 1
    print("\n[Summary genre:]")
    for g, c in sorted(genre_counts.items(), key=lambda x: -x[1]):
        print(f"  {g}: {c}")


if __name__ == "__main__":
    main()
