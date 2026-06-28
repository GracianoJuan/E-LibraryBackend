from __future__ import annotations
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
from scipy import sparse
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "books.csv"
TOKEN_PATTERN = re.compile(r'\b\w+\b')
STOPWORDS_SET = set(StopWordRemoverFactory().get_stop_words())
STEMMER = StemmerFactory().create_stemmer()


def _ensure_author_columns(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    if "authors" not in prepared.columns and "author" in prepared.columns:
        prepared["authors"] = prepared["author"]
    if "author" not in prepared.columns and "authors" in prepared.columns:
        prepared["author"] = prepared["authors"]
    return prepared


def tokenize_text(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    tokens = TOKEN_PATTERN.findall(value.lower())
    return [token for token in tokens if token not in STOPWORDS_SET]


def stem_tokens(tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    sentence = " ".join(tokens)
    stemmed_sentence = STEMMER.stem(sentence)
    return stemmed_sentence.split()


def prepare_recommendation_text(row: pd.Series | dict) -> str:
    if hasattr(row, "get"):
        author_value = row.get("authors", row.get("author", ""))
        parts = [
            str(row.get(col, ""))
            for col in ["title", "publisher", "genre", "description"]
        ]
        parts.insert(1, str(author_value))
    else:
        parts = [str(row)]

    text = " ".join(parts)
    tokens = stem_tokens(tokenize_text(text))
    return " ".join(tokens)


def load_books(path: Path = DATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path)
    df = _ensure_author_columns(df)
    for col in ["isbn", "title", "authors", "author", "publisher", "genre", "description", "cover_image_url"]:
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

    sort_columns = [col for col in ["genre", "title"] if col in prepared.columns]
    prepared = prepared.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    sampled_parts = []
    for _, group in prepared.groupby("genre", sort=False):
        sampled_parts.append(group.head(sample_per_genre))

    sampled = pd.concat(sampled_parts, ignore_index=True) if sampled_parts else prepared.iloc[0:0].copy()
    return sampled.reset_index(drop=True)


def sample_one_per_target_genre(
    frame: pd.DataFrame,
    target_genres: list[str] | None = None,
) -> pd.DataFrame:
    """Return one representative book per target genre.

    Each book is picked as the first match (alphabetically by title) that
    contains the target genre token (case-insensitive).  If *target_genres*
    is None the default list is used.  Genres that have no matching book are
    silently skipped.  Books are de-duplicated so the same title never
    appears twice even when it covers multiple target genres.
    """
    if target_genres is None:
        target_genres = [
            "Fiction",
            "Children",
            "Romance",
            "Mystery",
            "Horror",
            "Science Fiction",
            "Fantasy",
        ]

    prepared = frame.copy()
    prepared["genre"] = prepared["genre"].fillna("").astype(str)
    prepared["title"] = prepared["title"].fillna("").astype(str)
    prepared = prepared.sort_values("title", kind="mergesort").reset_index(drop=True)

    seen_titles: set[str] = set()
    parts: list[pd.DataFrame] = []
    for genre_token in target_genres:
        mask = prepared["genre"].str.contains(genre_token, case=False, regex=False)
        candidates = prepared[mask]
        # skip already-selected titles
        candidates = candidates[~candidates["title"].isin(seen_titles)]
        if candidates.empty:
            continue
        row = candidates.iloc[[0]].copy()
        row["sampled_for_genre"] = genre_token
        seen_titles.add(row["title"].iloc[0])
        parts.append(row)

    if not parts:
        return frame.iloc[0:0].copy()
    return pd.concat(parts, ignore_index=True)


def build_round_robin_genre_samples(frame: pd.DataFrame) -> list[pd.DataFrame]:
    """Build round-robin genre samples (1 row per genre per round).

    This function creates multiple sampled DataFrames. In each round, it picks
    at most one book for each genre token, then continues with the next
    available books for the following round.
    """
    prepared = frame.copy()
    prepared["genre"] = prepared["genre"].fillna("").astype(str)
    prepared["title"] = prepared["title"].fillna("").astype(str)
    prepared["_source_idx"] = np.arange(len(prepared))
    prepared["_genre_tokens"] = prepared["genre"].apply(lambda value: sorted(split_genres(value)))

    exploded = prepared.explode("_genre_tokens").rename(columns={"_genre_tokens": "genre_token"})
    exploded = exploded[exploded["genre_token"].astype(str).str.strip() != ""].copy()
    if exploded.empty:
        return []

    sort_columns = [col for col in ["genre_token", "book_id", "title", "_source_idx"] if col in exploded.columns]
    exploded = exploded.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    genre_order = sorted(exploded["genre_token"].dropna().astype(str).unique().tolist())
    grouped_records: dict[str, list[dict]] = {
        genre: exploded[exploded["genre_token"] == genre].to_dict("records")
        for genre in genre_order
    }
    pointers = {genre: 0 for genre in genre_order}

    rounds: list[pd.DataFrame] = []
    while True:
        picked_rows: list[dict] = []
        used_sources: set[int] = set()
        used_titles: set[str] = set()

        for genre in genre_order:
            candidates = grouped_records[genre]
            pointer = pointers[genre]

            while pointer < len(candidates):
                candidate = candidates[pointer]
                pointer += 1

                source_idx = int(candidate.get("_source_idx", -1))
                normalized_title = str(candidate.get("title", "")).strip().lower()

                if source_idx in used_sources:
                    continue
                if normalized_title and normalized_title in used_titles:
                    continue

                row = dict(candidate)
                row["genre_label"] = str(genre).title()
                picked_rows.append(row)
                used_sources.add(source_idx)
                if normalized_title:
                    used_titles.add(normalized_title)
                break

            pointers[genre] = pointer

        if not picked_rows:
            break

        round_df = pd.DataFrame(picked_rows)
        for helper_col in ["_source_idx", "genre_token"]:
            if helper_col in round_df.columns:
                round_df = round_df.drop(columns=[helper_col])
        rounds.append(round_df.reset_index(drop=True))

    return rounds


def split_by_genre_holdout(frame: pd.DataFrame, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared = frame.copy()
    prepared["genre"] = prepared["genre"].fillna("").astype(str)
    prepared["title"] = prepared["title"].fillna("").astype(str)

    sort_columns = [col for col in ["genre", "title"] if col in prepared.columns]
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
class RecommendationId:
    name: str = "description"
    df: Optional[pd.DataFrame] = None
    vectorizer: Optional[TfidfVectorizer] = None
    feature_matrix: Optional[sparse.csr_matrix] = None
    similarity_matrix: Optional[np.ndarray] = None

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = _ensure_author_columns(df)
        for col in ["isbn", "title", "authors", "author", "publisher", "genre", "description", "cover_image_url"]:
            if col not in prepared.columns:
                prepared[col] = ""
        if "published_year" not in prepared.columns:
            prepared["published_year"] = 0
        prepared["published_year"] = pd.to_numeric(prepared["published_year"], errors="coerce").fillna(0)
        prepared["title"] = prepared["title"].astype(str).fillna("").str.strip()
        prepared["authors"] = prepared["authors"].astype(str).fillna("").str.strip()
        prepared["author"] = prepared["author"].astype(str).fillna("").str.strip()
        prepared["authors"] = prepared["authors"].where(prepared["authors"] != "", prepared["author"])
        prepared["author"] = prepared["author"].where(prepared["author"] != "", prepared["authors"])
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
        ).str.replace(r"\s+", " ", regex=True).str.strip()
        prepared["text_features"] = prepared["text_features"].apply(prepare_recommendation_text)
        return prepared.reset_index(drop=True)

    def fit(self, df: pd.DataFrame) -> None:
        self.df = self._prepare_df(df)
        text_data = self.df["text_features"].fillna("").astype(str)

        self.vectorizer = TfidfVectorizer(
            max_features=100,
            ngram_range=(1, 2),
            stop_words=None,
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

        columns = [c for c in ["isbn", "title", "authors", "author", "publisher", "genre", "description"] if c in self.df.columns]
        recs = self.df.loc[top_indices, columns].copy()
        recs["similarity_score"] = scores[top_indices]
        return recs.reset_index(drop=True)

    def get_recommendations_for_record(self, record, top_n: int = 10) -> pd.DataFrame:
        if self.df is None or self.vectorizer is None or self.feature_matrix is None:
            raise RuntimeError("Model has not been fitted")

        if hasattr(record, "get"):
            text_features = prepare_recommendation_text(record)
        else:
            text_features = prepare_recommendation_text({"title": str(record)})

        query_matrix = self.vectorizer.transform([text_features])
        scores = cosine_similarity(query_matrix, self.feature_matrix).ravel()
        top_indices = np.argsort(scores)[::-1][:top_n]

        columns = [c for c in ["isbn", "title", "authors", "author", "publisher", "genre", "description"] if c in self.df.columns]
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
    capped_relevant = min(total_relevant, k) if total_relevant > 0 else 0
    recall = hits / capped_relevant if capped_relevant > 0 else np.nan
    return precision, recall


def evaluate_model(
    model: RecommendationId,
    eval_frame: pd.DataFrame,
    train_frame: pd.DataFrame,
    k_values=(5, 10),
    jaccard_threshold: float = 0.4,
    return_per_query: bool = False,
) -> pd.DataFrame:
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