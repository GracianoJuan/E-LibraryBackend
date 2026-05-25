import time
from pathlib import Path

import pandas as pd

from cbf import SentenceEmbeddingCBF, TFIDFCosine, Word2VecCBF, save_fit_times


def build_text_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    text_cols = ["subjects", "genre", "description", "title", "authors", "publisher"]
    for col in text_cols:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)

    # numeric_cols = ["pages", "ratings_avg", "publish_year", "ratings_count", "want_to_read_count", "edition_count"]
    numeric_cols = ["pages", "publish_year"]
    for col in numeric_cols:
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    out["text_features"] = (
        out["subjects"].str.strip()
        + " "
        + out["genre"].str.strip()
        + " "
        + out["description"].str.strip()
    ).str.strip()

    return out


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    books_path = base_dir / "books_cleaned.csv"
    processed_path = base_dir / "books_processed.csv"
    fit_times_path = base_dir / "model_fit_times.json"

    if not books_path.exists():
        raise FileNotFoundError(f"Missing input dataset: {books_path}")

    print(f"Reading dataset from {books_path}...")
    df = pd.read_csv(books_path)
    processed_df = build_text_features(df)
    processed_df.to_csv(processed_path, index=False)
    print(f"Saved processed dataset to {processed_path}")

    models = {
        "tfidf": TFIDFCosine(),
        "word2vec": Word2VecCBF(),
        "sentence": SentenceEmbeddingCBF(),
    }

    fit_times = {}
    for name, model in models.items():
        start = time.perf_counter()
        model.fit(processed_df)
        model.save(str(base_dir))
        elapsed = time.perf_counter() - start
        fit_times[name] = elapsed
        print(f"{name.upper()} fit + save time: {elapsed:.2f} seconds")

    save_fit_times(str(fit_times_path), fit_times)
    print(f"Saved fit times to {fit_times_path}")


if __name__ == "__main__":
    main()
