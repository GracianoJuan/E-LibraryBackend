import csv
import html
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests


OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
REQUEST_DELAY_SECONDS = 0.3
QUERY_RESULT_LIMIT = 1000
PAGE_SIZE = 100
CHECKPOINT_EVERY = 500
MAX_REQUEST_RETRIES = 3
OPENLIBRARY_FIELDS = ",".join(
    [
        "key",
        "title",
        "author_name",
        "language",
        "publish_year",
        "first_publish_year",
        "isbn",
        "subject",
        "publisher",
        "first_sentence",
        "number_of_pages_median",
        "edition_count",
        "ratings_average",
        "ratings_count",
        "want_to_read_count",
    ]
)


BROAD_QUERIES = [
    "fiction",
    "nonfiction",
    "novel",
    "history",
    "science",
    "biography",
    "psychology",
    "business",
    "technology",
    "philosophy",
    "economics",
    "health",
    "politics",
    "art",
    "religion",
    "education",
    "nature",
    "travel",
    "cooking",
    "sports",
    "music",
    "mathematics",
    "medicine",
    "law",
    "environment",
]


GENRE_KEYWORDS = {
    "Fiction": ["fiction", "novel", "literary", "story"],
    "Nonfiction": ["nonfiction", "non-fiction", "essay"],
    "Science": ["science", "physics", "chemistry", "biology", "astronomy"],
    "History": ["history", "historical", "ancient", "civilization"],
    "Biography": ["biography", "memoir", "autobiography"],
    "Psychology": ["psychology", "mental", "mindfulness"],
    "Business": ["business", "management", "leadership", "entrepreneur"],
    "Technology": ["technology", "software", "computer", "ai", "programming"],
    "Philosophy": ["philosophy", "ethics", "metaphysics"],
    "Economics": ["economics", "finance", "market", "money"],
    "Health": ["health", "wellness", "medical", "nutrition"],
    "Politics": ["politics", "government", "policy", "democracy"],
    "Art": ["art", "design", "painting", "photography"],
    "Religion": ["religion", "spiritual", "theology", "faith"],
    "Education": ["education", "teaching", "learning", "pedagogy"],
    "Nature": ["nature", "ecology", "wildlife", "earth"],
    "Travel": ["travel", "tourism", "guidebook"],
    "Cooking": ["cooking", "recipe", "culinary", "food"],
    "Sports": ["sports", "athletics", "fitness"],
    "Music": ["music", "song", "instrument"],
    "Mathematics": ["mathematics", "math", "algebra", "geometry", "calculus"],
    "Medicine": ["medicine", "clinical", "medical"],
    "Law": ["law", "legal", "jurisprudence"],
    "Environment": ["environment", "climate", "sustainability"],
    "Self-Help": ["self-help", "personal development", "productivity", "habit"],
    "Children": ["children", "juvenile", "young readers"],
}


def clean_text(text: Optional[str]) -> str:
    """Clean text by removing HTML entities, normalizing unicode, and fixing whitespace."""
    if not text:
        return ""
    
    # Decode HTML entities
    text = html.unescape(text)
    
    # Remove control characters and normalize unicode
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith('C'))
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def normalize_isbn(raw: str) -> Optional[str]:
    if not raw:
        return None
    candidate = re.sub(r"[^0-9Xx]", "", raw).upper()
    if len(candidate) in {10, 13}:
        return candidate
    return None


def choose_isbn(isbn_list: Iterable[str]) -> Optional[str]:
    normalized = [normalize_isbn(x) for x in isbn_list if normalize_isbn(x)]
    isbn13 = next((x for x in normalized if len(x) == 13), None)
    if isbn13:
        return isbn13
    return next((x for x in normalized if len(x) == 10), None)


def infer_genre(subjects: List[str]) -> str:
    joined = " ".join(subjects).lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        if any(keyword in joined for keyword in keywords):
            return genre
    return "General"


def is_english(doc: Dict[str, Any]) -> bool:
    language_values = doc.get("language", [])
    if not language_values:
        return False
    normalized = [str(item).lower() for item in language_values]
    
    # Check if language field indicates English
    is_lang_english = any(item in {"eng", "en", "/languages/eng"} or "eng" in item for item in normalized)
    if not is_lang_english:
        return False
    
    # Additional check: verify title doesn't have too many non-ASCII characters
    title = str(doc.get("title", "")).strip()
    if title:
        non_ascii = sum(1 for c in title if ord(c) > 127)
        if non_ascii / len(title) > 0.3:  # More than 30% non-ASCII
            return False
    
    return True


def parse_publish_year(doc: Dict[str, Any]) -> Optional[int]:
    years = [int(y) for y in doc.get("publish_year", []) if str(y).isdigit()]
    first_publish_year = doc.get("first_publish_year")
    if first_publish_year is not None and str(first_publish_year).isdigit():
        years.append(int(first_publish_year))
    valid = [year for year in years if year >= 2020]
    if not valid:
        return None
    return max(valid)


def fetch_google_description(session: requests.Session, isbn: str, api_key: Optional[str]) -> str:
    params = {
        "q": f"isbn:{isbn}",
        "maxResults": 1,
    }
    if api_key:
        params["key"] = api_key
    try:
        response = session.get(GOOGLE_BOOKS_URL, params=params, timeout=20)
        time.sleep(REQUEST_DELAY_SECONDS)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])
        if not items:
            return ""
        volume = items[0].get("volumeInfo", {})
        description = volume.get("description", "")
        # Remove HTML tags and clean text
        description = re.sub(r"<[^>]+>", " ", description).strip()
        description = clean_text(description)
        return description
    except Exception:
        return ""


def extract_openlibrary_first_sentence(doc: Dict[str, Any]) -> str:
    value = doc.get("first_sentence")
    if isinstance(value, dict):
        text = str(value.get("value", "")).strip()
    elif isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            text = str(first.get("value", "")).strip()
        else:
            text = str(first).strip()
    elif isinstance(value, str):
        text = value.strip()
    else:
        return ""
    
    return clean_text(text)


def to_book_row(
    doc: Dict[str, Any],
    session: requests.Session,
    api_key: Optional[str],
) -> Optional[Dict[str, Any]]:
    title = clean_text(doc.get("title", ""))
    authors = [clean_text(a) for a in doc.get("author_name", [])[:3]]
    if not title or not authors:
        return None

    if not is_english(doc):
        return None

    publish_year = parse_publish_year(doc)
    if publish_year is None:
        return None

    isbn = choose_isbn(doc.get("isbn", []))
    if not isbn:
        return None

    subjects = [clean_text(s) for s in doc.get("subject", []) if clean_text(s)][:8]
    genre = infer_genre(subjects)
    publisher = ""
    publishers = doc.get("publisher", [])
    if publishers:
        publisher = clean_text(str(publishers[0]))

    description = ""
    if api_key:
        description = fetch_google_description(session, isbn, api_key)
    if not description:
        description = extract_openlibrary_first_sentence(doc)

    row = {
        "book_id": "",
        "title": title,
        "authors": "; ".join(authors),
        "publisher": publisher,
        "publish_year": publish_year,
        "isbn": isbn,
        "genre": genre,
        "subjects": "; ".join(subjects),
        "description": description,
        "pages": int(doc.get("number_of_pages_median") or 0),
        "edition_count": int(doc.get("edition_count") or 0),
        "ratings_avg": float(doc.get("ratings_average") or 0.0),
        "ratings_count": int(doc.get("ratings_count") or 0),
        "want_to_read_count": int(doc.get("want_to_read_count") or 0),
        "language": "English",
        "image_url": f"https://images-na.ssl-images-amazon.com/images/P/{isbn}.jpg",
        "cover_url_openlibrary": f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg",
        "openlibrary_link": f"https://openlibrary.org{doc.get('key', '')}",
    }
    return row


def build_query_plan() -> List[Tuple[str, Dict[str, Any]]]:
    plan: List[Tuple[str, Dict[str, Any]]] = []
    for query in BROAD_QUERIES:
        plan.append((f"broad:{query}", {"q": query}))

    for letter in "abcdefghijklmnopqrstuvwxyz":
        plan.append((f"title_prefix:{letter}", {"title": f"{letter}*"}))

    return plan


def save_rows(rows: List[Dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "book_id",
        "title",
        "authors",
        "publisher",
        "publish_year",
        "isbn",
        "genre",
        "subjects",
        "description",
        "pages",
        "edition_count",
        "ratings_avg",
        "ratings_count",
        "want_to_read_count",
        "language",
        "image_url",
        "cover_url_openlibrary",
        "openlibrary_link",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            row["book_id"] = f"B{index:04d}"
            writer.writerow(row)


def load_checkpoint(path: Path) -> Tuple[List[Dict[str, Any]], Set[str]]:
    if not path.exists():
        return [], set()

    rows: List[Dict[str, Any]] = []
    seen_isbns: Set[str] = set()

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            isbn = normalize_isbn(row.get("isbn", ""))
            if not isbn or isbn in seen_isbns:
                continue
            row["isbn"] = isbn
            rows.append(row)
            seen_isbns.add(isbn)

    print(f"Loaded checkpoint: {len(rows)} books from {path.name}")
    return rows, seen_isbns


def print_final_summary(rows: List[Dict[str, Any]]) -> None:
    print("\n=== Final Summary ===")
    print(f"Total books: {len(rows)}")

    genre_counts: Dict[str, int] = {}
    year_counts: Dict[int, int] = {}

    for row in rows:
        genre = str(row.get("genre", "General"))
        year = int(row.get("publish_year") or 0)
        genre_counts[genre] = genre_counts.get(genre, 0) + 1
        year_counts[year] = year_counts.get(year, 0) + 1

    print("\nGenre breakdown:")
    for genre, count in sorted(genre_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"  {genre}: {count}")

    print("\nYear distribution:")
    for year, count in sorted(year_counts.items()):
        print(f"  {year}: {count}")


def dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    final_seen: Set[str] = set()
    for row in rows:
        isbn = normalize_isbn(str(row.get("isbn", "")))
        if not isbn or isbn in final_seen:
            continue
        row["isbn"] = isbn
        deduped.append(row)
        final_seen.add(isbn)
    return deduped


def save_current_state(rows: List[Dict[str, Any]], output_path: Path, checkpoint_path: Path) -> List[Dict[str, Any]]:
    deduped = dedupe_rows(rows)
    save_rows(deduped, output_path)
    save_rows(deduped, checkpoint_path)
    return deduped


def fetch_with_retries(
    session: requests.Session,
    url: str,
    params: Dict[str, Any],
    timeout: int = 30,
) -> Optional[requests.Response]:
    for attempt in range(1, MAX_REQUEST_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            time.sleep(REQUEST_DELAY_SECONDS)
            response.raise_for_status()
            return response
        except Exception as exc:
            if attempt < MAX_REQUEST_RETRIES:
                wait_seconds = REQUEST_DELAY_SECONDS * attempt * 2
                print(f"Request failed ({attempt}/{MAX_REQUEST_RETRIES}): {exc}. Retrying in {wait_seconds:.1f}s...")
                time.sleep(wait_seconds)
            else:
                print(f"Request failed after {MAX_REQUEST_RETRIES} attempts: {exc}")
    return None


def run_scraper() -> None:
    base_dir = Path(__file__).resolve().parent
    checkpoint_path = base_dir / "books_raw_checkpoint.csv"
    output_path = base_dir / "books.csv"

    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")

    rows, seen_isbns = load_checkpoint(checkpoint_path)
    queries = build_query_plan()

    requests_made = 0
    duplicates_skipped = 0
    new_since_checkpoint = 0
    try:
        with requests.Session() as session:
            session.headers.update({"User-Agent": "book-dataset-pipeline/1.0"})

            for label, query_params in queries:
                print(f"\nRunning query: {label}")
                for offset in range(0, QUERY_RESULT_LIMIT, PAGE_SIZE):
                    params = dict(query_params)
                    params.update({"limit": PAGE_SIZE, "offset": offset, "fields": OPENLIBRARY_FIELDS})

                    response = fetch_with_retries(session, OPENLIBRARY_SEARCH_URL, params=params, timeout=30)
                    requests_made += 1
                    if response is None:
                        continue

                    try:
                        payload = response.json()
                    except Exception as exc:
                        print(f"Skipping malformed response at offset {offset}: {exc}")
                        continue

                    docs = payload.get("docs", [])
                    num_found = int(payload.get("numFound", 0) or 0)
                    max_for_query = min(num_found, QUERY_RESULT_LIMIT)

                    if not docs:
                        break

                    for doc in docs:
                        isbn = choose_isbn(doc.get("isbn", []))
                        if not isbn:
                            continue
                        if isbn in seen_isbns:
                            duplicates_skipped += 1
                            continue

                        row = to_book_row(doc, session=session, api_key=api_key)
                        if not row:
                            continue

                        seen_isbns.add(isbn)
                        rows.append(row)
                        new_since_checkpoint += 1

                        if len(rows) % 100 == 0:
                            print(
                                f"Collected={len(rows)} | Duplicates skipped={duplicates_skipped} | Requests={requests_made}"
                            )

                        if new_since_checkpoint >= CHECKPOINT_EVERY:
                            save_rows(rows, checkpoint_path)
                            print(f"Checkpoint saved: {len(rows)} books")
                            new_since_checkpoint = 0

                    if offset + PAGE_SIZE >= max_for_query:
                        break
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        print(f"\nUnexpected error during scraping: {exc}")
    finally:
        try:
            saved_rows = save_current_state(rows, output_path, checkpoint_path)
            print(f"\nSaved current dataset to: {output_path}")
            if len(saved_rows) < 5000:
                print("Warning: target of 5000+ unique titles not reached yet. Re-run to continue growth.")
            print_final_summary(saved_rows)
        except Exception as save_exc:
            print(f"Failed to save current dataset: {save_exc}")


if __name__ == "__main__":
    run_scraper()
