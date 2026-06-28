from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from cleaned_recommender import load_books


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
DATA_PATH = BASE_DIR / "books_balanced.csv"

TOKEN_PATTERN = re.compile(r"[A-Za-z]+")


def stem_word(token: str) -> str:
    if len(token) <= 3:
        return token

    suffix_replacements = (
        ("ingly", ""),
        ("edly", ""),
        ("ing", ""),
        ("edly", ""),
        ("ed", ""),
        ("ies", "y"),
        ("ment", ""),
        ("ness", ""),
        ("ation", "ate"),
        ("ions", "ion"),
        ("s", ""),
    )

    for suffix, replacement in suffix_replacements:
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            return token[: -len(suffix)] + replacement

    return token


def build_source_text(row: pd.Series) -> str:
    parts = [
        str(row.get(column, ""))
        for column in ["title", "authors", "publisher", "genre", "description"]
    ]
    return " ".join(parts).strip()


def tokenize_text(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return TOKEN_PATTERN.findall(value.lower())


def remove_stopwords(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token not in ENGLISH_STOP_WORDS]


def stem_tokens(tokens: list[str]) -> list[str]:
    return [stem_word(token) for token in tokens]


def make_serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_serializable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(make_serializable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def build_processing_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy().reset_index(drop=True)
    prepared["source_text"] = prepared.apply(build_source_text, axis=1)
    prepared["tokenized_tokens"] = prepared["source_text"].apply(tokenize_text)
    prepared["stopword_removed_tokens"] = prepared["tokenized_tokens"].apply(remove_stopwords)
    prepared["stemmed_tokens"] = prepared["stopword_removed_tokens"].apply(stem_tokens)
    prepared["stemmed_text"] = prepared["stemmed_tokens"].apply(lambda tokens: " ".join(tokens))
    return prepared


def export_process_json(frame: pd.DataFrame, output_path: Path, token_column: str) -> None:
    records = []
    for _, row in frame.iterrows():
        records.append(
            {
                "book_id": row.get("book_id", ""),
                "title": row.get("title", ""),
                "source_text": row.get("source_text", ""),
                "tokens": row.get(token_column, []),
            }
        )
    write_json(output_path, records)


def export_processing_trace(frame: pd.DataFrame, output_path: Path) -> None:
    records = []
    for _, row in frame.iterrows():
        records.append(
            {
                "book_id": row.get("book_id", ""),
                "title": row.get("title", ""),
                "source_text": row.get("source_text", ""),
                "tokenized_tokens": row.get("tokenized_tokens", []),
                "stopword_removed_tokens": row.get("stopword_removed_tokens", []),
                "stemmed_tokens": row.get("stemmed_tokens", []),
                "stemmed_text": row.get("stemmed_text", ""),
            }
        )
    write_json(output_path, records)


def export_tfidf_csv(frame: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    vectorizer = TfidfVectorizer(
        tokenizer=str.split,
        preprocessor=None,
        lowercase=False,
        token_pattern=None,
        min_df=1,
    )
    matrix = vectorizer.fit_transform(frame["stemmed_text"].fillna("").astype(str))
    feature_names = vectorizer.get_feature_names_out()

    tfidf_frame = pd.DataFrame(matrix.toarray(), columns=feature_names)
    tfidf_frame.insert(0, "title", frame["title"].fillna("").astype(str).tolist())
    tfidf_frame.insert(0, "book_id", frame["book_id"].fillna("").astype(str).tolist())
    tfidf_frame.to_csv(output_path, index=False)
    return tfidf_frame


def export_cosine_csv(tfidf_frame: pd.DataFrame, output_path: Path) -> None:
    feature_columns = [column for column in tfidf_frame.columns if column not in {"book_id", "title"}]
    similarity_matrix = cosine_similarity(tfidf_frame[feature_columns].to_numpy())

    labels = tfidf_frame["book_id"].fillna("").astype(str).tolist()
    cosine_frame = pd.DataFrame(similarity_matrix, columns=labels)
    cosine_frame.insert(0, "book_id", labels)
    cosine_frame.to_csv(output_path, index=False)


def main() -> dict[str, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    source_frame = load_books(DATA_PATH)
    processing_frame = build_processing_frame(source_frame)

    tokenized_path = RESULTS_DIR / "tokenized.json"
    stopword_removed_path = RESULTS_DIR / "stopword_removed.json"
    stemmed_path = RESULTS_DIR / "stemmed.json"
    trace_path = RESULTS_DIR / "processing_trace.json"
    tfidf_path = RESULTS_DIR / "tfidf.csv"
    cosine_path = RESULTS_DIR / "cosine_similarity.csv"

    export_process_json(processing_frame, tokenized_path, "tokenized_tokens")
    export_process_json(processing_frame, stopword_removed_path, "stopword_removed_tokens")
    export_process_json(processing_frame, stemmed_path, "stemmed_tokens")
    export_processing_trace(processing_frame, trace_path)

    tfidf_frame = export_tfidf_csv(processing_frame, tfidf_path)
    export_cosine_csv(tfidf_frame, cosine_path)

    summary = {
        "source_rows": len(source_frame),
        "result_files": {
            "tokenized": tokenized_path.name,
            "stopword_removed": stopword_removed_path.name,
            "stemmed": stemmed_path.name,
            "processing_trace": trace_path.name,
            "tfidf": tfidf_path.name,
            "cosine_similarity": cosine_path.name,
        },
    }
    write_json(RESULTS_DIR / "summary.json", summary)

    print(f"Saved results to: {RESULTS_DIR}")
    for name, filename in summary["result_files"].items():
        print(f"- {name}: {RESULTS_DIR / filename}")

    return {
        "tokenized": tokenized_path,
        "stopword_removed": stopword_removed_path,
        "stemmed": stemmed_path,
        "processing_trace": trace_path,
        "tfidf": tfidf_path,
        "cosine_similarity": cosine_path,
    }


if __name__ == "__main__":
    main()