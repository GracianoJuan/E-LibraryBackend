
import pandas as pd
from langdetect import detect_langs, DetectorFactory

# Untuk hasil konsisten di setiap run
DetectorFactory.seed = 0

# ─────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────
INPUT_FILE  = "books_id.csv"
OUTPUT_FILE = "books_id_cleaned.csv"

# Bahasa yang dianggap jelas bukan Indonesia
CLEARLY_FOREIGN_LANGS = {
    "en", "fr", "es", "de", "nl", "pt", "ja", "zh",
    "ko", "ar", "ru", "it", "da",
}

# Kata kunci nama penerbit Indonesia
INDONESIAN_PUBLISHER_KEYWORDS = [
    "gramedia", "erlangga", "mizan", "bentang", "balai pustaka", "kompas",
    "republika", "grasindo", "elex media", "dian rakyat", "obor", "pustaka",
    "yrama widya", "alfabeta", "rosdakarya", "bumi aksara", "rineka cipta",
    "sinar grafika", "kanisius", "diva press", "media pressindo", "falcon",
    "room to read", "asia foundation", "tiga serangkai", "moka media",
    "solomon publisher", "kayla pustaka", "bisnis2030", "noura", "lentera",
    "al-kautsar", "litera", "insani press", "gema insani", "qibla", "ufuk",
    "sagufindo", "buku kompas", "penerbit", "percetakan", "cv.",
    "andi", "deepublish", "kepustakaan populer", "kpg",
    "oncor semesta", "gadjah mada", "ugm", "ui press", "itb press", "uns press",
    "unhas", "unpad", "isi press", "lp3es", "puspa swara",
    "second chance foundation", "lembaga penelitian", "dinas pendidikan",
    "dinas kebudayaan", "departemen", "kementerian", "universitas",
    "institut", "sekolah tinggi", "lembaga", "yayasan", "badan", "pt.",
]

# Kata kunci konteks Indonesia dalam judul
INDONESIAN_CONTEXT_KEYWORDS = [
    "indonesia", "jawa", "java", "bali", "sumatera", "kalimantan", "sulawesi",
    "papua", "minangkabau", "betawi", "sunda", "melayu", "nusantara",
    "pancasila", "soekarno", "soeharto", "habibie", "jakarta", "yogyakarta",
    "gamelan", "batik", "wayang", "javanese", "balinese", "sundanese",
    "di indonesia", "of indonesia", "in indonesia", "islam di", "hukum",
]


# ─────────────────────────────────────────────
# FUNGSI PEMBANTU
# ─────────────────────────────────────────────
def has_indonesian_publisher(publisher: str) -> bool:
    """Kembalikan True jika nama penerbit mengandung kata kunci Indonesia."""
    if pd.isna(publisher):
        return False
    pub_lower = str(publisher).lower()
    return any(kw in pub_lower for kw in INDONESIAN_PUBLISHER_KEYWORDS)


def has_indonesian_context_in_title(title: str) -> bool:
    """Kembalikan True jika judul mengandung kata kunci konteks Indonesia."""
    if pd.isna(title):
        return False
    title_lower = str(title).lower()
    return any(kw in title_lower for kw in INDONESIAN_CONTEXT_KEYWORDS)


def is_clearly_foreign_title(title: str) -> bool:
    """
    Kembalikan True jika judul terdeteksi sebagai bahasa asing dengan
    probabilitas tinggi (dan tidak ada probabilitas Indonesia).
    Judul pendek (≤2 kata) membutuhkan threshold lebih tinggi (0.90)
    karena rentan salah deteksi.
    """
    if pd.isna(title) or str(title).strip() == "":
        return False
    title = str(title).strip()
    word_count = len(title.split())
    try:
        langs = detect_langs(title)
        top_lang = langs[0].lang
        top_prob = langs[0].prob
        id_prob = next((l.prob for l in langs if l.lang == "id"), 0)

        # Jika ada kemungkinan Indonesia, jangan hapus
        if id_prob > 0.15:
            return False

        threshold = 0.90 if word_count <= 2 else 0.70
        return top_lang in CLEARLY_FOREIGN_LANGS and top_prob >= threshold
    except Exception:
        return False


def should_delete_row(row) -> bool:
    """
    Kembalikan True jika baris ini harus dihapus:
    judul asing + penerbit bukan Indonesia + tidak ada konteks Indonesia.
    """
    foreign_title   = is_clearly_foreign_title(row["title"])
    indo_publisher  = has_indonesian_publisher(row["publisher"])
    indo_context    = has_indonesian_context_in_title(row["title"])
    return foreign_title and not indo_publisher and not indo_context


# ─────────────────────────────────────────────
# EKSEKUSI
# ─────────────────────────────────────────────
def main():
    print(f"Membaca file: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE)
    total_awal = len(df)
    print(f"Total baris awal : {total_awal}")

    print("Mendeteksi bahasa judul… (mungkin butuh beberapa detik)")
    mask_hapus = df.apply(should_delete_row, axis=1)

    df_hapus    = df[mask_hapus]
    df_bersih   = df[~mask_hapus]

    total_hapus = len(df_hapus)
    total_sisa  = len(df_bersih)

    print(f"\nBuku yang DIHAPUS ({total_hapus} baris):")
    print(df_hapus[["book_id", "title", "publisher"]].to_string(index=False))

    df_bersih.to_csv(OUTPUT_FILE, index=False)

    print(f"\n{'─'*60}")
    print(f"Selesai!")
    print(f"  Total awal      : {total_awal}")
    print(f"  Dihapus         : {total_hapus}")
    print(f"  Tersisa (bersih): {total_sisa}")
    print(f"  File output     : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
