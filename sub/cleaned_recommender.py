from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - notebook dependency check handles this in practice
    SentenceTransformer = None


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "books_cleaned.csv"
SENTENCE_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SENTENCE_MODEL_CACHE_DIR = BASE_DIR / "models" / "all-MiniLM-L6-v2"


def load_books(path: Path = DATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path)
    for col in ["book_id", "isbn", "title", "authors", "publisher", "genre", "description", "cover_image_url"]:
        if col not in df.columns:
            df[col] = ""
    if "published_year" not in df.columns:
        df["published_year"] = 0
    df["published_year"] = pd.to_numeric(df["published_year"], errors="coerce").fillna(0)
    return df


def sample_rows_per_genre(frame: pd.DataFrame, sample_per_genre: int = 20) -> pd.DataFrame:
    if sample_per_genre <= 0:
        return frame.reset_index(drop=True)

    prepared = frame.copy()
    prepared["genre"] = prepared["genre"].fillna("").astype(str)
    prepared["title"] = prepared["title"].fillna("").astype(str)

    sort_columns = [col for col in ["genre", "book_id", "title"] if col in prepared.columns]
    prepared = prepared.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    sampled_parts = []
    for _, group in prepared.groupby("genre", sort=False):
        sampled_parts.append(group.head(sample_per_genre))

    sampled = pd.concat(sampled_parts, ignore_index=True) if sampled_parts else prepared.iloc[0:0].copy()
    return sampled.reset_index(drop=True)


def split_by_genre_holdout(frame: pd.DataFrame, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared = frame.copy()
    prepared["genre"] = prepared["genre"].fillna("").astype(str)
    prepared["title"] = prepared["title"].fillna("").astype(str)

    sort_columns = [col for col in ["genre", "book_id", "title"] if col in prepared.columns]
    prepared = prepared.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    train_parts = []
    eval_parts = []
    for _, group in prepared.groupby("genre", sort=False):
        if len(group) <= 1:
            train_parts.append(group)
            continue

        split_index = int(np.floor(len(group) * train_ratio))
        split_index = min(max(split_index, 1), len(group) - 1)
        train_parts.append(group.iloc[:split_index])
        eval_parts.append(group.iloc[split_index:])

    train_df = pd.concat(train_parts, ignore_index=True) if train_parts else prepared.iloc[0:0].copy()
    eval_df = pd.concat(eval_parts, ignore_index=True) if eval_parts else prepared.iloc[0:0].copy()
    return train_df.reset_index(drop=True), eval_df.reset_index(drop=True)


def split_genres(value: str) -> set[str]:
    if not isinstance(value, str):
        return set()
    return {part.strip().lower() for part in value.split(";") if part.strip()}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left.union(right)
    if not union:
        return 0.0
    return len(left.intersection(right)) / len(union)


@dataclass
class CleanedGenreDescriptionRecommender:
    name: str = "cleaned_genre_description"
    df: Optional[pd.DataFrame] = None
    vectorizer: Optional[TfidfVectorizer] = None
    feature_matrix: Optional[sparse.csr_matrix] = None
    similarity_matrix: Optional[np.ndarray] = None

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        for col in ["book_id", "isbn", "title", "authors", "publisher", "genre", "description", "cover_image_url"]:
            if col not in prepared.columns:
                prepared[col] = ""
        if "published_year" not in prepared.columns:
            prepared["published_year"] = 0
        prepared["published_year"] = pd.to_numeric(prepared["published_year"], errors="coerce").fillna(0)
        prepared["title"] = prepared["title"].astype(str).fillna("").str.strip()
        prepared["authors"] = prepared["authors"].astype(str).fillna("").str.strip()
        prepared["publisher"] = prepared["publisher"].astype(str).fillna("").str.strip()
        prepared["genre"] = prepared["genre"].astype(str).fillna("").str.strip()
        prepared["description"] = prepared["description"].astype(str).fillna("").str.strip()
        prepared["text_features"] = (
            prepared["title"]
            + " "
            + prepared["authors"]
            + " "
            + prepared["publisher"]
            + " "
            + prepared["genre"]
            + " "
            + prepared["description"]
            + " "
            + prepared["published_year"].astype(int).astype(str)
        ).str.replace(r"\s+", " ", regex=True).str.strip()
        return prepared.reset_index(drop=True)

    def fit(self, df: pd.DataFrame) -> None:
        self.df = self._prepare_df(df)
        text_data = self.df["text_features"].fillna("").astype(str)

        self.vectorizer = TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True,
            min_df=1,
        )
        self.feature_matrix = self.vectorizer.fit_transform(text_data)
        self.similarity_matrix = cosine_similarity(self.feature_matrix)

    def _resolve_title_index(self, title: str) -> int:
        if self.df is None:
            raise RuntimeError("Model has not been fitted")

        key = str(title).strip().lower()
        title_series = self.df["title"].astype(str).str.lower()
        exact_matches = self.df.index[title_series == key].tolist()
        if exact_matches:
            return int(exact_matches[0])

        partial_matches = self.df.index[title_series.str.contains(key, regex=False, na=False)].tolist()
        if partial_matches:
            return int(partial_matches[0])

        raise ValueError(f"Title not found: {title}")

    def get_recommendations(self, title: str, top_n: int = 10) -> pd.DataFrame:
        if self.df is None or self.similarity_matrix is None:
            raise RuntimeError("Model has not been fitted")

        idx = self._resolve_title_index(title)
        scores = self.similarity_matrix[idx].copy()
        scores[idx] = -1.0
        top_indices = np.argsort(scores)[::-1][:top_n]

        columns = [c for c in ["book_id", "title", "authors", "publisher", "genre", "description", "cover_image_url"] if c in self.df.columns]
        recs = self.df.loc[top_indices, columns].copy()
        recs["similarity_score"] = scores[top_indices]
        return recs.reset_index(drop=True)

    def get_recommendations_for_record(self, record, top_n: int = 10) -> pd.DataFrame:
        if self.df is None or self.vectorizer is None or self.feature_matrix is None:
            raise RuntimeError("Model has not been fitted")

        if hasattr(record, "get"):
            row = record
            text_features = " ".join(
                str(row.get(col, "")) for col in ["title", "authors", "publisher", "genre", "description", "published_year"]
            )
        else:
            text_features = str(record)

        query_matrix = self.vectorizer.transform([text_features])
        scores = cosine_similarity(query_matrix, self.feature_matrix).ravel()
        top_indices = np.argsort(scores)[::-1][:top_n]

        columns = [c for c in ["book_id", "title", "authors", "publisher", "genre", "description", "cover_image_url"] if c in self.df.columns]
        recs = self.df.loc[top_indices, columns].copy()
        recs["similarity_score"] = scores[top_indices]
        return recs.reset_index(drop=True)


def _load_sentence_transformer_model(model_name: str = SENTENCE_MODEL_NAME, cache_dir: Path = SENTENCE_MODEL_CACHE_DIR):
    if SentenceTransformer is None:
        raise ImportError(
            "sentence-transformers is required for the embedding-based recommender. "
            "Install it in the active environment before running this notebook."
        )

    if cache_dir.exists() and any(cache_dir.iterdir()):
        return SentenceTransformer(str(cache_dir))

    model = SentenceTransformer(model_name)
    cache_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(cache_dir))
    return model


@dataclass
class SentenceTransformerGenreDescriptionRecommender:
    name: str = "sentence_transformer_genre_description"
    model_name: str = SENTENCE_MODEL_NAME
    model_cache_dir: Path = SENTENCE_MODEL_CACHE_DIR
    df: Optional[pd.DataFrame] = None
    model: Optional[object] = None
    embedding_matrix: Optional[np.ndarray] = None

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        for col in ["book_id", "isbn", "title", "authors", "publisher", "genre", "description", "cover_image_url"]:
            if col not in prepared.columns:
                prepared[col] = ""
        if "published_year" not in prepared.columns:
            prepared["published_year"] = 0
        prepared["published_year"] = pd.to_numeric(prepared["published_year"], errors="coerce").fillna(0)
        prepared["title"] = prepared["title"].astype(str).fillna("").str.strip()
        prepared["authors"] = prepared["authors"].astype(str).fillna("").str.strip()
        prepared["publisher"] = prepared["publisher"].astype(str).fillna("").str.strip()
        prepared["genre"] = prepared["genre"].astype(str).fillna("").str.strip()
        prepared["description"] = prepared["description"].astype(str).fillna("").str.strip()
        prepared["text_features"] = (
            prepared["title"]
            + " "
            + prepared["authors"]
            + " "
            + prepared["publisher"]
            + " "
            + prepared["genre"]
            + " "
            + prepared["description"]
            + " "
            + prepared["published_year"].astype(int).astype(str)
        ).str.replace(r"\s+", " ", regex=True).str.strip()
        return prepared.reset_index(drop=True)

    def fit(self, df: pd.DataFrame) -> None:
        self.df = self._prepare_df(df)
        text_data = self.df["text_features"].fillna("").astype(str).tolist()
        self.model = _load_sentence_transformer_model(self.model_name, self.model_cache_dir)
        self.embedding_matrix = self.model.encode(
            text_data,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def _resolve_title_index(self, title: str) -> int:
        if self.df is None:
            raise RuntimeError("Model has not been fitted")

        key = str(title).strip().lower()
        title_series = self.df["title"].astype(str).str.lower()
        exact_matches = self.df.index[title_series == key].tolist()
        if exact_matches:
            return int(exact_matches[0])

        partial_matches = self.df.index[title_series.str.contains(key, regex=False, na=False)].tolist()
        if partial_matches:
            return int(partial_matches[0])

        raise ValueError(f"Title not found: {title}")

    def get_recommendations(self, title: str, top_n: int = 10) -> pd.DataFrame:
        if self.df is None or self.embedding_matrix is None or self.model is None:
            raise RuntimeError("Model has not been fitted")

        idx = self._resolve_title_index(title)
        query_embedding = self.embedding_matrix[idx]
        scores = self.embedding_matrix @ query_embedding
        scores = np.asarray(scores).ravel().copy()
        scores[idx] = -1.0
        top_indices = np.argsort(scores)[::-1][:top_n]

        columns = [c for c in ["book_id", "title", "authors", "publisher", "genre", "description", "cover_image_url"] if c in self.df.columns]
        recs = self.df.loc[top_indices, columns].copy()
        recs["similarity_score"] = scores[top_indices]
        return recs.reset_index(drop=True)

    def get_recommendations_for_record(self, record, top_n: int = 10) -> pd.DataFrame:
        if self.df is None or self.embedding_matrix is None or self.model is None:
            raise RuntimeError("Model has not been fitted")

        if hasattr(record, "get"):
            row = record
            text_features = " ".join(
                str(row.get(col, "")) for col in ["title", "authors", "publisher", "genre", "description", "published_year"]
            )
        else:
            text_features = str(record)

        query_embedding = self.model.encode([text_features], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]
        scores = self.embedding_matrix @ query_embedding
        scores = np.asarray(scores).ravel()
        top_indices = np.argsort(scores)[::-1][:top_n]

        columns = [c for c in ["book_id", "title", "authors", "publisher", "genre", "description", "cover_image_url"] if c in self.df.columns]
        recs = self.df.loc[top_indices, columns].copy()
        recs["similarity_score"] = scores[top_indices]
        return recs.reset_index(drop=True)


def is_relevant(query_row, candidate_row, jaccard_threshold: float = 0.3) -> bool:
    query_genre = str(query_row.get("genre", "")).strip().lower()
    candidate_genre = str(candidate_row.get("genre", "")).strip().lower()
    if query_genre and query_genre == candidate_genre:
        return True

    query_subjects = split_genres(query_row.get("genre", ""))
    candidate_subjects = split_genres(candidate_row.get("genre", ""))
    return jaccard(query_subjects, candidate_subjects) >= jaccard_threshold


def precision_recall_at_k(relevance_flags: list[bool], total_relevant: int) -> tuple[float, float]:
    k = len(relevance_flags)
    hits = sum(relevance_flags)
    precision = hits / k if k else np.nan
    # Cap denominator at k: you can't retrieve more than k items,
    # so recall@k = hits / min(total_relevant, k)
    capped_relevant = min(total_relevant, k) if total_relevant > 0 else 0
    recall = hits / capped_relevant if capped_relevant > 0 else np.nan
    return precision, recall


# def precision_recall_at_k(relevance_flags: list[bool], total_relevant: int) -> tuple[float, float]:
#     k = len(relevance_flags)
#     if k == 0:
#         return np.nan, np.nan
        
#     hits = sum(relevance_flags)
    
#     # Standard Precision@K
#     precision = hits / k
    
#     # Standard Recall@K: Divided by ALL truly relevant items
#     # If total_relevant is 0, recall is conventionally 0.0 or NaN depending on your use case
#     recall = hits / total_relevant if total_relevant > 0 else 0.0
    
#     return precision, recall

def evaluate_model(
    model: CleanedGenreDescriptionRecommender,
    eval_frame: pd.DataFrame,
    train_frame: pd.DataFrame,
    k_values=(5, 10),
    jaccard_threshold: float = 0.4,
    return_per_query: bool = False,
) -> pd.DataFrame:
    """
    Evaluate a model on the evaluation frame.

    - If `return_per_query` is False (default) returns a DataFrame grouped by `K` with
      `precision_at_k` and `recall_at_k` (means over evaluation rows).
    - If `return_per_query` is True returns the raw per-query rows with columns
      `K`, `precision`, `recall` so callers can compute custom averages (e.g. average
      across all eval rows / genres).
    """
    rows = []
    train_records = list(train_frame.to_dict("records"))

    for _, query_row in eval_frame.iterrows():
        total_relevant = sum(is_relevant(query_row, candidate_row, jaccard_threshold) for candidate_row in train_records)

        for k in k_values:
            recs = model.get_recommendations_for_record(query_row, top_n=k)
            relevance_flags = [is_relevant(query_row, rec_row, jaccard_threshold) for _, rec_row in recs.iterrows()]
            precision, recall = precision_recall_at_k(relevance_flags, total_relevant)
            rows.append({"K": k, "precision": precision, "recall": recall})

    metric_frame = pd.DataFrame(rows)
    if return_per_query:
        return metric_frame

    if metric_frame.empty:
        return pd.DataFrame(columns=["K", "precision_at_k", "recall_at_k"])

    return metric_frame.groupby("K", as_index=False).agg(
        precision_at_k=("precision", "mean"),
        recall_at_k=("recall", "mean"),
    )


def summarize_k_metrics(metric_frame: pd.DataFrame) -> pd.DataFrame:
    if metric_frame.empty:
        return pd.DataFrame(columns=["average_precision", "average_recall"])

    return pd.DataFrame(
        [
            {
                "average_precision": float(metric_frame["precision_at_k"].mean()),
                "average_recall": float(metric_frame["recall_at_k"].mean()),
            }
        ]
    )


def summarize_overall_metrics(per_query_metric_frame: pd.DataFrame) -> pd.DataFrame:
    """
    Compute average precision and recall across every evaluation row (every query/genre).

    Expects the per-query metric frame returned by `evaluate_model(..., return_per_query=True)`
    with columns `K`, `precision`, `recall`.
    """
    if per_query_metric_frame.empty:
        return pd.DataFrame(columns=["average_precision", "average_recall"]) 

    return pd.DataFrame(
        [
            {
                "average_precision": float(per_query_metric_frame["precision"].mean()),
                "average_recall": float(per_query_metric_frame["recall"].mean()),
            }
        ]
    )
